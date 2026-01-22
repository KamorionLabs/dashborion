"""
Pipelines Lambda Handler.

Handles all CI/CD pipeline-related endpoints:
- GET /api/{project}/pipelines/build/{service} - Build pipeline info
- GET /api/{project}/pipelines/deploy/{service}/{env} - Deploy pipeline info
- GET /api/{project}/images/{service} - ECR images
- POST /api/{project}/actions/build/{service} - Trigger build

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
    get_query_params,
)
from app_config import get_config
from providers import ProviderFactory
from auth.user_management import _audit_log


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for pipelines endpoints.
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

    # Check for Jenkins discovery/history routes (no project prefix)
    # /api/pipelines/jenkins/{action}/{path...}
    if parts[1] == 'pipelines' and len(parts) >= 3 and parts[2] == 'jenkins':
        return handle_jenkins_routes(event, auth, parts)

    project = parts[1]
    resource = parts[2]

    # Validate project
    config = get_config()
    project_config = config.get_project(project)
    if not project_config:
        return error_response('not_found', f'Unknown project: {project}', 404)

    # Route to appropriate handler
    if resource == 'pipelines':
        return handle_pipelines(event, auth, project, parts, config)
    elif resource == 'images':
        return handle_images(event, auth, project, parts, config)
    elif resource == 'actions' and len(parts) >= 4 and parts[3] == 'build':
        return handle_build_action(event, auth, project, parts, config)

    return error_response('not_found', f'Unknown pipelines endpoint: {path}', 404)


def handle_pipelines(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/pipelines/{type}/{service}/{env?} endpoints
    Path: /api/{project}/pipelines/{type}/{service}/{env?}
    Index:  0     1         2        3       4       5
    """
    if len(parts) < 5:
        return error_response('invalid_path', 'Use /api/{project}/pipelines/{type}/{service}/{env?}', 400)

    pipeline_type = parts[3]  # build or deploy
    service = parts[4]
    env = parts[5] if len(parts) > 5 else None

    # Check read permission (use * for build pipelines which are env-agnostic)
    permission_env = env if env else '*'
    if not check_permission(auth, Action.READ, project, permission_env):
        return error_response('forbidden', f'Permission denied: read on {project}/{permission_env}', 403)

    # Get provider for this specific service and pipeline type
    ci = ProviderFactory.get_ci_provider_for_service(config, project, service, pipeline_type)
    if not ci:
        return error_response('not_configured', f'CI/CD provider not configured for {service} {pipeline_type}', 501)

    if pipeline_type == 'build':
        pipeline = ci.get_build_pipeline(service)
        return json_response(200, format_pipeline(pipeline))
    elif pipeline_type == 'deploy':
        if not env:
            return error_response('validation_error', 'Environment required for deploy pipeline', 400)
        pipeline = ci.get_deploy_pipeline(env, service)
        return json_response(200, format_pipeline(pipeline))
    else:
        return error_response('invalid_type', f'Unknown pipeline type: {pipeline_type}', 400)


