"""
Dynamic configuration system for the Operations Dashboard.
Supports multi-client, multi-provider configurations loaded from environment variables.
"""

import os
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from functools import lru_cache


@dataclass
class NamingPattern:
    """Resource naming patterns - supports placeholders {project}, {env}, {service}"""
    cluster: str = "{project}-{env}-cluster"
    service: str = "{project}-{env}-{service}"
    task_family: str = "{project}-{env}-{service}"
    build_pipeline: str = "{project}-build-{service}"
    deploy_pipeline: str = "{project}-deploy-{service}-{env}"
    log_group: str = "/ecs/{project}-{env}/{service}"
    secret: str = "{project}/{env}/{service}"
    ecr_repo: str = "{project}-{service}"
    db_identifier: str = "{project}-{env}"

    def format(self, pattern_name: str, **kwargs) -> str:
        """Format a pattern with given values"""
        pattern = getattr(self, pattern_name, None)
        if not pattern:
            raise ValueError(f"Unknown pattern: {pattern_name}")
        return pattern.format(**kwargs)


@dataclass
class EnvironmentConfig:
    """Configuration for a single environment"""
    account_id: str
    services: List[str]
    region: str = "eu-west-3"
    cluster_name: Optional[str] = None  # Override naming pattern
    namespace: Optional[str] = None  # For EKS

    def to_dict(self) -> dict:
        return {
            'account_id': self.account_id,
            'services': self.services,
            'region': self.region,
            'cluster_name': self.cluster_name,
            'namespace': self.namespace
        }


@dataclass
class CIProviderConfig:
    """CI/CD provider configuration"""
    type: str  # "codepipeline", "github_actions", "bitbucket", "gitlab", "argocd"
    config: Dict[str, Any] = field(default_factory=dict)

    # GitHub Actions specific
    @property
    def github_owner(self) -> Optional[str]:
        return self.config.get('owner')

    @property
    def github_repo_pattern(self) -> str:
        return self.config.get('repo_pattern', '{project}-{service}')

    @property
    def github_token_secret(self) -> Optional[str]:
        return self.config.get('token_secret')

    # Bitbucket specific
    @property
    def bitbucket_workspace(self) -> Optional[str]:
        return self.config.get('workspace')

    # ArgoCD specific
    @property
    def argocd_url(self) -> Optional[str]:
        return self.config.get('api_url')

    @property
    def argocd_token_secret(self) -> Optional[str]:
        return self.config.get('token_secret')


@dataclass
class OrchestratorConfig:
    """Container orchestrator configuration"""
    type: str  # "ecs", "eks", "argocd"
    config: Dict[str, Any] = field(default_factory=dict)

    # EKS specific
    @property
    def eks_cluster_name(self) -> Optional[str]:
        return self.config.get('cluster_name')

    @property
    def default_namespace(self) -> str:
        return self.config.get('namespace', 'default')

    # ArgoCD specific
    @property
    def argocd_url(self) -> Optional[str]:
        return self.config.get('api_url')


