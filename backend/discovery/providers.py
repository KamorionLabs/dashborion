"""
AWS Resource Discovery Providers.

Each function discovers resources of a specific type in a target AWS account
using cross-account role assumption.
"""

from typing import Dict, List, Any, Optional
import boto3


def get_cross_account_client(service: str, role_arn: str, region: str):
    """
    Get boto3 client with cross-account role assumption.

    Args:
        service: AWS service name (e.g., 'ec2', 'eks')
        role_arn: ARN of the role to assume
        region: AWS region

    Returns:
        boto3 client for the specified service in the target account
    """
    sts = boto3.client('sts')
    assumed = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='dashborion-discovery'
    )

    credentials = assumed['Credentials']
    return boto3.client(
        service,
        region_name=region,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )


def discover_vpcs(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover VPCs in the target account.

    Returns list of VPCs with id, name, cidr, and tags.
    """
    ec2 = get_cross_account_client('ec2', role_arn, region)
    response = ec2.describe_vpcs()

    vpcs = []
    for vpc in response.get('Vpcs', []):
        name = ''
        for tag in vpc.get('Tags', []):
            if tag['Key'] == 'Name':
                name = tag['Value']
                break

        vpcs.append({
            'id': vpc['VpcId'],
            'name': name or vpc['VpcId'],
            'cidr': vpc.get('CidrBlock'),
            'isDefault': vpc.get('IsDefault', False),
            'state': vpc.get('State'),
            'tags': {t['Key']: t['Value'] for t in vpc.get('Tags', [])},
        })

    return sorted(vpcs, key=lambda x: (x['isDefault'], x['name']))


def discover_route53_zones(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover Route53 hosted zones.

    Note: Route53 is a global service, region is ignored but kept for consistency.
    """
    # Route53 is global, use us-east-1
    route53 = get_cross_account_client('route53', role_arn, 'us-east-1')
    response = route53.list_hosted_zones()

    zones = []
    for zone in response.get('HostedZones', []):
        zone_id = zone['Id'].replace('/hostedzone/', '')
        zones.append({
            'id': zone_id,
            'name': zone['Name'].rstrip('.'),
            'private': zone.get('Config', {}).get('PrivateZone', False),
            'recordCount': zone.get('ResourceRecordSetCount', 0),
            'comment': zone.get('Config', {}).get('Comment', ''),
        })

    return sorted(zones, key=lambda x: x['name'])


def discover_eks_clusters(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover EKS clusters in the target account.
    """
    eks = get_cross_account_client('eks', role_arn, region)
    response = eks.list_clusters()

    clusters = []
    for cluster_name in response.get('clusters', []):
        try:
            detail = eks.describe_cluster(name=cluster_name)
            cluster = detail.get('cluster', {})
            clusters.append({
                'id': cluster_name,
                'name': cluster_name,
                'arn': cluster.get('arn'),
                'version': cluster.get('version'),
                'status': cluster.get('status'),
                'endpoint': cluster.get('endpoint'),
                'vpcId': cluster.get('resourcesVpcConfig', {}).get('vpcId'),
                'createdAt': cluster.get('createdAt').isoformat() if cluster.get('createdAt') else None,
                'tags': cluster.get('tags', {}),
            })
        except Exception as e:
            # Skip clusters we can't describe
            clusters.append({
                'id': cluster_name,
                'name': cluster_name,
                'error': str(e),
            })

    return sorted(clusters, key=lambda x: x['name'])


def discover_eks_namespaces(role_arn: str, region: str, cluster_name: str) -> List[Dict[str, Any]]:
    """
    Discover Kubernetes namespaces in an EKS cluster.
    Requires kubernetes client and proper IAM/K8s RBAC permissions.
    """
    try:
        from kubernetes import client as k8s_client
        from kubernetes.client import Configuration
    except ImportError:
        return [{'error': 'kubernetes package not installed'}]

    # Get EKS cluster info and auth token
    eks = get_cross_account_client('eks', role_arn, region)
    cluster_info = eks.describe_cluster(name=cluster_name)['cluster']

    # Get authentication token
    sts = boto3.client('sts')
    assumed = sts.assume_role(RoleArn=role_arn, RoleSessionName='eks-discovery')
    credentials = assumed['Credentials']

    # Create STS client with assumed credentials for token
    sts_assumed = boto3.client(
        'sts',
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name=region
    )

    # Get bearer token
    token = sts_assumed.get_caller_identity()  # This won't work directly, need presigned URL
    # Simplified: use boto3's get_token approach
    import base64
    from botocore.signers import RequestSigner

    session = boto3.Session(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name=region
    )
    sts_client = session.client('sts', region_name=region)
    service_id = sts_client.meta.service_model.service_id

    signer = RequestSigner(
        service_id,
        region,
        'sts',
        'v4',
        session.get_credentials(),
        session.events
    )

    params = {
        'method': 'GET',
        'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
        'body': {},
        'headers': {'x-k8s-aws-id': cluster_name},
        'context': {}
    }

    signed_url = signer.generate_presigned_url(params, region_name=region, expires_in=60, operation_name='')
    token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8').rstrip('=')

    # Configure K8s client
    configuration = Configuration()
    configuration.host = cluster_info['endpoint']
    configuration.verify_ssl = True
    configuration.ssl_ca_cert = None  # Would need to write CA to temp file
    configuration.api_key = {'authorization': f'Bearer {token}'}

    # For simplicity, disable SSL verification (not recommended for production)
    configuration.verify_ssl = False

    api_client = k8s_client.ApiClient(configuration)
    v1 = k8s_client.CoreV1Api(api_client)

    namespaces = []
    try:
        ns_list = v1.list_namespace()
        for ns in ns_list.items:
            namespaces.append({
                'id': ns.metadata.name,
                'name': ns.metadata.name,
                'status': ns.status.phase,
                'labels': ns.metadata.labels or {},
            })
    except Exception as e:
        return [{'error': f'Failed to list namespaces: {str(e)}'}]

    return sorted(namespaces, key=lambda x: x['name'])


def discover_eks_workloads(role_arn: str, region: str, cluster_name: str, namespace: str) -> List[Dict[str, Any]]:
    """
    Discover Kubernetes workloads (Deployments, StatefulSets) in an EKS namespace.
    Returns a simplified list for service selection.
    """
    try:
        from kubernetes import client as k8s_client
        from kubernetes.client import Configuration
    except ImportError:
        return [{'error': 'kubernetes package not installed'}]

    eks = get_cross_account_client('eks', role_arn, region)
    cluster_info = eks.describe_cluster(name=cluster_name)['cluster']

    sts = boto3.client('sts')
    assumed = sts.assume_role(RoleArn=role_arn, RoleSessionName='eks-discovery')
    credentials = assumed['Credentials']

    import base64
    from botocore.signers import RequestSigner

    session = boto3.Session(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name=region
    )
    sts_client = session.client('sts', region_name=region)
    service_id = sts_client.meta.service_model.service_id

    signer = RequestSigner(
        service_id,
        region,
        'sts',
        'v4',
        session.get_credentials(),
        session.events
    )

    params = {
        'method': 'GET',
        'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
        'body': {},
        'headers': {'x-k8s-aws-id': cluster_name},
        'context': {}
    }

    signed_url = signer.generate_presigned_url(params, region_name=region, expires_in=60, operation_name='')
    token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8').rstrip('=')

    configuration = Configuration()
    configuration.host = cluster_info['endpoint']
    configuration.verify_ssl = True
    configuration.ssl_ca_cert = None
    configuration.api_key = {'authorization': f'Bearer {token}'}
    configuration.verify_ssl = False

    api_client = k8s_client.ApiClient(configuration)
    apps = k8s_client.AppsV1Api(api_client)

    workloads = []
    try:
        deployments = apps.list_namespaced_deployment(namespace)
        for dep in deployments.items:
            workloads.append({
                'id': dep.metadata.name,
                'name': dep.metadata.name,
                'type': 'k8s-deployment',
                'kind': 'Deployment',
                'desiredCount': dep.spec.replicas,
                'availableCount': dep.status.available_replicas or 0,
            })
    except Exception as e:
        return [{'error': f'Failed to list deployments: {str(e)}'}]

    try:
        statefulsets = apps.list_namespaced_stateful_set(namespace)
        for sts in statefulsets.items:
            workloads.append({
                'id': sts.metadata.name,
                'name': sts.metadata.name,
                'type': 'k8s-statefulset',
                'kind': 'StatefulSet',
                'desiredCount': sts.spec.replicas,
                'availableCount': sts.status.ready_replicas or 0,
            })
    except Exception as e:
        return [{'error': f'Failed to list statefulsets: {str(e)}'}]

    return sorted(workloads, key=lambda x: x['name'])


def discover_ecs_clusters(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover ECS clusters in the target account.
    """
    ecs = get_cross_account_client('ecs', role_arn, region)
    response = ecs.list_clusters()

    clusters = []
    cluster_arns = response.get('clusterArns', [])

    if cluster_arns:
        details = ecs.describe_clusters(clusters=cluster_arns, include=['TAGS'])
        for cluster in details.get('clusters', []):
            clusters.append({
                'id': cluster['clusterName'],
                'name': cluster['clusterName'],
                'arn': cluster['clusterArn'],
                'status': cluster.get('status'),
                'runningTasksCount': cluster.get('runningTasksCount', 0),
                'pendingTasksCount': cluster.get('pendingTasksCount', 0),
                'activeServicesCount': cluster.get('activeServicesCount', 0),
                'registeredContainerInstancesCount': cluster.get('registeredContainerInstancesCount', 0),
                'tags': {t['key']: t['value'] for t in cluster.get('tags', [])},
            })

    return sorted(clusters, key=lambda x: x['name'])


def discover_ecs_services(role_arn: str, region: str, cluster_name: str) -> List[Dict[str, Any]]:
    """
    Discover ECS services in a specific cluster.
    """
    ecs = get_cross_account_client('ecs', role_arn, region)

    services = []
    paginator = ecs.get_paginator('list_services')

    service_arns = []
    for page in paginator.paginate(cluster=cluster_name):
        service_arns.extend(page.get('serviceArns', []))

    if service_arns:
        # Describe services in batches of 10 (API limit)
        for i in range(0, len(service_arns), 10):
            batch = service_arns[i:i+10]
            details = ecs.describe_services(cluster=cluster_name, services=batch)
            for svc in details.get('services', []):
                services.append({
                    'id': svc['serviceName'],
                    'name': svc['serviceName'],
                    'arn': svc['serviceArn'],
                    'status': svc.get('status'),
                    'desiredCount': svc.get('desiredCount', 0),
                    'runningCount': svc.get('runningCount', 0),
                    'launchType': svc.get('launchType'),
                    'taskDefinition': svc.get('taskDefinition', '').split('/')[-1],
                })

    return sorted(services, key=lambda x: x['name'])


def discover_rds_clusters(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover RDS/Aurora clusters and instances in the target account.
    """
    rds = get_cross_account_client('rds', role_arn, region)

    resources = []

    # Aurora clusters
    try:
        response = rds.describe_db_clusters()
        for cluster in response.get('DBClusters', []):
            resources.append({
                'id': cluster['DBClusterIdentifier'],
                'name': cluster['DBClusterIdentifier'],
                'type': 'aurora-cluster',
                'engine': cluster.get('Engine'),
                'engineVersion': cluster.get('EngineVersion'),
                'status': cluster.get('Status'),
                'endpoint': cluster.get('Endpoint'),
                'readerEndpoint': cluster.get('ReaderEndpoint'),
                'port': cluster.get('Port'),
                'multiAz': cluster.get('MultiAZ', False),
                'storageEncrypted': cluster.get('StorageEncrypted', False),
            })
    except Exception:
        pass

    # Standalone RDS instances (not part of Aurora)
    try:
        response = rds.describe_db_instances()
        for instance in response.get('DBInstances', []):
            # Skip instances that are part of an Aurora cluster
            if instance.get('DBClusterIdentifier'):
                continue
            resources.append({
                'id': instance['DBInstanceIdentifier'],
                'name': instance['DBInstanceIdentifier'],
                'type': 'rds-instance',
                'engine': instance.get('Engine'),
                'engineVersion': instance.get('EngineVersion'),
                'status': instance.get('DBInstanceStatus'),
                'endpoint': instance.get('Endpoint', {}).get('Address'),
                'port': instance.get('Endpoint', {}).get('Port'),
                'instanceClass': instance.get('DBInstanceClass'),
                'multiAz': instance.get('MultiAZ', False),
                'storageEncrypted': instance.get('StorageEncrypted', False),
            })
    except Exception:
        pass

    return sorted(resources, key=lambda x: x['name'])


def discover_documentdb_clusters(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover DocumentDB clusters in the target account.
    """
    docdb = get_cross_account_client('docdb', role_arn, region)

    clusters = []
    try:
        response = docdb.describe_db_clusters()
        for cluster in response.get('DBClusters', []):
            # DocumentDB uses 'docdb' engine
            if cluster.get('Engine') == 'docdb':
                clusters.append({
                    'id': cluster['DBClusterIdentifier'],
                    'name': cluster['DBClusterIdentifier'],
                    'engine': cluster.get('Engine'),
                    'engineVersion': cluster.get('EngineVersion'),
                    'status': cluster.get('Status'),
                    'endpoint': cluster.get('Endpoint'),
                    'readerEndpoint': cluster.get('ReaderEndpoint'),
                    'port': cluster.get('Port'),
                    'storageEncrypted': cluster.get('StorageEncrypted', False),
                })
    except Exception:
        pass

    return sorted(clusters, key=lambda x: x['name'])


def discover_elasticache_clusters(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover ElastiCache clusters (Redis/Memcached) in the target account.
    """
    elasticache = get_cross_account_client('elasticache', role_arn, region)

    clusters = []

    # Replication groups (Redis cluster mode)
    try:
        response = elasticache.describe_replication_groups()
        for group in response.get('ReplicationGroups', []):
            clusters.append({
                'id': group['ReplicationGroupId'],
                'name': group['ReplicationGroupId'],
                'type': 'replication-group',
                'engine': 'redis',
                'status': group.get('Status'),
                'clusterEnabled': group.get('ClusterEnabled', False),
                'nodeGroups': len(group.get('NodeGroups', [])),
                'primaryEndpoint': group.get('NodeGroups', [{}])[0].get('PrimaryEndpoint', {}).get('Address') if group.get('NodeGroups') else None,
            })
    except Exception:
        pass

    # Cache clusters (Memcached or standalone Redis)
    try:
        response = elasticache.describe_cache_clusters()
        for cluster in response.get('CacheClusters', []):
            # Skip if part of a replication group (already listed above)
            if cluster.get('ReplicationGroupId'):
                continue
            clusters.append({
                'id': cluster['CacheClusterId'],
                'name': cluster['CacheClusterId'],
                'type': 'cache-cluster',
                'engine': cluster.get('Engine'),
                'engineVersion': cluster.get('EngineVersion'),
                'status': cluster.get('CacheClusterStatus'),
                'nodeType': cluster.get('CacheNodeType'),
                'numNodes': cluster.get('NumCacheNodes'),
            })
    except Exception:
        pass

    return sorted(clusters, key=lambda x: x['name'])


def discover_efs_filesystems(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover EFS file systems in the target account.
    """
    efs = get_cross_account_client('efs', role_arn, region)
    response = efs.describe_file_systems()

    filesystems = []
    for fs in response.get('FileSystems', []):
        name = fs.get('Name', fs['FileSystemId'])
        filesystems.append({
            'id': fs['FileSystemId'],
            'name': name,
            'arn': fs.get('FileSystemArn'),
            'lifeCycleState': fs.get('LifeCycleState'),
            'sizeInBytes': fs.get('SizeInBytes', {}).get('Value', 0),
            'performanceMode': fs.get('PerformanceMode'),
            'throughputMode': fs.get('ThroughputMode'),
            'encrypted': fs.get('Encrypted', False),
            'tags': {t['Key']: t['Value'] for t in fs.get('Tags', [])},
        })

    return sorted(filesystems, key=lambda x: x['name'])


def discover_albs(role_arn: str, region: str, tags: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Discover Application Load Balancers in the target account.

    Args:
        role_arn: Role to assume
        region: AWS region
        tags: Optional tag filter (key=value pairs)
    """
    elbv2 = get_cross_account_client('elbv2', role_arn, region)
    response = elbv2.describe_load_balancers()

    albs = []
    lb_arns = []

    for lb in response.get('LoadBalancers', []):
        if lb.get('Type') == 'application':
            lb_arns.append(lb['LoadBalancerArn'])
            albs.append({
                'id': lb['LoadBalancerArn'].split('/')[-1],
                'arn': lb['LoadBalancerArn'],
                'name': lb['LoadBalancerName'],
                'dnsName': lb.get('DNSName'),
                'scheme': lb.get('Scheme'),  # internet-facing or internal
                'state': lb.get('State', {}).get('Code'),
                'vpcId': lb.get('VpcId'),
                'type': lb.get('Type'),
                'tags': {},
            })

    # Fetch tags for all ALBs
    if lb_arns:
        try:
            tag_response = elbv2.describe_tags(ResourceArns=lb_arns)
            for tag_desc in tag_response.get('TagDescriptions', []):
                arn = tag_desc['ResourceArn']
                tag_dict = {t['Key']: t['Value'] for t in tag_desc.get('Tags', [])}
                # Find matching ALB and add tags
                for alb in albs:
                    if alb['arn'] == arn:
                        alb['tags'] = tag_dict
                        break
        except Exception:
            pass

    # Filter by tags if specified
    if tags:
        albs = [
            alb for alb in albs
            if all(alb.get('tags', {}).get(k) == v for k, v in tags.items())
        ]

    return sorted(albs, key=lambda x: x['name'])


def discover_security_groups(role_arn: str, region: str, vpc_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Discover Security Groups in the target account.

    Args:
        role_arn: Role to assume
        region: AWS region
        vpc_id: Optional VPC ID filter
    """
    ec2 = get_cross_account_client('ec2', role_arn, region)

    filters = []
    if vpc_id:
        filters.append({'Name': 'vpc-id', 'Values': [vpc_id]})

    response = ec2.describe_security_groups(Filters=filters) if filters else ec2.describe_security_groups()

    sgs = []
    for sg in response.get('SecurityGroups', []):
        sgs.append({
            'id': sg['GroupId'],
            'name': sg.get('GroupName'),
            'description': sg.get('Description'),
            'vpcId': sg.get('VpcId'),
            'inboundRulesCount': len(sg.get('IpPermissions', [])),
            'outboundRulesCount': len(sg.get('IpPermissionsEgress', [])),
            'tags': {t['Key']: t['Value'] for t in sg.get('Tags', [])},
        })

    return sorted(sgs, key=lambda x: x['name'] or x['id'])


def discover_s3_buckets(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover S3 buckets in the target account.

    Note: S3 ListBuckets is global, but we filter by region.
    """
    s3 = get_cross_account_client('s3', role_arn, region)
    response = s3.list_buckets()

    buckets = []
    for bucket in response.get('Buckets', []):
        bucket_name = bucket['Name']
        try:
            # Get bucket location to filter by region
            location_response = s3.get_bucket_location(Bucket=bucket_name)
            bucket_region = location_response.get('LocationConstraint') or 'us-east-1'

            # Only include buckets in the specified region
            if bucket_region == region:
                buckets.append({
                    'id': bucket_name,
                    'name': bucket_name,
                    'region': bucket_region,
                    'createdAt': bucket.get('CreationDate').isoformat() if bucket.get('CreationDate') else None,
                })
        except Exception:
            # Skip buckets we can't access
            pass

    return sorted(buckets, key=lambda x: x['name'])


def discover_cloudfront_distributions(role_arn: str, region: str) -> List[Dict[str, Any]]:
    """
    Discover CloudFront distributions in the target account.

    Note: CloudFront is global; region is ignored.
    """
    cloudfront = get_cross_account_client('cloudfront', role_arn, 'us-east-1')
    response = cloudfront.list_distributions()

    distributions = []
    for dist in response.get('DistributionList', {}).get('Items', []):
        distributions.append({
            'id': dist.get('Id'),
            'domainName': dist.get('DomainName'),
            'status': dist.get('Status'),
            'enabled': dist.get('Enabled', False),
            'aliases': dist.get('Aliases', {}).get('Items', []),
        })

    return sorted(distributions, key=lambda x: x['id'] or '')


# Discovery function registry
DISCOVERY_FUNCTIONS = {
    'vpc': discover_vpcs,
    'route53': discover_route53_zones,
    'eks': discover_eks_clusters,
    'ecs': discover_ecs_clusters,
    'rds': discover_rds_clusters,
    'documentdb': discover_documentdb_clusters,
    'elasticache': discover_elasticache_clusters,
    'efs': discover_efs_filesystems,
    'alb': discover_albs,
    'sg': discover_security_groups,
    's3': discover_s3_buckets,
    'cloudfront': discover_cloudfront_distributions,
}
