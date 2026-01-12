"""Diagram command group for Dashborion CLI - API-based implementation"""

import click
import sys
import base64
from pathlib import Path
from typing import Optional

from dashborion.utils.output import OutputFormatter


@click.group()
def diagram():
    """Generate and publish architecture diagrams"""
    pass


def _get_collector(ctx, env: Optional[str] = None):
    """Get API collector configured for the environment."""
    from dashborion.collectors.api import APICollector
    from dashborion.utils.api_client import get_api_client
    from dashborion.config.cli_config import get_environment_config

    # Use provided env or fall back to context env
    effective_env = env or ctx.env
    env_config = get_environment_config(ctx.config or {}, effective_env) if effective_env else {}

    # Get project from context
    project = ctx.project
    if not project:
        click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
        sys.exit(1)

    client = get_api_client()
    return APICollector(client, project), env_config, effective_env


@diagram.command('generate')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--output', '-o', default='architecture', help='Output filename (without extension)')
@click.option('--format', '-f', 'output_format', type=click.Choice(['png', 'svg', 'pdf']),
              default='png', help='Output format')
@click.option('--namespaces', '-n', multiple=True, help='Kubernetes namespaces to include')
@click.option('--include-rds', is_flag=True, help='Include RDS databases')
@click.option('--include-elasticache', is_flag=True, help='Include ElastiCache clusters')
@click.option('--include-cloudfront', is_flag=True, help='Include CloudFront distributions')
@click.pass_obj
def generate_diagram(ctx, env: Optional[str], output: str, output_format: str, namespaces: tuple,
                     include_rds: bool, include_elasticache: bool, include_cloudfront: bool):
    """Generate architecture diagram from infrastructure via API"""

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        click.echo(f"Generating diagram for environment: {effective_env}")

        result = collector.generate_diagram(
            env=effective_env,
            output_format=output_format,
            namespaces=list(namespaces) if namespaces else ['default'],
            include_rds=include_rds,
            include_elasticache=include_elasticache,
            include_cloudfront=include_cloudfront
        )

        if result.get('error'):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        # Save the diagram to file
        output_file = f"{output}.{output_format}"
        diagram_data = result.get('data')

        if diagram_data:
            # Decode base64 and write to file
            decoded_data = base64.b64decode(diagram_data)
            with open(output_file, 'wb') as f:
                f.write(decoded_data)
            click.echo(f"Diagram generated: {output_file}")
        else:
            click.echo("No diagram data received from API", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error generating diagram: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@diagram.command('publish')
@click.option('--env', '-e', help='Environment name')
@click.option('--file', '-f', 'diagram_file', type=click.Path(exists=True),
              help='Diagram file to publish')
@click.option('--confluence-page', required=True, help='Confluence page ID')
@click.option('--title', '-t', help='Page title (default: from filename)')
@click.option('--space', '-s', help='Confluence space key (overrides config)')
@click.pass_obj
def publish_diagram(ctx, env: Optional[str], diagram_file: Optional[str],
                    confluence_page: str, title: Optional[str], space: Optional[str]):
    """Publish diagram to Confluence via API"""

    try:
        # Determine file to publish
        if diagram_file:
            file_path = Path(diagram_file)
        elif env:
            # Look for recently generated diagram
            file_path = Path(f"{env}-architecture.png")
            if not file_path.exists():
                file_path = Path("architecture.png")
        else:
            click.echo("Please specify --file or --env", err=True)
            sys.exit(1)

        if not file_path.exists():
            click.echo(f"Diagram file not found: {file_path}", err=True)
            sys.exit(1)

        collector, env_config, effective_env = _get_collector(ctx, env)

        # Read file and encode to base64
        with open(file_path, 'rb') as f:
            diagram_data = base64.b64encode(f.read()).decode('utf-8')

        file_format = file_path.suffix.lstrip('.') or 'png'
        page_title = title or f"Architecture - {file_path.stem}"

        click.echo(f"Publishing {file_path} to Confluence page {confluence_page}...")

        result = collector.publish_diagram(
            diagram_data=diagram_data,
            file_format=file_format,
            confluence_page=confluence_page,
            title=page_title,
            space=space
        )

        if result.get('error'):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        if result.get('success'):
            click.echo(f"Diagram published to Confluence page {confluence_page}")
        else:
            click.echo("Publish failed with unknown error", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error publishing diagram: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@diagram.command('list-templates')
@click.pass_obj
def list_templates(ctx):
    """List available diagram templates"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, _, _ = _get_collector(ctx)
        templates = collector.list_diagram_templates()

        if isinstance(templates, dict) and templates.get('error'):
            click.echo(f"Error: {templates.get('error')}", err=True)
            sys.exit(1)

        formatter.output(templates, title="Available Diagram Templates")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
