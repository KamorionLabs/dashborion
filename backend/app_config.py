"""
Dynamic configuration system for the Operations Dashboard.

Configuration is stored in DynamoDB Config Registry (CONFIG_TABLE_NAME env var).
"""

import os
import json
import boto3
from botocore.exceptions import ClientError
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from functools import lru_cache
from decimal import Decimal

# Lazy initialized client
_dynamodb_resource = None


class ConfigNotInitializedError(Exception):
    """Raised when the Config Registry is not initialized or inaccessible."""

    def __init__(self, message: str = "Configuration not initialized", details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert to dict for API response."""
        result = {
            "error": "CONFIG_NOT_INITIALIZED",
            "message": self.message
        }
        if self.details:
            result["details"] = self.details
        return result


def _get_dynamodb_resource():
    """Get or create DynamoDB resource."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        # Support LocalStack for local development
        localstack_endpoint = os.environ.get('LOCALSTACK_ENDPOINT')
        if localstack_endpoint:
            _dynamodb_resource = boto3.resource(
                'dynamodb',
                endpoint_url=localstack_endpoint,
                region_name=os.environ.get('AWS_DEFAULT_REGION', 'eu-west-3'),
                aws_access_key_id='test',
                aws_secret_access_key='test'
            )
        else:
            _dynamodb_resource = boto3.resource('dynamodb')
    return _dynamodb_resource


def _decimal_to_native(obj):
    """Convert Decimal to int/float for JSON compatibility."""
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_decimal_to_native(v) for v in obj]
    return obj


def _load_dynamodb_config(table_name: str) -> Tuple[dict, dict, dict, dict, dict]:
    """
    Load configuration from DynamoDB Config Registry.

    Returns:
        Tuple of (projects, environments, clusters, aws_accounts, settings)
    """
    table = _get_dynamodb_resource().Table(table_name)

    # Scan all items (config table is small)
    response = table.scan()
    items = response.get('Items', [])

    # Organize by type
    settings = {}
    projects = {}
    environments = {}  # Keyed by "projectId#envId"
    clusters = {}
    aws_accounts = {}

    for item in items:
        item = _decimal_to_native(item)
        pk = item.get('pk')
        sk = item.get('sk')

        if pk == 'GLOBAL' and sk == 'settings':
            settings = item
        elif pk == 'PROJECT':
            project_id = sk
            projects[project_id] = item
        elif pk == 'ENV':
            # sk format: projectId#envId
            environments[sk] = item
        elif pk == 'GLOBAL' and sk.startswith('cluster:'):
            cluster_id = sk.replace('cluster:', '')
            clusters[cluster_id] = item
        elif pk == 'GLOBAL' and sk.startswith('aws-account:'):
            account_id = sk.replace('aws-account:', '')
            aws_accounts[account_id] = item

    return projects, environments, clusters, aws_accounts, settings


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
class InfrastructureResourceConfig:
    """Infrastructure resource selection config (IDs take precedence over tags)."""
    ids: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class InfrastructureConfig:
    """Infrastructure discovery configuration for an environment"""
    default_tags: Dict[str, str] = field(default_factory=dict)
    resources: Dict[str, InfrastructureResourceConfig] = field(default_factory=dict)
    domain_config: Optional[Dict[str, Any]] = None


