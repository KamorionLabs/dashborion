"""
Services Lambda Handler.

Handles all service-related endpoints:
- GET /api/projects - List available projects
- GET /api/{project}/environments - List environments for a project
- GET /api/{project}/services/{env} - List services
- GET /api/{project}/services/{env}/{service} - Service details
- GET /api/{project}/details/{env}/{service} - Extended service details
- GET /api/{project}/tasks/{env}/{service}/{task_id} - Task details
- GET /api/{project}/logs/{env}/{service} - Service logs
- GET /api/{project}/metrics/{env}/{service} - Service metrics
- POST /api/{project}/actions/deploy/{env}/{service}/{action} - Deploy actions

All endpoints require authentication and appropriate permissions.
RBAC checks are performed per-action via decorators.
"""

import json
from datetime import datetime
from typing import Dict, Any

from shared.rbac import (
    Action,
    get_auth_context,
    check_permission,
    require_permission,
)
from shared.response import (
    json_response,
    error_response,
    success_response,
    not_found_response,
    get_path_param,
    get_method,
    get_path,
    get_body,
)
from config import get_config
from providers import ProviderFactory
from auth.user_management import _audit_log


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for services endpoints.

    Routes requests based on path structure.
    """
    method = get_method(event)
    path = get_path(event)
    auth = get_auth_context(event)

    # Handle CORS preflight
    if method == 'OPTIONS':
        return json_response(200, {})

    # Parse path components
    parts = path.strip('/').split('/')
    # parts[0] = 'api', ...

    config = get_config()

    # =================================================================
    # GLOBAL ROUTES (no project context)
    # =================================================================

    # GET /api/projects - List all projects
    if path == '/api/projects' or (len(parts) == 2 and parts[1] == 'projects'):
        return handle_list_projects(auth, config)

    # =================================================================
    # PROJECT-SCOPED ROUTES
    # =================================================================

    if len(parts) < 3:
        return error_response('invalid_path', 'Invalid path structure', 400)

    project = parts[1]
    resource = parts[2]

    # GET /api/{project}/environments - List environments for project
    if resource == 'environments':
        return handle_list_environments(auth, project, config)

    # Validate project for other routes
    project_config = config.get_project(project)
    if not project_config:
        return error_response('not_found', f'Unknown project: {project}', 404)

    # Route to appropriate handler
    if resource == 'services':
        return handle_services(event, auth, project, parts, config)
    elif resource == 'details':
        return handle_details(event, auth, project, parts, config)
    elif resource == 'tasks':
        return handle_tasks(event, auth, project, parts, config)
    elif resource == 'logs':
        return handle_logs(event, auth, project, parts, config)
    elif resource == 'metrics':
        return handle_metrics(event, auth, project, parts, config)
    elif resource == 'actions' and len(parts) >= 4 and parts[3] == 'deploy':
        return handle_deploy_actions(event, auth, project, parts, config)
    else:
        return error_response('not_found', f'Unknown services endpoint: {path}', 404)


def handle_list_projects(auth, config) -> Dict[str, Any]:
    """
    Handle GET /api/projects - List all available projects.
    Returns project names, display names, and environments.
    """
    projects_list = []
    for project_name, project_config in config.projects.items():
        projects_list.append({
            'name': project_name,
            'displayName': project_config.display_name,
            'description': '',
            'environments': list(project_config.environments.keys()),
            'orchestrator': config.orchestrator.type if config.orchestrator else 'unknown'
        })

    return json_response(200, {'projects': projects_list})


def handle_list_environments(auth, project: str, config) -> Dict[str, Any]:
    """
    Handle GET /api/{project}/environments - List environments for a project.
    Returns environment names, types, and status.
    """
    project_config = config.get_project(project)
    if not project_config:
        return error_response('not_found', f'Unknown project: {project}', 404)

    environments_list = []
    for env_name, env_config in project_config.environments.items():
        environments_list.append({
            'name': env_name,
            'type': config.orchestrator.type if config.orchestrator else 'unknown',
            'status': env_config.status or 'active',
            'region': env_config.region,
            'description': ''
        })

    return json_response(200, {'environments': environments_list})


def handle_services(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/services/... endpoints
    Path: /api/{project}/services/{env?}/{service?}
    Index:  0     1         2        3       4
    """
    # Check read permission
    env = parts[3] if len(parts) > 3 else '*'
    if not check_permission(auth, Action.READ, project, env):
        return error_response('forbidden', f'Permission denied: read on {project}/{env}', 403)

    orchestrator = ProviderFactory.get_orchestrator_provider(config, project)

    if len(parts) == 3:
        # /api/{project}/services - list all environments
        return list_all_environments(project, config, orchestrator)

    elif len(parts) == 4:
        # /api/{project}/services/{env} - list services in env
        env = parts[3]
        return list_services(project, env, config, orchestrator)

    elif len(parts) >= 5:
        # /api/{project}/services/{env}/{service} - service details
        env = parts[3]
        service = parts[4]
        return get_service(project, env, service, orchestrator)

    return error_response('invalid_path', 'Invalid services path', 400)


