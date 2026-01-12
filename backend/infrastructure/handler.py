"""
Infrastructure Lambda Handler.

Handles all infrastructure-related endpoints:
- GET /api/{project}/infrastructure/{env} - Infrastructure overview
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

import json
import traceback
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

    infrastructure = InfrastructureAggregator(config, project)
    query_params = event.get('queryStringParameters') or {}

    # Check for sub-resources
    if len(parts) >= 5:
        sub_resource = parts[4]

        if sub_resource == 'routing':
            # /api/{project}/infrastructure/{env}/routing
            sg_str = query_params.get('securityGroups', '')
            security_groups_list = sg_str.split(',') if sg_str else None
            result = infrastructure.get_routing_details(env, security_groups_list)
            return json_response(200, result)

        elif sub_resource == 'enis':
            # /api/{project}/infrastructure/{env}/enis
            subnet_id = query_params.get('subnetId')
            search_ip = query_params.get('searchIp')
            vpc_id = query_params.get('vpcId')
            result = infrastructure.get_enis(env, vpc_id, subnet_id, search_ip)
            return json_response(200, result)

        elif sub_resource == 'security-group' and len(parts) >= 6:
            # /api/{project}/infrastructure/{env}/security-group/{sg_id}
            sg_id = parts[5]
            result = infrastructure.get_security_group(env, sg_id)
            return json_response(200, result)

        elif sub_resource == 'nodes':
            # /api/{project}/infrastructure/{env}/nodes
            return handle_eks_nodes(config, project, env, query_params)

        elif sub_resource == 'k8s-services':
            # /api/{project}/infrastructure/{env}/k8s-services
            return handle_eks_services(config, project, env, query_params)

        elif sub_resource == 'ingresses':
            # /api/{project}/infrastructure/{env}/ingresses
            return handle_eks_ingresses(config, project, env, query_params)

        elif sub_resource == 'namespaces':
            # /api/{project}/infrastructure/{env}/namespaces
            return handle_eks_namespaces(config, project, env)

        return error_response('not_found', f'Unknown sub-resource: {sub_resource}', 404)

    # Main infrastructure info
    # First try query params, then fall back to config
    discovery_tags = None
    discovery_tags_str = query_params.get('discoveryTags', '')
    if discovery_tags_str:
        try:
            discovery_tags = json.loads(discovery_tags_str)
        except json.JSONDecodeError:
            pass

    # If no discovery tags from query params, get from config
    if not discovery_tags and env_config.infrastructure:
        discovery_tags = env_config.infrastructure.discovery_tags

    services_str = query_params.get('services', '')
    services_list = services_str.split(',') if services_str else None

    domain_config = None
    domain_config_str = query_params.get('domainConfig', '')
    if domain_config_str:
        try:
            domain_config = json.loads(domain_config_str)
        except json.JSONDecodeError:
            pass

    # Get databases/caches from query params or config
    databases_str = query_params.get('databases', '')
    if databases_str:
        databases_list = databases_str.split(',')
    elif env_config.infrastructure and env_config.infrastructure.databases:
        databases_list = env_config.infrastructure.databases
    else:
        databases_list = None

    caches_str = query_params.get('caches', '')
    if caches_str:
        caches_list = caches_str.split(',')
    elif env_config.infrastructure and env_config.infrastructure.caches:
        caches_list = env_config.infrastructure.caches
    else:
        caches_list = None

    result = infrastructure.get_infrastructure(
        env,
        discovery_tags=discovery_tags,
        services=services_list,
        domain_config=domain_config,
        databases=databases_list,
        caches=caches_list
    )

    return json_response(200, result)


def handle_eks_nodes(config, project: str, env: str, query_params: dict) -> Dict[str, Any]:
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

        result = {
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

        return json_response(200, result)

    except Exception as e:
        print(f"ERROR in handle_eks_nodes: {e}")
        traceback.print_exc()
        return error_response('error', str(e), 500)


def handle_eks_services(config, project: str, env: str, query_params: dict) -> Dict[str, Any]:
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

        services = orchestrator.get_k8s_services(env, namespace=namespace, components=components)

        result = {
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

        return json_response(200, result)

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_eks_ingresses(config, project: str, env: str, query_params: dict) -> Dict[str, Any]:
    """
    Handle /api/{project}/infrastructure/{env}/ingresses endpoint

    Returns list of Kubernetes Ingresses with rules and load balancer info.
    """
    try:
        orchestrator = ProviderFactory.get_orchestrator_provider(config, project)

        if not hasattr(orchestrator, 'get_ingresses'):
            return error_response('not_supported', 'Ingresses endpoint only supported for EKS', 400)

        namespace = query_params.get('namespace')
        ingresses = orchestrator.get_ingresses(env, namespace=namespace)

        result = {
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

        return json_response(200, result)

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_eks_namespaces(config, project: str, env: str) -> Dict[str, Any]:
    """
    Handle /api/{project}/infrastructure/{env}/namespaces endpoint

    Returns list of namespaces in the cluster.
    """
    try:
        orchestrator = ProviderFactory.get_orchestrator_provider(config, project)

        if not hasattr(orchestrator, 'get_namespaces'):
            return error_response('not_supported', 'Namespaces endpoint only supported for EKS', 400)

        namespaces = orchestrator.get_namespaces(env)

        result = {
            'environment': env,
            'count': len(namespaces),
            'namespaces': namespaces
        }

        return json_response(200, result)

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
