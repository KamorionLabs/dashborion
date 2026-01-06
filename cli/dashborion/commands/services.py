"""Services command group for Dashborion CLI"""

import click
import sys
from typing import Optional

from dashborion.utils.output import OutputFormatter, format_status, format_datetime


@click.group()
def services():
    """Manage and view services (ECS/EKS)"""
    pass


@services.command('list')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--cluster', '-c', help='Override cluster name')
@click.pass_obj
def list_services(ctx, env: str, cluster: Optional[str]):
    """List all services in an environment"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    if not env_config:
        click.echo(f"Environment '{env}' not found", err=True)
        sys.exit(1)

    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        env_type = env_config.get('type', 'ecs')
        cluster_name = cluster or env_config.get('cluster')

        if env_type == 'ecs':
            from dashborion.collectors.ecs import ECSCollector
            collector = ECSCollector(session)
            services_data = collector.list_services(cluster_name)
        elif env_type == 'eks':
            from dashborion.collectors.eks import EKSCollector
            collector = EKSCollector(session, env_config.get('context'))
            services_data = collector.list_services(
                namespaces=env_config.get('namespaces', ['default'])
            )
        else:
            click.echo(f"Unknown environment type: {env_type}", err=True)
            sys.exit(1)

        # Format for table output
        if ctx.output_format == 'table':
            table_data = []
            for svc in services_data:
                table_data.append({
                    'name': svc.get('name', svc.get('serviceName', '')),
                    'status': format_status(svc.get('status', 'unknown')),
                    'running': f"{svc.get('runningCount', 0)}/{svc.get('desiredCount', 0)}",
                    'cpu': svc.get('cpu', '-'),
                    'memory': svc.get('memory', '-'),
                })
            formatter.output(table_data, title=f"Services in {env}")
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
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--cluster', '-c', help='Override cluster name')
@click.pass_obj
def describe_service(ctx, service: str, env: str, cluster: Optional[str]):
    """Show detailed information about a service"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        env_type = env_config.get('type', 'ecs')
        cluster_name = cluster or env_config.get('cluster')

        if env_type == 'ecs':
            from dashborion.collectors.ecs import ECSCollector
            collector = ECSCollector(session)
            service_data = collector.describe_service(cluster_name, service)
        elif env_type == 'eks':
            from dashborion.collectors.eks import EKSCollector
            collector = EKSCollector(session, env_config.get('context'))
            service_data = collector.describe_service(
                service,
                namespace=env_config.get('namespaces', ['default'])[0]
            )
        else:
            click.echo(f"Unknown environment type: {env_type}", err=True)
            sys.exit(1)

        formatter.output(service_data, title=f"Service: {service}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('tasks')
@click.argument('service')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--cluster', '-c', help='Override cluster name')
@click.pass_obj
def list_tasks(ctx, service: str, env: str, cluster: Optional[str]):
    """List tasks/pods for a service"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        env_type = env_config.get('type', 'ecs')
        cluster_name = cluster or env_config.get('cluster')

        if env_type == 'ecs':
            from dashborion.collectors.ecs import ECSCollector
            collector = ECSCollector(session)
            tasks_data = collector.list_tasks(cluster_name, service)
        elif env_type == 'eks':
            from dashborion.collectors.eks import EKSCollector
            collector = EKSCollector(session, env_config.get('context'))
            tasks_data = collector.list_pods(
                service,
                namespace=env_config.get('namespaces', ['default'])[0]
            )
        else:
            click.echo(f"Unknown environment type: {env_type}", err=True)
            sys.exit(1)

        # Format for table output
        if ctx.output_format == 'table':
            table_data = []
            for task in tasks_data:
                table_data.append({
                    'id': task.get('taskId', task.get('name', ''))[:12],
                    'status': format_status(task.get('lastStatus', task.get('status', 'unknown'))),
                    'health': task.get('healthStatus', '-'),
                    'started': format_datetime(task.get('startedAt', task.get('startTime'))),
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
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--tail', '-n', default=50, help='Number of log lines (default: 50)')
@click.option('--follow', '-f', is_flag=True, help='Follow log output')
@click.option('--since', '-s', help='Show logs since (e.g., 1h, 30m, 2d)')
@click.pass_obj
def service_logs(ctx, service: str, env: str, tail: int, follow: bool, since: Optional[str]):
    """View logs for a service"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        env_type = env_config.get('type', 'ecs')

        if env_type == 'ecs':
            from dashborion.collectors.ecs import ECSCollector
            collector = ECSCollector(session)
            collector.stream_logs(
                cluster=env_config.get('cluster'),
                service=service,
                tail=tail,
                follow=follow,
                since=since
            )
        elif env_type == 'eks':
            from dashborion.collectors.eks import EKSCollector
            collector = EKSCollector(session, env_config.get('context'))
            collector.stream_logs(
                service=service,
                namespace=env_config.get('namespaces', ['default'])[0],
                tail=tail,
                follow=follow,
                since=since
            )
        else:
            click.echo(f"Unknown environment type: {env_type}", err=True)
            sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\nStopped following logs", err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@services.command('deploy')
@click.argument('service')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--force', is_flag=True, help='Force new deployment')
@click.option('--image', help='New image to deploy (tag or full URI)')
@click.pass_obj
def deploy_service(ctx, service: str, env: str, force: bool, image: Optional[str]):
    """Deploy or redeploy a service"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        env_type = env_config.get('type', 'ecs')
        cluster_name = env_config.get('cluster')

        if env_type == 'ecs':
            from dashborion.collectors.ecs import ECSCollector
            collector = ECSCollector(session)

            click.echo(f"Deploying {service} in {env}...")

            result = collector.force_deploy(cluster_name, service, image=image)

            if result.get('success'):
                click.echo(f"Deployment initiated successfully")
                click.echo(f"  Deployment ID: {result.get('deploymentId', 'N/A')}")
            else:
                click.echo(f"Deployment failed: {result.get('error')}", err=True)
                sys.exit(1)

        elif env_type == 'eks':
            from dashborion.collectors.eks import EKSCollector
            collector = EKSCollector(session, env_config.get('context'))

            click.echo(f"Restarting {service} in {env}...")

            result = collector.restart_deployment(
                service,
                namespace=env_config.get('namespaces', ['default'])[0],
                image=image
            )

            if result.get('success'):
                click.echo(f"Rollout restarted successfully")
            else:
                click.echo(f"Restart failed: {result.get('error')}", err=True)
                sys.exit(1)

        else:
            click.echo(f"Unknown environment type: {env_type}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
