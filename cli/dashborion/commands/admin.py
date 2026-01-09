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


def _get_auth_headers() -> dict:
    """Get authorization headers for API requests"""
    token = get_valid_token()
    if not token:
        raise click.ClickException(
            "Not authenticated. Run 'dashborion auth login' first."
        )
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def _api_request(method: str, path: str, data: dict = None, params: dict = None) -> dict:
    """Make authenticated API request"""
    api_url = get_api_base_url()
    headers = _get_auth_headers()

    url = f"{api_url}{path}"

    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, json=data, timeout=30)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers, json=data, timeout=30)
        else:
            raise ValueError(f"Unknown method: {method}")

        if response.status_code == 401:
            raise click.ClickException("Unauthorized. Please re-authenticate.")
        if response.status_code == 403:
            raise click.ClickException("Permission denied. Admin privileges required.")

        return response.json()

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
