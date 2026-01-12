"""
AWS ElastiCache Provider implementation.
"""

from typing import List, Optional

from providers.base import CacheProvider, ProviderFactory
from app_config import DashboardConfig
from utils.aws import get_cross_account_client, build_sso_console_url


def matches_discovery_tags(resource_tags: list, discovery_tags: dict) -> bool:
    """
    Check if a resource's tags match all the discovery tags.
    resource_tags: List of {'Key': 'x', 'Value': 'y'} or {'key': 'x', 'value': 'y'}
    discovery_tags: Dict of {tag_key: tag_value} to match
    Returns True if ALL discovery_tags are present in resource_tags.
    """
    if not discovery_tags:
        return True  # No tags to match = match all
    if not resource_tags:
        return False

    # Normalize resource tags to dict (handle both AWS tag formats)
    resource_tag_dict = {}
    for tag in resource_tags:
        key = tag.get('Key') or tag.get('key')
        value = tag.get('Value') or tag.get('value')
        if key:
            resource_tag_dict[key] = value

    # Check if all discovery tags match
    for tag_key, tag_value in discovery_tags.items():
        if resource_tag_dict.get(tag_key) != tag_value:
            return False
    return True


class ElastiCacheProvider(CacheProvider):
    """
    AWS ElastiCache implementation of the cache provider.
    Supports Redis, Valkey, and Memcached.
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

    def _get_elasticache_client(self, env: str):
        """Get ElastiCache client for environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client(
            'elasticache', env_config.account_id, env_config.region,
            project=self.project, env=env
        )

    def get_cache_cluster(self, env: str, discovery_tags: dict = None, cache_types: List[str] = None) -> dict:
        """Get ElastiCache Redis/Valkey info (filtered by discovery_tags and cache type)

        Args:
            env: Environment name
            discovery_tags: Dict of {tag_key: tag_value} to filter resources
            cache_types: List of cache types to look for (e.g., ["redis", "valkey"])
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.account_id
        elasticache = self._get_elasticache_client(env)
        cache_types = cache_types or ['redis']

        try:
            clusters = elasticache.describe_cache_clusters(ShowCacheNodeInfo=True)
            for cluster in clusters.get('CacheClusters', []):
                cluster_id = cluster['CacheClusterId']
                cache_engine = cluster['Engine'].lower()

                # Check if this cache type is in our requested list
                engine_matches = False
                for cache_type in cache_types:
                    if cache_type.lower() in cache_engine or cache_engine in cache_type.lower() or \
                       (cache_type.lower() == 'redis' and cache_engine == 'valkey'):
                        engine_matches = True
                        break
                if not engine_matches:
                    continue

                # Get ElastiCache tags and check if they match discovery_tags
                try:
                    cluster_arn = cluster['ARN']
                    tag_response = elasticache.list_tags_for_resource(ResourceName=cluster_arn)
                    cache_tags = tag_response.get('TagList', [])
                except Exception:
                    cache_tags = []

                # Check if discovery_tags match (or fallback to name-based matching)
                tags_match = matches_discovery_tags(cache_tags, discovery_tags) if discovery_tags else (self.project in cluster_id and env in cluster_id)

                if not tags_match:
                    continue

                # Get replication group info if available
                repl_group_id = cluster.get('ReplicationGroupId')
                repl_group_info = None
                if repl_group_id:
                    try:
                        repl_groups = elasticache.describe_replication_groups(ReplicationGroupId=repl_group_id)
                        if repl_groups.get('ReplicationGroups'):
                            repl_group_info = repl_groups['ReplicationGroups'][0]
                    except:
                        pass

                cache_nodes = cluster.get('CacheNodes', [])
                endpoint = None
                if repl_group_info and repl_group_info.get('ConfigurationEndpoint'):
                    endpoint = repl_group_info['ConfigurationEndpoint']
                elif repl_group_info and repl_group_info.get('NodeGroups'):
                    endpoint = repl_group_info['NodeGroups'][0].get('PrimaryEndpoint')
                elif cache_nodes:
                    endpoint = cache_nodes[0].get('Endpoint')

                nodes_by_az = {}
                for node in cache_nodes:
                    az = node.get('CustomerAvailabilityZone') or cluster.get('PreferredAvailabilityZone')
                    if az:
                        if az not in nodes_by_az:
                            nodes_by_az[az] = []
                        nodes_by_az[az].append({
                            'id': node.get('CacheNodeId'),
                            'status': node.get('CacheNodeStatus'),
                            'endpoint': node.get('Endpoint', {}).get('Address')
                        })

                multi_az = False
                if repl_group_info:
                    multi_az = repl_group_info.get('MultiAZ', 'disabled') == 'enabled'
                    if not multi_az and len(nodes_by_az) > 1:
                        multi_az = True

                return {
                    'clusterId': cluster_id,
                    'replicationGroupId': repl_group_id,
                    'engine': cluster['Engine'],
                    'engineVersion': cluster['EngineVersion'],
                    'cacheNodeType': cluster['CacheNodeType'],
                    'status': cluster['CacheClusterStatus'],
                    'numCacheNodes': cluster.get('NumCacheNodes', 0),
                    'multiAz': multi_az,
                    'nodesByAz': nodes_by_az,
                    'endpoint': {
                        'address': endpoint.get('Address') if endpoint else None,
                        'port': endpoint.get('Port') if endpoint else None
                    } if endpoint else None,
                    'preferredAvailabilityZone': cluster.get('PreferredAvailabilityZone'),
                    'snapshotRetentionLimit': cluster.get('SnapshotRetentionLimit', 0),
                    'snapshotWindow': cluster.get('SnapshotWindow'),
                    'maintenanceWindow': cluster.get('PreferredMaintenanceWindow'),
                    'transitEncryption': cluster.get('TransitEncryptionEnabled', False),
                    'atRestEncryption': cluster.get('AtRestEncryptionEnabled', False),
                    'authTokenEnabled': cluster.get('AuthTokenEnabled', False),
                    'securityGroups': [sg['SecurityGroupId'] for sg in cluster.get('SecurityGroups', [])],
                    'parameterGroup': cluster.get('CacheParameterGroup', {}).get('CacheParameterGroupName'),
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/elasticache/home?region={self.region}#/redis/{cluster_id}"
                    )
                }

            return None

        except Exception as e:
            return {'error': str(e)}


# Register the provider
ProviderFactory.register_cache_provider('elasticache', ElastiCacheProvider)
