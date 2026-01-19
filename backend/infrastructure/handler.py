"""
Infrastructure Lambda Handler.

Handles all infrastructure-related endpoints:
- GET /api/{project}/infrastructure/{env} - Infrastructure overview (deprecated)
- GET /api/{project}/infrastructure/{env}/meta - Metadata (domains, accountId, orchestrator)
- GET /api/{project}/infrastructure/{env}/cloudfront - CloudFront details
- GET /api/{project}/infrastructure/{env}/alb - Load balancer details
- GET /api/{project}/infrastructure/{env}/rds - Database details
- GET /api/{project}/infrastructure/{env}/redis - Cache details
- GET /api/{project}/infrastructure/{env}/s3 - S3 buckets (CloudFront origins)
- GET /api/{project}/infrastructure/{env}/workloads - Services/Workloads
- GET /api/{project}/infrastructure/{env}/efs - EFS details
- GET /api/{project}/infrastructure/{env}/network - Network topology
- GET /api/{project}/infrastructure/{env}/routing - Routing details
- GET /api/{project}/infrastructure/{env}/enis - ENIs list
- GET /api/{project}/infrastructure/{env}/security-group/{sg_id} - SG details
- GET /api/{project}/infrastructure/{env}/nodes - EKS nodes list
- GET /api/{project}/infrastructure/{env}/k8s-services - K8s services list
- GET /api/{project}/infrastructure/{env}/ingresses - K8s ingresses list
- GET /api/{project}/infrastructure/{env}/namespaces - K8s namespaces list
- POST /api/{project}/actions/rds/{env}/{action} - RDS actions (admin only)
- POST /api/{project}/actions/cloudfront/{env}/invalidate - CloudFront invalidation

All endpoints require authentication and appropriate permissions.
"""

import hashlib
import json
import traceback
from functools import lru_cache
from typing import Dict, Any

from shared.rbac import (
    Action,
    get_auth_context,
    check_permission,
)
from shared.response import (
    json_response,
    error_response,
    get_method,
    get_path,
    get_body,
    get_query_param,
)
from app_config import get_config
from providers import ProviderFactory
from providers.aggregators.infrastructure import InfrastructureAggregator
from auth.user_management import _audit_log
from cache.dynamodb import DynamoDBCache
from cache.policies import get_ttl


@lru_cache(maxsize=1)
def _get_cache_backend() -> DynamoDBCache:
    return DynamoDBCache()


def _cache_pk(project: str, env: str) -> str:
    return f"CACHE#{project}#{env}"


