"""
Operations Dashboard - Lambda Handler (Multi-Project)
Main entry point using provider abstraction layer.

Routes:
  - /api/health - Health check
  - /api/config - Dashboard configuration
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
        elif path.startswith('/api/admin/'):
            if ADMIN_HANDLERS_AVAILABLE:
                query_params = event.get('queryStringParameters') or {}
                result = route_admin_request(path, method, body, query_params, user_email)
            else:
                result = {'error': 'Admin handlers not available'}

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
    # ACTION ENDPOINTS: /api/{project}/actions/...
    # -------------------------------------------------------------
    elif resource == 'actions':
        if method != 'POST':
            return {'error': 'Actions require POST method'}

        if len(parts) >= 6 and parts[4] == 'build':
            # POST /api/{project}/actions/build/{service}
            service = parts[5]
            image_tag = body.get('imageTag', 'latest')
            source_revision = body.get('sourceRevision', '')
            return ci.trigger_build(service, user_email, image_tag, source_revision)

        elif len(parts) >= 7 and parts[4] == 'deploy':
            # POST /api/{project}/actions/deploy/{env}/{service}/{action}
            env = parts[5]
            service = parts[6]
            action = parts[7] if len(parts) > 7 else 'reload'

            if action == 'reload':
                return orchestrator.force_deployment(env, service, user_email)
            elif action == 'latest':
                return ci.trigger_deploy(env, service, user_email)
            elif action == 'stop':
                return orchestrator.scale_service(env, service, 0, user_email)
            elif action == 'start':
                desired_count = int(body.get('desiredCount', 1))
                if desired_count < 1 or desired_count > 10:
                    return {'error': 'desiredCount must be between 1 and 10'}
                return orchestrator.scale_service(env, service, desired_count, user_email)
            else:
                return {'error': f'Unknown action: {action}'}

        elif len(parts) >= 6 and parts[4] == 'rds':
            # POST /api/{project}/actions/rds/{env}/{action}
            env = parts[5]
            action = parts[6] if len(parts) > 6 else None

            if not database:
                return {'error': 'Database provider not configured'}
            elif action == 'stop':
                return database.stop_database(env, user_email)
            elif action == 'start':
                return database.start_database(env, user_email)
            else:
                return {'error': 'Use stop or start for RDS action'}

        elif len(parts) >= 6 and parts[4] == 'cloudfront':
            # POST /api/{project}/actions/cloudfront/{env}/invalidate
            env = parts[5]
            action = parts[6] if len(parts) > 6 else None

            if not cdn:
                return {'error': 'CDN provider not configured'}
            elif action == 'invalidate':
                distribution_id = body.get('distributionId')
                paths = body.get('paths', ['/*'])
                if not distribution_id:
                    return {'error': 'distributionId is required'}
                return cdn.invalidate_cache(env, distribution_id, paths, user_email)
            else:
                return {'error': 'Use invalidate for CloudFront action'}

        return {'error': 'Invalid action path'}

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
