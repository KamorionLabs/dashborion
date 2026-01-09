"""
Authentication Middleware for Lambda API Handler

Extracts authentication context from Lambda@Edge headers
and validates user sessions.
"""

from typing import Dict, Any, Optional
from .models import AuthContext, Permission, DashborionRole, UnauthorizedError
from .permissions import parse_permissions_from_header
from .user_management import get_user, get_user_effective_permissions


def get_header(headers: Dict[str, str], name: str, default: str = "") -> str:
    """Get header value case-insensitively"""
    # Lambda headers can be lowercase or mixed case
    lower_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value
    return default


def extract_auth_headers(event: Dict[str, Any]) -> Dict[str, str]:
    """Extract auth headers from Lambda event"""
    headers = event.get('headers', {}) or {}
    return {
        'user_id': get_header(headers, 'x-auth-user-id'),
        'email': get_header(headers, 'x-auth-user-email'),
        'groups': get_header(headers, 'x-auth-user-groups'),
        'roles': get_header(headers, 'x-auth-user-roles'),
        'session_id': get_header(headers, 'x-auth-session-id'),
        'mfa_verified': get_header(headers, 'x-auth-mfa-verified'),
        'permissions': get_header(headers, 'x-auth-permissions'),
    }


def parse_roles(roles_str: str) -> list[DashborionRole]:
    """Parse roles from comma-separated string"""
    if not roles_str:
        return []

    roles = []
    for role_name in roles_str.split(','):
        role_name = role_name.strip()
        try:
            roles.append(DashborionRole(role_name))
        except ValueError:
            continue  # Skip unknown roles
    return roles


def get_auth_context(event: Dict[str, Any]) -> Optional[AuthContext]:
    """
    Extract authentication context from Lambda event.

    Supports two authentication methods:
    1. x-auth-* headers (from Lambda@Edge SSO)
    2. Bearer token (from CLI/API clients)

    Returns None if no auth headers are present (unauthenticated request).
    """
    headers = event.get('headers', {}) or {}
    auth_headers = extract_auth_headers(event)

    # Check x-auth-* headers first (Lambda@Edge SSO)
    if auth_headers['user_id'] or auth_headers['email']:
        email = auth_headers['email'] or auth_headers['user_id']
        groups = auth_headers['groups'].split(',') if auth_headers['groups'] else []

        # Get permissions from DynamoDB (authoritative source)
        # Lambda@Edge headers may include SSO groups, but permissions come from DB
        user = get_user(email)
        local_groups = user.local_groups if user else []

        # Combine local groups with SSO groups for permission lookup
        permissions = get_user_effective_permissions(email, local_groups, groups)

        return AuthContext(
            user_id=auth_headers['user_id'],
            email=email,
            groups=groups,
            roles=parse_roles(auth_headers['roles']),
            permissions=permissions,
            session_id=auth_headers['session_id'],
            mfa_verified=auth_headers['mfa_verified'].lower() == 'true',
        )

    # Check Bearer token (CLI/API clients)
    auth_header = get_header(headers, 'Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        from .device_flow import validate_token
        return validate_token(token)

    return None


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
    Get user email from event (backward compatible with existing code).

    Falls back to legacy x-sso-user-email header if new headers not present.
    """
    headers = event.get('headers', {}) or {}

    # Try new auth header first
    email = get_header(headers, 'x-auth-user-email')
    if email:
        return email

    # Fall back to legacy SSO header
    email = get_header(headers, 'x-sso-user-email')
    if email:
        return email

    return 'unknown'
