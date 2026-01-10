"""
Cookie-based session authentication.

Validates session cookies set by the SAML handler.
Session data is encrypted with KMS and stored in DynamoDB.
"""

import os
import time
import json
import hashlib
from typing import Optional, Dict, Any

import boto3
from botocore.exceptions import ClientError

from .models import AuthContext, Permission, DashborionRole
from .user_management import get_user, get_user_effective_permissions


# Lazy init clients
_dynamodb = None
_kms = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.client('dynamodb')
    return _dynamodb


def _get_kms():
    global _kms
    if _kms is None:
        _kms = boto3.client('kms')
    return _kms


COOKIE_NAME = '__dashborion_session'


def hash_session_id(session_id: str) -> str:
    """Hash session ID for storage lookup."""
    return hashlib.sha256(session_id.encode()).hexdigest()


def get_session_from_cookie(cookie_header: str) -> Optional[str]:
    """Extract session ID from Cookie header."""
    if not cookie_header:
        return None

    for cookie in cookie_header.split(';'):
        cookie = cookie.strip()
        if cookie.startswith(f'{COOKIE_NAME}='):
            return cookie[len(COOKIE_NAME) + 1:]

    return None


def decrypt_session_data(
    encrypted_data: str,
    session_hash: str,
) -> Optional[Dict[str, Any]]:
    """Decrypt session data with KMS."""
    kms = _get_kms()

    try:
        response = kms.decrypt(
            CiphertextBlob=bytes.fromhex(encrypted_data) if len(encrypted_data) % 2 == 0 and all(c in '0123456789abcdef' for c in encrypted_data.lower()) else __import__('base64').b64decode(encrypted_data),
            EncryptionContext={
                'service': 'dashborion',
                'purpose': 'web_session',
                'session_hash': session_hash[:16],
            }
        )
        return json.loads(response['Plaintext'].decode('utf-8'))
    except ClientError as e:
        print(f"[Session] KMS decryption failed: {e}")
        return None
    except Exception as e:
        print(f"[Session] Decryption error: {e}")
        return None


def validate_session_cookie(cookie_header: str) -> Optional[AuthContext]:
    """
    Validate session cookie and return auth context.

    Args:
        cookie_header: The Cookie header from the request

    Returns:
        AuthContext if valid, None otherwise
    """
    session_id = get_session_from_cookie(cookie_header)
    if not session_id:
        return None

    session_hash = hash_session_id(session_id)

    # Look up session in DynamoDB
    dynamodb = _get_dynamodb()
    table_name = os.environ.get('TOKENS_TABLE_NAME', 'dashborion-tokens')

    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'SESSION#{session_hash}'},
                'sk': {'S': 'META'},
            }
        )
    except ClientError as e:
        print(f"[Session] DynamoDB lookup failed: {e}")
        return None

    item = response.get('Item')
    if not item:
        print("[Session] Session not found")
        return None

    # Check expiry
    expires_at = int(item.get('expires_at', {}).get('N', 0))
    if time.time() > expires_at:
        print("[Session] Session expired")
        return None

    # Decrypt session data
    encrypted_data = item.get('encrypted_data', {}).get('S')
    if not encrypted_data:
        print("[Session] No encrypted data")
        return None

    session_data = decrypt_session_data(encrypted_data, session_hash)
    if not session_data:
        return None

    email = session_data.get('email', '').lower()
    if not email:
        return None

    # Get user from DynamoDB to check status
    user = get_user(email)
    if user and user.disabled:
        print(f"[Session] User {email} is disabled")
        return None

    # Get effective permissions
    sso_groups = session_data.get('groups', [])
    local_groups = user.local_groups if user else []

    permissions = get_user_effective_permissions(
        email=email,
        local_groups=local_groups,
        sso_groups=sso_groups,
    )

    return AuthContext(
        user_id=session_data.get('userId', email),
        email=email,
        permissions=permissions,
        groups=sso_groups,
        session_id=session_data.get('sessionId', f'session-{session_hash[:8]}'),
        mfa_verified=session_data.get('mfaVerified', False),
    )
