"""
Comparison Provider for Environment Comparison data.

Queries the ops-dashboard-shared-state DynamoDB table for comparison results
between Legacy (Source) and New Horizon (Destination) environments.

Also provides orchestrator integration for triggering comparisons.
"""

from .dynamodb import DynamoDBComparisonProvider
from .orchestrator import ComparisonOrchestratorProvider

__all__ = ['DynamoDBComparisonProvider', 'ComparisonOrchestratorProvider']
