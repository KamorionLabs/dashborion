"""
Context Management for Dashborion CLI

Supports multiple Dashborion instances (clients/projects) with:
- Named contexts with API URLs and credentials
- Current context tracking
- Easy switching between contexts

Similar to kubectl contexts or AWS profiles.
"""

import click
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


def get_contexts_path() -> Path:
    """Get path to contexts configuration file"""
    return Path.home() / '.dashborion' / 'contexts.json'


def get_credentials_dir() -> Path:
    """Get path to credentials directory"""
    return Path.home() / '.dashborion' / 'credentials'


def load_contexts() -> Dict[str, Any]:
    """Load contexts configuration"""
    contexts_path = get_contexts_path()
    if not contexts_path.exists():
        return {
            'current': None,
            'contexts': {}
        }

    try:
        with open(contexts_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {
            'current': None,
            'contexts': {}
        }


def save_contexts(data: Dict[str, Any]) -> None:
    """Save contexts configuration"""
    contexts_path = get_contexts_path()
    contexts_path.parent.mkdir(parents=True, exist_ok=True)

    with open(contexts_path, 'w') as f:
        json.dump(data, f, indent=2)

    # Set restrictive permissions
    try:
        os.chmod(contexts_path, 0o600)
    except (OSError, AttributeError):
        pass


def get_current_context() -> Optional[Dict[str, Any]]:
    """Get the current active context"""
    data = load_contexts()
    current_name = data.get('current')

    if not current_name:
        return None

    context = data.get('contexts', {}).get(current_name)
    if context:
        context['name'] = current_name

    return context


def get_current_project() -> Optional[str]:
    """Get the current project from the active context"""
    ctx = get_current_context()
    if ctx:
        return ctx.get('current_project')
    return None


def get_current_environment() -> Optional[str]:
    """Get the current environment from the active context"""
    ctx = get_current_context()
    if ctx:
        return ctx.get('current_environment')
    return None


def set_current_project(project: str) -> None:
    """Set the current project in the active context"""
    data = load_contexts()
    current_name = data.get('current')

    if not current_name:
        raise ValueError("No current context set")

    if current_name not in data.get('contexts', {}):
        raise ValueError(f"Context '{current_name}' not found")

    data['contexts'][current_name]['current_project'] = project
    save_contexts(data)


def set_current_environment(environment: str) -> None:
    """Set the current environment in the active context"""
    data = load_contexts()
    current_name = data.get('current')

    if not current_name:
        raise ValueError("No current context set")

    if current_name not in data.get('contexts', {}):
        raise ValueError(f"Context '{current_name}' not found")

    data['contexts'][current_name]['current_environment'] = environment
    save_contexts(data)


def get_current_orchestrator() -> Optional[str]:
    """Get the orchestrator type for the current project (ecs, eks, etc.)"""
    ctx = get_current_context()
    if ctx:
        return ctx.get('orchestrator')
    return None


def set_current_orchestrator(orchestrator: str) -> None:
    """Set the orchestrator type for the current project"""
    data = load_contexts()
    current_name = data.get('current')

    if not current_name:
        raise ValueError("No current context set")

    if current_name not in data.get('contexts', {}):
        raise ValueError(f"Context '{current_name}' not found")

    data['contexts'][current_name]['orchestrator'] = orchestrator
    save_contexts(data)


def is_eks_project() -> bool:
    """Check if current project uses EKS/Kubernetes"""
    orch = get_current_orchestrator()
    return orch in ('eks', 'kubernetes', 'k8s')


def is_ecs_project() -> bool:
    """Check if current project uses ECS"""
    orch = get_current_orchestrator()
    return orch in ('ecs', 'fargate')


def get_context(name: str) -> Optional[Dict[str, Any]]:
    """Get a specific context by name"""
    data = load_contexts()
    context = data.get('contexts', {}).get(name)
    if context:
        context['name'] = name
    return context


def get_context_credentials(context_name: str) -> Optional[Dict[str, Any]]:
    """Get credentials for a specific context"""
    creds_path = get_credentials_dir() / f"{context_name}.json"

    if not creds_path.exists():
        return None

    try:
        with open(creds_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_context_credentials(context_name: str, credentials: Dict[str, Any]) -> None:
    """Save credentials for a specific context"""
    creds_dir = get_credentials_dir()
    creds_dir.mkdir(parents=True, exist_ok=True)

    creds_path = creds_dir / f"{context_name}.json"

    with open(creds_path, 'w') as f:
        json.dump(credentials, f, indent=2)

    # Set restrictive permissions
    try:
        os.chmod(creds_path, 0o600)
    except (OSError, AttributeError):
        pass


def delete_context_credentials(context_name: str) -> bool:
    """Delete credentials for a specific context"""
    creds_path = get_credentials_dir() / f"{context_name}.json"

    if creds_path.exists():
        creds_path.unlink()
        return True
    return False


@click.group()
def context():
    """Manage Dashborion contexts (multiple clients/instances)"""
    pass


@context.command('list')
@click.option('--output', '-o', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
def list_contexts(output: str):
    """
    List all configured contexts

    Shows all Dashborion instances you have configured, with the current
    context marked with an asterisk (*).

    \b
    Examples:
      dashborion context list
      dashborion context list -o json
    """
    data = load_contexts()
    current = data.get('current')
    contexts = data.get('contexts', {})

    if not contexts:
        click.echo("No contexts configured.")
        click.echo()
        click.echo("Add a context with:")
        click.echo("  dashborion context add <name> --api-url <url>")
        return

    if output == 'json':
        result = {
            'current': current,
            'contexts': [
                {
                    'name': name,
                    'current': name == current,
                    **ctx
                }
                for name, ctx in contexts.items()
            ]
        }
        click.echo(json.dumps(result, indent=2))
        return

    # Table output
    click.echo()
    click.echo(f"{'':2} {'NAME':<20} {'API URL':<45} {'DESCRIPTION'}")
    click.echo(f"{'':2} {'-'*20} {'-'*45} {'-'*30}")

    for name, ctx in sorted(contexts.items()):
        marker = '*' if name == current else ' '
        api_url = ctx.get('api_url', '')[:43]
        description = ctx.get('description', '')[:30]
        click.echo(f"{marker:2} {name:<20} {api_url:<45} {description}")

    click.echo()


@context.command('current')
def current_context():
    """
    Show the current context

    Displays information about the currently active Dashborion context,
    including the selected project and environment.
    """
    ctx = get_current_context()

    if not ctx:
        click.echo("No current context set.")
        click.echo()
        click.echo("Set a context with:")
        click.echo("  dashborion context use <name>")
        sys.exit(1)

    click.echo(f"Current context: {click.style(ctx['name'], bold=True, fg='green')}")
    click.echo(f"API URL: {ctx.get('api_url', 'not set')}")

    if ctx.get('description'):
        click.echo(f"Description: {ctx['description']}")

    # Show current project, orchestrator, and environment
    current_proj = ctx.get('current_project')
    current_env = ctx.get('current_environment')
    orchestrator = ctx.get('orchestrator')

    if current_proj:
        click.echo(f"Project: {click.style(current_proj, fg='cyan')}")
        if orchestrator:
            click.echo(f"Orchestrator: {click.style(orchestrator, fg='cyan')}")
    else:
        click.echo(f"Project: {click.style('not set', fg='yellow')} (use 'dashborion project use <name>')")

    if current_env:
        click.echo(f"Environment: {click.style(current_env, fg='cyan')}")
    else:
        click.echo(f"Environment: {click.style('not set', fg='yellow')} (use 'dashborion env use <name>')")

    # Check credentials
    creds = get_context_credentials(ctx['name'])
    if creds:
        import time
        expires_at = creds.get('expires_at', 0)
        if expires_at > time.time():
            remaining = expires_at - time.time()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            click.echo(f"Auth status: {click.style('authenticated', fg='green')} ({hours}h {minutes}m remaining)")
        else:
            click.echo(f"Auth status: {click.style('expired', fg='yellow')}")
    else:
        click.echo(f"Auth status: {click.style('not authenticated', fg='red')}")


@context.command('use')
@click.argument('name')
def use_context(name: str):
    """
    Switch to a different context

    Sets the specified context as the current active context.
    All subsequent commands will use this context's configuration.

    \b
    Examples:
      dashborion context use production
      dashborion context use client-a
    """
    data = load_contexts()
    contexts = data.get('contexts', {})

    if name not in contexts:
        click.echo(f"Error: Context '{name}' not found.", err=True)
        click.echo()
        click.echo("Available contexts:")
        for ctx_name in sorted(contexts.keys()):
            click.echo(f"  - {ctx_name}")
        sys.exit(1)

    data['current'] = name
    save_contexts(data)

    ctx = contexts[name]
    click.echo(f"Switched to context: {click.style(name, bold=True, fg='green')}")
    click.echo(f"API URL: {ctx.get('api_url', 'not set')}")


@context.command('add')
@click.argument('name')
@click.option('--api-url', required=True,
              help='API URL for this context (e.g., https://api.dashboard.example.com)')
@click.option('--description', '-d',
              help='Optional description for this context')
@click.option('--set-current', is_flag=True,
              help='Set as current context after adding')
def add_context(name: str, api_url: str, description: Optional[str], set_current: bool):
    """
    Add a new context

    Creates a new named context pointing to a Dashborion API instance.

    \b
    Examples:
      dashborion context add production --api-url https://api.prod.example.com
      dashborion context add staging --api-url https://api.staging.example.com -d "Staging environment"
      dashborion context add client-a --api-url https://dashboard-api.client-a.com --set-current
    """
    data = load_contexts()

    if name in data.get('contexts', {}):
        click.echo(f"Error: Context '{name}' already exists.", err=True)
        click.echo("Use 'dashborion context update' to modify it.")
        sys.exit(1)

    # Normalize URL
    api_url = api_url.rstrip('/')

    # Add context
    if 'contexts' not in data:
        data['contexts'] = {}

    data['contexts'][name] = {
        'api_url': api_url,
        'description': description or '',
        'created_at': datetime.utcnow().isoformat(),
    }

    # Set as current if requested or if first context
    if set_current or not data.get('current'):
        data['current'] = name

    save_contexts(data)

    click.echo(f"Added context: {click.style(name, bold=True, fg='green')}")
    click.echo(f"API URL: {api_url}")

    if data['current'] == name:
        click.echo(f"Set as current context.")
    else:
        click.echo()
        click.echo(f"To use this context:")
        click.echo(f"  dashborion context use {name}")


@context.command('update')
@click.argument('name')
@click.option('--api-url',
              help='New API URL')
@click.option('--description', '-d',
              help='New description')
def update_context(name: str, api_url: Optional[str], description: Optional[str]):
    """
    Update an existing context

    Modifies the configuration of an existing context.

    \b
    Examples:
      dashborion context update production --api-url https://new-api.example.com
      dashborion context update staging -d "New staging environment"
    """
    data = load_contexts()

    if name not in data.get('contexts', {}):
        click.echo(f"Error: Context '{name}' not found.", err=True)
        sys.exit(1)

    if not api_url and not description:
        click.echo("Error: Provide at least one option to update (--api-url or --description)", err=True)
        sys.exit(1)

    if api_url:
        data['contexts'][name]['api_url'] = api_url.rstrip('/')

    if description is not None:
        data['contexts'][name]['description'] = description

    data['contexts'][name]['updated_at'] = datetime.utcnow().isoformat()

    save_contexts(data)

    click.echo(f"Updated context: {click.style(name, bold=True)}")


@context.command('remove')
@click.argument('name')
@click.option('--force', '-f', is_flag=True,
              help='Force removal without confirmation')
def remove_context(name: str, force: bool):
    """
    Remove a context

    Deletes a context and its associated credentials.

    \b
    Examples:
      dashborion context remove old-client
      dashborion context remove staging -f
    """
    data = load_contexts()

    if name not in data.get('contexts', {}):
        click.echo(f"Error: Context '{name}' not found.", err=True)
        sys.exit(1)

    if not force:
        if not click.confirm(f"Remove context '{name}' and its credentials?"):
            click.echo("Cancelled.")
            return

    # Remove context
    del data['contexts'][name]

    # Clear current if this was the current context
    if data.get('current') == name:
        data['current'] = None
        # Set to first available context
        if data['contexts']:
            data['current'] = next(iter(data['contexts'].keys()))

    save_contexts(data)

    # Remove credentials
    delete_context_credentials(name)

    click.echo(f"Removed context: {name}")

    if data.get('current'):
        click.echo(f"Current context is now: {data['current']}")


@context.command('rename')
@click.argument('old_name')
@click.argument('new_name')
def rename_context(old_name: str, new_name: str):
    """
    Rename a context

    Changes the name of an existing context.

    \b
    Examples:
      dashborion context rename prod production
    """
    data = load_contexts()

    if old_name not in data.get('contexts', {}):
        click.echo(f"Error: Context '{old_name}' not found.", err=True)
        sys.exit(1)

    if new_name in data.get('contexts', {}):
        click.echo(f"Error: Context '{new_name}' already exists.", err=True)
        sys.exit(1)

    # Rename context
    data['contexts'][new_name] = data['contexts'].pop(old_name)

    # Update current if needed
    if data.get('current') == old_name:
        data['current'] = new_name

    save_contexts(data)

    # Rename credentials file if exists
    old_creds = get_credentials_dir() / f"{old_name}.json"
    new_creds = get_credentials_dir() / f"{new_name}.json"

    if old_creds.exists():
        old_creds.rename(new_creds)

    click.echo(f"Renamed context: {old_name} -> {click.style(new_name, bold=True)}")
