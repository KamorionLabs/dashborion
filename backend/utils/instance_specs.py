"""
AWS Instance Specs Fetcher via Pricing API.

Fetches EC2 and RDS instance specifications (vCPU, memory, network performance)
using the AWS Pricing API (only available in us-east-1).

Results are cached to avoid redundant API calls.
"""

import json
import boto3
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class InstanceSpecs:
    """Instance specifications"""
    vcpu: int
    memory_gib: float
    network_performance: str
    architecture: str
    processor_features: str = ""


class InstanceSpecsFetcher:
    """
    Fetches instance specifications from AWS Pricing API.

    The Pricing API is only available in us-east-1, so we use a dedicated
    client for that region regardless of the target region.
    """

    def __init__(self, session: boto3.Session = None):
        """
        Initialize the fetcher.

        Args:
            session: Optional boto3 session (uses default credentials if not provided)
        """
        self._session = session or boto3.Session()
        # Pricing API is only available in us-east-1
        self._pricing_client = self._session.client('pricing', region_name='us-east-1')
        self._cache: Dict[str, InstanceSpecs] = {}

    def _normalize_instance_type(self, instance_type: str) -> str:
        """Remove db. prefix for RDS instance types."""
        return instance_type.replace('db.', '')

    def get_instance_specs(
        self,
        instance_type: str,
        region: str,
        for_rds: bool = False
    ) -> Optional[InstanceSpecs]:
        """
        Get specifications for an EC2 or RDS instance type.

        Args:
            instance_type: Instance type (e.g., 'm5.xlarge', 'db.r5.large')
            region: AWS region code (e.g., 'eu-central-1')
            for_rds: True if this is an RDS instance type

        Returns:
            InstanceSpecs or None if not found
        """
        # Normalize instance type for caching
        normalized = self._normalize_instance_type(instance_type)
        cache_key = f"{normalized}:{region}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            specs = self._fetch_specs(instance_type, region, for_rds)
            if specs:
                # Cache with normalized key
                self._cache[cache_key] = specs
            return specs
        except Exception as e:
            print(f"Warning: Could not fetch specs for {instance_type}: {e}")
            return None

    def _fetch_specs(
        self,
        instance_type: str,
        region: str,
        for_rds: bool
    ) -> Optional[InstanceSpecs]:
        """Fetch specs from Pricing API."""
        service_code = 'AmazonRDS' if for_rds else 'AmazonEC2'
        product_family = 'Database Instance' if for_rds else 'Compute Instance'

        # For RDS, use the instance type as-is; for EC2, use normalized
        query_type = instance_type if for_rds else self._normalize_instance_type(instance_type)

        filters = [
            {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': query_type},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': product_family},
            {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region},
        ]

        response = self._pricing_client.get_products(
            ServiceCode=service_code,
            Filters=filters
        )

        if not response.get('PriceList'):
            # If RDS query failed, try EC2
            if for_rds:
                return self._fetch_specs(
                    self._normalize_instance_type(instance_type),
                    region,
                    for_rds=False
                )
            return None

        price_item = json.loads(response['PriceList'][0])
        attributes = price_item['product']['attributes']

        # Parse memory (e.g., "16 GiB" -> 16.0)
        memory_str = attributes.get('memory', '0 GiB')
        memory_gib = float(memory_str.split()[0]) if memory_str else 0.0

        return InstanceSpecs(
            vcpu=int(attributes.get('vcpu', 0)),
            memory_gib=memory_gib,
            network_performance=attributes.get('networkPerformance', 'Unknown'),
            architecture=attributes.get('processorArchitecture', 'Unknown'),
            processor_features=attributes.get('processorFeatures', '')
        )

    def format_instance_type_display(
        self,
        instance_type: str,
        region: str,
        for_rds: bool = False
    ) -> str:
        """
        Format instance type with specs for display.

        Args:
            instance_type: Instance type
            region: AWS region
            for_rds: True if RDS instance

        Returns:
            Formatted string like "m5.xlarge (4 vCPU, 16 GB, arm64)"
        """
        specs = self.get_instance_specs(instance_type, region, for_rds)
        if not specs:
            return instance_type

        if for_rds:
            return f"{instance_type} ({specs.vcpu} vCPU, {specs.memory_gib:.1f} GB)"
        else:
            return f"{instance_type} ({specs.vcpu} vCPU, {specs.memory_gib:.1f} GB, {specs.architecture})"

    def clear_cache(self):
        """Clear the specs cache."""
        self._cache = {}


# Global singleton instance
_specs_fetcher: Optional[InstanceSpecsFetcher] = None


def get_instance_specs_fetcher() -> InstanceSpecsFetcher:
    """Get the global InstanceSpecsFetcher instance."""
    global _specs_fetcher
    if _specs_fetcher is None:
        _specs_fetcher = InstanceSpecsFetcher()
    return _specs_fetcher


def format_instance_type(
    instance_type: str,
    region: str,
    for_rds: bool = False
) -> str:
    """
    Convenience function to format an instance type with specs.

    Args:
        instance_type: Instance type (e.g., 'm5.xlarge')
        region: AWS region
        for_rds: True if RDS instance

    Returns:
        Formatted string like "m5.xlarge (4 vCPU, 16 GB, arm64)"
    """
    return get_instance_specs_fetcher().format_instance_type_display(
        instance_type, region, for_rds
    )
