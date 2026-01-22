"""Pipelines command group for Dashborion CLI - API-based implementation"""

import click
import sys
import json
from typing import Optional, List

from dashborion.utils.output import OutputFormatter, format_status, format_datetime


PROVIDERS = ['codepipeline', 'argocd', 'jenkins', 'gitlab', 'bitbucket', 'github-actions', 'azure-devops']


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


# =============================================================================
# Pipeline Configuration Commands
# =============================================================================

def _get_api_client():
    """Get authenticated API client."""
    from dashborion.utils.api_client import get_api_client
    return get_api_client()


def _get_project_config(client, project: str) -> dict:
    """Get project configuration from API."""
    response = client.get(f'/api/config/projects/{project}')
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _get_environment_config(client, project: str, env: str) -> dict:
    """Get environment configuration from API."""
    response = client.get(f'/api/config/environments/{project}/{env}')
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _update_project_config(client, project: str, data: dict) -> dict:
    """Update project configuration via API."""
    response = client.put(f'/api/config/projects/{project}', json_data=data)
    response.raise_for_status()
    return response.json()


def _update_environment_config(client, project: str, env: str, data: dict) -> dict:
    """Update environment configuration via API."""
    response = client.put(f'/api/config/environments/{project}/{env}', json_data=data)
    response.raise_for_status()
    return response.json()


@pipelines.group('config')
def pipelines_config():
    """Configure pipelines for services

    Manage build (CI) and deploy (CD) pipeline configuration for services.

    \b
    Build pipelines are configured at:
    - Project level (buildMode: 'project') - shared across all environments
    - Environment level (buildMode: 'environment') - specific per environment

    Deploy pipelines are always configured per environment/service.

    \b
    Examples:
      # Show current pipeline configuration
      dashborion pipelines config show

      # Configure a build pipeline for a service
      dashborion pipelines config set-build -s hybris -p jenkins -j RubixDeployment/EKS/build-hybris

      # Configure a deploy pipeline for a service
      dashborion pipelines config set-deploy -s hybris -e staging -p jenkins -j RubixDeployment/EKS/STAGING/deploy-hybris

      # Browse available Jenkins jobs
      dashborion pipelines discover -p jenkins

      # Browse Jenkins jobs in a specific folder
      dashborion pipelines discover -p jenkins --path RubixDeployment/EKS/STAGING
    """
    pass


