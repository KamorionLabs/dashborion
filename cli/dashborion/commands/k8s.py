"""Kubernetes command group for Dashborion CLI"""

import click
import sys
from typing import Optional

from dashborion.utils.output import OutputFormatter, format_status, format_datetime


@click.group()
def k8s():
    """Kubernetes resources (pods, services, deployments)"""
    pass


@k8s.command('pods')
@click.option('--context', '-c', required=True, help='Kubernetes context')
@click.option('--namespace', '-n', default='default', help='Namespace (default: default)')
@click.option('--all-namespaces', '-A', is_flag=True, help='All namespaces')
@click.option('--selector', '-l', help='Label selector')
@click.pass_obj
def list_pods(ctx, context: str, namespace: str, all_namespaces: bool, selector: Optional[str]):
    """List Kubernetes pods"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        from dashborion.collectors.k8s_cli import KubernetesCollector

        collector = KubernetesCollector(context)

        if all_namespaces:
            pods = collector.get_pods(namespace=None, selector=selector)
        else:
            pods = collector.get_pods(namespace=namespace, selector=selector)

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
@click.option('--context', '-c', required=True, help='Kubernetes context')
@click.option('--namespace', '-n', default='default', help='Namespace')
@click.option('--all-namespaces', '-A', is_flag=True, help='All namespaces')
@click.pass_obj
def list_services(ctx, context: str, namespace: str, all_namespaces: bool):
    """List Kubernetes services"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        from dashborion.collectors.k8s_cli import KubernetesCollector

        collector = KubernetesCollector(context)

        if all_namespaces:
            services = collector.get_services(namespace=None)
        else:
            services = collector.get_services(namespace=namespace)

        if ctx.output_format == 'table':
            table_data = []
            for svc in services:
                table_data.append({
                    'namespace': svc.get('namespace', '-'),
                    'name': svc.get('name', ''),
                    'type': svc.get('type', '-'),
                    'cluster_ip': svc.get('clusterIP', '-'),
                    'ports': svc.get('ports', '-'),
                })
            formatter.output(table_data, title="Services")
        else:
            formatter.output(services)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@k8s.command('deployments')
@click.option('--context', '-c', required=True, help='Kubernetes context')
@click.option('--namespace', '-n', default='default', help='Namespace')
@click.option('--all-namespaces', '-A', is_flag=True, help='All namespaces')
@click.pass_obj
def list_deployments(ctx, context: str, namespace: str, all_namespaces: bool):
    """List Kubernetes deployments"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        from dashborion.collectors.k8s_cli import KubernetesCollector

        collector = KubernetesCollector(context)

        if all_namespaces:
            deployments = collector.get_deployments(namespace=None)
        else:
            deployments = collector.get_deployments(namespace=namespace)

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
        sys.exit(1)


@k8s.command('ingresses')
@click.option('--context', '-c', required=True, help='Kubernetes context')
@click.option('--namespace', '-n', default='default', help='Namespace')
@click.option('--all-namespaces', '-A', is_flag=True, help='All namespaces')
@click.pass_obj
def list_ingresses(ctx, context: str, namespace: str, all_namespaces: bool):
    """List Kubernetes ingresses"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        from dashborion.collectors.k8s_cli import KubernetesCollector

        collector = KubernetesCollector(context)

        if all_namespaces:
            ingresses = collector.get_ingresses(namespace=None)
        else:
            ingresses = collector.get_ingresses(namespace=namespace)

        if ctx.output_format == 'table':
            table_data = []
            for ing in ingresses:
                table_data.append({
                    'namespace': ing.get('namespace', '-'),
                    'name': ing.get('name', ''),
                    'class': ing.get('ingressClass', '-'),
                    'hosts': ing.get('hosts', '-'),
                    'address': ing.get('address', '-'),
                })
            formatter.output(table_data, title="Ingresses")
        else:
            formatter.output(ingresses)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@k8s.command('nodes')
@click.option('--context', '-c', required=True, help='Kubernetes context')
@click.pass_obj
def list_nodes(ctx, context: str):
    """List Kubernetes nodes"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        from dashborion.collectors.k8s_cli import KubernetesCollector

        collector = KubernetesCollector(context)
        nodes = collector.get_nodes()

        if ctx.output_format == 'table':
            table_data = []
            for node in nodes:
                table_data.append({
                    'name': node.get('name', ''),
                    'status': format_status(node.get('status', 'unknown')),
                    'roles': node.get('roles', '-'),
                    'version': node.get('version', '-'),
                    'instance_type': node.get('instanceType', '-'),
                    'zone': node.get('zone', '-'),
                })
            formatter.output(table_data, title="Nodes")
        else:
            formatter.output(nodes)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@k8s.command('logs')
@click.argument('pod')
@click.option('--context', '-c', required=True, help='Kubernetes context')
@click.option('--namespace', '-n', default='default', help='Namespace')
@click.option('--container', help='Container name')
@click.option('--tail', '-t', default=100, help='Number of lines')
@click.option('--follow', '-f', is_flag=True, help='Follow logs')
@click.option('--since', '-s', help='Since duration (e.g., 1h, 30m)')
@click.pass_obj
def pod_logs(ctx, pod: str, context: str, namespace: str, container: Optional[str],
             tail: int, follow: bool, since: Optional[str]):
    """View pod logs"""
    try:
        from dashborion.collectors.k8s_cli import KubernetesCollector

        collector = KubernetesCollector(context)
        collector.stream_logs(
            pod=pod,
            namespace=namespace,
            container=container,
            tail=tail,
            follow=follow,
            since=since
        )

    except KeyboardInterrupt:
        click.echo("\nStopped following logs", err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@k8s.command('describe')
@click.argument('resource_type', type=click.Choice(['pod', 'service', 'deployment', 'ingress', 'node']))
@click.argument('name')
@click.option('--context', '-c', required=True, help='Kubernetes context')
@click.option('--namespace', '-n', default='default', help='Namespace')
@click.pass_obj
def describe_resource(ctx, resource_type: str, name: str, context: str, namespace: str):
    """Describe a Kubernetes resource"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        from dashborion.collectors.k8s_cli import KubernetesCollector

        collector = KubernetesCollector(context)
        resource = collector.describe(resource_type, name, namespace)

        formatter.output(resource, title=f"{resource_type.capitalize()}: {name}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
