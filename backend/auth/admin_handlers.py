"""
Admin API Handlers for User, Group, and Permission Management

Endpoints for:
- User management (CRUD)
- Group management (CRUD, members)
- Permission management (grant, revoke, list)
- Audit logs
- System initialization
"""

import os
import json
import time
from typing import Dict, Any, Optional
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from .user_management import (
    create_user, get_user, list_users, update_user, delete_user,
    create_group, get_group, list_groups, update_group, delete_group,
    add_user_to_group, remove_user_from_group, get_group_members,
    grant_group_permission, revoke_group_permission, get_group_permissions,
    get_user_effective_permissions, init_admin,
)

PERMISSIONS_TABLE = os.environ.get('PERMISSIONS_TABLE_NAME', 'dashborion-permissions')
AUDIT_TABLE = os.environ.get('AUDIT_TABLE_NAME', 'dashborion-audit')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'dashborion')


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _get_dynamodb():
    """Get DynamoDB resource."""
    return boto3.resource('dynamodb')


def _audit_log(actor_email: str, action: str, target: Dict, result: str, details: Dict = None):
    """Record audit log entry."""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(AUDIT_TABLE)

        timestamp = int(time.time())

        table.put_item(Item={
            'pk': f'USER#{actor_email}',
            'sk': f'TS#{timestamp}#{action}',
            'gsi1pk': f'ACTION#{action}',
            'gsi1sk': f'TS#{timestamp}',
            'timestamp': timestamp,
            'action': action,
            'actor': actor_email,
            'target': target,
            'result': result,
            'details': details or {},
            'ttl': timestamp + (90 * 24 * 60 * 60),  # 90 days retention
        })
    except Exception as e:
        print(f"Audit log error: {e}")