@pipelines_config.command('show')
@click.option('--service', '-s', help='Show config for specific service')
@click.option('--env', '-e', help='Show config for specific environment')
@click.pass_obj
def config_show(ctx, service: Optional[str], env: Optional[str]):
    """Show current pipeline configuration

    Without options, shows all pipeline configuration for the current project.
    Use --service to filter to a specific service.
    Use --env to show environment-specific deploy pipelines.

    \b
    Examples:
      dashborion pipelines config show
      dashborion pipelines config show -s hybris
      dashborion pipelines config show -e staging
      dashborion pipelines config show -s hybris -e staging
    """
    formatter = OutputFormatter(ctx.output_format)

    project = ctx.project
    if not project:
        click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
        sys.exit(1)

    try:
        client = _get_api_client()

        # Get project config
        project_config = _get_project_config(client, project)
        if not project_config:
            click.echo(f"Project '{project}' not found", err=True)
            sys.exit(1)

        # Extract pipeline info
        pipelines_cfg = project_config.get('pipelines', {})
        build_mode = pipelines_cfg.get('buildMode', 'project')
        services_cfg = pipelines_cfg.get('services', {})

        # Get services list from project or topology
        topology = project_config.get('topology', {})
        all_services = list(services_cfg.keys())
        for comp_id, comp_cfg in topology.get('components', {}).items():
            if isinstance(comp_cfg, dict) and comp_cfg.get('type') in ('k8s-deployment', 'k8s-statefulset'):
                if comp_id not in all_services:
                    all_services.append(comp_id)

        if ctx.output_format == 'json':
            result = {
                'project': project,
                'buildMode': build_mode,
                'services': services_cfg,
            }
            if env:
                env_config = _get_environment_config(client, project, env)
                if env_config:
                    result['environment'] = {
                        'name': env,
                        'services': env_config.get('services', []),
                        'pipelines': env_config.get('pipelines', {}),
                    }
            click.echo(json.dumps(result, indent=2))
            return

        # Table output
        click.echo()
        click.echo(f"Pipeline Configuration for: {click.style(project, bold=True)}")
        click.echo(f"Build Mode: {click.style(build_mode, fg='cyan')}")
        click.echo()

        # Filter services if specified
        show_services = [service] if service else all_services

        if not show_services:
            click.echo("No services configured.")
            return

        # Build pipelines (project-level)
        click.echo(click.style("Build Pipelines (CI):", bold=True))
        click.echo(f"  {'SERVICE':<20} {'PROVIDER':<15} {'JOB PATH'}")
        click.echo(f"  {'-'*20} {'-'*15} {'-'*50}")

        for svc in show_services:
            svc_cfg = services_cfg.get(svc, {})
            build_cfg = svc_cfg.get('build', {})
            if build_cfg.get('enabled'):
                provider = build_cfg.get('provider', '-')
                job = build_cfg.get('jobPath', '-')
                click.echo(f"  {svc:<20} {provider:<15} {job}")
            else:
                click.echo(f"  {svc:<20} {click.style('not configured', fg='yellow')}")

        # Deploy pipelines (environment-level)
        if env:
            click.echo()
            click.echo(click.style(f"Deploy Pipelines (CD) - {env}:", bold=True))

            env_config = _get_environment_config(client, project, env)
            if not env_config:
                click.echo(f"  Environment '{env}' not found")
            else:
                env_services = env_config.get('services', [])
                env_pipelines = env_config.get('pipelines', {}).get('services', {})

                click.echo(f"  {'SERVICE':<20} {'PROVIDER':<15} {'JOB PATH'}")
                click.echo(f"  {'-'*20} {'-'*15} {'-'*50}")

                for svc in show_services:
                    if service and svc != service:
                        continue
                    if svc not in env_services and not service:
                        continue

                    svc_cfg = env_pipelines.get(svc, {})
                    deploy_cfg = svc_cfg.get('deploy', {})
                    if deploy_cfg.get('enabled'):
                        provider = deploy_cfg.get('provider', '-')
                        job = deploy_cfg.get('jobPath', '-')
                        click.echo(f"  {svc:<20} {provider:<15} {job}")
                    else:
                        click.echo(f"  {svc:<20} {click.style('not configured', fg='yellow')}")
        else:
            click.echo()
            click.echo(f"Use --env to show deploy pipelines for a specific environment")

        click.echo()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines_config.command('set-build')
