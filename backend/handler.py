"""
Operations Dashboard - Lambda Handler (Multi-Project)
Main entry point using provider abstraction layer.

Routes:
  - /api/health - Health check
  - /api/config - Dashboard configuration
  - /api/projects - List available projects
  - /api/{project}/environments - List environments for a project
  - /api/{project}/services/{env} - List services
  - /api/{project}/services/{env}/{service} - Service details
  - /api/{project}/details/{env}/{service} - Extended service details
  - /api/{project}/pipelines/{type}/{service}/{env?} - Pipeline info
  - /api/{project}/images/{service} - ECR images
  - /api/{project}/metrics/{env}/{service} - Service metrics
  - /api/{project}/infrastructure/{env} - Infrastructure overview
  - /api/{project}/tasks/{env}/{service}/{task_id} - Task details
  - /api/{project}/logs/{env}/{service} - Service logs
  - /api/{project}/events/{env} - Events timeline
  - /api/{project}/actions/* - Actions (deploy, scale, etc.)
  - /api/auth/* - Authentication endpoints
  - /api/admin/* - Admin endpoints
"""

import json
from datetime import datetime

from config import get_config
from utils.aws import get_user_email
from providers.base import ProviderFactory

# Permission checking
from auth.middleware import authorize_request
from auth.permissions import check_permission, log_audit_event
from auth.models import ForbiddenError

# Import providers to register them
from providers.ci.codepipeline import CodePipelineProvider
from providers.ci.github_actions import GitHubActionsProvider
from providers.orchestrator.ecs import ECSProvider
from providers.orchestrator.eks import EKSProvider
from providers.events.combined import CombinedEventsProvider
from providers.infrastructure.rds import RDSProvider
from providers.infrastructure.cloudfront import CloudFrontProvider
from providers.infrastructure.network import VPCProvider
from providers.infrastructure.alb import ALBProvider
from providers.infrastructure.elasticache import ElastiCacheProvider
from providers.aggregators.infrastructure import InfrastructureAggregator

# Auth handlers
try:
    from auth.admin_handlers import route_admin_request
    ADMIN_HANDLERS_AVAILABLE = True
except ImportError:
    ADMIN_HANDLERS_AVAILABLE = False

try:
    from auth.handlers import route_auth_request
    AUTH_HANDLERS_AVAILABLE = True
except ImportError:
    AUTH_HANDLERS_AVAILABLE = False


def get_providers(project: str):
    """Get configured providers for a project"""
    config = get_config()
    return {
        'ci': ProviderFactory.get_ci_provider(config, project),
        'orchestrator': ProviderFactory.get_orchestrator_provider(config, project),
        'events': ProviderFactory.get_events_provider(config, project),
        'database': ProviderFactory.get_database_provider(config, project),
        'cdn': ProviderFactory.get_cdn_provider(config, project),
        'infrastructure': InfrastructureAggregator(config, project),
        'config': config,
        'project': project
    }


def lambda_handler(event, context):
    """Main Lambda handler"""
    print(f"Event: {json.dumps(event)}")

    # Handle API Gateway v2 (HTTP API)
    path = event.get('rawPath', event.get('path', '/'))
    method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', 'GET'))

    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-SSO-User-Email',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }

    # Handle CORS preflight
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    # Get user email from SSO header
    user_email = get_user_email(event)

    try:
        config = get_config()

        # Parse JSON body for POST requests
        body = {}
        if method == 'POST' and event.get('body'):
            import base64
            body_str = event['body']
            if event.get('isBase64Encoded'):
                body_str = base64.b64decode(body_str).decode('utf-8')
            body = json.loads(body_str) if body_str else {}

        # Initialize result
        result = None

        # =================================================================
        # GLOBAL ROUTES (no project context)
        # =================================================================

        # Health check
        if path == '/api/health':
            result = {
                'status': 'ok',
                'timestamp': datetime.utcnow().isoformat(),
                'user': user_email,
                'config': config.to_dict()
            }

        # Configuration endpoint
        elif path == '/api/config':
            result = config.to_dict()

        # Auth endpoints (no project context)
        elif path.startswith('/api/auth/'):
            if AUTH_HANDLERS_AVAILABLE:
                auth_response = route_auth_request(event, context)
                if auth_response:
                    return auth_response
                else:
                    result = {'error': f'Unknown auth endpoint: {method} {path}'}
            else:
                result = {'error': 'Auth handlers not available'}

        # Admin endpoints (no project context)
        # Requires global admin, except for /api/admin/init
        elif path.startswith('/api/admin/'):
            if ADMIN_HANDLERS_AVAILABLE:
                # /api/admin/init is public (for initial setup)
                if path == '/api/admin/init':
                    query_params = event.get('queryStringParameters') or {}
                    result = route_admin_request(path, method, body, query_params, user_email)
                else:
                    # All other admin endpoints require global admin
                    try:
                        auth = authorize_request(event, require_auth=True)
                        if not auth.is_global_admin:
                            result = {'error': 'Global admin access required', 'code': 403}
                        else:
                            query_params = event.get('queryStringParameters') or {}
                            result = route_admin_request(path, method, body, query_params, user_email)
                    except Exception as e:
                        result = {'error': 'Authentication required', 'code': 401}
            else:
                result = {'error': 'Admin handlers not available'}

        # =================================================================
        # PROJECTS LISTING (global route)
        # =================================================================
        elif path == '/api/projects':
            # Return list of projects with basic info
            try:
                auth = authorize_request(event, require_auth=True)
                projects_list = []
                for project_name, project_config in config.projects.items():
                    projects_list.append({
                        'name': project_name,
                        'displayName': project_config.display_name,
                        'description': '',  # Could be added to ProjectConfig
                        'environments': list(project_config.environments.keys()),
                        'orchestrator': config.orchestrator.type if config.orchestrator else 'unknown'
                    })
                result = {'projects': projects_list}
            except Exception as e:
                result = {'error': 'Authentication required', 'code': 401}

        # =================================================================
        # PROJECT ENVIRONMENTS LISTING: /api/{project}/environments
        # =================================================================
        elif path.startswith('/api/') and path.endswith('/environments'):
            parts = path.split('/')
            if len(parts) == 4:  # /api/{project}/environments
                project_name = parts[2]
                project_config = config.get_project(project_name)
                if not project_config:
                    result = {'error': f'Unknown project: {project_name}'}
                else:
                    try:
                        auth = authorize_request(event, require_auth=True)
                        environments_list = []
                        for env_name, env_config in project_config.environments.items():
                            environments_list.append({
                                'name': env_name,
                                'type': config.orchestrator.type if config.orchestrator else 'unknown',
                                'status': env_config.status or 'active',
                                'region': env_config.region,
                                'description': ''
                            })
                        result = {'environments': environments_list}
                    except Exception as e:
                        result = {'error': 'Authentication required', 'code': 401}
            else:
                result = {'error': f'Unknown path: {path}'}

        # =================================================================
        # PROJECT-SCOPED ROUTES: /api/{project}/...
        # =================================================================
        elif path.startswith('/api/') and len(path.split('/')) >= 4:
            parts = path.split('/')
            # parts[0] = '', parts[1] = 'api', parts[2] = project, parts[3] = resource
            project = parts[2]
            resource = parts[3] if len(parts) > 3 else None

            # Validate project exists
            project_config = config.get_project(project)
            if not project_config:
                result = {'error': f'Unknown project: {project}'}
            else:
                # Get providers for this project
                providers = get_providers(project)
                ci = providers['ci']
                orchestrator = providers['orchestrator']
                events_provider = providers['events']
                database = providers['database']
                cdn = providers['cdn']
                infrastructure = providers['infrastructure']

                # Route to appropriate handler
                result = route_project_request(
                    project, resource, parts, method, body, event,
                    config, ci, orchestrator, events_provider, database, cdn, infrastructure, user_email
                )

        else:
            result = {'error': f'Unknown path: {path}'}

        status_code = 400 if result and 'error' in result else 200

        return {
            'statusCode': status_code,
            'headers': headers,
            'body': json.dumps(result, default=str)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }


