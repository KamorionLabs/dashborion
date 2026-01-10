"""
Infrastructure Lambda Handler.

Handles all infrastructure-related endpoints:
- GET /api/{project}/infrastructure/{env} - Infrastructure overview
- GET /api/{project}/infrastructure/{env}/routing - Routing details
- GET /api/{project}/infrastructure/{env}/enis - ENIs list
- GET /api/{project}/infrastructure/{env}/security-group/{sg_id} - SG details
- POST /api/{project}/actions/rds/{env}/{action} - RDS actions (admin only)
- POST /api/{project}/actions/cloudfront/{env}/invalidate - CloudFront invalidation

All endpoints require authentication and appropriate permissions.
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
    get_query_param,
)
from config import get_config
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

        return error_response('not_found', f'Unknown sub-resource: {sub_resource}', 404)

    # Main infrastructure info
    discovery_tags = None
    discovery_tags_str = query_params.get('discoveryTags', '')
    if discovery_tags_str:
        try:
            discovery_tags = json.loads(discovery_tags_str)
        except json.JSONDecodeError:
            pass

    services_str = query_params.get('services', '')
    services_list = services_str.split(',') if services_str else None

    domain_config = None
    domain_config_str = query_params.get('domainConfig', '')
    if domain_config_str:
        try:
            domain_config = json.loads(domain_config_str)
        except json.JSONDecodeError:
            pass

    databases_str = query_params.get('databases', '')
    databases_list = databases_str.split(',') if databases_str else None

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

    return json_response(200, result)


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
