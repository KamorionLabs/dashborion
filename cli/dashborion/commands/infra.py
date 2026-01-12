"""Infrastructure command group for Dashborion CLI - API-based implementation"""

import click
import sys
from typing import Optional

from dashborion.utils.output import OutputFormatter, format_status


@click.group()
def infra():
    """View infrastructure resources (ALB, RDS, ElastiCache, CloudFront)"""
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


@infra.command('show')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--resource', '-r', type=click.Choice(['all', 'alb', 'rds', 'redis', 'cloudfront', 'vpc']),
              default='all', help='Resource type to show')
@click.pass_obj
def show_infra(ctx, env: Optional[str], resource: str):
    """Show infrastructure overview for an environment"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        infra_data = collector.get_infrastructure(effective_env)

        # Filter resources if requested
        if resource != 'all':
            resource_map = {
                'alb': 'loadBalancers',
                'rds': 'databases',
                'redis': 'caches',
                'cloudfront': 'distributions',
                'vpc': 'vpcs'
            }
            key = resource_map.get(resource)
            if key and key in infra_data:
                infra_data = {key: infra_data[key]}

        formatter.output(infra_data, title=f"Infrastructure - {effective_env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('alb')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--name', '-n', help='ALB name filter')
@click.pass_obj
def show_alb(ctx, env: Optional[str], name: Optional[str]):
    """Show Application Load Balancer details"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        alb_data = collector.get_load_balancers(effective_env, name_filter=name)

        if ctx.output_format == 'table':
            table_data = []
            for alb in alb_data:
                dns = alb.get('dnsName', alb.get('dns_name', '-'))
                table_data.append({
                    'name': alb.get('name', '-'),
                    'dns': dns[:40] + '...' if len(dns) > 40 else dns,
                    'scheme': alb.get('scheme', '-'),
                    'state': format_status(alb.get('state', 'unknown')),
                    'type': alb.get('type', 'application'),
                })
            formatter.output(table_data, title=f"Load Balancers - {effective_env}")
        else:
            formatter.output(alb_data, title=f"Load Balancers - {effective_env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('rds')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--identifier', '-i', help='RDS instance identifier')
@click.pass_obj
def show_rds(ctx, env: Optional[str], identifier: Optional[str]):
    """Show RDS database details"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        rds_data = collector.get_databases(effective_env, identifier_filter=identifier)

        if ctx.output_format == 'table':
            table_data = []
            for db in rds_data:
                table_data.append({
                    'identifier': db.get('identifier', '-'),
                    'engine': f"{db.get('engine', '-')} {db.get('engineVersion', '')}",
                    'instance': db.get('instanceClass', '-'),
                    'status': format_status(db.get('status', 'unknown')),
                    'az': db.get('availabilityZone', '-'),
                })
            formatter.output(table_data, title=f"Databases - {effective_env}")
        else:
            formatter.output(rds_data, title=f"Databases - {effective_env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('redis')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.pass_obj
def show_redis(ctx, env: Optional[str]):
    """Show ElastiCache/Redis details"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        cache_data = collector.get_caches(effective_env)

        if ctx.output_format == 'table':
            table_data = []
            for cache in cache_data:
                table_data.append({
                    'id': cache.get('clusterId', cache.get('cluster_id', '-')),
                    'engine': cache.get('engine', 'redis'),
                    'node_type': cache.get('nodeType', cache.get('node_type', '-')),
                    'nodes': cache.get('numCacheNodes', cache.get('num_nodes', '-')),
                    'status': format_status(cache.get('status', 'unknown')),
                })
            formatter.output(table_data, title=f"Caches - {effective_env}")
        else:
            formatter.output(cache_data, title=f"Caches - {effective_env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('cloudfront')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--id', 'distribution_id', help='Distribution ID')
@click.pass_obj
def show_cloudfront(ctx, env: Optional[str], distribution_id: Optional[str]):
    """Show CloudFront distribution details"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        cf_data = collector.get_cloudfront_distributions(effective_env, distribution_id=distribution_id)

        if ctx.output_format == 'table':
            table_data = []
            for dist in cf_data:
                aliases = dist.get('aliases', [])
                alias_str = aliases[0] if aliases else '-'
                table_data.append({
                    'id': dist.get('id', '-'),
                    'domain': dist.get('domainName', dist.get('domain_name', '-'))[:35],
                    'alias': alias_str[:30],
                    'status': format_status(dist.get('status', 'unknown')),
                    'enabled': 'Yes' if dist.get('enabled', True) else 'No',
                })
            formatter.output(table_data, title=f"CloudFront - {effective_env}")
        else:
            formatter.output(cf_data, title=f"CloudFront Distributions - {effective_env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('network')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.pass_obj
def show_network(ctx, env: Optional[str]):
    """Show network topology (VPC, subnets, security groups)"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        network_data = collector.get_routing_details(effective_env)

        formatter.output(network_data, title=f"Network - {effective_env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('security-groups')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--id', 'sg_id', required=True, help='Security group ID')
@click.pass_obj
def show_security_groups(ctx, env: Optional[str], sg_id: str):
    """Show security group rules"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        sg_data = collector.get_security_group(effective_env, sg_id)

        if ctx.output_format == 'table':
            # Format ingress rules
            click.echo(f"\nIngress Rules for {sg_id}:")
            ingress_data = []
            for rule in sg_data.get('ingressRules', sg_data.get('ingress_rules', [])):
                ingress_data.append({
                    'protocol': rule.get('protocol', '-'),
                    'port_range': f"{rule.get('fromPort', '*')}-{rule.get('toPort', '*')}",
                    'source': rule.get('source', rule.get('cidr', '-'))[:30],
                    'description': (rule.get('description', '-') or '-')[:30],
                })
            formatter.output(ingress_data, title="Ingress")

            # Format egress rules
            click.echo(f"\nEgress Rules for {sg_id}:")
            egress_data = []
            for rule in sg_data.get('egressRules', sg_data.get('egress_rules', [])):
                egress_data.append({
                    'protocol': rule.get('protocol', '-'),
                    'port_range': f"{rule.get('fromPort', '*')}-{rule.get('toPort', '*')}",
                    'destination': rule.get('destination', rule.get('cidr', '-'))[:30],
                    'description': (rule.get('description', '-') or '-')[:30],
                })
            formatter.output(egress_data, title="Egress")
        else:
            formatter.output(sg_data, title=f"Security Group {sg_id}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('vpc')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.pass_obj
def show_vpcs(ctx, env: Optional[str]):
    """Show VPCs"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        vpcs = collector.get_vpcs(effective_env)

        if ctx.output_format == 'table':
            table_data = []
            for vpc in vpcs:
                table_data.append({
                    'id': vpc.get('vpcId', vpc.get('id', '-')),
                    'cidr': vpc.get('cidrBlock', vpc.get('cidr', '-')),
                    'name': vpc.get('name', '-'),
                    'state': format_status(vpc.get('state', 'unknown')),
                })
            formatter.output(table_data, title=f"VPCs - {effective_env}")
        else:
            formatter.output(vpcs, title=f"VPCs - {effective_env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('enis')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--vpc', help='Filter by VPC ID')
@click.option('--subnet', help='Filter by subnet ID')
@click.option('--ip', help='Search by IP address')
@click.pass_obj
def show_enis(ctx, env: Optional[str], vpc: Optional[str], subnet: Optional[str], ip: Optional[str]):
    """Show ENI details"""
    formatter = OutputFormatter(ctx.output_format)

    try:
        collector, env_config, effective_env = _get_collector(ctx, env)
        enis = collector.get_enis(effective_env, vpc_id=vpc, subnet_id=subnet, search_ip=ip)

        if ctx.output_format == 'table':
            table_data = []
            for eni in enis:
                table_data.append({
                    'id': eni.get('eniId', eni.get('id', '-')),
                    'private_ip': eni.get('privateIp', eni.get('private_ip', '-')),
                    'status': format_status(eni.get('status', 'unknown')),
                    'type': eni.get('interfaceType', eni.get('type', '-')),
                    'description': (eni.get('description', '-') or '-')[:30],
                })
            formatter.output(table_data, title=f"ENIs - {effective_env}")
        else:
            formatter.output(enis, title=f"ENIs - {effective_env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('invalidate')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--id', '-i', 'distribution_id', required=True, help='CloudFront distribution ID')
@click.option('--paths', '-p', default='/*', help='Paths to invalidate (comma-separated, default: /*)')
@click.pass_obj
def invalidate_cloudfront(ctx, env: Optional[str], distribution_id: str, paths: str):
    """Invalidate CloudFront cache"""
    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        path_list = [p.strip() for p in paths.split(',')]
        click.echo(f"Invalidating CloudFront {distribution_id}...")
        click.echo(f"  Paths: {path_list}")

        result = collector.invalidate_cloudfront(effective_env, distribution_id, path_list)

        if result.get('success') or result.get('invalidationId'):
            click.echo("Invalidation created successfully")
            if result.get('invalidationId'):
                click.echo(f"  Invalidation ID: {result.get('invalidationId')}")
            click.echo(f"  Status: {result.get('status', 'InProgress')}")
        else:
            click.echo(f"Invalidation failed: {result.get('error')}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('rds-control')
@click.option('--env', '-e', help='Environment name (default: from context)')
@click.option('--action', '-a', type=click.Choice(['start', 'stop']), required=True, help='Action to perform')
@click.pass_obj
def control_rds(ctx, env: Optional[str], action: str):
    """Start or stop RDS database"""
    try:
        collector, env_config, effective_env = _get_collector(ctx, env)

        click.echo(f"{'Starting' if action == 'start' else 'Stopping'} RDS in {effective_env}...")

        result = collector.control_rds(effective_env, action)

        if result.get('success'):
            click.echo(f"RDS {action} initiated successfully")
        else:
            click.echo(f"RDS control failed: {result.get('error')}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
