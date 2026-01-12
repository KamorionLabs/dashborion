"""Services command group for Dashborion CLI - API-based implementation"""

import click
import sys
from typing import Optional

from dashborion.utils.output import OutputFormatter, format_status, format_datetime


@click.group()
def services():
    """Manage and view services (ECS/EKS)"""
    pass


def _get_collector(ctx, env: Optional[str] = None):
    """Get API collector configured for the environment."""
    from dashborion.collectors.api import APICollector
    from dashborion.utils.api_client import get_api_client
    from dashborion.config.cli_config import get_environment_config

    # Use provided env or fall back to context env
    effective_env = env or ctx.env
    if not effective_env:
        click.echo("No environment specified. Use -e/--env or select with 'dashborion env use <name>'", err=True)
        sys.exit(1)

    env_config = get_environment_config(ctx.config or {}, effective_env)

    # Get project from context
    project = ctx.project
    if not project:
        click.echo("No project selected. Use 'dashborion project use <name>'", err=True)
        sys.exit(1)

    client = get_api_client()
    return APICollector(client, project), env_config, effective_env


@services.command('list')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--cluster', '-c', help='Override cluster name (ignored in API mode)')
@click.pass_obj
def list_services(ctx, env: Optional[str], cluster: Optional[str]):
    """List all services in an environment"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        services_data = collector.list_services(effective_env)

        # Format for table output
        if ctx.output_format == 'table':
            table_data = []
            for svc_name, svc in services_data.items():
                if isinstance(svc, dict):
                    table_data.append({
                        'name': svc_name,
                        'status': format_status(svc.get('status', 'unknown')),
                        'running': f"{svc.get('runningCount', 0)}/{svc.get('desiredCount', 0)}",
                        'health': svc.get('health', '-'),
                        'image': svc.get('image', '-'),
                    })
            formatter.output(table_data, title=f"Services in {effective_env}")
        else:
            formatter.output(services_data)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('describe')
@click.argument('service')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--cluster', '-c', help='Override cluster name (ignored in API mode)')
@click.pass_obj
def describe_service(ctx, service: str, env: Optional[str], cluster: Optional[str]):
    """Show detailed information about a service"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        service_data = collector.describe_service(effective_env, service)

        formatter.output(service_data, title=f"Service: {service}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('tasks')
@click.argument('service')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--cluster', '-c', help='Override cluster name (ignored in API mode)')
@click.pass_obj
def list_tasks(ctx, service: str, env: Optional[str], cluster: Optional[str]):
    """List tasks/pods for a service"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        # Get service details which includes tasks
        service_data = collector.describe_service(effective_env, service)
        tasks_data = service_data.get('tasks', [])

        # Format for table output
        if ctx.output_format == 'table':
            table_data = []
            for task in tasks_data:
                table_data.append({
                    'id': task.get('taskId', task.get('name', ''))[:12],
                    'status': format_status(task.get('status', 'unknown')),
                    'health': task.get('health', '-'),
                    'started': format_datetime(task.get('startedAt')),
                    'ip': task.get('privateIp', task.get('ip', '-')),
                })
            formatter.output(table_data, title=f"Tasks for {service}")
        else:
            formatter.output(tasks_data)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('logs')
@click.argument('service')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--tail', '-n', default=50, help='Number of log lines (default: 50)')
@click.option('--follow', '-f', is_flag=True, help='Follow log output (not supported via API)')
@click.option('--since', '-s', help='Show logs since (e.g., 1h, 30m, 2d)')
@click.pass_obj
def service_logs(ctx, service: str, env: Optional[str], tail: int, follow: bool, since: Optional[str]):
    """View logs for a service"""
    if follow:
        click.echo("Warning: --follow is not supported via API, showing recent logs", err=True)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        logs = collector.get_service_logs(effective_env, service, tail=tail)

        for log_entry in logs:
            if isinstance(log_entry, dict):
                timestamp = log_entry.get('timestamp', '')
                message = log_entry.get('message', '')
                pod = log_entry.get('pod', '')
                if pod:
                    click.echo(f"[{pod}] {timestamp} {message}")
                else:
                    click.echo(f"{timestamp} {message}")
            else:
                click.echo(log_entry)

    except KeyboardInterrupt:
        click.echo("\nStopped", err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('deploy')
@click.argument('service')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--force', is_flag=True, help='Force new deployment')
@click.option('--image', help='New image to deploy (tag or full URI)')
@click.pass_obj
def deploy_service(ctx, service: str, env: Optional[str], force: bool, image: Optional[str]):
    """Deploy or redeploy a service"""
    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        click.echo(f"Deploying {service} in {effective_env}...")

        # Use 'reload' action for force deploy, 'latest' for image update
        action = 'reload' if force or not image else 'latest'
        result = collector.deploy_service(effective_env, service, action=action, image_tag=image)

        if result.get('success'):
            click.echo(f"Deployment initiated successfully")
            if result.get('deploymentId'):
                click.echo(f"  Deployment ID: {result.get('deploymentId')}")
            if result.get('action'):
                click.echo(f"  Action: {result.get('action')}")
        else:
            click.echo(f"Deployment failed: {result.get('error')}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('scale')
@click.argument('service')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--replicas', '-r', type=int, required=True, help='Desired replica count')
@click.pass_obj
def scale_service(ctx, service: str, env: Optional[str], replicas: int):
    """Scale a service to specified replica count"""
    if replicas < 0 or replicas > 10:
        click.echo("Error: replicas must be between 0 and 10", err=True)
        sys.exit(1)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        click.echo(f"Scaling {service} to {replicas} replicas...")

        result = collector.scale_service(effective_env, service, replicas)

        if result.get('success'):
            click.echo(f"Scaling initiated successfully")
            click.echo(f"  Desired count: {result.get('desiredCount', replicas)}")
        else:
            click.echo(f"Scaling failed: {result.get('error')}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('details')
@click.argument('service')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.pass_obj
def service_details(ctx, service: str, env: Optional[str]):
    """Show extended service details (env vars, secrets, logs)"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        details = collector.get_service_details(effective_env, service)

        formatter.output(details, title=f"Details: {service}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('metrics')
@click.argument('service')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.pass_obj
def service_metrics(ctx, service: str, env: Optional[str]):
    """Show service metrics (CPU, Memory)"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        metrics = collector.get_metrics(effective_env, service)

        if ctx.output_format == 'table':
            # Show latest metrics in table format
            cpu_data = metrics.get('metrics', {}).get('cpu', [])
            memory_data = metrics.get('metrics', {}).get('memory', [])

            latest_cpu = cpu_data[-1] if cpu_data else {}
            latest_memory = memory_data[-1] if memory_data else {}

            table_data = [
                {'metric': 'CPU', 'value': f"{latest_cpu.get('value', '-')}%", 'timestamp': latest_cpu.get('timestamp', '-')},
                {'metric': 'Memory', 'value': f"{latest_memory.get('value', '-')}%", 'timestamp': latest_memory.get('timestamp', '-')},
            ]
            formatter.output(table_data, title=f"Metrics: {service}")
        else:
            formatter.output(metrics)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
