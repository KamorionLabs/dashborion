"""
Base interfaces for CI/CD and Orchestrator providers.
All provider implementations must inherit from these abstract classes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


# =============================================================================
# DATA CLASSES - Common data structures returned by providers
# =============================================================================

@dataclass
class PipelineStage:
    """Pipeline stage information"""
    name: str
    status: str  # succeeded, failed, in_progress, pending
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    logs_url: Optional[str] = None


@dataclass
class PipelineExecution:
    """Pipeline execution information"""
    execution_id: str
    status: str  # succeeded, failed, in_progress, cancelled
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    commit_sha: Optional[str] = None
    commit_message: Optional[str] = None
    commit_author: Optional[str] = None
    commit_url: Optional[str] = None
    console_url: Optional[str] = None
    trigger_type: Optional[str] = None  # webhook, manual, scheduled


@dataclass
class Pipeline:
    """Pipeline information"""
    name: str
    pipeline_type: str  # build, deploy
    service: str
    environment: Optional[str] = None
    version: Optional[int] = None
    stages: List[PipelineStage] = field(default_factory=list)
    last_execution: Optional[PipelineExecution] = None
    executions: List[PipelineExecution] = field(default_factory=list)
    console_url: Optional[str] = None
    build_logs: Optional[List[dict]] = None


@dataclass
class ContainerImage:
    """Container image information"""
    digest: str
    tags: List[str]
    pushed_at: Optional[datetime] = None
    size_bytes: Optional[int] = None
    size_mb: Optional[float] = None


@dataclass
class ServiceTask:
    """Container task/pod information"""
    task_id: str
    status: str  # running, pending, stopped
    desired_status: str
    health: str  # healthy, unhealthy, unknown
    revision: Optional[str] = None
    is_latest: bool = True
    az: Optional[str] = None
    subnet_id: Optional[str] = None
    private_ip: Optional[str] = None
    cpu: Optional[str] = None
    memory: Optional[str] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None


@dataclass
class ServiceDeployment:
    """Service deployment information"""
    deployment_id: str
    status: str  # primary, active
    task_definition: str
    revision: str
    desired_count: int
    running_count: int
    pending_count: int = 0
    rollout_state: Optional[str] = None
    rollout_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class TaskDefinitionDiff:
    """Diff between two task definitions/revisions"""
    from_revision: str
    to_revision: str
    changes: List[Dict[str, str]]  # [{'field': 'image', 'label': 'Image', 'from': 'v1', 'to': 'v2'}]


@dataclass
class Service:
    """Container service information"""
    name: str
    service: str  # Short name (backend, frontend, etc.)
    environment: str
    cluster_name: str
    status: str  # active, draining, inactive
    desired_count: int
    running_count: int
    pending_count: int = 0
    tasks: List[ServiceTask] = field(default_factory=list)
    deployments: List[ServiceDeployment] = field(default_factory=list)
    task_definition: Optional[dict] = None
    latest_diff: Optional[TaskDefinitionDiff] = None
    console_url: Optional[str] = None
    account_id: Optional[str] = None


@dataclass
class ServiceDetails(Service):
    """Detailed service information with logs and env vars"""
    environment_variables: List[Dict[str, str]] = field(default_factory=list)
    secrets: List[Dict[str, str]] = field(default_factory=list)
    recent_logs: List[Dict[str, str]] = field(default_factory=list)
    ecs_events: List[Dict[str, Any]] = field(default_factory=list)
    deploy_pipeline: Optional[Pipeline] = None
    deployment_state: str = "stable"  # stable, in_progress, rolling_back, failed
    is_rolling_back: bool = False
    console_urls: Dict[str, str] = field(default_factory=dict)
    latest_task_definition: Optional[dict] = None  # Most recent task def in family


@dataclass
class Event:
    """Timeline event"""
    id: str
    type: str  # build, deploy, rollback, scale, reload, cache, rds
    timestamp: datetime
    service: str
    status: str  # succeeded, failed, in_progress, triggered
    duration_seconds: Optional[int] = None
    user: Optional[str] = None
    actor_type: Optional[str] = None  # human, dashboard, pipeline, eventbridge, service
    details: Dict[str, Any] = field(default_factory=dict)
    steps: Optional[List[Dict[str, Any]]] = None


# =============================================================================
# PROVIDER INTERFACES
# =============================================================================

class CIProvider(ABC):
    """
    Abstract base class for CI/CD providers.
    Implementations: CodePipelineProvider, GitHubActionsProvider, BitbucketProvider, GitLabProvider
    """

    @abstractmethod
    def get_build_pipeline(self, service: str) -> Pipeline:
        """Get build pipeline information for a service"""
        pass

    @abstractmethod
    def get_deploy_pipeline(self, env: str, service: str) -> Pipeline:
        """Get deploy pipeline information for a service in an environment"""
        pass

    @abstractmethod
    def get_pipeline_executions(self, pipeline_name: str, max_results: int = 5) -> List[PipelineExecution]:
        """Get recent executions for a pipeline"""
        pass

    @abstractmethod
    def trigger_build(self, service: str, user_email: str, image_tag: str = None, source_revision: str = None) -> dict:
        """Trigger a build pipeline"""
        pass

    @abstractmethod
    def trigger_deploy(self, env: str, service: str, user_email: str) -> dict:
        """Trigger a deploy pipeline"""
        pass

    @abstractmethod
    def get_build_logs(self, service: str, execution_id: str = None) -> List[dict]:
        """Get build logs for a service"""
        pass

    @abstractmethod
    def get_images(self, service: str) -> List[ContainerImage]:
        """Get container images for a service from registry"""
        pass


class OrchestratorProvider(ABC):
    """
    Abstract base class for container orchestrators.
    Implementations: ECSProvider, EKSProvider, ArgoCDOrchestratorProvider
    """

    @abstractmethod
    def get_services(self, env: str) -> Dict[str, Service]:
        """Get all services for an environment"""
        pass

    @abstractmethod
    def get_service(self, env: str, service: str) -> Service:
        """Get service information"""
        pass

    @abstractmethod
    def get_service_details(self, env: str, service: str) -> ServiceDetails:
        """Get detailed service information including logs and env vars"""
        pass

    @abstractmethod
    def get_task_details(self, env: str, service: str, task_id: str) -> dict:
        """Get detailed task/pod information"""
        pass

    @abstractmethod
    def get_service_logs(self, env: str, service: str, lines: int = 50) -> List[dict]:
        """Get recent logs for a service"""
        pass

    @abstractmethod
    def scale_service(self, env: str, service: str, replicas: int, user_email: str) -> dict:
        """Scale service to specified replica count"""
        pass

    @abstractmethod
    def force_deployment(self, env: str, service: str, user_email: str) -> dict:
        """Force a new deployment (reload)"""
        pass

    @abstractmethod
    def get_infrastructure(self, env: str) -> dict:
        """Get infrastructure topology for an environment"""
        pass

    @abstractmethod
    def get_metrics(self, env: str, service: str) -> dict:
        """Get service metrics (CPU, memory, etc.)"""
        pass


class EventsProvider(ABC):
    """
    Abstract base class for events timeline.
    Can aggregate events from multiple sources.
    """

    @abstractmethod
    def get_events(self, env: str, hours: int = 24, event_types: List[str] = None) -> List[Event]:
        """Get timeline events for an environment"""
        pass

    @abstractmethod
    def enrich_events(self, events: List[Event], env: str) -> List[Event]:
        """Enrich events with user attribution from audit logs"""
        pass


class DatabaseProvider(ABC):
    """
    Abstract base class for database operations.
    Implementations: RDSProvider (could add Aurora, DocumentDB, etc.)
    """

    @abstractmethod
    def get_database_status(self, env: str) -> dict:
        """Get database status for an environment"""
        pass

    @abstractmethod
    def start_database(self, env: str, user_email: str) -> dict:
        """Start the database"""
        pass

    @abstractmethod
    def stop_database(self, env: str, user_email: str) -> dict:
        """Stop the database"""
        pass


class CDNProvider(ABC):
    """
    Abstract base class for CDN operations.
    Implementations: CloudFrontProvider (could add CloudFlare, Fastly, etc.)
    """

    @abstractmethod
    def get_distribution(self, env: str) -> dict:
        """Get CDN distribution information"""
        pass

    @abstractmethod
    def invalidate_cache(self, env: str, distribution_id: str, paths: List[str], user_email: str) -> dict:
        """Invalidate CDN cache"""
        pass


class NetworkProvider(ABC):
    """
    Abstract base class for network/VPC operations.
    Implementations: VPCProvider (AWS VPC, subnets, NAT, routing, security groups)
    """

    @abstractmethod
    def get_network_info(self, env: str) -> dict:
        """Get VPC and basic network info (subnets, NAT gateways, connectivity summary)"""
        pass

    @abstractmethod
    def get_routing_details(self, env: str, service_security_groups: List[str] = None) -> dict:
        """Get detailed routing and security info (route tables, peerings, VPN, TGW, SGs, NACLs)"""
        pass


class LoadBalancerProvider(ABC):
    """
    Abstract base class for load balancer operations.
    Implementations: ALBProvider (AWS Application Load Balancer)
    """

    @abstractmethod
    def get_load_balancer(self, env: str, services: List[str] = None) -> dict:
        """Get load balancer info with target groups filtered by services"""
        pass


class CacheProvider(ABC):
    """
    Abstract base class for cache operations.
    Implementations: ElastiCacheProvider (Redis, Valkey, Memcached)
    """

    @abstractmethod
    def get_cache_cluster(self, env: str, discovery_tags: dict = None, cache_types: List[str] = None) -> dict:
        """Get cache cluster info"""
        pass


# =============================================================================
# PROVIDER FACTORY
# =============================================================================

class ProviderFactory:
    """
    Factory for creating provider instances based on configuration.
    """

    _ci_providers = {}
    _orchestrator_providers = {}
    _events_providers = {}
    _database_providers = {}
    _cdn_providers = {}
    _network_providers = {}
    _loadbalancer_providers = {}
    _cache_providers = {}

    @classmethod
    def register_ci_provider(cls, provider_type: str, provider_class: type):
        """Register a CI provider implementation"""
        cls._ci_providers[provider_type] = provider_class

    @classmethod
    def register_orchestrator_provider(cls, provider_type: str, provider_class: type):
        """Register an orchestrator provider implementation"""
        cls._orchestrator_providers[provider_type] = provider_class

    @classmethod
    def register_events_provider(cls, provider_type: str, provider_class: type):
        """Register an events provider implementation"""
        cls._events_providers[provider_type] = provider_class

    @classmethod
    def register_database_provider(cls, provider_type: str, provider_class: type):
        """Register a database provider implementation"""
        cls._database_providers[provider_type] = provider_class

    @classmethod
    def register_cdn_provider(cls, provider_type: str, provider_class: type):
        """Register a CDN provider implementation"""
        cls._cdn_providers[provider_type] = provider_class

    @classmethod
    def get_ci_provider(cls, config, project: str) -> CIProvider:
        """Get CI provider instance based on config"""
        provider_type = config.ci_provider.type
        if provider_type not in cls._ci_providers:
            raise ValueError(f"Unknown CI provider type: {provider_type}")
        return cls._ci_providers[provider_type](config, project)

    @classmethod
    def get_orchestrator_provider(cls, config, project: str) -> OrchestratorProvider:
        """Get orchestrator provider instance based on config"""
        provider_type = config.orchestrator.type
        if provider_type not in cls._orchestrator_providers:
            raise ValueError(f"Unknown orchestrator type: {provider_type}")
        return cls._orchestrator_providers[provider_type](config, project)

    @classmethod
    def get_events_provider(cls, config, project: str) -> EventsProvider:
        """Get events provider instance"""
        # Default to combined provider that aggregates from CI + orchestrator
        provider_type = getattr(config, 'events_provider_type', 'combined')
        if provider_type not in cls._events_providers:
            # Fallback to combined if specific not found
            provider_type = 'combined'
        if provider_type not in cls._events_providers:
            raise ValueError(f"No events provider registered")
        return cls._events_providers[provider_type](config, project)

    @classmethod
    def get_database_provider(cls, config, project: str) -> Optional[DatabaseProvider]:
        """Get database provider instance"""
        provider_type = getattr(config, 'database_provider_type', 'rds')
        if provider_type not in cls._database_providers:
            return None
        return cls._database_providers[provider_type](config, project)

    @classmethod
    def get_cdn_provider(cls, config, project: str) -> Optional[CDNProvider]:
        """Get CDN provider instance"""
        provider_type = getattr(config, 'cdn_provider_type', 'cloudfront')
        if provider_type not in cls._cdn_providers:
            return None
        return cls._cdn_providers[provider_type](config, project)

    @classmethod
    def register_network_provider(cls, provider_type: str, provider_class: type):
        """Register a network provider implementation"""
        cls._network_providers[provider_type] = provider_class

    @classmethod
    def register_loadbalancer_provider(cls, provider_type: str, provider_class: type):
        """Register a load balancer provider implementation"""
        cls._loadbalancer_providers[provider_type] = provider_class

    @classmethod
    def register_cache_provider(cls, provider_type: str, provider_class: type):
        """Register a cache provider implementation"""
        cls._cache_providers[provider_type] = provider_class

    @classmethod
    def get_network_provider(cls, config, project: str) -> Optional['NetworkProvider']:
        """Get network provider instance"""
        provider_type = getattr(config, 'network_provider_type', 'vpc')
        if provider_type not in cls._network_providers:
            return None
        return cls._network_providers[provider_type](config, project)

    @classmethod
    def get_loadbalancer_provider(cls, config, project: str) -> Optional['LoadBalancerProvider']:
        """Get load balancer provider instance"""
        provider_type = getattr(config, 'loadbalancer_provider_type', 'alb')
        if provider_type not in cls._loadbalancer_providers:
            return None
        return cls._loadbalancer_providers[provider_type](config, project)

    @classmethod
    def get_cache_provider(cls, config, project: str) -> Optional['CacheProvider']:
        """Get cache provider instance"""
        provider_type = getattr(config, 'cache_provider_type', 'elasticache')
        if provider_type not in cls._cache_providers:
            return None
        return cls._cache_providers[provider_type](config, project)
