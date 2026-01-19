"""
User and Group Management for Dashborion

Handles CRUD operations for users and groups stored in DynamoDB.
Supports both local users and SSO group mappings.
"""

import os
import time
import hashlib
import secrets
from typing import Dict, List, Optional, Any, Tuple

import boto3
from botocore.exceptions import ClientError

from .models import User, Group, Permission, DashborionRole

# Table names from environment
USERS_TABLE = os.environ.get('USERS_TABLE_NAME', 'dashborion-users')
GROUPS_TABLE = os.environ.get('GROUPS_TABLE_NAME', 'dashborion-groups')
PERMISSIONS_TABLE = os.environ.get('PERMISSIONS_TABLE_NAME', 'dashborion-permissions')
AUDIT_TABLE = os.environ.get('AUDIT_TABLE_NAME', 'dashborion-audit')

# DynamoDB client (lazy initialized)
_dynamodb = None


def _get_dynamodb():
    """Get DynamoDB resource"""
    global _dynamodb
    if _dynamodb is None:
        # Support LocalStack for local development
        localstack_endpoint = os.environ.get('LOCALSTACK_ENDPOINT')
        if localstack_endpoint:
            _dynamodb = boto3.resource(
                'dynamodb',
                endpoint_url=localstack_endpoint,
                region_name=os.environ.get('AWS_DEFAULT_REGION', 'eu-west-3'),
                aws_access_key_id='test',
                aws_secret_access_key='test'
            )
        else:
            _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def _hash_password(password: str) -> str:
    """
    Hash password using PBKDF2 with SHA256.
    Format: pbkdf2:sha256:iterations$salt$hash
    """
    iterations = 260000
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations)
    hash_value = dk.hex()
    return f"pbkdf2:sha256:{iterations}${salt}${hash_value}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored hash"""
    try:
        if not password_hash.startswith('pbkdf2:sha256:'):
            return False

        parts = password_hash.split('$')
        if len(parts) != 3:
            return False

        header = parts[0]
        salt = parts[1]
        stored_hash = parts[2]

        iterations = int(header.split(':')[2])
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations)
        return dk.hex() == stored_hash
    except Exception:
        return False


def _audit_log(actor_email: str, action: str, target: Dict, result: str, details: Dict = None):
    """Record audit log entry"""
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


# =============================================================================
# User Management
# =============================================================================

def create_user(
    email: str,
    password: Optional[str] = None,
    display_name: Optional[str] = None,
    default_role: str = "viewer",
    groups: List[str] = None,
    actor_email: str = "system"
) -> Dict[str, Any]:
    """
    Create a new user.

    Args:
        email: User email (unique identifier)
        password: Optional password for local auth (hashed before storage)
        display_name: Display name
        default_role: Default role (viewer, operator, admin)
        groups: List of local group names to add user to
        actor_email: Email of user performing this action

    Returns:
        Dict with success status and user data or error
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(USERS_TABLE)

        # Check if user already exists
        existing = table.get_item(Key={'pk': f'USER#{email}', 'sk': 'PROFILE'})
        if 'Item' in existing:
            return {'success': False, 'error': f'User {email} already exists'}

        timestamp = int(time.time())
        role = DashborionRole.from_string(default_role)

        item = {
            'pk': f'USER#{email}',
            'sk': 'PROFILE',
            'gsi1pk': f'ROLE#{role.value}',
            'gsi1sk': f'USER#{email}',
            'email': email,
            'displayName': display_name or email.split('@')[0],
            'defaultRole': role.value,
            'disabled': False,
            'createdAt': timestamp,
            'createdBy': actor_email,
            'updatedAt': timestamp,
            'localGroups': groups or [],
        }

        if password:
            item['passwordHash'] = _hash_password(password)

        table.put_item(Item=item)

        # Add user to groups
        if groups:
            for group_name in groups:
                add_user_to_group(email, group_name, actor_email)

        _audit_log(actor_email, 'create_user', {'email': email}, 'success',
                   {'role': role.value, 'groups': groups})

        return {
            'success': True,
            'user': {
                'email': email,
                'displayName': item['displayName'],
                'defaultRole': role.value,
                'disabled': False,
                'createdAt': timestamp,
                'localGroups': groups or [],
            }
        }

    except ClientError as e:
        _audit_log(actor_email, 'create_user', {'email': email}, 'error', {'error': str(e)})
        return {'success': False, 'error': str(e)}


def get_user(email: str) -> Optional[User]:
    """Get user by email"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(USERS_TABLE)

        response = table.get_item(Key={'pk': f'USER#{email}', 'sk': 'PROFILE'})

        if 'Item' not in response:
            return None

        item = response['Item']
        return User(
            email=item['email'],
            display_name=item.get('displayName'),
            password_hash=item.get('passwordHash'),
            default_role=DashborionRole.from_string(item.get('defaultRole', 'viewer')),
            disabled=item.get('disabled', False),
            created_at=item.get('createdAt'),
            created_by=item.get('createdBy'),
            updated_at=item.get('updatedAt'),
            last_login=item.get('lastLogin'),
            local_groups=item.get('localGroups', []),
        )

    except ClientError:
        return None