@click.option('--service', '-s', required=True, help='Service name')
@click.option('--provider', '-p', required=True, type=click.Choice(PROVIDERS), help='CI/CD provider')
@click.option('--job', '-j', required=True, help='Job path (e.g., folder/job-name)')
@click.option('--disable', is_flag=True, help='Disable the build pipeline')
@click.pass_obj
def config_set_build(ctx, service: str, provider: str, job: str, disable: bool):
    """Configure build pipeline for a service

    Sets or updates the build (CI) pipeline configuration for a service.
    Build pipelines are typically configured at the project level.

    \b
    Examples:
      # Configure Jenkins build pipeline
      dashborion pipelines config set-build -s hybris -p jenkins -j RubixDeployment/build-hybris

      # Configure CodePipeline
      dashborion pipelines config set-build -s api -p codepipeline -j my-build-pipeline

      # Disable build pipeline
      dashborion pipelines config set-build -s hybris -p jenkins -j "" --disable
    """
    project = ctx.project
    if not project:
        click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
        sys.exit(1)

    try:
        client = _get_api_client()

        # Get current project config
        project_config = _get_project_config(client, project)
        if not project_config:
            click.echo(f"Project '{project}' not found", err=True)
            sys.exit(1)

        # Update pipelines config
        pipelines_cfg = project_config.get('pipelines', {})
        services_cfg = pipelines_cfg.setdefault('services', {})
        service_cfg = services_cfg.setdefault(service, {})

        service_cfg['build'] = {
            'enabled': not disable,
            'provider': provider,
            'jobPath': job if not disable else '',
        }

        project_config['pipelines'] = pipelines_cfg

        # Save via API
        result = _update_project_config(client, project, project_config)

        if disable:
            click.echo(f"Disabled build pipeline for {click.style(service, bold=True)}")
        else:
            click.echo(f"Configured build pipeline for {click.style(service, bold=True)}:")
            click.echo(f"  Provider: {click.style(provider, fg='cyan')}")
            click.echo(f"  Job: {click.style(job, fg='green')}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines_config.command('set-deploy')
@click.option('--service', '-s', required=True, help='Service name')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--provider', '-p', required=True, type=click.Choice(PROVIDERS), help='CI/CD provider')
@click.option('--job', '-j', required=True, help='Job path (e.g., folder/job-name)')
@click.option('--disable', is_flag=True, help='Disable the deploy pipeline')
@click.pass_obj
def config_set_deploy(ctx, service: str, env: str, provider: str, job: str, disable: bool):
    """Configure deploy pipeline for a service in an environment

    Sets or updates the deploy (CD) pipeline configuration for a service.
    Deploy pipelines are configured per environment.

    \b
    Examples:
      # Configure Jenkins deploy pipeline for staging
      dashborion pipelines config set-deploy -s hybris -e staging -p jenkins -j RubixDeployment/EKS/STAGING/deploy-hybris

      # Configure ArgoCD deploy
      dashborion pipelines config set-deploy -s api -e production -p argocd -j rubix-api

      # Disable deploy pipeline
      dashborion pipelines config set-deploy -s hybris -e staging -p jenkins -j "" --disable
    """
    project = ctx.project
    if not project:
        click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
        sys.exit(1)

    try:
        client = _get_api_client()

        # Get current environment config
        env_config = _get_environment_config(client, project, env)
        if not env_config:
            click.echo(f"Environment '{env}' not found in project '{project}'", err=True)
            sys.exit(1)

        # Update pipelines config
        pipelines_cfg = env_config.setdefault('pipelines', {})
        services_cfg = pipelines_cfg.setdefault('services', {})
        service_cfg = services_cfg.setdefault(service, {})

        service_cfg['deploy'] = {
            'enabled': not disable,
            'provider': provider,
            'jobPath': job if not disable else '',
        }

        env_config['pipelines'] = pipelines_cfg

        # Save via API
        result = _update_environment_config(client, project, env, env_config)

        if disable:
            click.echo(f"Disabled deploy pipeline for {click.style(service, bold=True)} in {click.style(env, fg='cyan')}")
        else:
            click.echo(f"Configured deploy pipeline for {click.style(service, bold=True)} in {click.style(env, fg='cyan')}:")
            click.echo(f"  Provider: {click.style(provider, fg='cyan')}")
            click.echo(f"  Job: {click.style(job, fg='green')}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines_config.command('set-build-mode')
@click.option('--mode', '-m', required=True, type=click.Choice(['project', 'environment']),
              help='Build mode (project or environment)')
@click.pass_obj
def config_set_build_mode(ctx, mode: str):
    """Set build mode for the project

    Controls where build pipelines are configured:
    - project: Build pipelines are shared across all environments (default)
    - environment: Each environment has its own build pipeline configuration

    \b
    Examples:
      dashborion pipelines config set-build-mode -m project
      dashborion pipelines config set-build-mode -m environment
    """
    project = ctx.project
    if not project:
        click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
        sys.exit(1)

    try:
        client = _get_api_client()

        # Get current project config
        project_config = _get_project_config(client, project)
        if not project_config:
            click.echo(f"Project '{project}' not found", err=True)
            sys.exit(1)

        # Update build mode
        pipelines_cfg = project_config.setdefault('pipelines', {})
        pipelines_cfg['buildMode'] = mode

        project_config['pipelines'] = pipelines_cfg

        # Save via API
        result = _update_project_config(client, project, project_config)

        click.echo(f"Build mode set to: {click.style(mode, bold=True, fg='green')}")
        if mode == 'project':
            click.echo("Build pipelines will be shared across all environments.")
        else:
            click.echo("Each environment will have its own build pipeline configuration.")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines.command('discover')
@click.option('--provider', '-p', default='jenkins', type=click.Choice(['jenkins', 'gitlab', 'bitbucket', 'azure-devops']),
              help='CI/CD provider to browse (default: jenkins)')
@click.option('--path', help='Folder path to browse (e.g., RubixDeployment/EKS)')
@click.option('--search', '-q', help='Search/filter pattern')
@click.option('--show-params/--no-params', default=True, help='Show parameter definitions')
@click.option('--limit', '-n', default=20, help='Maximum number of results')
@click.pass_obj
def discover(ctx, provider: str, path: Optional[str], search: Optional[str], show_params: bool, limit: int):
    """Browse and discover available CI/CD jobs with parameters

    Interactively browse jobs from the CI/CD provider.
    Shows parameter definitions for each job.

    \b
    Examples:
      # Browse Jenkins root
      dashborion pipelines discover

      # Browse a specific Jenkins folder
      dashborion pipelines discover --path RubixDeployment/EKS/STAGING

      # Hide parameter definitions
      dashborion pipelines discover --path RubixDeployment/EKS/STAGING --no-params

      # Search for jobs containing 'deploy'
      dashborion pipelines discover -q deploy
    """
    formatter = OutputFormatter(ctx.output_format)

    try:
        client = _get_api_client()

        # For Jenkins, use the new dedicated discovery endpoint
        if provider == 'jenkins':
            params = {
                'includeParams': 'true' if show_params else 'false',
                'limit': limit,
            }
            if path:
                params['path'] = path

            response = client.get('/api/pipelines/jenkins/discover', params=params)
        else:
            # Fallback for other providers (may need project)
            project = ctx.project
            if not project:
                click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
                sys.exit(1)

            params = {
                'provider': provider,
                'limit': limit,
            }
            if path:
                params['path'] = path
            if search:
                params['search'] = search

            response = client.get(f'/api/{project}/pipelines/discover', params=params)

        response.raise_for_status()
        data = response.json()

        jobs = data.get('jobs', [])
        folders = data.get('folders', [])
        current_path = data.get('currentPath', '')

        # Apply search filter client-side if provided
        if search:
            search_lower = search.lower()
            jobs = [j for j in jobs if search_lower in j.get('name', '').lower()]
            folders = [f for f in folders if search_lower in f.get('name', '').lower()]

        if ctx.output_format == 'json':
            click.echo(json.dumps(data, indent=2))
            return

        # Table output
        click.echo()
        if current_path:
            click.echo(f"Browsing: {click.style(current_path, bold=True, fg='cyan')}")
        else:
            click.echo(f"Browsing: {click.style('(root)', fg='cyan')}")
        click.echo()

        # Show folders first
        if folders:
            click.echo(click.style("Folders:", bold=True))
            for folder in folders:
                name = folder.get('name', folder) if isinstance(folder, dict) else folder
                full_path = folder.get('fullPath', name) if isinstance(folder, dict) else name
                click.echo(f"  [D] {name}")
                click.echo(f"      Path: {full_path}")
            click.echo()

        # Show jobs with parameters
        if jobs:
            click.echo(click.style("Jobs:", bold=True))
            for job in jobs:
                name = job.get('name', job) if isinstance(job, dict) else job
                full_path = job.get('fullPath', name) if isinstance(job, dict) else name
                job_type = job.get('type', '') if isinstance(job, dict) else ''
                last_build = job.get('lastBuild', {}) if isinstance(job, dict) else {}
                parameters = job.get('parameters', []) if isinstance(job, dict) else []

                status_icon = '+' if last_build.get('result') == 'SUCCESS' else 'x' if last_build.get('result') == 'FAILURE' else 'o'
                status_color = 'green' if status_icon == '+' else 'red' if status_icon == 'x' else 'yellow'

                click.echo(f"  [{click.style(status_icon, fg=status_color)}] {name}")
                click.echo(f"      Path: {click.style(full_path, fg='green')}")
                if job_type:
                    click.echo(f"      Type: {job_type}")

                # Show parameters
                if parameters and show_params:
                    click.echo(f"      Parameters:")
                    for param in parameters:
                        param_name = param.get('name', '')
                        param_type = param.get('type', 'string')
                        default = param.get('default', '')
                        choices = param.get('choices', [])

                        if choices:
                            click.echo(f"        - {param_name}: {click.style(param_type, fg='cyan')} (choices: {', '.join(choices[:5])}{'...' if len(choices) > 5 else ''})")
                        elif default:
                            click.echo(f"        - {param_name}: {click.style(param_type, fg='cyan')} (default: {default})")
                        else:
                            click.echo(f"        - {param_name}: {click.style(param_type, fg='cyan')}")
                click.echo()

        elif not folders:
            click.echo("No jobs or folders found.")

        click.echo()
        click.echo("Use the 'Path' value with:")
        click.echo(f"  dashborion pipelines config set-build -s <service> -p {provider} -j <path>")
        click.echo(f"  dashborion pipelines config set-deploy -s <service> -e <env> -p {provider} -j <path>")
        click.echo()
        click.echo("View build history for a job:")
        click.echo(f"  dashborion pipelines history -j <path>")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines.command('history')
@click.option('--job', '-j', required=True, help='Job path (e.g., RubixDeployment/EKS/STAGING/deploy-hybris)')
@click.option('--filter', '-f', 'filters', multiple=True, help='Filter by parameter (e.g., -f Webshop=MI2)')
@click.option('--result', '-r', type=click.Choice(['SUCCESS', 'FAILURE', 'UNSTABLE', 'ABORTED']),
              help='Filter by build result')
@click.option('--limit', '-n', default=15, help='Maximum builds to show')
@click.pass_obj
def history(ctx, job: str, filters: tuple, result: Optional[str], limit: int):
    """View build history with parameter filtering

    Shows recent builds for a Jenkins job, optionally filtered by parameter values.
    Useful for finding which builds used specific parameters.

    \b
    Examples:
      # Show recent builds for a job
      dashborion pipelines history -j RubixDeployment/EKS/STAGING/deploy-hybris

      # Filter by Webshop parameter
      dashborion pipelines history -j RubixDeployment/EKS/STAGING/deploy-hybris -f Webshop=MI2

      # Filter by multiple parameters
      dashborion pipelines history -j RubixDeployment/EKS/STAGING/deploy-hybris -f Webshop=MI2 -f Tag=develop

      # Show only failed builds
      dashborion pipelines history -j RubixDeployment/EKS/STAGING/deploy-hybris -r FAILURE
    """
    formatter = OutputFormatter(ctx.output_format)

    try:
        client = _get_api_client()

        # Build query params
        params = {'limit': limit}
        if result:
            params['result'] = result

        # Parse filter options (format: key=value)
        for f in filters:
            if '=' in f:
                key, value = f.split('=', 1)
                params[key] = value

        response = client.get(f'/api/pipelines/jenkins/history/{job}', params=params)
        response.raise_for_status()
        data = response.json()

        if ctx.output_format == 'json':
            click.echo(json.dumps(data, indent=2))
            return

        job_name = data.get('jobName', job.split('/')[-1])
        parameters = data.get('parameters', [])
        builds = data.get('builds', [])
        applied_filters = data.get('filters', {})

        click.echo()
        click.echo(f"Build History: {click.style(job_name, bold=True)}")
        click.echo(f"Job Path: {click.style(job, fg='cyan')}")

        # Show available parameters
        if parameters:
            param_names = [p.get('name') for p in parameters]
            click.echo(f"Parameters: {', '.join(param_names)}")

        # Show applied filters
        if applied_filters:
            filter_str = ', '.join([f"{k}={v}" for k, v in applied_filters.items()])
            click.echo(f"Filters: {click.style(filter_str, fg='yellow')}")

        click.echo()

        if not builds:
            click.echo("No builds found matching criteria.")
            return

        # Show builds
        click.echo(f"{'#':<6} {'Result':<10} {'Duration':<12} {'Date':<20} {'Parameters'}")
        click.echo(f"{'-'*6} {'-'*10} {'-'*12} {'-'*20} {'-'*40}")

        for build in builds:
            number = build.get('number', '')
            build_result = build.get('result', 'RUNNING' if build.get('building') else 'UNKNOWN')
            duration = build.get('durationFormatted', '-')
            dt = build.get('datetime', '')
            if dt:
                # Format datetime nicely
                dt = dt.replace('T', ' ')[:19]

            # Format result with color
            result_colors = {
                'SUCCESS': 'green',
                'FAILURE': 'red',
                'UNSTABLE': 'yellow',
                'ABORTED': 'magenta',
                'RUNNING': 'cyan',
            }
            result_color = result_colors.get(build_result, 'white')
            result_styled = click.style(build_result[:10], fg=result_color)

            # Format parameters
            build_params = build.get('parameters', {})
            params_str = ', '.join([f"{k}={v}" for k, v in build_params.items()])
            if len(params_str) > 40:
                params_str = params_str[:37] + '...'

            click.echo(f"#{number:<5} {result_styled:<19} {duration:<12} {dt:<20} {params_str}")

        click.echo()
        click.echo(f"Total: {data.get('count', len(builds))} builds")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@pipelines.command('params')
@click.option('--job', '-j', required=True, help='Job path')
@click.option('--param', '-p', required=True, help='Parameter name to analyze')
@click.option('--limit', '-n', default=50, help='Number of builds to analyze')
@click.pass_obj
def params(ctx, job: str, param: str, limit: int):
    """Analyze parameter values used in recent builds

    Shows unique values used for a parameter across recent builds,
    sorted by frequency. Useful for discovering valid parameter values.

    \b
    Examples:
      # See which Webshop values are used
      dashborion pipelines params -j RubixDeployment/EKS/STAGING/deploy-hybris -p Webshop

      # See which Tags are commonly used
      dashborion pipelines params -j RubixDeployment/EKS/STAGING/deploy-hybris -p Tag
    """
    formatter = OutputFormatter(ctx.output_format)

    try:
        client = _get_api_client()

        params_dict = {'param': param, 'limit': limit}
        response = client.get(f'/api/pipelines/jenkins/params/{job}', params=params_dict)
        response.raise_for_status()
        data = response.json()

        if ctx.output_format == 'json':
            click.echo(json.dumps(data, indent=2))
            return

        values = data.get('values', [])

        click.echo()
        click.echo(f"Parameter Values: {click.style(param, bold=True)}")
        click.echo(f"Job: {click.style(job, fg='cyan')}")
        click.echo(f"Analyzed: {limit} recent builds")
        click.echo()

        if not values:
            click.echo("No values found for this parameter.")
            return

        click.echo(f"{'Value':<30} {'Count':<10} {'Usage'}")
        click.echo(f"{'-'*30} {'-'*10} {'-'*20}")

        max_count = values[0]['count'] if values else 1
        for v in values:
            value = v.get('value', '')
            count = v.get('count', 0)
            bar_len = int((count / max_count) * 20)
            bar = '#' * bar_len

            if len(value) > 28:
                value = value[:25] + '...'

            click.echo(f"{value:<30} {count:<10} {click.style(bar, fg='green')}")

        click.echo()
        click.echo(f"Total unique values: {len(values)}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