def check_action_permission(event, project: str, env: str, action: str, resource: str = "*") -> tuple:
    """
    Check if user has permission to perform an action.

    Args:
        event: Lambda event (contains auth headers)
        project: Project name
        env: Environment name
        action: Action to perform (deploy, scale, restart, etc.)
        resource: Resource name (service name, etc.)

    Returns:
        (auth, error_response): auth context and None if allowed,
                               None and error dict if denied
    """
    try:
        auth = authorize_request(event, require_auth=True)
    except Exception as e:
        return None, {'error': 'Authentication required', 'code': 401}

    if not check_permission(auth, action, project, env, resource):
        log_audit_event(auth, action, project, env, resource, 'denied')
        return None, {
            'error': f'Permission denied: {action} on {project}/{env}',
            'code': 403
        }

    return auth, None


def route_project_request(project, resource, parts, method, body, event,
                          config, ci, orchestrator, events_provider, database, cdn, infrastructure, user_email):
    """Route project-scoped requests"""
    query_params = event.get('queryStringParameters') or {}

    # -------------------------------------------------------------
    # SERVICES ENDPOINTS: /api/{project}/services/...
    # -------------------------------------------------------------
    if resource == 'services':
        if len(parts) == 4:
            # /api/{project}/services - list all environments
            project_config = config.get_project(project)
            result = {
                'project': project,
                'environments': {},
                'timestamp': datetime.utcnow().isoformat()
            }
            for env_name, env_config in project_config.environments.items():
                try:
                    services = orchestrator.get_services(env_name)
                    result['environments'][env_name] = {
                        'accountId': env_config.account_id,
                        'services': {
                            svc_name: _format_service_summary(svc)
                            for svc_name, svc in services.items()
                            if not isinstance(svc, dict) or 'error' not in svc
                        }
                    }
                except Exception as e:
                    result['environments'][env_name] = {'error': str(e)}
            return result

        elif len(parts) == 5:
            # /api/{project}/services/{env}
            env = parts[4]
            env_config = config.get_environment(project, env)
            if not env_config:
                return {'error': f'Unknown environment: {env} for project {project}'}

            services = orchestrator.get_services(env)
            return {
                'project': project,
                'environment': env,
                'accountId': env_config.account_id,
                'services': {
                    svc_name: _format_service_summary(svc)
                    for svc_name, svc in services.items()
                    if not isinstance(svc, dict) or 'error' not in svc
                },
                'timestamp': datetime.utcnow().isoformat()
            }

        elif len(parts) >= 6:
            # /api/{project}/services/{env}/{service}
            env = parts[4]
            service = parts[5]
            svc = orchestrator.get_service(env, service)
            return _format_service(svc)

    # -------------------------------------------------------------
    # DETAILS ENDPOINT: /api/{project}/details/{env}/{service}
    # -------------------------------------------------------------
    elif resource == 'details':
        if len(parts) >= 6:
            env = parts[4]
            service = parts[5]
            details = orchestrator.get_service_details(env, service)
            return _format_service_details(details)
        return {'error': 'Invalid path. Use /api/{project}/details/{env}/{service}'}

    # -------------------------------------------------------------
    # PIPELINES ENDPOINTS: /api/{project}/pipelines/{type}/{service}/{env?}
    # -------------------------------------------------------------
    elif resource == 'pipelines':
        if len(parts) >= 6:
            pipeline_type = parts[4]  # build or deploy
            service = parts[5]
            env = parts[6] if len(parts) > 6 else None

            if pipeline_type == 'build':
                pipeline = ci.get_build_pipeline(service)
                return _format_pipeline(pipeline)
            else:
                if not env:
                    return {'error': 'Environment required for deploy pipeline'}
                pipeline = ci.get_deploy_pipeline(env, service)
                return _format_pipeline(pipeline)
        return {'error': 'Invalid path'}

    # -------------------------------------------------------------
    # IMAGES ENDPOINT: /api/{project}/images/{service}
    # -------------------------------------------------------------
    elif resource == 'images':
        if len(parts) >= 5:
            service = parts[4]
            images = ci.get_images(service)
            return {
                'project': project,
                'repositoryName': config.get_ecr_repo(project, service),
                'images': [_format_image(img) for img in images]
            }
        return {'error': 'Invalid path'}

    # -------------------------------------------------------------
    # METRICS ENDPOINT: /api/{project}/metrics/{env}/{service}
    # -------------------------------------------------------------
    elif resource == 'metrics':
        if len(parts) >= 6:
            env = parts[4]
            service = parts[5]
            return orchestrator.get_metrics(env, service)
        return {'error': 'Invalid path'}

    # -------------------------------------------------------------
    # INFRASTRUCTURE ENDPOINT: /api/{project}/infrastructure/{env}
    # -------------------------------------------------------------
    elif resource == 'infrastructure':
        if len(parts) >= 5:
            env = parts[4]
            env_config = config.get_environment(project, env)
            if not env_config:
                return {'error': f'Unknown environment: {env} for project {project}'}

            # Check for sub-resources
            if len(parts) >= 6:
                sub_resource = parts[5]

                if sub_resource == 'routing':
                    # /api/{project}/infrastructure/{env}/routing
                    sg_str = query_params.get('securityGroups', '')
                    security_groups_list = sg_str.split(',') if sg_str else None
                    return infrastructure.get_routing_details(env, security_groups_list)

                elif sub_resource == 'enis':
                    # /api/{project}/infrastructure/{env}/enis
                    subnet_id = query_params.get('subnetId')
                    search_ip = query_params.get('searchIp')
                    vpc_id = query_params.get('vpcId')
                    return infrastructure.get_enis(env, vpc_id, subnet_id, search_ip)

                elif sub_resource == 'security-group' and len(parts) >= 7:
                    # /api/{project}/infrastructure/{env}/security-group/{sg_id}
                    sg_id = parts[6]
                    return infrastructure.get_security_group(env, sg_id)

            # /api/{project}/infrastructure/{env} - main infrastructure info
            discovery_tags = None
            discovery_tags_str = query_params.get('discoveryTags', '')
            if discovery_tags_str:
                try:
                    discovery_tags = json.loads(discovery_tags_str)
                except json.JSONDecodeError:
                    discovery_tags = None

            services_str = query_params.get('services', '')
            services_list = services_str.split(',') if services_str else None

            domain_config = None
            domain_config_str = query_params.get('domainConfig', '')
            if domain_config_str:
                try:
                    domain_config = json.loads(domain_config_str)
                except json.JSONDecodeError:
                    domain_config = None

            databases_str = query_params.get('databases', '')
            databases_list = databases_str.split(',') if databases_str else None

            caches_str = query_params.get('caches', '')
            caches_list = caches_str.split(',') if caches_str else None

            return infrastructure.get_infrastructure(
                env,
                discovery_tags=discovery_tags,
                services=services_list,
                domain_config=domain_config,
                databases=databases_list,
                caches=caches_list
            )

        return {'error': 'Invalid path. Use /api/{project}/infrastructure/{env}'}

    # -------------------------------------------------------------
    # TASKS ENDPOINT: /api/{project}/tasks/{env}/{service}/{task_id}
    # -------------------------------------------------------------
    elif resource == 'tasks':
        if len(parts) >= 7:
            env = parts[4]
            service = parts[5]
            task_id = parts[6]
            return orchestrator.get_task_details(env, service, task_id)
        return {'error': 'Invalid path. Use /api/{project}/tasks/{env}/{service}/{task_id}'}

    # -------------------------------------------------------------
    # LOGS ENDPOINT: /api/{project}/logs/{env}/{service}
    # -------------------------------------------------------------
    elif resource == 'logs':
        if len(parts) >= 6:
            env = parts[4]
            service = parts[5]
            logs = orchestrator.get_service_logs(env, service)
            return {
                'project': project,
                'environment': env,
                'service': service,
                'logs': logs
            }
        return {'error': 'Invalid path'}

    # -------------------------------------------------------------
    # EVENTS TIMELINE: /api/{project}/events/{env}
    # -------------------------------------------------------------
    elif resource == 'events':
        # /api/{project}/events/{env}/enrich - POST to enrich events with CloudTrail
        if len(parts) >= 6 and parts[5] == 'enrich':
            if method != 'POST':
                return {'error': 'Enrich endpoint requires POST with events in body'}
            env = parts[4]
            return events_provider.enrich_events(body, env=env)

        # /api/{project}/events/{env}/task-diff - POST to compute task definition diffs
        elif len(parts) >= 6 and parts[5] == 'task-diff':
            if method != 'POST':
                return {'error': 'Task-diff endpoint requires POST with items in body'}
            env = parts[4]
            items = body.get('items', [])
            return _get_task_definition_diffs(orchestrator, config, project, env, items)

        elif len(parts) >= 5:
            # /api/{project}/events/{env}?hours=24&types=build,deploy&services=backend,frontend
            env = parts[4]
            hours = int(query_params.get('hours', 24))
            hours = min(max(hours, 1), 168)  # 1h to 7 days
            types_str = query_params.get('types', '')
            event_types = types_str.split(',') if types_str else None
            services_str = query_params.get('services', '')
            services = services_str.split(',') if services_str else None
            return events_provider.get_events(env, hours=hours, event_types=event_types, services=services)

        return {'error': 'Invalid path. Use /api/{project}/events/{env}'}

    # -------------------------------------------------------------
    # KUBERNETES ENDPOINTS: /api/{project}/k8s/{env}/...
    # Direct K8s resource access for EKS environments
    # -------------------------------------------------------------
    elif resource == 'k8s':
        if len(parts) >= 5:
            env = parts[4]
            env_config = config.get_environment(project, env)
            if not env_config:
                return {'error': f'Unknown environment: {env} for project {project}'}

            # Check if environment is EKS
            if env_config.orchestrator_type != 'eks':
                return {'error': f'Environment {env} is not EKS-based'}

            k8s_resource = parts[5] if len(parts) > 5 else 'pods'
            resource_name = parts[6] if len(parts) > 6 else None

            namespace = query_params.get('namespace')
            selector = query_params.get('selector')

            if k8s_resource == 'pods':
                # GET /api/{project}/k8s/{env}/pods?namespace=x&selector=y
                pods = orchestrator.get_pods(env, namespace=namespace, selector=selector)
                return {
                    'project': project,
                    'environment': env,
                    'pods': [_format_k8s_pod(p) for p in pods]
                }

            elif k8s_resource == 'services':
                # GET /api/{project}/k8s/{env}/services?namespace=x
                services = orchestrator.get_k8s_services(env, namespace=namespace)
                return {
                    'project': project,
                    'environment': env,
                    'services': [_format_k8s_service(s) for s in services]
                }

            elif k8s_resource == 'deployments':
                # GET /api/{project}/k8s/{env}/deployments?namespace=x
                deployments = orchestrator.get_deployments(env, namespace=namespace)
                return {
                    'project': project,
                    'environment': env,
                    'deployments': [_format_k8s_deployment(d) for d in deployments]
                }

            elif k8s_resource == 'ingresses':
                # GET /api/{project}/k8s/{env}/ingresses?namespace=x
                ingresses = orchestrator.get_ingresses(env, namespace=namespace)
                return {
                    'project': project,
                    'environment': env,
                    'ingresses': [_format_k8s_ingress(i) for i in ingresses]
                }

            elif k8s_resource == 'nodes':
                # GET /api/{project}/k8s/{env}/nodes
                include_metrics = query_params.get('metrics', 'true').lower() == 'true'
                nodes = orchestrator.get_nodes(env, include_metrics=include_metrics)
                return {
                    'project': project,
                    'environment': env,
                    'nodes': [_format_k8s_node(n) for n in nodes]
                }

            elif k8s_resource == 'namespaces':
                # GET /api/{project}/k8s/{env}/namespaces
                namespaces = orchestrator.get_namespaces(env)
                return {
                    'project': project,
                    'environment': env,
                    'namespaces': namespaces
                }

            elif k8s_resource == 'logs' and resource_name:
                # GET /api/{project}/k8s/{env}/logs/{pod}?namespace=x&container=y&tail=100
                container = query_params.get('container')
                tail = int(query_params.get('tail', 100))
                since = query_params.get('since')
                logs = orchestrator.get_pod_logs(
                    env, resource_name,
                    namespace=namespace or 'default',
                    container=container,
                    tail=tail,
                    since=since
                )
                return {
                    'project': project,
                    'environment': env,
                    'pod': resource_name,
                    'logs': logs
                }

            elif k8s_resource in ['pod', 'service', 'deployment', 'ingress', 'node'] and resource_name:
                # GET /api/{project}/k8s/{env}/{type}/{name}?namespace=x
                resource_data = orchestrator.describe_k8s_resource(
                    env, k8s_resource, resource_name,
                    namespace=namespace or 'default'
                )
                return {
                    'project': project,
                    'environment': env,
                    'resourceType': k8s_resource,
                    'name': resource_name,
                    'resource': resource_data
                }

            return {'error': f'Unknown k8s resource: {k8s_resource}'}

        return {'error': 'Invalid path. Use /api/{project}/k8s/{env}/{resource}'}

    # -------------------------------------------------------------
    # PIPELINES LIST ENDPOINT: /api/{project}/pipelines/list
    # -------------------------------------------------------------
    elif resource == 'pipelines' and len(parts) >= 5 and parts[4] == 'list':
        # GET /api/{project}/pipelines/list?prefix=x&type=build
        prefix = query_params.get('prefix')
        pipeline_type = query_params.get('type')
        pipelines = ci.list_pipelines(prefix=prefix, pipeline_type=pipeline_type)
        return {
            'project': project,
            'pipelines': [_format_pipeline_summary(p) for p in pipelines]
        }

    # -------------------------------------------------------------
    # DIAGRAM ENDPOINTS: /api/{project}/diagram/...
    # -------------------------------------------------------------
    elif resource == 'diagram':
        if len(parts) >= 5:
            action = parts[4]

            if action == 'templates':
                # GET /api/{project}/diagram/templates
                templates = _get_diagram_templates()
                return {
                    'project': project,
                    'templates': templates
                }

            elif action == 'generate' and method == 'POST':
                # POST /api/{project}/diagram/generate
                # Body: {env, outputFormat, namespaces, includeRds, includeElasticache, includeCloudfront}
                env = body.get('env')
                output_format = body.get('outputFormat', 'png')
                namespaces = body.get('namespaces', ['default'])
                include_rds = body.get('includeRds', False)
                include_elasticache = body.get('includeElasticache', False)
                include_cloudfront = body.get('includeCloudfront', False)

                if not env:
                    return {'error': 'Environment required for diagram generation'}

                env_config = config.get_environment(project, env)
                if not env_config:
                    return {'error': f'Unknown environment: {env} for project {project}'}

                try:
                    from generators.diagram import DiagramGenerator

                    generator = DiagramGenerator(
                        env_config=env_config,
                        orchestrator=orchestrator,
                        infrastructure=infrastructure,
                        namespaces=namespaces,
                        include_rds=include_rds,
                        include_elasticache=include_elasticache,
                        include_cloudfront=include_cloudfront
                    )

                    # Generate diagram and return base64 encoded
                    diagram_data = generator.generate_base64(
                        output_format=output_format,
                        env_type=env_config.orchestrator_type,
                        cluster=env_config.cluster_name
                    )

                    return {
                        'project': project,
                        'environment': env,
                        'format': output_format,
                        'data': diagram_data,
                        'filename': f'{project}-{env}-architecture.{output_format}'
                    }
                except ImportError:
                    return {'error': 'Diagram generator not available on server'}
                except Exception as e:
                    return {'error': f'Diagram generation failed: {str(e)}'}

            elif action == 'publish' and method == 'POST':
                # POST /api/{project}/diagram/publish
                # Body: {diagramData, format, confluencePage, title, space}
                auth, error = check_action_permission(event, project, '*', 'publish', 'diagram')
                if error:
                    return error

                diagram_data = body.get('diagramData')
                file_format = body.get('format', 'png')
                confluence_page = body.get('confluencePage')
                title = body.get('title')
                space = body.get('space')

                if not diagram_data or not confluence_page:
                    return {'error': 'diagramData and confluencePage are required'}

                try:
                    from publishers.confluence import ConfluencePublisher

                    confluence_config = config.confluence if hasattr(config, 'confluence') else {}
                    publisher = ConfluencePublisher.from_env_or_config(config=confluence_config)

                    page_title = title or f'Architecture - {project}'
                    result = publisher.publish_diagram_from_base64(
                        data=diagram_data,
                        file_format=file_format,
                        title=page_title,
                        parent_page_id=confluence_page,
                        space_key=space
                    )

                    log_audit_event(auth, 'publish', project, '*', 'diagram', 'success',
                                    {'page': confluence_page, 'title': page_title})
                    return {
                        'success': True,
                        'pageId': confluence_page,
                        'title': page_title
                    }
                except ImportError:
                    return {'error': 'Confluence publisher not available on server'}
                except Exception as e:
                    return {'error': f'Publish failed: {str(e)}'}

        return {'error': 'Invalid diagram path. Use /api/{project}/diagram/{templates|generate|publish}'}

    # -------------------------------------------------------------
    # ACTION ENDPOINTS: /api/{project}/actions/...
    # Permission checks: operator or admin required for all actions
    # -------------------------------------------------------------
    elif resource == 'actions':
        if method != 'POST':
            return {'error': 'Actions require POST method'}

        if len(parts) >= 6 and parts[4] == 'build':
            # POST /api/{project}/actions/build/{service}
            # Requires: deploy permission (operator/admin)
            service = parts[5]

            auth, error = check_action_permission(event, project, '*', 'deploy', service)
            if error:
                return error

            image_tag = body.get('imageTag', 'latest')
            source_revision = body.get('sourceRevision', '')
            result = ci.trigger_build(service, user_email, image_tag, source_revision)
            log_audit_event(auth, 'build', project, '*', service, 'success')
            return result

        elif len(parts) >= 7 and parts[4] == 'deploy':
            # POST /api/{project}/actions/deploy/{env}/{service}/{action}
            env = parts[5]
            service = parts[6]
            action_type = parts[7] if len(parts) > 7 else 'reload'

            # Map action type to permission
            permission_action = 'deploy' if action_type in ('reload', 'latest') else 'scale'

            auth, error = check_action_permission(event, project, env, permission_action, service)
            if error:
                return error

            if action_type == 'reload':
                result = orchestrator.force_deployment(env, service, user_email)
                log_audit_event(auth, 'restart', project, env, service, 'success')
                return result
            elif action_type == 'latest':
                result = ci.trigger_deploy(env, service, user_email)
                log_audit_event(auth, 'deploy', project, env, service, 'success')
                return result
            elif action_type == 'stop':
                result = orchestrator.scale_service(env, service, 0, user_email)
                log_audit_event(auth, 'scale', project, env, service, 'success', {'desiredCount': 0})
                return result
            elif action_type == 'start':
                desired_count = int(body.get('desiredCount', 1))
                if desired_count < 1 or desired_count > 10:
                    return {'error': 'desiredCount must be between 1 and 10'}
                result = orchestrator.scale_service(env, service, desired_count, user_email)
                log_audit_event(auth, 'scale', project, env, service, 'success', {'desiredCount': desired_count})
                return result
            else:
                return {'error': f'Unknown action: {action_type}'}

        elif len(parts) >= 6 and parts[4] == 'rds':
            # POST /api/{project}/actions/rds/{env}/{action}
            # Requires: rds-control permission (admin only)
            env = parts[5]
            action_type = parts[6] if len(parts) > 6 else None

            auth, error = check_action_permission(event, project, env, 'rds-control', 'rds')
            if error:
                return error

            if not database:
                return {'error': 'Database provider not configured'}
            elif action_type == 'stop':
                result = database.stop_database(env, user_email)
                log_audit_event(auth, 'rds-control', project, env, 'rds', 'success', {'action': 'stop'})
                return result
            elif action_type == 'start':
                result = database.start_database(env, user_email)
                log_audit_event(auth, 'rds-control', project, env, 'rds', 'success', {'action': 'start'})
                return result
            else:
                return {'error': 'Use stop or start for RDS action'}

        elif len(parts) >= 6 and parts[4] == 'cloudfront':
            # POST /api/{project}/actions/cloudfront/{env}/invalidate
            # Requires: invalidate permission (operator/admin)
            env = parts[5]
            action_type = parts[6] if len(parts) > 6 else None

            auth, error = check_action_permission(event, project, env, 'invalidate', 'cloudfront')
            if error:
                return error

            if not cdn:
                return {'error': 'CDN provider not configured'}
            elif action_type == 'invalidate':
                distribution_id = body.get('distributionId')
                paths = body.get('paths', ['/*'])
                if not distribution_id:
                    return {'error': 'distributionId is required'}
                result = cdn.invalidate_cache(env, distribution_id, paths, user_email)
                log_audit_event(auth, 'invalidate', project, env, distribution_id, 'success', {'paths': paths})
                return result
            else:
                return {'error': 'Use invalidate for CloudFront action'}

        return {'error': 'Invalid action path'}

    # -------------------------------------------------------------
    # COMPARISON ENDPOINTS: /api/{project}/comparison/...
    # Generic environment comparison (source vs destination)
    # Routes:
    #   GET /api/{project}/comparison/config - Get comparison configuration
    #   GET /api/{project}/comparison/{sourceEnv}/{destEnv}/summary - Comparison summary
    #   GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType} - Detailed comparison
    #   GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}/history - History
    # -------------------------------------------------------------
    elif resource == 'comparison':
        from providers.comparison import DynamoDBComparisonProvider

        if len(parts) < 5:
            return {'error': 'Invalid path. Use /api/{project}/comparison/{sourceEnv}/{destEnv}/summary'}

        # GET /api/{project}/comparison/config - Return comparison configuration
        if parts[4] == 'config':
            return _get_comparison_config(project, config)

        # Routes with source/dest envs
        if len(parts) < 6:
            return {'error': 'Invalid path. Use /api/{project}/comparison/{sourceEnv}/{destEnv}/summary'}

        source_env = parts[4]
        dest_env = parts[5]

        # Validate environments exist
        source_env_config = config.get_environment(project, source_env)
        dest_env_config = config.get_environment(project, dest_env)

        if not source_env_config:
            return {'error': f'Unknown source environment: {source_env} for project {project}'}
        if not dest_env_config:
            return {'error': f'Unknown destination environment: {dest_env} for project {project}'}

        # Get comparison config for this pair
        comparison_config = _get_comparison_pair_config(project, source_env, dest_env, config)
        provider = DynamoDBComparisonProvider(
            table_name=comparison_config.get('tableName'),
            region=comparison_config.get('region'),
        )

        domain = comparison_config.get('domain', 'comparison')
        target = comparison_config.get('target')
        source_label = comparison_config.get('sourceLabel', source_env)
        dest_label = comparison_config.get('destinationLabel', dest_env)

        if len(parts) == 6:
            # /api/{project}/comparison/{sourceEnv}/{destEnv} - redirect to summary
            return {'error': 'Use /api/{project}/comparison/{sourceEnv}/{destEnv}/summary'}

        sub_resource = parts[6]

        if sub_resource == 'summary':
            # GET /api/{project}/comparison/{sourceEnv}/{destEnv}/summary
            try:
                summary = provider.get_comparison_summary(
                    domain=domain,
                    target=target,
                    source_label=source_label,
                    destination_label=dest_label,
                )
                result = summary.to_dict()
                result['project'] = project
                result['sourceEnvironment'] = source_env
                result['destinationEnvironment'] = dest_env
                return result
            except Exception as e:
                return {'error': str(e)}

        else:
            # GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}
            check_type = sub_resource

            if len(parts) >= 8 and parts[7] == 'history':
                # GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}/history
                limit = int(query_params.get('limit', '50'))
                history = provider.get_comparison_history(domain, target, check_type, limit)
                return {
                    'checkType': check_type,
                    'count': len(history),
                    'history': history,
                }

            # GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}
            detail = provider.get_comparison_detail(domain, target, check_type)
            if detail is None:
                return {'error': f'No data for check type: {check_type}'}
            return detail

    return {'error': f'Unknown resource: {resource}'}