def list_permissions(query_params: Dict = None, actor_email: str = None) -> Dict:
    """
    List all permissions.

    Query params:
    - project: Filter by project
    - user: Filter by user email
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(PERMISSIONS_TABLE)

        project_filter = query_params.get('project') if query_params else None
        user_filter = query_params.get('user') if query_params else None

        if user_filter:
            # Query by user
            response = table.query(
                KeyConditionExpression='pk = :pk',
                ExpressionAttributeValues={':pk': f'USER#{user_filter}'}
            )
        elif project_filter:
            # Query by project using GSI
            response = table.query(
                IndexName='project-env-index',
                KeyConditionExpression='gsi1pk = :pk',
                ExpressionAttributeValues={':pk': f'PROJECT#{project_filter}'}
            )
        else:
            # Scan all (use with caution)
            response = table.scan(
                FilterExpression='begins_with(pk, :prefix)',
                ExpressionAttributeValues={':prefix': 'USER#'}
            )

        items = response.get('Items', [])

        # Transform items to cleaner format
        permissions = []
        for item in items:
            permissions.append({
                'email': item.get('pk', '').replace('USER#', ''),
                'project': item.get('project', '*'),
                'environment': item.get('environment', '*'),
                'role': item.get('role', 'viewer'),
                'resources': item.get('resources', ['*']),
                'grantedBy': item.get('grantedBy'),
                'grantedAt': item.get('grantedAt'),
                'expiresAt': item.get('expiresAt'),
                'conditions': item.get('conditions', {}),
            })

        return {
            'success': True,
            'permissions': permissions,
            'count': len(permissions)
        }

    except ClientError as e:
        return {'error': str(e), 'success': False}


def get_user_permissions_legacy(email: str) -> Dict:
    """Get all permissions for a specific user (legacy format)."""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(PERMISSIONS_TABLE)

        response = table.query(
            KeyConditionExpression='pk = :pk',
            ExpressionAttributeValues={':pk': f'USER#{email}'}
        )

        items = response.get('Items', [])

        permissions = []
        for item in items:
            permissions.append({
                'project': item.get('project', '*'),
                'environment': item.get('environment', '*'),
                'role': item.get('role', 'viewer'),
                'resources': item.get('resources', ['*']),
                'grantedBy': item.get('grantedBy'),
                'grantedAt': item.get('grantedAt'),
                'expiresAt': item.get('expiresAt'),
                'conditions': item.get('conditions', {}),
            })

        return {
            'success': True,
            'email': email,
            'permissions': permissions
        }

    except ClientError as e:
        return {'error': str(e), 'success': False}


def grant_permission(data: Dict, actor_email: str) -> Dict:
    """
    Grant permission to a user.

    Required fields:
    - email: User email
    - project: Project name or '*' for all
    - role: viewer, operator, or admin

    Optional fields:
    - environment: Environment name or '*' for all (default: '*')
    - resources: List of resource names or ['*'] for all (default: ['*'])
    - expiresAt: Unix timestamp for expiration (default: null = no expiry)
    - conditions: Dict with requireMfa, allowedIpRanges, etc.
    """
    email = data.get('email')
    project = data.get('project')
    role = data.get('role')

    if not email or not project or not role:
        return {'error': 'Missing required fields: email, project, role', 'success': False}

    if role not in ['viewer', 'operator', 'admin']:
        return {'error': f'Invalid role: {role}. Must be viewer, operator, or admin', 'success': False}

    environment = data.get('environment', '*')
    resources = data.get('resources', ['*'])
    expires_at = data.get('expiresAt')
    conditions = data.get('conditions', {})

    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(PERMISSIONS_TABLE)

        timestamp = int(time.time())

        item = {
            'pk': f'USER#{email}',
            'sk': f'PERM#{project}#{environment}',
            'gsi1pk': f'PROJECT#{project}',
            'gsi1sk': f'ENV#{environment}#{email}',
            'project': project,
            'environment': environment,
            'role': role,
            'resources': resources,
            'grantedBy': actor_email,
            'grantedAt': timestamp,
            'conditions': conditions,
        }

        if expires_at:
            item['expiresAt'] = expires_at
            item['ttl'] = expires_at

        table.put_item(Item=item)

        # Audit log
        _audit_log(
            actor_email=actor_email,
            action='grant_permission',
            target={'email': email, 'project': project, 'environment': environment},
            result='success',
            details={'role': role, 'resources': resources}
        )

        return {
            'success': True,
            'message': f'Permission granted: {email} is now {role} for {project}/{environment}',
            'permission': {
                'email': email,
                'project': project,
                'environment': environment,
                'role': role,
                'resources': resources,
                'grantedBy': actor_email,
                'grantedAt': timestamp,
            }
        }

    except ClientError as e:
        _audit_log(
            actor_email=actor_email,
            action='grant_permission',
            target={'email': email, 'project': project},
            result='error',
            details={'error': str(e)}
        )
        return {'error': str(e), 'success': False}


def revoke_permission(data: Dict, actor_email: str) -> Dict:
    """
    Revoke permission from a user.

    Required fields:
    - email: User email
    - project: Project name
    - environment: Environment name (default: '*')
    """
    email = data.get('email')
    project = data.get('project')
    environment = data.get('environment', '*')

    if not email or not project:
        return {'error': 'Missing required fields: email, project', 'success': False}

    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(PERMISSIONS_TABLE)

        # Delete the permission
        table.delete_item(
            Key={
                'pk': f'USER#{email}',
                'sk': f'PERM#{project}#{environment}'
            }
        )

        # Audit log
        _audit_log(
            actor_email=actor_email,
            action='revoke_permission',
            target={'email': email, 'project': project, 'environment': environment},
            result='success'
        )

        return {
            'success': True,
            'message': f'Permission revoked: {email} no longer has access to {project}/{environment}'
        }

    except ClientError as e:
        _audit_log(
            actor_email=actor_email,
            action='revoke_permission',
            target={'email': email, 'project': project},
            result='error',
            details={'error': str(e)}
        )
        return {'error': str(e), 'success': False}


def list_roles() -> Dict:
    """List available roles and their permissions."""
    return {
        'success': True,
        'roles': {
            'viewer': {
                'description': 'Read-only access',
                'permissions': ['read'],
                'actions': [
                    'View services, logs, metrics',
                    'View infrastructure',
                    'View pipelines and images',
                    'View events'
                ]
            },
            'operator': {
                'description': 'Can perform deployments and operational actions',
                'permissions': ['read', 'deploy'],
                'actions': [
                    'All viewer actions',
                    'Trigger builds',
                    'Deploy services',
                    'Restart services',
                    'Scale services (within limits)',
                    'Invalidate CloudFront cache'
                ]
            },
            'admin': {
                'description': 'Full administrative access',
                'permissions': ['read', 'deploy', 'admin'],
                'actions': [
                    'All operator actions',
                    'Stop/start RDS',
                    'Stop services (scale to 0)',
                    'Manage user permissions'
                ]
            }
        }
    }


def list_audit_logs(query_params: Dict = None) -> Dict:
    """
    List audit logs.

    Query params:
    - user: Filter by user email
    - action: Filter by action type
    - hours: Hours of history (default: 24)
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(AUDIT_TABLE)

        user_filter = query_params.get('user') if query_params else None
        action_filter = query_params.get('action') if query_params else None
        hours = int(query_params.get('hours', 24)) if query_params else 24

        since_timestamp = int(time.time()) - (hours * 3600)

        if user_filter:
            # Query by user
            response = table.query(
                KeyConditionExpression='pk = :pk AND sk >= :since',
                ExpressionAttributeValues={
                    ':pk': f'USER#{user_filter}',
                    ':since': f'TS#{since_timestamp}'
                },
                ScanIndexForward=False,  # Newest first
                Limit=100
            )
        elif action_filter:
            # Query by action using GSI
            response = table.query(
                IndexName='project-env-index',
                KeyConditionExpression='gsi1pk = :pk AND gsi1sk >= :since',
                ExpressionAttributeValues={
                    ':pk': f'ACTION#{action_filter}',
                    ':since': f'TS#{since_timestamp}'
                },
                ScanIndexForward=False,
                Limit=100
            )
        else:
            # Scan recent logs
            response = table.scan(
                FilterExpression='#ts >= :since',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={':since': since_timestamp},
                Limit=100
            )

        items = response.get('Items', [])

        # Sort by timestamp descending
        items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        logs = []
        for item in items:
            logs.append({
                'timestamp': item.get('timestamp'),
                'actor': item.get('actor'),
                'action': item.get('action'),
                'target': item.get('target'),
                'result': item.get('result'),
                'details': item.get('details'),
            })

        return {
            'success': True,
            'logs': logs,
            'count': len(logs),
            'hours': hours
        }

    except ClientError as e:
        return {'error': str(e), 'success': False}


