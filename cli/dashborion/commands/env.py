"""
Environment Management for Dashborion CLI

List and select environments from the current project.
The selected environment is persisted in the context configuration.
"""

import click
import sys
from typing import Optional

from dashborion.commands.context import (
    get_current_context,
    get_current_project,
    get_current_environment,
    set_current_environment,
    get_context_credentials
)
from dashborion.utils.api_client import get_api_client


@click.group()
def env():
    """Manage environments (list and select)"""
    pass


def _check_auth_and_project():
    """Check if user is authenticated and has a project selected"""
    ctx = get_current_context()
    if not ctx:
        click.echo("No context set. Use 'dashborion context use <name>'", err=True)
        sys.exit(1)

    creds = get_context_credentials(ctx['name'])
    if not creds:
        click.echo("Not authenticated. Use 'dashborion auth login'", err=True)
        sys.exit(1)

    import time
    if creds.get('expires_at', 0) < time.time():
        click.echo("Token expired. Use 'dashborion auth login'", err=True)
        sys.exit(1)

    project = get_current_project()
    if not project:
        click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
        sys.exit(1)

    return ctx, project


@env.command('list')
@click.option('--output', '-o', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
@click.option('--project', '-p', help='Project name (default: current project)')
def list_environments(output: str, project: Optional[str]):
    """
    List available environments

    Fetches the list of environments for the current (or specified) project.
    The current environment is marked with an asterisk (*).

    \b
    Examples:
      dashborion env list
      dashborion env list -p homebox
      dashborion env list -o json
    """
    ctx = get_current_context()
    if not ctx:
        click.echo("No context set. Use 'dashborion context use <name>'", err=True)
        sys.exit(1)

    # Use specified project or current
    proj = project or get_current_project()
    if not proj:
        click.echo("No project selected. Use 'dashborion project use <name>' or specify with -p", err=True)
        sys.exit(1)

    try:
        client = get_api_client()
        response = client.get(f'/api/{proj}/environments')
        response.raise_for_status()
        data = response.json()

        environments = data.get('environments', [])
        current = get_current_environment()

        if not environments:
            click.echo(f"No environments found for project '{proj}'.")
            return

        if output == 'json':
            import json
            result = {
                'project': proj,
                'current': current,
                'environments': environments
            }
            click.echo(json.dumps(result, indent=2))
            return

        # Table output
        click.echo()
        click.echo(f"Environments for project: {click.style(proj, bold=True)}")
        click.echo()
        click.echo(f"{'':2} {'NAME':<20} {'TYPE':<10} {'STATUS':<12} {'DESCRIPTION'}")
        click.echo(f"{'':2} {'-'*20} {'-'*10} {'-'*12} {'-'*30}")

        for env_item in environments:
            if isinstance(env_item, str):
                name = env_item
                env_type = '-'
                status = '-'
                description = ''
            else:
                name = env_item.get('name', '')
                env_type = env_item.get('type', '-')
                status = env_item.get('status', '-')
                description = env_item.get('description', '')[:28]

            marker = '*' if name == current else ' '
            click.echo(f"{marker:2} {name:<20} {env_type:<10} {status:<12} {description}")

        click.echo()

    except Exception as e:
        click.echo(f"Error fetching environments: {e}", err=True)
        sys.exit(1)


@env.command('use')
@click.argument('name')
@click.option('--project', '-p', help='Project name (default: current project)')
def use_environment(name: str, project: Optional[str]):
    """
    Select an environment

    Sets the specified environment as the current environment for this context.
    All subsequent commands will use this environment by default.

    \b
    Examples:
      dashborion env use staging
      dashborion env use production
    """
    ctx = get_current_context()
    if not ctx:
        click.echo("No context set. Use 'dashborion context use <name>'", err=True)
        sys.exit(1)

    proj = project or get_current_project()
    if not proj:
        click.echo("No project selected. Use 'dashborion project use <name>' first", err=True)
        sys.exit(1)

    try:
        # Verify environment exists
        client = get_api_client()
        response = client.get(f'/api/{proj}/environments')
        response.raise_for_status()
        data = response.json()

        environments = data.get('environments', [])
        env_names = [e if isinstance(e, str) else e.get('name', '') for e in environments]

        if name not in env_names:
            click.echo(f"Error: Environment '{name}' not found in project '{proj}'.", err=True)
            click.echo()
            click.echo("Available environments:")
            for e in env_names:
                click.echo(f"  - {e}")
            sys.exit(1)

        # Set current environment
        set_current_environment(name)

        click.echo(f"Switched to environment: {click.style(name, bold=True, fg='green')}")
        click.echo(f"Project: {proj}")
        click.echo()
        click.echo("You can now run commands without specifying -e:")
        click.echo("  dashborion services list")
        click.echo("  dashborion k8s pods")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@env.command('current')
def current_environment():
    """
    Show the current environment

    Displays the currently selected environment for this context.
    """
    ctx = get_current_context()

    if not ctx:
        click.echo("No context set. Use 'dashborion context use <name>'", err=True)
        sys.exit(1)

    project = get_current_project()
    current = get_current_environment()

    if project:
        click.echo(f"Current project: {click.style(project, fg='cyan')}")
    else:
        click.echo("No project selected.")

    if current:
        click.echo(f"Current environment: {click.style(current, bold=True, fg='green')}")
    else:
        click.echo("No environment selected.")
        click.echo()
        click.echo("Select an environment with:")
        click.echo("  dashborion env list")
        click.echo("  dashborion env use <name>")
