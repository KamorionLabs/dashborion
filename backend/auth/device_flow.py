"""
Device Authorization Flow for CLI Authentication

Implements RFC 8628 Device Authorization Grant for CLI clients
that cannot use browser-based SAML flow directly.

Flow:
1. CLI requests device code: POST /api/auth/device/code
2. User opens browser to verification URL with code
3. User authenticates via SAML
4. CLI polls for token: POST /api/auth/device/token
5. Once user completes auth, CLI receives access token
"""

import os
import time
import json
import secrets
import hashlib
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

import boto3
from botocore.exceptions import ClientError

from .models import AuthContext, Permission, DashborionRole

# KMS encryption - optional, enabled via environment variable
_kms_enabled = None

def _is_kms_enabled() -> bool:
    """Check if KMS encryption is enabled."""
    global _kms_enabled
    if _kms_enabled is None:
        _kms_enabled = bool(os.environ.get('KMS_KEY_ARN') or os.environ.get('KMS_KEY_ID'))
    return _kms_enabled

def _get_kms_crypto():
    """Lazy import KMS crypto module."""
    from shared.kms_crypto import encrypt_data, decrypt_data, token_context, refresh_context
    return encrypt_data, decrypt_data, token_context, refresh_context


class DeviceCodeStatus(str, Enum):
    """Status of a device code request"""
    PENDING = "pending"           # Waiting for user to authenticate
    AUTHORIZED = "authorized"     # User authenticated, ready to exchange
    EXPIRED = "expired"           # Code expired
    DENIED = "denied"             # User denied access


@dataclass
class DeviceCode:
    """Device code for CLI authentication"""
    device_code: str              # Secret code for CLI polling
    user_code: str                # Human-readable code for user
    verification_uri: str         # URL for user to visit
    expires_at: int               # Unix timestamp
    interval: int                 # Polling interval in seconds
    client_id: str                # CLI client identifier
    status: DeviceCodeStatus = DeviceCodeStatus.PENDING
    # Filled after user authenticates
    user_email: Optional[str] = None
    permissions: Optional[str] = None  # JSON-encoded permissions


@dataclass
class AccessToken:
    """Access token for CLI"""
    token: str
    token_type: str = "Bearer"
    expires_in: int = 3600        # 1 hour default
    expires_at: int = 0
    refresh_token: Optional[str] = None
    scope: str = "read write"
    # User info
    user_id: str = ""
    email: str = ""
    permissions: str = "[]"       # JSON-encoded


# Configuration
DEVICE_CODE_TTL = 600             # 10 minutes to complete auth
POLLING_INTERVAL = 5              # 5 seconds between polls
ACCESS_TOKEN_TTL = 3600           # 1 hour
REFRESH_TOKEN_TTL = 86400 * 30    # 30 days

# DynamoDB client (lazy init)
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.client('dynamodb')
    return _dynamodb


def _get_table_name(table_type: str) -> str:
    """Get DynamoDB table name from environment"""
    if table_type == "device_codes":
        return os.environ.get('DEVICE_CODES_TABLE_NAME', 'dashborion-device-codes')
    elif table_type == "tokens":
        return os.environ.get('TOKENS_TABLE_NAME', 'dashborion-tokens')
    return f"dashborion-{table_type}"


def generate_user_code() -> str:
    """Generate human-readable user code (e.g., ABCD-1234)"""
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ'  # No I, O to avoid confusion
    digits = '23456789'  # No 0, 1 to avoid confusion

    part1 = ''.join(secrets.choice(chars) for _ in range(4))
    part2 = ''.join(secrets.choice(digits) for _ in range(4))
    return f"{part1}-{part2}"


def generate_device_code() -> str:
    """Generate secure device code for polling"""
    return secrets.token_urlsafe(32)


def generate_access_token() -> str:
    """Generate secure access token"""
    return secrets.token_urlsafe(48)


def generate_refresh_token() -> str:
    """Generate secure refresh token"""
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    """Hash token for storage (we don't store raw tokens)"""
    return hashlib.sha256(token.encode()).hexdigest()