@dataclass
class DashboardConfig:
    """Main dashboard configuration"""
    project_name: str
    region: str
    shared_services_account: str
    sso_portal_url: str
    environments: Dict[str, EnvironmentConfig]
    naming_pattern: NamingPattern
    ci_provider: CIProviderConfig
    orchestrator: OrchestratorConfig

    # Optional GitHub configuration for commit links
    github_org: Optional[str] = None

    # Console URL patterns
    console_urls: Dict[str, str] = field(default_factory=lambda: {
        'ecs_cluster': "https://{region}.console.aws.amazon.com/ecs/v2/clusters/{cluster}/services?region={region}",
        'ecs_service': "https://{region}.console.aws.amazon.com/ecs/v2/clusters/{cluster}/services/{service}?region={region}",
        'ecs_task': "https://{region}.console.aws.amazon.com/ecs/v2/clusters/{cluster}/tasks/{task}?region={region}",
        'cloudwatch': "https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#dashboards",
        'codepipeline': "https://{region}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline}/view?region={region}",
        'ecr': "https://{region}.console.aws.amazon.com/ecr/repositories/private/{account}/{repo}?region={region}",
        'rds': "https://{region}.console.aws.amazon.com/rds/home?region={region}#database:id={db};is-cluster=false",
        'eks_cluster': "https://{region}.console.aws.amazon.com/eks/home?region={region}#/clusters/{cluster}",
        'eks_workload': "https://{region}.console.aws.amazon.com/eks/home?region={region}#/clusters/{cluster}/workloads?namespace={namespace}",
    })

    def get_environment(self, env: str) -> Optional[EnvironmentConfig]:
        """Get environment configuration by name"""
        return self.environments.get(env)

    def get_cluster_name(self, env: str) -> str:
        """Get cluster name for an environment"""
        env_config = self.get_environment(env)
        if env_config and env_config.cluster_name:
            return env_config.cluster_name
        return self.naming_pattern.format('cluster', project=self.project_name, env=env)

    def get_service_name(self, env: str, service: str) -> str:
        """Get full service name"""
        return self.naming_pattern.format('service', project=self.project_name, env=env, service=service)

    def get_log_group(self, env: str, service: str) -> str:
        """Get CloudWatch log group"""
        return self.naming_pattern.format('log_group', project=self.project_name, env=env, service=service)

    def get_build_pipeline_name(self, service: str) -> str:
        """Get build pipeline name"""
        return self.naming_pattern.format('build_pipeline', project=self.project_name, service=service)

    def get_deploy_pipeline_name(self, env: str, service: str) -> str:
        """Get deploy pipeline name"""
        return self.naming_pattern.format('deploy_pipeline', project=self.project_name, env=env, service=service)

    def get_ecr_repo(self, service: str) -> str:
        """Get ECR repository name"""
        return self.naming_pattern.format('ecr_repo', project=self.project_name, service=service)

    def get_db_identifier(self, env: str) -> str:
        """Get RDS database identifier"""
        return self.naming_pattern.format('db_identifier', project=self.project_name, env=env)

    def get_cross_account_role(self, env: str, role_type: str = 'read') -> str:
        """Get cross-account IAM role ARN"""
        env_config = self.get_environment(env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        role_name = f"{self.project_name}-dashboard-{role_type}-role"
        return f"arn:aws:iam::{env_config.account_id}:role/{role_name}"

    def build_console_url(self, url_type: str, **kwargs) -> str:
        """Build a console URL from template"""
        template = self.console_urls.get(url_type)
        if not template:
            raise ValueError(f"Unknown console URL type: {url_type}")
        return template.format(**kwargs)

    def to_dict(self) -> dict:
        """Convert config to dictionary for API response"""
        return {
            'projectName': self.project_name,
            'region': self.region,
            'ssoPortalUrl': self.sso_portal_url,
            'ciProvider': self.ci_provider.type,
            'orchestrator': self.orchestrator.type,
            'githubOrg': self.github_org,
            'environments': {
                env: {
                    'accountId': cfg.account_id,
                    'services': cfg.services,
                    'region': cfg.region
                }
                for env, cfg in self.environments.items()
            }
        }


@lru_cache(maxsize=1)
def get_config() -> DashboardConfig:
    """
    Load configuration from environment variables.
    Uses caching to avoid repeated parsing.
    """

    # Core settings
    project_name = os.environ.get('PROJECT_NAME', 'myproject')
    region = os.environ.get('AWS_REGION_DEFAULT', os.environ.get('AWS_REGION', 'eu-west-3'))
    shared_services_account = os.environ.get('SHARED_SERVICES_ACCOUNT', '')
    sso_portal_url = os.environ.get('SSO_PORTAL_URL', '')

    # Parse environments JSON
    environments_raw = json.loads(os.environ.get('ENVIRONMENTS', '{}'))
    environments = {}
    for env_name, env_data in environments_raw.items():
        environments[env_name] = EnvironmentConfig(
            account_id=env_data.get('account_id', ''),
            services=env_data.get('services', []),
            region=env_data.get('region', region),
            cluster_name=env_data.get('cluster_name'),
            namespace=env_data.get('namespace')
        )

    # Parse naming pattern
    naming_raw = json.loads(os.environ.get('NAMING_PATTERN', '{}'))
    naming_pattern = NamingPattern(
        cluster=naming_raw.get('cluster', NamingPattern.cluster),
        service=naming_raw.get('service', NamingPattern.service),
        task_family=naming_raw.get('task_family', NamingPattern.task_family),
        build_pipeline=naming_raw.get('build_pipeline', NamingPattern.build_pipeline),
        deploy_pipeline=naming_raw.get('deploy_pipeline', NamingPattern.deploy_pipeline),
        log_group=naming_raw.get('log_group', NamingPattern.log_group),
        secret=naming_raw.get('secret', NamingPattern.secret),
        ecr_repo=naming_raw.get('ecr_repo', NamingPattern.ecr_repo),
        db_identifier=naming_raw.get('db_identifier', NamingPattern.db_identifier)
    )

    # Parse CI provider config
    ci_raw = json.loads(os.environ.get('CI_PROVIDER', '{"type": "codepipeline"}'))
    ci_provider = CIProviderConfig(
        type=ci_raw.get('type', 'codepipeline'),
        config=ci_raw.get('config', {})
    )

    # Parse orchestrator config
    orch_raw = json.loads(os.environ.get('ORCHESTRATOR', '{"type": "ecs"}'))
    orchestrator = OrchestratorConfig(
        type=orch_raw.get('type', 'ecs'),
        config=orch_raw.get('config', {})
    )

    # GitHub org (for commit links)
    github_org = os.environ.get('GITHUB_ORG', ci_provider.github_owner)

    return DashboardConfig(
        project_name=project_name,
        region=region,
        shared_services_account=shared_services_account,
        sso_portal_url=sso_portal_url,
        environments=environments,
        naming_pattern=naming_pattern,
        ci_provider=ci_provider,
        orchestrator=orchestrator,
        github_org=github_org
    )


def clear_config_cache():
    """Clear the config cache (useful for testing)"""
    get_config.cache_clear()


# Helper functions for backwards compatibility with existing code
def get_environments() -> Dict[str, EnvironmentConfig]:
    """Get all environment configurations"""
    return get_config().environments


def get_project_name() -> str:
    """Get project name"""
    return get_config().project_name


def get_region() -> str:
    """Get default region"""
    return get_config().region


def get_shared_services_account() -> str:
    """Get shared services account ID"""
    return get_config().shared_services_account


def get_sso_portal_url() -> str:
    """Get SSO portal URL"""
    return get_config().sso_portal_url