def list_users(limit: int = 100) -> Dict[str, Any]:
    """List all users"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(USERS_TABLE)

        response = table.scan(
            FilterExpression='sk = :sk',
            ExpressionAttributeValues={':sk': 'PROFILE'},
            Limit=limit
        )

        users = []
        for item in response.get('Items', []):
            users.append({
                'email': item['email'],
                'displayName': item.get('displayName'),
                'defaultRole': item.get('defaultRole', 'viewer'),
                'disabled': item.get('disabled', False),
                'createdAt': item.get('createdAt'),
                'lastLogin': item.get('lastLogin'),
                'localGroups': item.get('localGroups', []),
            })

        return {'success': True, 'users': users, 'count': len(users)}

    except ClientError as e:
        return {'success': False, 'error': str(e)}


def update_user(
    email: str,
    display_name: Optional[str] = None,
    default_role: Optional[str] = None,
    password: Optional[str] = None,
    disabled: Optional[bool] = None,
    actor_email: str = "system"
) -> Dict[str, Any]:
    """Update user attributes"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(USERS_TABLE)

        # Build update expression
        update_parts = ['updatedAt = :updatedAt']
        values = {':updatedAt': int(time.time())}

        if display_name is not None:
            update_parts.append('displayName = :displayName')
            values[':displayName'] = display_name

        if default_role is not None:
            role = DashborionRole.from_string(default_role)
            update_parts.append('defaultRole = :defaultRole')
            update_parts.append('gsi1pk = :gsi1pk')
            values[':defaultRole'] = role.value
            values[':gsi1pk'] = f'ROLE#{role.value}'

        if password is not None:
            update_parts.append('passwordHash = :passwordHash')
            values[':passwordHash'] = _hash_password(password)

        if disabled is not None:
            update_parts.append('disabled = :disabled')
            values[':disabled'] = disabled

        table.update_item(
            Key={'pk': f'USER#{email}', 'sk': 'PROFILE'},
            UpdateExpression='SET ' + ', '.join(update_parts),
            ExpressionAttributeValues=values,
            ConditionExpression='attribute_exists(pk)'
        )

        _audit_log(actor_email, 'update_user', {'email': email}, 'success',
                   {'changes': list(values.keys())})

        return {'success': True, 'message': f'User {email} updated'}

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return {'success': False, 'error': f'User {email} not found'}
        _audit_log(actor_email, 'update_user', {'email': email}, 'error', {'error': str(e)})
        return {'success': False, 'error': str(e)}