def create_device_code(client_id: str, base_url: str) -> DeviceCode:
    """
    Create a new device code for CLI authentication.

    Args:
        client_id: Identifier for the CLI client
        base_url: Base URL for verification (e.g., https://dashboard.example.com)

    Returns:
        DeviceCode with all necessary info for CLI
    """
    device_code = generate_device_code()
    user_code = generate_user_code()
    expires_at = int(time.time()) + DEVICE_CODE_TTL

    code = DeviceCode(
        device_code=device_code,
        user_code=user_code,
        verification_uri=f"{base_url}/auth/device",
        expires_at=expires_at,
        interval=POLLING_INTERVAL,
        client_id=client_id,
        status=DeviceCodeStatus.PENDING,
    )

    # Store in DynamoDB
    _store_device_code(code)

    return code


def _store_device_code(code: DeviceCode) -> None:
    """Store device code in DynamoDB"""
    client = _get_dynamodb()
    table_name = _get_table_name("device_codes")

    item = {
        'pk': {'S': f"DEVICE#{code.device_code}"},
        'sk': {'S': f"USER_CODE#{code.user_code}"},
        'device_code': {'S': code.device_code},
        'user_code': {'S': code.user_code},
        'verification_uri': {'S': code.verification_uri},
        'expires_at': {'N': str(code.expires_at)},
        'interval': {'N': str(code.interval)},
        'client_id': {'S': code.client_id},
        'status': {'S': code.status.value},
        'ttl': {'N': str(code.expires_at + 300)},  # TTL 5min after expiry
    }

    if code.user_email:
        item['user_email'] = {'S': code.user_email}
    if code.permissions:
        item['permissions'] = {'S': code.permissions}

    # Also create GSI entry for user_code lookup
    client.put_item(TableName=table_name, Item=item)

    # Create secondary item for user_code lookup
    user_code_item = {
        'pk': {'S': f"USER_CODE#{code.user_code}"},
        'sk': {'S': f"DEVICE#{code.device_code}"},
        'device_code': {'S': code.device_code},
        'ttl': {'N': str(code.expires_at + 300)},
    }
    client.put_item(TableName=table_name, Item=user_code_item)


def get_device_code_by_user_code(user_code: str) -> Optional[DeviceCode]:
    """Look up device code by user-entered code"""
    client = _get_dynamodb()
    table_name = _get_table_name("device_codes")

    # First, find the device_code from user_code
    response = client.query(
        TableName=table_name,
        KeyConditionExpression='pk = :pk',
        ExpressionAttributeValues={
            ':pk': {'S': f"USER_CODE#{user_code.upper()}"}
        }
    )

    items = response.get('Items', [])
    if not items:
        return None

    device_code = items[0].get('device_code', {}).get('S')
    if not device_code:
        return None

    # Now get the full device code record
    return get_device_code(device_code)


def get_device_code(device_code: str) -> Optional[DeviceCode]:
    """Get device code by device_code"""
    client = _get_dynamodb()
    table_name = _get_table_name("device_codes")

    response = client.query(
        TableName=table_name,
        KeyConditionExpression='pk = :pk',
        ExpressionAttributeValues={
            ':pk': {'S': f"DEVICE#{device_code}"}
        }
    )

    items = response.get('Items', [])
    if not items:
        return None

    item = items[0]

    # Check expiry
    expires_at = int(item.get('expires_at', {}).get('N', 0))
    if time.time() > expires_at:
        return DeviceCode(
            device_code=device_code,
            user_code=item.get('user_code', {}).get('S', ''),
            verification_uri=item.get('verification_uri', {}).get('S', ''),
            expires_at=expires_at,
            interval=int(item.get('interval', {}).get('N', POLLING_INTERVAL)),
            client_id=item.get('client_id', {}).get('S', ''),
            status=DeviceCodeStatus.EXPIRED,
        )

    return DeviceCode(
        device_code=device_code,
        user_code=item.get('user_code', {}).get('S', ''),
        verification_uri=item.get('verification_uri', {}).get('S', ''),
        expires_at=expires_at,
        interval=int(item.get('interval', {}).get('N', POLLING_INTERVAL)),
        client_id=item.get('client_id', {}).get('S', ''),
        status=DeviceCodeStatus(item.get('status', {}).get('S', 'pending')),
        user_email=item.get('user_email', {}).get('S'),
        permissions=item.get('permissions', {}).get('S'),
    )


