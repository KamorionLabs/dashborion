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

    ci = ProviderFactory.get_ci_provider(config, project)
    if not ci:
        return error_response('not_configured', 'CI/CD provider not configured for this project', 501)

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

    ci = ProviderFactory.get_ci_provider(config, project)
    if not ci:
        return error_response('not_configured', 'CI/CD provider not configured for this project', 501)

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

    ci = ProviderFactory.get_ci_provider(config, project)
    if not ci:
        return error_response('not_configured', 'CI/CD provider not configured for this project', 501)

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
