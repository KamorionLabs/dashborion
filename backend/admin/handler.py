"""
Admin Lambda Handler.

Handles all admin-related endpoints:
- User management (CRUD)
- Group management (CRUD)
- Permission management
- Audit logs
- System initialization

All endpoints (except /api/admin/init) require global admin access.
"""

import json
from typing import Dict, Any

from shared.rbac import (
    get_auth_context,
    is_global_admin,
)
from shared.response import (
    json_response,
    error_response,
    get_method,
    get_path,
    get_body,
)

# Import existing admin handlers
from auth.admin_handlers import route_admin_request


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for admin endpoints.

    Routes requests to existing admin_handlers after RBAC check.
    """
    method = get_method(event)
    path = get_path(event)
    auth = get_auth_context(event)

    # Handle CORS preflight
    if method == 'OPTIONS':
        return json_response(200, {})

    # Parse body
    body = get_body(event)
    query_params = event.get('queryStringParameters') or {}

    # Special case: /api/admin/init is public (for initial setup)
    if path == '/api/admin/init':
        result = route_admin_request(path, method, body, query_params, 'system-init')
        return format_admin_response(result)

    # All other admin endpoints require global admin
    if not is_global_admin(auth):
        return error_response(
            'forbidden',
            'Global admin access required',
            403
        )

    # Get actor email from auth context
    actor_email = auth.get('email', 'unknown')

    # Route to existing admin handlers
    result = route_admin_request(path, method, body, query_params, actor_email)

    return format_admin_response(result)


def format_admin_response(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format admin handler result as API Gateway response.
    """
    if not result:
        return error_response('internal_error', 'No response from handler', 500)

    # Check for error
    if 'error' in result and not result.get('success', True):
        error_msg = result.get('error', 'Unknown error')
        status_code = result.get('code', 400)
        return error_response('admin_error', error_msg, status_code)

    # Success response
    return json_response(200, result)
