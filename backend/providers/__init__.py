"""
Provider abstraction layer for the Operations Dashboard.
Supports multiple CI/CD systems and container orchestrators.

Auto-registers all provider implementations on import.
"""

from .base import (
    CIProvider,
    OrchestratorProvider,
    EventsProvider,
    DatabaseProvider,
    CDNProvider,
    ProviderFactory
)

# Import providers to register them with ProviderFactory
# CI Providers
from .ci.codepipeline import CodePipelineProvider
from .ci.github_actions import GitHubActionsProvider

# Orchestrator Providers
from .orchestrator.ecs import ECSProvider
from .orchestrator.eks import EKSProvider

# Events Provider
from .events.combined import CombinedEventsProvider

# Infrastructure Providers (for aggregator)
from .infrastructure.rds import RDSProvider
from .infrastructure.cloudfront import CloudFrontProvider
from .infrastructure.network import VPCProvider
from .infrastructure.alb import ALBProvider
from .infrastructure.elasticache import ElastiCacheProvider

__all__ = [
    'CIProvider',
    'OrchestratorProvider',
    'EventsProvider',
    'DatabaseProvider',
    'CDNProvider',
    'ProviderFactory',
    # Providers (for explicit import if needed)
    'CodePipelineProvider',
    'GitHubActionsProvider',
    'ECSProvider',
    'EKSProvider',
    'CombinedEventsProvider',
    'RDSProvider',
    'CloudFrontProvider',
    'VPCProvider',
    'ALBProvider',
    'ElastiCacheProvider',
]
