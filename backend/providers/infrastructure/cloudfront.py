"""
AWS CloudFront CDN Provider implementation.
"""

import time
from urllib.parse import quote
from typing import List

from providers.base import CDNProvider, ProviderFactory
from config import DashboardConfig
from utils.aws import get_cross_account_client, get_action_client, build_sso_console_url


class CloudFrontProvider(CDNProvider):
    """
    AWS CloudFront implementation of the CDN provider.
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
        return get_cross_account_client('cloudfront', env_config.account_id)

    def get_distribution(self, env: str) -> dict:
        """Get CloudFront distribution for an environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            cloudfront = self._get_cloudfront_client(env)
            domain_suffix = f"{env}.{self.project}"

            distributions = cloudfront.list_distributions()
            for dist in distributions.get('DistributionList', {}).get('Items', []):
                aliases = dist.get('Aliases', {}).get('Items', [])
                if any(domain_suffix in alias for alias in aliases):
                    dist_id = dist['Id']

                    result = {
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
                        result['origins'].append({
                            'id': origin['Id'],
                            'domainName': origin_domain,
                            'type': origin_type,
                            'path': origin.get('OriginPath', '')
                        })

                    # Get full distribution config
                    try:
                        dist_config = cloudfront.get_distribution(Id=dist_id)
                        dist_detail = dist_config.get('Distribution', {}).get('DistributionConfig', {})

                        # WAF Web ACL
                        web_acl = dist_detail.get('WebACLId', '')
                        if web_acl:
                            result['webAclId'] = web_acl

                        # Default cache behavior
                        default_behavior = dist_detail.get('DefaultCacheBehavior', {})
                        if default_behavior:
                            result['cacheBehaviors'].append({
                                'pathPattern': 'Default (*)',
                                'targetOriginId': default_behavior.get('TargetOriginId'),
                                'viewerProtocolPolicy': default_behavior.get('ViewerProtocolPolicy'),
                                'defaultTTL': default_behavior.get('DefaultTTL', 0),
                                'compress': default_behavior.get('Compress', False),
                                'lambdaEdge': len(default_behavior.get('LambdaFunctionAssociations', {}).get('Items', [])) > 0
                            })

                        # Additional cache behaviors
                        for behavior in dist_detail.get('CacheBehaviors', {}).get('Items', []):
                            result['cacheBehaviors'].append({
                                'pathPattern': behavior.get('PathPattern'),
                                'targetOriginId': behavior.get('TargetOriginId'),
                                'viewerProtocolPolicy': behavior.get('ViewerProtocolPolicy'),
                                'defaultTTL': behavior.get('DefaultTTL', 0),
                                'compress': behavior.get('Compress', False),
                                'lambdaEdge': len(behavior.get('LambdaFunctionAssociations', {}).get('Items', [])) > 0
                            })
                    except:
                        pass

                    return result

            return {'error': f'Distribution not found for domain pattern: {domain_suffix}'}

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
