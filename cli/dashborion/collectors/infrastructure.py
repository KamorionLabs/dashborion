"""Infrastructure collector for Dashborion CLI"""

from typing import Dict, List, Optional, Any


class InfrastructureCollector:
    """Collect AWS infrastructure data (ALB, RDS, ElastiCache, CloudFront, VPC)"""

    def __init__(self, session):
        self.session = session
        self.region = session.region_name

    def get_load_balancers(self, name_filter: Optional[str] = None,
                           tags: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Get Application Load Balancers"""
        albs = []

        try:
            elbv2 = self.session.client('elbv2')

            paginator = elbv2.get_paginator('describe_load_balancers')

            for page in paginator.paginate():
                for lb in page.get('LoadBalancers', []):
                    if lb.get('Type') != 'application':
                        continue

                    if name_filter and name_filter not in lb.get('LoadBalancerName', ''):
                        continue

                    # Get target groups
                    tg_response = elbv2.describe_target_groups(LoadBalancerArn=lb['LoadBalancerArn'])
                    target_groups = []

                    for tg in tg_response.get('TargetGroups', []):
                        # Get target health
                        health_response = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])
                        healthy = sum(1 for t in health_response.get('TargetHealthDescriptions', [])
                                      if t.get('TargetHealth', {}).get('State') == 'healthy')
                        total = len(health_response.get('TargetHealthDescriptions', []))

                        target_groups.append({
                            'name': tg.get('TargetGroupName'),
                            'arn': tg.get('TargetGroupArn'),
                            'protocol': tg.get('Protocol'),
                            'port': tg.get('Port'),
                            'healthCheckPath': tg.get('HealthCheckPath'),
                            'health': {
                                'healthy': healthy,
                                'total': total,
                                'status': 'healthy' if healthy == total and total > 0 else 'unhealthy'
                            }
                        })

                    albs.append({
                        'name': lb.get('LoadBalancerName'),
                        'arn': lb.get('LoadBalancerArn'),
                        'dnsName': lb.get('DNSName'),
                        'scheme': lb.get('Scheme'),
                        'state': lb.get('State', {}).get('Code'),
                        'type': lb.get('Type'),
                        'securityGroups': lb.get('SecurityGroups', []),
                        'targetGroups': target_groups,
                    })

        except Exception as e:
            return [{'error': str(e)}]

        return albs

    def get_databases(self, identifier_filter: Optional[str] = None,
                      tags: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Get RDS databases"""
        databases = []

        try:
            rds = self.session.client('rds')

            paginator = rds.get_paginator('describe_db_instances')

            for page in paginator.paginate():
                for db in page.get('DBInstances', []):
                    if identifier_filter and identifier_filter not in db.get('DBInstanceIdentifier', ''):
                        continue

                    databases.append({
                        'identifier': db.get('DBInstanceIdentifier'),
                        'engine': db.get('Engine'),
                        'engineVersion': db.get('EngineVersion'),
                        'instanceClass': db.get('DBInstanceClass'),
                        'status': db.get('DBInstanceStatus'),
                        'endpoint': db.get('Endpoint', {}).get('Address'),
                        'port': db.get('Endpoint', {}).get('Port'),
                        'multiAZ': db.get('MultiAZ'),
                        'storageType': db.get('StorageType'),
                        'allocatedStorage': db.get('AllocatedStorage'),
                        'availabilityZone': db.get('AvailabilityZone'),
                        'encrypted': db.get('StorageEncrypted'),
                    })

        except Exception as e:
            return [{'error': str(e)}]

        return databases

    def get_caches(self, tags: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Get ElastiCache clusters"""
        caches = []

        try:
            elasticache = self.session.client('elasticache')

            paginator = elasticache.get_paginator('describe_cache_clusters')

            for page in paginator.paginate(ShowCacheNodeInfo=True):
                for cluster in page.get('CacheClusters', []):
                    nodes = cluster.get('CacheNodes', [])
                    endpoint = nodes[0].get('Endpoint', {}) if nodes else {}

                    caches.append({
                        'clusterId': cluster.get('CacheClusterId'),
                        'engine': cluster.get('Engine'),
                        'engineVersion': cluster.get('EngineVersion'),
                        'cacheNodeType': cluster.get('CacheNodeType'),
                        'status': cluster.get('CacheClusterStatus'),
                        'numNodes': cluster.get('NumCacheNodes'),
                        'endpoint': {
                            'address': endpoint.get('Address'),
                            'port': endpoint.get('Port'),
                        },
                        'preferredAvailabilityZone': cluster.get('PreferredAvailabilityZone'),
                    })

        except Exception as e:
            return [{'error': str(e)}]

        return caches

    def get_cloudfront_distributions(self, distribution_id: Optional[str] = None,
                                     tags: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Get CloudFront distributions"""
        distributions = []

        try:
            cloudfront = self.session.client('cloudfront')

            paginator = cloudfront.get_paginator('list_distributions')

            for page in paginator.paginate():
                for dist in page.get('DistributionList', {}).get('Items', []):
                    if distribution_id and dist.get('Id') != distribution_id:
                        continue

                    # Get origins
                    origins = []
                    for origin in dist.get('Origins', {}).get('Items', []):
                        origin_type = 'custom'
                        if origin.get('S3OriginConfig'):
                            origin_type = 's3'
                        elif 'elb' in origin.get('DomainName', '').lower():
                            origin_type = 'alb'

                        origins.append({
                            'id': origin.get('Id'),
                            'domainName': origin.get('DomainName'),
                            'type': origin_type,
                            'path': origin.get('OriginPath'),
                        })

                    distributions.append({
                        'id': dist.get('Id'),
                        'domainName': dist.get('DomainName'),
                        'status': dist.get('Status'),
                        'enabled': dist.get('Enabled'),
                        'aliases': dist.get('Aliases', {}).get('Items', []),
                        'origins': origins,
                        'webAclId': dist.get('WebACLId'),
                    })

        except Exception as e:
            return [{'error': str(e)}]

        return distributions

    def get_vpcs(self, tags: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Get VPCs"""
        vpcs = []

        try:
            ec2 = self.session.client('ec2')

            response = ec2.describe_vpcs()

            for vpc in response.get('Vpcs', []):
                vpc_id = vpc.get('VpcId')

                # Get subnets
                subnets_response = ec2.describe_subnets(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )

                subnets = []
                for subnet in subnets_response.get('Subnets', []):
                    subnets.append({
                        'id': subnet.get('SubnetId'),
                        'cidr': subnet.get('CidrBlock'),
                        'az': subnet.get('AvailabilityZone'),
                        'public': subnet.get('MapPublicIpOnLaunch', False),
                    })

                # Get name tag
                name = None
                for tag in vpc.get('Tags', []):
                    if tag.get('Key') == 'Name':
                        name = tag.get('Value')
                        break

                vpcs.append({
                    'id': vpc_id,
                    'name': name,
                    'cidr': vpc.get('CidrBlock'),
                    'state': vpc.get('State'),
                    'isDefault': vpc.get('IsDefault'),
                    'subnets': subnets,
                })

        except Exception as e:
            return [{'error': str(e)}]

        return vpcs

    def get_network_topology(self, tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Get full network topology"""
        return {
            'vpcs': self.get_vpcs(tags),
            'loadBalancers': self.get_load_balancers(tags=tags),
        }

    def get_security_groups(self, sg_id: Optional[str] = None,
                            tags: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Get security groups with rules"""
        security_groups = []

        try:
            ec2 = self.session.client('ec2')

            kwargs = {}
            if sg_id:
                kwargs['GroupIds'] = [sg_id]

            response = ec2.describe_security_groups(**kwargs)

            for sg in response.get('SecurityGroups', []):
                inbound_rules = []
                for rule in sg.get('IpPermissions', []):
                    for ip_range in rule.get('IpRanges', []):
                        inbound_rules.append({
                            'protocol': rule.get('IpProtocol'),
                            'fromPort': rule.get('FromPort'),
                            'toPort': rule.get('ToPort'),
                            'source': ip_range.get('CidrIp'),
                            'description': ip_range.get('Description'),
                        })
                    for sg_ref in rule.get('UserIdGroupPairs', []):
                        inbound_rules.append({
                            'protocol': rule.get('IpProtocol'),
                            'fromPort': rule.get('FromPort'),
                            'toPort': rule.get('ToPort'),
                            'source': sg_ref.get('GroupId'),
                            'description': sg_ref.get('Description'),
                        })

                outbound_rules = []
                for rule in sg.get('IpPermissionsEgress', []):
                    for ip_range in rule.get('IpRanges', []):
                        outbound_rules.append({
                            'protocol': rule.get('IpProtocol'),
                            'fromPort': rule.get('FromPort'),
                            'toPort': rule.get('ToPort'),
                            'destination': ip_range.get('CidrIp'),
                            'description': ip_range.get('Description'),
                        })

                security_groups.append({
                    'id': sg.get('GroupId'),
                    'name': sg.get('GroupName'),
                    'description': sg.get('Description'),
                    'vpcId': sg.get('VpcId'),
                    'inboundRules': inbound_rules,
                    'outboundRules': outbound_rules,
                })

        except Exception as e:
            return [{'error': str(e)}]

        return security_groups
