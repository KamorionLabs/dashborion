"""CLI configuration management for Dashborion"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to the config file

    Returns:
        Configuration dictionary
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}

    # Store the config path for reference
    config['_config_path'] = config_path

    return config


def get_default_config_path() -> Optional[str]:
    """Get the default configuration file path"""
    paths = [
        Path.home() / '.dashborion' / 'config.yaml',
        Path.home() / '.dashborion' / 'config.yml',
        Path.cwd() / 'dashborion.yaml',
        Path.cwd() / '.dashborion.yaml',
    ]

    for path in paths:
        if path.exists():
            return str(path)

    return None


def get_environment_config(config: Dict[str, Any], env: str) -> Dict[str, Any]:
    """
    Get configuration for a specific environment.

    Args:
        config: Full configuration dictionary
        env: Environment name

    Returns:
        Environment-specific configuration
    """
    environments = config.get('environments', {})
    env_config = environments.get(env, {})

    # Merge with defaults
    defaults = {
        'type': 'ecs',
        'aws_region': config.get('default_region', 'eu-west-3'),
        'aws_profile': config.get('default_profile'),
    }

    return {**defaults, **env_config}


def create_default_config(config_dir: Optional[str] = None) -> str:
    """
    Create a default configuration file.

    Args:
        config_dir: Directory for the config file (default: ~/.dashborion)

    Returns:
        Path to the created config file
    """
    if config_dir is None:
        config_dir = Path.home() / '.dashborion'

    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / 'config.yaml'

    default_config = """# Dashborion CLI Configuration
# See https://github.com/KamorionLabs/dashborion for documentation

# Default AWS settings
default_profile: default
default_region: eu-west-3

# Environment configurations
environments:
  staging:
    type: ecs  # ecs or eks
    cluster: my-staging-cluster
    aws_profile: my-staging-profile
    aws_region: eu-west-3
    services:
      - backend
      - frontend

  production:
    type: ecs
    cluster: my-production-cluster
    aws_profile: my-production-profile
    aws_region: eu-west-3
    services:
      - backend
      - frontend

  # Example EKS environment
  # eks-staging:
  #   type: eks
  #   context: arn:aws:eks:eu-west-3:123456789012:cluster/my-eks-cluster
  #   aws_profile: my-eks-profile
  #   namespaces:
  #     - staging
  #     - common

# CI/CD provider configuration (optional)
# ci_provider:
#   type: codepipeline  # codepipeline, argocd, jenkins, gitlab, bitbucket
#   config:
#     build_prefix: my-build
#     deploy_prefix: my-deploy

# Confluence publishing (optional)
# confluence:
#   url: https://your-company.atlassian.net/wiki
#   space_key: INFRA
#   # Credentials from environment: CONFLUENCE_USERNAME, CONFLUENCE_TOKEN

# Diagram generation defaults
# diagrams:
#   output_dir: ./diagrams
#   default_format: png
"""

    with open(config_path, 'w') as f:
        f.write(default_config)

    return str(config_path)


def validate_config(config: Dict[str, Any]) -> list:
    """
    Validate configuration and return list of warnings/errors.

    Args:
        config: Configuration dictionary

    Returns:
        List of warning/error messages
    """
    issues = []

    # Check for required fields
    if not config.get('environments'):
        issues.append("Warning: No environments configured")

    # Check each environment
    for env_name, env_config in config.get('environments', {}).items():
        env_type = env_config.get('type', 'ecs')

        if env_type == 'ecs' and not env_config.get('cluster'):
            issues.append(f"Warning: Environment '{env_name}' (ECS) has no cluster defined")

        if env_type == 'eks' and not env_config.get('context'):
            issues.append(f"Warning: Environment '{env_name}' (EKS) has no context defined")

    return issues
