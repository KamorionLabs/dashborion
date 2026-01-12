"""
Dynamic configuration system for the Operations Dashboard.
Supports multi-project, multi-environment configurations loaded from SSM Parameter Store.
"""

import os
import json
import boto3
from botocore.exceptions import ClientError
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from functools import lru_cache

# SSM client (lazy initialized)
_ssm_client = None


def _get_ssm_client():
    """Get or create SSM client."""
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client('ssm')
    return _ssm_client


def _load_ssm_config(prefix: str) -> tuple[dict, dict]:
    """
    Load PROJECTS and CROSS_ACCOUNT_ROLES from SSM Parameter Store.

    Projects are discovered via GetParametersByPath under {prefix}/projects/
    Cross-account roles are loaded from {prefix}/cross-account-roles

    Args:
        prefix: SSM parameter prefix (e.g., /dashborion/rubix)

    Returns:
        Tuple of (projects_dict, cross_account_roles_dict)
    """
    ssm = _get_ssm_client()

    # Discover all project parameters under {prefix}/projects/
    projects = {}
    paginator = ssm.get_paginator('get_parameters_by_path')
    for page in paginator.paginate(
        Path=f"{prefix}/projects",
        Recursive=False,
        WithDecryption=True
    ):
        for param in page.get('Parameters', []):
            project_data = json.loads(param['Value'])
            project_id = project_data.get('id') or param['Name'].split('/')[-1]
            projects[project_id] = project_data

    # Load cross-account roles
    cross_account_roles = {}
    try:
        response = ssm.get_parameter(
            Name=f"{prefix}/cross-account-roles",
            WithDecryption=True
        )
        cross_account_roles = json.loads(response['Parameter']['Value'])
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            pass  # No cross-account roles configured
        else:
            raise

    return projects, cross_account_roles


@dataclass
class NamingPattern:
    """Resource naming patterns - supports placeholders {project}, {env}, {service}"""
    cluster: str = "{project}-{env}"
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
class InfrastructureConfig:
    """Infrastructure discovery configuration for an environment"""
    discovery_tags: Dict[str, str] = field(default_factory=dict)  # Tags for resource discovery
    databases: List[str] = field(default_factory=list)  # Database types to discover
    caches: List[str] = field(default_factory=list)  # Cache types to discover


@dataclass
class EnvironmentConfig:
    """Configuration for a single environment within a project"""
    account_id: str
    services: List[str]
    region: str = "eu-west-3"
    cluster_name: Optional[str] = None  # Override naming pattern
    namespace: Optional[str] = None  # For EKS
    read_role_arn: Optional[str] = None  # Override cross-account read role
    action_role_arn: Optional[str] = None  # Override cross-account action role
    status: Optional[str] = None  # Environment status (active, deployed, planned)
    infrastructure: Optional[InfrastructureConfig] = None  # Infrastructure discovery config

    def to_dict(self) -> dict:
        result = {
            'accountId': self.account_id,
            'services': self.services,
            'region': self.region,
            'clusterName': self.cluster_name,
            'namespace': self.namespace,
            'status': self.status
        }
        if self.read_role_arn:
            result['readRoleArn'] = self.read_role_arn
        if self.action_role_arn:
            result['actionRoleArn'] = self.action_role_arn
        if self.infrastructure:
            result['infrastructure'] = {
                'discoveryTags': self.infrastructure.discovery_tags,
                'databases': self.infrastructure.databases,
                'caches': self.infrastructure.caches
            }
        return result


@dataclass
class CrossAccountRole:
    """IAM roles for cross-account access"""
    read_role_arn: str
    action_role_arn: str


