"""Infrastructure command group for Dashborion CLI"""

import click
import sys
from typing import Optional

from dashborion.utils.output import OutputFormatter


@click.group()
def infra():
    """View infrastructure resources (ALB, RDS, ElastiCache, CloudFront)"""
    pass


@infra.command('show')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--resource', '-r', type=click.Choice(['all', 'alb', 'rds', 'redis', 'cloudfront', 'vpc']),
              default='all', help='Resource type to show')
@click.pass_obj
def show_infra(ctx, env: str, resource: str):
    """Show infrastructure overview for an environment"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        from dashborion.collectors.infrastructure import InfrastructureCollector
        collector = InfrastructureCollector(session)

        # Collect resources based on filter
        infra_data = {}

        if resource in ['all', 'alb']:
            infra_data['loadBalancers'] = collector.get_load_balancers(
                tags=env_config.get('discovery_tags', {})
            )

        if resource in ['all', 'rds']:
            infra_data['databases'] = collector.get_databases(
                tags=env_config.get('discovery_tags', {})
            )

        if resource in ['all', 'redis']:
            infra_data['caches'] = collector.get_caches(
                tags=env_config.get('discovery_tags', {})
            )

        if resource in ['all', 'cloudfront']:
            infra_data['distributions'] = collector.get_cloudfront_distributions(
                tags=env_config.get('discovery_tags', {})
            )

        if resource in ['all', 'vpc']:
            infra_data['vpcs'] = collector.get_vpcs(
                tags=env_config.get('discovery_tags', {})
            )

        formatter.output(infra_data, title=f"Infrastructure - {env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@infra.command('alb')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--name', '-n', help='ALB name filter')
@click.pass_obj
def show_alb(ctx, env: str, name: Optional[str]):
    """Show Application Load Balancer details"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        from dashborion.collectors.infrastructure import InfrastructureCollector
        collector = InfrastructureCollector(session)

        alb_data = collector.get_load_balancers(
            name_filter=name,
            tags=env_config.get('discovery_tags', {})
        )

        formatter.output(alb_data, title=f"Load Balancers - {env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@infra.command('rds')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--identifier', '-i', help='RDS instance identifier')
@click.pass_obj
def show_rds(ctx, env: str, identifier: Optional[str]):
    """Show RDS database details"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        from dashborion.collectors.infrastructure import InfrastructureCollector
        collector = InfrastructureCollector(session)

        rds_data = collector.get_databases(
            identifier_filter=identifier,
            tags=env_config.get('discovery_tags', {})
        )

        formatter.output(rds_data, title=f"Databases - {env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@infra.command('redis')
@click.option('--env', '-e', required=True, help='Environment name')
@click.pass_obj
def show_redis(ctx, env: str):
    """Show ElastiCache/Redis details"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        from dashborion.collectors.infrastructure import InfrastructureCollector
        collector = InfrastructureCollector(session)

        cache_data = collector.get_caches(
            tags=env_config.get('discovery_tags', {})
        )

        formatter.output(cache_data, title=f"Caches - {env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@infra.command('cloudfront')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--id', 'distribution_id', help='Distribution ID')
@click.pass_obj
def show_cloudfront(ctx, env: str, distribution_id: Optional[str]):
    """Show CloudFront distribution details"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        from dashborion.collectors.infrastructure import InfrastructureCollector
        collector = InfrastructureCollector(session)

        cf_data = collector.get_cloudfront_distributions(
            distribution_id=distribution_id,
            tags=env_config.get('discovery_tags', {})
        )

        formatter.output(cf_data, title=f"CloudFront Distributions - {env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@infra.command('network')
@click.option('--env', '-e', required=True, help='Environment name')
@click.pass_obj
def show_network(ctx, env: str):
    """Show network topology (VPC, subnets, security groups)"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        from dashborion.collectors.infrastructure import InfrastructureCollector
        collector = InfrastructureCollector(session)

        network_data = collector.get_network_topology(
            tags=env_config.get('discovery_tags', {})
        )

        formatter.output(network_data, title=f"Network - {env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@infra.command('security-groups')
@click.option('--env', '-e', required=True, help='Environment name')
@click.option('--id', 'sg_id', help='Security group ID')
@click.pass_obj
def show_security_groups(ctx, env: str, sg_id: Optional[str]):
    """Show security group rules"""
    from dashborion.config.cli_config import get_environment_config

    env_config = get_environment_config(ctx.config or {}, env)
    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        from dashborion.collectors.infrastructure import InfrastructureCollector
        collector = InfrastructureCollector(session)

        sg_data = collector.get_security_groups(
            sg_id=sg_id,
            tags=env_config.get('discovery_tags', {})
        )

        formatter.output(sg_data, title=f"Security Groups - {env}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
