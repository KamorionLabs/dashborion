"""
Permission checking logic for Dashborion authorization
"""

import os
import json
import base64
from typing import List, Dict, Optional, Any
from functools import lru_cache
import boto3
from botocore.exceptions import ClientError

from .models import AuthContext, Permission, DashborionRole

# Role to actions mapping
ROLE_PERMISSIONS: Dict[DashborionRole, List[str]] = {
    DashborionRole.VIEWER: ["read"],
    DashborionRole.OPERATOR: ["read", "deploy", "scale", "restart", "invalidate"],
    DashborionRole.ADMIN: [
        "read", "deploy", "scale", "restart", "invalidate",
        "rds-control", "manage-permissions", "view-audit"
    ],
}


def role_can_perform(role: DashborionRole, action: str) -> bool:
    """Check if a role can perform an action"""
    return action in ROLE_PERMISSIONS.get(role, [])


def parse_permissions_from_header(header_value: str) -> List[Permission]:
    """Parse permissions from X-Auth-Permissions header (base64 JSON)"""
    try:
        decoded = base64.b64decode(header_value).decode('utf-8')
        perms_data = json.loads(decoded)

        permissions = []
        for perm in perms_data:
            permissions.append(Permission(
                project=perm.get('project', '*'),
                environment=perm.get('environment', '*'),
                role=DashborionRole(perm.get('role', 'viewer')),
                resources=perm.get('resources', ['*']),
                require_mfa=perm.get('requireMfa', False),
                expires_at=perm.get('expiresAt'),
            ))
        return permissions
    except Exception as e:
        print(f"Failed to parse permissions header: {e}")
        return []


def check_permission(
    auth: AuthContext,
    action: str,
    project: str,
    environment: str = "*",
    resource: str = "*"
) -> bool:
    """
    Check if user has permission to perform an action.

    Args:
        auth: Authentication context
        action: Action to perform (read, deploy, scale, etc.)
        project: Project name
        environment: Environment name (* for any)
        resource: Resource name (* for any)

    Returns:
        True if user has permission, False otherwise
    """
    if not auth.is_authenticated:
        return False

    for perm in auth.permissions:
        # Check project match
        if perm.project not in [project, "*"]:
            continue

        # Check environment match
        if perm.environment not in [environment, "*"]:
            continue

        # Check resource match
        if resource != "*" and "*" not in perm.resources and resource not in perm.resources:
            continue

        # Check if role can perform the action
        if role_can_perform(perm.role, action):
            # Check MFA requirement
            if perm.require_mfa and not auth.mfa_verified:
                continue

            # Check expiration
            if perm.expires_at:
                import time
                if time.time() > perm.expires_at:
                    continue

            return True

    return False


# DynamoDB client for permission lookups (lazy initialized)
_dynamodb_client = None


def _get_dynamodb_client():
    """Get or create DynamoDB client"""
    global _dynamodb_client
    if _dynamodb_client is None:
        _dynamodb_client = boto3.client('dynamodb')
    return _dynamodb_client


@lru_cache(maxsize=100)
def get_user_permissions_from_db(
    email: str,
    table_name: str = None
) -> List[Permission]:
    """
    Get user permissions from DynamoDB.

    Note: This is cached for performance. Cache is cleared on Lambda cold start.
    """
    table_name = table_name or os.environ.get('PERMISSIONS_TABLE_NAME', 'dashborion-permissions')

    try:
        client = _get_dynamodb_client()

        response = client.query(
            TableName=table_name,
            KeyConditionExpression='pk = :pk',
            ExpressionAttributeValues={
                ':pk': {'S': f'USER#{email}'}
            }
        )

        permissions = []
        for item in response.get('Items', []):
            # Parse DynamoDB item
            perm = Permission(
                project=item.get('project', {}).get('S', '*'),
                environment=item.get('environment', {}).get('S', '*'),
                role=DashborionRole(item.get('role', {}).get('S', 'viewer')),
                resources=item.get('resources', {}).get('SS', ['*']),
                require_mfa=item.get('requireMfa', {}).get('BOOL', False),
                expires_at=int(item['expiresAt']['N']) if 'expiresAt' in item else None,
            )
            permissions.append(perm)

        return permissions

    except ClientError as e:
        print(f"DynamoDB error getting permissions: {e}")
        return []


def get_user_permissions(auth: AuthContext, use_db: bool = False) -> List[Permission]:
    """
    Get user permissions from auth context or database.

    Args:
        auth: Authentication context (may contain permissions from headers)
        use_db: If True, also check DynamoDB for additional permissions

    Returns:
        List of permissions
    """
    permissions = list(auth.permissions)

    if use_db:
        db_permissions = get_user_permissions_from_db(auth.email)
        # Merge, preferring DB permissions (they may have been updated)
        existing_keys = {(p.project, p.environment) for p in permissions}
        for perm in db_permissions:
            if (perm.project, perm.environment) not in existing_keys:
                permissions.append(perm)

    return permissions


def clear_permission_cache():
    """Clear the permission cache (e.g., after permission update)"""
    get_user_permissions_from_db.cache_clear()


def log_audit_event(
    auth: AuthContext,
    action: str,
    project: str,
    environment: str,
    resource: str,
    result: str,
    details: Optional[Dict[str, Any]] = None,
    table_name: str = None
):
    """
    Log an audit event to DynamoDB.

    Args:
        auth: Authentication context
        action: Action performed
        project: Project name
        environment: Environment name
        resource: Resource name
        result: Result (success, failure, denied)
        details: Additional details
        table_name: Audit table name
    """
    import time
    import uuid

    table_name = table_name or os.environ.get('AUDIT_TABLE_NAME', 'dashborion-audit')
    timestamp = int(time.time())
    ttl = timestamp + (90 * 24 * 60 * 60)  # 90 days retention

    try:
        client = _get_dynamodb_client()

        item = {
            'pk': {'S': f'USER#{auth.email}'},
            'sk': {'S': f'TS#{timestamp}#{action}#{uuid.uuid4().hex[:8]}'},
            'gsi1pk': {'S': f'PROJECT#{project}'},
            'gsi1sk': {'S': f'ENV#{environment}#{timestamp}'},
            'userId': {'S': auth.user_id},
            'email': {'S': auth.email},
            'timestamp': {'N': str(timestamp)},
            'action': {'S': action},
            'project': {'S': project},
            'environment': {'S': environment},
            'resource': {'S': resource},
            'result': {'S': result},
            'sessionId': {'S': auth.session_id},
            'mfaVerified': {'BOOL': auth.mfa_verified},
            'ttl': {'N': str(ttl)},
        }

        if details:
            item['details'] = {'S': json.dumps(details)}

        client.put_item(
            TableName=table_name,
            Item=item
        )

    except ClientError as e:
        print(f"Failed to log audit event: {e}")
