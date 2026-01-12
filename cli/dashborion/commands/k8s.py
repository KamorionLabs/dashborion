"""Kubernetes command group for Dashborion CLI - API-based implementation"""

import click
import sys
from typing import Optional

from dashborion.utils.output import OutputFormatter, format_status
from dashborion.commands.context import is_eks_project, get_current_orchestrator


def _require_eks():
    """Validate that current project uses EKS/Kubernetes orchestrator."""
    if not is_eks_project():
        orchestrator = get_current_orchestrator()
        if not orchestrator or orchestrator == 'unknown':
            click.echo("Error: No project selected or orchestrator type unknown.", err=True)
            click.echo()
            click.echo("Select a project first:", err=True)
            click.echo("  dashborion project list", err=True)
            click.echo("  dashborion project use <name>", err=True)
        else:
            click.echo(f"Error: Kubernetes commands are not available for this project.", err=True)
            click.echo(f"Current orchestrator: {orchestrator}", err=True)
            click.echo()
            click.echo("This project uses ECS. For ECS resources, use:", err=True)
            click.echo("  dashborion services list", err=True)
            click.echo("  dashborion infra show", err=True)
        sys.exit(1)


@click.group()
def k8s():
    """Kubernetes resources (pods, services, deployments) - EKS projects only"""
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


@k8s.command('pods')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--namespace', '-n', help='Namespace (default: from config)')
@click.option('--all-namespaces', '-A', is_flag=True, help='All namespaces')
@click.option('--selector', '-l', help='Label selector')
@click.option('--context', '-c', help='(Ignored) Use --env instead')
@click.pass_obj
def list_pods(ctx, env: Optional[str], namespace: Optional[str], all_namespaces: bool,
              selector: Optional[str], context: Optional[str]):
    """List Kubernetes pods"""
    _require_eks()

    if context:
        click.echo("Warning: --context is ignored. Using --env for API mode.", err=True)

    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        ns = None if all_namespaces else namespace
        pods = collector.get_pods(effective_env, namespace=ns, selector=selector)

        if ctx.output_format == 'table':
            table_data = []
            for pod in pods:
                table_data.append({
                    'namespace': pod.get('namespace', '-'),
                    'name': pod.get('name', ''),
                    'status': format_status(pod.get('status', 'unknown')),
                    'ready': pod.get('ready', '-'),
                    'restarts': pod.get('restarts', 0),
                    'age': pod.get('age', '-'),
                })
            formatter.output(table_data, title="Pods")
        else:
            formatter.output(pods)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@k8s.command('services')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--namespace', '-n', help='Namespace')
@click.option('--all-namespaces', '-A', is_flag=True, help='All namespaces')
@click.option('--context', '-c', help='(Ignored) Use --env instead')
@click.pass_obj
def list_services(ctx, env: Optional[str], namespace: Optional[str], all_namespaces: bool,
                  context: Optional[str]):
    """List Kubernetes services"""
    _require_eks()

    if context:
        click.echo("Warning: --context is ignored. Using --env for API mode.", err=True)

    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        ns = None if all_namespaces else namespace
        services = collector.get_k8s_services(effective_env, namespace=ns)

        if ctx.output_format == 'table':
            table_data = []
            for svc in services:
                ports = svc.get('ports', [])
                port_str = ', '.join([f"{p.get('port', '?')}/{p.get('protocol', 'TCP')}" for p in ports[:3]])
                table_data.append({
                    'namespace': svc.get('namespace', '-'),
                    'name': svc.get('name', ''),
                    'type': svc.get('type', '-'),
                    'cluster_ip': svc.get('clusterIP', '-'),
                    'ports': port_str or '-',
                })
            formatter.output(table_data, title="Services")
        else:
            formatter.output(services)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@k8s.command('deployments')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--namespace', '-n', help='Namespace')
@click.option('--all-namespaces', '-A', is_flag=True, help='All namespaces')
@click.option('--context', '-c', help='(Ignored) Use --env instead')
@click.pass_obj
def list_deployments(ctx, env: Optional[str], namespace: Optional[str], all_namespaces: bool,
                     context: Optional[str]):
    """List Kubernetes deployments"""
    _require_eks()

    if context:
        click.echo("Warning: --context is ignored. Using --env for API mode.", err=True)

    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        ns = None if all_namespaces else namespace
        deployments = collector.get_deployments(effective_env, namespace=ns)

        if ctx.output_format == 'table':
            table_data = []
            for deploy in deployments:
                table_data.append({
                    'namespace': deploy.get('namespace', '-'),
                    'name': deploy.get('name', ''),
                    'ready': deploy.get('ready', '-'),
                    'available': deploy.get('available', '-'),
                    'age': deploy.get('age', '-'),
                })
            formatter.output(table_data, title="Deployments")
        else:
            formatter.output(deployments)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@k8s.command('ingresses')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--namespace', '-n', help='Namespace')
