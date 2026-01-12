"""
Comparison Lambda Handler.

Handles environment comparison endpoints:
- GET /api/{project}/comparison/config - Comparison configuration (available pairs)
- GET /api/{project}/comparison/{sourceEnv}/{destEnv}/summary - Comparison summary
- GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType} - Detailed comparison
- GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}/history - Historical data

All endpoints require authentication and appropriate permissions.
"""

import os
from typing import Dict, Any, List, Optional, Tuple

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
    get_query_param,
)
from config import get_config
from providers.comparison import DynamoDBComparisonProvider, ComparisonOrchestratorProvider


def _get_comparison_keys(project: str, source_env: str, dest_env: str, config) -> Tuple[str, str, str]:
    """
    Build DynamoDB keys for comparison data.

    Returns: (pk, source_label, destination_label)

    New format (dashborion-integration):
    - pk: {project}#comparison:{sourceEnv}:{destEnv}
    - sk: check:{category}:{type}:current (handled by provider)

    Example:
    - pk: mro-mi2#comparison:legacy-staging:nh-staging
    - sk: check:k8s:pods:current
    """
    # Build pk in the new format
    pk = f"{project}#comparison:{source_env}:{dest_env}"

    # Get labels from config groups (fallback to generic Source/Destination)
    comparison_config = getattr(config, 'comparison', None) or {}
    groups = comparison_config.get('groups', [])

    source_label = 'Source'
    dest_label = 'Destination'

    for group in groups:
        prefix = group.get('prefix', '')
        if prefix and source_env.startswith(prefix):
            source_label = group.get('label', 'Source')
        if prefix and dest_env.startswith(prefix):
            dest_label = group.get('label', 'Destination')

    return pk, source_label, dest_label