def _grant_global_admin_permission(email: str) -> None:
    """Grant global admin permission to user (used for bootstrap)"""
    import os
    client = _get_dynamodb()
    table_name = os.environ.get('PERMISSIONS_TABLE_NAME', 'dashborion-permissions')

    client.put_item(
        TableName=table_name,
        Item={
            'pk': {'S': f'USER#{email}'},
            'sk': {'S': 'PERM#*#*'},  # project=*, environment=*
            'project': {'S': '*'},
            'environment': {'S': '*'},
            'role': {'S': 'admin'},
            'resources': {'L': [{'S': '*'}]},
            'grantedBy': {'S': 'sso-bootstrap'},
            'grantedAt': {'N': str(int(time.time()))},
        }
    )


def authorize_device_code(user_code: str, auth: AuthContext) -> bool:
    """
    Called when user completes SAML authentication for a device code.

    Args:
        user_code: The code user entered
        auth: Authentication context from SAML (contains SSO groups in auth.groups)

    Returns:
        True if successful, False if code not found/expired
    """
    from .user_management import get_user, create_user, get_user_effective_permissions, has_any_admin

    code = get_device_code_by_user_code(user_code)
    if not code or code.status != DeviceCodeStatus.PENDING:
        return False

    if time.time() > code.expires_at:
        return False

    email = auth.email.lower() if auth.email else ''
    if not email:
        return False

    # Get or create user in DynamoDB
    user = get_user(email)
    if not user:
        # First user becomes admin (bootstrap), others become viewer
        is_first_user = not has_any_admin()
        default_role = DashborionRole.ADMIN.value if is_first_user else DashborionRole.VIEWER.value

        result = create_user(
            email=email,
            display_name=email.split('@')[0],
            default_role=default_role,
            password=None,  # SSO users don't have local password
            actor_email='sso-bootstrap' if is_first_user else 'sso-auto',
        )
        if not result.get('success'):
            return False

        # For first user (bootstrap), grant global admin permission
        if is_first_user:
            _grant_global_admin_permission(email)

        # Re-fetch user to get User object
        user = get_user(email)

    if not user:
        return False

    if user.disabled:
        return False

    # Get effective permissions
    # - auth.groups contains SSO groups from SAML (Azure AD object IDs or group names)
    # - user.local_groups contains local group membership from DynamoDB
    sso_groups = auth.groups if auth.groups else []
    local_groups = user.local_groups if user.local_groups else []

    permissions = get_user_effective_permissions(
        email=email,
        local_groups=local_groups,
        sso_groups=sso_groups,
    )

    # Build permissions JSON
    permissions_json = json.dumps([
        {
            'project': p.project,
            'environment': p.environment,
            'role': p.role.value,
            'resources': p.resources,
            'source': p.source,
        }
        for p in permissions
    ])

    # Update the device code with user info
    client = _get_dynamodb()
    table_name = _get_table_name("device_codes")

    client.update_item(
        TableName=table_name,
        Key={
            'pk': {'S': f"DEVICE#{code.device_code}"},
            'sk': {'S': f"USER_CODE#{code.user_code}"},
        },
        UpdateExpression='SET #status = :status, user_email = :email, #perms = :perms',
        ExpressionAttributeNames={
            '#status': 'status',
            '#perms': 'permissions',  # 'permissions' is a DynamoDB reserved keyword
        },
        ExpressionAttributeValues={
            ':status': {'S': DeviceCodeStatus.AUTHORIZED.value},
            ':email': {'S': email},
            ':perms': {'S': permissions_json},
        }
    )

    return True


