"""
Lambda Authorizer for API Gateway.

Validates authentication and returns IAM policy with user context.
Supports four authentication methods:
1. Cookie session (from SAML SSO web flow)
2. Bearer token (from CLI device flow)
3. SigV4 IAM Identity Center (for AWS SSO users - AWSReservedSSO_*)
4. SigV4 IAM Service Role (for M2M - any other IAM role)

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
from auth.session_auth import validate_session_cookie
from auth.sigv4_auth import validate_sigv4_auth
from auth.service_auth import validate_service_auth
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
    request_context = event.get('requestContext', {})

    # Normalize headers to lowercase for consistent access
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    # Try to authenticate
    auth_result = authenticate(normalized_headers, request_context)

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
    auth_method = auth_result.get('auth_method', 'unknown')

    print(f"Authorized: {email} via {auth_method} with {len(permissions)} permissions")

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
            'auth_method': auth_method,
        }
    }


def authenticate(
    headers: Dict[str, str],
    request_context: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Attempt to authenticate using available credentials.

    Tries in order:
    1. Cookie session (SAML web SSO)
    2. Bearer token (CLI device flow)
    3. SigV4 IAM (AWS Identity Center)

    Args:
        headers: Normalized (lowercase) request headers
        request_context: API Gateway request context

    Returns:
        Dict with email, user_id, groups, permissions, auth_method if authenticated
    """
    # Method 1: Cookie session (SAML SSO)
    cookie_header = headers.get('cookie', '')
    if cookie_header and '__dashborion_session=' in cookie_header:
        print("Attempting Cookie session authentication")
        auth_context = validate_session_cookie(cookie_header)
        if auth_context:
            print(f"Cookie session valid for: {auth_context.email}")
            return format_auth_result(auth_context, 'cookie')
        print("Cookie session validation failed")

    # Method 2: Bearer token (CLI)
    auth_header = headers.get('authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        print("Attempting Bearer token authentication")
        auth_context = validate_token(token)
        if auth_context:
            print(f"Bearer token valid for: {auth_context.email}")
            return format_auth_result(auth_context, 'bearer')
        print("Bearer token validation failed")

    # Method 3: SigV4 IAM (AWS Identity Center users)
    identity = request_context.get('identity', {})
    user_arn = identity.get('userArn', '')
    account_id = identity.get('accountId', '')

    if user_arn and 'AWSReservedSSO_' in user_arn:
        # Identity Center user
        enable_sigv4_users = os.environ.get('ENABLE_SIGV4_USERS', 'true').lower() == 'true'
        if enable_sigv4_users:
            print(f"Attempting SigV4 IAM authentication for: {user_arn}")
            sigv4_identity = validate_sigv4_auth(user_arn, account_id)
            if sigv4_identity and sigv4_identity.email:
                result = authenticate_sigv4_user(sigv4_identity.email)
                if result:
                    print(f"SigV4 IAM valid for: {sigv4_identity.email}")
                    result['auth_method'] = 'sigv4_user'
                    return result
            print("SigV4 IAM user validation failed")
    elif user_arn:
        # Method 4: SigV4 IAM Service Role (M2M)
        enable_sigv4_services = os.environ.get('ENABLE_SIGV4_SERVICES', 'false').lower() == 'true'
        if enable_sigv4_services:
            print(f"Attempting SigV4 M2M service authentication for: {user_arn}")
            auth_context = validate_service_auth(user_arn, account_id)
            if auth_context:
                print(f"SigV4 M2M valid for: {auth_context.email}")
                return format_auth_result(auth_context, 'sigv4_service')
            print("SigV4 M2M service validation failed")

    return None


def format_auth_result(auth_context, auth_method: str) -> Dict[str, Any]:
    """Format AuthContext into auth result dict."""
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
        'auth_method': auth_method,
    }


def authenticate_sigv4_user(email: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user identified by SigV4.

    Looks up user in DynamoDB and returns permissions.

    Args:
        email: Email extracted from Identity Center session name

    Returns:
        Auth result dict or None if user not found/disabled
    """
    from auth.models import Permission, DashborionRole

    email = email.lower()

    # Get user from DynamoDB
    user = get_user(email)

    if user and user.disabled:
        print(f"[SigV4] User {email} is disabled")
        return None

    # For SigV4, we don't have SSO groups from SAML
    # User must have permissions assigned directly or via local groups
    local_groups = user.local_groups if user else []

    # Get effective permissions
    permissions = get_user_effective_permissions(
        email=email,
        local_groups=local_groups,
        sso_groups=[],  # No SSO groups for SigV4
    )

    # If user doesn't exist and no permissions, reject
    if not user and not permissions:
        print(f"[SigV4] User {email} not found and no permissions")
        return None

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
        'user_id': email,
        'groups': local_groups,
        'permissions': permissions_list,
    }