def delete_user(email: str, actor_email: str = "system") -> Dict[str, Any]:
    """Delete a user and all their permissions"""
    try:
        dynamodb = _get_dynamodb()
        users_table = dynamodb.Table(USERS_TABLE)
        permissions_table = dynamodb.Table(PERMISSIONS_TABLE)

        # Delete user profile
        users_table.delete_item(Key={'pk': f'USER#{email}', 'sk': 'PROFILE'})

        # Delete all user permissions
        response = permissions_table.query(
            KeyConditionExpression='pk = :pk',
            ExpressionAttributeValues={':pk': f'USER#{email}'}
        )
        for item in response.get('Items', []):
            permissions_table.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

        _audit_log(actor_email, 'delete_user', {'email': email}, 'success')

        return {'success': True, 'message': f'User {email} deleted'}

    except ClientError as e:
        _audit_log(actor_email, 'delete_user', {'email': email}, 'error', {'error': str(e)})
        return {'success': False, 'error': str(e)}


def verify_user_password(email: str, password: str) -> Tuple[bool, Optional[User]]:
    """Verify user password for local authentication"""
    user = get_user(email)
    if not user:
        return False, None

    if user.disabled:
        return False, None

    if not user.password_hash:
        return False, None

    if _verify_password(password, user.password_hash):
        # Update last login
        try:
            dynamodb = _get_dynamodb()
            table = dynamodb.Table(USERS_TABLE)
            table.update_item(
                Key={'pk': f'USER#{email}', 'sk': 'PROFILE'},
                UpdateExpression='SET lastLogin = :lastLogin',
                ExpressionAttributeValues={':lastLogin': int(time.time())}
            )
        except Exception:
            pass
        return True, user

    return False, None


# =============================================================================
# Group Management
# =============================================================================

def create_group(
    name: str,
    description: Optional[str] = None,
    sso_group_name: Optional[str] = None,
    sso_group_id: Optional[str] = None,
    default_role: str = "viewer",
    actor_email: str = "system"
) -> Dict[str, Any]:
    """
    Create a new group.

    Args:
        name: Group name (unique identifier)
        description: Group description
        sso_group_name: SSO group name for mapping (e.g., "Platform Admins" from Azure AD)
        sso_group_id: SSO group ID for mapping (e.g., Azure AD group object ID) - legacy
        default_role: Default role for group members
        actor_email: Email of user performing this action

    Returns:
        Dict with success status and group data or error
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        # Check if group already exists
        existing = table.get_item(Key={'pk': f'GROUP#{name}', 'sk': 'METADATA'})
        if 'Item' in existing:
            return {'success': False, 'error': f'Group {name} already exists'}

        timestamp = int(time.time())
        role = DashborionRole.from_string(default_role)
        source = 'sso' if (sso_group_name or sso_group_id) else 'local'

        item = {
            'pk': f'GROUP#{name}',
            'sk': 'METADATA',
            'name': name,
            'description': description or '',
            'ssoGroupName': sso_group_name,
            'ssoGroupId': sso_group_id,
            'source': source,
            'defaultRole': role.value,
            'createdAt': timestamp,
            'createdBy': actor_email,
            'updatedAt': timestamp,
        }

        # Add GSI for SSO group lookup (by name or ID)
        if sso_group_name:
            item['gsi1pk'] = f'SSONAME#{sso_group_name}'
            item['gsi1sk'] = f'GROUP#{name}'
        elif sso_group_id:
            item['gsi1pk'] = f'SSO#{sso_group_id}'
            item['gsi1sk'] = f'GROUP#{name}'

        table.put_item(Item=item)

        _audit_log(actor_email, 'create_group', {'name': name}, 'success',
                   {'ssoGroupName': sso_group_name, 'ssoGroupId': sso_group_id, 'role': role.value})

        return {
            'success': True,
            'group': {
                'name': name,
                'description': description,
                'ssoGroupName': sso_group_name,
                'ssoGroupId': sso_group_id,
                'source': source,
                'defaultRole': role.value,
                'createdAt': timestamp,
            }
        }

    except ClientError as e:
        _audit_log(actor_email, 'create_group', {'name': name}, 'error', {'error': str(e)})
        return {'success': False, 'error': str(e)}


def get_group(name: str) -> Optional[Group]:
    """Get group by name"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        response = table.get_item(Key={'pk': f'GROUP#{name}', 'sk': 'METADATA'})

        if 'Item' not in response:
            return None

        item = response['Item']
        return Group(
            name=item['name'],
            description=item.get('description'),
            sso_group_name=item.get('ssoGroupName'),
            sso_group_id=item.get('ssoGroupId'),
            source=item.get('source', 'local'),
            default_role=DashborionRole.from_string(item.get('defaultRole', 'viewer')),
            created_at=item.get('createdAt'),
            created_by=item.get('createdBy'),
            updated_at=item.get('updatedAt'),
        )

    except ClientError:
        return None