def exchange_device_code(device_code: str) -> Optional[AccessToken]:
    """
    Exchange device code for access token (CLI polling endpoint).

    Returns:
        AccessToken if authorized, None if pending/expired/denied

    Raises:
        DeviceCodePendingError: If still waiting for user
        DeviceCodeExpiredError: If code expired
        DeviceCodeDeniedError: If user denied
    """
    code = get_device_code(device_code)
    if not code:
        return None

    if code.status == DeviceCodeStatus.PENDING:
        raise DeviceCodePendingError("authorization_pending")

    if code.status == DeviceCodeStatus.EXPIRED or time.time() > code.expires_at:
        raise DeviceCodeExpiredError("expired_token")

    if code.status == DeviceCodeStatus.DENIED:
        raise DeviceCodeDeniedError("access_denied")

    if code.status == DeviceCodeStatus.AUTHORIZED:
        # Generate tokens
        access_token = generate_access_token()
        refresh_token = generate_refresh_token()
        expires_at = int(time.time()) + ACCESS_TOKEN_TTL

        token = AccessToken(
            token=access_token,
            expires_in=ACCESS_TOKEN_TTL,
            expires_at=expires_at,
            refresh_token=refresh_token,
            user_id=code.user_email or "",
            email=code.user_email or "",
            permissions=code.permissions or "[]",
        )

        # Store tokens
        _store_token(token, code.client_id)

        # Mark device code as used (delete it)
        _delete_device_code(code)

        return token

    return None


def _store_token(token: AccessToken, client_id: str) -> None:
    """Store access token in DynamoDB (hashed, with optional KMS encryption)"""
    client = _get_dynamodb()
    table_name = _get_table_name("tokens")

    token_hash = hash_token(token.token)
    refresh_hash = hash_token(token.refresh_token) if token.refresh_token else None

    # Sensitive data to potentially encrypt
    sensitive_data = {
        'email': token.email,
        'user_id': token.user_id,
        'permissions': token.permissions,
        'scope': token.scope,
    }

    if _is_kms_enabled():
        # Encrypt sensitive data with KMS
        encrypt_data, _, token_context, _ = _get_kms_crypto()
        encrypted = encrypt_data(sensitive_data, token_context(token_hash))
        item = {
            'pk': {'S': f"TOKEN#{token_hash}"},
            'sk': {'S': 'SESSION'},  # Don't leak email in sort key
            'token_hash': {'S': token_hash},
            'token_type': {'S': token.token_type},
            'expires_at': {'N': str(token.expires_at)},
            'encrypted_data': {'S': encrypted},
            'client_id': {'S': client_id},
            'ttl': {'N': str(token.expires_at + 86400)},
        }
    else:
        # Backward compatible: store in clear (for migration)
        item = {
            'pk': {'S': f"TOKEN#{token_hash}"},
            'sk': {'S': f"USER#{token.email}"},
            'token_hash': {'S': token_hash},
            'token_type': {'S': token.token_type},
            'expires_at': {'N': str(token.expires_at)},
            'user_id': {'S': token.user_id},
            'email': {'S': token.email},
            'permissions': {'S': token.permissions},
            'client_id': {'S': client_id},
            'scope': {'S': token.scope},
            'ttl': {'N': str(token.expires_at + 86400)},
        }

    if refresh_hash:
        item['refresh_hash'] = {'S': refresh_hash}
        # Store refresh token mapping
        if _is_kms_enabled():
            _, _, _, refresh_context = _get_kms_crypto()
            encrypt_data, _, _, _ = _get_kms_crypto()
            refresh_sensitive = {
                'email': token.email,
                'permissions': token.permissions,
                'token_hash': token_hash,
            }
            refresh_encrypted = encrypt_data(refresh_sensitive, refresh_context(refresh_hash))
            refresh_item = {
                'pk': {'S': f"REFRESH#{refresh_hash}"},
                'sk': {'S': 'SESSION'},
                'encrypted_data': {'S': refresh_encrypted},
                'client_id': {'S': client_id},
                'expires_at': {'N': str(int(time.time()) + REFRESH_TOKEN_TTL)},
                'ttl': {'N': str(int(time.time()) + REFRESH_TOKEN_TTL + 86400)},
            }
        else:
            refresh_item = {
                'pk': {'S': f"REFRESH#{refresh_hash}"},
                'sk': {'S': f"TOKEN#{token_hash}"},
                'token_hash': {'S': token_hash},
                'email': {'S': token.email},
                'permissions': {'S': token.permissions},
                'client_id': {'S': client_id},
                'expires_at': {'N': str(int(time.time()) + REFRESH_TOKEN_TTL)},
                'ttl': {'N': str(int(time.time()) + REFRESH_TOKEN_TTL + 86400)},
            }
        client.put_item(TableName=table_name, Item=refresh_item)

    client.put_item(TableName=table_name, Item=item)