# =============================================================================
# TASK DEFINITION DIFF HELPER
# =============================================================================

def _get_task_definition_diffs(orchestrator, config, project: str, env: str, items: list) -> dict:
    """Get task definition diffs for a batch of events"""
    from utils.aws import get_cross_account_client

    env_config = config.get_environment(project, env)
    if not env_config:
        return {'error': f'Unknown environment: {env} for project {project}'}

    try:
        ecs = get_cross_account_client('ecs', env_config.account_id, env_config.region)
        results = []

        for item in items:
            current_td = item.get('taskDefinition')
            previous_td = item.get('previousTaskDefinition')
            event_id = item.get('id')

            if not current_td or not previous_td:
                results.append({'id': event_id, 'diff': None})
                continue

            try:
                # Get current task definition
                current_family = current_td.split(':')[0]
                current_revision = current_td.split(':')[-1]
                current_resp = ecs.describe_task_definition(taskDefinition=current_td)
                current_def = current_resp.get('taskDefinition', {})

                # Get previous task definition
                previous_resp = ecs.describe_task_definition(taskDefinition=previous_td)
                previous_def = previous_resp.get('taskDefinition', {})

                # Compute diff
                changes = []

                # Compare container definitions
                current_containers = {c['name']: c for c in current_def.get('containerDefinitions', [])}
                previous_containers = {c['name']: c for c in previous_def.get('containerDefinitions', [])}

                for name, current_container in current_containers.items():
                    prev_container = previous_containers.get(name, {})

                    # Image
                    current_image = current_container.get('image', '')
                    prev_image = prev_container.get('image', '')
                    if current_image != prev_image:
                        changes.append({
                            'field': 'image',
                            'label': 'Image',
                            'from': prev_image.split('/')[-1] if prev_image else None,
                            'to': current_image.split('/')[-1] if current_image else None
                        })

                    # CPU
                    if current_container.get('cpu') != prev_container.get('cpu'):
                        changes.append({
                            'field': 'cpu',
                            'label': 'CPU',
                            'from': str(prev_container.get('cpu')),
                            'to': str(current_container.get('cpu'))
                        })

                    # Memory
                    if current_container.get('memory') != prev_container.get('memory'):
                        changes.append({
                            'field': 'memory',
                            'label': 'Memory',
                            'from': str(prev_container.get('memory')),
                            'to': str(current_container.get('memory'))
                        })

                    # Environment variables count
                    current_env_count = len(current_container.get('environment', []))
                    prev_env_count = len(prev_container.get('environment', []))
                    if current_env_count != prev_env_count:
                        changes.append({
                            'field': 'environment',
                            'label': 'Env Vars',
                            'from': str(prev_env_count),
                            'to': str(current_env_count)
                        })

                    # Secrets count
                    current_secrets_count = len(current_container.get('secrets', []))
                    prev_secrets_count = len(prev_container.get('secrets', []))
                    if current_secrets_count != prev_secrets_count:
                        changes.append({
                            'field': 'secrets',
                            'label': 'Secrets',
                            'from': str(prev_secrets_count),
                            'to': str(current_secrets_count)
                        })

                results.append({
                    'id': event_id,
                    'diff': {
                        'fromRevision': previous_td.split(':')[-1],
                        'toRevision': current_revision,
                        'changes': changes
                    } if changes else None
                })

            except Exception as e:
                results.append({'id': event_id, 'diff': None, 'error': str(e)})

        return {'results': results}

    except Exception as e:
        return {'error': str(e)}


