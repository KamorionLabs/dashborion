#!/usr/bin/env python3
"""
Dashborion CLI - Multi-cloud infrastructure management tool

Supports:
- ECS (Fargate & EC2) and EKS/Kubernetes
- AWS CodePipeline, ArgoCD, Jenkins, GitLab CI, Bitbucket Pipelines
- Architecture diagram generation with Confluence publishing
"""

import click
import os
import sys
import json
import yaml
from typing import Optional
from pathlib import Path

from dashborion.commands import services, infra, diagram, k8s, pipelines, auth
from dashborion.config.cli_config import load_config, get_environment_config
from dashborion.utils.output import OutputFormatter

# Version
__version__ = "0.1.0"


class DashborionContext:
    """Context object passed to all commands"""

    def __init__(self):
        self.config = None
        self.profile = None
        self.region = None
        self.output_format = 'table'
        self.verbose = False
        self.env = None

    def get_aws_session(self, profile: Optional[str] = None, region: Optional[str] = None):
        """Get boto3 session with specified or configured profile/region"""
        import boto3

        profile = profile or self.profile or self.config.get('default_profile')
        region = region or self.region or self.config.get('default_region', 'eu-west-3')

        if profile:
            return boto3.Session(profile_name=profile, region_name=region)
        return boto3.Session(region_name=region)

    def get_env_config(self, env: str) -> dict:
        """Get configuration for a specific environment"""
        if not self.config:
            return {}
        return get_environment_config(self.config, env)


pass_context = click.make_pass_decorator(DashborionContext, ensure=True)


@click.group()
@click.version_option(version=__version__, prog_name='dashborion')
@click.option('--profile', '-p', envvar='AWS_PROFILE',
              help='AWS profile to use')
@click.option('--region', '-r', envvar='AWS_REGION',
              help='AWS region (default: from config or eu-west-3)')
@click.option('--config', '-c', 'config_path', envvar='DASHBORION_CONFIG',
              type=click.Path(exists=True),
              help='Path to config file (default: ~/.dashborion/config.yaml)')
@click.option('--output', '-o', 'output_format',
              type=click.Choice(['table', 'json', 'yaml']),
              default='table',
              help='Output format (default: table)')
@click.option('--verbose', '-v', is_flag=True,
              help='Enable verbose output')
@pass_context
def cli(ctx, profile, region, config_path, output_format, verbose):
    """
    Dashborion - Multi-cloud infrastructure dashboard CLI

    Visualize and manage ECS, EKS, and CI/CD pipelines from the command line.

    Examples:

    \b
      # List services in staging
      dashborion services list --env staging

    \b
      # Show infrastructure overview
      dashborion infra show --env production --output json

    \b
      # Generate architecture diagram
      dashborion diagram generate --env staging --output architecture.png

    \b
      # List Kubernetes pods
      dashborion k8s pods --context my-cluster --namespace default
    """
    ctx.verbose = verbose
    ctx.output_format = output_format
    ctx.profile = profile
    ctx.region = region

    # Load configuration
    if config_path:
        ctx.config = load_config(config_path)
    else:
        # Try default locations
        default_paths = [
            Path.home() / '.dashborion' / 'config.yaml',
            Path.home() / '.dashborion' / 'config.yml',
            Path.cwd() / 'dashborion.yaml',
            Path.cwd() / '.dashborion.yaml',
        ]
        for path in default_paths:
            if path.exists():
                ctx.config = load_config(str(path))
                if ctx.verbose:
                    click.echo(f"Loaded config from {path}", err=True)
                break
        else:
            ctx.config = {}


# Register command groups
cli.add_command(auth.auth)
cli.add_command(services.services)
cli.add_command(infra.infra)
cli.add_command(diagram.diagram)
cli.add_command(k8s.k8s)
cli.add_command(pipelines.pipelines)


@cli.command()
@pass_context
def config(ctx):
    """Show current configuration"""
    formatter = OutputFormatter(ctx.output_format)

    config_info = {
        'profile': ctx.profile or ctx.config.get('default_profile', 'default'),
        'region': ctx.region or ctx.config.get('default_region', 'eu-west-3'),
        'environments': list(ctx.config.get('environments', {}).keys()),
        'config_file': ctx.config.get('_config_path', 'not loaded'),
    }

    formatter.output(config_info, title="Configuration")


@cli.command()
@click.option('--env', '-e', required=True,
              help='Environment name')
@pass_context
def status(ctx, env):
    """Quick status check for an environment"""
    env_config = ctx.get_env_config(env)
    if not env_config:
        click.echo(f"Environment '{env}' not found in configuration", err=True)
        sys.exit(1)

    formatter = OutputFormatter(ctx.output_format)

    try:
        session = ctx.get_aws_session(
            profile=env_config.get('aws_profile'),
            region=env_config.get('aws_region')
        )

        env_type = env_config.get('type', 'ecs')

        if env_type == 'ecs':
            from dashborion.collectors.ecs import ECSCollector
            collector = ECSCollector(session)
            status_info = collector.get_cluster_status(env_config.get('cluster'))
        elif env_type == 'eks':
            from dashborion.collectors.eks import EKSCollector
            collector = EKSCollector(session, env_config.get('context'))
            status_info = collector.get_cluster_status()
        else:
            click.echo(f"Unknown environment type: {env_type}", err=True)
            sys.exit(1)

        formatter.output(status_info, title=f"{env} Status")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point"""
    cli(auto_envvar_prefix='DASHBORION')


if __name__ == '__main__':
    main()
