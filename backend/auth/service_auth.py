"""
Machine-to-Machine (M2M) authentication for IAM service roles.

Allows AWS services and applications to authenticate via their IAM role.
Service permissions are stored in DynamoDB.

DynamoDB Schema for services:
  pk: SERVICE#<role_arn>
  sk: PERMISSIONS
  service_name: string
  permissions: list (same format as user permissions)
  enabled: bool
  created_at: number
  created_by: string
"""

import os
import re
import time
import json
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from .models import AuthContext, Permission, DashborionRole


# Lazy init
_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.client('dynamodb')
    return _dynamodb


@dataclass
class ServiceIdentity:
    """Parsed IAM role identity."""
    arn: str
    account_id: str
    role_name: str
    session_name: Optional[str] = None


# Pattern for assumed role ARNs
# arn:aws:sts::123456789012:assumed-role/RoleName/SessionName
ASSUMED_ROLE_PATTERN = re.compile(
    r'^arn:aws:sts::(\d{12}):assumed-role/([^/]+)(?:/(.+))?$'
)

# Pattern for IAM role ARNs
# arn:aws:iam::123456789012:role/RoleName
IAM_ROLE_PATTERN = re.compile(
    r'^arn:aws:iam::(\d{12}):role/(.+)$'
)


def get_allowed_account_ids() -> Set[str]:
    """Get set of allowed AWS account IDs from environment."""
    account_ids_str = os.environ.get('ALLOWED_AWS_ACCOUNT_IDS', '')
    if not account_ids_str:
        return set()

    return {
        aid.strip()
        for aid in account_ids_str.split(',')
        if aid.strip() and aid.strip().isdigit() and len(aid.strip()) == 12
    }


def parse_service_identity(user_arn: str) -> Optional[ServiceIdentity]:
    """
    Parse IAM role ARN for service authentication.

    Rejects Identity Center roles (handled separately).

    Args:
        user_arn: The userArn from API Gateway requestContext

    Returns:
        ServiceIdentity if valid service role, None otherwise
    """
    if not user_arn:
        return None

    # Reject Identity Center roles - those go through user auth
    if 'AWSReservedSSO_' in user_arn:
        return None

    # Try assumed-role pattern first
    match = ASSUMED_ROLE_PATTERN.match(user_arn)
    if match:
        account_id = match.group(1)
        role_name = match.group(2)
        session_name = match.group(3)

        # Validate account is in allowed list
        allowed_accounts = get_allowed_account_ids()
        if allowed_accounts and account_id not in allowed_accounts:
            print(f"[ServiceAuth] Account {account_id} not in allowed list")
            return None

        return ServiceIdentity(
            arn=user_arn,
            account_id=account_id,
            role_name=role_name,
            session_name=session_name,
        )

    # Try IAM role pattern
    match = IAM_ROLE_PATTERN.match(user_arn)
    if match:
        account_id = match.group(1)
        role_name = match.group(2)

        allowed_accounts = get_allowed_account_ids()
        if allowed_accounts and account_id not in allowed_accounts:
            print(f"[ServiceAuth] Account {account_id} not in allowed list")
            return None

        return ServiceIdentity(
            arn=user_arn,
            account_id=account_id,
            role_name=role_name,
        )

    return None


def get_service_permissions(role_arn: str) -> Optional[Dict[str, Any]]:
    """
    Look up service permissions from DynamoDB.

    Args:
        role_arn: Full ARN of the IAM role

    Returns:
        Service record with permissions, or None if not found/disabled
    """
    dynamodb = _get_dynamodb()
    table_name = os.environ.get('PERMISSIONS_TABLE_NAME', 'dashborion-permissions')

    # Normalize ARN: if it's an assumed-role, convert to IAM role ARN
    # arn:aws:sts::123:assumed-role/RoleName/Session -> arn:aws:iam::123:role/RoleName
    normalized_arn = role_arn
    assumed_match = ASSUMED_ROLE_PATTERN.match(role_arn)
    if assumed_match:
        account_id = assumed_match.group(1)
        role_name = assumed_match.group(2)
        normalized_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'SERVICE#{normalized_arn}'},
                'sk': {'S': 'PERMISSIONS'},
            }
        )
    except ClientError as e:
        print(f"[ServiceAuth] DynamoDB lookup failed: {e}")
        return None

    item = response.get('Item')
    if not item:
        print(f"[ServiceAuth] Service {normalized_arn} not found")
        return None

    # Check if enabled
    enabled = item.get('enabled', {}).get('BOOL', True)
    if not enabled:
        print(f"[ServiceAuth] Service {normalized_arn} is disabled")
        return None

    # Parse permissions
    permissions_json = item.get('permissions', {}).get('S', '[]')
    try:
        permissions = json.loads(permissions_json)
    except json.JSONDecodeError:
        permissions = []

    return {
        'service_name': item.get('service_name', {}).get('S', role_arn),
        'permissions': permissions,
        'role_arn': normalized_arn,
    }


def validate_service_auth(
    user_arn: str,
    account_id: str,
) -> Optional[AuthContext]:
    """
    Validate service (M2M) authentication.

    Args:
        user_arn: event.requestContext.identity.userArn
        account_id: event.requestContext.identity.accountId

    Returns:
        AuthContext if valid service, None otherwise
    """
    identity = parse_service_identity(user_arn)
    if not identity:
        return None

    # Verify account ID matches
    if identity.account_id != account_id:
        print(f"[ServiceAuth] Account mismatch: {identity.account_id} vs {account_id}")
        return None

    # Look up service permissions
    service = get_service_permissions(identity.arn)
    if not service:
        return None

    # Build permissions list
    permissions = [
        Permission(
            project=p.get('project', '*'),
            environment=p.get('environment', '*'),
            role=DashborionRole(p.get('role', 'viewer')),
            resources=p.get('resources', ['*']),
        )
        for p in service.get('permissions', [])
    ]

    return AuthContext(
        user_id=service['role_arn'],
        email=f"service:{service['service_name']}",  # Use service: prefix for M2M
        permissions=permissions,
        groups=[],
        session_id=f"service-{identity.role_name}",
    )


def register_service(
    role_arn: str,
    service_name: str,
    permissions: List[Dict[str, Any]],
    created_by: str,
) -> bool:
    """
    Register a service for M2M authentication.

    Args:
        role_arn: Full IAM role ARN
        service_name: Human-readable service name
        permissions: List of permission dicts
        created_by: Email of admin creating this service

    Returns:
        True if successful
    """
    dynamodb = _get_dynamodb()
    table_name = os.environ.get('PERMISSIONS_TABLE_NAME', 'dashborion-permissions')

    # Normalize to IAM role ARN if needed
    normalized_arn = role_arn
    assumed_match = ASSUMED_ROLE_PATTERN.match(role_arn)
    if assumed_match:
        account_id = assumed_match.group(1)
        role_name = assumed_match.group(2)
        normalized_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    try:
        dynamodb.put_item(
            TableName=table_name,
            Item={
                'pk': {'S': f'SERVICE#{normalized_arn}'},
                'sk': {'S': 'PERMISSIONS'},
                'service_name': {'S': service_name},
                'permissions': {'S': json.dumps(permissions)},
                'enabled': {'BOOL': True},
                'created_at': {'N': str(int(time.time()))},
                'created_by': {'S': created_by},
            }
        )
        return True
    except ClientError as e:
        print(f"[ServiceAuth] Failed to register service: {e}")
        return False
