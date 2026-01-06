"""
API Gateway Lambda Authorizer

Handles authentication for both:
- Web dashboard (session cookie from Lambda@Edge SAML)
- CLI (JWT Bearer token from Device Flow or AWS SSO exchange)

Returns authorization decision with user context passed to backend Lambda.
"""

import os
import json
import base64
import hashlib
import hmac
import time
import re
from typing import Optional, Dict, Any, Tuple
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError


# =============================================================================
# CONFIGURATION
# =============================================================================

COOKIE_NAME = os.environ.get('SESSION_COOKIE_NAME', 'dashborion_session')
PERMISSIONS_TABLE = os.environ.get('PERMISSIONS_TABLE', 'dashborion-permissions')
TOKENS_TABLE = os.environ.get('TOKENS_TABLE', 'dashborion-tokens')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'dashborion')

# Secrets Manager ARNs (loaded at runtime)
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN', '')
SESSION_ENCRYPTION_KEY_ARN = os.environ.get('SESSION_ENCRYPTION_KEY_ARN', '')

# Permission cache TTL (seconds)
PERMISSION_CACHE_TTL = 300  # 5 minutes

# Secrets cache (lazy loaded)
_secrets_cache: Dict[str, Tuple[float, str]] = {}
SECRETS_CACHE_TTL = 300  # 5 minutes


def get_secret(secret_arn: str) -> Optional[str]:
    """
    Get secret value from Secrets Manager with caching.
    """
    if not secret_arn:
        return None

    # Check cache
    if secret_arn in _secrets_cache:
        cached_time, cached_value = _secrets_cache[secret_arn]
        if time.time() - cached_time < SECRETS_CACHE_TTL:
            return cached_value

    try:
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId=secret_arn)
        secret_value = response.get('SecretString', '')

        # Cache result
        _secrets_cache[secret_arn] = (time.time(), secret_value)
        return secret_value

    except ClientError as e:
        print(f"Failed to get secret {secret_arn}: {e}")
        return None


def get_jwt_secret() -> str:
    """Get JWT signing secret from Secrets Manager."""
    return get_secret(JWT_SECRET_ARN) or ''


def get_encryption_key() -> str:
    """Get session encryption key from Secrets Manager."""
    return get_secret(SESSION_ENCRYPTION_KEY_ARN) or ''


# =============================================================================
# ROUTE PERMISSIONS
# =============================================================================

# Routes that don't require authentication
PUBLIC_ROUTES = [
    (r'^/api/health$', ['GET']),
    (r'^/api/auth/device/code$', ['POST']),
    (r'^/api/auth/device/token$', ['POST']),
    (r'^/api/auth/sso/exchange$', ['POST']),
]

# Routes that require specific permissions
# Format: (pattern, methods, required_permission)
# Permission: 'read', 'deploy', 'admin'
PROTECTED_ROUTES = [
    # Read-only routes (viewer role)
    (r'^/api/config$', ['GET'], 'read'),
    (r'^/api/services', ['GET'], 'read'),
    (r'^/api/details/', ['GET'], 'read'),
    (r'^/api/pipelines/', ['GET'], 'read'),
    (r'^/api/images/', ['GET'], 'read'),
    (r'^/api/metrics/', ['GET'], 'read'),
    (r'^/api/infrastructure/', ['GET'], 'read'),
    (r'^/api/tasks/', ['GET'], 'read'),
    (r'^/api/logs/', ['GET'], 'read'),
    (r'^/api/events/', ['GET', 'POST'], 'read'),

    # Auth info routes (any authenticated user)
    (r'^/api/auth/me$', ['GET'], 'read'),
    (r'^/api/auth/whoami$', ['GET'], 'read'),
    (r'^/api/auth/device/verify$', ['POST'], 'read'),
    (r'^/api/auth/token/refresh$', ['POST'], 'read'),
    (r'^/api/auth/token/revoke$', ['POST'], 'read'),

    # Deploy actions (operator role)
    (r'^/api/actions/build/', ['POST'], 'deploy'),
    (r'^/api/actions/deploy/[^/]+/[^/]+/reload$', ['POST'], 'deploy'),
    (r'^/api/actions/deploy/[^/]+/[^/]+/latest$', ['POST'], 'deploy'),
    (r'^/api/actions/deploy/[^/]+/[^/]+/start$', ['POST'], 'deploy'),
    (r'^/api/actions/cloudfront/', ['POST'], 'deploy'),

    # Admin actions (admin role)
    (r'^/api/actions/deploy/[^/]+/[^/]+/stop$', ['POST'], 'admin'),
    (r'^/api/actions/rds/', ['POST'], 'admin'),
    (r'^/api/admin/', ['GET', 'POST', 'PUT', 'DELETE'], 'admin'),
]

# Role hierarchy: admin > operator (deploy) > viewer (read)
ROLE_PERMISSIONS = {
    'viewer': ['read'],
    'operator': ['read', 'deploy'],
    'admin': ['read', 'deploy', 'admin'],
}


