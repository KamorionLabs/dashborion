"""Pipelines command group for Dashborion CLI - API-based implementation"""

import click
import sys
from typing import Optional

from dashborion.utils.output import OutputFormatter, format_status, format_datetime


@click.group()
def pipelines():
    """View CI/CD pipelines (CodePipeline, ArgoCD, Jenkins, GitLab, Bitbucket)"""
    pass


def _get_collector(ctx, env: Optional[str] = None):
    """Get API collector configured for the environment."""
    from dashborion.collectors.api import APICollector
    from dashborion.utils.api_client import get_api_client
    from dashborion.config.cli_config import get_environment_config

    # Use provided env or fall back to context env (env is optional for pipelines)
    effective_env = env or ctx.env
    env_config = get_environment_config(ctx.config or {}, effective_env) if effective_env else {}

    # Get project from context
    project = ctx.project
    if not project:
        click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
        sys.exit(1)

    client = get_api_client()
    return APICollector(client, project), env_config, effective_env


@pipelines.command('list')
@click.option('--env', '-e', help='Environment name')
@click.option('--provider', '-p', type=click.Choice(['codepipeline', 'argocd', 'jenkins', 'gitlab', 'bitbucket']),
              help='CI/CD provider (default: from config)')
@click.option('--type', 'pipeline_type', type=click.Choice(['build', 'deploy', 'all']),
              default='all', help='Pipeline type filter')
@click.pass_obj
def list_pipelines(ctx, env: Optional[str], provider: Optional[str], pipeline_type: str):
    """List pipelines"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        # Determine provider from config if not specified
        ci_config = (ctx.config or {}).get('ci_provider', {})
        provider_type = provider or ci_config.get('type', 'codepipeline')

        pipelines_data = collector.list_pipelines(
            env=effective_env,
            provider=provider_type,
            pipeline_type=pipeline_type if pipeline_type != 'all' else None
        )

        if ctx.output_format == 'table':
            table_data = []
            for pipeline in pipelines_data:
                table_data.append({
                    'name': pipeline.get('name', ''),
                    'status': format_status(pipeline.get('status', 'unknown')),
                    'last_run': format_datetime(pipeline.get('lastRun')),
                    'type': pipeline.get('type', '-'),
                })
            formatter.output(table_data, title="Pipelines")
        else:
            formatter.output(pipelines_data)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines.command('status')
@click.argument('pipeline')
@click.option('--env', '-e', help='Environment name')
@click.option('--provider', '-p', type=click.Choice(['codepipeline', 'argocd', 'jenkins', 'gitlab', 'bitbucket']),
              help='CI/CD provider')
@click.pass_obj
def pipeline_status(ctx, pipeline: str, env: Optional[str], provider: Optional[str]):
    """Show pipeline status and history"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        ci_config = (ctx.config or {}).get('ci_provider', {})
        provider_type = provider or ci_config.get('type', 'codepipeline')

        status_data = collector.get_pipeline_status(
            env=effective_env,
            pipeline_name=pipeline,
            provider=provider_type
        )

        formatter.output(status_data, title=f"Pipeline: {pipeline}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines.command('logs')
@click.argument('pipeline')
@click.option('--env', '-e', help='Environment name')
@click.option('--execution', help='Execution ID')
@click.option('--tail', '-n', default=100, help='Number of log lines')
@click.pass_obj
def pipeline_logs(ctx, pipeline: str, env: Optional[str], execution: Optional[str], tail: int):
    """View pipeline execution logs"""
    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        logs = collector.get_pipeline_logs(
            env=effective_env,
            pipeline_name=pipeline,
            execution_id=execution,
            tail=tail
        )

        # Logs come as a string or list from the API
        if isinstance(logs, str):
            click.echo(logs)
        elif isinstance(logs, list):
            for line in logs:
                click.echo(line)
        elif isinstance(logs, dict) and 'logs' in logs:
            for line in logs['logs']:
                click.echo(line)
        else:
            click.echo(logs)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines.command('trigger')
@click.argument('pipeline')
@click.option('--env', '-e', help='Environment name')
@click.option('--provider', '-p', type=click.Choice(['codepipeline', 'argocd', 'jenkins', 'gitlab', 'bitbucket']),
              help='CI/CD provider')
@click.option('--wait', '-w', is_flag=True, help='Wait for completion')
@click.pass_obj
def trigger_pipeline(ctx, pipeline: str, env: Optional[str], provider: Optional[str], wait: bool):
    """Trigger a pipeline execution"""
    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        ci_config = (ctx.config or {}).get('ci_provider', {})
        provider_type = provider or ci_config.get('type', 'codepipeline')

        click.echo(f"Triggering pipeline: {pipeline}")
        result = collector.trigger_pipeline(
            env=effective_env,
            pipeline_name=pipeline,
            provider=provider_type,
            wait=wait
        )

        if result.get('success'):
            execution_id = result.get('executionId') or result.get('execution_id')
            if execution_id:
                click.echo(f"Execution started: {execution_id}")
            else:
                click.echo("Pipeline triggered successfully")

            if wait and result.get('finalStatus'):
                click.echo(f"Final status: {result.get('finalStatus')}")
        else:
            click.echo(f"Failed to trigger: {result.get('error')}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines.command('images')
@click.argument('service')
@click.option('--env', '-e', help='Environment name')
@click.option('--limit', '-n', default=10, help='Number of images to show')
@click.pass_obj
def list_images(ctx, service: str, env: Optional[str], limit: int):
    """List ECR images for a service"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        images = collector.list_ecr_images(
            env=effective_env,
            service=service,
            limit=limit
        )

        if ctx.output_format == 'table':
            table_data = []
            for img in images:
                table_data.append({
                    'tags': ', '.join(img.get('tags', ['untagged']))[:30],
                    'digest': (img.get('digest', '')[:20] + '...') if img.get('digest') else '-',
                    'pushed': format_datetime(img.get('pushedAt')),
                    'size': f"{img.get('sizeMB', 0):.1f} MB",
                })
            formatter.output(table_data, title=f"Images for {service}")
        else:
            formatter.output(images)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