def get_group_by_sso_name(sso_group_name: str) -> Optional[Group]:
    """Get group by SSO group name (from SAML claims)"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        response = table.query(
            IndexName='sso-group-index',
            KeyConditionExpression='gsi1pk = :pk',
            ExpressionAttributeValues={':pk': f'SSONAME#{sso_group_name}'},
            Limit=1
        )

        if not response.get('Items'):
            return None

        item = response['Items'][0]
        return Group(
            name=item['name'],
            description=item.get('description'),
            sso_group_name=item.get('ssoGroupName'),
            sso_group_id=item.get('ssoGroupId'),
            source=item.get('source', 'sso'),
            default_role=DashborionRole.from_string(item.get('defaultRole', 'viewer')),
            created_at=item.get('createdAt'),
            created_by=item.get('createdBy'),
            updated_at=item.get('updatedAt'),
        )

    except ClientError:
        return None


def get_group_by_sso_id(sso_group_id: str) -> Optional[Group]:
    """Get group by SSO group ID (legacy - prefer get_group_by_sso_name)"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        response = table.query(
            IndexName='sso-group-index',
            KeyConditionExpression='gsi1pk = :pk',
            ExpressionAttributeValues={':pk': f'SSO#{sso_group_id}'},
            Limit=1
        )

        if not response.get('Items'):
            return None

        item = response['Items'][0]
        return Group(
            name=item['name'],
            description=item.get('description'),
            sso_group_name=item.get('ssoGroupName'),
            sso_group_id=item.get('ssoGroupId'),
            source=item.get('source', 'sso'),
            default_role=DashborionRole.from_string(item.get('defaultRole', 'viewer')),
            created_at=item.get('createdAt'),
            created_by=item.get('createdBy'),
            updated_at=item.get('updatedAt'),
        )

    except ClientError:
        return None


def list_groups() -> Dict[str, Any]:
    """List all groups"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        response = table.scan(
            FilterExpression='sk = :sk',
            ExpressionAttributeValues={':sk': 'METADATA'}
        )

        groups = []
        for item in response.get('Items', []):
            groups.append({
                'name': item['name'],
                'description': item.get('description'),
                'ssoGroupName': item.get('ssoGroupName'),
                'ssoGroupId': item.get('ssoGroupId'),
                'source': item.get('source', 'local'),
                'defaultRole': item.get('defaultRole', 'viewer'),
                'createdAt': item.get('createdAt'),
            })

        return {'success': True, 'groups': groups, 'count': len(groups)}

    except ClientError as e:
        return {'success': False, 'error': str(e)}


def update_group(
    name: str,
    description: Optional[str] = None,
    sso_group_name: Optional[str] = None,
    sso_group_id: Optional[str] = None,
    default_role: Optional[str] = None,
    actor_email: str = "system"
) -> Dict[str, Any]:
    """Update group attributes"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        # Build update expression
        update_parts = ['updatedAt = :updatedAt']
        values = {':updatedAt': int(time.time())}

        if description is not None:
            update_parts.append('description = :description')
            values[':description'] = description

        # Handle SSO mapping - prefer name over ID
        if sso_group_name is not None:
            update_parts.append('ssoGroupName = :ssoGroupName')
            update_parts.append('gsi1pk = :gsi1pk')
            update_parts.append('gsi1sk = :gsi1sk')
            values[':ssoGroupName'] = sso_group_name
            values[':gsi1pk'] = f'SSONAME#{sso_group_name}' if sso_group_name else None
            values[':gsi1sk'] = f'GROUP#{name}' if sso_group_name else None
        elif sso_group_id is not None:
            update_parts.append('ssoGroupId = :ssoGroupId')
            update_parts.append('gsi1pk = :gsi1pk')
            update_parts.append('gsi1sk = :gsi1sk')
            values[':ssoGroupId'] = sso_group_id
            values[':gsi1pk'] = f'SSO#{sso_group_id}' if sso_group_id else None
            values[':gsi1sk'] = f'GROUP#{name}' if sso_group_id else None

        if default_role is not None:
            role = DashborionRole.from_string(default_role)
            update_parts.append('defaultRole = :defaultRole')
            values[':defaultRole'] = role.value

        table.update_item(
            Key={'pk': f'GROUP#{name}', 'sk': 'METADATA'},
            UpdateExpression='SET ' + ', '.join(update_parts),
            ExpressionAttributeValues=values,
            ConditionExpression='attribute_exists(pk)'
        )

        _audit_log(actor_email, 'update_group', {'name': name}, 'success')

        return {'success': True, 'message': f'Group {name} updated'}

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return {'success': False, 'error': f'Group {name} not found'}
        _audit_log(actor_email, 'update_group', {'name': name}, 'error', {'error': str(e)})
        return {'success': False, 'error': str(e)}


