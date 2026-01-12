"""
Infrastructure Aggregator - combines all infrastructure providers for the topology view.
"""

from typing import Dict, List, Optional

from app_config import DashboardConfig
from utils.aws import get_cross_account_client, build_sso_console_url
from providers.base import ProviderFactory


class InfrastructureAggregator:
    """
    Aggregates data from all infrastructure providers (CloudFront, ALB, RDS, ElastiCache, Network)
    to provide a unified infrastructure topology view.
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

        # Get individual providers
        self.network_provider = ProviderFactory.get_network_provider(config, project)
        self.loadbalancer_provider = ProviderFactory.get_loadbalancer_provider(config, project)
        self.cdn_provider = ProviderFactory.get_cdn_provider(config, project)
        self.database_provider = ProviderFactory.get_database_provider(config, project)
        self.cache_provider = ProviderFactory.get_cache_provider(config, project)

    def get_infrastructure(self, env: str, discovery_tags: dict = None, services: list = None,
                           domain_config: dict = None, databases: list = None, caches: list = None) -> dict:
        """Get infrastructure topology for an environment (CloudFront, ALB, S3, ECS services, RDS, Redis, Network)

        Args:
            env: Environment name (staging, preprod, production)
            discovery_tags: Dict of {tag_key: tag_value} to filter resources
            services: List of service names to look for
            domain_config: Dict with domain patterns
            databases: List of database types to look for (e.g., ["postgres", "mysql"])
            caches: List of cache types to look for (e.g., ["redis"])
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        # Default values for backwards compatibility
        services = services or ['backend', 'frontend', 'cms']
        databases = databases if databases is not None else ['postgres']
        caches = caches if caches is not None else ['redis']

        account_id = env_config.account_id
        domain_suffix = f"{env}.{self.project}.kamorion.cloud"

        # Domain patterns - use domain_config or fallback to defaults
        if domain_config and domain_config.get('domains'):
            domains_map = domain_config.get('domains', {})
            result_domains = {}
            for svc, prefix in domains_map.items():
                result_domains[svc] = f"https://{prefix}.{domain_suffix}"
        else:
            result_domains = {
                'frontend': f"https://fr.{domain_suffix}",
                'backend': f"https://back.{domain_suffix}",
                'cms': f"https://cms.{domain_suffix}"
            }

        # Determine orchestrator type
        orchestrator_type = getattr(self.config.orchestrator, 'type', 'ecs') if self.config.orchestrator else 'ecs'

        result = {
            'environment': env,
            'accountId': account_id,
            'domains': result_domains,
            'cloudfront': None,
            'alb': None,
            's3Buckets': [],
            'workloads': {},  # Unified term for services/deployments
            'rds': None,
            'redis': None,
            'efs': None,
            'network': None,
            'orchestrator': orchestrator_type
        }

        cloudfront_s3_origins = set()

        # Extract domain prefixes from domain_config for precise CloudFront matching
        domain_prefixes = None
        if domain_config and domain_config.get('domains'):
            domain_prefixes = list(domain_config['domains'].values())

        # For EKS: Get Ingress to find ALB hostname
        ingress_hostname = None
        ingresses = []
        if orchestrator_type == 'eks':
            try:
                orchestrator = ProviderFactory.get_orchestrator_provider(self.config, self.project)
                if hasattr(orchestrator, 'get_ingresses'):
                    ingresses = orchestrator.get_ingresses(env)
                    # Find the first ingress with a load balancer hostname
                    for ing in ingresses:
                        if ing.load_balancer_hostname:
                            ingress_hostname = ing.load_balancer_hostname
                            break
            except Exception as e:
                print(f"Failed to get ingresses for ALB discovery: {e}")

        # CloudFront (using dedicated provider with tag-based discovery)
        try:
            if self.cdn_provider:
                cf_data = self.cdn_provider.get_distribution(
                    env,
                    discovery_tags=discovery_tags,
                    domain_patterns=domain_prefixes
                )
                result['cloudfront'] = cf_data
                if cf_data and 'origins' in cf_data:
                    for origin in cf_data.get('origins', []):
                        if origin.get('type') == 's3':
                            bucket_name = origin['domainName'].split('.s3.')[0]
                            cloudfront_s3_origins.add(bucket_name)
        except Exception as e:
            result['cloudfront'] = {'error': str(e)}

        # ALB (using dedicated provider with tag-based and ingress-based discovery)
        try:
            if self.loadbalancer_provider:
                result['alb'] = self.loadbalancer_provider.get_load_balancer(
                    env,
                    services=services,
                    discovery_tags=discovery_tags,
                    ingress_hostname=ingress_hostname
                )
                # Enrich ALB with ingress info for EKS
                if result['alb'] and ingresses and orchestrator_type == 'eks':
                    result['alb']['ingresses'] = [
                        {
                            'name': ing.name,
                            'namespace': ing.namespace,
                            'hosts': [r.host for r in ing.rules if r.host],
                            'paths': [r.path for r in ing.rules if r.path]
                        }
                        for ing in ingresses
                    ]
        except Exception as e:
            result['alb'] = {'error': str(e)}

        # S3 Buckets (CloudFront origins only) - no dedicated provider needed, simple list
        try:
            s3 = get_cross_account_client('s3', account_id, env_config.region, project=self.project, env=env)
            buckets = s3.list_buckets()
            for bucket in buckets.get('Buckets', []):
                bucket_name = bucket['Name']
                if bucket_name in cloudfront_s3_origins:
                    bucket_type = 'frontend' if 'frontend' in bucket_name else 'cms-public' if 'cms-public' in bucket_name else 'assets' if 'assets' in bucket_name else 'other'
                    result['s3Buckets'].append({
                        'name': bucket_name,
                        'type': bucket_type,
                        'createdAt': bucket['CreationDate'].isoformat() if bucket.get('CreationDate') else None,
                        'consoleUrl': build_sso_console_url(
                            self.config.sso_portal_url, account_id,
                            f"https://s3.console.aws.amazon.com/s3/buckets/{bucket_name}?region={self.region}"
                        )
                    })
        except Exception as e:
            result['s3Buckets'] = [{'error': str(e)}]

        # Workloads (ECS Services or K8s Deployments)
        try:
            orchestrator = ProviderFactory.get_orchestrator_provider(self.config, self.project)

            if orchestrator_type == 'eks':
                # EKS: Use get_services which returns Service dataclass objects
                services_data = orchestrator.get_services(env)
                result['workloads'] = self._normalize_workloads_from_services(services_data, account_id)
            else:
                # ECS: Use original method
                result['workloads'] = orchestrator._get_services_for_infrastructure(
                    orchestrator._get_ecs_client(env),
                    env,
                    self.config.get_cluster_name(self.project, env),
                    account_id,
                    services
                )
        except Exception as e:
            result['workloads'] = {'error': str(e)}

        # RDS (using dedicated provider with tag-based discovery)
        try:
            if self.database_provider:
                result['rds'] = self.database_provider.get_database_status(
                    env,
                    discovery_tags=discovery_tags,
                    database_types=databases
                )
        except Exception as e:
            result['rds'] = {'error': str(e)}

        # EFS (for EKS clusters) - enriched with PVC data
        if orchestrator_type == 'eks':
            try:
                result['efs'] = self._get_efs_for_infrastructure(env, account_id, discovery_tags)

                # Enrich with PVC data if EFS was found
                if result['efs'] and not result['efs'].get('error'):
                    try:
                        orchestrator = ProviderFactory.get_orchestrator_provider(self.config, self.project)
                        if hasattr(orchestrator, 'get_efs_pvcs'):
                            efs_pvcs = orchestrator.get_efs_pvcs(env)
                            if efs_pvcs:
                                result['efs']['pvcs'] = [
                                    {
                                        'name': pvc.get('name'),
                                        'namespace': pvc.get('namespace'),
                                        'status': pvc.get('status'),
                                        'capacity': pvc.get('capacity'),
                                        'storageClass': pvc.get('storageClass'),
                                        'volumeMode': pvc.get('volumeMode'),
                                        'age': pvc.get('age'),
                                    }
                                    for pvc in efs_pvcs
                                ]
                                result['efs']['pvcCount'] = len(efs_pvcs)
                                # Calculate total EFS capacity from PVCs
                                total_bytes = sum(pvc.get('capacityBytes', 0) for pvc in efs_pvcs)
                                if total_bytes > 0:
                                    result['efs']['pvcTotalCapacity'] = self._format_capacity(total_bytes)
                    except Exception as e:
                        print(f"Failed to enrich EFS with PVC data: {e}")
            except Exception as e:
                result['efs'] = {'error': str(e)}

        # ElastiCache Redis (using dedicated provider)
        if caches:
            try:
                if self.cache_provider:
                    result['redis'] = self.cache_provider.get_cache_cluster(env, discovery_tags, caches)
            except Exception as e:
                result['redis'] = {'error': str(e)}

        # Network (using dedicated provider)
        try:
            if self.network_provider:
                result['network'] = self.network_provider.get_network_info(env)
        except Exception as e:
            result['network'] = {'error': str(e)}

        # Add 'services' alias for backward compatibility with frontend
        # Frontend components use data.services, unified backend uses workloads
        result['services'] = result['workloads']

        return result

    def _normalize_workloads_from_services(self, services_data: dict, account_id: str) -> dict:
        """Normalize Service dataclass objects to unified workload format.

        Converts EKS/ECS Service objects to a consistent dict format for the frontend.

        Args:
            services_data: Dict of {service_name: Service} or {service_name: {'error': ...}}
            account_id: AWS account ID for console URLs

        Returns:
            Dict of normalized workload data
        """
        if isinstance(services_data, dict) and 'error' in services_data:
            return services_data

        result = {}
        for name, svc in services_data.items():
            # Handle error cases
            if isinstance(svc, dict) and 'error' in svc:
                result[name] = svc
                continue

            try:
                # Convert Service dataclass to dict
                tasks = []
                tasks_by_location = {}

                for task in (svc.tasks or []):
                    task_info = {
                        'taskId': task.task_id[:8] if task.task_id else '',
                        'fullId': task.task_id,
                        'status': task.status.upper() if task.status else 'UNKNOWN',
                        'desiredStatus': task.desired_status.upper() if task.desired_status else 'RUNNING',
                        'health': task.health.upper() if task.health else 'UNKNOWN',
                        'revision': task.revision,
                        'isLatest': task.is_latest,
                        'az': task.az,  # Node name for EKS, AZ for ECS
                        'ip': task.private_ip,
                        'startedAt': task.started_at.isoformat() if task.started_at else None
                    }
                    tasks.append(task_info)

                    # Group by location (AZ for ECS, node for EKS)
                    location = task.az or 'unknown'
                    if location not in tasks_by_location:
                        tasks_by_location[location] = []
                    tasks_by_location[location].append(task_info)

                # Convert deployments
                deployments = []
                for dep in (svc.deployments or []):
                    deployments.append({
                        'status': dep.status.upper() if dep.status else 'PRIMARY',
                        'taskDefinition': dep.task_definition,
                        'revision': dep.revision,
                        'desiredCount': dep.desired_count,
                        'runningCount': dep.running_count,
                        'pendingCount': dep.pending_count,
                        'rolloutState': dep.rollout_state,
                        'rolloutStateReason': dep.rollout_reason,
                        'isPrimary': dep.status.lower() == 'primary' if dep.status else True
                    })

                # Check for rolling update
                is_rolling = len(deployments) > 1 or svc.pending_count > 0

                result[name] = {
                    'name': svc.name,
                    'type': 'k8s-deployment' if self.config.orchestrator and self.config.orchestrator.type == 'eks' else 'ecs-service',
                    'status': svc.status.upper() if svc.status else 'ACTIVE',
                    'runningCount': svc.running_count,
                    'desiredCount': svc.desired_count,
                    'pendingCount': svc.pending_count,
                    'health': 'healthy' if svc.running_count == svc.desired_count and svc.desired_count > 0 else 'unhealthy',
                    'currentRevision': svc.task_definition.get('revision') if svc.task_definition else None,
                    'image': svc.task_definition.get('image') if svc.task_definition else None,
                    'tasks': tasks,
                    'tasksByLocation': tasks_by_location,  # Unified: AZ or Node
                    'deployments': deployments,
                    'isRollingUpdate': is_rolling,
                    'consoleUrl': svc.console_url,
                    'selector': svc.selector if hasattr(svc, 'selector') else {},  # K8s selector for grouping
                }
            except Exception as e:
                result[name] = {'error': str(e)}

        return result

    def _get_cloudfront_for_infrastructure(self, env: str, domain_suffix: str, account_id: str, domain_prefixes: list = None) -> dict:
        """Get CloudFront distribution info with precise filtering

        Args:
            env: Environment name
            domain_suffix: e.g., 'staging.example.com'
            account_id: AWS account ID
            domain_prefixes: List of domain prefixes to match (e.g., ['fr', 'back', 'cms'])
        """
        env_config = self.config.get_environment(self.project, env)
        cloudfront = get_cross_account_client('cloudfront', account_id, project=self.project, env=env)

        distributions = cloudfront.list_distributions()
        for dist in distributions.get('DistributionList', {}).get('Items', []):
            aliases = dist.get('Aliases', {}).get('Items', [])

            # If domain_prefixes provided, match precisely; otherwise use broad matching
            if domain_prefixes:
                expected_aliases = [f"{prefix}.{domain_suffix}" for prefix in domain_prefixes]
                if not any(alias in expected_aliases for alias in aliases):
                    continue
            elif not any(domain_suffix in alias for alias in aliases):
                continue

            dist_id = dist['Id']
            cf_info = {
                'id': dist_id,
                'domainName': dist['DomainName'],
                'aliases': aliases,
                'status': dist['Status'],
                'enabled': dist['Enabled'],
                'origins': [],
                'cacheBehaviors': [],
                'webAclId': None,
                'consoleUrl': build_sso_console_url(
                    self.config.sso_portal_url, account_id,
                    f"https://console.aws.amazon.com/cloudfront/v4/home#/distributions/{dist_id}"
                )
            }

            for origin in dist.get('Origins', {}).get('Items', []):
                origin_domain = origin['DomainName']
                origin_type = 'alb' if 'elb.amazonaws.com' in origin_domain else 's3' if 's3.' in origin_domain else 'custom'
                cf_info['origins'].append({
                    'id': origin['Id'],
                    'domainName': origin_domain,
                    'type': origin_type,
                    'path': origin.get('OriginPath', '')
                })

            try:
                dist_config = cloudfront.get_distribution(Id=dist_id)
                dist_detail = dist_config.get('Distribution', {}).get('DistributionConfig', {})
                cf_info['webAclId'] = dist_detail.get('WebACLId', '') or None

                default_behavior = dist_detail.get('DefaultCacheBehavior', {})
                if default_behavior:
                    cf_info['cacheBehaviors'].append({
                        'pathPattern': 'Default (*)',
                        'targetOriginId': default_behavior.get('TargetOriginId'),
                        'viewerProtocolPolicy': default_behavior.get('ViewerProtocolPolicy'),
                        'defaultTTL': default_behavior.get('DefaultTTL', 0),
                        'compress': default_behavior.get('Compress', False),
                        'lambdaEdge': len(default_behavior.get('LambdaFunctionAssociations', {}).get('Items', [])) > 0
                    })

                for behavior in dist_detail.get('CacheBehaviors', {}).get('Items', []):
                    cf_info['cacheBehaviors'].append({
                        'pathPattern': behavior.get('PathPattern'),
                        'targetOriginId': behavior.get('TargetOriginId'),
                        'viewerProtocolPolicy': behavior.get('ViewerProtocolPolicy'),
                        'defaultTTL': behavior.get('DefaultTTL', 0),
                        'compress': behavior.get('Compress', False),
                        'lambdaEdge': len(behavior.get('LambdaFunctionAssociations', {}).get('Items', [])) > 0
                    })
            except:
                pass
            return cf_info
        return None

    def _get_rds_for_infrastructure(self, env: str, account_id: str, discovery_tags: dict = None, databases: list = None) -> dict:
        """Get RDS database info (filtered by discovery_tags and database type)"""
        env_config = self.config.get_environment(self.project, env)
        rds = get_cross_account_client('rds', account_id, env_config.region, project=self.project, env=env)
        databases = databases or ['postgres']

        db_instances = rds.describe_db_instances()
        for db in db_instances.get('DBInstances', []):
            db_id = db['DBInstanceIdentifier']
            db_engine = db['Engine'].lower()

            # Check if this database type is in our requested list
            engine_matches = False
            for db_type in databases:
                if db_type.lower() in db_engine or db_engine in db_type.lower():
                    engine_matches = True
                    break
            if not engine_matches:
                continue

            # Get RDS tags and check if they match discovery_tags
            try:
                db_arn = db['DBInstanceArn']
                tag_response = rds.list_tags_for_resource(ResourceName=db_arn)
                db_tags = tag_response.get('TagList', [])
            except Exception:
                db_tags = []

            # Check if discovery_tags match (or fallback to name-based matching)
            from providers.infrastructure.elasticache import matches_discovery_tags
            tags_match = matches_discovery_tags(db_tags, discovery_tags) if discovery_tags else (self.project in db_id and env in db_id)

            if tags_match:
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
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/rds/home?region={self.region}#database:id={db_id};is-cluster=false"
                    )
                }
        return None

    def _format_capacity(self, bytes_value: int) -> str:
        """Format bytes to human-readable capacity."""
        if bytes_value >= 1024**4:
            return f"{bytes_value / 1024**4:.0f}Ti"
        elif bytes_value >= 1024**3:
            return f"{bytes_value / 1024**3:.0f}Gi"
        elif bytes_value >= 1024**2:
            return f"{bytes_value / 1024**2:.0f}Mi"
        elif bytes_value >= 1024:
            return f"{bytes_value / 1024:.0f}Ki"
        return f"{bytes_value}"

    def _get_efs_for_infrastructure(self, env: str, account_id: str, discovery_tags: dict = None) -> dict:
        """Get EFS filesystem info (filtered by discovery_tags)

        Args:
            env: Environment name
            account_id: AWS account ID
            discovery_tags: Dict of tags to filter EFS filesystems
        """
        env_config = self.config.get_environment(self.project, env)
        efs = get_cross_account_client('efs', account_id, env_config.region, project=self.project, env=env)

        try:
            filesystems = efs.describe_file_systems()
            for fs in filesystems.get('FileSystems', []):
                fs_id = fs['FileSystemId']
                fs_name = fs.get('Name', fs_id)

                # Get EFS tags
                try:
                    tag_response = efs.describe_tags(FileSystemId=fs_id)
                    fs_tags = tag_response.get('Tags', [])
                except Exception:
                    fs_tags = []

                # Check if discovery_tags match (or fallback to name-based matching)
                from providers.infrastructure.elasticache import matches_discovery_tags
                tags_match = matches_discovery_tags(fs_tags, discovery_tags) if discovery_tags else (self.project.replace('-', '') in fs_name.lower().replace('-', ''))

                if tags_match:
                    return {
                        'fileSystemId': fs_id,
                        'name': fs_name,
                        'lifeCycleState': fs['LifeCycleState'],
                        'sizeInBytes': fs.get('SizeInBytes', {}).get('Value', 0),
                        'performanceMode': fs.get('PerformanceMode', 'generalPurpose'),
                        'throughputMode': fs.get('ThroughputMode', 'bursting'),
                        'encrypted': fs.get('Encrypted', False),
                        'numberOfMountTargets': fs.get('NumberOfMountTargets', 0),
                        'consoleUrl': build_sso_console_url(
                            self.config.sso_portal_url, account_id,
                            f"https://{env_config.region}.console.aws.amazon.com/efs/home?region={env_config.region}#/file-systems/{fs_id}"
                        )
                    }
            return None
        except Exception as e:
            return {'error': str(e)}

    def get_routing_details(self, env: str, service_security_groups: list = None) -> dict:
        """Get detailed routing and security information (called on demand via toggle)

        Args:
            env: Environment name
            service_security_groups: List of security group IDs to filter (only show SGs associated with services)
        """
        if self.network_provider:
            return self.network_provider.get_routing_details(env, service_security_groups)
        return {'error': 'Network provider not available'}

    def get_enis(self, env: str, vpc_id: str = None, subnet_id: str = None, search_ip: str = None) -> dict:
        """Get ENIs (Elastic Network Interfaces) for a VPC or subnet

        Args:
            env: Environment name
            vpc_id: Optional VPC ID filter (if not provided, uses project VPC)
            subnet_id: Optional subnet ID filter
            search_ip: Optional IP address search term
        """
        if self.network_provider:
            return self.network_provider.get_enis(env, vpc_id, subnet_id, search_ip)
        return {'error': 'Network provider not available'}

    def get_security_group(self, env: str, sg_id: str) -> dict:
        """Get detailed Security Group information including rules

        Args:
            env: Environment name
            sg_id: Security Group ID
        """
        if self.network_provider:
            return self.network_provider.get_security_group(env, sg_id)
        return {'error': 'Network provider not available'}
