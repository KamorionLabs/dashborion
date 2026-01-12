"""
Comparison Provider for Environment Comparison data.

Queries the ops-dashboard-shared-state DynamoDB table for comparison results
between Legacy (Source) and New Horizon (Destination) environments.
"""

from .dynamodb import DynamoDBComparisonProvider

__all__ = ['DynamoDBComparisonProvider']