# =============================================================================
# COMPARISON HELPERS
# =============================================================================

def _get_comparison_config(project: str, config) -> dict:
    """
    Get comparison configuration for a project.

    Returns available comparison pairs and their configuration.
    Configuration can come from:
    1. Project config (comparison.pairs)
    2. Auto-generated from environments

    Args:
        project: Project name
        config: DashboardConfig instance

    Returns:
        dict with comparison configuration
    """
    project_config = config.get_project(project)
    if not project_config:
        return {'error': f'Unknown project: {project}'}

    # Get environments for this project
    environments = list(project_config.environments.keys())

    # Check if project has explicit comparison config
    # This would be in project_config if we add comparison field to ProjectConfig
    comparison_config = getattr(project_config, 'comparison', None)

    if comparison_config and comparison_config.get('pairs'):
        # Use explicit configuration
        return {
            'project': project,
            'enabled': comparison_config.get('enabled', True),
            'pairs': comparison_config.get('pairs', []),
            'environments': environments,
        }

    # Auto-generate pairs from environments
    # Group by base env (staging, preprod, production) and source type (legacy, nh)
    pairs = []
    env_groups = {}

    for env in environments:
        # Parse environment name to extract base and source
        if env.startswith('legacy-'):
            source_type = 'legacy'
            base_env = env.replace('legacy-', '')
        elif env.startswith('nh-'):
            source_type = 'nh'
            base_env = env.replace('nh-', '')
        else:
            continue  # Skip unknown patterns

        if base_env not in env_groups:
            env_groups[base_env] = {'legacy': None, 'nh': None}
        env_groups[base_env][source_type] = env

    # Create pairs for each base env that has both legacy and nh
    for base_env, sources in env_groups.items():
        if sources['legacy'] and sources['nh']:
            pairs.append({
                'id': f"{base_env}-legacy-vs-nh",
                'label': f"{base_env.title()}: Legacy vs NH",
                'source': {
                    'env': sources['legacy'],
                    'label': 'Legacy',
                },
                'destination': {
                    'env': sources['nh'],
                    'label': 'New Horizon',
                },
            })

    return {
        'project': project,
        'enabled': len(pairs) > 0,
        'pairs': pairs,
        'environments': environments,
        'allowCustomPairs': True,  # Allow selecting any env pair
    }


