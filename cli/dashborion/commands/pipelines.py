"""Pipelines command group for Dashborion CLI"""

import click
import sys
from typing import Optional

from dashborion.utils.output import OutputFormatter, format_status, format_datetime


@click.group()
def pipelines():
    """View CI/CD pipelines (CodePipeline, ArgoCD, Jenkins, GitLab, Bitbucket)"""
    pass


@pipelines.command('list')
@click.option('--env', '-e', help='Environment name')
@click.option('--provider', '-p', type=click.Choice(['codepipeline', 'argocd', 'jenkins', 'gitlab', 'bitbucket']),
              help='CI/CD provider (default: from config)')
@click.option('--type', 'pipeline_type', type=click.Choice(['build', 'deploy', 'all']),
              default='all', help='Pipeline type filter')
@click.pass_obj
def list_pipelines(ctx, env: Optional[str], provider: Optional[str], pipeline_type: str):
    """List pipelines"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env) if env else {}
    formatter = OutputFormatter(ctx.output_format)

    try:
        # Determine provider
        ci_config = ctx.config.get('ci_provider', {})
        provider_type = provider or ci_config.get('type', 'codepipeline')

        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        if provider_type == 'codepipeline':
            from dashborion.collectors.codepipeline import CodePipelineCollector
            collector = CodePipelineCollector(session)
            pipelines_data = collector.list_pipelines(
                prefix=ci_config.get('config', {}).get('prefix'),
                pipeline_type=pipeline_type if pipeline_type != 'all' else None
            )

        elif provider_type == 'argocd':
            from dashborion.collectors.argocd import ArgoCDCollector
            collector = ArgoCDCollector(
                api_url=ci_config.get('config', {}).get('api_url'),
                token_secret=ci_config.get('config', {}).get('token_secret'),
                session=session
            )
            pipelines_data = collector.list_applications()

        elif provider_type == 'jenkins':
            from dashborion.collectors.jenkins import JenkinsCollector
            collector = JenkinsCollector(
                url=ci_config.get('config', {}).get('url'),
                credentials_secret=ci_config.get('config', {}).get('credentials_secret'),
                session=session
            )
            pipelines_data = collector.list_jobs()

        elif provider_type == 'gitlab':
            from dashborion.collectors.gitlab import GitLabCollector
            collector = GitLabCollector(
                url=ci_config.get('config', {}).get('url'),
                token_secret=ci_config.get('config', {}).get('token_secret'),
                project_id=ci_config.get('config', {}).get('project_id'),
                session=session
            )
            pipelines_data = collector.list_pipelines()

        elif provider_type == 'bitbucket':
            from dashborion.collectors.bitbucket import BitbucketCollector
            collector = BitbucketCollector(
                workspace=ci_config.get('config', {}).get('workspace'),
                credentials_secret=ci_config.get('config', {}).get('credentials_secret'),
                session=session
            )
            pipelines_data = collector.list_pipelines()

        else:
            click.echo(f"Unknown provider: {provider_type}", err=True)
            sys.exit(1)

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
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env) if env else {}
    formatter = OutputFormatter(ctx.output_format)

    try:
        ci_config = ctx.config.get('ci_provider', {})
        provider_type = provider or ci_config.get('type', 'codepipeline')

        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        if provider_type == 'codepipeline':
            from dashborion.collectors.codepipeline import CodePipelineCollector
            collector = CodePipelineCollector(session)
            status_data = collector.get_pipeline_status(pipeline)

        elif provider_type == 'argocd':
            from dashborion.collectors.argocd import ArgoCDCollector
            collector = ArgoCDCollector(
                api_url=ci_config.get('config', {}).get('api_url'),
                token_secret=ci_config.get('config', {}).get('token_secret'),
                session=session
            )
            status_data = collector.get_application_status(pipeline)

        else:
            click.echo(f"Status not implemented for provider: {provider_type}", err=True)
            sys.exit(1)

        formatter.output(status_data, title=f"Pipeline: {pipeline}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@pipelines.command('logs')
@click.argument('pipeline')
@click.option('--env', '-e', help='Environment name')
@click.option('--execution', help='Execution ID')
@click.option('--tail', '-n', default=100, help='Number of log lines')
@click.pass_obj
def pipeline_logs(ctx, pipeline: str, env: Optional[str], execution: Optional[str], tail: int):
    """View pipeline execution logs"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env) if env else {}

    try:
        ci_config = ctx.config.get('ci_provider', {})
        provider_type = ci_config.get('type', 'codepipeline')

        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        if provider_type == 'codepipeline':
            from dashborion.collectors.codepipeline import CodePipelineCollector
            collector = CodePipelineCollector(session)
            collector.stream_logs(pipeline, execution_id=execution, tail=tail)

        else:
            click.echo(f"Logs not implemented for provider: {provider_type}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
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
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env) if env else {}

    try:
        ci_config = ctx.config.get('ci_provider', {})
        provider_type = provider or ci_config.get('type', 'codepipeline')

        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        if provider_type == 'codepipeline':
            from dashborion.collectors.codepipeline import CodePipelineCollector
            collector = CodePipelineCollector(session)

            click.echo(f"Triggering pipeline: {pipeline}")
            result = collector.start_execution(pipeline)

            if result.get('success'):
                click.echo(f"Execution started: {result.get('executionId')}")

                if wait:
                    click.echo("Waiting for completion...")
                    final_status = collector.wait_for_completion(
                        pipeline,
                        result.get('executionId')
                    )
                    click.echo(f"Final status: {final_status}")
            else:
                click.echo(f"Failed to trigger: {result.get('error')}", err=True)
                sys.exit(1)

        elif provider_type == 'argocd':
            from dashborion.collectors.argocd import ArgoCDCollector
            collector = ArgoCDCollector(
                api_url=ci_config.get('config', {}).get('api_url'),
                token_secret=ci_config.get('config', {}).get('token_secret'),
                session=session
            )

            click.echo(f"Syncing ArgoCD application: {pipeline}")
            result = collector.sync_application(pipeline)

            if result.get('success'):
                click.echo("Sync initiated")
            else:
                click.echo(f"Sync failed: {result.get('error')}", err=True)
                sys.exit(1)

        else:
            click.echo(f"Trigger not implemented for provider: {provider_type}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@pipelines.command('images')
@click.argument('service')
@click.option('--env', '-e', help='Environment name')
@click.option('--limit', '-n', default=10, help='Number of images to show')
@click.pass_obj
def list_images(ctx, service: str, env: Optional[str], limit: int):
    """List ECR images for a service"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env) if env else {}
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        from dashborion.collectors.ecr import ECRCollector
        collector = ECRCollector(session)

        # Get repository name from config or derive from service name
        project_name = ctx.config.get('project_name', 'myproject')
        repo_pattern = ctx.config.get('ecr', {}).get('repo_pattern', '{project}-{service}')
        repo_name = repo_pattern.format(project=project_name, service=service)

        images = collector.list_images(repo_name, limit=limit)

        if ctx.output_format == 'table':
            table_data = []
            for img in images:
                table_data.append({
                    'tags': ', '.join(img.get('tags', ['untagged']))[:30],
                    'digest': img.get('digest', '')[:20] + '...',
                    'pushed': format_datetime(img.get('pushedAt')),
                    'size': f"{img.get('sizeMB', 0):.1f} MB",
                })
            formatter.output(table_data, title=f"Images for {service}")
        else:
            formatter.output(images)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