def route_admin_request(path: str, method: str, body: Dict, query_params: Dict, actor_email: str) -> Dict:
    """
    Route admin API requests.

    Endpoints:
    User Management:
    - GET    /api/admin/users              - List all users
    - GET    /api/admin/users/{email}      - Get user details
    - POST   /api/admin/users              - Create user
    - PUT    /api/admin/users              - Update user
    - DELETE /api/admin/users              - Delete user

    Group Management:
    - GET    /api/admin/groups             - List all groups
    - GET    /api/admin/groups/{name}      - Get group details
    - POST   /api/admin/groups             - Create group
    - PUT    /api/admin/groups             - Update group
    - DELETE /api/admin/groups             - Delete group
    - GET    /api/admin/groups/{name}/members      - List group members
    - POST   /api/admin/groups/{name}/members      - Add member to group
    - DELETE /api/admin/groups/{name}/members      - Remove member from group
    - POST   /api/admin/groups/permissions         - Grant group permission
    - DELETE /api/admin/groups/permissions         - Revoke group permission

    Permission Management:
    - GET    /api/admin/permissions        - List all permissions
    - GET    /api/admin/permissions/{email} - Get user permissions
    - POST   /api/admin/permissions        - Grant permission
    - DELETE /api/admin/permissions        - Revoke permission

    Other:
    - GET    /api/admin/roles              - List available roles
    - GET    /api/admin/audit              - List audit logs
    - POST   /api/admin/init               - Initialize first admin (no auth required)
    """

    # ==========================================================================
    # User Management
    # ==========================================================================

    # GET /api/admin/users
    if path == '/api/admin/users' and method == 'GET':
        return list_users()

    # GET /api/admin/users/{email}
    if path.startswith('/api/admin/users/') and method == 'GET' and '/members' not in path:
        email = path.replace('/api/admin/users/', '')
        user = get_user(email)
        if not user:
            return {'success': False, 'error': f'User {email} not found'}
        permissions = get_user_effective_permissions(email, user.local_groups)
        return {
            'success': True,
            'user': user.to_dict(),
            'permissions': [
                {
                    'project': p.project,
                    'environment': p.environment,
                    'role': p.role.value,
                    'source': p.source,
                    'sourceName': p.source_name,
                }
                for p in permissions
            ]
        }

    # POST /api/admin/users
    if path == '/api/admin/users' and method == 'POST':
        return create_user(
            email=body.get('email'),
            password=body.get('password'),
            display_name=body.get('displayName'),
            default_role=body.get('defaultRole', 'viewer'),
            groups=body.get('groups', []),
            actor_email=actor_email
        )

    # PUT /api/admin/users
    if path == '/api/admin/users' and method == 'PUT':
        return update_user(
            email=body.get('email'),
            display_name=body.get('displayName'),
            default_role=body.get('defaultRole'),
            password=body.get('password'),
            disabled=body.get('disabled'),
            actor_email=actor_email
        )

    # DELETE /api/admin/users
    if path == '/api/admin/users' and method == 'DELETE':
        return delete_user(body.get('email'), actor_email)

    # ==========================================================================
    # Group Management
    # ==========================================================================

    # GET /api/admin/groups
    if path == '/api/admin/groups' and method == 'GET':
        return list_groups()

    # GET /api/admin/groups/{name}
    if path.startswith('/api/admin/groups/') and method == 'GET':
        # Check if it's a members request
        if '/members' in path:
            group_name = path.replace('/api/admin/groups/', '').replace('/members', '')
            return get_group_members(group_name)

        group_name = path.replace('/api/admin/groups/', '')
        group = get_group(group_name)
        if not group:
            return {'success': False, 'error': f'Group {group_name} not found'}
        permissions = get_group_permissions(group_name)
        return {
            'success': True,
            'group': group.to_dict(),
            'permissions': [
                {
                    'project': p.project,
                    'environment': p.environment,
                    'role': p.role.value,
                }
                for p in permissions
            ]
        }

    # POST /api/admin/groups
    if path == '/api/admin/groups' and method == 'POST':
        return create_group(
            name=body.get('name'),
            description=body.get('description'),
            sso_group_name=body.get('ssoGroupName'),
            sso_group_id=body.get('ssoGroupId'),
            default_role=body.get('defaultRole', 'viewer'),
            actor_email=actor_email
        )

    # PUT /api/admin/groups
    if path == '/api/admin/groups' and method == 'PUT':
        return update_group(
            name=body.get('name'),
            description=body.get('description'),
            sso_group_name=body.get('ssoGroupName'),
            sso_group_id=body.get('ssoGroupId'),
            default_role=body.get('defaultRole'),
            actor_email=actor_email
        )

    # DELETE /api/admin/groups
    if path == '/api/admin/groups' and method == 'DELETE':
        return delete_group(body.get('name'), actor_email)

    # POST /api/admin/groups/{name}/members
    if '/members' in path and method == 'POST':
        group_name = path.replace('/api/admin/groups/', '').replace('/members', '')
        return add_user_to_group(body.get('email'), group_name, actor_email)

    # DELETE /api/admin/groups/{name}/members
    if '/members' in path and method == 'DELETE':
        group_name = path.replace('/api/admin/groups/', '').replace('/members', '')
        return remove_user_from_group(body.get('email'), group_name, actor_email)

    # POST /api/admin/groups/permissions
    if path == '/api/admin/groups/permissions' and method == 'POST':
        return grant_group_permission(
            group_name=body.get('group'),
            project=body.get('project'),
            environment=body.get('environment', '*'),
            role=body.get('role', 'viewer'),
            resources=body.get('resources'),
            actor_email=actor_email
        )

    # DELETE /api/admin/groups/permissions
    if path == '/api/admin/groups/permissions' and method == 'DELETE':
        return revoke_group_permission(
            group_name=body.get('group'),
            project=body.get('project'),
            environment=body.get('environment', '*'),
            actor_email=actor_email
        )

    # ==========================================================================
    # Permission Management (User-specific)
    # ==========================================================================

    # GET /api/admin/permissions
    if path == '/api/admin/permissions' and method == 'GET':
        return list_permissions(query_params, actor_email)

    # GET /api/admin/permissions/{email}
    if path.startswith('/api/admin/permissions/') and method == 'GET':
        email = path.replace('/api/admin/permissions/', '')
        return get_user_permissions_legacy(email)

    # POST /api/admin/permissions
    if path == '/api/admin/permissions' and method == 'POST':
        return grant_permission(body, actor_email)

    # DELETE /api/admin/permissions
    if path == '/api/admin/permissions' and method == 'DELETE':
        return revoke_permission(body, actor_email)

    # ==========================================================================
    # Other
    # ==========================================================================

    # GET /api/admin/roles
    if path == '/api/admin/roles' and method == 'GET':
        return list_roles()

    # GET /api/admin/audit
    if path == '/api/admin/audit' and method == 'GET':
        return list_audit_logs(query_params)

    # POST /api/admin/init
    if path == '/api/admin/init' and method == 'POST':
        return init_admin(
            email=body.get('email'),
            password=body.get('password')
        )

    return {'error': f'Unknown admin endpoint: {method} {path}', 'success': False}