def _get_comparison_pair_config(project: str, source_env: str, dest_env: str, config) -> dict:
    """
    Get configuration for a specific comparison pair.

    Determines the DynamoDB keys and labels for a source/destination pair.

    Args:
        project: Project name
        source_env: Source environment name
        dest_env: Destination environment name
        config: DashboardConfig instance

    Returns:
        dict with domain, target, labels, and table configuration
    """
    # Check if project has explicit comparison config with this pair
    project_config = config.get_project(project)
    comparison_config = getattr(project_config, 'comparison', None) if project_config else None

    if comparison_config and comparison_config.get('pairs'):
        for pair in comparison_config['pairs']:
            if (pair.get('source', {}).get('env') == source_env and
                pair.get('destination', {}).get('env') == dest_env):
                # Found explicit configuration
                state_key = pair.get('stateKey', {})
                return {
                    'domain': state_key.get('domain', 'comparison'),
                    'target': state_key.get('target', f"{project}-{source_env}-vs-{dest_env}"),
                    'sourceLabel': pair.get('source', {}).get('label', source_env),
                    'destinationLabel': pair.get('destination', {}).get('label', dest_env),
                    'tableName': state_key.get('tableName'),
                    'region': state_key.get('region'),
                }

    # Auto-generate configuration
    # Extract instance from project (e.g., mro-mi2 -> mi2)
    instance = project.replace('mro-', '').lower() if project.startswith('mro-') else project.lower()

    # Determine base environment (staging, preprod, production -> stg, ppd, prd)
    env_map = {
        'integration': 'int',
        'staging': 'stg',
        'preprod': 'ppd',
        'production': 'prd',
    }

    # Extract base env from source or dest
    base_env = None
    for env in [source_env, dest_env]:
        for full, short in env_map.items():
            if full in env:
                base_env = short
                break
        if base_env:
            break

    if not base_env:
        base_env = 'comparison'

    # Determine labels
    source_label = source_env
    dest_label = dest_env
    if 'legacy' in source_env.lower():
        source_label = 'Legacy'
    if 'nh-' in dest_env.lower() or 'newhorizon' in dest_env.lower():
        dest_label = 'New Horizon'

    return {
        'domain': 'mro',  # Default domain
        'target': f"{instance}-{base_env}-comparison",
        'sourceLabel': source_label,
        'destinationLabel': dest_label,
        'tableName': None,  # Use default
        'region': None,  # Use default
    }