def validate_token(token: str) -> Optional[AuthContext]:
    """
    Validate an access token and return auth context.

    Supports both KMS-encrypted and legacy unencrypted tokens.

    Args:
        token: Bearer token from CLI

    Returns:
        AuthContext if valid, None if invalid/expired
    """
    client = _get_dynamodb()
    table_name = _get_table_name("tokens")

    token_hash = hash_token(token)

    response = client.query(
        TableName=table_name,
        KeyConditionExpression='pk = :pk',
        ExpressionAttributeValues={
            ':pk': {'S': f"TOKEN#{token_hash}"}
        }
    )

    items = response.get('Items', [])
    if not items:
        return None

    item = items[0]
    expires_at = int(item.get('expires_at', {}).get('N', 0))

    if time.time() > expires_at:
        return None

    # Check if data is encrypted
    encrypted_data = item.get('encrypted_data', {}).get('S')
    if encrypted_data:
        # Decrypt with KMS
        try:
            _, decrypt_data, token_context, _ = _get_kms_crypto()
            decrypted = decrypt_data(encrypted_data, token_context(token_hash))
            email = decrypted.get('email', '')
            user_id = decrypted.get('user_id', email)
            permissions_json = decrypted.get('permissions', '[]')
        except Exception as e:
            print(f"[Token] Decryption failed: {e}")
            return None
    else:
        # Legacy unencrypted token
        email = item.get('email', {}).get('S', '')
        user_id = item.get('user_id', {}).get('S', email)
        permissions_json = item.get('permissions', {}).get('S', '[]')

    # Parse permissions
    permissions_data = json.loads(permissions_json) if isinstance(permissions_json, str) else permissions_json

    permissions = [
        Permission(
            project=p.get('project', '*'),
            environment=p.get('environment', '*'),
            role=DashborionRole(p.get('role', 'viewer')),
            resources=p.get('resources', ['*']),
        )
        for p in permissions_data
    ]

    return AuthContext(
        user_id=user_id,
        email=email,
        permissions=permissions,
        session_id=f"cli-{token_hash[:8]}",
    )


