"""
Operations Dashboard - Lambda Handler (Refactored)
Main entry point using provider abstraction layer.
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


def get_providers():
    """Get configured providers"""
    config = get_config()
    return {
        'ci': ProviderFactory.get_ci_provider(config),
        'orchestrator': ProviderFactory.get_orchestrator_provider(config),
        'events': ProviderFactory.get_events_provider(config),
        'database': ProviderFactory.get_database_provider(config),
        'cdn': ProviderFactory.get_cdn_provider(config),
        'infrastructure': InfrastructureAggregator(config),
        'config': config
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
        # Get providers
        providers = get_providers()
        ci = providers['ci']
        orchestrator = providers['orchestrator']
        events_provider = providers['events']
        database = providers['database']
        cdn = providers['cdn']
        infrastructure = providers['infrastructure']
        config = providers['config']

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
        # ROUTE HANDLING
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

        # -------------------------------------------------------------
        # SERVICES ENDPOINTS
        # -------------------------------------------------------------
        elif path == '/api/services' or path == '/api/services/':
            # Get all services across all environments
            result = {
                'environments': {},
                'timestamp': datetime.utcnow().isoformat(),
                'config': config.to_dict()
            }
            for env_name, env_config in config.environments.items():
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

        elif path.startswith('/api/services/'):
            parts = path.split('/')
            if len(parts) == 4:
                # /api/services/{env}
                env = parts[3]
                services = orchestrator.get_services(env)
                env_config = config.get_environment(env)
                result = {
                    'accountId': env_config.account_id if env_config else None,
                    'services': {
                        svc_name: _format_service_summary(svc)
                        for svc_name, svc in services.items()
                        if not isinstance(svc, dict) or 'error' not in svc
                    },
                    'timestamp': datetime.utcnow().isoformat()
                }
            elif len(parts) >= 5:
                # /api/services/{env}/{service}
                env = parts[3]
                service = parts[4]
                svc = orchestrator.get_service(env, service)
                result = _format_service(svc)
            else:
                result = {'error': 'Invalid path'}

        # -------------------------------------------------------------
        # DETAILS ENDPOINT (detailed service info)
        # -------------------------------------------------------------
        elif path.startswith('/api/details/'):
            parts = path.split('/')
            if len(parts) >= 5:
                env = parts[3]
                service = parts[4]
                details = orchestrator.get_service_details(env, service)
                result = _format_service_details(details)
            else:
                result = {'error': 'Invalid path. Use /api/details/{env}/{service}'}

        # -------------------------------------------------------------
        # PIPELINES ENDPOINTS
        # -------------------------------------------------------------
        elif path.startswith('/api/pipelines/'):
            parts = path.split('/')
            if len(parts) >= 5:
                pipeline_type = parts[3]  # build or deploy
                service = parts[4]
                env = parts[5] if len(parts) > 5 else None

                if pipeline_type == 'build':
                    pipeline = ci.get_build_pipeline(service)
                    result = _format_pipeline(pipeline)
                else:
                    if not env:
                        result = {'error': 'Environment required for deploy pipeline'}
                    else:
                        pipeline = ci.get_deploy_pipeline(env, service)
                        result = _format_pipeline(pipeline)
            else:
                result = {'error': 'Invalid path'}

        # -------------------------------------------------------------
        # IMAGES ENDPOINT
        # -------------------------------------------------------------
        elif path.startswith('/api/images/'):
            parts = path.split('/')
            if len(parts) >= 4:
                service = parts[3]
                images = ci.get_images(service)
                result = {
                    'repositoryName': config.get_ecr_repo(service),
                    'images': [_format_image(img) for img in images]
                }
            else:
                result = {'error': 'Invalid path'}

        # -------------------------------------------------------------
        # METRICS ENDPOINT
        # -------------------------------------------------------------
        elif path.startswith('/api/metrics/'):
            parts = path.split('/')
            if len(parts) >= 5:
                env = parts[3]
                service = parts[4]
                result = orchestrator.get_metrics(env, service)
            else:
                result = {'error': 'Invalid path'}

        # -------------------------------------------------------------
        # INFRASTRUCTURE ENDPOINT
        # -------------------------------------------------------------
        elif path.startswith('/api/infrastructure/'):
            parts = path.split('/')
            if len(parts) >= 4:
                env = parts[3]
                # Parse query parameters
                query_params = event.get('queryStringParameters') or {}

                # Check if requesting routing details (lazy-loaded via toggle)
                if len(parts) >= 5 and parts[4] == 'routing':
                    # /api/infrastructure/{env}/routing - detailed routing/security info
                    # Parse security groups list (comma-separated) - optional filter for SGs
                    sg_str = query_params.get('securityGroups', '')
                    security_groups_list = sg_str.split(',') if sg_str else None

                    result = infrastructure.get_routing_details(env, security_groups_list)
                elif len(parts) >= 5 and parts[4] == 'enis':
                    # /api/infrastructure/{env}/enis - list ENIs with optional filters
                    # Query params: subnetId, searchIp, vpcId
                    subnet_id = query_params.get('subnetId')
                    search_ip = query_params.get('searchIp')
                    vpc_id = query_params.get('vpcId')

                    result = infrastructure.get_enis(env, vpc_id, subnet_id, search_ip)
                elif len(parts) >= 6 and parts[4] == 'security-group':
                    # /api/infrastructure/{env}/security-group/{sg_id} - get SG details with rules
                    sg_id = parts[5]
                    result = infrastructure.get_security_group(env, sg_id)
                else:
                    # /api/infrastructure/{env} - main infrastructure info

                    # Parse discoveryTags (JSON-encoded object)
                    discovery_tags = None
                    discovery_tags_str = query_params.get('discoveryTags', '')
                    if discovery_tags_str:
                        try:
                            discovery_tags = json.loads(discovery_tags_str)
                        except json.JSONDecodeError:
                            discovery_tags = None

                    # Parse services list (comma-separated)
                    services_str = query_params.get('services', '')
                    services_list = services_str.split(',') if services_str else None

                    # Parse domain_config (JSON-encoded object)
                    domain_config = None
                    domain_config_str = query_params.get('domainConfig', '')
                    if domain_config_str:
                        try:
                            domain_config = json.loads(domain_config_str)
                        except json.JSONDecodeError:
                            domain_config = None

                    # Parse databases list (comma-separated)
                    databases_str = query_params.get('databases', '')
                    databases_list = databases_str.split(',') if databases_str else None

                    # Parse caches list (comma-separated)
                    caches_str = query_params.get('caches', '')
                    caches_list = caches_str.split(',') if caches_str else None

                    result = infrastructure.get_infrastructure(
                        env,
                        discovery_tags=discovery_tags,
                        services=services_list,
                        domain_config=domain_config,
                        databases=databases_list,
                        caches=caches_list
                    )
            else:
                result = {'error': 'Invalid path. Use /api/infrastructure/{env} or /api/infrastructure/{env}/routing'}

        # -------------------------------------------------------------
        # TASKS ENDPOINT
        # -------------------------------------------------------------
        elif path.startswith('/api/tasks/'):
            parts = path.split('/')
            if len(parts) >= 6:
                env = parts[3]
                service = parts[4]
                task_id = parts[5]
                result = orchestrator.get_task_details(env, service, task_id)
            else:
                result = {'error': 'Invalid path. Use /api/tasks/{env}/{service}/{task_id}'}

        # -------------------------------------------------------------
        # LOGS ENDPOINT
        # -------------------------------------------------------------
        elif path.startswith('/api/logs/'):
            parts = path.split('/')
            if len(parts) >= 5:
                env = parts[3]
                service = parts[4]
                logs = orchestrator.get_service_logs(env, service)
                result = {
                    'environment': env,
                    'service': service,
                    'logs': logs
                }
            else:
                result = {'error': 'Invalid path'}

        # -------------------------------------------------------------
        # AUTH ENDPOINTS (Device Flow, Token, User Info)
        # -------------------------------------------------------------
        elif path.startswith('/api/auth/'):
            if AUTH_HANDLERS_AVAILABLE:
                auth_response = route_auth_request(event, context)
                if auth_response:
                    # Auth handlers return full API Gateway response
                    return auth_response
                else:
                    result = {'error': f'Unknown auth endpoint: {method} {path}'}
            else:
                result = {'error': 'Auth handlers not available'}

        # -------------------------------------------------------------
        # ADMIN ENDPOINTS (Permission Management)
        # -------------------------------------------------------------
        elif path.startswith('/api/admin/'):
            if ADMIN_HANDLERS_AVAILABLE:
                query_params = event.get('queryStringParameters') or {}
                result = route_admin_request(path, method, body, query_params, user_email)
            else:
                result = {'error': 'Admin handlers not available'}

        # -------------------------------------------------------------
        # EVENTS TIMELINE ENDPOINTS
        # -------------------------------------------------------------
        elif path.startswith('/api/events/'):
            parts = path.split('/')

            # /api/events/{env}/enrich - POST to enrich events with CloudTrail
            if len(parts) >= 5 and parts[4] == 'enrich':
                if method != 'POST':
                    result = {'error': 'Enrich endpoint requires POST with events in body'}
                else:
                    env = parts[3]
                    result = events_provider.enrich_events(body, env=env)

            # /api/events/{env}/task-diff - POST to compute task definition diffs
            elif len(parts) >= 5 and parts[4] == 'task-diff':
                if method != 'POST':
                    result = {'error': 'Task-diff endpoint requires POST with items in body'}
                else:
                    env = parts[3]
                    items = body.get('items', [])
                    result = _get_task_definition_diffs(orchestrator, config, env, items)

            elif len(parts) >= 4:
                # /api/events/{env}?hours=24&types=build,deploy&services=backend,frontend
                env = parts[3]
                query_params = event.get('queryStringParameters') or {}
                hours = int(query_params.get('hours', 24))
                hours = min(max(hours, 1), 168)  # 1h to 7 days
                types_str = query_params.get('types', '')
                event_types = types_str.split(',') if types_str else None
                services_str = query_params.get('services', '')
                services = services_str.split(',') if services_str else None
                result = events_provider.get_events(env, hours=hours, event_types=event_types, services=services)
            else:
                result = {'error': 'Invalid path. Use /api/events/{env}'}

        # -------------------------------------------------------------
        # ACTION ENDPOINTS (POST only)
        # -------------------------------------------------------------
        elif path.startswith('/api/actions/'):
            if method != 'POST':
                result = {'error': 'Actions require POST method'}
            else:
                parts = path.split('/')

                if len(parts) >= 5 and parts[3] == 'build':
                    # POST /api/actions/build/{service}
                    service = parts[4]
                    image_tag = body.get('imageTag', 'latest')
                    source_revision = body.get('sourceRevision', '')
                    result = ci.trigger_build(service, user_email, image_tag, source_revision)

                elif len(parts) >= 6 and parts[3] == 'deploy':
                    # POST /api/actions/deploy/{env}/{service}/{action}
                    env = parts[4]
                    service = parts[5]
                    action = parts[6] if len(parts) > 6 else 'reload'

                    if action == 'reload':
                        result = orchestrator.force_deployment(env, service, user_email)
                    elif action == 'latest':
                        result = ci.trigger_deploy(env, service, user_email)
                    elif action == 'stop':
                        result = orchestrator.scale_service(env, service, 0, user_email)
                    elif action == 'start':
                        desired_count = int(body.get('desiredCount', 1))
                        if desired_count < 1 or desired_count > 10:
                            result = {'error': 'desiredCount must be between 1 and 10'}
                        else:
                            result = orchestrator.scale_service(env, service, desired_count, user_email)
                    else:
                        result = {'error': f'Unknown action: {action}'}

                elif len(parts) >= 5 and parts[3] == 'rds':
                    # POST /api/actions/rds/{env}/{action}
                    env = parts[4]
                    action = parts[5] if len(parts) > 5 else None

                    if not database:
                        result = {'error': 'Database provider not configured'}
                    elif action == 'stop':
                        result = database.stop_database(env, user_email)
                    elif action == 'start':
                        result = database.start_database(env, user_email)
                    else:
                        result = {'error': 'Use stop or start for RDS action'}

                elif len(parts) >= 5 and parts[3] == 'cloudfront':
                    # POST /api/actions/cloudfront/{env}/invalidate
                    env = parts[4]
                    action = parts[5] if len(parts) > 5 else None

                    if not cdn:
                        result = {'error': 'CDN provider not configured'}
                    elif action == 'invalidate':
                        distribution_id = body.get('distributionId')
                        paths = body.get('paths', ['/*'])
                        if not distribution_id:
                            result = {'error': 'distributionId is required'}
                        else:
                            result = cdn.invalidate_cache(env, distribution_id, paths, user_email)
                    else:
                        result = {'error': 'Use invalidate for CloudFront action'}

                else:
                    result = {'error': 'Invalid action path'}

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


# =============================================================================
# TASK DEFINITION DIFF HELPER
# =============================================================================

def _get_task_definition_diffs(orchestrator, config, env: str, items: list) -> dict:
    """Get task definition diffs for a batch of events"""
    from utils.aws import get_cross_account_client

    env_config = config.get_environment(env)
    if not env_config:
        return {'error': f'Unknown environment: {env}'}

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
