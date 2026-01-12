"""
Admin Commands for Dashborion CLI

Provides commands for:
- User management (add, list, remove, update)
- Group management (add, list, remove, members, permissions)
- Permission management (grant, revoke, list)
- Audit log viewing
- Initial setup (init)

All admin commands require authentication with admin privileges.
"""

import click
import json
import sys
from typing import Optional
from datetime import datetime

import requests

from dashborion.commands.auth import get_valid_token, get_api_base_url
from dashborion.commands.context import get_current_context
from dashborion.utils.api_client import get_api_client, AuthenticationError


def _api_request(method: str, path: str, data: dict = None, params: dict = None) -> dict:
    """Make authenticated API request using centralized client"""
    try:
        client = get_api_client()

        if method == 'GET':
            response = client.get(path, params=params)
        elif method == 'POST':
            response = client.post(path, json_data=data)
        elif method == 'PUT':
            response = client.put(path, json_data=data)
        elif method == 'DELETE':
            response = client.delete(path, json_data=data)
        else:
            raise ValueError(f"Unknown method: {method}")

        if response.status_code == 401:
            raise click.ClickException("Unauthorized. Please re-authenticate.")
        if response.status_code == 403:
            raise click.ClickException("Permission denied. Admin privileges required.")

        return response.json()

    except AuthenticationError as e:
        raise click.ClickException(str(e))
    except requests.RequestException as e:
        raise click.ClickException(f"API request failed: {e}")


def _format_timestamp(ts: int) -> str:
    """Format Unix timestamp to human readable string"""
    if not ts:
        return "N/A"
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')


@click.group()
def admin():
    """Admin commands for user and permission management"""
    pass


# =============================================================================
# User Commands
# =============================================================================

@admin.group()
def user():
    """User management commands"""
    pass


@user.command('list')
@click.option('--output', '-o', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
def user_list(output: str):
    """List all users"""
    result = _api_request('GET', '/api/admin/users')

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    users = result.get('users', [])

    if output == 'json':
        click.echo(json.dumps(users, indent=2))
        return

    if not users:
        click.echo("No users found.")
        click.echo()
        click.echo("Create the first admin user:")
        click.echo("  dashborion admin init --email admin@example.com")
        return

    click.echo()
    click.echo(f"{'EMAIL':<35} {'ROLE':<10} {'GROUPS':<20} {'LAST LOGIN':<16} {'STATUS'}")
    click.echo(f"{'-'*35} {'-'*10} {'-'*20} {'-'*16} {'-'*10}")

    for u in users:
        email = u.get('email', '')[:33]
        role = u.get('defaultRole', 'viewer')
        groups = ', '.join(u.get('localGroups', []))[:18]
        last_login = _format_timestamp(u.get('lastLogin'))
        status = 'disabled' if u.get('disabled') else 'active'

        click.echo(f"{email:<35} {role:<10} {groups:<20} {last_login:<16} {status}")

    click.echo()
    click.echo(f"Total: {len(users)} users")


@user.command('add')
@click.argument('email')
@click.option('--role', '-r', type=click.Choice(['viewer', 'operator', 'admin']),
              default='viewer', help='Default role')
@click.option('--password', '-p', help='Password for local authentication (optional)')
@click.option('--display-name', '-n', help='Display name')
@click.option('--group', '-g', multiple=True, help='Add to group(s)')
def user_add(email: str, role: str, password: Optional[str], display_name: Optional[str], group: tuple):
    """Add a new user"""
    if password is None:
        # Prompt for password if desired
        if click.confirm("Set a password for local authentication?", default=False):
            password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    data = {
        'email': email,
        'defaultRole': role,
        'groups': list(group) if group else [],
    }
    if password:
        data['password'] = password
    if display_name:
        data['displayName'] = display_name

    result = _api_request('POST', '/api/admin/users', data)

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"User created: {click.style(email, bold=True, fg='green')}")
    click.echo(f"Role: {role}")
    if group:
        click.echo(f"Groups: {', '.join(group)}")


@user.command('remove')
@click.argument('email')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
def user_remove(email: str, force: bool):
    """Remove a user"""
    if not force:
        if not click.confirm(f"Remove user '{email}' and all their permissions?"):
            click.echo("Cancelled.")
            return

    result = _api_request('DELETE', '/api/admin/users', {'email': email})

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"User removed: {email}")


@user.command('update')
@click.argument('email')
@click.option('--role', '-r', type=click.Choice(['viewer', 'operator', 'admin']),
              help='Set default role')