@dataclass
class EnvironmentConfig:
    """Configuration for a single environment within a project"""
    account_id: str
    services: List[str]
    region: str = "eu-west-3"
    cluster_name: Optional[str] = None  # Override naming pattern
    namespace: Optional[str] = None  # For EKS
    orchestrator_type: Optional[str] = None  # "ecs" or "eks" - overrides global setting
    read_role_arn: Optional[str] = None  # Override cross-account read role
    action_role_arn: Optional[str] = None  # Override cross-account action role
    status: Optional[str] = None  # Environment status (active, deployed, planned)
    infrastructure: Optional[InfrastructureConfig] = None  # Infrastructure discovery config
    topology: Optional[Dict[str, Any]] = None  # Environment topology config

    def to_dict(self) -> dict:
        result = {
            'accountId': self.account_id,
            'services': self.services,
            'region': self.region,
            'clusterName': self.cluster_name,
            'namespace': self.namespace,
            'orchestratorType': self.orchestrator_type,
            'status': self.status
        }
        if self.read_role_arn:
            result['readRoleArn'] = self.read_role_arn
        if self.action_role_arn:
            result['actionRoleArn'] = self.action_role_arn
        if self.infrastructure:
            resources = {}
            for key, cfg in self.infrastructure.resources.items():
                resources[key] = {
                    'ids': cfg.ids,
                    'tags': cfg.tags
                }
            result['infrastructure'] = {
                'defaultTags': self.infrastructure.default_tags,
                'domainConfig': self.infrastructure.domain_config,
                'resources': resources,
            }
        if self.topology:
            result['topology'] = self.topology
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
    topology: Optional[Dict[str, Any]] = None
    service_naming: Optional[Dict[str, Any]] = None

    def get_environment(self, env: str) -> Optional[EnvironmentConfig]:
        """Get environment configuration by name"""
        return self.environments.get(env)

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'displayName': self.display_name,
            'topology': self.topology,
            'serviceNaming': self.service_naming,
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
            env_config = proj.get_environment(env)
            if not env_config:
                return None
            if proj.topology:
                env_topology = env_config.topology
                env_has_services = bool(_derive_services_from_topology(env_topology))
                if not env_topology or not env_has_services:
                    merged = dict(proj.topology)
                    if env_topology:
                        merged_components = {
                            **(proj.topology.get('components') or {}),
                            **(env_topology.get('components') or {})
                        }
                        merged['components'] = merged_components
                        if env_topology.get('layout'):
                            merged['layout'] = env_topology['layout']
                    env_config.topology = merged
            return env_config
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
        if not service:
            return service
        proj = self.get_project(project)
        service_naming = proj.service_naming if proj else None
        # If service_naming is defined (even with empty values), use it
        if service_naming is not None:
            prefix_template = service_naming.get('prefix', '')
            suffix_template = service_naming.get('suffix', '')
            prefix = prefix_template.format(project=project, env=env) if prefix_template else ""
            suffix = suffix_template.format(project=project, env=env) if suffix_template else ""
            if service.startswith(prefix) and service.endswith(suffix):
                return service
            return f"{prefix}{service}{suffix}"
        # Fall back to default naming pattern
        pattern = self.naming_pattern.service
        if '{service}' in pattern:
            prefix, suffix = pattern.split('{service}', 1)
            prefix = prefix.format(project=project, env=env)
            suffix = suffix.format(project=project, env=env)
            if service.startswith(prefix) and service.endswith(suffix):
                return service
            return f"{prefix}{service}{suffix}"
        return self.naming_pattern.format('service', project=project, env=env, service=service)

    def strip_service_name(self, project: str, env: str, service: str, strict: bool = False) -> Optional[str]:
        """Strip project/env prefix (and suffix) from a service name."""
        if not service:
            return service
        proj = self.get_project(project)
        service_naming = proj.service_naming if proj else None
        prefix_template = service_naming.get('prefix') if service_naming else None
        suffix_template = service_naming.get('suffix') if service_naming else None
        prefix = prefix_template.format(project=project, env=env) if prefix_template else ""
        suffix = suffix_template.format(project=project, env=env) if suffix_template else ""

        if prefix or suffix:
            if service.startswith(prefix) and service.endswith(suffix):
                end = len(service) - len(suffix) if suffix else None
                return service[len(prefix):end]
            return None if strict else service

        pattern = self.naming_pattern.service
        if '{service}' in pattern:
            pattern_prefix, pattern_suffix = pattern.split('{service}', 1)
            pattern_prefix = pattern_prefix.format(project=project, env=env)
            pattern_suffix = pattern_suffix.format(project=project, env=env)
            if service.startswith(pattern_prefix) and service.endswith(pattern_suffix):
                end = len(service) - len(pattern_suffix) if pattern_suffix else None
                return service[len(pattern_prefix):end]
            return None if strict else service

        return service

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

    def get_orchestrator_type(self, project: str, env: str) -> str:
        """Get orchestrator type for an environment with fallback to global.
        Priority: environment.orchestratorType > global orchestrator.type
        Returns: 'ecs' or 'eks'
        """
        env_config = self.get_environment(project, env)
        if env_config and env_config.orchestrator_type:
            return env_config.orchestrator_type
        return self.orchestrator.type

    def has_mixed_orchestrators(self, project: str) -> bool:
        """Check if a project has environments with different orchestrator types.

        Returns True if the project has both ECS and EKS environments,
        which requires using the DynamicOrchestratorProxy.
        """
        proj = self.get_project(project)
        if not proj:
            return False

        orchestrator_types = set()
        for env_name in proj.environments:
            orch_type = self.get_orchestrator_type(project, env_name)
            orchestrator_types.add(orch_type)
            # Early exit if we found both types
            if len(orchestrator_types) > 1:
                return True

        return False

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


