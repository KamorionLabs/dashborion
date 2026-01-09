"""
Auth Lambda Handler.

Main entry point for all authentication endpoints.
Routes requests to specific handlers based on path.

Public endpoints (no auth required):
- POST /api/auth/device/code
- POST /api/auth/device/token
- POST /api/auth/sso/exchange
- POST /api/auth/login

Protected endpoints (auth required):
- GET /api/auth/me
- GET /api/auth/whoami
- POST /api/auth/device/verify
- POST /api/auth/token/refresh
- POST /api/auth/token/revoke
- POST /api/auth/token/issue (SSO cookie to Bearer token exchange)
"""

import json
from typing import Dict, Any

# Import existing handlers
from .handlers import (
    handle_device_code_request,
    handle_device_token_request,
    handle_device_verify,
    handle_token_refresh,
    handle_token_revoke,
    handle_token_issue,
    handle_sso_exchange,
    handle_login,
    handle_auth_me,
    handle_auth_whoami,
)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for auth endpoints.

    Routes requests based on HTTP method and path.
    """
    # Extract request info
    request_context = event.get('requestContext', {})
    http = request_context.get('http', {})
    method = http.get('method', event.get('httpMethod', 'GET'))
    path = event.get('rawPath', event.get('path', ''))

    # Route table
    routes = {
        # Public endpoints
        ('POST', '/api/auth/device/code'): handle_device_code_request,
        ('POST', '/api/auth/device/token'): handle_device_token_request,
        ('POST', '/api/auth/sso/exchange'): handle_sso_exchange,
        ('POST', '/api/auth/login'): handle_login,

        # Protected endpoints (Lambda Authorizer checks auth)
        ('GET', '/api/auth/me'): handle_auth_me,
        ('GET', '/api/auth/whoami'): handle_auth_whoami,
        ('POST', '/api/auth/device/verify'): handle_device_verify,
        ('POST', '/api/auth/token/refresh'): handle_token_refresh,
        ('POST', '/api/auth/token/revoke'): handle_token_revoke,
        ('POST', '/api/auth/token/issue'): handle_token_issue,
    }

    # Find handler
    route_handler = routes.get((method, path))

    if route_handler:
        return route_handler(event, context)

    # Not found
    return {
        'statusCode': 404,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps({
            'error': 'not_found',
            'message': f'Unknown auth endpoint: {method} {path}',
        }),
    }
