"""
RBAC decorators and helpers for Lambda handlers.

Provides fine-grained authorization control at the handler level.
Each Lambda can use these decorators to enforce permission checks.

Authentication is handled by the Lambda Authorizer, which injects
user context into requestContext.authorizer.lambda.
This module provides authorization (permission checking).
"""

import json
from functools import wraps
from enum import Enum
from typing import Dict, Any, Callable, Optional, Union

# Import auth context from middleware
from auth.middleware import get_auth_context, authorize_request
from auth.models import AuthContext, DashborionRole


class Action(Enum):
    """Actions that can be performed on resources."""
    READ = "read"
    DEPLOY = "deploy"
    RESTART = "restart"
    SCALE = "scale"
    INVALIDATE = "invalidate"
    RDS_CONTROL = "rds-control"
    ADMIN = "admin"


# Mapping of roles to allowed actions
ROLE_ACTIONS: Dict[str, list[Action]] = {
    "viewer": [Action.READ],
    "operator": [
        Action.READ,
        Action.DEPLOY,
        Action.RESTART,
        Action.SCALE,
        Action.INVALIDATE,
    ],
    "admin": [
        Action.READ,
        Action.DEPLOY,
        Action.RESTART,
        Action.SCALE,
        Action.INVALIDATE,
        Action.RDS_CONTROL,
        Action.ADMIN,
    ],
}


def check_permission(
    auth: AuthContext,
    action: Union[Action, str],
    project: str = "*",
    env: str = "*",
    resource: str = "*"
) -> bool:
    """
    Check if user has permission for action on project/env/resource.

    Permission matching rules:
    - project='*' matches any project
    - environment='*' matches any environment
    - Role must include the requested action

    Args:
        auth: AuthContext from get_auth_context()
        action: Action enum or string action name
        project: Project identifier (e.g., 'homebox')
        env: Environment name (e.g., 'staging', 'production')
        resource: Resource identifier (optional)

    Returns:
        True if permission granted, False otherwise
    """
    print(f"[DEBUG] check_permission: auth={auth}, action={action}, project={project}, env={env}")
    if not auth or not auth.is_authenticated:
        print(f"[DEBUG] check_permission: NOT authenticated (auth={auth}, is_authenticated={auth.is_authenticated if auth else None})")
        return False

    print(f"[DEBUG] check_permission: user={auth.email}, permissions_count={len(auth.permissions)}")
    for p in auth.permissions:
        print(f"[DEBUG]   - Permission: project={p.project}, env={p.environment}, role={p.role}")

    # Convert string action to Action enum
    if isinstance(action, str):
        try:
            action = Action(action)
        except ValueError:
            return False

    for perm in auth.permissions:
        # Project match (wildcard or exact)
        if perm.project != '*' and perm.project != project:
            continue

        # Environment match (wildcard or exact)
        if perm.environment != '*' and perm.environment != env:
            continue

        # Resource match (if specified)
        if resource != '*':
            if '*' not in perm.resources and resource not in perm.resources:
                continue

        # Role allows action
        role_name = perm.role.value if hasattr(perm.role, 'value') else str(perm.role)
        role_actions = ROLE_ACTIONS.get(role_name, [])
        if action in role_actions:
            return True

    return False


def is_global_admin(auth: AuthContext) -> bool:
    """Check if user has global admin permissions (project=*, role=admin)."""
    if not auth or not auth.is_authenticated:
        return False

    for perm in auth.permissions:
        if perm.project == '*' and perm.role == DashborionRole.ADMIN:
            return True
    return False


def require_permission(action: Action = Action.READ):
    """
    Decorator to check permission before handler execution.

    Extracts project and env from pathParameters and checks
    if the authenticated user has the required permission.

    Usage:
        @require_permission(action=Action.DEPLOY)
        def handle_deploy(event, context, auth):
            # auth is injected by decorator
            ...

    Args:
        action: Required action (default: READ)

    Returns:
        Decorated function that receives auth as third parameter
    """
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(event: Dict[str, Any], context: Any):
            auth = get_auth_context(event)

            if not auth or not auth.is_authenticated:
                return _unauthorized_response("Authentication required")

            params = event.get('pathParameters', {}) or {}
            project = params.get('project', '*')
            env = params.get('env', '*')

            if not check_permission(auth, action, project, env):
                return _forbidden_response(
                    f"Permission denied: {action.value} on {project}/{env}"
                )

            # Pass auth context to handler
            return fn(event, context, auth)
        return wrapper
    return decorator


def require_global_admin(fn: Callable):
    """
    Decorator requiring global admin (project=*, role=admin).

    Use for admin endpoints like user management.

    Usage:
        @require_global_admin
        def handle_create_user(event, context, auth):
            ...
    """
    @wraps(fn)
    def wrapper(event: Dict[str, Any], context: Any):
        auth = get_auth_context(event)

        if not auth or not auth.is_authenticated:
            return _unauthorized_response("Authentication required")

        if not is_global_admin(auth):
            return _forbidden_response("Global admin access required")

        return fn(event, context, auth)
    return wrapper


def require_authenticated(fn: Callable):
    """
    Decorator requiring authentication (any valid user).

    Does not check specific permissions, just that the user is authenticated.

    Usage:
        @require_authenticated
        def handle_whoami(event, context, auth):
            return {'email': auth.email}
    """
    @wraps(fn)
    def wrapper(event: Dict[str, Any], context: Any):
        auth = get_auth_context(event)

        if not auth or not auth.is_authenticated:
            return _unauthorized_response("Authentication required")

        return fn(event, context, auth)
    return wrapper


def _unauthorized_response(message: str) -> Dict[str, Any]:
    """Create 401 Unauthorized response."""
    return {
        'statusCode': 401,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps({
            'error': 'unauthorized',
            'message': message,
        })
    }


def _forbidden_response(message: str) -> Dict[str, Any]:
    """Create 403 Forbidden response."""
    return {
        'statusCode': 403,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps({
            'error': 'forbidden',
            'message': message,
        })
    }
