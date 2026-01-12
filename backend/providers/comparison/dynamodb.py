"""
DynamoDB Comparison Provider.

Generic provider for environment comparison data.
Supports querying pre-calculated comparisons from DynamoDB.
"""

import os
import boto3
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


# DynamoDB table name - configurable via environment
TABLE_NAME = os.environ.get('COMPARISON_TABLE', os.environ.get('OPS_DASHBOARD_TABLE', 'ops-dashboard-shared-state'))

# Default check types for comparisons - new format: {category}:{type}
# These map to sk format: check:{category}:{type}:current
DEFAULT_COMPARISON_CHECK_TYPES = [
    'k8s:pods',
    'k8s:services',
    'k8s:ingress',
    'k8s:pvc',
    'k8s:secrets',
    'config:sm',
    'config:ssm',
    'net:dns',
    'net:alb',
    'net:cloudfront',
    'net:sg',
]

# Check type categories for grouping in UI
DEFAULT_CHECK_TYPE_CATEGORIES = {
    'kubernetes': ['k8s:pods', 'k8s:services', 'k8s:ingress', 'k8s:pvc', 'k8s:secrets'],
    'configuration': ['config:sm', 'config:ssm'],
    'network': ['net:dns', 'net:alb', 'net:cloudfront', 'net:sg'],
}

# Human-readable labels for check types
DEFAULT_CHECK_TYPE_LABELS = {
    'k8s:pods': 'Pods',
    'k8s:services': 'Services',
    'k8s:ingress': 'Ingress',
    'k8s:pvc': 'PVC',
    'k8s:secrets': 'Secrets',
    'config:sm': 'Secrets Manager',
    'config:ssm': 'SSM Parameters',
    'net:dns': 'DNS',
    'net:alb': 'ALB',
    'net:cloudfront': 'CloudFront',
    'net:sg': 'Security Groups',
}


@dataclass
class ComparisonItem:
    """Individual comparison result"""
    check_type: str
    label: str
    category: str
    status: str  # synced, differs, critical, pending
    source_count: int = 0
    destination_count: int = 0
    synced_count: int = 0
    differs_count: int = 0
    only_source_count: int = 0
    only_destination_count: int = 0
    last_updated: Optional[datetime] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'checkType': self.check_type,
            'label': self.label,
            'category': self.category,
            'status': self.status,
            'sourceCount': self.source_count,
            'destinationCount': self.destination_count,
            'syncedCount': self.synced_count,
            'differsCount': self.differs_count,
            'onlySourceCount': self.only_source_count,
            'onlyDestinationCount': self.only_destination_count,
            'lastUpdated': self.last_updated.isoformat() if self.last_updated else None,
            'syncPercentage': self._calc_sync_percentage(),
        }

    def _calc_sync_percentage(self) -> float:
        """Calculate sync percentage based on synced vs total"""
        total = self.source_count + self.only_destination_count
        if total == 0:
            return 100.0
        return round((self.synced_count / total) * 100, 1)


@dataclass
class ComparisonSummary:
    """Summary of all comparisons for a target"""
    domain: str
    target: str
    source_label: str
    destination_label: str
    overall_status: str  # synced, differs, critical, incomplete, incomplete_differs, incomplete_critical
    overall_sync_percentage: float
    items: List[ComparisonItem] = field(default_factory=list)
    categories: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_updated: Optional[datetime] = None
    # New fields for tracking completeness
    total_checks: int = 0
    completed_checks: int = 0
    pending_checks: int = 0

    def to_dict(self) -> dict:
        return {
            'domain': self.domain,
            'target': self.target,
            'sourceLabel': self.source_label,
            'destinationLabel': self.destination_label,
            'overallStatus': self.overall_status,
            'overallSyncPercentage': self.overall_sync_percentage,
            'items': [item.to_dict() for item in self.items],
            'categories': self.categories,
            'lastUpdated': self.last_updated.isoformat() if self.last_updated else None,
            # Completeness info for frontend
            'totalChecks': self.total_checks,
            'completedChecks': self.completed_checks,
            'pendingChecks': self.pending_checks,
        }


def _convert_decimals(obj):
    """Convert Decimal objects to int/float for JSON serialization"""
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj


class DynamoDBComparisonProvider:
    """
    Generic provider for environment comparison data from DynamoDB.

    Queries a DynamoDB table for pre-calculated comparison results.
    Fully configurable - no hardcoded project/environment assumptions.
    """

    def __init__(
        self,
        table_name: str = None,
        region: str = None,
        check_types: List[str] = None,
        check_type_labels: Dict[str, str] = None,
        check_type_categories: Dict[str, List[str]] = None,
    ):
        """
        Initialize the comparison provider.

        Args:
            table_name: DynamoDB table name (default from env or 'ops-dashboard-shared-state')
            region: AWS region (default from env or 'eu-central-1')
            check_types: List of check types to query (default: DEFAULT_COMPARISON_CHECK_TYPES)
            check_type_labels: Human-readable labels for check types
            check_type_categories: Grouping of check types into categories
        """
        self.table_name = table_name or TABLE_NAME
        self.region = region or os.environ.get('AWS_REGION', 'eu-central-1')
        self.check_types = check_types or DEFAULT_COMPARISON_CHECK_TYPES
        self.check_type_labels = check_type_labels or DEFAULT_CHECK_TYPE_LABELS
        self.check_type_categories = check_type_categories or DEFAULT_CHECK_TYPE_CATEGORIES
        self._dynamodb = None
        self._table = None

    @property
    def dynamodb(self):
        if self._dynamodb is None:
            self._dynamodb = boto3.resource('dynamodb', region_name=self.region)
        return self._dynamodb

    @property
    def table(self):
        if self._table is None:
            self._table = self.dynamodb.Table(self.table_name)
        return self._table

    def get_comparison_summary(
        self,
        pk: str,
        source_label: str = 'Source',
        destination_label: str = 'Destination'
    ) -> ComparisonSummary:
        """
        Get summary of all comparison check types for a pk.

        Args:
            pk: Partition key (e.g., 'mro-mi2#comparison:legacy-staging:nh-staging')
            source_label: Label for source environment
            destination_label: Label for destination environment

        Returns:
            ComparisonSummary with all comparison items
        """
        # Extract domain and target from pk for backward compat in response
        parts = pk.split('#', 1)
        domain = parts[0] if parts else pk
        target = parts[1] if len(parts) > 1 else ''
        items = []
        categories_summary = {cat: {'synced': 0, 'differs': 0, 'total': 0} for cat in self.check_type_categories.keys()}
        latest_update = None

        for check_type in self.check_types:
            # New sk format: check:{category}:{type}:current
            # check_type is already in format "category:type" (e.g., "k8s:pods")
            sk = f"check:{check_type}:current"

            try:
                response = self.table.get_item(Key={'pk': pk, 'sk': sk})
                if 'Item' not in response:
                    # No data for this check type - mark as pending
                    item = ComparisonItem(
                        check_type=check_type,
                        label=self.check_type_labels.get(check_type, check_type),
                        category=self._get_category(check_type),
                        status='pending',
                    )
                else:
                    raw = _convert_decimals(response['Item'])
                    payload = raw.get('payload', {})
                    summary = payload.get('summary', {})

                    # Parse the summary data - handle two formats:
                    # Format 1 (config-*): {sourceCount: N, synced: N, ...}
                    # Format 2 (k8s-*): {front: "synced", bo: "differs", ...}
                    if 'sourceCount' in summary:
                        # Format 1: numeric counts
                        source_count = summary.get('sourceCount', 0)
                        dest_count = summary.get('destinationCount', 0)
                        synced = summary.get('synced', 0) + summary.get('differs_expected', 0)
                        differs = summary.get('differs_unexpected', 0)
                        only_source = summary.get('only_source_unexpected', 0)
                        only_dest = summary.get('only_destination_unexpected', 0)
                    else:
                        # Format 2: status strings per item (k8s comparisons)
                        # Count items by their status
                        source_count = 0
                        dest_count = 0
                        synced = 0
                        differs = 0
                        only_source = 0
                        only_dest = 0

                        for item_key, item_status in summary.items():
                            if isinstance(item_status, str):
                                source_count += 1
                                dest_count += 1
                                if item_status == 'synced':
                                    synced += 1
                                elif item_status == 'differs':
                                    differs += 1
                                elif item_status == 'only_source':
                                    only_source += 1
                                    dest_count -= 1  # Not in destination
                                elif item_status == 'only_destination':
                                    only_dest += 1
                                    source_count -= 1  # Not in source
                                elif item_status == 'missing':
                                    source_count -= 1
                                    dest_count -= 1

                    # Determine status from payload or calculated values
                    comparison_status = payload.get('comparison_status') or payload.get('status', 'unknown')
                    if comparison_status in ('synced', 'synced_with_expected_diffs', 'synced_with_warnings'):
                        status = 'synced'
                    elif comparison_status == 'critical' or differs > 0:
                        status = 'critical'
                    elif comparison_status == 'differs' or only_source > 0:
                        status = 'differs'
                    else:
                        status = 'synced'

                    # Parse timestamp
                    updated_at = None
                    if 'updated_at' in raw:
                        try:
                            updated_at = datetime.fromisoformat(raw['updated_at'].replace('Z', '+00:00'))
                        except (ValueError, TypeError):
                            pass

                    if updated_at and (latest_update is None or updated_at > latest_update):
                        latest_update = updated_at

                    item = ComparisonItem(
                        check_type=check_type,
                        label=self.check_type_labels.get(check_type, check_type),
                        category=self._get_category(check_type),
                        status=status,
                        source_count=source_count,
                        destination_count=dest_count,
                        synced_count=synced,
                        differs_count=differs,
                        only_source_count=only_source,
                        only_destination_count=only_dest,
                        last_updated=updated_at,
                        payload=payload,
                    )

                    # Update category summary
                    cat = self._get_category(check_type)
                    if cat in categories_summary:
                        categories_summary[cat]['total'] += 1
                        if status == 'synced':
                            categories_summary[cat]['synced'] += 1
                        else:
                            categories_summary[cat]['differs'] += 1

                items.append(item)

            except Exception as e:
                # Log error but continue with other check types
                print(f"Error fetching {check_type} for {pk}: {e}")
                items.append(ComparisonItem(
                    check_type=check_type,
                    label=self.check_type_labels.get(check_type, check_type),
                    category=self._get_category(check_type),
                    status='error',
                ))

        # Calculate overall stats
        total_synced = sum(1 for i in items if i.status == 'synced')
        total_differs = sum(1 for i in items if i.status == 'differs')
        total_critical = sum(1 for i in items if i.status == 'critical')
        total_pending = sum(1 for i in items if i.status == 'pending')
        total_error = sum(1 for i in items if i.status == 'error')
        total_with_data = len([i for i in items if i.status not in ('pending', 'error')])
        total_items = len(items)

        # Determine overall status - "incomplete" if checks are missing data
        if total_pending > 0 or total_error > 0:
            # Checks are missing data - status reflects this
            if total_critical > 0:
                overall_status = 'incomplete_critical'
            elif total_differs > 0:
                overall_status = 'incomplete_differs'
            else:
                overall_status = 'incomplete'
        elif total_critical > 0:
            overall_status = 'critical'
        elif total_differs > 0:
            overall_status = 'differs'
        else:
            overall_status = 'synced'

        # Calculate percentage including ALL checks (pending = 0%)
        # This gives a realistic view: 2 synced out of 11 total = 18%, not 100%
        overall_percentage = (total_synced / total_items * 100) if total_items > 0 else 0

        return ComparisonSummary(
            domain=domain,
            target=target,
            source_label=source_label,
            destination_label=destination_label,
            overall_status=overall_status,
            overall_sync_percentage=round(overall_percentage, 1),
            items=items,
            categories=categories_summary,
            last_updated=latest_update,
            total_checks=total_items,
            completed_checks=total_with_data,
            pending_checks=total_pending,
        )

    def get_comparison_detail(
        self,
        pk: str,
        check_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed comparison data for a specific check type.

        Args:
            pk: Partition key (e.g., 'mro-mi2#comparison:legacy-staging:nh-staging')
            check_type: Check type in category:type format (e.g., 'k8s:pods')

        Returns:
            Full comparison payload with details
        """
        # New sk format: check:{category}:{type}:current
        sk = f"check:{check_type}:current"

        try:
            response = self.table.get_item(Key={'pk': pk, 'sk': sk})
            if 'Item' not in response:
                return None

            raw = _convert_decimals(response['Item'])
            payload = raw.get('payload', {})

            # Build result with metadata
            result = {
                'checkType': check_type,
                'label': self.check_type_labels.get(check_type, check_type),
                'category': self._get_category(check_type),
                'lastUpdated': raw.get('updated_at'),
                # Include the status from payload (may be 'status' or 'comparison_status')
                'comparisonStatus': payload.get('comparison_status') or payload.get('status'),
            }

            # Include all payload fields - different check types have different structures
            # K8s comparisons: summary, rulesComparison, hostsComparison, tgbComparison, sftpComparison, issues
            # Config comparisons: summary, details, issues
            for key, value in payload.items():
                if key not in result:
                    # Convert snake_case to camelCase for consistency
                    camel_key = key
                    if '_' in key:
                        parts = key.split('_')
                        camel_key = parts[0] + ''.join(p.capitalize() for p in parts[1:])
                    result[camel_key] = value

            return result

        except Exception as e:
            print(f"Error fetching detail {check_type} for {pk}: {e}")
            return {'error': str(e)}

    def get_comparison_history(
        self,
        pk: str,
        check_type: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get historical comparison results for a check type.

        Args:
            pk: Partition key (e.g., 'mro-mi2#comparison:legacy-staging:nh-staging')
            check_type: Check type in category:type format (e.g., 'k8s:pods')
            limit: Max number of history items to return

        Returns:
            List of historical comparison results
        """
        # New sk format: check:{category}:{type}:history#timestamp
        sk_prefix = f"check:{check_type}:history#"

        try:
            response = self.table.query(
                KeyConditionExpression='pk = :pk AND begins_with(sk, :sk_prefix)',
                ExpressionAttributeValues={
                    ':pk': pk,
                    ':sk_prefix': sk_prefix,
                },
                Limit=limit,
                ScanIndexForward=False,  # Most recent first
            )

            items = []
            for raw in response.get('Items', []):
                raw = _convert_decimals(raw)
                payload = raw.get('payload', {})
                items.append({
                    'timestamp': raw.get('updated_at'),
                    'summary': payload.get('summary', {}),
                    'status': payload.get('comparison_status'),
                })

            return items

        except Exception as e:
            print(f"Error fetching history {check_type} for {pk}: {e}")
            return []

    def _get_category(self, check_type: str) -> str:
        """Get category for a check type"""
        for category, types in self.check_type_categories.items():
            if check_type in types:
                return category
        return 'other'