def delete_group(name: str, actor_email: str = "system") -> Dict[str, Any]:
    """Delete a group and all its permissions"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        # Delete all group items (metadata + permissions)
        response = table.query(
            KeyConditionExpression='pk = :pk',
            ExpressionAttributeValues={':pk': f'GROUP#{name}'}
        )
        for item in response.get('Items', []):
            table.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

        # Remove group from all users
        users_table = dynamodb.Table(USERS_TABLE)
        users_response = users_table.scan(
            FilterExpression='contains(localGroups, :group)',
            ExpressionAttributeValues={':group': name}
        )
        for user_item in users_response.get('Items', []):
            groups = user_item.get('localGroups', [])
            if name in groups:
                groups.remove(name)
                users_table.update_item(
                    Key={'pk': user_item['pk'], 'sk': user_item['sk']},
                    UpdateExpression='SET localGroups = :groups',
                    ExpressionAttributeValues={':groups': groups}
                )

        _audit_log(actor_email, 'delete_group', {'name': name}, 'success')

        return {'success': True, 'message': f'Group {name} deleted'}

    except ClientError as e:
        _audit_log(actor_email, 'delete_group', {'name': name}, 'error', {'error': str(e)})
        return {'success': False, 'error': str(e)}


def add_user_to_group(email: str, group_name: str, actor_email: str = "system") -> Dict[str, Any]:
    """Add user to a local group"""
    try:
        # Verify group exists
        group = get_group(group_name)
        if not group:
            return {'success': False, 'error': f'Group {group_name} not found'}

        dynamodb = _get_dynamodb()
        table = dynamodb.Table(USERS_TABLE)

        # Get current groups
        response = table.get_item(Key={'pk': f'USER#{email}', 'sk': 'PROFILE'})
        if 'Item' not in response:
            return {'success': False, 'error': f'User {email} not found'}

        groups = response['Item'].get('localGroups', [])
        if group_name in groups:
            return {'success': True, 'message': f'User {email} already in group {group_name}'}

        groups.append(group_name)

        table.update_item(
            Key={'pk': f'USER#{email}', 'sk': 'PROFILE'},
            UpdateExpression='SET localGroups = :groups, updatedAt = :updatedAt',
            ExpressionAttributeValues={
                ':groups': groups,
                ':updatedAt': int(time.time())
            }
        )

        _audit_log(actor_email, 'add_user_to_group',
                   {'email': email, 'group': group_name}, 'success')

        return {'success': True, 'message': f'User {email} added to group {group_name}'}

    except ClientError as e:
        return {'success': False, 'error': str(e)}


def remove_user_from_group(email: str, group_name: str, actor_email: str = "system") -> Dict[str, Any]:
    """Remove user from a local group"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(USERS_TABLE)

        # Get current groups
        response = table.get_item(Key={'pk': f'USER#{email}', 'sk': 'PROFILE'})
        if 'Item' not in response:
            return {'success': False, 'error': f'User {email} not found'}

        groups = response['Item'].get('localGroups', [])
        if group_name not in groups:
            return {'success': True, 'message': f'User {email} not in group {group_name}'}

        groups.remove(group_name)

        table.update_item(
            Key={'pk': f'USER#{email}', 'sk': 'PROFILE'},
            UpdateExpression='SET localGroups = :groups, updatedAt = :updatedAt',
            ExpressionAttributeValues={
                ':groups': groups,
                ':updatedAt': int(time.time())
            }
        )

        _audit_log(actor_email, 'remove_user_from_group',
                   {'email': email, 'group': group_name}, 'success')

        return {'success': True, 'message': f'User {email} removed from group {group_name}'}

    except ClientError as e:
        return {'success': False, 'error': str(e)}


