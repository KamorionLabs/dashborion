"""
KMS-based encryption for sensitive authentication data.

Provides envelope encryption using AWS KMS for:
- Session data (email, permissions, groups)
- Token metadata stored in DynamoDB

Uses encryption context for additional security binding.
"""

import os
import json
import base64
from typing import Dict, Any, Optional
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError


# Lazy-init KMS client
_kms_client = None


def _get_kms_client():
    """Get or create KMS client."""
    global _kms_client
    if _kms_client is None:
        _kms_client = boto3.client('kms')
    return _kms_client


@lru_cache(maxsize=1)
def _get_key_id() -> str:
    """Get KMS key ID/ARN from environment."""
    key_id = os.environ.get('KMS_KEY_ARN') or os.environ.get('KMS_KEY_ID')
    if not key_id:
        raise ValueError("KMS_KEY_ARN or KMS_KEY_ID environment variable required")
    return key_id


def encrypt_data(
    data: Dict[str, Any],
    context: Optional[Dict[str, str]] = None
) -> str:
    """
    Encrypt data with KMS.

    Args:
        data: Dictionary to encrypt
        context: Encryption context for additional security binding

    Returns:
        Base64-encoded ciphertext
    """
    kms = _get_kms_client()
    key_id = _get_key_id()

    plaintext = json.dumps(data, separators=(',', ':')).encode('utf-8')

    kwargs = {
        'KeyId': key_id,
        'Plaintext': plaintext,
    }
    if context:
        kwargs['EncryptionContext'] = context

    try:
        response = kms.encrypt(**kwargs)
        return base64.b64encode(response['CiphertextBlob']).decode('utf-8')
    except ClientError as e:
        raise RuntimeError(f"KMS encryption failed: {e}")


def decrypt_data(
    encrypted: str,
    context: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Decrypt data with KMS.

    Args:
        encrypted: Base64-encoded ciphertext
        context: Encryption context (must match what was used for encryption)

    Returns:
        Decrypted dictionary

    Raises:
        RuntimeError: If decryption fails (invalid context, tampered data, etc.)
    """
    kms = _get_kms_client()

    ciphertext = base64.b64decode(encrypted)

    kwargs = {
        'CiphertextBlob': ciphertext,
    }
    if context:
        kwargs['EncryptionContext'] = context

    try:
        response = kms.decrypt(**kwargs)
        plaintext = response['Plaintext'].decode('utf-8')
        return json.loads(plaintext)
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'InvalidCiphertextException':
            raise RuntimeError("Decryption failed: invalid ciphertext or wrong context")
        raise RuntimeError(f"KMS decryption failed: {e}")
    except json.JSONDecodeError:
        raise RuntimeError("Decryption failed: invalid JSON payload")


# Encryption contexts for different use cases
def token_context(token_hash: str) -> Dict[str, str]:
    """Encryption context for access tokens."""
    return {
        "service": "dashborion",
        "purpose": "access_token",
        "token_hash": token_hash[:16],  # First 16 chars for binding
    }


def session_context(session_id: str) -> Dict[str, str]:
    """Encryption context for web sessions."""
    return {
        "service": "dashborion",
        "purpose": "web_session",
        "session_id": session_id[:16],
    }


def refresh_context(token_hash: str) -> Dict[str, str]:
    """Encryption context for refresh tokens."""
    return {
        "service": "dashborion",
        "purpose": "refresh_token",
        "token_hash": token_hash[:16],
    }