@dataclass
class ProjectConfig:
    """Configuration for a single project"""
    name: str
    display_name: str
    environments: Dict[str, EnvironmentConfig]
    idp_group_mapping: Optional[Dict[str, Any]] = None

    def get_environment(self, env: str) -> Optional[EnvironmentConfig]:
        """Get environment configuration by name"""
        return self.environments.get(env)

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'displayName': self.display_name,
            'environments': {
                env: cfg.to_dict()
                for env, cfg in self.environments.items()
            }
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
    region: str
    shared_services_account: str
    sso_portal_url: str
    projects: Dict[str, ProjectConfig]
    cross_account_roles: Dict[str, CrossAccountRole]  # Indexed by account ID
    naming_pattern: NamingPattern
    ci_provider: CIProviderConfig
    orchestrator: OrchestratorConfig

    # Optional GitHub configuration for commit links
    github_org: Optional[str] = None

    # Feature flags for frontend
    features: Dict[str, bool] = field(default_factory=dict)

    # Comparison configuration (groups for env pairing)
    comparison: Dict[str, Any] = field(default_factory=dict)

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

    def get_project(self, project: str) -> Optional[ProjectConfig]:
        """Get project configuration by name"""
        return self.projects.get(project)

    def get_environment(self, project: str, env: str) -> Optional[EnvironmentConfig]:
        """Get environment configuration for a project"""
        proj = self.get_project(project)
        if proj:
            return proj.get_environment(env)
        return None

    def get_cross_account_role(self, account_id: str) -> Optional[CrossAccountRole]:
        """Get cross-account role by AWS account ID"""
        return self.cross_account_roles.get(account_id)

    def get_cluster_name(self, project: str, env: str) -> str:
        """Get cluster name for a project/environment"""
        env_config = self.get_environment(project, env)
        if env_config and env_config.cluster_name:
            return env_config.cluster_name
        return self.naming_pattern.format('cluster', project=project, env=env)

    def get_service_name(self, project: str, env: str, service: str) -> str:
        """Get full service name"""
        return self.naming_pattern.format('service', project=project, env=env, service=service)

    def get_log_group(self, project: str, env: str, service: str) -> str:
        """Get CloudWatch log group"""
        return self.naming_pattern.format('log_group', project=project, env=env, service=service)

    def get_build_pipeline_name(self, project: str, service: str) -> str:
        """Get build pipeline name"""
        return self.naming_pattern.format('build_pipeline', project=project, service=service)

    def get_deploy_pipeline_name(self, project: str, env: str, service: str) -> str:
        """Get deploy pipeline name"""
        return self.naming_pattern.format('deploy_pipeline', project=project, env=env, service=service)

    def get_ecr_repo(self, project: str, service: str) -> str:
        """Get ECR repository name"""
        return self.naming_pattern.format('ecr_repo', project=project, service=service)

    def get_db_identifier(self, project: str, env: str) -> str:
        """Get RDS database identifier"""
        return self.naming_pattern.format('db_identifier', project=project, env=env)

    def get_read_role_arn(self, account_id: str) -> Optional[str]:
        """Get read role ARN for an account"""
        role = self.get_cross_account_role(account_id)
        return role.read_role_arn if role else None

    def get_action_role_arn(self, account_id: str) -> Optional[str]:
        """Get action role ARN for an account"""
        role = self.get_cross_account_role(account_id)
        return role.action_role_arn if role else None

    def get_read_role_arn_for_env(self, project: str, env: str, account_id: str) -> Optional[str]:
        """Get read role ARN with environment-level override.
        Priority: environment.readRoleArn > crossAccountRoles[accountId].readRoleArn
        """
        env_config = self.get_environment(project, env)
        if env_config and env_config.read_role_arn:
            return env_config.read_role_arn
        return self.get_read_role_arn(account_id)

    def get_action_role_arn_for_env(self, project: str, env: str, account_id: str) -> Optional[str]:
        """Get action role ARN with environment-level override.
        Priority: environment.actionRoleArn > crossAccountRoles[accountId].actionRoleArn
        """
        env_config = self.get_environment(project, env)
        if env_config and env_config.action_role_arn:
            return env_config.action_role_arn
        return self.get_action_role_arn(account_id)

    def build_console_url(self, url_type: str, **kwargs) -> str:
        """Build a console URL from template"""
        template = self.console_urls.get(url_type)
        if not template:
            raise ValueError(f"Unknown console URL type: {url_type}")
        return template.format(**kwargs)

    def to_dict(self) -> dict:
        """Convert config to dictionary for API response"""
        return {
            'region': self.region,
            'ssoPortalUrl': self.sso_portal_url,
            'ciProvider': self.ci_provider.type,
            'orchestrator': self.orchestrator.type,
            'githubOrg': self.github_org,
            'features': self.features,
            'projects': {
                name: proj.to_dict()
                for name, proj in self.projects.items()
            }
        }