def get_group_members(group_name: str) -> Dict[str, Any]:
    """Get all members of a group"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(USERS_TABLE)

        response = table.scan(
            FilterExpression='contains(localGroups, :group)',
            ExpressionAttributeValues={':group': group_name}
        )

        members = []
        for item in response.get('Items', []):
            members.append({
                'email': item['email'],
                'displayName': item.get('displayName'),
                'defaultRole': item.get('defaultRole', 'viewer'),
            })

        return {'success': True, 'group': group_name, 'members': members, 'count': len(members)}

    except ClientError as e:
        return {'success': False, 'error': str(e)}


# =============================================================================
# Group Permission Management
# =============================================================================

def grant_group_permission(
    group_name: str,
    project: str,
    environment: str = "*",
    role: str = "viewer",
    resources: List[str] = None,
    actor_email: str = "system"
) -> Dict[str, Any]:
    """Grant permission to a group"""
    try:
        # Verify group exists
        group = get_group(group_name)
        if not group:
            return {'success': False, 'error': f'Group {group_name} not found'}

        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        timestamp = int(time.time())
        role_enum = DashborionRole.from_string(role)

        item = {
            'pk': f'GROUP#{group_name}',
            'sk': f'PERM#{project}#{environment}',
            'gsi1pk': f'PROJECT#{project}',
            'gsi1sk': f'ENV#{environment}#GROUP#{group_name}',
            'project': project,
            'environment': environment,
            'role': role_enum.value,
            'resources': resources or ['*'],
            'grantedBy': actor_email,
            'grantedAt': timestamp,
        }

        table.put_item(Item=item)

        _audit_log(actor_email, 'grant_group_permission',
                   {'group': group_name, 'project': project, 'environment': environment},
                   'success', {'role': role_enum.value})

        return {
            'success': True,
            'message': f'Permission granted: {group_name} is now {role_enum.value} for {project}/{environment}'
        }

    except ClientError as e:
        return {'success': False, 'error': str(e)}


def revoke_group_permission(
    group_name: str,
    project: str,
    environment: str = "*",
    actor_email: str = "system"
) -> Dict[str, Any]:
    """Revoke permission from a group"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        table.delete_item(
            Key={
                'pk': f'GROUP#{group_name}',
                'sk': f'PERM#{project}#{environment}'
            }
        )

        _audit_log(actor_email, 'revoke_group_permission',
                   {'group': group_name, 'project': project, 'environment': environment},
                   'success')

        return {
            'success': True,
            'message': f'Permission revoked: {group_name} no longer has access to {project}/{environment}'
        }

    except ClientError as e:
        return {'success': False, 'error': str(e)}


def get_group_permissions(group_name: str) -> List[Permission]:
    """Get all permissions for a group"""
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(GROUPS_TABLE)

        response = table.query(
            KeyConditionExpression='pk = :pk AND begins_with(sk, :prefix)',
            ExpressionAttributeValues={
                ':pk': f'GROUP#{group_name}',
                ':prefix': 'PERM#'
            }
        )

        permissions = []
        for item in response.get('Items', []):
            permissions.append(Permission(
                project=item.get('project', '*'),
                environment=item.get('environment', '*'),
                role=DashborionRole.from_string(item.get('role', 'viewer')),
                resources=item.get('resources', ['*']),
                source='group',
                source_name=group_name,
            ))

        return permissions

    except ClientError:
        return []


