"""
AWS RDS Database Provider implementation.
"""

from typing import Optional

from providers.base import DatabaseProvider, ProviderFactory
from config import DashboardConfig
from utils.aws import get_cross_account_client, get_action_client, build_sso_console_url


class RDSProvider(DatabaseProvider):
    """
    AWS RDS implementation of the database provider.
    """

    def __init__(self, config: DashboardConfig):
        self.config = config
        self.region = config.region

    def _get_rds_client(self, env: str):
        """Get RDS client for environment"""
        env_config = self.config.get_environment(env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client('rds', env_config.account_id, env_config.region)

    def get_database_status(self, env: str) -> dict:
        """Get RDS database status for an environment"""
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            rds = self._get_rds_client(env)
            db_identifier = self.config.get_db_identifier(env)

            db_instances = rds.describe_db_instances()
            for db in db_instances.get('DBInstances', []):
                db_id = db['DBInstanceIdentifier']
                # Match by pattern or exact name
                if db_id == db_identifier or (self.config.project_name in db_id and env in db_id):
                    return {
                        'identifier': db_id,
                        'engine': db['Engine'],
                        'engineVersion': db['EngineVersion'],
                        'instanceClass': db['DBInstanceClass'],
                        'status': db['DBInstanceStatus'],
                        'endpoint': db.get('Endpoint', {}).get('Address'),
                        'port': db.get('Endpoint', {}).get('Port'),
                        'storage': {
                            'allocated': db.get('AllocatedStorage'),
                            'type': db.get('StorageType'),
                            'iops': db.get('Iops'),
                            'encrypted': db.get('StorageEncrypted', False)
                        },
                        'multiAz': db.get('MultiAZ', False),
                        'availabilityZone': db.get('AvailabilityZone'),
                        'dbName': db.get('DBName'),
                        'masterUsername': db.get('MasterUsername'),
                        'backupRetention': db.get('BackupRetentionPeriod'),
                        'preferredBackupWindow': db.get('PreferredBackupWindow'),
                        'preferredMaintenanceWindow': db.get('PreferredMaintenanceWindow'),
                        'publiclyAccessible': db.get('PubliclyAccessible', False),
                        'securityGroups': [sg['VpcSecurityGroupId'] for sg in db.get('VpcSecurityGroups', [])],
                        'parameterGroup': db.get('DBParameterGroups', [{}])[0].get('DBParameterGroupName') if db.get('DBParameterGroups') else None,
                        'consoleUrl': build_sso_console_url(
                            self.config.sso_portal_url,
                            env_config.account_id,
                            f"https://{self.region}.console.aws.amazon.com/rds/home?region={self.region}#database:id={db_id};is-cluster=false"
                        ),
                        'accountId': env_config.account_id
                    }

            return {'error': f'Database not found for pattern: {db_identifier}'}

        except Exception as e:
            return {'error': str(e)}

    def start_database(self, env: str, user_email: str) -> dict:
        """Start RDS database"""
        return self._control_database(env, 'start', user_email)

    def stop_database(self, env: str, user_email: str) -> dict:
        """Stop RDS database"""
        return self._control_database(env, 'stop', user_email)

    def _control_database(self, env: str, action: str, user_email: str) -> dict:
        """Start or stop RDS database instance"""
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        db_identifier = self.config.get_db_identifier(env)

        try:
            rds = get_action_client('rds', env_config.account_id, user_email, env_config.region)

            # Find actual DB identifier if using pattern
            if not self._db_exists(env, db_identifier):
                # Search for matching DB
                read_rds = self._get_rds_client(env)
                db_instances = read_rds.describe_db_instances()
                for db in db_instances.get('DBInstances', []):
                    if self.config.project_name in db['DBInstanceIdentifier'] and env in db['DBInstanceIdentifier']:
                        db_identifier = db['DBInstanceIdentifier']
                        break

            if action == 'stop':
                rds.stop_db_instance(DBInstanceIdentifier=db_identifier)
            elif action == 'start':
                rds.start_db_instance(DBInstanceIdentifier=db_identifier)
            else:
                return {'error': f'Unknown action: {action}'}

            return {
                'success': True,
                'dbIdentifier': db_identifier,
                'action': action,
                'triggeredBy': user_email
            }
        except Exception as e:
            return {'error': str(e), 'dbIdentifier': db_identifier}

    def _db_exists(self, env: str, db_identifier: str) -> bool:
        """Check if DB exists with exact identifier"""
        try:
            rds = self._get_rds_client(env)
            rds.describe_db_instances(DBInstanceIdentifier=db_identifier)
            return True
        except:
            return False


# Register the provider
ProviderFactory.register_database_provider('rds', RDSProvider)