@click.option('--all-namespaces', '-A', is_flag=True, help='All namespaces')
@click.option('--context', '-c', help='(Ignored) Use --env instead')
@click.pass_obj
def list_ingresses(ctx, env: Optional[str], namespace: Optional[str], all_namespaces: bool,
                   context: Optional[str]):
    """List Kubernetes ingresses"""
    _require_eks()

    if context:
        click.echo("Warning: --context is ignored. Using --env for API mode.", err=True)

    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        ns = None if all_namespaces else namespace
        ingresses = collector.get_ingresses(effective_env, namespace=ns)

        if ctx.output_format == 'table':
            table_data = []
            for ing in ingresses:
                hosts = ing.get('hosts', [])
                host_str = ', '.join(hosts[:2])
                if len(hosts) > 2:
                    host_str += '...'
                table_data.append({
                    'namespace': ing.get('namespace', '-'),
                    'name': ing.get('name', ''),
                    'class': ing.get('ingressClass', '-'),
                    'hosts': host_str or '-',
                    'address': ing.get('address', '-'),
                })
            formatter.output(table_data, title="Ingresses")
        else:
            formatter.output(ingresses)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@k8s.command('nodes')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--metrics/--no-metrics', default=True, help='Include node metrics')
@click.option('--context', '-c', help='(Ignored) Use --env instead')
@click.pass_obj
def list_nodes(ctx, env: Optional[str], metrics: bool, context: Optional[str]):
    """List Kubernetes nodes"""
    _require_eks()

    if context:
        click.echo("Warning: --context is ignored. Using --env for API mode.", err=True)

    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        nodes = collector.get_nodes(effective_env)

        if ctx.output_format == 'table':
            table_data = []
            for node in nodes:
                table_data.append({
                    'name': node.get('name', ''),
                    'status': format_status(node.get('status', 'unknown')),
                    'instance_type': node.get('instanceType', '-'),
                    'zone': node.get('zone', '-'),
                    'cpu': node.get('capacity', {}).get('cpu', '-'),
                    'memory': node.get('capacity', {}).get('memory', '-'),
                })
            formatter.output(table_data, title="Nodes")
        else:
            formatter.output(nodes)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@k8s.command('logs')
@click.argument('pod')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--namespace', '-n', default='default', help='Namespace')
@click.option('--container', help='Container name')
@click.option('--tail', '-t', default=100, help='Number of lines')
@click.option('--follow', '-f', is_flag=True, help='Follow logs (not supported via API)')
@click.option('--since', '-s', help='Since duration (e.g., 1h, 30m)')
@click.option('--context', '-c', help='(Ignored) Use --env instead')
@click.pass_obj
def pod_logs(ctx, pod: str, env: Optional[str], namespace: str, container: Optional[str],
             tail: int, follow: bool, since: Optional[str], context: Optional[str]):
    """View pod logs"""
    _require_eks()

    if context:
        click.echo("Warning: --context is ignored. Using --env for API mode.", err=True)

    if follow:
        click.echo("Warning: --follow is not supported via API. Showing recent logs.", err=True)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        logs = collector.get_pod_logs(
            env=effective_env,
            pod=pod,
            namespace=namespace,
            container=container,
            tail=tail,
            since=since
        )

        # Logs come as a string from the API
        if isinstance(logs, str):
            click.echo(logs)
        elif isinstance(logs, list):
            for line in logs:
                click.echo(line)
        else:
            click.echo(logs)

    except KeyboardInterrupt:
        click.echo("\nStopped", err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@k8s.command('describe')
@click.argument('resource_type', type=click.Choice(['pod', 'service', 'deployment', 'ingress', 'node']))
@click.argument('name')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--namespace', '-n', default='default', help='Namespace')
@click.option('--context', '-c', help='(Ignored) Use --env instead')
@click.pass_obj
def describe_resource(ctx, resource_type: str, name: str, env: Optional[str], namespace: str,
                      context: Optional[str]):
    """Describe a Kubernetes resource"""
    _require_eks()

    if context:
        click.echo("Warning: --context is ignored. Using --env for API mode.", err=True)

    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        resource = collector.describe_k8s_resource(
            env=effective_env,
            resource_type=resource_type,
            name=name,
            namespace=namespace
        )

        formatter.output(resource, title=f"{resource_type.capitalize()}: {name}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@k8s.command('namespaces')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--context', '-c', help='(Ignored) Use --env instead')
@click.pass_obj
def list_namespaces(ctx, env: Optional[str], context: Optional[str]):
    """List Kubernetes namespaces"""
    _require_eks()

    if context:
        click.echo("Warning: --context is ignored. Using --env for API mode.", err=True)

    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        # Get namespaces via infrastructure endpoint
        infra = collector.get_infrastructure(effective_env)
        namespaces = infra.get('namespaces', [])

        if not namespaces:
            # Fallback: try k8s endpoint if available
            try:
                from dashborion.utils.api_client import get_api_client
                client = get_api_client()
                project = ctx.project
                response = client.get(f'/api/{project}/k8s/{effective_env}/namespaces')
                if response.status_code == 200:
                    data = response.json()
                    namespaces = data.get('namespaces', [])
            except Exception:
                pass

        if ctx.output_format == 'table':
            table_data = [{'name': ns} for ns in namespaces]
            formatter.output(table_data, title="Namespaces")
        else:
            formatter.output({'namespaces': namespaces})

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
