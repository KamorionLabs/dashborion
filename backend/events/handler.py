"""
Events Lambda Handler.

Handles all events-related endpoints:
- GET /api/{project}/events/{env} - Events timeline
- POST /api/{project}/events/{env}/enrich - Enrich events with CloudTrail
- POST /api/{project}/events/{env}/task-diff - Task definition diffs

All endpoints require authentication and read permissions.
"""

import json
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
)
from config import get_config
from providers import ProviderFactory
from utils.aws import get_cross_account_client


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for events endpoints.
    """
    method = get_method(event)
    path = get_path(event)
    auth = get_auth_context(event)

    # Handle CORS preflight
    if method == 'OPTIONS':
        return json_response(200, {})

    # Parse path
    # Path: /api/{project}/events/{env}/{sub_resource?}
    # Index:  0     1        2      3        4
    parts = path.strip('/').split('/')
    if len(parts) < 4:
        return error_response('invalid_path', 'Use /api/{project}/events/{env}', 400)

    project = parts[1]
    env = parts[3]

    # Validate project
    config = get_config()
    project_config = config.get_project(project)
    if not project_config:
        return error_response('not_found', f'Unknown project: {project}', 404)

    # Check read permission
    if not check_permission(auth, project, env, Action.READ):
        return error_response('forbidden', f'Permission denied: read on {project}/{env}', 403)

    query_params = event.get('queryStringParameters') or {}

    # Check for sub-resources
    if len(parts) >= 5:
        sub_resource = parts[4]

        if sub_resource == 'enrich':
            return handle_enrich(event, auth, project, env, config)
        elif sub_resource == 'task-diff':
            return handle_task_diff(event, auth, project, env, config)

    # GET /api/{project}/events/{env}
    return handle_list_events(event, auth, project, env, config, query_params)


def handle_list_events(event, auth, project: str, env: str, config, query_params) -> Dict[str, Any]:
    """
    Handle GET /api/{project}/events/{env}
    """
    events_provider = ProviderFactory.get_events_provider(config, project)

    hours = int(query_params.get('hours', 24))
    hours = min(max(hours, 1), 168)  # 1h to 7 days

    types_str = query_params.get('types', '')
    event_types = types_str.split(',') if types_str else None

    services_str = query_params.get('services', '')
    services = services_str.split(',') if services_str else None

    result = events_provider.get_events(env, hours=hours, event_types=event_types, services=services)

    return json_response(200, result)


def handle_enrich(event, auth, project: str, env: str, config) -> Dict[str, Any]:
    """
    Handle POST /api/{project}/events/{env}/enrich
    """
    method = get_method(event)
    if method != 'POST':
        return error_response('method_not_allowed', 'POST required', 405)

    body = get_body(event)
    events_provider = ProviderFactory.get_events_provider(config, project)

    result = events_provider.enrich_events(body, env=env)

    return json_response(200, result)


def handle_task_diff(event, auth, project: str, env: str, config) -> Dict[str, Any]:
    """
    Handle POST /api/{project}/events/{env}/task-diff
    """
    method = get_method(event)
    if method != 'POST':
        return error_response('method_not_allowed', 'POST required', 405)

    body = get_body(event)
    items = body.get('items', [])

    if not items:
        return json_response(200, {'results': []})

    orchestrator = ProviderFactory.get_orchestrator_provider(config, project)
    result = get_task_definition_diffs(orchestrator, config, project, env, items)

    return json_response(200, result)


def get_task_definition_diffs(orchestrator, config, project: str, env: str, items: list) -> dict:
    """Get task definition diffs for a batch of events"""
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