def _cache_sk(resource: str, params: Dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"{resource}#{digest}"


def _should_cache(payload: Any) -> bool:
    if isinstance(payload, dict):
        if payload.get("error"):
            return False
        if len(payload) == 1:
            value = next(iter(payload.values()))
            if isinstance(value, dict) and value.get("error"):
                return False
    return True


def _fetch_with_cache(
    resource: str,
    project: str,
    env: str,
    params: Dict[str, Any],
    fetch_fn,
    force_refresh: bool = False,
):
    cache = _get_cache_backend()
    pk = _cache_pk(project, env)
    sk = _cache_sk(resource, params)
    if not force_refresh:
        cached = cache.get(pk, sk)
        if cached is not None:
            return cached, "hit"

    data = fetch_fn()
    if _should_cache(data):
        cache.set(pk, sk, data, get_ttl(resource))
    return data, "miss"


def _parse_infra_params(env_config, project_config) -> Dict[str, Any]:
    infra_config = env_config.infrastructure
    return {
        "infra_config": infra_config,
        "services": env_config.services or [],
        "topology": getattr(env_config, "topology", None),
        "service_naming": getattr(project_config, "service_naming", None),
    }


def _resolve_resource_filters(infra_config, resource: str) -> Dict[str, Any]:
    if not infra_config:
        return {"ids": None, "tags": None}

    resource_cfg = (infra_config.resources or {}).get(resource)
    ids = resource_cfg.ids if resource_cfg and resource_cfg.ids else None
    tags = resource_cfg.tags if resource_cfg and resource_cfg.tags else infra_config.default_tags or None
    return {"ids": ids, "tags": tags}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for infrastructure endpoints.
    """
    method = get_method(event)
    path = get_path(event)
    auth = get_auth_context(event)

    # Handle CORS preflight
    if method == 'OPTIONS':
        return json_response(200, {})

    # Parse path
    parts = path.strip('/').split('/')
    if len(parts) < 3:
        return error_response('invalid_path', 'Invalid path structure', 400)

    project = parts[1]
    resource = parts[2]

    # Validate project
    config = get_config()
    project_config = config.get_project(project)
    if not project_config:
        return error_response('not_found', f'Unknown project: {project}', 404)

    # Route to appropriate handler
    if resource == 'infrastructure':
        return handle_infrastructure(event, auth, project, parts, config)
    elif resource == 'actions' and len(parts) >= 4:
        if parts[3] == 'rds':
            return handle_rds_actions(event, auth, project, parts, config)
        elif parts[3] == 'cloudfront':
            return handle_cloudfront_actions(event, auth, project, parts, config)

    return error_response('not_found', f'Unknown infrastructure endpoint: {path}', 404)


def handle_infrastructure(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/infrastructure/... endpoints
    Path: /api/{project}/infrastructure/{env}/{sub_resource?}/{id?}
    Index:  0     1            2          3        4           5
    """
    if len(parts) < 4:
        return error_response('invalid_path', 'Use /api/{project}/infrastructure/{env}', 400)

    env = parts[3]

    # Check read permission
    if not check_permission(auth, Action.READ, project, env):
        return error_response('forbidden', f'Permission denied: read on {project}/{env}', 403)

    env_config = config.get_environment(project, env)
    if not env_config:
        return error_response('not_found', f'Unknown environment: {env} for project {project}', 404)

    project_config = config.get_project(project)
    infrastructure = InfrastructureAggregator(config, project)
    query_params = event.get('queryStringParameters') or {}
    force_refresh = query_params.get('force', 'false').lower() == 'true'
    infra_params = _parse_infra_params(env_config, project_config)

    # Check for sub-resources
    if len(parts) >= 5:
        sub_resource = parts[4]

        if sub_resource in {'meta', 'cloudfront', 'alb', 'rds', 'redis', 's3', 'workloads', 'efs', 'network'}:
            return handle_infrastructure_resource(
                infrastructure,
                project,
                env,
                sub_resource,
                infra_params,
                force_refresh
            )

        if sub_resource == 'routing':
            # /api/{project}/infrastructure/{env}/routing
            sg_str = query_params.get('securityGroups', '')
            security_groups_list = sg_str.split(',') if sg_str else None
            resource_filters = _resolve_resource_filters(infra_params["infra_config"], "network")
            vpc_id = query_params.get('vpcId') or (resource_filters["ids"][0] if resource_filters["ids"] else None)
            discovery_tags = resource_filters["tags"]

            params = {
                "securityGroups": security_groups_list,
                "vpcId": vpc_id,
                "discoveryTags": discovery_tags,
            }

            def fetch():
                return infrastructure.get_routing_details(
                    env,
                    security_groups_list,
                    vpc_id=vpc_id,
                    discovery_tags=discovery_tags
                )

            data, cache_status = _fetch_with_cache(
                "routing",
                project,
                env,
                params,
                fetch,
                force_refresh
            )
            return json_response(200, data, headers={"X-Cache": cache_status})

        elif sub_resource == 'enis':
            # /api/{project}/infrastructure/{env}/enis
            subnet_id = query_params.get('subnetId')
            search_ip = query_params.get('searchIp')
            vpc_id = query_params.get('vpcId')
            params = {
                "vpcId": vpc_id,
                "subnetId": subnet_id,
                "searchIp": search_ip,
            }

            def fetch():
                return infrastructure.get_enis(env, vpc_id, subnet_id, search_ip)

            data, cache_status = _fetch_with_cache(
                "enis",
                project,
                env,
                params,
                fetch,
                force_refresh
            )
            return json_response(200, data, headers={"X-Cache": cache_status})

        elif sub_resource == 'security-group' and len(parts) >= 6:
            # /api/{project}/infrastructure/{env}/security-group/{sg_id}
            sg_id = parts[5]
            params = {"sgId": sg_id}

            def fetch():
                return infrastructure.get_security_group(env, sg_id)

            data, cache_status = _fetch_with_cache(
                "security-group",
                project,
                env,
                params,
                fetch,
                force_refresh
            )
            return json_response(200, data, headers={"X-Cache": cache_status})

        elif sub_resource == 'nodes':
            # /api/{project}/infrastructure/{env}/nodes
            return handle_eks_nodes(config, project, env, query_params, force_refresh)

        elif sub_resource == 'k8s-services':
            # /api/{project}/infrastructure/{env}/k8s-services
            return handle_eks_services(config, project, env, query_params, force_refresh)

        elif sub_resource == 'ingresses':
            # /api/{project}/infrastructure/{env}/ingresses
            return handle_eks_ingresses(config, project, env, query_params, force_refresh)

        elif sub_resource == 'namespaces':
            # /api/{project}/infrastructure/{env}/namespaces
            return handle_eks_namespaces(config, project, env, force_refresh)

        return error_response('not_found', f'Unknown sub-resource: {sub_resource}', 404)

    # Main infrastructure info (deprecated)
    result = infrastructure.get_infrastructure(
        env,
        services=infra_params["services"],
        infra_config=infra_params["infra_config"],
    )

    headers = {
        "Deprecation": "true",
        "X-Deprecation-Notice": "Use /api/{project}/infrastructure/{env}/<resource> endpoints instead.",
    }

    result["deprecated"] = True
    result["deprecationMessage"] = "Use /api/{project}/infrastructure/{env}/<resource> endpoints instead."
    return json_response(200, result, headers=headers)


def handle_infrastructure_resource(
    infrastructure: InfrastructureAggregator,
    project: str,
    env: str,
    resource: str,
    infra_params: Dict[str, Any],
    force_refresh: bool
) -> Dict[str, Any]:
    resource_filters = _resolve_resource_filters(infra_params["infra_config"], resource)
    params = {
        "resource": resource,
        "ids": resource_filters["ids"],
        "tags": resource_filters["tags"],
        "services": infra_params.get("services"),
        "serviceNaming": infra_params.get("service_naming"),
    }
    if resource == "meta" and infra_params.get("topology"):
        params["topology"] = infra_params.get("topology")

    def fetch():
        result = infrastructure.get_infrastructure(
            env,
            services=infra_params["services"],
            infra_config=infra_params["infra_config"],
            resources=[resource],
        )
        if resource == "meta":
            return {
                "environment": result.get("environment"),
                "accountId": result.get("accountId"),
                "domains": result.get("domains"),
                "orchestrator": result.get("orchestrator"),
                "topology": infra_params.get("topology"),
            }
        if resource == "s3":
            return {"s3Buckets": result.get("s3Buckets", [])}
        if resource == "workloads":
            return {
                "workloads": result.get("workloads"),
                "services": result.get("services"),
            }
        return {resource: result.get(resource)}

    data, cache_status = _fetch_with_cache(
        resource,
        project,
        env,
        params,
        fetch,
        force_refresh
    )
    return json_response(200, data, headers={"X-Cache": cache_status})


def handle_eks_nodes(config, project: str, env: str, query_params: dict, force_refresh: bool) -> Dict[str, Any]:
    """
    Handle /api/{project}/infrastructure/{env}/nodes endpoint

    Returns list of EKS nodes with instance details, capacity, metrics, and optionally pods.

    Query params:
        includeMetrics: bool (default: true) - Include CPU/memory metrics
        includePods: bool (default: false) - Include pods running on each node
        namespace: str (optional) - Filter pods by namespace
    """
    try:
        orchestrator = ProviderFactory.get_orchestrator_provider(config, project)

        # Check if it's EKS provider
        if not hasattr(orchestrator, 'get_nodes'):
            return error_response('not_supported', 'Nodes endpoint only supported for EKS', 400)

        include_metrics = query_params.get('includeMetrics', 'true').lower() == 'true'
        include_pods = query_params.get('includePods', 'false').lower() == 'true'
        namespace = query_params.get('namespace')

        params = {
            "includeMetrics": include_metrics,
            "includePods": include_pods,
            "namespace": namespace,
        }

        def fetch():
            nodes = orchestrator.get_nodes(
                env,
                include_metrics=include_metrics,
                include_pods=include_pods,
                namespace=namespace
            )

            # Helper to parse K8s resource quantities for summary
            def parse_cpu(cpu_str):
                """Parse CPU string to millicores (int)"""
                if not cpu_str:
                    return 0
                if cpu_str.endswith('n'):
                    return int(cpu_str[:-1]) // 1000000
                elif cpu_str.endswith('m'):
                    return int(cpu_str[:-1])
                else:
                    return int(cpu_str) * 1000

            def parse_memory(mem_str):
                """Parse memory string to bytes (int)"""
                if not mem_str:
                    return 0
                if mem_str.endswith('Ki'):
                    return int(mem_str[:-2]) * 1024
                elif mem_str.endswith('Mi'):
                    return int(mem_str[:-2]) * 1024 * 1024
                elif mem_str.endswith('Gi'):
                    return int(mem_str[:-2]) * 1024 * 1024 * 1024
                elif mem_str.endswith('Ti'):
                    return int(mem_str[:-2]) * 1024 * 1024 * 1024 * 1024
                else:
                    return int(mem_str)

            def format_memory(bytes_val):
                """Format bytes to human readable"""
                if bytes_val >= 1024 * 1024 * 1024:
                    return f"{bytes_val // (1024 * 1024 * 1024)}Gi"
                elif bytes_val >= 1024 * 1024:
                    return f"{bytes_val // (1024 * 1024)}Mi"
                else:
                    return f"{bytes_val // 1024}Ki"

            # Calculate summary
            nodes_by_zone = {}
            nodes_by_nodegroup = {}
            total_capacity_cpu = 0
            total_capacity_memory = 0
            total_capacity_pods = 0
            total_allocatable_cpu = 0
            total_allocatable_memory = 0
            total_allocatable_pods = 0
            total_usage_cpu = 0
            total_usage_memory = 0
            total_pod_count = 0
            ready_nodes = 0

            for node in nodes:
                # Count by zone
                zone = node.zone or 'unknown'
                nodes_by_zone[zone] = nodes_by_zone.get(zone, 0) + 1

                # Count by nodegroup
                nodegroup = node.nodegroup or 'unknown'
                nodes_by_nodegroup[nodegroup] = nodes_by_nodegroup.get(nodegroup, 0) + 1

                # Sum capacities
                total_capacity_cpu += parse_cpu(node.capacity_cpu)
                total_capacity_memory += parse_memory(node.capacity_memory)
                total_capacity_pods += node.capacity_pods or 0
                total_allocatable_cpu += parse_cpu(node.allocatable_cpu)
                total_allocatable_memory += parse_memory(node.allocatable_memory)
                total_allocatable_pods += node.allocatable_pods or 0
                total_usage_cpu += parse_cpu(node.usage_cpu)
                total_usage_memory += parse_memory(node.usage_memory)
                total_pod_count += node.pod_count

                if node.status == 'Ready':
                    ready_nodes += 1

            # Calculate utilization percentages
            cpu_utilization = (total_usage_cpu / total_allocatable_cpu * 100) if total_allocatable_cpu > 0 else 0
            memory_utilization = (total_usage_memory / total_allocatable_memory * 100) if total_allocatable_memory > 0 else 0

            # Convert dataclasses to dicts for JSON serialization
            nodes_data = []
            for node in nodes:
                node_dict = {
                    'name': node.name,
                    'instanceType': node.instance_type,
                    'instanceTypeDisplay': node.instance_type_display,
                    'zone': node.zone,
                    'region': node.region,
                    'nodegroup': node.nodegroup,
                    'status': node.status,
                    'capacity': {
                        'cpu': node.capacity_cpu,
                        'memory': node.capacity_memory,
                        'pods': node.capacity_pods
                    },
                    'allocatable': {
                        'cpu': node.allocatable_cpu,
                        'memory': node.allocatable_memory,
                        'pods': node.allocatable_pods
                    },
                    'usage': {
                        'cpu': node.usage_cpu,
                        'memory': node.usage_memory
                    } if node.usage_cpu or node.usage_memory else None,
                    'podCount': node.pod_count,
                    'subnetId': node.subnet_id,
                    'instanceId': node.instance_id,
                    'labels': node.labels
                }

                # Calculate node utilization
                node_alloc_cpu = parse_cpu(node.allocatable_cpu)
                node_usage_cpu = parse_cpu(node.usage_cpu)
                node_alloc_mem = parse_memory(node.allocatable_memory)
                node_usage_mem = parse_memory(node.usage_memory)

                node_dict['utilizationPercent'] = {
                    'cpu': round(node_usage_cpu / node_alloc_cpu * 100, 1) if node_alloc_cpu > 0 else 0,
                    'memory': round(node_usage_mem / node_alloc_mem * 100, 1) if node_alloc_mem > 0 else 0,
                    'pods': round(node.pod_count / node.allocatable_pods * 100, 1) if node.allocatable_pods else 0
                }

                # Include pods if requested
                if include_pods and node.pods:
                    node_dict['pods'] = [
                        {
                            'name': pod.name,
                            'namespace': pod.namespace,
                            'component': pod.component,
                            'status': pod.status,
                            'ready': pod.ready,
                            'restarts': pod.restarts,
                            'requests': {
                                'cpu': pod.requests_cpu,
                                'memory': pod.requests_memory
                            } if pod.requests_cpu or pod.requests_memory else None,
                            'usage': {
                                'cpu': pod.usage_cpu,
                                'memory': pod.usage_memory
                            } if pod.usage_cpu or pod.usage_memory else None
                        }
                        for pod in node.pods
                    ]

                nodes_data.append(node_dict)

            return {
                'environment': env,
                'count': len(nodes),
                'summary': {
                    'totalNodes': len(nodes),
                    'readyNodes': ready_nodes,
                    'nodesByZone': nodes_by_zone,
                    'nodesByNodegroup': nodes_by_nodegroup,
                    'totalCapacity': {
                        'cpu': f"{total_capacity_cpu}m",
                        'memory': format_memory(total_capacity_memory),
                        'pods': total_capacity_pods
                    },
                    'totalAllocatable': {
                        'cpu': f"{total_allocatable_cpu}m",
                        'memory': format_memory(total_allocatable_memory),
                        'pods': total_allocatable_pods
                    },
                    'totalUsage': {
                        'cpu': f"{total_usage_cpu}m",
                        'memory': format_memory(total_usage_memory),
                        'pods': total_pod_count
                    },
                    'utilizationPercent': {
                        'cpu': round(cpu_utilization, 1),
                        'memory': round(memory_utilization, 1),
                        'pods': round(total_pod_count / total_allocatable_pods * 100, 1) if total_allocatable_pods > 0 else 0
                    }
                },
                'nodes': nodes_data
            }

        data, cache_status = _fetch_with_cache(
            "nodes",
            project,
            env,
            params,
            fetch,
            force_refresh
        )
        return json_response(200, data, headers={"X-Cache": cache_status})

    except Exception as e:
        print(f"ERROR in handle_eks_nodes: {e}")
        traceback.print_exc()
        return error_response('error', str(e), 500)


def handle_eks_services(config, project: str, env: str, query_params: dict, force_refresh: bool) -> Dict[str, Any]:
    """
    Handle /api/{project}/infrastructure/{env}/k8s-services endpoint

    Returns list of Kubernetes Services (ClusterIP, LoadBalancer, etc.)
    """
    try:
        orchestrator = ProviderFactory.get_orchestrator_provider(config, project)

        if not hasattr(orchestrator, 'get_k8s_services'):
            return error_response('not_supported', 'K8s services endpoint only supported for EKS', 400)

        namespace = query_params.get('namespace')
        components_str = query_params.get('components', '')
        components = components_str.split(',') if components_str else None

        params = {
            "namespace": namespace,
            "components": components,
        }

        def fetch():
            services = orchestrator.get_k8s_services(env, namespace=namespace, components=components)
            return {
                'environment': env,
                'namespace': namespace,
                'count': len(services),
                'services': [
                    {
                        'name': svc.name,
                        'namespace': svc.namespace,
                        'type': svc.service_type,
                        'clusterIp': svc.cluster_ip,
                        'externalIp': svc.external_ip,
                        'ports': svc.ports,
                        'selector': svc.selector,
                        'labels': svc.labels
                    }
                    for svc in services
                ]
            }

        data, cache_status = _fetch_with_cache(
            "k8s-services",
            project,
            env,
            params,
            fetch,
            force_refresh
        )
        return json_response(200, data, headers={"X-Cache": cache_status})

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_eks_ingresses(config, project: str, env: str, query_params: dict, force_refresh: bool) -> Dict[str, Any]:
    """
    Handle /api/{project}/infrastructure/{env}/ingresses endpoint

    Returns list of Kubernetes Ingresses with rules and load balancer info.
    """
    try:
        orchestrator = ProviderFactory.get_orchestrator_provider(config, project)

        if not hasattr(orchestrator, 'get_ingresses'):
            return error_response('not_supported', 'Ingresses endpoint only supported for EKS', 400)

        namespace = query_params.get('namespace')

        params = {"namespace": namespace}

        def fetch():
            ingresses = orchestrator.get_ingresses(env, namespace=namespace)
            return {
                'environment': env,
                'namespace': namespace,
                'count': len(ingresses),
                'ingresses': [
                    {
                        'name': ing.name,
                        'namespace': ing.namespace,
                        'ingressClass': ing.ingress_class,
                        'rules': [
                            {
                                'host': rule.host,
                                'path': rule.path,
                                'pathType': rule.path_type,
                                'serviceName': rule.service_name,
                                'servicePort': rule.service_port
                            }
                            for rule in ing.rules
                        ],
                        'tls': ing.tls,
                        'loadBalancer': {
                            'hostname': ing.load_balancer_hostname,
                            'ip': ing.load_balancer_ip
                        } if ing.load_balancer_hostname or ing.load_balancer_ip else None,
                        'annotations': ing.annotations,
                        'labels': ing.labels
                    }
                    for ing in ingresses
                ]
            }

        data, cache_status = _fetch_with_cache(
            "ingresses",
            project,
            env,
            params,
            fetch,
            force_refresh
        )
        return json_response(200, data, headers={"X-Cache": cache_status})

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_eks_namespaces(config, project: str, env: str, force_refresh: bool) -> Dict[str, Any]:
    """
    Handle /api/{project}/infrastructure/{env}/namespaces endpoint

    Returns list of namespaces in the cluster.
    """
    try:
        orchestrator = ProviderFactory.get_orchestrator_provider(config, project)

        if not hasattr(orchestrator, 'get_namespaces'):
            return error_response('not_supported', 'Namespaces endpoint only supported for EKS', 400)

        def fetch():
            namespaces = orchestrator.get_namespaces(env)
            return {
                'environment': env,
                'count': len(namespaces),
                'namespaces': namespaces
            }

        data, cache_status = _fetch_with_cache(
            "namespaces",
            project,
            env,
            {},
            fetch,
            force_refresh
        )
        return json_response(200, data, headers={"X-Cache": cache_status})

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_rds_actions(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/actions/rds/{env}/{action} endpoints

    Requires RDS_CONTROL permission (admin only)
    """
    method = get_method(event)
    if method != 'POST':
        return error_response('method_not_allowed', 'POST required', 405)

    if len(parts) < 6:
        return error_response('invalid_path', 'Use /api/{project}/actions/rds/{env}/{action}', 400)

    env = parts[4]
    action_type = parts[5]

    # Check RDS control permission (admin only)
    if not check_permission(auth, Action.RDS_CONTROL, project, env):
        return error_response(
            'forbidden',
            f'Permission denied: rds-control on {project}/{env} (admin required)',
            403
        )

    email = auth.email if auth else 'unknown'
    database = ProviderFactory.get_database_provider(config, project)

    if not database:
        return error_response('not_configured', 'Database provider not configured', 400)

    # Audit log start
    _audit_log(email, f'rds_{action_type}', {
        'project': project,
        'env': env,
    }, 'started')

    try:
        if action_type == 'stop':
            result = database.stop_database(env, email)
        elif action_type == 'start':
            result = database.start_database(env, email)
        else:
            return error_response('invalid_action', 'Use stop or start for RDS action', 400)

        _audit_log(email, f'rds_{action_type}', {
            'project': project,
            'env': env,
        }, 'success')

        return json_response(200, result)

    except Exception as e:
        _audit_log(email, f'rds_{action_type}', {
            'project': project,
            'env': env,
            'error': str(e),
        }, 'failed')

        return error_response('action_failed', str(e), 500)


def handle_cloudfront_actions(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/actions/cloudfront/{env}/invalidate endpoint

    Requires INVALIDATE permission (operator/admin)
    """
    method = get_method(event)
    if method != 'POST':
        return error_response('method_not_allowed', 'POST required', 405)

    if len(parts) < 6:
        return error_response('invalid_path', 'Use /api/{project}/actions/cloudfront/{env}/invalidate', 400)

    env = parts[4]
    action_type = parts[5]

    if action_type != 'invalidate':
        return error_response('invalid_action', 'Use invalidate for CloudFront action', 400)

    # Check invalidate permission
    if not check_permission(auth, Action.INVALIDATE, project, env):
        return error_response(
            'forbidden',
            f'Permission denied: invalidate on {project}/{env}',
            403
        )

    email = auth.email if auth else 'unknown'
    body = get_body(event)
    cdn = ProviderFactory.get_cdn_provider(config, project)

    if not cdn:
        return error_response('not_configured', 'CDN provider not configured', 400)

    distribution_id = body.get('distributionId')
    paths = body.get('paths', ['/*'])

    if not distribution_id:
        return error_response('validation_error', 'distributionId is required', 400)

    # Audit log start
    _audit_log(email, 'cloudfront_invalidate', {
        'project': project,
        'env': env,
        'distributionId': distribution_id,
        'paths': paths,
    }, 'started')

    try:
        result = cdn.invalidate_cache(env, distribution_id, paths, email)

        _audit_log(email, 'cloudfront_invalidate', {
            'project': project,
            'env': env,
            'distributionId': distribution_id,
        }, 'success')

        return json_response(200, result)

    except Exception as e:
        _audit_log(email, 'cloudfront_invalidate', {
            'project': project,
            'env': env,
            'error': str(e),
        }, 'failed')

        return error_response('action_failed', str(e), 500)