@lru_cache(maxsize=1)
def get_config() -> DashboardConfig:
    """
    Load configuration from SSM Parameter Store.
    Uses caching to avoid repeated parsing and SSM calls.
    """

    # Core settings
    region = os.environ.get('AWS_REGION_DEFAULT', os.environ.get('AWS_REGION', 'eu-west-3'))
    shared_services_account = os.environ.get('SHARED_SERVICES_ACCOUNT', '')
    sso_portal_url = os.environ.get('SSO_PORTAL_URL', '')

    # Load projects and cross-account roles from SSM
    ssm_prefix = os.environ.get('CONFIG_SSM_PREFIX')
    if not ssm_prefix:
        raise ValueError("CONFIG_SSM_PREFIX environment variable is required")

    projects_raw, roles_raw = _load_ssm_config(ssm_prefix)

    # Parse projects
    projects = {}
    for project_name, project_data in projects_raw.items():
        # Skip comment entries
        if project_name.startswith('_'):
            continue

        environments = {}
        envs_data = project_data.get('environments', {})
        for env_name, env_data in envs_data.items():
            # Parse infrastructure config if present
            infra_config = None
            infra_data = env_data.get('infrastructure')
            if infra_data:
                infra_config = InfrastructureConfig(
                    discovery_tags=infra_data.get('discoveryTags', {}),
                    databases=infra_data.get('databases', []),
                    caches=infra_data.get('caches', [])
                )

            environments[env_name] = EnvironmentConfig(
                account_id=env_data.get('accountId', ''),
                services=env_data.get('services', []),
                region=env_data.get('region', region),
                cluster_name=env_data.get('clusterName'),
                namespace=env_data.get('namespace'),
                read_role_arn=env_data.get('readRoleArn'),
                action_role_arn=env_data.get('actionRoleArn'),
                status=env_data.get('status'),
                infrastructure=infra_config
            )

        projects[project_name] = ProjectConfig(
            name=project_name,
            display_name=project_data.get('displayName', project_name),
            environments=environments,
            idp_group_mapping=project_data.get('idpGroupMapping')
        )

    # Parse cross-account roles (indexed by account ID)
    cross_account_roles = {}
    for account_id, role_data in roles_raw.items():
        # Skip comment entries
        if account_id.startswith('_'):
            continue
        cross_account_roles[account_id] = CrossAccountRole(
            read_role_arn=role_data.get('readRoleArn', ''),
            action_role_arn=role_data.get('actionRoleArn', '')
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

    # Parse feature flags
    features_raw = json.loads(os.environ.get('FEATURES', '{}'))
    features = {k: v for k, v in features_raw.items() if isinstance(v, bool)}

    # Parse comparison config (optional)
    comparison = json.loads(os.environ.get('COMPARISON', '{}'))

    return DashboardConfig(
        region=region,
        shared_services_account=shared_services_account,
        sso_portal_url=sso_portal_url,
        projects=projects,
        cross_account_roles=cross_account_roles,
        naming_pattern=naming_pattern,
        ci_provider=ci_provider,
        orchestrator=orchestrator,
        github_org=github_org,
        features=features,
        comparison=comparison
    )


def clear_config_cache():
    """Clear the config cache (useful for testing)"""
    get_config.cache_clear()


# Helper functions
def get_projects() -> Dict[str, ProjectConfig]:
    """Get all project configurations"""
    return get_config().projects


def get_project(project: str) -> Optional[ProjectConfig]:
    """Get a specific project configuration"""
    return get_config().get_project(project)


def get_environment(project: str, env: str) -> Optional[EnvironmentConfig]:
    """Get environment configuration for a project"""
    return get_config().get_environment(project, env)


def get_region() -> str:
    """Get default region"""
    return get_config().region


def get_shared_services_account() -> str:
    """Get shared services account ID"""
    return get_config().shared_services_account


def get_sso_portal_url() -> str:
    """Get SSO portal URL"""
    return get_config().sso_portal_url