@click.option('--display-name', '-n', help='Set display name')
@click.option('--password', '-p', is_flag=True, help='Set new password')
@click.option('--enable', is_flag=True, help='Enable user')
@click.option('--disable', is_flag=True, help='Disable user')
def user_update(email: str, role: Optional[str], display_name: Optional[str],
                password: bool, enable: bool, disable: bool):
    """Update user attributes"""
    data = {'email': email}

    if role:
        data['defaultRole'] = role
    if display_name:
        data['displayName'] = display_name
    if password:
        data['password'] = click.prompt("New password", hide_input=True, confirmation_prompt=True)
    if enable:
        data['disabled'] = False
    if disable:
        data['disabled'] = True

    if len(data) == 1:
        click.echo("Error: No changes specified", err=True)
        sys.exit(1)

    result = _api_request('PUT', '/api/admin/users', data)

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"User updated: {email}")


@user.command('show')
@click.argument('email')
def user_show(email: str):
    """Show user details"""
    result = _api_request('GET', f'/api/admin/users/{email}')

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    user_data = result.get('user', {})

    click.echo()
    click.echo(f"Email: {click.style(user_data.get('email', ''), bold=True)}")
    click.echo(f"Display Name: {user_data.get('displayName', 'N/A')}")
    click.echo(f"Default Role: {user_data.get('defaultRole', 'viewer')}")
    click.echo(f"Status: {'disabled' if user_data.get('disabled') else 'active'}")
    click.echo(f"Created: {_format_timestamp(user_data.get('createdAt'))}")
    click.echo(f"Created By: {user_data.get('createdBy', 'N/A')}")
    click.echo(f"Last Login: {_format_timestamp(user_data.get('lastLogin'))}")

    groups = user_data.get('localGroups', [])
    if groups:
        click.echo(f"Groups: {', '.join(groups)}")

    # Show permissions
    permissions = result.get('permissions', [])
    if permissions:
        click.echo()
        click.echo("Permissions:")
        for perm in permissions:
            source = f" (from {perm.get('source', 'user')})" if perm.get('source') != 'user' else ''
            click.echo(f"  - {perm.get('project')}/{perm.get('environment')}: {perm.get('role')}{source}")


# =============================================================================
# Group Commands
# =============================================================================

@admin.group()
def group():
    """Group management commands"""
    pass


@group.command('list')
@click.option('--output', '-o', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
def group_list(output: str):
    """List all groups"""
    result = _api_request('GET', '/api/admin/groups')

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    groups = result.get('groups', [])

    if output == 'json':
        click.echo(json.dumps(groups, indent=2))
        return

    if not groups:
        click.echo("No groups found.")
        click.echo()
        click.echo("Create a group:")
        click.echo("  dashborion admin group add <name> [--sso-name 'Group Name']")
        return

    click.echo()
    click.echo(f"{'NAME':<25} {'ROLE':<10} {'SOURCE':<8} {'SSO MAPPING':<35} {'DESCRIPTION'}")
    click.echo(f"{'-'*25} {'-'*10} {'-'*8} {'-'*35} {'-'*30}")

    for g in groups:
        name = g.get('name', '')[:23]
        role = g.get('defaultRole', 'viewer')
        source = g.get('source', 'local')
        # Prefer ssoGroupName, fall back to ssoGroupId
        sso_mapping = g.get('ssoGroupName') or g.get('ssoGroupId') or ''
        sso_mapping = sso_mapping[:33]
        desc = (g.get('description') or '')[:28]

        click.echo(f"{name:<25} {role:<10} {source:<8} {sso_mapping:<35} {desc}")

    click.echo()
    click.echo(f"Total: {len(groups)} groups")


@group.command('add')
@click.argument('name')
@click.option('--description', '-d', help='Group description')
@click.option('--sso-name', '-s', help='SSO group name for mapping (e.g., "Platform Admins" from Azure AD)')
@click.option('--sso-id', help='SSO group ID for mapping (legacy, prefer --sso-name)')
@click.option('--role', '-r', type=click.Choice(['viewer', 'operator', 'admin']),
              default='viewer', help='Default role for group members')
def group_add(name: str, description: Optional[str], sso_name: Optional[str],
              sso_id: Optional[str], role: str):
    """Add a new group

    Examples:

        dashborion admin group add platform-admins --sso-name "Platform Admins" --role admin

        dashborion admin group add developers --role operator
    """
    data = {
        'name': name,
        'defaultRole': role,
    }
    if description:
        data['description'] = description
    if sso_name:
        data['ssoGroupName'] = sso_name
    if sso_id:
        data['ssoGroupId'] = sso_id

    result = _api_request('POST', '/api/admin/groups', data)

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"Group created: {click.style(name, bold=True, fg='green')}")
    click.echo(f"Default role: {role}")
    if sso_name:
        click.echo(f"SSO group name: {sso_name}")
    elif sso_id:
        click.echo(f"SSO group ID: {sso_id}")


@group.command('remove')
@click.argument('name')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
def group_remove(name: str, force: bool):
    """Remove a group"""
    if not force:
        if not click.confirm(f"Remove group '{name}' and all its permissions?"):
            click.echo("Cancelled.")
            return

    result = _api_request('DELETE', '/api/admin/groups', {'name': name})

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"Group removed: {name}")