# =============================================================================
# Permission Resolution
# =============================================================================

def get_user_effective_permissions(
    email: str,
    local_groups: List[str] = None,
    sso_groups: List[str] = None
) -> List[Permission]:
    """
    Get effective permissions for a user, including group permissions.

    Priority (highest role wins):
    1. User-specific permissions
    2. Local group permissions
    3. SSO group permissions (mapped via sso_group_id)

    Args:
        email: User email
        local_groups: List of local group names (from user profile)
        sso_groups: List of SSO group IDs (from IdP)

    Returns:
        List of effective permissions
    """
    permissions_map: Dict[str, Permission] = {}

    def add_permission(perm: Permission):
        """Add permission, keeping the highest role per project/environment"""
        key = f"{perm.project}#{perm.environment}"
        role_priority = {DashborionRole.ADMIN: 3, DashborionRole.OPERATOR: 2, DashborionRole.VIEWER: 1}

        if key not in permissions_map:
            permissions_map[key] = perm
        else:
            existing = permissions_map[key]
            if role_priority.get(perm.role, 0) > role_priority.get(existing.role, 0):
                permissions_map[key] = perm

    # 1. Get user-specific permissions
    try:
        dynamodb = _get_dynamodb()
        perm_table = dynamodb.Table(PERMISSIONS_TABLE)

        response = perm_table.query(
            KeyConditionExpression='pk = :pk',
            ExpressionAttributeValues={':pk': f'USER#{email}'}
        )

        for item in response.get('Items', []):
            perm = Permission(
                project=item.get('project', '*'),
                environment=item.get('environment', '*'),
                role=DashborionRole.from_string(item.get('role', 'viewer')),
                resources=item.get('resources', ['*']),
                require_mfa=item.get('conditions', {}).get('requireMfa', False),
                expires_at=item.get('expiresAt'),
                source='user',
            )
            add_permission(perm)
    except Exception:
        pass

    # 2. Get local group permissions
    if local_groups:
        for group_name in local_groups:
            group_perms = get_group_permissions(group_name)
            for perm in group_perms:
                add_permission(perm)

    # 3. Get SSO group permissions (map SSO groups to local groups)
    # sso_groups can contain either group names (preferred) or group IDs
    if sso_groups:
        for sso_group in sso_groups:
            # Try by name first (more common in SAML claims)
            group = get_group_by_sso_name(sso_group)
            if not group:
                # Fall back to ID (legacy)
                group = get_group_by_sso_id(sso_group)
            if group:
                group_perms = get_group_permissions(group.name)
                for perm in group_perms:
                    perm.source = 'sso'
                    perm.source_name = group.name
                    add_permission(perm)

    return list(permissions_map.values())


# =============================================================================
# Bootstrap / Init
# =============================================================================

def has_any_admin() -> bool:
    """
    Check if any admin user exists in the system.
    Used to determine if first SSO user should be auto-promoted to admin.
    """
    try:
        result = list_users()
        if result.get('success'):
            for user in result.get('users', []):
                if user.get('defaultRole') == 'admin':
                    return True
        return False
    except Exception:
        return False


def init_admin(email: str, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Initialize the first admin user.

    This should only be called when no admin exists.
    """
    try:
        # Check if any admin exists
        result = list_users()
        if result.get('success'):
            for user in result.get('users', []):
                if user.get('defaultRole') == 'admin':
                    return {
                        'success': False,
                        'error': 'An admin user already exists. Use admin commands to manage users.'
                    }

        # Create admin user
        return create_user(
            email=email,
            password=password,
            default_role='admin',
            actor_email='system-init'
        )

    except Exception as e:
        return {'success': False, 'error': str(e)}
