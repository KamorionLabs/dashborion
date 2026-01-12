"""
AWS CloudFront CDN Provider implementation.

Supports:
- Tag-based discovery (EKS/NewHorizon style)
- Domain-based discovery (legacy style)
"""

import time
from urllib.parse import quote
from typing import List, Optional, Dict

from providers.base import CDNProvider, ProviderFactory
from app_config import DashboardConfig
from utils.aws import get_cross_account_client, get_action_client, build_sso_console_url


class CloudFrontProvider(CDNProvider):
    """
    AWS CloudFront implementation of the CDN provider.

    Discovery order:
    1. If discovery_tags provided, find distribution by tags
    2. If domain_patterns provided, match aliases
    3. Fallback to legacy pattern: {env}.{project}
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

    def _get_cloudfront_client(self, env: str):
        """Get CloudFront client for environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client(
            'cloudfront', env_config.account_id,
            project=self.project, env=env
        )

    def _get_resourcegroupstaggingapi_client(self, env: str):
        """Get Resource Groups Tagging API client for tag-based discovery"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        # CloudFront tags are global (us-east-1)
        return get_cross_account_client(
            'resourcegroupstaggingapi', env_config.account_id, 'us-east-1',
            project=self.project, env=env
        )

    def _find_distribution_by_tags(self, env: str, discovery_tags: Dict[str, str]) -> List[str]:
        """Find CloudFront distribution IDs by tags (returns all matching)"""
        if not discovery_tags:
            return []

        try:
            tagging = self._get_resourcegroupstaggingapi_client(env)

            # Build tag filters
            tag_filters = [{'Key': k, 'Values': [v]} for k, v in discovery_tags.items()]

            response = tagging.get_resources(
                ResourceTypeFilters=['cloudfront:distribution'],
                TagFilters=tag_filters
            )

            # Return all matching distribution IDs
            dist_ids = []
            for resource in response.get('ResourceTagMappingList', []):
                arn = resource['ResourceARN']
                # ARN format: arn:aws:cloudfront::account:distribution/DIST_ID
                dist_id = arn.split('/')[-1]
                dist_ids.append(dist_id)

            return dist_ids
        except Exception as e:
            print(f"Tag-based CloudFront discovery failed: {e}")
            return []

    def _find_distribution_by_domain(self, env: str, cloudfront, domain_patterns: List[str]) -> Optional[dict]:
        """Find CloudFront distribution by domain aliases"""
        try:
            distributions = cloudfront.list_distributions()
            for dist in distributions.get('DistributionList', {}).get('Items', []):
                aliases = dist.get('Aliases', {}).get('Items', [])
                for pattern in domain_patterns:
                    if any(pattern in alias for alias in aliases):
                        return dist
            return None
        except Exception as e:
            print(f"Domain-based CloudFront discovery failed: {e}")
            return None

    def get_distribution(self, env: str, discovery_tags: Dict[str, str] = None,
                         domain_patterns: List[str] = None) -> dict:
        """Get CloudFront distribution(s) for an environment

        Args:
            env: Environment name
            discovery_tags: Dict of tags to find distribution (e.g., {'rubix_Environment': 'stg'})
            domain_patterns: List of domain patterns to match aliases

        Returns:
            For single distribution: dict with distribution details
            For multiple distributions: dict with aggregated info and 'distributions' list
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            cloudfront = self._get_cloudfront_client(env)
            dist_ids = []
            discovery_method = None

            # 1. Try tag-based discovery first (returns all matching)
            if discovery_tags:
                dist_ids = self._find_distribution_by_tags(env, discovery_tags)
                if dist_ids:
                    discovery_method = 'tags'

            # 2. Try domain patterns (single distribution)
            if not dist_ids and domain_patterns:
                dist = self._find_distribution_by_domain(env, cloudfront, domain_patterns)
                if dist:
                    dist_ids = [dist['Id']]
                    discovery_method = 'domain'

            # 3. Fallback to legacy pattern (single distribution)
            if not dist_ids:
                domain_suffix = f"{env}.{self.project}"
                distributions = cloudfront.list_distributions()
                for d in distributions.get('DistributionList', {}).get('Items', []):
                    aliases = d.get('Aliases', {}).get('Items', [])
                    if any(domain_suffix in alias for alias in aliases):
                        dist_ids = [d['Id']]
                        discovery_method = 'naming'
                        break

            if not dist_ids:
                return None

            # Fetch all distributions in one call
            distributions_list = cloudfront.list_distributions()
            all_dists = {d['Id']: d for d in distributions_list.get('DistributionList', {}).get('Items', [])}

            # Build result for each distribution
            results = []
            all_aliases = []
            all_origins = []
            statuses = set()

            for dist_id in dist_ids:
                dist = all_dists.get(dist_id)
                if not dist:
                    continue

                aliases = dist.get('Aliases', {}).get('Items', [])
                all_aliases.extend(aliases)
                statuses.add(dist['Status'])

                dist_result = {
                    'id': dist_id,
                    'domainName': dist['DomainName'],
                    'aliases': aliases,
                    'status': dist['Status'],
                    'enabled': dist['Enabled'],
                    'origins': [],
                    'cacheBehaviors': [],
                    'webAclId': None,
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url,
                        env_config.account_id,
                        f"https://console.aws.amazon.com/cloudfront/v4/home#/distributions/{dist_id}"
                    )
                }

                # Get origins
                for origin in dist.get('Origins', {}).get('Items', []):
                    origin_domain = origin['DomainName']
                    origin_type = 'alb' if 'elb.amazonaws.com' in origin_domain else 's3' if 's3.' in origin_domain else 'custom'
                    origin_info = {
                        'id': origin['Id'],
                        'domainName': origin_domain,
                        'type': origin_type,
                        'path': origin.get('OriginPath', '')
                    }
                    dist_result['origins'].append(origin_info)
                    all_origins.append(origin_info)

                # Get full distribution config for more details
                try:
                    dist_config = cloudfront.get_distribution(Id=dist_id)
                    dist_detail = dist_config.get('Distribution', {}).get('DistributionConfig', {})

                    # WAF Web ACL
                    web_acl = dist_detail.get('WebACLId', '')
                    if web_acl:
                        dist_result['webAclId'] = web_acl

                    # Default cache behavior
                    default_behavior = dist_detail.get('DefaultCacheBehavior', {})
                    if default_behavior:
                        dist_result['cacheBehaviors'].append({
                            'pathPattern': 'Default (*)',
                            'targetOriginId': default_behavior.get('TargetOriginId'),
                            'viewerProtocolPolicy': default_behavior.get('ViewerProtocolPolicy'),
                            'defaultTTL': default_behavior.get('DefaultTTL', 0),
                            'compress': default_behavior.get('Compress', False),
                            'lambdaEdge': len(default_behavior.get('LambdaFunctionAssociations', {}).get('Items', [])) > 0
                        })

                    # Additional cache behaviors
                    for behavior in dist_detail.get('CacheBehaviors', {}).get('Items', []):
                        dist_result['cacheBehaviors'].append({
                            'pathPattern': behavior.get('PathPattern'),
                            'targetOriginId': behavior.get('TargetOriginId'),
                            'viewerProtocolPolicy': behavior.get('ViewerProtocolPolicy'),
                            'defaultTTL': behavior.get('DefaultTTL', 0),
                            'compress': behavior.get('Compress', False),
                            'lambdaEdge': len(behavior.get('LambdaFunctionAssociations', {}).get('Items', [])) > 0
                        })
                except:
                    pass

                results.append(dist_result)

            # Single distribution: return directly (backward compatible)
            if len(results) == 1:
                results[0]['discoveryMethod'] = discovery_method
                return results[0]

            # Multiple distributions: return aggregated result
            # Determine overall status
            if all(s == 'Deployed' for s in statuses):
                overall_status = 'Deployed'
            elif 'InProgress' in statuses:
                overall_status = 'InProgress'
            else:
                overall_status = 'Mixed'

            return {
                'id': f"{len(results)} distributions",
                'domainName': results[0]['domainName'] if results else None,
                'aliases': list(set(all_aliases)),  # Deduplicated
                'status': overall_status,
                'enabled': all(d['enabled'] for d in results),
                'origins': all_origins,
                'cacheBehaviors': [],  # Too complex to aggregate
                'webAclId': None,
                'discoveryMethod': discovery_method,
                'distributionCount': len(results),
                'distributions': results,  # Full details for each
                'consoleUrl': build_sso_console_url(
                    self.config.sso_portal_url,
                    env_config.account_id,
                    "https://console.aws.amazon.com/cloudfront/v4/home#/distributions"
                )
            }

        except Exception as e:
            return {'error': str(e)}

    def invalidate_cache(self, env: str, distribution_id: str, paths: List[str], user_email: str) -> dict:
        """Create CloudFront cache invalidation"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            cloudfront = get_action_client('cloudfront', env_config.account_id, user_email)

            caller_ref = f"dashboard-{int(time.time())}"

            response = cloudfront.create_invalidation(
                DistributionId=distribution_id,
                InvalidationBatch={
                    'Paths': {
                        'Quantity': len(paths),
                        'Items': paths
                    },
                    'CallerReference': caller_ref
                }
            )

            invalidation = response['Invalidation']
            return {
                'success': True,
                'invalidationId': invalidation['Id'],
                'status': invalidation['Status'],
                'distributionId': distribution_id,
                'paths': paths,
                'triggeredBy': user_email
            }
        except Exception as e:
            return {'error': str(e), 'distributionId': distribution_id}


# Register the provider
ProviderFactory.register_cdn_provider('cloudfront', CloudFrontProvider)