@group.command('update')
@click.argument('name')
@click.option('--description', '-d', help='Set description')
@click.option('--sso-name', '-s', help='Set SSO group name for mapping')
@click.option('--sso-id', help='Set SSO group ID (legacy, prefer --sso-name)')
@click.option('--role', '-r', type=click.Choice(['viewer', 'operator', 'admin']),
              help='Set default role')
def group_update(name: str, description: Optional[str], sso_name: Optional[str],
                 sso_id: Optional[str], role: Optional[str]):
    """Update group attributes"""
    data = {'name': name}

    if description is not None:
        data['description'] = description
    if sso_name is not None:
        data['ssoGroupName'] = sso_name
    if sso_id is not None:
        data['ssoGroupId'] = sso_id
    if role:
        data['defaultRole'] = role

    if len(data) == 1:
        click.echo("Error: No changes specified", err=True)
        sys.exit(1)

    result = _api_request('PUT', '/api/admin/groups', data)

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"Group updated: {name}")


@group.command('members')
@click.argument('name')
def group_members(name: str):
    """List group members"""
    result = _api_request('GET', f'/api/admin/groups/{name}/members')

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    members = result.get('members', [])

    if not members:
        click.echo(f"Group '{name}' has no members.")
        return

    click.echo()
    click.echo(f"Members of '{name}':")
    click.echo()
    click.echo(f"{'EMAIL':<35} {'DISPLAY NAME':<25} {'ROLE'}")
    click.echo(f"{'-'*35} {'-'*25} {'-'*10}")

    for m in members:
        email = m.get('email', '')[:33]
        display_name = (m.get('displayName') or '')[:23]
        role = m.get('defaultRole', 'viewer')
        click.echo(f"{email:<35} {display_name:<25} {role}")

    click.echo()
    click.echo(f"Total: {len(members)} members")


@group.command('add-member')
@click.argument('group_name')
@click.argument('email')
def group_add_member(group_name: str, email: str):
    """Add user to group"""
    result = _api_request('POST', f'/api/admin/groups/{group_name}/members', {'email': email})

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"Added {email} to group {group_name}")


@group.command('remove-member')
@click.argument('group_name')
@click.argument('email')
def group_remove_member(group_name: str, email: str):
    """Remove user from group"""
    result = _api_request('DELETE', f'/api/admin/groups/{group_name}/members', {'email': email})

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"Removed {email} from group {group_name}")


# =============================================================================
# Permission Commands
# =============================================================================

@admin.group()
def permission():
    """Permission management commands"""
    pass


