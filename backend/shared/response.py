"""
API response helpers for Lambda handlers.

Provides consistent response formatting across all endpoints.
"""

import json
from typing import Any, Dict, Optional


# Default CORS headers
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Auth-User-Email',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


def json_response(
    status_code: int,
    body: Any,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Create a JSON API Gateway response.

    Args:
        status_code: HTTP status code
        body: Response body (will be JSON serialized)
        headers: Additional headers to include

    Returns:
        API Gateway response dict
    """
    response_headers = {
        'Content-Type': 'application/json',
        **CORS_HEADERS,
    }
    if headers:
        response_headers.update(headers)

    return {
        'statusCode': status_code,
        'headers': response_headers,
        'body': json.dumps(body, default=str),
    }


def success_response(
    data: Any = None,
    message: Optional[str] = None,
    status_code: int = 200
) -> Dict[str, Any]:
    """
    Create a success response.

    Args:
        data: Response data
        message: Optional success message
        status_code: HTTP status code (default 200)

    Returns:
        API Gateway response dict
    """
    body: Dict[str, Any] = {}
    if data is not None:
        if isinstance(data, dict):
            body.update(data)
        else:
            body['data'] = data
    if message:
        body['message'] = message

    return json_response(status_code, body)


def error_response(
    error: str,
    message: str,
    status_code: int = 400,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create an error response.

    Args:
        error: Error code/type (e.g., 'not_found', 'validation_error')
        message: Human-readable error message
        status_code: HTTP status code
        details: Additional error details

    Returns:
        API Gateway response dict
    """
    body = {
        'error': error,
        'message': message,
    }
    if details:
        body['details'] = details

    return json_response(status_code, body)


def not_found_response(resource: str = 'Resource') -> Dict[str, Any]:
    """Create a 404 not found response."""
    return error_response(
        error='not_found',
        message=f'{resource} not found',
        status_code=404
    )


def unauthorized_response(message: str = 'Authentication required') -> Dict[str, Any]:
    """Create a 401 unauthorized response."""
    return error_response(
        error='unauthorized',
        message=message,
        status_code=401
    )


def forbidden_response(message: str = 'Access denied') -> Dict[str, Any]:
    """Create a 403 forbidden response."""
    return error_response(
        error='forbidden',
        message=message,
        status_code=403
    )


def validation_error_response(
    message: str,
    fields: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Create a 400 validation error response."""
    return error_response(
        error='validation_error',
        message=message,
        status_code=400,
        details={'fields': fields} if fields else None
    )


def internal_error_response(
    message: str = 'Internal server error',
    error_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create a 500 internal error response."""
    details = {'error_id': error_id} if error_id else None
    return error_response(
        error='internal_error',
        message=message,
        status_code=500,
        details=details
    )


def get_path_param(event: Dict[str, Any], name: str, default: str = '') -> str:
    """Get a path parameter from the event."""
    params = event.get('pathParameters', {}) or {}
    return params.get(name, default)


def get_query_param(event: Dict[str, Any], name: str, default: str = '') -> str:
    """Get a query string parameter from the event."""
    params = event.get('queryStringParameters', {}) or {}
    return params.get(name, default)


def get_query_params(event: Dict[str, Any]) -> Dict[str, str]:
    """Get all query string parameters from the event."""
    return event.get('queryStringParameters', {}) or {}


def get_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse JSON body from the event."""
    body = event.get('body', '')
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def get_method(event: Dict[str, Any]) -> str:
    """Get HTTP method from the event."""
    # API Gateway v2 format
    http = event.get('requestContext', {}).get('http', {})
    if http:
        return http.get('method', 'GET').upper()
    # API Gateway v1 format
    return event.get('httpMethod', 'GET').upper()


def get_path(event: Dict[str, Any]) -> str:
    """Get request path from the event."""
    # API Gateway v2 format
    raw_path = event.get('rawPath', '')
    if raw_path:
        return raw_path
    # API Gateway v1 format
    return event.get('path', '/')