def _parse_environment_config(env_data: dict, default_region: str) -> EnvironmentConfig:
    """Parse environment data into EnvironmentConfig dataclass."""
    infra_config = None
    infra_data = env_data.get('infrastructure')
    if infra_data is None:
        infra_data = {}
    if isinstance(infra_data, dict):
        resources = {}
        for key, value in (infra_data.get('resources') or {}).items():
            if not isinstance(value, dict):
                continue
            resources[key] = InfrastructureResourceConfig(
                ids=value.get('ids', []),
                tags=value.get('tags', {})
            )
        legacy_default_tags = env_data.get('discoveryTags') or infra_data.get('discoveryTags') or {}
        default_tags = infra_data.get('defaultTags') or legacy_default_tags or {}
        domain_config = infra_data.get('domainConfig') or env_data.get('domainConfig')
        infra_config = InfrastructureConfig(
            default_tags=default_tags,
            resources=resources,
            domain_config=domain_config,
        )

    # Support both SSM format (clusterName) and DynamoDB format (kubernetes.clusterName)
    k8s = env_data.get('kubernetes', {})
    cluster_name = env_data.get('clusterName') or k8s.get('clusterName')
    namespace = env_data.get('namespace') or k8s.get('namespace')

    return EnvironmentConfig(
        account_id=env_data.get('accountId', ''),
        services=env_data.get('services', []),
        region=env_data.get('region', default_region),
        cluster_name=cluster_name,
        namespace=namespace,
        orchestrator_type=env_data.get('orchestratorType'),
        read_role_arn=env_data.get('readRoleArn'),
        action_role_arn=env_data.get('actionRoleArn'),
        status=env_data.get('status'),
        infrastructure=infra_config,
        topology=env_data.get('topology'),
    )


def _derive_services_from_topology(topology: Optional[Dict[str, Any]]) -> List[str]:
    if not topology:
        return []
    components = topology.get('components') or {}
    if not isinstance(components, dict):
        return []

    service_types = {'ecs-service', 'k8s-deployment', 'k8s-statefulset', 'service'}
    infra_layers = {'edge', 'ingress', 'data'}
    services = []
    for name, component in components.items():
        if not name:
            continue
        comp_type = component.get('type') if isinstance(component, dict) else None
        layer = component.get('layer') if isinstance(component, dict) else None
        if comp_type in service_types:
            services.append(name)
            continue
        if comp_type is None and layer not in infra_layers:
            services.append(name)
    return services


def _load_config_from_dynamodb(table_name: str, region: str) -> Tuple[dict, dict, dict, dict]:
    """
    Load and parse config from DynamoDB into projects and cross_account_roles.

    Returns:
        Tuple of (projects, cross_account_roles, features, comparison)
    """
    projects_raw, envs_raw, clusters_raw, accounts_raw, settings = _load_dynamodb_config(table_name)

    # Parse projects and environments
    projects = {}
    for project_id, project_data in projects_raw.items():
        # Build environments dict for this project
        environments = {}
        for env_key, env_data in envs_raw.items():
            # env_key format: "projectId#envId"
            if env_key.startswith(f"{project_id}#"):
                env_id = env_key.split('#', 1)[1]
                environments[env_id] = _parse_environment_config(env_data, region)

        projects[project_id] = ProjectConfig(
            name=project_id,
            display_name=project_data.get('displayName', project_id),
            environments=environments,
            idp_group_mapping=project_data.get('idpGroupMapping'),
            topology=project_data.get('topology'),
            service_naming=project_data.get('serviceNaming')
        )

    # Parse AWS accounts as cross-account roles
    cross_account_roles = {}
    for account_id, account_data in accounts_raw.items():
        cross_account_roles[account_id] = CrossAccountRole(
            read_role_arn=account_data.get('readRoleArn', ''),
            action_role_arn=account_data.get('actionRoleArn', '')
        )

    # Extract features and comparison from settings
    features = settings.get('features', {})
    comparison = settings.get('comparison', {})

    return projects, cross_account_roles, features, comparison


@lru_cache(maxsize=1)
def get_config() -> DashboardConfig:
    """
    Load configuration from DynamoDB Config Registry.

    Requires CONFIG_TABLE_NAME environment variable.
    Raises ConfigNotInitializedError if config is not accessible or empty.

    Uses caching to avoid repeated parsing and AWS calls.
    """

    # Core settings from env vars
    region = os.environ.get('AWS_REGION_DEFAULT', os.environ.get('AWS_REGION', 'eu-west-3'))
    shared_services_account = os.environ.get('SHARED_SERVICES_ACCOUNT', '')
    sso_portal_url = os.environ.get('SSO_PORTAL_URL', '')

    # Config table is required
    config_table = os.environ.get('CONFIG_TABLE_NAME')
    if not config_table:
        raise ConfigNotInitializedError(
            message="Configuration table not configured",
            details="CONFIG_TABLE_NAME environment variable is not set"
        )

    # Load from DynamoDB Config Registry
    try:
        projects, cross_account_roles, features, comparison = _load_config_from_dynamodb(config_table, region)
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        raise ConfigNotInitializedError(
            message="Unable to access configuration table",
            details=f"DynamoDB error: {error_code} - {str(e)}"
        )

    # Check if config is empty (no projects configured)
    if not projects:
        raise ConfigNotInitializedError(
            message="Configuration not initialized",
            details="No projects found in Config Registry. Use the CLI or API to seed the configuration."
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

    # Filter features to boolean values only
    features = {k: v for k, v in features.items() if isinstance(v, bool)}

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
