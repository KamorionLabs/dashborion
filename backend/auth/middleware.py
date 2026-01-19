"""
Authentication Middleware for Lambda API Handlers

Extracts authentication context from Lambda Authorizer.
The authorizer validates credentials and injects user context into
requestContext.authorizer.lambda.

Supported auth methods (handled by Lambda Authorizer):
1. Cookie session (SAML SSO web flow)
2. Bearer token (CLI device flow)
3. SigV4 IAM Identity Center (AWS SSO users)
4. SigV4 IAM Service Role (M2M)
"""

import json
from typing import Dict, Any, Optional
from .models import AuthContext, Permission, DashborionRole, UnauthorizedError


def get_auth_context(event: Dict[str, Any]) -> Optional[AuthContext]:
    """
    Extract authentication context from Lambda event.

    The Lambda Authorizer has already validated credentials and injected
    user context into requestContext.authorizer.lambda.

    Falls back to Bearer token validation for direct API calls
    (e.g., local testing without authorizer).

    Returns None if no auth is present (unauthenticated request).
    """
    # Primary: Lambda Authorizer context (API Gateway v2 format)
    authorizer = event.get('requestContext', {}).get('authorizer', {}).get('lambda', {})
    print(f"[DEBUG] get_auth_context: authorizer={authorizer}")

    if authorizer and authorizer.get('email'):
        print(f"[DEBUG] get_auth_context: found email={authorizer.get('email')}, parsing authorizer context")
        return _parse_authorizer_context(authorizer)

    # Fallback: Bearer token (for direct calls without authorizer)
    headers = event.get('headers', {}) or {}
    auth_header = _get_header(headers, 'authorization')

    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]
        from .device_flow import validate_token
        return validate_token(token)

    return None


def _parse_authorizer_context(authorizer: Dict[str, Any]) -> AuthContext:
    """Parse Lambda Authorizer context into AuthContext."""
    email = authorizer.get('email', '')
    user_id = authorizer.get('user_id', email)
    auth_method = authorizer.get('auth_method', 'unknown')

    # Parse JSON fields
    try:
        groups = json.loads(authorizer.get('groups', '[]'))
    except (json.JSONDecodeError, TypeError):
        groups = []

    try:
        permissions_data = json.loads(authorizer.get('permissions', '[]'))
    except (json.JSONDecodeError, TypeError):
        permissions_data = []

    # Convert to Permission objects
    permissions = [
        Permission(
            project=p.get('project', '*'),
            environment=p.get('environment', '*'),
            role=DashborionRole.from_string(p.get('role', 'viewer')),
            resources=p.get('resources', ['*']),
            source=p.get('source', 'authorizer'),
        )
        for p in permissions_data
    ]

    return AuthContext(
        user_id=user_id,
        email=email,
        groups=groups,
        permissions=permissions,
        auth_method=auth_method,
        mfa_verified=str(authorizer.get('mfa_verified', 'false')).lower() == 'true',
    )


def _get_header(headers: Dict[str, str], name: str) -> str:
    """Get header value case-insensitively."""
    lower_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value
    return ''


def authorize_request(
    event: Dict[str, Any],
    require_auth: bool = True
) -> AuthContext:
    """
    Authorize a request and return auth context.

    Args:
        event: Lambda event
        require_auth: If True, raises UnauthorizedError if not authenticated

    Returns:
        AuthContext

    Raises:
        UnauthorizedError: If require_auth=True and user is not authenticated
    """
    auth = get_auth_context(event)

    if require_auth and (auth is None or not auth.is_authenticated):
        raise UnauthorizedError("Authentication required")

    # Return empty context for unauthenticated requests (when allowed)
    if auth is None:
        return AuthContext(user_id="", email="")

    return auth


def get_user_email(event: Dict[str, Any]) -> str:
    """
    Get user email from event.

    Convenience function for handlers that just need the email.
    """
    auth = get_auth_context(event)
    if auth and auth.email:
        return auth.email
    return 'unknown'
