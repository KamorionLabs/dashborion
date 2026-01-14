"""
AWS RDS Database Provider implementation.

Supports:
- Explicit identifiers
- Tag-based discovery
- Aurora clusters and DB instances
"""

from typing import Optional, Dict, List

from providers.base import DatabaseProvider, ProviderFactory
from app_config import DashboardConfig
from utils.aws import get_cross_account_client, get_action_client, build_sso_console_url


class RDSProvider(DatabaseProvider):
    """
    AWS RDS implementation of the database provider.

    Discovery order:
    1. Explicit identifiers (clusters, then instances)
    2. Tag-based discovery (clusters, then instances)
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

    def _get_rds_client(self, env: str):
        """Get RDS client for environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client(
            'rds', env_config.account_id, env_config.region,
            project=self.project, env=env
        )

    def _get_resourcegroupstaggingapi_client(self, env: str):
        """Get Resource Groups Tagging API client for tag-based discovery"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client(
            'resourcegroupstaggingapi', env_config.account_id, env_config.region,
            project=self.project, env=env
        )

    def _find_by_tags(self, env: str, discovery_tags: Dict[str, str], resource_type: str) -> Optional[str]:
        """Find RDS resource ARN by tags"""
        if not discovery_tags:
            return None

        try:
            tagging = self._get_resourcegroupstaggingapi_client(env)
            tag_filters = [{'Key': k, 'Values': [v]} for k, v in discovery_tags.items()]

            response = tagging.get_resources(
                ResourceTypeFilters=[f'rds:{resource_type}'],
                TagFilters=tag_filters
            )

            for resource in response.get('ResourceTagMappingList', []):
                return resource['ResourceARN']

            return None
        except Exception as e:
            print(f"Tag-based RDS discovery failed: {e}")
            return None

    def _extract_identifier_from_arn(self, arn: str) -> str:
        """Extract DB identifier from ARN"""
        # ARN format: arn:aws:rds:region:account:db:identifier or arn:aws:rds:region:account:cluster:identifier
        return arn.split(':')[-1]

    def get_database_status(self, env: str, discovery_tags: Dict[str, str] = None,
                           identifiers: Optional[List[str]] = None) -> dict:
        """Get RDS database status for an environment

        Args:
            env: Environment name
            discovery_tags: Dict of tags to find database (e.g., {'rubix_Environment': 'stg'})
            identifiers: Optional list of DB instance/cluster identifiers to match
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        if not identifiers and not discovery_tags:
            infra = env_config.infrastructure if hasattr(env_config, "infrastructure") else None
            if infra:
                rds_cfg = (infra.resources or {}).get("rds")
                if rds_cfg and rds_cfg.ids:
                    identifiers = rds_cfg.ids
                if rds_cfg and rds_cfg.tags:
                    discovery_tags = rds_cfg.tags
                elif infra.default_tags:
                    discovery_tags = infra.default_tags

        region = env_config.region
        account_id = env_config.account_id

        try:
            rds = self._get_rds_client(env)
            discovery_method = None

            # 1. Try explicit identifiers for Aurora clusters first
            cluster = None
            if identifiers:
                for cluster_id in identifiers:
                    try:
                        response = rds.describe_db_clusters(DBClusterIdentifier=cluster_id)
                        if response.get('DBClusters'):
                            cluster = response['DBClusters'][0]
                            discovery_method = 'id'
                            break
                    except Exception:
                        continue

            # 2. Try tag-based discovery for Aurora clusters
            if not cluster and discovery_tags:
                cluster_arn = self._find_by_tags(env, discovery_tags, 'cluster')
                if cluster_arn:
                    cluster_id = self._extract_identifier_from_arn(cluster_arn)
                    try:
                        response = rds.describe_db_clusters(DBClusterIdentifier=cluster_id)
                        if response.get('DBClusters'):
                            cluster = response['DBClusters'][0]
                            discovery_method = 'tags'
                    except Exception:
                        pass

            # If we found a cluster, return cluster info
            if cluster:
                # Get instance details for the cluster
                instances = []
                for member in cluster.get('DBClusterMembers', []):
                    instance_id = member['DBInstanceIdentifier']
                    try:
                        inst_response = rds.describe_db_instances(DBInstanceIdentifier=instance_id)
                        if inst_response.get('DBInstances'):
                            inst = inst_response['DBInstances'][0]
                            instances.append({
                                'identifier': instance_id,
                                'instanceClass': inst['DBInstanceClass'],
                                'status': inst['DBInstanceStatus'],
                                'isWriter': member.get('IsClusterWriter', False),
                                'availabilityZone': inst.get('AvailabilityZone')
                            })
                    except:
                        instances.append({
                            'identifier': instance_id,
                            'isWriter': member.get('IsClusterWriter', False)
                        })

                return {
                    'type': 'cluster',
                    'identifier': cluster['DBClusterIdentifier'],
                    'engine': cluster['Engine'],
                    'engineVersion': cluster['EngineVersion'],
                    'status': cluster['Status'],
                    'endpoint': cluster.get('Endpoint'),
                    'readerEndpoint': cluster.get('ReaderEndpoint'),
                    'port': cluster.get('Port'),
                    'storage': {
                        'allocated': cluster.get('AllocatedStorage'),
                        'encrypted': cluster.get('StorageEncrypted', False)
                    },
                    'multiAz': cluster.get('MultiAZ', False),
                    'dbName': cluster.get('DatabaseName'),
                    'masterUsername': cluster.get('MasterUsername'),
                    'backupRetention': cluster.get('BackupRetentionPeriod'),
                    'preferredBackupWindow': cluster.get('PreferredBackupWindow'),
                    'preferredMaintenanceWindow': cluster.get('PreferredMaintenanceWindow'),
                    'securityGroups': [sg['VpcSecurityGroupId'] for sg in cluster.get('VpcSecurityGroups', [])],
                    'parameterGroup': cluster.get('DBClusterParameterGroup'),
                    'instances': instances,
                    'discoveryMethod': discovery_method,
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url,
                        account_id,
                        f"https://{region}.console.aws.amazon.com/rds/home?region={region}#database:id={cluster['DBClusterIdentifier']};is-cluster=true"
                    ),
                    'accountId': account_id
                }

            # 3. Try explicit identifiers for standalone DB instances
            db_instance = None
            if identifiers and not cluster:
                for db_id in identifiers:
                    try:
                        response = rds.describe_db_instances(DBInstanceIdentifier=db_id)
                        if response.get('DBInstances'):
                            db_instance = response['DBInstances'][0]
                            discovery_method = 'id'
                            break
                    except Exception:
                        continue

            # 4. Try tag-based discovery for standalone DB instances
            if not db_instance and discovery_tags and not cluster:
                db_arn = self._find_by_tags(env, discovery_tags, 'db')
                if db_arn:
                    db_id = self._extract_identifier_from_arn(db_arn)
                    try:
                        response = rds.describe_db_instances(DBInstanceIdentifier=db_id)
                        if response.get('DBInstances'):
                            db_instance = response['DBInstances'][0]
                            discovery_method = 'tags'
                    except Exception:
                        pass

            if db_instance:
                return {
                    'type': 'instance',
                    'identifier': db_instance['DBInstanceIdentifier'],
                    'engine': db_instance['Engine'],
                    'engineVersion': db_instance['EngineVersion'],
                    'instanceClass': db_instance['DBInstanceClass'],
                    'status': db_instance['DBInstanceStatus'],
                    'endpoint': db_instance.get('Endpoint', {}).get('Address'),
                    'port': db_instance.get('Endpoint', {}).get('Port'),
                    'storage': {
                        'allocated': db_instance.get('AllocatedStorage'),
                        'type': db_instance.get('StorageType'),
                        'iops': db_instance.get('Iops'),
                        'encrypted': db_instance.get('StorageEncrypted', False)
                    },
                    'multiAz': db_instance.get('MultiAZ', False),
                    'availabilityZone': db_instance.get('AvailabilityZone'),
                    'dbName': db_instance.get('DBName'),
                    'masterUsername': db_instance.get('MasterUsername'),
                    'backupRetention': db_instance.get('BackupRetentionPeriod'),
                    'preferredBackupWindow': db_instance.get('PreferredBackupWindow'),
                    'preferredMaintenanceWindow': db_instance.get('PreferredMaintenanceWindow'),
                    'publiclyAccessible': db_instance.get('PubliclyAccessible', False),
                    'securityGroups': [sg['VpcSecurityGroupId'] for sg in db_instance.get('VpcSecurityGroups', [])],
                    'parameterGroup': db_instance.get('DBParameterGroups', [{}])[0].get('DBParameterGroupName') if db_instance.get('DBParameterGroups') else None,
                    'discoveryMethod': discovery_method,
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url,
                        account_id,
                        f"https://{region}.console.aws.amazon.com/rds/home?region={region}#database:id={db_instance['DBInstanceIdentifier']};is-cluster=false"
                    ),
                    'accountId': account_id
                }

            return None

        except Exception as e:
            return {'error': str(e)}

    def start_database(self, env: str, user_email: str) -> dict:
        """Start RDS database"""
        return self._control_database(env, 'start', user_email)

    def stop_database(self, env: str, user_email: str) -> dict:
        """Stop RDS database"""
        return self._control_database(env, 'stop', user_email)

    def _control_database(self, env: str, action: str, user_email: str) -> dict:
        """Start or stop RDS database instance or cluster"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            # First get current status to find the identifier
            status = self.get_database_status(env)
            if not status or 'error' in status:
                return {'error': f'Could not find database for environment: {env}'}

            db_identifier = status['identifier']
            is_cluster = status.get('type') == 'cluster'

            rds = get_action_client('rds', env_config.account_id, user_email, env_config.region)

            if is_cluster:
                if action == 'stop':
                    rds.stop_db_cluster(DBClusterIdentifier=db_identifier)
                elif action == 'start':
                    rds.start_db_cluster(DBClusterIdentifier=db_identifier)
            else:
                if action == 'stop':
                    rds.stop_db_instance(DBInstanceIdentifier=db_identifier)
                elif action == 'start':
                    rds.start_db_instance(DBInstanceIdentifier=db_identifier)

            return {
                'success': True,
                'dbIdentifier': db_identifier,
                'type': 'cluster' if is_cluster else 'instance',
                'action': action,
                'triggeredBy': user_email
            }
        except Exception as e:
            return {'error': str(e)}


# Register the provider
ProviderFactory.register_database_provider('rds', RDSProvider)
