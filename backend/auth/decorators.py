"""
Authorization Decorators for API Handlers

Provides decorators to enforce permission checks on route handlers.
"""

import functools
import re
from typing import Callable, Optional, Any, Dict
from .models import AuthContext, DashborionRole, ForbiddenError, MfaRequiredError, UnauthorizedError
from .middleware import authorize_request
from .permissions import check_permission, log_audit_event


def extract_path_params(event: Dict[str, Any], param_name: str) -> Optional[str]:
    """Extract a parameter from the request path"""
    # API Gateway v2 format
    path_params = event.get('pathParameters', {}) or {}
    if param_name in path_params:
        return path_params[param_name]

    # Try to extract from raw path
    path = event.get('rawPath', event.get('path', ''))

    # Common patterns: /api/services/{env}/{service}, /api/actions/{action}/{env}/{service}
    patterns = {
        'env': r'/api/(?:services|infrastructure|logs|events|actions/[^/]+)/([^/]+)',
        'service': r'/api/(?:services|details|logs)/[^/]+/([^/]+)',
        'project': r'/api/projects/([^/]+)',
    }

    if param_name in patterns:
        match = re.search(patterns[param_name], path)
        if match:
            return match.group(1)

    return None


def require_permission(
    action: str,
    project_param: str = None,
    env_param: str = None,
    resource_param: str = None,
    require_mfa: bool = False,
    audit: bool = True
):
    """
    Decorator to enforce permission checks on route handlers.

    Args:
        action: Required action (read, deploy, scale, etc.)
        project_param: Name of path parameter containing project name
        env_param: Name of path parameter containing environment name
        resource_param: Name of path parameter containing resource name
        require_mfa: If True, MFA verification is required
        audit: If True, log the action to audit trail

    Usage:
        @require_permission('deploy', env_param='env', resource_param='service')
        def handle_deploy(event, context, auth: AuthContext):
            # auth is automatically injected
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(event: Dict[str, Any], context: Any, *args, **kwargs) -> Any:
            # Authorize request
            auth = authorize_request(event, require_auth=True)

            # Extract parameters
            project = kwargs.get(project_param) if project_param else None
            if project is None and project_param:
                project = extract_path_params(event, project_param)

            env = kwargs.get(env_param) if env_param else None
            if env is None and env_param:
                env = extract_path_params(event, env_param)

            resource = kwargs.get(resource_param) if resource_param else None
            if resource is None and resource_param:
                resource = extract_path_params(event, resource_param)

            # Default values
            project = project or '*'
            env = env or '*'
            resource = resource or '*'

            # Check MFA requirement
            if require_mfa and not auth.mfa_verified:
                if audit:
                    log_audit_event(auth, action, project, env, resource, 'denied_mfa')
                raise MfaRequiredError(f"MFA verification required for {action}")

            # Check permission
            if not check_permission(auth, action, project, env, resource):
                if audit:
                    log_audit_event(auth, action, project, env, resource, 'denied')
                raise ForbiddenError(
                    f"Permission denied: {action} on {project}/{env}/{resource}"
                )

            # Inject auth context into kwargs
            kwargs['auth'] = auth

            # Execute handler
            try:
                result = func(event, context, *args, **kwargs)

                # Log successful action
                if audit and action != 'read':
                    log_audit_event(auth, action, project, env, resource, 'success')

                return result

            except Exception as e:
                # Log failed action
                if audit and action != 'read':
                    log_audit_event(
                        auth, action, project, env, resource, 'error',
                        details={'error': str(e)}
                    )
                raise

        return wrapper
    return decorator


def require_role(role: DashborionRole, project_param: str = None, env_param: str = None):
    """
    Decorator to require a specific role.

    Args:
        role: Required role
        project_param: Name of path parameter containing project name
        env_param: Name of path parameter containing environment name
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(event: Dict[str, Any], context: Any, *args, **kwargs) -> Any:
            auth = authorize_request(event, require_auth=True)

            project = None
            if project_param:
                project = kwargs.get(project_param) or extract_path_params(event, project_param)

            env = None
            if env_param:
                env = kwargs.get(env_param) or extract_path_params(event, env_param)

            if not auth.has_role(role, project, env):
                raise ForbiddenError(f"Role {role.value} required")

            kwargs['auth'] = auth
            return func(event, context, *args, **kwargs)

        return wrapper
    return decorator


def require_admin(func: Callable) -> Callable:
    """
    Decorator to require admin role.

    Shortcut for @require_role(DashborionRole.ADMIN)
    """
    @functools.wraps(func)
    def wrapper(event: Dict[str, Any], context: Any, *args, **kwargs) -> Any:
        auth = authorize_request(event, require_auth=True)

        if not auth.is_admin:
            raise ForbiddenError("Admin access required")

        kwargs['auth'] = auth
        return func(event, context, *args, **kwargs)

    return wrapper


def optional_auth(func: Callable) -> Callable:
    """
    Decorator for endpoints that work with or without authentication.

    Injects auth context if available, None otherwise.
    """
    @functools.wraps(func)
    def wrapper(event: Dict[str, Any], context: Any, *args, **kwargs) -> Any:
        auth = authorize_request(event, require_auth=False)
        kwargs['auth'] = auth if auth.is_authenticated else None
        return func(event, context, *args, **kwargs)

    return wrapper
