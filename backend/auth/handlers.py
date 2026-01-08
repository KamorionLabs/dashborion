"""
API Handlers for Authentication Endpoints

Provides REST API endpoints for:
- Device Flow (CLI authentication)
- Token validation
- User info
"""

import json
import os
from typing import Dict, Any, Optional

from .models import AuthContext, UnauthorizedError
from .middleware import authorize_request, get_auth_context
from .device_flow import (
    create_device_code,
    exchange_device_code,
    authorize_device_code,
    refresh_access_token,
    revoke_token,
    validate_token,
    DeviceCodePendingError,
    DeviceCodeExpiredError,
    DeviceCodeDeniedError,
    generate_access_token,
    generate_refresh_token,
    AccessToken,
    ACCESS_TOKEN_TTL,
    _store_token,
)
from .permissions import get_user_permissions


def _json_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        },
        'body': json.dumps(body),
    }


def _get_base_url(event: Dict[str, Any]) -> str:
    """Extract base URL from request"""
    headers = event.get('headers', {}) or {}
    host = headers.get('host', headers.get('Host', 'localhost'))
    protocol = 'https' if headers.get('x-forwarded-proto') == 'https' else 'http'

    # Check for custom domain
    if 'cloudfront' in host.lower() or '.' in host:
        protocol = 'https'

    return f"{protocol}://{host}"


def _parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse JSON body from request"""
    body = event.get('body', '{}')
    if not body:
        return {}

    # Handle base64 encoding
    if event.get('isBase64Encoded'):
        import base64
        body = base64.b64decode(body).decode('utf-8')

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def _get_bearer_token(event: Dict[str, Any]) -> Optional[str]:
    """Extract Bearer token from Authorization header"""
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization', headers.get('Authorization', ''))

    if auth_header.lower().startswith('bearer '):
        return auth_header[7:]

    return None


# =============================================================================
# Device Flow Endpoints
# =============================================================================

def handle_device_code_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    POST /api/auth/device/code

    Start device authorization flow. CLI calls this to get a code.

    Request body:
        {
            "client_id": "dashborion-cli"  // Optional, defaults to "cli"
        }

    Response:
        {
            "device_code": "...",          // Secret, for CLI polling
            "user_code": "ABCD-1234",      // User enters this
            "verification_uri": "https://...",
            "verification_uri_complete": "https://...?code=ABCD-1234",
            "expires_in": 600,
            "interval": 5
        }
    """
    body = _parse_body(event)
    client_id = body.get('client_id', 'dashborion-cli')
    base_url = _get_base_url(event)

    code = create_device_code(client_id, base_url)

    return _json_response(200, {
        'device_code': code.device_code,
        'user_code': code.user_code,
        'verification_uri': code.verification_uri,
        'verification_uri_complete': f"{code.verification_uri}?code={code.user_code}",
        'expires_in': code.expires_at - int(__import__('time').time()),
        'interval': code.interval,
    })


