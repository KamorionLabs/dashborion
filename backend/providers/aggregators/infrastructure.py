"""
Infrastructure Aggregator - combines all infrastructure providers for the topology view.
"""

from typing import Dict, List, Optional

from app_config import DashboardConfig, InfrastructureConfig
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

    def _resolve_resource_filters(self, infra_config: Optional[InfrastructureConfig], resource: str) -> Dict[str, Optional[object]]:
        if not infra_config:
            return {"ids": None, "tags": None}
        resource_cfg = (infra_config.resources or {}).get(resource)
        ids = resource_cfg.ids if resource_cfg and resource_cfg.ids else None
        tags = resource_cfg.tags if resource_cfg and resource_cfg.tags else infra_config.default_tags or None
        return {"ids": ids, "tags": tags}

    def _discover_services(self, env: str, env_config, orchestrator_type: str) -> List[str]:
        """Discover services/workloads when env.services is empty."""
        try:
            orchestrator = ProviderFactory.get_orchestrator_provider(self.config, self.project)
            names = []

            if orchestrator_type == 'eks':
                deployments = orchestrator.get_deployments(env, namespace=env_config.namespace)
                names = [deploy.name for deploy in deployments if deploy and deploy.name]
            else:
                ecs = orchestrator._get_ecs_client(env)
                cluster_name = self.config.get_cluster_name(self.project, env)
                paginator = ecs.get_paginator('list_services')
                service_arns = []
                for page in paginator.paginate(cluster=cluster_name):
                    service_arns.extend(page.get('serviceArns', []))
                names = [arn.split('/')[-1] for arn in service_arns if arn]

            if not names:
                return []

            normalized = []
            for name in names:
                short = self.config.strip_service_name(self.project, env, name, strict=True)
                if short:
                    normalized.append(short)

            if normalized:
                return sorted(set(normalized))

            fallback = [
                self.config.strip_service_name(self.project, env, name, strict=False)
                for name in names
            ]
            return sorted(set([name for name in fallback if name]))
        except Exception as e:
            print(f"Failed to discover services for {self.project}/{env}: {e}")
            return []

    def get_infrastructure(self, env: str, services: list = None,
                           infra_config: Optional[InfrastructureConfig] = None,
                           resources: Optional[List[str]] = None) -> dict:
        """Get infrastructure topology for an environment (CloudFront, ALB, S3, ECS services, RDS, Redis, Network)

        Args:
            env: Environment name (staging, preprod, production)
            services: List of service names to look for
            infra_config: InfrastructureConfig with resource filters
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        services = services or env_config.services or []

        account_id = env_config.account_id
        domain_suffix = f"{env}.{self.project}.kamorion.cloud"
        domain_config = infra_config.domain_config if infra_config else None

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

        resource_set = set(resources) if resources else None

        def should_fetch(name: str) -> bool:
            return resource_set is None or name in resource_set

        needs_services = resource_set is None or any(
            name in resource_set for name in ('workloads', 'alb')
        )
        if needs_services and not services:
            services = self._discover_services(env, env_config, orchestrator_type)

        cloudfront_filters = self._resolve_resource_filters(infra_config, 'cloudfront')
        alb_filters = self._resolve_resource_filters(infra_config, 'alb')
        rds_filters = self._resolve_resource_filters(infra_config, 'rds')
        redis_filters = self._resolve_resource_filters(infra_config, 'redis')
        efs_filters = self._resolve_resource_filters(infra_config, 'efs')
        network_filters = self._resolve_resource_filters(infra_config, 'network')
        s3_filters = self._resolve_resource_filters(infra_config, 's3')

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
        if should_fetch('cloudfront') or should_fetch('s3'):
            try:
                if self.cdn_provider and (cloudfront_filters["ids"] or cloudfront_filters["tags"] or domain_prefixes):
                    cf_data = self.cdn_provider.get_distribution(
                        env,
                        discovery_tags=cloudfront_filters["tags"],
                        distribution_ids=cloudfront_filters["ids"],
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
        if should_fetch('alb'):
            try:
                if self.loadbalancer_provider and (alb_filters["ids"] or alb_filters["tags"] or ingress_hostname):
                    result['alb'] = self.loadbalancer_provider.get_load_balancer(
                        env,
                        services=services,
                        discovery_tags=alb_filters["tags"],
                        alb_arns=alb_filters["ids"],
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
        if should_fetch('s3'):
            try:
                s3 = get_cross_account_client('s3', account_id, env_config.region, project=self.project, env=env)
                buckets = s3.list_buckets()
                from providers.infrastructure.elasticache import matches_discovery_tags

                s3_ids = set(s3_filters["ids"] or [])
                use_tag_filter = bool(s3_filters["tags"]) and not s3_ids

                for bucket in buckets.get('Buckets', []):
                    bucket_name = bucket['Name']
                    include_bucket = False

                    if s3_ids:
                        include_bucket = bucket_name in s3_ids
                    elif use_tag_filter:
                        try:
                            tag_response = s3.get_bucket_tagging(Bucket=bucket_name)
                            bucket_tags = tag_response.get('TagSet', [])
                        except Exception:
                            bucket_tags = []
                        include_bucket = matches_discovery_tags(bucket_tags, s3_filters["tags"])
                    else:
                        include_bucket = bucket_name in cloudfront_s3_origins

                    if include_bucket:
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
        if should_fetch('workloads'):
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
        if should_fetch('rds') and (rds_filters["ids"] or rds_filters["tags"]):
            try:
                if self.database_provider:
                    result['rds'] = self.database_provider.get_database_status(
                        env,
                        discovery_tags=rds_filters["tags"],
                        identifiers=rds_filters["ids"]
                    )
            except Exception as e:
                result['rds'] = {'error': str(e)}

        # EFS (for EKS clusters) - enriched with PVC data
        if should_fetch('efs') and orchestrator_type == 'eks' and (efs_filters["ids"] or efs_filters["tags"]):
            try:
                result['efs'] = self._get_efs_for_infrastructure(
                    env,
                    account_id,
                    ids=efs_filters["ids"],
                    discovery_tags=efs_filters["tags"]
                )

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
        if should_fetch('redis') and (redis_filters["ids"] or redis_filters["tags"]):
            try:
                if self.cache_provider:
                    result['redis'] = self.cache_provider.get_cache_cluster(
                        env,
                        discovery_tags=redis_filters["tags"],
                        cluster_ids=redis_filters["ids"]
                    )
            except Exception as e:
                result['redis'] = {'error': str(e)}

        # Network (using dedicated provider with tag-based discovery)
        # For EKS, also get VPC ID from cluster for more reliable discovery
        if should_fetch('network') and (network_filters["ids"] or network_filters["tags"]):
            eks_vpc_id = None
            if orchestrator_type == 'eks':
                try:
                    orchestrator = ProviderFactory.get_orchestrator_provider(self.config, self.project)
                    if hasattr(orchestrator, 'get_infrastructure'):
                        eks_infra = orchestrator.get_infrastructure(env)
                        if eks_infra and 'network' in eks_infra:
                            eks_vpc_id = eks_infra['network'].get('vpcId')
                except Exception as e:
                    print(f"Failed to get VPC ID from EKS cluster: {e}")

            try:
                if self.network_provider:
                    vpc_id = network_filters["ids"][0] if network_filters["ids"] else eks_vpc_id
                    result['network'] = self.network_provider.get_network_info(
                        env,
                        vpc_id=vpc_id,
                        discovery_tags=network_filters["tags"]
                    )
            except Exception as e:
                result['network'] = {'error': str(e)}

        # Add 'services' alias for backward compatibility with frontend
        # Frontend components use data.services, unified backend uses workloads
        if should_fetch('workloads'):
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

    def _get_efs_for_infrastructure(self, env: str, account_id: str,
                                    ids: Optional[List[str]] = None,
                                    discovery_tags: dict = None) -> dict:
        """Get EFS filesystem info (filtered by IDs or tags)

        Args:
            env: Environment name
            account_id: AWS account ID
            ids: Optional list of EFS fileSystemIds to match
            discovery_tags: Dict of tags to filter EFS filesystems
        """
        env_config = self.config.get_environment(self.project, env)
        efs = get_cross_account_client('efs', account_id, env_config.region, project=self.project, env=env)
        if not ids and not discovery_tags:
            return None

        try:
            filesystems = efs.describe_file_systems()
            for fs in filesystems.get('FileSystems', []):
                fs_id = fs['FileSystemId']
                fs_name = fs.get('Name', fs_id)

                if ids and fs_id not in ids:
                    continue

                # Get EFS tags
                try:
                    tag_response = efs.describe_tags(FileSystemId=fs_id)
                    fs_tags = tag_response.get('Tags', [])
                except Exception:
                    fs_tags = []

                # Check if discovery_tags match
                from providers.infrastructure.elasticache import matches_discovery_tags
                tags_match = matches_discovery_tags(fs_tags, discovery_tags) if discovery_tags else True

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

    def get_routing_details(self, env: str, service_security_groups: list = None,
                            vpc_id: str = None, discovery_tags: dict = None) -> dict:
        """Get detailed routing and security information (called on demand via toggle)

        Args:
            env: Environment name
            service_security_groups: List of security group IDs to filter (only show SGs associated with services)
            vpc_id: Optional VPC ID (from previous get_infrastructure call or EKS cluster)
            discovery_tags: Optional tags for VPC discovery
        """
        # For EKS, try to get VPC ID from cluster if not provided
        if not vpc_id:
            orchestrator_type = getattr(self.config.orchestrator, 'type', 'ecs') if self.config.orchestrator else 'ecs'
            if orchestrator_type == 'eks':
                try:
                    orchestrator = ProviderFactory.get_orchestrator_provider(self.config, self.project)
                    if hasattr(orchestrator, 'get_infrastructure'):
                        eks_infra = orchestrator.get_infrastructure(env)
                        if eks_infra and 'network' in eks_infra:
                            vpc_id = eks_infra['network'].get('vpcId')
                except Exception as e:
                    print(f"Failed to get VPC ID from EKS cluster for routing: {e}")

        if self.network_provider:
            return self.network_provider.get_routing_details(
                env,
                service_security_groups,
                vpc_id=vpc_id,
                discovery_tags=discovery_tags
            )
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