def handle_details(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/details/{env}/{service} endpoint
    Path: /api/{project}/details/{env}/{service}
    Index:  0     1         2      3       4
    """
    if len(parts) < 5:
        return error_response('invalid_path', 'Use /api/{project}/details/{env}/{service}', 400)

    env = parts[3]
    service = parts[4]

    # Check read permission
    if not check_permission(auth, Action.READ, project, env):
        return error_response('forbidden', f'Permission denied: read on {project}/{env}', 403)

    orchestrator = ProviderFactory.get_orchestrator_provider(config, project)
    details = orchestrator.get_service_details(env, service)

    return json_response(200, format_service_details(details))


def handle_tasks(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/tasks/{env}/{service}/{task_id} endpoint
    Path: /api/{project}/tasks/{env}/{service}/{task_id}
    Index:  0     1        2     3       4         5
    """
    if len(parts) < 6:
        return error_response('invalid_path', 'Use /api/{project}/tasks/{env}/{service}/{task_id}', 400)

    env = parts[3]
    service = parts[4]
    task_id = parts[5]

    # Check read permission
    if not check_permission(auth, Action.READ, project, env):
        return error_response('forbidden', f'Permission denied: read on {project}/{env}', 403)

    orchestrator = ProviderFactory.get_orchestrator_provider(config, project)
    task_details = orchestrator.get_task_details(env, service, task_id)

    return json_response(200, task_details)


def handle_logs(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/logs/{env}/{service} endpoint
    Path: /api/{project}/logs/{env}/{service}
    Index:  0     1        2    3       4
    """
    if len(parts) < 5:
        return error_response('invalid_path', 'Use /api/{project}/logs/{env}/{service}', 400)

    env = parts[3]
    service = parts[4]

    # Check read permission
    if not check_permission(auth, Action.READ, project, env):
        return error_response('forbidden', f'Permission denied: read on {project}/{env}', 403)

    orchestrator = ProviderFactory.get_orchestrator_provider(config, project)
    logs = orchestrator.get_service_logs(env, service)

    return json_response(200, {
        'project': project,
        'environment': env,
        'service': service,
        'logs': logs
    })


def handle_metrics(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/metrics/{env}/{service} endpoint
    Path: /api/{project}/metrics/{env}/{service}
    Index:  0     1         2      3       4
    """
    if len(parts) < 5:
        return error_response('invalid_path', 'Use /api/{project}/metrics/{env}/{service}', 400)

    env = parts[3]
    service = parts[4]

    # Check read permission
    if not check_permission(auth, Action.READ, project, env):
        return error_response('forbidden', f'Permission denied: read on {project}/{env}', 403)

    orchestrator = ProviderFactory.get_orchestrator_provider(config, project)
    metrics = orchestrator.get_metrics(env, service)

    return json_response(200, metrics)


def handle_deploy_actions(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/actions/deploy/{env}/{service}/{action} endpoints
    Path: /api/{project}/actions/deploy/{env}/{service}/{action}
    Index:  0     1         2       3     4       5         6

    Actions:
    - reload: Force new deployment (same image)
    - latest: Deploy latest build
    - stop: Scale to 0
    - start: Scale to desired count
    """
    method = get_method(event)
    if method != 'POST':
        return error_response('method_not_allowed', 'POST required', 405)

    if len(parts) < 7:
        return error_response('invalid_path', 'Use /api/{project}/actions/deploy/{env}/{service}/{action}', 400)

    env = parts[4]
    service = parts[5]
    action_type = parts[6]

    # Determine required permission based on action
    if action_type in ('reload', 'latest'):
        required_action = Action.DEPLOY
    elif action_type in ('stop', 'start'):
        required_action = Action.SCALE
    else:
        return error_response('invalid_action', f'Unknown action: {action_type}', 400)

    # Check permission
    if not check_permission(auth, required_action, project, env):
        return error_response(
            'forbidden',
            f'Permission denied: {required_action.value} on {project}/{env}',
            403
        )

    email = auth.email if auth else 'unknown'
    body = get_body(event)

    # Audit log start
    _audit_log(email, f'deploy_{action_type}', {
        'project': project,
        'env': env,
        'service': service,
    }, 'started')

    orchestrator = ProviderFactory.get_orchestrator_provider(config, project)
    ci = ProviderFactory.get_ci_provider(config, project)

    try:
        if action_type == 'reload':
            result = orchestrator.force_deployment(env, service, email)
        elif action_type == 'latest':
            result = ci.trigger_deploy(env, service, email)
        elif action_type == 'stop':
            result = orchestrator.scale_service(env, service, 0, email)
        elif action_type == 'start':
            desired_count = int(body.get('desiredCount', 1))
            if desired_count < 1 or desired_count > 10:
                return error_response('validation_error', 'desiredCount must be between 1 and 10', 400)
            result = orchestrator.scale_service(env, service, desired_count, email)
        else:
            return error_response('invalid_action', f'Unknown action: {action_type}', 400)

        # Audit log success
        _audit_log(email, f'deploy_{action_type}', {
            'project': project,
            'env': env,
            'service': service,
        }, 'success')

        return json_response(200, result)

    except Exception as e:
        # Audit log failure
        _audit_log(email, f'deploy_{action_type}', {
            'project': project,
            'env': env,
            'service': service,
            'error': str(e),
        }, 'failed')

        return error_response('action_failed', str(e), 500)


# =============================================================================
# Helper Functions
# =============================================================================

def list_all_environments(project: str, config, orchestrator) -> Dict[str, Any]:
    """List services across all environments"""
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
                    svc_name: format_service_summary(svc)
                    for svc_name, svc in services.items()
                    if not isinstance(svc, dict) or 'error' not in svc
                }
            }
        except Exception as e:
            result['environments'][env_name] = {'error': str(e)}

    return json_response(200, result)


def list_services(project: str, env: str, config, orchestrator) -> Dict[str, Any]:
    """List services in a specific environment"""
    env_config = config.get_environment(project, env)
    if not env_config:
        return error_response('not_found', f'Unknown environment: {env} for project {project}', 404)

    services = orchestrator.get_services(env)

    return json_response(200, {
        'project': project,
        'environment': env,
        'accountId': env_config.account_id,
        'services': {
            svc_name: format_service_summary(svc)
            for svc_name, svc in services.items()
            if not isinstance(svc, dict) or 'error' not in svc
        },
        'timestamp': datetime.utcnow().isoformat()
    })


def get_service(project: str, env: str, service: str, orchestrator) -> Dict[str, Any]:
    """Get details for a specific service"""
    svc = orchestrator.get_service(env, service)
    return json_response(200, format_service(svc))


# =============================================================================
# Formatting Functions
# =============================================================================

def format_service_summary(svc) -> Dict[str, Any]:
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


def format_service(svc) -> Dict[str, Any]:
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
            'tasks': [format_task(t) for t in svc.tasks],
            'deployments': [format_deployment(d) for d in svc.deployments],
            'consoleUrl': svc.console_url,
            'accountId': svc.account_id
        }
    return svc


def format_service_details(details) -> Dict[str, Any]:
    """Format service details"""
    base = format_service(details)
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


def format_task(task) -> Dict[str, Any]:
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


def format_deployment(dep) -> Dict[str, Any]:
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