@permission.command('list')
@click.option('--user', '-u', 'user_email', help='Filter by user email')
@click.option('--group', '-g', 'group_name', help='Filter by group name')
@click.option('--project', '-p', help='Filter by project')
@click.option('--output', '-o', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
def permission_list(user_email: Optional[str], group_name: Optional[str],
                    project: Optional[str], output: str):
    """List permissions"""
    params = {}
    if user_email:
        params['user'] = user_email
    if group_name:
        params['group'] = group_name
    if project:
        params['project'] = project

    result = _api_request('GET', '/api/admin/permissions', params=params)

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    permissions = result.get('permissions', [])

    if output == 'json':
        click.echo(json.dumps(permissions, indent=2))
        return

    if not permissions:
        click.echo("No permissions found.")
        return

    click.echo()
    click.echo(f"{'TARGET':<35} {'PROJECT':<15} {'ENVIRONMENT':<12} {'ROLE':<10} {'SOURCE'}")
    click.echo(f"{'-'*35} {'-'*15} {'-'*12} {'-'*10} {'-'*15}")

    for p in permissions:
        target = p.get('email') or p.get('group', '')
        target = target[:33]
        project_name = p.get('project', '*')[:13]
        env = p.get('environment', '*')[:10]
        role = p.get('role', 'viewer')
        source = p.get('source', 'user')

        click.echo(f"{target:<35} {project_name:<15} {env:<12} {role:<10} {source}")

    click.echo()
    click.echo(f"Total: {len(permissions)} permissions")


@permission.command('grant')
@click.argument('target')
@click.option('--project', '-p', required=True, help='Project name (or * for all)')
@click.option('--environment', '-e', default='*', help='Environment name (or * for all)')
@click.option('--role', '-r', type=click.Choice(['viewer', 'operator', 'admin']),
              required=True, help='Role to grant')
@click.option('--group', '-g', is_flag=True, help='Target is a group name (not user email)')
def permission_grant(target: str, project: str, environment: str, role: str, group: bool):
    """Grant permission to user or group"""
    endpoint = '/api/admin/groups/permissions' if group else '/api/admin/permissions'
    key = 'group' if group else 'email'

    data = {
        key: target,
        'project': project,
        'environment': environment,
        'role': role,
    }

    result = _api_request('POST', endpoint, data)

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    target_type = "group" if group else "user"
    click.echo(f"Permission granted: {target} ({target_type}) is now {role} for {project}/{environment}")


@permission.command('revoke')
@click.argument('target')
@click.option('--project', '-p', required=True, help='Project name')
@click.option('--environment', '-e', default='*', help='Environment name')
@click.option('--group', '-g', is_flag=True, help='Target is a group name (not user email)')
def permission_revoke(target: str, project: str, environment: str, group: bool):
    """Revoke permission from user or group"""
    endpoint = '/api/admin/groups/permissions' if group else '/api/admin/permissions'
    key = 'group' if group else 'email'

    data = {
        key: target,
        'project': project,
        'environment': environment,
    }

    result = _api_request('DELETE', endpoint, data)

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo(f"Permission revoked: {target} no longer has access to {project}/{environment}")


# =============================================================================
# Audit Commands
# =============================================================================

@admin.command('audit')
@click.option('--user', '-u', 'user_email', help='Filter by user email')
@click.option('--action', '-a', help='Filter by action type')
@click.option('--hours', '-h', default=24, help='Hours of history (default: 24)')
@click.option('--output', '-o', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
def audit(user_email: Optional[str], action: Optional[str], hours: int, output: str):
    """View audit logs"""
    params = {'hours': hours}
    if user_email:
        params['user'] = user_email
    if action:
        params['action'] = action

    result = _api_request('GET', '/api/admin/audit', params=params)

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    logs = result.get('logs', [])

    if output == 'json':
        click.echo(json.dumps(logs, indent=2))
        return

    if not logs:
        click.echo(f"No audit logs found in the last {hours} hours.")
        return

    click.echo()
    click.echo(f"{'TIMESTAMP':<16} {'ACTOR':<30} {'ACTION':<25} {'TARGET':<30} {'RESULT'}")
    click.echo(f"{'-'*16} {'-'*30} {'-'*25} {'-'*30} {'-'*10}")

    for log in logs:
        ts = _format_timestamp(log.get('timestamp'))
        actor = (log.get('actor') or '')[:28]
        action_name = (log.get('action') or '')[:23]
        target = str(log.get('target', {}))[:28]
        result_str = log.get('result', '')

        click.echo(f"{ts:<16} {actor:<30} {action_name:<25} {target:<30} {result_str}")

    click.echo()
    click.echo(f"Showing {len(logs)} events from the last {hours} hours")


# =============================================================================
# Init Command
# =============================================================================

@admin.command('init')
@click.option('--email', '-e', required=True, help='Admin email address')
@click.option('--password', '-p', help='Admin password (for local auth)')
def init(email: str, password: Optional[str]):
    """
    Initialize Dashborion with first admin user

    This command creates the first admin user. It can only be run once
    when no admin users exist.

    Examples:
        dashborion admin init --email admin@example.com
        dashborion admin init --email admin@example.com --password secret
    """
    if password is None:
        if click.confirm("Set a password for local authentication?", default=False):
            password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    data = {'email': email}
    if password:
        data['password'] = password

    try:
        result = _api_request('POST', '/api/admin/init', data)
    except click.ClickException as e:
        # If not authenticated, try without auth for init
        if "Not authenticated" in str(e) or "Unauthorized" in str(e):
            api_url = get_api_base_url()
            try:
                response = requests.post(
                    f"{api_url}/api/admin/init",
                    json=data,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                result = response.json()
            except requests.RequestException as req_e:
                raise click.ClickException(f"API request failed: {req_e}")
        else:
            raise

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    click.echo()
    click.echo(click.style("Dashborion initialized successfully!", fg='green', bold=True))
    click.echo()
    click.echo(f"Admin user created: {email}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Login: dashborion auth login")
    click.echo("  2. Create groups: dashborion admin group add <name>")
    click.echo("  3. Add users: dashborion admin user add <email>")
    click.echo("  4. Grant permissions: dashborion admin permission grant <email> -p <project> -r <role>")


# =============================================================================
# Roles Command
# =============================================================================

@admin.command('roles')
def roles():
    """List available roles and their permissions"""
    result = _api_request('GET', '/api/admin/roles')

    if not result.get('success'):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    roles_data = result.get('roles', {})

    click.echo()
    for role_name, role_info in roles_data.items():
        click.echo(f"{click.style(role_name.upper(), bold=True)}")
        click.echo(f"  {role_info.get('description', '')}")
        click.echo()
        click.echo("  Actions:")
        for action in role_info.get('actions', []):
            click.echo(f"    - {action}")
        click.echo()


# =============================================================================
# Backup/Restore Commands
# =============================================================================

def _get_dynamodb_client(profile: Optional[str] = None, region: Optional[str] = None):
    """Get DynamoDB client with optional profile"""
    import boto3
    session_args = {}
    if profile:
        session_args['profile_name'] = profile
    if region:
        session_args['region_name'] = region
    session = boto3.Session(**session_args)
    return session.client('dynamodb')


def _get_dashborion_tables(dynamodb, prefix: str = 'dashborion') -> list:
    """List all DynamoDB tables matching the prefix"""
    tables = []
    paginator = dynamodb.get_paginator('list_tables')
    for page in paginator.paginate():
        for table_name in page.get('TableNames', []):
            if prefix in table_name.lower():
                tables.append(table_name)
    return sorted(tables)


def _scan_table(dynamodb, table_name: str) -> list:
    """Scan all items from a DynamoDB table"""
    items = []
    paginator = dynamodb.get_paginator('scan')
    for page in paginator.paginate(TableName=table_name):
        items.extend(page.get('Items', []))
    return items


def _deserialize_dynamodb_item(item: dict) -> dict:
    """Convert DynamoDB item format to regular Python dict"""
    from boto3.dynamodb.types import TypeDeserializer
    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in item.items()}


def _serialize_dynamodb_item(item: dict) -> dict:
    """Convert regular Python dict to DynamoDB item format"""
    from boto3.dynamodb.types import TypeSerializer
    serializer = TypeSerializer()
    return {k: serializer.serialize(v) for k, v in item.items()}


def _get_kms_client(profile: Optional[str] = None, region: Optional[str] = None):
    """Get KMS client with optional profile"""
    import boto3
    session_args = {}
    if profile:
        session_args['profile_name'] = profile
    if region:
        session_args['region_name'] = region
    session = boto3.Session(**session_args)
    return session.client('kms')


def _decrypt_kms_data(kms_client, encrypted_b64: str, context: dict) -> dict:
    """Decrypt KMS-encrypted data"""
    import base64
    ciphertext = base64.b64decode(encrypted_b64)
    response = kms_client.decrypt(
        CiphertextBlob=ciphertext,
        EncryptionContext=context
    )
    plaintext = response['Plaintext'].decode('utf-8')
    return json.loads(plaintext)


def _encrypt_kms_data(kms_client, data: dict, key_arn: str, context: dict) -> str:
    """Encrypt data with KMS"""
    import base64
    plaintext = json.dumps(data)
    response = kms_client.encrypt(
        KeyId=key_arn,
        Plaintext=plaintext.encode('utf-8'),
        EncryptionContext=context
    )
    return base64.b64encode(response['CiphertextBlob']).decode('utf-8')


def _get_encryption_context(item: dict) -> Optional[dict]:
    """
    Determine encryption context based on item type.

    Returns context dict or None if item doesn't have encrypted data.
    """
    pk = item.get('pk', '')

    # Token encryption context
    if pk.startswith('TOKEN#'):
        token_hash = pk.replace('TOKEN#', '')
        return {
            'service': 'dashborion',
            'purpose': 'access_token',
            'token_hash': token_hash[:16],
        }

    # Refresh token context
    if pk.startswith('REFRESH#'):
        refresh_hash = pk.replace('REFRESH#', '')
        return {
            'service': 'dashborion',
            'purpose': 'refresh_token',
            'token_hash': refresh_hash[:16],
        }

    # Session (SAML cookie) context
    if pk.startswith('SESSION#'):
        session_hash = pk.replace('SESSION#', '')
        return {
            'service': 'dashborion',
            'purpose': 'web_session',
            'session_hash': session_hash[:16],
        }

    return None


def _decrypt_item_if_needed(item: dict, kms_client) -> tuple[dict, bool]:
    """
    Decrypt encrypted_data field in item if present.

    Returns (modified_item, was_decrypted)
    """
    if 'encrypted_data' not in item:
        return item, False

    context = _get_encryption_context(item)
    if not context:
        return item, False

    try:
        decrypted = _decrypt_kms_data(kms_client, item['encrypted_data'], context)

        # Merge decrypted data into item and remove encrypted_data
        new_item = {k: v for k, v in item.items() if k != 'encrypted_data'}
        new_item['_decrypted'] = True  # Mark as decrypted for restore
        new_item.update(decrypted)

        return new_item, True
    except Exception as e:
        # If decryption fails, keep original item
        click.echo(f"\n    Warning: Could not decrypt item {item.get('pk', '?')}: {e}", err=True)
        return item, False


def _encrypt_item_if_needed(item: dict, kms_client, key_arn: str) -> dict:
    """
    Re-encrypt item if it was previously decrypted.

    Returns modified item with encrypted_data field.
    """
    if not item.get('_decrypted'):
        return item

    context = _get_encryption_context(item)
    if not context:
        return item

    # Fields to encrypt based on item type
    pk = item.get('pk', '')

    if pk.startswith('TOKEN#'):
        sensitive_fields = ['email', 'user_id', 'permissions', 'scope']
    elif pk.startswith('REFRESH#'):
        sensitive_fields = ['email', 'permissions', 'token_hash']
    elif pk.startswith('SESSION#'):
        sensitive_fields = ['userId', 'email', 'displayName', 'groups', 'mfaVerified', 'sessionId', 'issuedAt']
    else:
        return item

    # Extract sensitive data
    sensitive_data = {k: item[k] for k in sensitive_fields if k in item}

    if not sensitive_data:
        return item

    try:
        encrypted = _encrypt_kms_data(kms_client, sensitive_data, key_arn, context)

        # Build new item without sensitive fields
        new_item = {k: v for k, v in item.items()
                    if k not in sensitive_fields and k != '_decrypted'}
        new_item['encrypted_data'] = encrypted

        # Update sk for encrypted format
        if pk.startswith('TOKEN#') or pk.startswith('REFRESH#') or pk.startswith('SESSION#'):
            new_item['sk'] = 'SESSION'  # Don't leak info in sk

        return new_item
    except Exception as e:
        click.echo(f"\n    Warning: Could not encrypt item {item.get('pk', '?')}: {e}", err=True)
        return item


@admin.command('tables')
@click.option('--profile', '-p', help='AWS profile to use')
@click.option('--region', '-r', help='AWS region')
@click.option('--prefix', default='dashborion', help='Table name prefix filter')
def tables(profile: Optional[str], region: Optional[str], prefix: str):
    """List DynamoDB tables for Dashborion"""
    try:
        dynamodb = _get_dynamodb_client(profile, region)
        table_list = _get_dashborion_tables(dynamodb, prefix)

        if not table_list:
            click.echo(f"No tables found matching prefix '{prefix}'")
            return

        click.echo()
        click.echo(f"{'TABLE NAME':<60} {'ITEMS':<10} {'STATUS'}")
        click.echo(f"{'-'*60} {'-'*10} {'-'*10}")

        for table_name in table_list:
            try:
                desc = dynamodb.describe_table(TableName=table_name)
                item_count = desc['Table'].get('ItemCount', 0)
                status = desc['Table'].get('TableStatus', 'UNKNOWN')
                click.echo(f"{table_name:<60} {item_count:<10} {status}")
            except Exception as e:
                click.echo(f"{table_name:<60} {'ERROR':<10} {str(e)[:20]}")

        click.echo()
        click.echo(f"Total: {len(table_list)} tables")

    except Exception as e:
        raise click.ClickException(f"Failed to list tables: {e}")


@admin.command('backup')
@click.option('--profile', '-p', help='AWS profile to use')
@click.option('--region', '-r', help='AWS region')
@click.option('--prefix', default='dashborion', help='Table name prefix filter')
@click.option('--output', '-o', default='.', help='Output directory for backup files')
@click.option('--tables', '-t', multiple=True, help='Specific table names (default: all matching prefix)')
@click.option('--decrypt', is_flag=True, help='Decrypt KMS-encrypted fields (for migration)')
def backup(profile: Optional[str], region: Optional[str], prefix: str, output: str,
           tables: tuple, decrypt: bool):
    """
    Backup DynamoDB tables to JSON files

    Creates one JSON file per table in the output directory.

    Use --decrypt to export data in plaintext (for migration to another
    environment with a different KMS key).

    Examples:
        dashborion admin backup --profile my-profile --region eu-west-3

        dashborion admin backup -o ./backups

        dashborion admin backup -t dashborion-homebox-UsersTable-xxx

        dashborion admin backup --decrypt -o ./migration-backup
    """
    import os
    from datetime import datetime as dt

    try:
        dynamodb = _get_dynamodb_client(profile, region)
        kms_client = _get_kms_client(profile, region) if decrypt else None

        # Get tables to backup
        if tables:
            table_list = list(tables)
        else:
            table_list = _get_dashborion_tables(dynamodb, prefix)

        if not table_list:
            click.echo(f"No tables found matching prefix '{prefix}'")
            return

        # Create output directory with timestamp
        timestamp = dt.now().strftime('%Y%m%d_%H%M%S')
        suffix = "-decrypted" if decrypt else ""
        backup_dir = os.path.join(output, f"dashborion-backup-{timestamp}{suffix}")
        os.makedirs(backup_dir, exist_ok=True)

        mode_str = click.style(" (DECRYPTED)", fg='yellow') if decrypt else ""
        click.echo(f"Backing up {len(table_list)} tables to {backup_dir}/{mode_str}")
        click.echo()

        total_items = 0
        decrypted_count = 0
        backup_manifest = {
            'timestamp': timestamp,
            'profile': profile,
            'region': region,
            'decrypted': decrypt,
            'tables': []
        }

        for table_name in table_list:
            click.echo(f"  {table_name}...", nl=False)
            try:
                items = _scan_table(dynamodb, table_name)
                item_count = len(items)
                total_items += item_count

                # Deserialize items for readable JSON
                deserialized_items = [_deserialize_dynamodb_item(item) for item in items]

                # Decrypt if requested
                table_decrypted = 0
                if decrypt and kms_client:
                    processed_items = []
                    for item in deserialized_items:
                        decrypted_item, was_decrypted = _decrypt_item_if_needed(item, kms_client)
                        processed_items.append(decrypted_item)
                        if was_decrypted:
                            table_decrypted += 1
                    deserialized_items = processed_items
                    decrypted_count += table_decrypted

                # Save to file
                backup_file = os.path.join(backup_dir, f"{table_name}.json")
                with open(backup_file, 'w') as f:
                    json.dump({
                        'table_name': table_name,
                        'item_count': item_count,
                        'decrypted_count': table_decrypted if decrypt else 0,
                        'items': deserialized_items
                    }, f, indent=2, default=str)

                backup_manifest['tables'].append({
                    'name': table_name,
                    'items': item_count,
                    'decrypted': table_decrypted if decrypt else 0,
                    'file': f"{table_name}.json"
                })

                if decrypt and table_decrypted > 0:
                    click.echo(f" {click.style(str(item_count), fg='green')} items ({table_decrypted} decrypted)")
                else:
                    click.echo(f" {click.style(str(item_count), fg='green')} items")

            except Exception as e:
                click.echo(f" {click.style('ERROR', fg='red')}: {e}")

        # Save manifest
        manifest_file = os.path.join(backup_dir, "manifest.json")
        with open(manifest_file, 'w') as f:
            json.dump(backup_manifest, f, indent=2)

        click.echo()
        click.echo(click.style(f"Backup complete!", fg='green', bold=True))
        click.echo(f"  Directory: {backup_dir}")
        click.echo(f"  Tables: {len(table_list)}")
        click.echo(f"  Total items: {total_items}")
        if decrypt:
            click.echo(f"  Decrypted: {decrypted_count} items")

    except Exception as e:
        raise click.ClickException(f"Backup failed: {e}")


@admin.command('restore')
@click.option('--profile', '-p', help='AWS profile to use')
@click.option('--region', '-r', help='AWS region')
@click.option('--input', '-i', 'input_dir', required=True, help='Backup directory to restore from')
@click.option('--tables', '-t', multiple=True, help='Specific table files to restore (default: all)')
@click.option('--dry-run', is_flag=True, help='Show what would be restored without making changes')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
@click.option('--encrypt', is_flag=True, help='Re-encrypt decrypted items with KMS (requires --kms-key)')
@click.option('--kms-key', 'kms_key_arn', help='KMS key ARN for encryption (required with --encrypt)')
def restore(profile: Optional[str], region: Optional[str], input_dir: str,
            tables: tuple, dry_run: bool, force: bool, encrypt: bool, kms_key_arn: Optional[str]):
    """
    Restore DynamoDB tables from JSON backup files

    For decrypted backups (created with --decrypt), use --encrypt --kms-key
    to re-encrypt sensitive data with a new KMS key.

    Examples:
        dashborion admin restore -i ./dashborion-backup-20240110_120000

        dashborion admin restore -i ./backup --dry-run

        dashborion admin restore -i ./backup -t dashborion-homebox-UsersTable.json

        dashborion admin restore -i ./decrypted-backup --encrypt \\
            --kms-key arn:aws:kms:eu-west-3:123456789012:key/xxx
    """
    import os

    try:
        # Validate options
        if encrypt and not kms_key_arn:
            raise click.ClickException("--encrypt requires --kms-key to specify the target KMS key ARN")

        # Check input directory
        if not os.path.isdir(input_dir):
            raise click.ClickException(f"Directory not found: {input_dir}")

        # Read manifest if exists
        manifest_file = os.path.join(input_dir, "manifest.json")
        manifest = {}
        backup_was_decrypted = False
        if os.path.exists(manifest_file):
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
            click.echo(f"Backup from: {manifest.get('timestamp', 'unknown')}")
            click.echo(f"Original profile: {manifest.get('profile', 'unknown')}")
            click.echo(f"Original region: {manifest.get('region', 'unknown')}")
            backup_was_decrypted = manifest.get('decrypted', False)
            if backup_was_decrypted:
                click.echo(click.style("  This is a DECRYPTED backup", fg='yellow'))
            click.echo()

        # Warn if decrypted backup and not re-encrypting
        if backup_was_decrypted and not encrypt:
            click.echo(click.style("WARNING:", fg='yellow', bold=True) +
                       " This backup was decrypted. Items with _decrypted=true will be")
            click.echo("         restored in plaintext (not recommended for auth tables).")
            click.echo("         Use --encrypt --kms-key <arn> to re-encrypt.")
            click.echo()

        # Get backup files
        if tables:
            backup_files = [os.path.join(input_dir, t) for t in tables]
        else:
            backup_files = [
                os.path.join(input_dir, f)
                for f in os.listdir(input_dir)
                if f.endswith('.json') and f != 'manifest.json'
            ]

        if not backup_files:
            click.echo("No backup files found.")
            return

        # Preview restore
        mode_str = click.style(" (with encryption)", fg='cyan') if encrypt else ""
        click.echo(f"Tables to restore ({len(backup_files)}):{mode_str}")
        total_items = 0
        decrypted_items = 0
        restore_plan = []

        for backup_file in backup_files:
            if not os.path.exists(backup_file):
                click.echo(f"  {click.style('MISSING', fg='red')}: {backup_file}")
                continue

            with open(backup_file, 'r') as f:
                data = json.load(f)

            table_name = data.get('table_name', os.path.basename(backup_file).replace('.json', ''))
            item_count = data.get('item_count', len(data.get('items', [])))
            file_decrypted = data.get('decrypted_count', 0)
            total_items += item_count
            decrypted_items += file_decrypted

            if file_decrypted > 0:
                click.echo(f"  {table_name}: {item_count} items ({file_decrypted} decrypted)")
            else:
                click.echo(f"  {table_name}: {item_count} items")
            restore_plan.append({
                'file': backup_file,
                'table_name': table_name,
                'items': data.get('items', [])
            })

        click.echo()
        click.echo(f"Total items to restore: {total_items}")
        if decrypted_items > 0:
            if encrypt:
                click.echo(f"Items to encrypt: {decrypted_items}")
            else:
                click.echo(click.style(f"Decrypted items (will be plaintext): {decrypted_items}", fg='yellow'))

        if dry_run:
            click.echo()
            click.echo(click.style("DRY RUN - no changes made", fg='yellow'))
            return

        # Confirm
        if not force:
            click.echo()
            click.echo(click.style("WARNING:", fg='yellow', bold=True) +
                       " This will overwrite existing items with the same keys!")
            if not click.confirm("Proceed with restore?"):
                click.echo("Cancelled.")
                return

        # Perform restore
        dynamodb = _get_dynamodb_client(profile, region)
        kms_client = _get_kms_client(profile, region) if encrypt else None
        click.echo()
        click.echo("Restoring...")

        restored_count = 0
        encrypted_count = 0
        error_count = 0

        for plan in restore_plan:
            table_name = plan['table_name']
            items = plan['items']

            click.echo(f"  {table_name}...", nl=False)

            try:
                # Check if table exists
                dynamodb.describe_table(TableName=table_name)
            except dynamodb.exceptions.ResourceNotFoundException:
                click.echo(f" {click.style('TABLE NOT FOUND', fg='red')}")
                error_count += len(items)
                continue
            except Exception as e:
                click.echo(f" {click.style('ERROR', fg='red')}: {e}")
                error_count += len(items)
                continue

            # Restore items
            success = 0
            table_encrypted = 0
            errors = 0

            for item in items:
                try:
                    # Re-encrypt if needed
                    if encrypt and kms_client and kms_key_arn and item.get('_decrypted'):
                        item = _encrypt_item_if_needed(item, kms_client, kms_key_arn)
                        table_encrypted += 1

                    # Remove internal marker before saving
                    if '_decrypted' in item:
                        item = {k: v for k, v in item.items() if k != '_decrypted'}

                    # Serialize back to DynamoDB format
                    dynamo_item = _serialize_dynamodb_item(item)
                    dynamodb.put_item(TableName=table_name, Item=dynamo_item)
                    success += 1
                except Exception as e:
                    errors += 1
                    if errors == 1:
                        click.echo(f" Error on item: {e}", err=True)

            restored_count += success
            encrypted_count += table_encrypted
            error_count += errors

            if errors:
                click.echo(f" {click.style(str(success), fg='green')}/{len(items)} ({click.style(str(errors) + ' errors', fg='red')})")
            elif table_encrypted > 0:
                click.echo(f" {click.style(str(success), fg='green')} items ({table_encrypted} encrypted)")
            else:
                click.echo(f" {click.style(str(success), fg='green')} items")

        click.echo()
        if error_count:
            click.echo(click.style(f"Restore completed with errors", fg='yellow', bold=True))
            click.echo(f"  Restored: {restored_count}")
            if encrypted_count > 0:
                click.echo(f"  Encrypted: {encrypted_count}")
            click.echo(f"  Errors: {error_count}")
        else:
            click.echo(click.style(f"Restore complete!", fg='green', bold=True))
            click.echo(f"  Restored: {restored_count} items")
            if encrypted_count > 0:
                click.echo(f"  Encrypted: {encrypted_count} items")

    except Exception as e:
        raise click.ClickException(f"Restore failed: {e}")