def _get_available_pairs(project: str, config) -> List[Dict[str, Any]]:
    """
    Get available comparison pairs for a project.

    Uses comparison.groups from config to detect pairs:
    - Groups define prefix and label for source/destination environments
    - Pairs are created by matching base env names (e.g., staging, preprod)
    """
    project_config = config.get_project(project)
    if not project_config:
        return []

    # ProjectConfig has .environments attribute (Dict[str, EnvironmentConfig])
    environments = getattr(project_config, 'environments', None)
    if not environments:
        return []

    # Get comparison groups from config (optional - if not configured, no auto-pairing)
    comparison_config = getattr(config, 'comparison', None) or {}
    groups = comparison_config.get('groups', [])

    # If no groups configured, return empty (comparison pairing is opt-in)
    if not groups:
        return []

    # Find source and destination groups
    source_group = next((g for g in groups if g.get('role') == 'source'), None)
    dest_group = next((g for g in groups if g.get('role') == 'destination'), None)

    # Need both source and destination groups to create pairs
    if not source_group or not dest_group:
        return []

    source_prefix = source_group.get('prefix', '')
    dest_prefix = dest_group.get('prefix', '')
    source_label = source_group.get('label', 'Source')
    dest_label = dest_group.get('label', 'Destination')

    # Get environment names from the dict keys
    env_names = list(environments.keys())

    # Find source and destination environments by prefix
    source_envs = [e for e in env_names if e.startswith(source_prefix)]
    dest_envs = [e for e in env_names if e.startswith(dest_prefix)]

    pairs = []
    for source_env in source_envs:
        # Extract base env (e.g., "legacy-staging" -> "staging")
        base = source_env.replace(source_prefix, '')
        # Find matching destination env
        dest_match = f"{dest_prefix}{base}"
        if dest_match in dest_envs:
            pairs.append({
                'id': f"{base}-comparison",
                'label': f"{base.title()}: {source_label} vs {dest_label}",
                'source': {
                    'env': source_env,
                    'label': source_label,
                },
                'destination': {
                    'env': dest_match,
                    'label': dest_label,
                },
            })

    return pairs


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for comparison endpoints.
    """
    method = get_method(event)
    path = get_path(event)
    auth = get_auth_context(event)

    # Handle CORS preflight
    if method == 'OPTIONS':
        return json_response(200, {})

    # GET and POST supported
    if method not in ('GET', 'POST'):
        return error_response('method_not_allowed', 'Only GET and POST are supported', 405)

    # Parse path: /api/{project}/comparison/...
    parts = path.strip('/').split('/')
    if len(parts) < 4:
        return error_response('invalid_path', 'Invalid path structure', 400)

    project = parts[1]
    resource = parts[2]  # Should be 'comparison'

    if resource != 'comparison':
        return error_response('invalid_path', 'Expected /comparison/ in path', 400)

    # Validate project
    config = get_config()
    project_config = config.get_project(project)
    if not project_config:
        return error_response('not_found', f'Unknown project: {project}', 404)

    # Route: /api/{project}/comparison/config
    if len(parts) == 4 and parts[3] == 'config':
        return handle_config(project, config, auth)

    # Routes with sourceEnv/destEnv
    if len(parts) >= 5:
        source_env = parts[3]
        dest_env = parts[4]

        # Check read permission for both environments
        if not check_permission(auth, Action.READ, project, source_env):
            return error_response('forbidden', f'Permission denied: read on {project}/{source_env}', 403)
        if not check_permission(auth, Action.READ, project, dest_env):
            return error_response('forbidden', f'Permission denied: read on {project}/{dest_env}', 403)

        # Get DynamoDB keys and labels from config
        pk, source_label, dest_label = _get_comparison_keys(project, source_env, dest_env, config)

        # Initialize provider
        provider = DynamoDBComparisonProvider()

        # Route: /api/{project}/comparison/{sourceEnv}/{destEnv}/summary
        if len(parts) == 6 and parts[5] == 'summary':
            # Get comparison config for refresh threshold
            comparison_config = getattr(config, 'comparison', None) or {}
            refresh_threshold = comparison_config.get('refreshThresholdSeconds', 3600)

            # Initialize orchestrator provider
            orch_provider = ComparisonOrchestratorProvider(
                refresh_threshold_seconds=refresh_threshold
            )

            return handle_summary(
                provider, orch_provider, pk, source_label, dest_label,
                project, source_env, dest_env
            )

        # Route: /api/{project}/comparison/{sourceEnv}/{destEnv}/trigger (POST)
        if len(parts) == 6 and parts[5] == 'trigger':
            if method != 'POST':
                return error_response('method_not_allowed', 'Only POST is supported for trigger', 405)

            # Check action permission for trigger
            if not check_permission(auth, Action.DEPLOY, project, source_env):
                return error_response('forbidden', f'Permission denied: action on {project}/{source_env}', 403)

            comparison_config = getattr(config, 'comparison', None) or {}
            refresh_threshold = comparison_config.get('refreshThresholdSeconds', 3600)

            orch_provider = ComparisonOrchestratorProvider(
                refresh_threshold_seconds=refresh_threshold
            )

            force = get_query_param(event, 'force', 'false').lower() == 'true'
            wait = get_query_param(event, 'wait', 'false').lower() == 'true'

            return handle_trigger(orch_provider, project, source_env, dest_env, force, wait)

        # Route: /api/{project}/comparison/{sourceEnv}/{destEnv}/status
        if len(parts) == 6 and parts[5] == 'status':
            comparison_config = getattr(config, 'comparison', None) or {}
            refresh_threshold = comparison_config.get('refreshThresholdSeconds', 3600)

            orch_provider = ComparisonOrchestratorProvider(
                refresh_threshold_seconds=refresh_threshold
            )

            return handle_status(orch_provider, project, source_env, dest_env)

        # Route: /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}
        if len(parts) >= 6:
            check_type = parts[5]

            # Route: /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}/history
            if len(parts) == 7 and parts[6] == 'history':
                limit = int(get_query_param(event, 'limit', '50'))
                return handle_history(provider, pk, check_type, limit)

            # Route: /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}
            return handle_detail(provider, pk, check_type)

    return error_response('not_found', f'Unknown comparison endpoint: {path}', 404)


def handle_config(project: str, config, auth) -> Dict[str, Any]:
    """Handle comparison config request - returns available pairs"""
    # Check basic read permission for project
    if not check_permission(auth, Action.READ, project):
        return error_response('forbidden', f'Permission denied: read on {project}', 403)

    pairs = _get_available_pairs(project, config)

    # Get all environments for dropdown
    project_config = config.get_project(project)
    environments = getattr(project_config, 'environments', {}) if project_config else {}

    # Convert EnvironmentConfig objects to dict for response
    env_list = [
        {
            'id': k,
            'label': getattr(v, 'display_name', k) if hasattr(v, 'display_name') else k
        }
        for k, v in environments.items()
    ]

    return json_response(200, {
        'project': project,
        'environments': env_list,
        'pairs': pairs,
    })


def handle_summary(
    provider: DynamoDBComparisonProvider,
    orch_provider: ComparisonOrchestratorProvider,
    pk: str,
    source_label: str,
    dest_label: str,
    project: str,
    source_env: str,
    dest_env: str
) -> Dict[str, Any]:
    """Handle comparison summary request with execution status"""
    try:
        summary = provider.get_comparison_summary(
            pk=pk,
            source_label=source_label,
            destination_label=dest_label,
        )
        result = summary.to_dict()
        result['project'] = project
        result['sourceEnv'] = source_env
        result['destEnv'] = dest_env

        # Add execution status
        exec_state = orch_provider.get_execution_state(project, source_env, dest_env)
        result['executionStatus'] = exec_state.to_dict()

        # Add refresh info
        last_updated = summary.last_updated.isoformat() if summary.last_updated else None
        result['shouldAutoRefresh'] = orch_provider.should_auto_refresh(
            project, source_env, dest_env, last_updated, summary.pending_checks
        )
        result['refreshThresholdSeconds'] = orch_provider.refresh_threshold_seconds

        return json_response(200, result)

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_trigger(
    provider: ComparisonOrchestratorProvider,
    project: str,
    source_env: str,
    dest_env: str,
    force: bool = False,
    wait: bool = False,
) -> Dict[str, Any]:
    """Handle trigger comparison request"""
    try:
        result = provider.trigger_orchestrator(
            project=project,
            source_env=source_env,
            dest_env=dest_env,
            force=force,
            wait=wait,
        )
        return json_response(200, result)

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_status(
    provider: ComparisonOrchestratorProvider,
    project: str,
    source_env: str,
    dest_env: str,
) -> Dict[str, Any]:
    """Handle execution status request"""
    try:
        exec_state = provider.get_execution_state(project, source_env, dest_env)
        return json_response(200, {
            'project': project,
            'sourceEnv': source_env,
            'destEnv': dest_env,
            **exec_state.to_dict(),
        })

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_detail(
    provider: DynamoDBComparisonProvider,
    pk: str,
    check_type: str
) -> Dict[str, Any]:
    """Handle detailed comparison request"""
    try:
        detail = provider.get_comparison_detail(
            pk=pk,
            check_type=check_type,
        )

        if detail is None:
            return error_response('not_found', f'No data for check type: {check_type}', 404)

        if 'error' in detail:
            return error_response('error', detail['error'], 500)

        return json_response(200, detail)

    except Exception as e:
        return error_response('error', str(e), 500)


def handle_history(
    provider: DynamoDBComparisonProvider,
    pk: str,
    check_type: str,
    limit: int
) -> Dict[str, Any]:
    """Handle comparison history request"""
    try:
        history = provider.get_comparison_history(
            pk=pk,
            check_type=check_type,
            limit=limit,
        )

        return json_response(200, {
            'checkType': check_type,
            'count': len(history),
            'history': history,
        })

    except Exception as e:
        return error_response('error', str(e), 500)