def handle_device_token_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    POST /api/auth/device/token

    Poll for access token (CLI calls this repeatedly).

    Request body:
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": "...",
            "client_id": "dashborion-cli"
        }

    Response (success):
        {
            "access_token": "...",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "...",
            "scope": "read write"
        }

    Response (pending):
        HTTP 400
        {
            "error": "authorization_pending",
            "error_description": "..."
        }

    Response (expired):
        HTTP 400
        {
            "error": "expired_token",
            "error_description": "..."
        }
    """
    body = _parse_body(event)
    grant_type = body.get('grant_type', '')
    device_code = body.get('device_code', '')

    # Validate grant type
    if grant_type != 'urn:ietf:params:oauth:grant-type:device_code':
        return _json_response(400, {
            'error': 'unsupported_grant_type',
            'error_description': 'Expected grant_type: urn:ietf:params:oauth:grant-type:device_code',
        })

    if not device_code:
        return _json_response(400, {
            'error': 'invalid_request',
            'error_description': 'device_code is required',
        })

    try:
        token = exchange_device_code(device_code)

        if token:
            return _json_response(200, {
                'access_token': token.token,
                'token_type': token.token_type,
                'expires_in': token.expires_in,
                'refresh_token': token.refresh_token,
                'scope': token.scope,
            })
        else:
            return _json_response(400, {
                'error': 'invalid_grant',
                'error_description': 'Invalid or unknown device code',
            })

    except DeviceCodePendingError as e:
        return _json_response(400, {
            'error': e.error,
            'error_description': e.description,
        })

    except DeviceCodeExpiredError as e:
        return _json_response(400, {
            'error': e.error,
            'error_description': e.description,
        })

    except DeviceCodeDeniedError as e:
        return _json_response(400, {
            'error': e.error,
            'error_description': e.description,
        })


def handle_device_verify(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    POST /api/auth/device/verify

    Called by web UI after user authenticates to authorize the device code.

    Request body:
        {
            "user_code": "ABCD-1234"
        }

    Requires: Valid session (user must be authenticated via SAML)

    Response:
        {
            "success": true,
            "message": "Device authorized"
        }
    """
    # Require authentication
    auth = get_auth_context(event)
    if not auth or not auth.is_authenticated:
        return _json_response(401, {
            'error': 'unauthorized',
            'error_description': 'Authentication required',
        })

    body = _parse_body(event)
    user_code = body.get('user_code', '').upper().strip()

    if not user_code:
        return _json_response(400, {
            'error': 'invalid_request',
            'error_description': 'user_code is required',
        })

    # Normalize format (accept with or without hyphen)
    if '-' not in user_code and len(user_code) == 8:
        user_code = f"{user_code[:4]}-{user_code[4:]}"

    success = authorize_device_code(user_code, auth)

    if success:
        return _json_response(200, {
            'success': True,
            'message': 'Device authorized. You can close this window.',
        })
    else:
        return _json_response(400, {
            'error': 'invalid_code',
            'error_description': 'Invalid or expired code',
        })


# =============================================================================
# Token Endpoints
# =============================================================================

