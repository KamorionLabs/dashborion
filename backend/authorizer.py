"""
Lambda Authorizer for API Gateway.

Validates authentication and returns IAM policy with user context.
Supports two authentication methods:
1. Bearer token (from CLI device flow)
2. SSO headers (from Lambda@Edge SAML flow)

The authorizer injects user context (email, permissions) into the request
which downstream handlers can access via:
- requestContext.authorizer.lambda (for payload format 2.0 simple response)
- requestContext.authorizer (for standard IAM policy response)

Note: This authorizer does NOT perform route-level permission checks.
Permission checks are delegated to individual Lambda handlers via
the @require_permission decorators in shared/rbac.py.
"""

import json
import os
from typing import Dict, Any, Optional

# Import auth modules
from auth.device_flow import validate_token
from auth.user_management import get_user, get_user_effective_permissions


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda Authorizer handler.

    Supports both:
    - Payload format 2.0 simple response (isAuthorized: bool)
    - Standard IAM policy response (policyDocument)

    The response format is determined by the API Gateway configuration.
    This handler returns the simple format by default, with full context.
    """
    print(f"Authorizer event type: {event.get('type', 'unknown')}")

    headers = event.get('headers', {}) or {}

    # Normalize headers to lowercase for consistent access
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    # Try to authenticate
    auth_result = authenticate(normalized_headers)

    if not auth_result:
        print("Authentication failed - no valid credentials found")
        return {
            'isAuthorized': False,
            'context': {
                'error': 'unauthorized',
                'message': 'No valid authentication found'
            }
        }

    email = auth_result['email']
    user_id = auth_result.get('user_id', email)
    groups = auth_result.get('groups', [])
    permissions = auth_result.get('permissions', [])

    print(f"Authorized: {email} with {len(permissions)} permissions")

    # Return simple response format with context
    # The context is available to downstream handlers via
    # event.requestContext.authorizer.lambda.*
    return {
        'isAuthorized': True,
        'context': {
            'email': email,
            'user_id': user_id,
            'groups': json.dumps(groups),
            'permissions': json.dumps(permissions),
        }
    }


def authenticate(headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Attempt to authenticate using available credentials.

    Tries in order:
    1. Bearer token in Authorization header (CLI device flow)
    2. SSO headers from Lambda@Edge (x-auth-user-email)

    Args:
        headers: Normalized (lowercase) request headers

    Returns:
        Dict with email, user_id, groups, permissions if authenticated, None otherwise
    """
    # Method 1: Bearer token (CLI)
    auth_header = headers.get('authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        print("Attempting Bearer token authentication")
        result = validate_bearer_token(token)
        if result:
            print(f"Bearer token valid for: {result.get('email')}")
            return result
        print("Bearer token validation failed")

    # Method 2: SSO headers from Lambda@Edge
    sso_email = headers.get('x-auth-user-email', '')
    if sso_email:
        print(f"Attempting SSO authentication for: {sso_email}")
        result = validate_sso_session(headers)
        if result:
            print(f"SSO session valid for: {result.get('email')}")
            return result
        print("SSO session validation failed")

    return None


def validate_bearer_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate Bearer token from CLI device flow.

    Args:
        token: Access token

    Returns:
        Auth context dict or None
    """
    auth_context = validate_token(token)
    if not auth_context:
        return None

    # Convert Permission objects to dicts for JSON serialization
    permissions = [
        {
            'project': p.project,
            'environment': p.environment,
            'role': p.role.value,
            'resources': p.resources,
        }
        for p in auth_context.permissions
    ]

    return {
        'email': auth_context.email,
        'user_id': auth_context.user_id,
        'groups': auth_context.groups or [],
        'permissions': permissions,
    }


def validate_sso_session(headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Validate SSO session from Lambda@Edge headers.

    Lambda@Edge has already validated the SAML assertion and set
    the x-auth-* headers. We trust these headers and look up
    permissions from DynamoDB.

    Args:
        headers: Normalized (lowercase) request headers

    Returns:
        Auth context dict or None
    """
    email = headers.get('x-auth-user-email', '')
    if not email:
        return None

    email = email.lower()

    # Get user from DynamoDB
    user = get_user(email)

    if user and user.disabled:
        print(f"User {email} is disabled")
        return None

    # Get SSO groups from header
    sso_groups_str = headers.get('x-auth-user-groups', '')
    sso_groups = [g.strip() for g in sso_groups_str.split(',') if g.strip()]

    # Get local groups from user record
    local_groups = user.local_groups if user else []

    # Get effective permissions
    permissions = get_user_effective_permissions(
        email=email,
        local_groups=local_groups,
        sso_groups=sso_groups,
    )

    # Convert Permission objects to dicts for JSON serialization
    permissions_list = [
        {
            'project': p.project,
            'environment': p.environment,
            'role': p.role.value,
            'resources': p.resources,
        }
        for p in permissions
    ]

    return {
        'email': email,
        'user_id': email,  # Use email as user_id for SSO users
        'groups': sso_groups,
        'permissions': permissions_list,
    }
