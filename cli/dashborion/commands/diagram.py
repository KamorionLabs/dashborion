"""Diagram command group for Dashborion CLI"""

import click
import sys
from pathlib import Path
from typing import Optional

from dashborion.utils.output import OutputFormatter


@click.group()
def diagram():
    """Generate and publish architecture diagrams"""
    pass


@diagram.command('generate')
@click.option('--env', '-e', help='Environment name (uses config)')
@click.option('--config', '-c', 'yaml_config', type=click.Path(exists=True),
              help='YAML config file for diagram generation')
@click.option('--output', '-o', default='architecture', help='Output filename (without extension)')
@click.option('--format', '-f', 'output_format', type=click.Choice(['png', 'svg', 'pdf']),
              default='png', help='Output format')
@click.option('--context', help='Kubernetes context (for EKS)')
@click.option('--namespaces', '-n', multiple=True, help='Kubernetes namespaces to include')
@click.option('--include-rds', is_flag=True, help='Include RDS databases')
@click.option('--include-elasticache', is_flag=True, help='Include ElastiCache clusters')
@click.option('--include-cloudfront', is_flag=True, help='Include CloudFront distributions')
@click.pass_obj
def generate_diagram(ctx, env: Optional[str], yaml_config: Optional[str], output: str,
                     output_format: str, context: Optional[str], namespaces: tuple,
                     include_rds: bool, include_elasticache: bool, include_cloudfront: bool):
    """Generate architecture diagram from infrastructure"""

    try:
        if yaml_config:
            # Generate from YAML config
            from dashborion.generators.diagram import generate_diagrams_from_yaml
            generate_diagrams_from_yaml(yaml_config)
            click.echo(f"Diagram(s) generated from {yaml_config}")

        elif env:
            # Generate from environment config
            from dashborion.config.cli_config import get_environment_config

            env_config = get_environment_config(ctx.config or {}, env)

            session = ctx.get_aws_session(
                profile=env_config.get('aws_profile'),
                region=env_config.get('aws_region')
            )

            env_type = env_config.get('type', 'ecs')

            from dashborion.generators.diagram import DiagramGenerator

            generator = DiagramGenerator(
                session=session,
                context=context or env_config.get('context'),
                namespaces=list(namespaces) or env_config.get('namespaces', ['default']),
                include_rds=include_rds,
                include_elasticache=include_elasticache,
                include_cloudfront=include_cloudfront
            )

            output_file = f"{output}.{output_format}"
            generator.generate(output_file, env_type=env_type, cluster=env_config.get('cluster'))
            click.echo(f"Diagram generated: {output_file}")

        elif context:
            # Generate from Kubernetes context directly
            from dashborion.generators.diagram import DiagramGenerator

            session = ctx.get_aws_session()

            generator = DiagramGenerator(
                session=session,
                context=context,
                namespaces=list(namespaces) or ['default'],
                include_rds=include_rds,
                include_elasticache=include_elasticache,
                include_cloudfront=include_cloudfront
            )

            output_file = f"{output}.{output_format}"
            generator.generate(output_file, env_type='eks')
            click.echo(f"Diagram generated: {output_file}")

        else:
            click.echo("Please specify --env, --config, or --context", err=True)
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
    """Publish diagram to Confluence"""

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

        # Get Confluence config
        confluence_config = ctx.config.get('confluence', {})

        confluence_url = confluence_config.get('url')
        confluence_space = space or confluence_config.get('space_key')

        if not confluence_url:
            click.echo("Confluence URL not configured. Set in config file or CONFLUENCE_URL env var", err=True)
            sys.exit(1)

        from dashborion.publishers.confluence import ConfluencePublisher

        publisher = ConfluencePublisher.from_env_or_config(
            config=confluence_config
        )

        page_title = title or f"Architecture - {file_path.stem}"

        publisher.publish_diagram(
            file_path=str(file_path),
            title=page_title,
            parent_page_id=confluence_page,
            space_key=confluence_space
        )

        click.echo(f"Diagram published to Confluence page {confluence_page}")

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

    templates = [
        {
            'name': 'ecs-basic',
            'description': 'Basic ECS cluster with ALB and RDS',
            'resources': 'ECS, ALB, RDS'
        },
        {
            'name': 'eks-full',
            'description': 'Full EKS cluster with ingress and services',
            'resources': 'EKS, Ingress, Services, RDS'
        },
        {
            'name': 'multi-region',
            'description': 'Multi-region architecture with CloudFront',
            'resources': 'CloudFront, ALB, ECS/EKS, RDS, ElastiCache'
        },
        {
            'name': 'serverless',
            'description': 'Serverless architecture with Lambda',
            'resources': 'API Gateway, Lambda, DynamoDB, S3'
        }
    ]

    formatter.output(templates, title="Available Diagram Templates")