def refresh_access_token(refresh_token: str) -> Optional[AccessToken]:
    """
    Exchange refresh token for new access token.

    Supports both KMS-encrypted and legacy unencrypted refresh tokens.

    Args:
        refresh_token: Refresh token from CLI

    Returns:
        New AccessToken if valid, None if invalid/expired
    """
    client = _get_dynamodb()
    table_name = _get_table_name("tokens")

    refresh_hash = hash_token(refresh_token)

    response = client.query(
        TableName=table_name,
        KeyConditionExpression='pk = :pk',
        ExpressionAttributeValues={
            ':pk': {'S': f"REFRESH#{refresh_hash}"}
        }
    )

    items = response.get('Items', [])
    if not items:
        return None

    item = items[0]
    expires_at = int(item.get('expires_at', {}).get('N', 0))

    if time.time() > expires_at:
        return None

    # Check if data is encrypted
    encrypted_data = item.get('encrypted_data', {}).get('S')
    if encrypted_data:
        try:
            _, decrypt_data, _, refresh_context = _get_kms_crypto()
            decrypted = decrypt_data(encrypted_data, refresh_context(refresh_hash))
            email = decrypted.get('email', '')
            permissions = decrypted.get('permissions', '[]')
            old_token_hash = decrypted.get('token_hash')
        except Exception as e:
            print(f"[Refresh] Decryption failed: {e}")
            return None
    else:
        # Legacy unencrypted
        email = item.get('email', {}).get('S', '')
        permissions = item.get('permissions', {}).get('S', '[]')
        old_token_hash = item.get('token_hash', {}).get('S')

    client_id = item.get('client_id', {}).get('S', 'cli')

    # Generate new access token (keep same refresh token)
    new_access_token = generate_access_token()
    new_expires_at = int(time.time()) + ACCESS_TOKEN_TTL

    token = AccessToken(
        token=new_access_token,
        expires_in=ACCESS_TOKEN_TTL,
        expires_at=new_expires_at,
        refresh_token=refresh_token,  # Return same refresh token
        user_id=email,
        email=email,
        permissions=permissions,
    )

    # Store new token
    _store_token(token, client_id)

    # Delete old access token
    if old_token_hash:
        # Try both possible sk formats (encrypted vs legacy)
        for sk in ['SESSION', f"USER#{email}"]:
            try:
                client.delete_item(
                    TableName=table_name,
                    Key={
                        'pk': {'S': f"TOKEN#{old_token_hash}"},
                        'sk': {'S': sk},
                    }
                )
                break  # Success, no need to try other sk
            except ClientError:
                pass  # Try next sk format

    return token


def revoke_token(token: str) -> bool:
    """Revoke an access token (logout)"""
    client = _get_dynamodb()
    table_name = _get_table_name("tokens")

    # First, validate and get token info
    auth = validate_token(token)
    if not auth:
        return False

    token_hash = hash_token(token)

    # Try both possible sk formats (encrypted vs legacy)
    for sk in ['SESSION', f"USER#{auth.email}"]:
        try:
            client.delete_item(
                TableName=table_name,
                Key={
                    'pk': {'S': f"TOKEN#{token_hash}"},
                    'sk': {'S': sk},
                }
            )
            return True
        except ClientError:
            pass  # Try next sk format

    return False


def _delete_device_code(code: DeviceCode) -> None:
    """Delete device code after use"""
    client = _get_dynamodb()
    table_name = _get_table_name("device_codes")

    try:
        # Delete main record
        client.delete_item(
            TableName=table_name,
            Key={
                'pk': {'S': f"DEVICE#{code.device_code}"},
                'sk': {'S': f"USER_CODE#{code.user_code}"},
            }
        )
        # Delete user_code lookup
        client.delete_item(
            TableName=table_name,
            Key={
                'pk': {'S': f"USER_CODE#{code.user_code}"},
                'sk': {'S': f"DEVICE#{code.device_code}"},
            }
        )
    except ClientError:
        pass  # Ignore errors on cleanup


# Custom exceptions for device flow
class DeviceCodeError(Exception):
    """Base exception for device code errors"""
    def __init__(self, error: str, description: str = ""):
        self.error = error
        self.description = description
        super().__init__(f"{error}: {description}")


class DeviceCodePendingError(DeviceCodeError):
    """Device code is still pending user authorization"""
    def __init__(self, error: str = "authorization_pending"):
        super().__init__(error, "The user has not yet completed authorization")


class DeviceCodeExpiredError(DeviceCodeError):
    """Device code has expired"""
    def __init__(self, error: str = "expired_token"):
        super().__init__(error, "The device code has expired")


class DeviceCodeDeniedError(DeviceCodeError):
    """User denied the authorization request"""
    def __init__(self, error: str = "access_denied"):
        super().__init__(error, "The user denied the authorization request")
