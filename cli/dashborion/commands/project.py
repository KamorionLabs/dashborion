"""
Project Management for Dashborion CLI

List and select projects from the current Dashborion context.
The selected project is persisted in the context configuration.
"""

import click
import sys
from typing import Optional

from dashborion.commands.context import (
    get_current_context,
    get_current_project,
    set_current_project,
    get_context_credentials,
    set_current_orchestrator,
    get_current_orchestrator
)
from dashborion.utils.api_client import get_api_client


@click.group()
def project():
    """Manage projects (list and select)"""
    pass


def _check_auth():
    """Check if user is authenticated"""
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

    return ctx


@project.command('list')
@click.option('--output', '-o', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
def list_projects(output: str):
    """
    List available projects

    Fetches the list of projects from the Dashborion API.
    The current project is marked with an asterisk (*).

    \b
    Examples:
      dashborion project list
      dashborion project list -o json
    """
    _check_auth()

    try:
        client = get_api_client()
        response = client.get('/api/projects')
        response.raise_for_status()
        data = response.json()

        projects = data.get('projects', [])
        current = get_current_project()

        if not projects:
            click.echo("No projects found.")
            return

        if output == 'json':
            import json
            result = {
                'current': current,
                'projects': projects
            }
            click.echo(json.dumps(result, indent=2))
            return

        # Table output
        click.echo()
        click.echo(f"{'':2} {'NAME':<25} {'DESCRIPTION':<40} {'ENVIRONMENTS'}")
        click.echo(f"{'':2} {'-'*25} {'-'*40} {'-'*20}")

        for proj in projects:
            name = proj if isinstance(proj, str) else proj.get('name', '')
            description = '' if isinstance(proj, str) else proj.get('description', '')[:38]
            envs = '' if isinstance(proj, str) else ', '.join(proj.get('environments', []))[:18]

            marker = '*' if name == current else ' '
            click.echo(f"{marker:2} {name:<25} {description:<40} {envs}")

        click.echo()

    except Exception as e:
        click.echo(f"Error fetching projects: {e}", err=True)
        sys.exit(1)


@project.command('use')
@click.argument('name')
def use_project(name: str):
    """
    Select a project

    Sets the specified project as the current project for this context.
    All subsequent commands will use this project.

    \b
    Examples:
      dashborion project use homebox
      dashborion project use rubix
    """
    ctx = _check_auth()

    try:
        # Verify project exists
        client = get_api_client()
        response = client.get('/api/projects')
        response.raise_for_status()
        data = response.json()

        projects = data.get('projects', [])
        project_names = [p if isinstance(p, str) else p.get('name', '') for p in projects]

        if name not in project_names:
            click.echo(f"Error: Project '{name}' not found.", err=True)
            click.echo()
            click.echo("Available projects:")
            for p in project_names:
                click.echo(f"  - {p}")
            sys.exit(1)

        # Set current project
        set_current_project(name)

        # Get and store orchestrator type
        proj_data = next((p for p in projects if (p if isinstance(p, str) else p.get('name')) == name), None)
        orchestrator = 'unknown'
        if proj_data and not isinstance(proj_data, str):
            orchestrator = proj_data.get('orchestrator', 'unknown')
            set_current_orchestrator(orchestrator)

        click.echo(f"Switched to project: {click.style(name, bold=True, fg='green')}")
        click.echo(f"Orchestrator: {click.style(orchestrator, fg='cyan')}")

        # Show available environments for this project
        if proj_data and not isinstance(proj_data, str):
            envs = proj_data.get('environments', [])
            if envs:
                click.echo(f"Available environments: {', '.join(envs)}")
                click.echo()
                click.echo("Select an environment with:")
                click.echo(f"  dashborion env use <name>")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@project.command('current')
def current_project():
    """
    Show the current project

    Displays the currently selected project for this context.
    """
    ctx = get_current_context()

    if not ctx:
        click.echo("No context set. Use 'dashborion context use <name>'", err=True)
        sys.exit(1)

    current = get_current_project()
    orchestrator = get_current_orchestrator()

    if current:
        click.echo(f"Current project: {click.style(current, bold=True, fg='green')}")
        if orchestrator:
            click.echo(f"Orchestrator: {click.style(orchestrator, fg='cyan')}")
    else:
        click.echo("No project selected.")
        click.echo()
        click.echo("Select a project with:")
        click.echo("  dashborion project list")
        click.echo("  dashborion project use <name>")