# =============================================================================
# FORMATTING HELPERS
# =============================================================================

def _format_service_summary(svc):
    """Format service for summary list"""
    if hasattr(svc, 'status'):
        return {
            'status': svc.status,
            'health': 'HEALTHY' if svc.running_count == svc.desired_count else 'UNHEALTHY',
            'runningCount': svc.running_count,
            'desiredCount': svc.desired_count,
            'taskDefinition': svc.task_definition.get('revision') if svc.task_definition else None,
            'image': svc.task_definition.get('image', '').split(':')[-1] if svc.task_definition else None
        }
    return svc


def _format_service(svc):
    """Format service for detailed view"""
    if hasattr(svc, 'status'):
        return {
            'environment': svc.environment,
            'service': svc.service,
            'serviceName': svc.name,
            'clusterName': svc.cluster_name,
            'status': svc.status,
            'desiredCount': svc.desired_count,
            'runningCount': svc.running_count,
            'pendingCount': svc.pending_count,
            'taskDefinition': svc.task_definition,
            'tasks': [_format_task(t) for t in svc.tasks],
            'deployments': [_format_deployment(d) for d in svc.deployments],
            'consoleUrl': svc.console_url,
            'accountId': svc.account_id
        }
    return svc


def _format_service_details(details):
    """Format service details"""
    base = _format_service(details)
    if hasattr(details, 'environment_variables'):
        base.update({
            'currentTaskDefinition': details.task_definition,
            'latestTaskDefinition': details.latest_task_definition,
            'environmentVariables': details.environment_variables,
            'secrets': details.secrets,
            'recentLogs': details.recent_logs,
            'ecsEvents': details.ecs_events,
            'deploymentState': details.deployment_state,
            'isRollingBack': details.is_rolling_back,
            'consoleUrls': details.console_urls
        })
    return base


