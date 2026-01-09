"""
RBAC decorators and helpers for Lambda handlers.

Provides fine-grained authorization control at the handler level.
Each Lambda can use these decorators to enforce permission checks.
"""

import json
from functools import wraps
from enum import Enum
from typing import Dict, Any, List, Callable, Optional


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
ROLE_ACTIONS: Dict[str, List[Action]] = {
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


def get_auth_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract auth context from API Gateway authorizer.

    The Lambda Authorizer injects context into the request which is
    available in requestContext.authorizer.lambda.

    Returns:
        Dict with email, user_id, groups, and permissions
    """
    # Check for Lambda Authorizer context (API Gateway v2 format)
    authorizer = event.get('requestContext', {}).get('authorizer', {}).get('lambda', {})

    if authorizer:
        return {
            'email': authorizer.get('email', ''),
            'user_id': authorizer.get('user_id', ''),
            'groups': json.loads(authorizer.get('groups', '[]')),
            'permissions': json.loads(authorizer.get('permissions', '[]')),
        }

    # Fallback: Check for direct x-auth headers (from Lambda@Edge or direct injection)
    headers = event.get('headers', {}) or {}

    def get_header(name: str) -> str:
        lower_name = name.lower()
        for key, value in headers.items():
            if key.lower() == lower_name:
                return value
        return ''

    email = get_header('x-auth-user-email')
    if email:
        permissions_str = get_header('x-auth-permissions')
        return {
            'email': email,
            'user_id': get_header('x-auth-user-id') or email,
            'groups': get_header('x-auth-user-groups').split(',') if get_header('x-auth-user-groups') else [],
            'permissions': json.loads(permissions_str) if permissions_str else [],
        }

    # No auth context found
    return {
        'email': '',
        'user_id': '',
        'groups': [],
        'permissions': [],
    }


def check_permission(
    auth: Dict[str, Any],
    project: str,
    env: str,
    action: Action
) -> bool:
    """
    Check if user has permission for action on project/env.

    Permission matching rules:
    - project='*' matches any project
    - environment='*' matches any environment
    - Role must include the requested action

    Args:
        auth: Auth context from get_auth_context()
        project: Project identifier (e.g., 'homebox')
        env: Environment name (e.g., 'staging', 'production')
        action: Action to perform

    Returns:
        True if permission granted, False otherwise
    """
    for perm in auth.get('permissions', []):
        # Project match (wildcard or exact)
        perm_project = perm.get('project', '')
        if perm_project != '*' and perm_project != project:
            continue

        # Environment match (wildcard or exact)
        perm_env = perm.get('environment', '')
        if perm_env != '*' and perm_env != env:
            continue

        # Role allows action
        role = perm.get('role', '')
        role_actions = ROLE_ACTIONS.get(role, [])
        if action in role_actions:
            return True

    return False


def is_global_admin(auth: Dict[str, Any]) -> bool:
    """Check if user has global admin permissions (project=*, role=admin)."""
    for perm in auth.get('permissions', []):
        if perm.get('project') == '*' and perm.get('role') == 'admin':
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
            params = event.get('pathParameters', {}) or {}

            project = params.get('project', '*')
            env = params.get('env', '*')

            if not check_permission(auth, project, env, action):
                return {
                    'statusCode': 403,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*',
                    },
                    'body': json.dumps({
                        'error': 'forbidden',
                        'message': f'Permission denied: {action.value} on {project}/{env}',
                    })
                }

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

        if not is_global_admin(auth):
            return {
                'statusCode': 403,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
                'body': json.dumps({
                    'error': 'forbidden',
                    'message': 'Global admin access required',
                })
            }

        return fn(event, context, auth)
    return wrapper


def require_authenticated(fn: Callable):
    """
    Decorator requiring authentication (any valid user).

    Does not check specific permissions, just that the user is authenticated.

    Usage:
        @require_authenticated
        def handle_whoami(event, context, auth):
            return {'email': auth['email']}
    """
    @wraps(fn)
    def wrapper(event: Dict[str, Any], context: Any):
        auth = get_auth_context(event)

        if not auth.get('email'):
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
                'body': json.dumps({
                    'error': 'unauthorized',
                    'message': 'Authentication required',
                })
            }

        return fn(event, context, auth)
    return wrapper