def handle_images(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/images/{service} endpoint
    Path: /api/{project}/images/{service}
    Index:  0     1         2       3
    """
    if len(parts) < 4:
        return error_response('invalid_path', 'Use /api/{project}/images/{service}', 400)

    service = parts[3]

    # Check read permission (images are global, not env-specific)
    if not check_permission(auth, Action.READ, project, '*'):
        return error_response('forbidden', f'Permission denied: read on {project}', 403)

    # Use build provider for images (images are typically from build pipelines)
    ci = ProviderFactory.get_ci_provider_for_service(config, project, service, 'build')
    if not ci:
        return error_response('not_configured', f'CI/CD provider not configured for {service}', 501)

    images = ci.get_images(service)

    return json_response(200, {
        'project': project,
        'repositoryName': config.get_ecr_repo(project, service),
        'images': [format_image(img) for img in images]
    })


def handle_build_action(event, auth, project: str, parts: list, config) -> Dict[str, Any]:
    """
    Handle /api/{project}/actions/build/{service} endpoint
    Path: /api/{project}/actions/build/{service}
    Index:  0     1         2       3      4

    Requires DEPLOY permission
    """
    method = get_method(event)
    if method != 'POST':
        return error_response('method_not_allowed', 'POST required', 405)

    if len(parts) < 5:
        return error_response('invalid_path', 'Use /api/{project}/actions/build/{service}', 400)

    service = parts[4]

    # Check deploy permission (build triggers are global)
    if not check_permission(auth, Action.DEPLOY, project, '*'):
        return error_response('forbidden', f'Permission denied: deploy on {project}', 403)

    email = auth.email if auth else 'unknown'
    body = get_body(event)
    image_tag = body.get('imageTag', 'latest')
    source_revision = body.get('sourceRevision', '')

    # Use build provider for triggering builds
    ci = ProviderFactory.get_ci_provider_for_service(config, project, service, 'build')
    if not ci:
        return error_response('not_configured', f'CI/CD provider not configured for {service} build', 501)

    # Audit log start
    _audit_log(email, 'build_trigger', {
        'project': project,
        'service': service,
        'imageTag': image_tag,
    }, 'started')

    try:
        result = ci.trigger_build(service, email, image_tag, source_revision)

        _audit_log(email, 'build_trigger', {
            'project': project,
            'service': service,
        }, 'success')

        return json_response(200, result)

    except Exception as e:
        _audit_log(email, 'build_trigger', {
            'project': project,
            'service': service,
            'error': str(e),
        }, 'failed')

        return error_response('action_failed', str(e), 500)


# =============================================================================
# Formatting Functions
# =============================================================================

def format_pipeline(pipeline) -> Dict[str, Any]:
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
        'lastExecution': format_execution(pipeline.last_execution) if pipeline.last_execution else None,
        'executions': [format_execution(e) for e in pipeline.executions],
        'buildLogs': pipeline.build_logs,
        'consoleUrl': pipeline.console_url
    }


def format_execution(exec) -> Dict[str, Any]:
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


def format_image(img) -> Dict[str, Any]:
    """Format container image"""
    return {
        'digest': img.digest,
        'tags': img.tags,
        'pushedAt': img.pushed_at.isoformat() if img.pushed_at else None,
        'sizeBytes': img.size_bytes,
        'sizeMB': img.size_mb
    }


# =============================================================================
# Jenkins Discovery and History Handlers
# =============================================================================

def handle_jenkins_routes(event, auth, parts: list) -> Dict[str, Any]:
    """
    Handle Jenkins-specific routes for discovery and history.

    Routes:
    - GET /api/pipelines/jenkins/discover?providerId=...&path=...&includeParams=true
    - GET /api/pipelines/jenkins/job/{jobPath+}?providerId=...
    - GET /api/pipelines/jenkins/history/{jobPath+}?providerId=...&Webshop=MI2&limit=20
    - GET /api/pipelines/jenkins/params/{jobPath+}?providerId=...&param=Webshop

    Path: /api/pipelines/jenkins/{action}/{path...}
    Index:  0     1         2        3        4...

    All routes require providerId query parameter referencing a global CI Provider.
    """
    # Require at least admin read permission for Jenkins discovery
    if not check_permission(auth, Action.READ, '*', '*'):
        return error_response('forbidden', 'Permission denied: admin read required', 403)

    if len(parts) < 4:
        return error_response('invalid_path', 'Use /api/pipelines/jenkins/{action}/...', 400)

    action = parts[3]
    config = get_config()
    params = get_query_params(event)

    # providerId is required - references global CI Provider
    provider_id = params.get('providerId')
    if not provider_id:
        return error_response('validation_error', 'providerId query parameter is required', 400)

    # Load CI Provider config with credentials
    from config.handler import get_ci_provider_with_credentials
    provider_config = get_ci_provider_with_credentials(provider_id)

    if not provider_config:
        return error_response('not_found', f'CI Provider not found: {provider_id}', 404)

    if provider_config.get('type') != 'jenkins':
        return error_response('invalid_type', f'CI Provider {provider_id} is not a Jenkins provider', 400)

    # Create Jenkins provider from global config
    from providers.ci.jenkins import JenkinsProvider
    jenkins = JenkinsProvider.from_provider_config(config, provider_config)

    if action == 'discover':
        return handle_jenkins_discover(event, jenkins)
    elif action == 'job':
        job_path = '/'.join(parts[4:]) if len(parts) > 4 else ''
        return handle_jenkins_job(event, jenkins, job_path)
    elif action == 'history':
        job_path = '/'.join(parts[4:]) if len(parts) > 4 else ''
        return handle_jenkins_history(event, jenkins, job_path)
    elif action == 'params':
        job_path = '/'.join(parts[4:]) if len(parts) > 4 else ''
        return handle_jenkins_params(event, jenkins, job_path)

    return error_response('not_found', f'Unknown Jenkins action: {action}', 404)


def handle_jenkins_discover(event, jenkins) -> Dict[str, Any]:
    """
    Handle GET /api/pipelines/jenkins/discover

    Query params:
    - path: Folder path to browse (optional)
    - includeParams: Include parameter definitions (default: true)
    - limit: Max jobs to return (default: 50)

    Returns:
    - items: Combined list of jobs and folders with type field
    - currentPath: Current folder path
    - error: Error message if any
    """
    params = get_query_params(event)
    folder_path = params.get('path', '')
    include_params = params.get('includeParams', 'true').lower() == 'true'
    limit = int(params.get('limit', '50'))

    result = jenkins.discover_jobs(
        folder_path=folder_path if folder_path else None,
        include_params=include_params,
        limit=limit
    )

    # Transform to unified items format for frontend compatibility
    # Frontend expects: { items: [...], currentPath: string, error: string|null }
    items = []

    # Add folders first (sorted by name)
    for folder in result.get('folders', []):
        items.append({
            'name': folder.get('name'),
            'path': folder.get('fullPath'),
            'fullPath': folder.get('fullPath'),
            'type': 'folder',
        })

    # Add jobs (sorted by name)
    for job in result.get('jobs', []):
        items.append({
            'name': job.get('name'),
            'path': job.get('fullPath'),
            'fullPath': job.get('fullPath'),
            'type': job.get('type', 'job'),
            'parameters': job.get('parameters'),
        })

    return json_response(200, {
        'items': items,
        'currentPath': result.get('currentPath', ''),
        'error': result.get('error'),
    })


def handle_jenkins_job(event, jenkins, job_path: str) -> Dict[str, Any]:
    """
    Handle GET /api/pipelines/jenkins/job/{jobPath+}

    Returns job details with parameter definitions.
    """
    if not job_path:
        return error_response('invalid_path', 'Job path required', 400)

    result = jenkins.get_job_with_params(job_path)

    if 'error' in result:
        return error_response('not_found', result['error'], 404)

    return json_response(200, result)


def handle_jenkins_history(event, jenkins, job_path: str) -> Dict[str, Any]:
    """
    Handle GET /api/pipelines/jenkins/history/{jobPath+}

    Query params:
    - limit: Max builds to return (default: 20)
    - result: Filter by result (SUCCESS, FAILURE, etc.)
    - Any other param: Filter by parameter value (e.g., Webshop=MI2)
    """
    if not job_path:
        return error_response('invalid_path', 'Job path required', 400)

    params = get_query_params(event)
    limit = int(params.get('limit', '20'))
    result_filter = params.get('result')

    # Extract parameter filters (any param that's not limit/result)
    filter_params = {}
    for key, value in params.items():
        if key not in ('limit', 'result'):
            filter_params[key] = value

    builds = jenkins.get_builds_filtered(
        job_path=job_path,
        filter_params=filter_params if filter_params else None,
        limit=limit,
        result_filter=result_filter
    )

    # Get job info for context
    job_info = jenkins.get_job_with_params(job_path)

    return json_response(200, {
        'jobPath': job_path,
        'jobName': job_info.get('name') if not job_info.get('error') else job_path.split('/')[-1],
        'parameters': job_info.get('parameters', []) if not job_info.get('error') else [],
        'filters': filter_params,
        'builds': builds,
        'count': len(builds),
    })


def handle_jenkins_params(event, jenkins, job_path: str) -> Dict[str, Any]:
    """
    Handle GET /api/pipelines/jenkins/params/{jobPath+}

    Query params:
    - param: Parameter name to analyze (required)
    - limit: Number of recent builds to analyze (default: 50)

    Returns unique values used for the parameter, sorted by frequency.
    """
    if not job_path:
        return error_response('invalid_path', 'Job path required', 400)

    params = get_query_params(event)
    param_name = params.get('param')
    if not param_name:
        return error_response('validation_error', 'param query parameter required', 400)

    limit = int(params.get('limit', '50'))

    values = jenkins.get_parameter_values(
        job_path=job_path,
        param_name=param_name,
        limit=limit
    )

    return json_response(200, {
        'jobPath': job_path,
        'parameterName': param_name,
        'values': values,
    })