def _format_task(task):
    """Format task/pod"""
    return {
        'taskId': task.task_id,
        'status': task.status,
        'desiredStatus': task.desired_status,
        'health': task.health,
        'revision': task.revision,
        'isLatest': task.is_latest,
        'az': task.az,
        'subnetId': task.subnet_id,
        'cpu': task.cpu,
        'memory': task.memory,
        'startedAt': task.started_at.isoformat() if task.started_at else None
    }


def _format_deployment(dep):
    """Format deployment"""
    return {
        'status': dep.status,
        'taskDefinition': dep.task_definition,
        'revision': dep.revision,
        'desiredCount': dep.desired_count,
        'runningCount': dep.running_count,
        'pendingCount': dep.pending_count,
        'rolloutState': dep.rollout_state,
        'createdAt': dep.created_at.isoformat() if dep.created_at else None,
        'updatedAt': dep.updated_at.isoformat() if dep.updated_at else None
    }


def _format_pipeline(pipeline):
    """Format pipeline"""
    if isinstance(pipeline, dict) and 'error' in pipeline:
        return pipeline
    return {
        'pipelineName': pipeline.name,
        'pipelineType': pipeline.pipeline_type,
        'service': pipeline.service,
        'environment': pipeline.environment,
        'version': pipeline.version,
        'stages': [{'name': s.name, 'status': s.status} for s in pipeline.stages],
        'lastExecution': _format_execution(pipeline.last_execution) if pipeline.last_execution else None,
        'executions': [_format_execution(e) for e in pipeline.executions],
        'buildLogs': pipeline.build_logs,
        'consoleUrl': pipeline.console_url
    }