def handle_token_refresh(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    POST /api/auth/token/refresh

    Refresh an access token.

    Request body:
        {
            "grant_type": "refresh_token",
            "refresh_token": "..."
        }

    Response:
        {
            "access_token": "...",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "...",
            "scope": "read write"
        }
    """
    body = _parse_body(event)
    grant_type = body.get('grant_type', '')
    refresh_token = body.get('refresh_token', '')

    if grant_type != 'refresh_token':
        return _json_response(400, {
            'error': 'unsupported_grant_type',
            'error_description': 'Expected grant_type: refresh_token',
        })

    if not refresh_token:
        return _json_response(400, {
            'error': 'invalid_request',
            'error_description': 'refresh_token is required',
        })

    token = refresh_access_token(refresh_token)

    if token:
        return _json_response(200, {
            'access_token': token.token,
            'token_type': token.token_type,
            'expires_in': token.expires_in,
            'refresh_token': token.refresh_token,
            'scope': token.scope,
        })
    else:
        return _json_response(400, {
            'error': 'invalid_grant',
            'error_description': 'Invalid or expired refresh token',
        })


def handle_token_revoke(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    POST /api/auth/token/revoke

    Revoke an access token (logout).

    Request: Bearer token in Authorization header

    Response:
        {
            "success": true
        }
    """
    token = _get_bearer_token(event)

    if not token:
        return _json_response(400, {
            'error': 'invalid_request',
            'error_description': 'Bearer token required',
        })

    success = revoke_token(token)

    return _json_response(200, {
        'success': success,
    })


# =============================================================================
# User Info Endpoints
# =============================================================================

def handle_auth_me(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /api/auth/me

    Get current user info and permissions.
    Supports both session auth (web) and bearer token (CLI).

    Response:
        {
            "user": {
                "id": "user@company.com",
                "email": "user@company.com",
                "groups": ["platform-team"],
                "mfa_verified": true
            },
            "permissions": [
                {
                    "project": "homebox",
                    "environment": "*",
                    "role": "operator",
                    "resources": ["*"]
                }
            ]
        }
    """
    # Try bearer token first (CLI)
    bearer_token = _get_bearer_token(event)
    if bearer_token:
        auth = validate_token(bearer_token)
        if not auth:
            return _json_response(401, {
                'error': 'invalid_token',
                'error_description': 'Invalid or expired token',
            })
    else:
        # Fall back to session auth (web)
        auth = get_auth_context(event)
        if not auth or not auth.is_authenticated:
            return _json_response(401, {
                'error': 'unauthorized',
                'error_description': 'Authentication required',
            })

    # Format permissions for response
    permissions = [
        {
            'project': p.project,
            'environment': p.environment,
            'role': p.role.value,
            'resources': p.resources,
        }
        for p in auth.permissions
    ]

    return _json_response(200, {
        'user': {
            'id': auth.user_id,
            'email': auth.email,
            'groups': auth.groups,
            'mfa_verified': auth.mfa_verified,
        },
        'permissions': permissions,
    })


def handle_auth_whoami(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /api/auth/whoami

    Simple endpoint to check authentication status.
    Returns minimal info, useful for CLI status check.

    Response (authenticated):
        {
            "authenticated": true,
            "email": "user@company.com",
            "method": "bearer" | "session"
        }

    Response (not authenticated):
        {
            "authenticated": false
        }
    """
    # Try bearer token first
    bearer_token = _get_bearer_token(event)
    if bearer_token:
        auth = validate_token(bearer_token)
        if auth:
            return _json_response(200, {
                'authenticated': True,
                'email': auth.email,
                'method': 'bearer',
            })

    # Try session auth
    auth = get_auth_context(event)
    if auth and auth.is_authenticated:
        return _json_response(200, {
            'authenticated': True,
            'email': auth.email,
            'method': 'session',
        })

    return _json_response(200, {
        'authenticated': False,
    })


# =============================================================================
# AWS SSO Integration
# =============================================================================

def handle_sso_exchange(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    POST /api/auth/sso/exchange

    Exchange AWS SSO credentials for Dashborion token.
    CLI can use existing AWS SSO session to authenticate.

    Request body:
        {
            "aws_access_key_id": "...",
            "aws_secret_access_key": "...",
            "aws_session_token": "..."
        }

    The CLI sends temporary AWS credentials from an SSO session.
    We validate them via STS GetCallerIdentity and extract user info.

    Response:
        {
            "access_token": "...",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "...",
            "user": {
                "email": "user@company.com",
                "arn": "arn:aws:sts::..."
            }
        }
    """
    import boto3

    body = _parse_body(event)
    access_key = body.get('aws_access_key_id', '')
    secret_key = body.get('aws_secret_access_key', '')
    session_token = body.get('aws_session_token', '')

    if not all([access_key, secret_key, session_token]):
        return _json_response(400, {
            'error': 'invalid_request',
            'error_description': 'AWS credentials required',
        })

    try:
        # Validate credentials via STS
        sts = boto3.client(
            'sts',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
        )

        identity = sts.get_caller_identity()
        user_arn = identity['Arn']
        account_id = identity['Account']

        # Extract email from ARN
        # ARN format: arn:aws:sts::ACCOUNT:assumed-role/AWSReservedSSO_*/user@email.com
        email = None
        if 'assumed-role' in user_arn:
            parts = user_arn.split('/')
            if len(parts) >= 3:
                email = parts[-1]

        if not email or '@' not in email:
            return _json_response(400, {
                'error': 'invalid_identity',
                'error_description': 'Could not extract email from AWS identity',
            })

        # Look up permissions for this user
        from .permissions import get_user_permissions_from_db
        permissions = get_user_permissions_from_db(email)

        # Create tokens
        from .device_flow import (
            generate_access_token,
            generate_refresh_token,
            AccessToken,
            ACCESS_TOKEN_TTL,
            _store_token,
        )
        import time
        import json

        access_token = generate_access_token()
        refresh_token = generate_refresh_token()
        expires_at = int(time.time()) + ACCESS_TOKEN_TTL

        permissions_json = json.dumps([
            {
                'project': p.project,
                'environment': p.environment,
                'role': p.role.value,
                'resources': p.resources,
            }
            for p in permissions
        ])

        token = AccessToken(
            token=access_token,
            expires_in=ACCESS_TOKEN_TTL,
            expires_at=expires_at,
            refresh_token=refresh_token,
            user_id=email,
            email=email,
            permissions=permissions_json,
        )

        _store_token(token, 'sso-cli')

        return _json_response(200, {
            'access_token': token.token,
            'token_type': token.token_type,
            'expires_in': token.expires_in,
            'refresh_token': token.refresh_token,
            'user': {
                'email': email,
                'arn': user_arn,
                'account_id': account_id,
            },
        })

    except Exception as e:
        return _json_response(401, {
            'error': 'invalid_credentials',
            'error_description': str(e),
        })


# =============================================================================
# Simple Login (when SAML not available)
# =============================================================================

def _get_auth_users() -> Dict[str, Dict[str, Any]]:
    """Get configured users from AUTH_USERS environment variable"""
    import json
    users_json = os.environ.get('AUTH_USERS', '{}')
    try:
        return json.loads(users_json)
    except json.JSONDecodeError:
        return {}


def _verify_password(stored_hash: str, password: str) -> bool:
    """Verify password against stored hash (bcrypt or plain for dev)"""
    import hashlib

    # Support plain text for development (prefix with 'plain:')
    if stored_hash.startswith('plain:'):
        return stored_hash[6:] == password

    # Support sha256 hash (prefix with 'sha256:')
    if stored_hash.startswith('sha256:'):
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return stored_hash[7:] == password_hash

    # Default: plain text comparison (legacy)
    return stored_hash == password


def handle_login(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    POST /api/auth/login

    Simple username/password login for environments without SAML.

    Request body:
        {
            "email": "user@example.com",
            "password": "secret"
        }

    Response:
        {
            "access_token": "...",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "...",
            "user": {
                "email": "user@example.com",
                "role": "admin"
            }
        }
    """
    body = _parse_body(event)
    email = body.get('email', '').lower().strip()
    password = body.get('password', '')

    if not email or not password:
        return _json_response(400, {
            'error': 'invalid_request',
            'error_description': 'Email and password required',
        })

    # Get configured users
    users = _get_auth_users()
    user_config = users.get(email)

    if not user_config:
        return _json_response(401, {
            'error': 'invalid_credentials',
            'error_description': 'Invalid email or password',
        })

    # Verify password
    stored_password = user_config.get('password', '')
    if not _verify_password(stored_password, password):
        return _json_response(401, {
            'error': 'invalid_credentials',
            'error_description': 'Invalid email or password',
        })

    # Get user permissions
    role = user_config.get('role', 'viewer')
    groups = user_config.get('groups', [])
    projects = user_config.get('projects', ['*'])  # Default to all projects

    # Build permissions based on role
    permissions = []
    for project in projects:
        permissions.append({
            'project': project,
            'environment': '*',
            'role': role,
            'resources': ['*'],
        })

    permissions_json = json.dumps(permissions)

    # Generate tokens
    import time
    access_token = generate_access_token()
    refresh_token = generate_refresh_token()
    expires_at = int(time.time()) + ACCESS_TOKEN_TTL

    token = AccessToken(
        token=access_token,
        expires_in=ACCESS_TOKEN_TTL,
        expires_at=expires_at,
        refresh_token=refresh_token,
        user_id=email,
        email=email,
        permissions=permissions_json,
    )

    # Store token in DynamoDB
    _store_token(token, 'web-login')

    return _json_response(200, {
        'access_token': token.token,
        'token_type': token.token_type,
        'expires_in': token.expires_in,
        'refresh_token': token.refresh_token,
        'user': {
            'email': email,
            'role': role,
            'groups': groups,
        },
    })


# =============================================================================
# Route Handler
# =============================================================================

AUTH_ROUTES = {
    ('POST', '/api/auth/device/code'): handle_device_code_request,
    ('POST', '/api/auth/device/token'): handle_device_token_request,
    ('POST', '/api/auth/device/verify'): handle_device_verify,
    ('POST', '/api/auth/token/refresh'): handle_token_refresh,
    ('POST', '/api/auth/token/revoke'): handle_token_revoke,
    ('POST', '/api/auth/sso/exchange'): handle_sso_exchange,
    ('POST', '/api/auth/login'): handle_login,
    ('GET', '/api/auth/me'): handle_auth_me,
    ('GET', '/api/auth/whoami'): handle_auth_whoami,
}


def route_auth_request(event: Dict[str, Any], context: Any) -> Optional[Dict[str, Any]]:
    """
    Route auth-related requests to appropriate handler.

    Returns None if path is not an auth endpoint.
    """
    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    path = event.get('rawPath', event.get('path', ''))

    # Normalize path
    if not path.startswith('/api/auth'):
        return None

    handler = AUTH_ROUTES.get((method, path))
    if handler:
        return handler(event, context)

    return None