# =============================================================================
# CRYPTO UTILITIES
# =============================================================================

def decrypt_session_cookie(encrypted_data: str) -> Optional[Dict[str, Any]]:
    """
    Decrypt AES-256-GCM encrypted session cookie.
    Format: base64(iv:tag:ciphertext)
    """
    encryption_key = get_encryption_key()
    if not encryption_key:
        print("SESSION_ENCRYPTION_KEY not configured")
        return None

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        # Decode base64
        raw = base64.b64decode(encrypted_data)

        # Extract components (IV:TAG:CIPHERTEXT)
        iv = raw[:12]  # 96-bit IV
        tag = raw[12:28]  # 128-bit tag
        ciphertext = raw[28:]

        # Derive key from secret
        key = hashlib.sha256(encryption_key.encode()).digest()

        # Decrypt
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(iv, ciphertext + tag, None)

        return json.loads(plaintext.decode('utf-8'))

    except Exception as e:
        print(f"Failed to decrypt session cookie: {e}")
        return None


def validate_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate JWT token and return payload.
    Simple HS256 validation (same as device_flow.py)
    """
    jwt_secret = get_jwt_secret()
    if not jwt_secret:
        print("JWT_SECRET not configured")
        return None

    try:
        # Split token
        parts = token.split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        message = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            jwt_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b'=').decode()

        # Pad signature for comparison
        sig_padded = signature_b64 + '=' * (4 - len(signature_b64) % 4)
        expected_padded = expected_sig_b64 + '=' * (4 - len(expected_sig_b64) % 4)

        if not hmac.compare_digest(sig_padded, expected_padded):
            print("JWT signature mismatch")
            return None

        # Decode payload
        payload_padded = payload_b64 + '=' * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_padded))

        # Check expiration
        if payload.get('exp', 0) < time.time():
            print("JWT token expired")
            return None

        return payload

    except Exception as e:
        print(f"Failed to validate JWT: {e}")
        return None


def validate_token_in_db(token_hash: str) -> Optional[Dict[str, Any]]:
    """Check if token exists and is not revoked in DynamoDB"""
    if not TOKENS_TABLE:
        return None

    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(TOKENS_TABLE)

        response = table.get_item(
            Key={
                'pk': f'TOKEN#{token_hash}',
                'sk': 'metadata'
            }
        )

        item = response.get('Item')
        if not item:
            return None

        # Check if revoked
        if item.get('revoked'):
            print("Token has been revoked")
            return None

        # Check expiry
        if item.get('ttl', 0) < time.time():
            print("Token expired in DB")
            return None

        return item

    except ClientError as e:
        print(f"DynamoDB error checking token: {e}")
        return None


# =============================================================================
# PERMISSION LOADING
# =============================================================================

# Simple in-memory cache for permissions
_permission_cache: Dict[str, Tuple[float, list]] = {}


def get_user_permissions(email: str, project: str = None) -> list:
    """
    Load user permissions from DynamoDB.
    Returns list of permission strings like: "project:env:role"
    """
    cache_key = f"{email}:{project or '*'}"

    # Check cache
    if cache_key in _permission_cache:
        cached_time, cached_perms = _permission_cache[cache_key]
        if time.time() - cached_time < PERMISSION_CACHE_TTL:
            return cached_perms

    permissions = []

    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(PERMISSIONS_TABLE)

        # Query all permissions for user
        response = table.query(
            KeyConditionExpression='pk = :pk',
            ExpressionAttributeValues={
                ':pk': f'USER#{email}'
            }
        )

        for item in response.get('Items', []):
            perm_project = item.get('project', '*')
            perm_env = item.get('environment', '*')
            perm_role = item.get('role', 'viewer')

            # Filter by project if specified
            if project and perm_project not in [project, '*']:
                continue

            permissions.append({
                'project': perm_project,
                'environment': perm_env,
                'role': perm_role,
                'resources': item.get('resources', ['*']),
                'conditions': item.get('conditions', {})
            })

        # Cache result
        _permission_cache[cache_key] = (time.time(), permissions)

    except ClientError as e:
        print(f"DynamoDB error loading permissions: {e}")

    return permissions


def check_permission(permissions: list, required: str, env: str = None) -> bool:
    """
    Check if user has required permission level.

    Args:
        permissions: List of user permission objects
        required: Required permission ('read', 'deploy', 'admin')
        env: Optional environment to check (extracted from path)
    """
    for perm in permissions:
        # Check environment match
        perm_env = perm.get('environment', '*')
        if env and perm_env not in [env, '*']:
            continue

        # Check role grants required permission
        role = perm.get('role', 'viewer')
        role_perms = ROLE_PERMISSIONS.get(role, [])

        if required in role_perms:
            return True

    return False


# =============================================================================
# ROUTE MATCHING
# =============================================================================

def is_public_route(path: str, method: str) -> bool:
    """Check if route is public (no auth required)"""
    for pattern, methods in PUBLIC_ROUTES:
        if method in methods and re.match(pattern, path):
            return True
    return False


def get_required_permission(path: str, method: str) -> Optional[str]:
    """Get required permission for a route"""
    for pattern, methods, permission in PROTECTED_ROUTES:
        if method in methods and re.match(pattern, path):
            return permission

    # Default: require read permission for any unmatched route
    return 'read'


def extract_env_from_path(path: str) -> Optional[str]:
    """Extract environment from API path"""
    # Patterns like /api/services/{env}, /api/actions/deploy/{env}/...
    patterns = [
        r'^/api/services/([^/]+)',
        r'^/api/details/([^/]+)',
        r'^/api/infrastructure/([^/]+)',
        r'^/api/tasks/([^/]+)',
        r'^/api/logs/([^/]+)',
        r'^/api/events/([^/]+)',
        r'^/api/metrics/([^/]+)',
        r'^/api/actions/deploy/([^/]+)',
        r'^/api/actions/rds/([^/]+)',
        r'^/api/actions/cloudfront/([^/]+)',
    ]

    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            return match.group(1)

    return None


# =============================================================================
# MAIN HANDLER
# =============================================================================

def handler(event, context):
    """
    Lambda Authorizer handler.

    Supports API Gateway HTTP API (payload format 2.0)
    """
    print(f"Authorizer event: {json.dumps(event)}")

    # Extract request info
    route_arn = event.get('routeArn', '')
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path = event.get('requestContext', {}).get('http', {}).get('path', '/')
    headers = event.get('headers', {})

    # Normalize headers to lowercase
    headers = {k.lower(): v for k, v in headers.items()}

    # Check if public route
    if is_public_route(path, method):
        print(f"Public route: {method} {path}")
        return {
            'isAuthorized': True,
            'context': {
                'userId': 'anonymous',
                'isPublic': True
            }
        }

    # Try to authenticate
    user_context = None

    # 1. Try Bearer token (CLI)
    auth_header = headers.get('authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        print("Attempting Bearer token authentication")

        # Validate JWT
        payload = validate_jwt_token(token)
        if payload:
            # Verify token not revoked
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            db_token = validate_token_in_db(token_hash)

            if db_token or not TOKENS_TABLE:  # Skip DB check if table not configured
                user_context = {
                    'userId': payload.get('sub', payload.get('email', '')),
                    'email': payload.get('email', ''),
                    'groups': payload.get('groups', []),
                    'sessionId': payload.get('jti', ''),
                    'authMethod': 'bearer'
                }

    # 2. Try session cookie (Web)
    if not user_context:
        cookie_header = headers.get('cookie', '')
        if cookie_header:
            print("Attempting cookie authentication")

            # Parse cookies
            cookies = {}
            for cookie in cookie_header.split(';'):
                if '=' in cookie:
                    name, value = cookie.strip().split('=', 1)
                    cookies[name] = value

            session_cookie = cookies.get(COOKIE_NAME)
            if session_cookie:
                session = decrypt_session_cookie(session_cookie)
                if session:
                    # Check session expiry
                    if session.get('expiresAt', 0) > time.time():
                        user_context = {
                            'userId': session.get('userId', session.get('email', '')),
                            'email': session.get('email', ''),
                            'groups': session.get('groups', []),
                            'sessionId': session.get('sessionId', ''),
                            'authMethod': 'cookie'
                        }
                    else:
                        print("Session cookie expired")

    # No valid authentication found
    if not user_context:
        print(f"Authentication failed for {method} {path}")
        return {
            'isAuthorized': False,
            'context': {
                'error': 'unauthorized',
                'message': 'No valid authentication found'
            }
        }

    # Load user permissions
    email = user_context.get('email', '')
    permissions = get_user_permissions(email, PROJECT_NAME)

    # Get required permission for this route
    required_permission = get_required_permission(path, method)
    env = extract_env_from_path(path)

    print(f"User: {email}, Required: {required_permission}, Env: {env}")
    print(f"User permissions: {json.dumps(permissions)}")

    # Check permission
    if required_permission and not check_permission(permissions, required_permission, env):
        print(f"Permission denied: {email} lacks '{required_permission}' for env={env}")
        return {
            'isAuthorized': False,
            'context': {
                'error': 'forbidden',
                'message': f'Permission denied: requires {required_permission}',
                'userId': email
            }
        }

    # Build permission strings for context
    perm_strings = []
    for perm in permissions:
        perm_strings.append(f"{perm['project']}:{perm['environment']}:{perm['role']}")

    # Authorized!
    print(f"Authorized: {email} for {method} {path}")
    return {
        'isAuthorized': True,
        'context': {
            'userId': user_context['userId'],
            'email': user_context['email'],
            'groups': json.dumps(user_context.get('groups', [])),
            'permissions': json.dumps(perm_strings),
            'sessionId': user_context.get('sessionId', ''),
            'authMethod': user_context.get('authMethod', '')
        }
    }