def _format_execution(exec):
    """Format pipeline execution"""
    return {
        'executionId': exec.execution_id,
        'status': exec.status,
        'startTime': exec.started_at.isoformat() if exec.started_at else None,
        'lastUpdateTime': exec.finished_at.isoformat() if exec.finished_at else None,
        'duration': exec.duration_seconds,
        'commit': exec.commit_sha,
        'commitMessage': exec.commit_message,
        'commitAuthor': exec.commit_author,
        'commitUrl': exec.commit_url,
        'consoleUrl': exec.console_url,
        'trigger': exec.trigger_type
    }


def _format_image(img):
    """Format container image"""
    return {
        'digest': img.digest,
        'tags': img.tags,
        'pushedAt': img.pushed_at.isoformat() if img.pushed_at else None,
        'sizeBytes': img.size_bytes,
        'sizeMB': img.size_mb
    }


# =============================================================================
# KUBERNETES FORMATTING HELPERS
# =============================================================================

def _format_k8s_pod(pod):
    """Format K8s pod for API response"""
    if isinstance(pod, dict):
        return pod
    return {
        'name': pod.name,
        'namespace': pod.namespace,
        'status': pod.status,
        'ready': pod.ready,
        'restarts': pod.restarts,
        'age': pod.age,
        'ip': pod.ip,
        'node': pod.node,
        'containers': pod.containers if hasattr(pod, 'containers') else []
    }


def _format_k8s_service(svc):
    """Format K8s service for API response"""
    if isinstance(svc, dict):
        return svc
    return {
        'name': svc.name,
        'namespace': svc.namespace,
        'type': svc.service_type,
        'clusterIP': svc.cluster_ip,
        'externalIP': svc.external_ip,
        'ports': svc.ports,
        'selector': svc.selector,
        'labels': svc.labels
    }


def _format_k8s_deployment(deploy):
    """Format K8s deployment for API response"""
    if isinstance(deploy, dict):
        return deploy
    return {
        'name': deploy.name,
        'namespace': deploy.namespace,
        'ready': deploy.ready,
        'available': deploy.available,
        'upToDate': deploy.up_to_date,
        'age': deploy.age,
        'image': deploy.image if hasattr(deploy, 'image') else None
    }


def _format_k8s_ingress(ing):
    """Format K8s ingress for API response"""
    if isinstance(ing, dict):
        return ing
    return {
        'name': ing.name,
        'namespace': ing.namespace,
        'ingressClass': ing.ingress_class,
        'hosts': [r.host for r in ing.rules] if ing.rules else [],
        'address': ing.load_balancer_hostname or ing.load_balancer_ip,
        'rules': [
            {
                'host': r.host,
                'path': r.path,
                'pathType': r.path_type,
                'serviceName': r.service_name,
                'servicePort': r.service_port
            }
            for r in ing.rules
        ] if ing.rules else [],
        'tls': ing.tls,
        'annotations': ing.annotations
    }


def _format_k8s_node(node):
    """Format K8s node for API response"""
    if isinstance(node, dict):
        return node
    return {
        'name': node.name,
        'status': node.status,
        'instanceType': node.instance_type,
        'instanceTypeDisplay': node.instance_type_display,
        'zone': node.zone,
        'region': node.region,
        'nodegroup': node.nodegroup,
        'capacity': {
            'cpu': node.capacity_cpu,
            'memory': node.capacity_memory
        },
        'allocatable': {
            'cpu': node.allocatable_cpu,
            'memory': node.allocatable_memory
        },
        'usage': {
            'cpu': node.usage_cpu,
            'memory': node.usage_memory
        } if node.usage_cpu or node.usage_memory else None,
        'subnetId': node.subnet_id,
        'instanceId': node.instance_id
    }


def _format_pipeline_summary(pipeline):
    """Format pipeline for list view"""
    if isinstance(pipeline, dict):
        return pipeline
    return {
        'name': pipeline.name,
        'type': pipeline.pipeline_type,
        'service': pipeline.service,
        'status': pipeline.last_execution.status if pipeline.last_execution else 'unknown',
        'lastRun': pipeline.last_execution.started_at.isoformat() if pipeline.last_execution and pipeline.last_execution.started_at else None
    }


def _get_diagram_templates():
    """Get available diagram templates"""
    return [
        {
            'name': 'ecs-basic',
            'description': 'Basic ECS cluster with ALB and RDS',
            'resources': 'ECS, ALB, RDS'
        },
        {
            'name': 'eks-full',
            'description': 'Full EKS cluster with ingress and services',
            'resources': 'EKS, Ingress, Services, RDS'
        },
        {
            'name': 'multi-region',
            'description': 'Multi-region architecture with CloudFront',
            'resources': 'CloudFront, ALB, ECS/EKS, RDS, ElastiCache'
        },
        {
            'name': 'serverless',
            'description': 'Serverless architecture with Lambda',
            'resources': 'API Gateway, Lambda, DynamoDB, S3'
        }
    ]
