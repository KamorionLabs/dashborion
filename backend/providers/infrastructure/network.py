"""
AWS VPC Network Provider implementation.
"""

from typing import List, Optional

from providers.base import NetworkProvider, ProviderFactory
from config import DashboardConfig
from utils.aws import get_cross_account_client, build_sso_console_url


class VPCProvider(NetworkProvider):
    """
    AWS VPC implementation of the network provider.
    Handles VPC, subnets, NAT gateways, routing, and security.
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

    def _get_ec2_client(self, env: str):
        """Get EC2 client for environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client(
            'ec2', env_config.account_id, env_config.region,
            project=self.project, env=env
        )

    def get_network_info(self, env: str) -> dict:
        """Get VPC and basic network info (subnets, NAT gateways, connectivity summary)"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.account_id
        ec2 = self._get_ec2_client(env)

        vpc_name = f"{self.project}-{env}"

        vpcs = ec2.describe_vpcs(
            Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}]
        )

        if not vpcs.get('Vpcs'):
            return None

        vpc = vpcs['Vpcs'][0]
        vpc_id = vpc['VpcId']

        # Get subnets
        subnets_response = ec2.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )

        subnets_by_az = {}
        for subnet in subnets_response.get('Subnets', []):
            az = subnet['AvailabilityZone']
            subnet_name = ''
            subnet_type = 'unknown'
            for tag in subnet.get('Tags', []):
                if tag['Key'] == 'Name':
                    subnet_name = tag['Value']
                elif tag['Key'] == 'Type':
                    subnet_type = tag['Value'].lower()
            if subnet_type == 'unknown' and subnet_name:
                if 'private' in subnet_name.lower():
                    subnet_type = 'private'
                elif 'public' in subnet_name.lower():
                    subnet_type = 'public'

            if az not in subnets_by_az:
                subnets_by_az[az] = []
            subnets_by_az[az].append({
                'id': subnet['SubnetId'],
                'name': subnet_name,
                'type': subnet_type,
                'cidr': subnet['CidrBlock'],
                'availableIps': subnet['AvailableIpAddressCount']
            })

        # NAT Gateways
        nat_gateways = ec2.describe_nat_gateways(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}, {'Name': 'state', 'Values': ['available']}]
        )

        nat_info = []
        for nat in nat_gateways.get('NatGateways', []):
            # Extract public IP from NatGatewayAddresses
            public_ip = None
            for addr in nat.get('NatGatewayAddresses', []):
                if addr.get('PublicIp'):
                    public_ip = addr['PublicIp']
                    break

            # Extract name from tags
            nat_name = ''
            for tag in nat.get('Tags', []):
                if tag['Key'] == 'Name':
                    nat_name = tag['Value']
                    break

            nat_info.append({
                'id': nat['NatGatewayId'],
                'name': nat_name,
                'publicIp': public_ip,
                'subnetId': nat['SubnetId'],
                'state': nat['State'],
                'type': nat.get('ConnectivityType', 'public'),
                'az': nat.get('SubnetId'),
                'consoleUrl': build_sso_console_url(
                    self.config.sso_portal_url, account_id,
                    f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#NatGatewayDetails:natGatewayId={nat['NatGatewayId']}"
                )
            })

        # Get connectivity summary (lightweight - just counts)
        connectivity_summary = self._get_connectivity_summary(ec2, vpc_id)

        return {
            'vpcId': vpc_id,
            'vpcName': vpc_name,
            'cidr': vpc['CidrBlock'],
            'availabilityZones': list(subnets_by_az.keys()),
            'subnetsByAz': subnets_by_az,
            'natGateways': nat_info,
            'egressIps': [nat['publicIp'] for nat in nat_info if nat.get('publicIp')],
            'connectivity': connectivity_summary,
            'consoleUrl': build_sso_console_url(
                self.config.sso_portal_url, account_id,
                f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#VpcDetails:VpcId={vpc_id}"
            )
        }

    def _get_connectivity_summary(self, ec2, vpc_id: str) -> dict:
        """Get lightweight connectivity summary (counts only, for main view)"""
        try:
            # Count VPC Peerings
            peerings = ec2.describe_vpc_peering_connections(
                Filters=[
                    {'Name': 'status-code', 'Values': ['active']},
                ]
            )
            # Filter for peerings involving this VPC
            vpc_peerings = [p for p in peerings.get('VpcPeeringConnections', [])
                          if p.get('AccepterVpcInfo', {}).get('VpcId') == vpc_id
                          or p.get('RequesterVpcInfo', {}).get('VpcId') == vpc_id]

            # Count VPN Connections
            vpn_connections = []
            try:
                vpn_gateways = ec2.describe_vpn_gateways(
                    Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]},
                             {'Name': 'state', 'Values': ['available']}]
                )
                if vpn_gateways.get('VpnGateways'):
                    vpn_conns = ec2.describe_vpn_connections(
                        Filters=[{'Name': 'state', 'Values': ['available']}]
                    )
                    vpn_connections = [v for v in vpn_conns.get('VpnConnections', [])
                                      if v.get('VpnGatewayId') in [vg['VpnGatewayId'] for vg in vpn_gateways['VpnGateways']]]
            except Exception:
                pass

            # Count Transit Gateway Attachments
            tgw_attachments = []
            try:
                tgw_response = ec2.describe_transit_gateway_vpc_attachments(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]},
                             {'Name': 'state', 'Values': ['available']}]
                )
                tgw_attachments = tgw_response.get('TransitGatewayVpcAttachments', [])
            except Exception:
                pass

            # Check Internet Gateway
            igw_response = ec2.describe_internet_gateways(
                Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
            )
            has_igw = len(igw_response.get('InternetGateways', [])) > 0

            return {
                'hasInternetGateway': has_igw,
                'vpcPeeringCount': len(vpc_peerings),
                'vpnConnectionCount': len(vpn_connections),
                'transitGatewayCount': len(tgw_attachments)
            }
        except Exception as e:
            return {'error': str(e)}

    def get_enis(self, env: str, vpc_id: str = None, subnet_id: str = None, search_ip: str = None) -> dict:
        """
        Get ENIs (Elastic Network Interfaces) for a VPC or subnet.
        Supports filtering by subnet and searching by IP address.
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.account_id
        ec2 = self._get_ec2_client(env)

        try:
            # Get VPC ID if not provided
            if not vpc_id:
                vpc_name = f"{self.project}-{env}"
                vpcs = ec2.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}])
                if not vpcs.get('Vpcs'):
                    return {'error': f'VPC {vpc_name} not found'}
                vpc_id = vpcs['Vpcs'][0]['VpcId']

            # Build filters
            filters = [{'Name': 'vpc-id', 'Values': [vpc_id]}]
            if subnet_id:
                filters.append({'Name': 'subnet-id', 'Values': [subnet_id]})

            # Fetch ENIs
            enis_response = ec2.describe_network_interfaces(Filters=filters)

            enis = []
            for eni in enis_response.get('NetworkInterfaces', []):
                # Extract primary private IP
                private_ip = eni.get('PrivateIpAddress', '')

                # Get all private IPs
                private_ips = [addr.get('PrivateIpAddress') for addr in eni.get('PrivateIpAddresses', [])]

                # Search filter by IP
                if search_ip:
                    match = any(search_ip in ip for ip in private_ips if ip)
                    if not match:
                        continue

                # Determine attachment type and details
                attachment = eni.get('Attachment', {})
                attachment_info = self._parse_eni_attachment(eni, attachment)

                # Extract name from tags
                eni_name = ''
                for tag in eni.get('TagSet', []):
                    if tag['Key'] == 'Name':
                        eni_name = tag['Value']
                        break

                # Get description (often contains attachment info)
                description = eni.get('Description', '')

                enis.append({
                    'id': eni['NetworkInterfaceId'],
                    'name': eni_name,
                    'description': description,
                    'privateIp': private_ip,
                    'privateIps': private_ips,
                    'publicIp': eni.get('Association', {}).get('PublicIp'),
                    'subnetId': eni.get('SubnetId'),
                    'az': eni.get('AvailabilityZone'),
                    'status': eni.get('Status'),
                    'type': eni.get('InterfaceType', 'interface'),
                    'attachment': attachment_info,
                    'securityGroups': [
                        {'id': sg['GroupId'], 'name': sg['GroupName']}
                        for sg in eni.get('Groups', [])
                    ],
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/ec2/v2/home?region={self.region}#NetworkInterface:networkInterfaceId={eni['NetworkInterfaceId']}"
                    )
                })

            # Sort by private IP for easier browsing
            enis.sort(key=lambda x: x.get('privateIp', ''))

            return {
                'vpcId': vpc_id,
                'subnetId': subnet_id,
                'searchIp': search_ip,
                'count': len(enis),
                'enis': enis
            }

        except Exception as e:
            return {'error': str(e)}

    def _parse_eni_attachment(self, eni: dict, attachment: dict) -> dict:
        """Parse ENI attachment to determine what it's attached to"""
        description = eni.get('Description', '')
        interface_type = eni.get('InterfaceType', 'interface')
        requester_id = eni.get('RequesterId', '')

        result = {
            'type': 'unknown',
            'instanceId': attachment.get('InstanceId'),
            'status': attachment.get('Status'),
            'deleteOnTermination': attachment.get('DeleteOnTermination', False)
        }

        # ECS Task - detect by ARN pattern "arn:aws:ecs:...:attachment/..."
        if 'arn:aws:ecs:' in description and ':attachment/' in description:
            result['type'] = 'ecs-task'
            # Extract attachment ID from ARN
            if ':attachment/' in description:
                result['attachmentId'] = description.split(':attachment/')[-1]

        # ECS Task - older format or interface_type based
        elif 'ECS' in description or interface_type == 'ecs':
            result['type'] = 'ecs-task'
            if 'ecs:task' in description.lower():
                parts = description.split('/')
                if len(parts) >= 2:
                    result['cluster'] = parts[-2] if len(parts) >= 2 else None
                    result['taskId'] = parts[-1] if parts else None

        # CloudFront managed ENI
        elif interface_type == 'cloudfront_managed' or 'CloudFront' in description:
            result['type'] = 'cloudfront'

        # Lambda
        elif 'Lambda' in description or 'AWS Lambda' in requester_id:
            result['type'] = 'lambda'
            # Extract function name if possible
            if ':function:' in description:
                try:
                    result['functionName'] = description.split(':function:')[1].split(':')[0]
                except IndexError:
                    pass

        # RDS
        elif 'RDSNetworkInterface' in description or 'rds' in requester_id.lower():
            result['type'] = 'rds'

        # ElastiCache
        elif 'ElastiCache' in description or 'elasticache' in requester_id.lower():
            result['type'] = 'elasticache'

        # NAT Gateway
        elif interface_type == 'nat_gateway' or 'NAT Gateway' in description:
            result['type'] = 'nat-gateway'

        # VPC Endpoint
        elif interface_type == 'vpc_endpoint' or 'VPC Endpoint' in description:
            result['type'] = 'vpc-endpoint'

        # ALB/NLB
        elif 'ELB' in description or 'elb' in requester_id.lower():
            result['type'] = 'load-balancer'
            if 'app/' in description:
                result['loadBalancerType'] = 'application'
            elif 'net/' in description:
                result['loadBalancerType'] = 'network'

        # EC2 Instance
        elif attachment.get('InstanceId'):
            result['type'] = 'ec2-instance'

        # Gateway Load Balancer Endpoint
        elif interface_type == 'gateway_load_balancer_endpoint':
            result['type'] = 'gwlb-endpoint'

        # Interface VPC Endpoint
        elif interface_type == 'interface':
            # Check if it's a VPC Endpoint by description
            if 'vpce-' in description.lower():
                result['type'] = 'vpc-endpoint'

        return result

    def get_routing_details(self, env: str, service_security_groups: List[str] = None) -> dict:
        """Get detailed routing and security information (called on demand via toggle)"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.account_id
        ec2 = self._get_ec2_client(env)

        # Get VPC ID
        vpc_name = f"{self.project}-{env}"
        vpcs = ec2.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}])
        if not vpcs.get('Vpcs'):
            return {'error': f'VPC {vpc_name} not found'}

        vpc_id = vpcs['Vpcs'][0]['VpcId']

        result = {
            'vpcId': vpc_id,
            'routing': {},
            'connectivity': {},
            'security': {}
        }

        # ===== ROUTING =====
        try:
            # Get Internet Gateway
            igw_response = ec2.describe_internet_gateways(
                Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
            )
            if igw_response.get('InternetGateways'):
                igw = igw_response['InternetGateways'][0]
                igw_name = next((t['Value'] for t in igw.get('Tags', []) if t['Key'] == 'Name'), '')
                result['routing']['internetGateway'] = {
                    'id': igw['InternetGatewayId'],
                    'name': igw_name,
                    'state': 'attached',
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#InternetGateway:internetGatewayId={igw['InternetGatewayId']}"
                    )
                }

            # Get Route Tables
            rt_response = ec2.describe_route_tables(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            route_tables = []
            for rt in rt_response.get('RouteTables', []):
                rt_name = next((t['Value'] for t in rt.get('Tags', []) if t['Key'] == 'Name'), '')

                # Get subnet associations
                subnet_associations = [a['SubnetId'] for a in rt.get('Associations', []) if a.get('SubnetId')]
                is_main = any(a.get('Main', False) for a in rt.get('Associations', []))

                # Parse routes
                routes = []
                default_route = None
                for route in rt.get('Routes', []):
                    dest = route.get('DestinationCidrBlock') or route.get('DestinationPrefixListId', '')

                    # Determine target type and ID
                    target_id = None
                    target_type = None
                    if route.get('GatewayId'):
                        target_id = route['GatewayId']
                        if target_id.startswith('igw-'):
                            target_type = 'internet-gateway'
                        elif target_id == 'local':
                            target_type = 'local'
                        else:
                            target_type = 'gateway'
                    elif route.get('NatGatewayId'):
                        target_id = route['NatGatewayId']
                        target_type = 'nat-gateway'
                    elif route.get('TransitGatewayId'):
                        target_id = route['TransitGatewayId']
                        target_type = 'transit-gateway'
                    elif route.get('VpcPeeringConnectionId'):
                        target_id = route['VpcPeeringConnectionId']
                        target_type = 'vpc-peering'
                    elif route.get('NetworkInterfaceId'):
                        target_id = route['NetworkInterfaceId']
                        target_type = 'network-interface'
                    elif route.get('InstanceId'):
                        target_id = route['InstanceId']
                        target_type = 'instance'

                    route_info = {
                        'destination': dest,
                        'targetId': target_id,
                        'targetType': target_type,
                        'state': route.get('State', 'unknown')
                    }
                    routes.append(route_info)

                    # Track default route (0.0.0.0/0)
                    if dest == '0.0.0.0/0' and route.get('State') == 'active':
                        default_route = route_info

                route_tables.append({
                    'id': rt['RouteTableId'],
                    'name': rt_name,
                    'isMain': is_main,
                    'subnetAssociations': subnet_associations,
                    'routes': routes,
                    'defaultRoute': default_route,
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#RouteTableDetails:routeTableId={rt['RouteTableId']}"
                    )
                })

            result['routing']['routeTables'] = route_tables

            # Get VPC Endpoints
            endpoints_response = ec2.describe_vpc_endpoints(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            vpc_endpoints = []
            for ep in endpoints_response.get('VpcEndpoints', []):
                ep_name = next((t['Value'] for t in ep.get('Tags', []) if t['Key'] == 'Name'), '')
                service_name = ep.get('ServiceName', '')

                # Extract friendly service name from full service name
                # e.g., com.amazonaws.eu-west-3.s3 -> S3
                # e.g., com.amazonaws.eu-west-3.ecr.api -> ECR API
                # e.g., com.amazonaws.eu-west-3.ecr.dkr -> ECR DKR
                # e.g., com.amazonaws.vpce.eu-west-3.vpce-svc-xxx -> PrivateLink
                friendly_service = service_name
                if service_name:
                    parts = service_name.split('.')
                    if len(parts) >= 4:
                        if parts[0] == 'com' and parts[1] == 'amazonaws':
                            if parts[2] == 'vpce':
                                friendly_service = 'PrivateLink'
                            else:
                                # e.g., ['com', 'amazonaws', 'eu-west-3', 's3'] -> 'S3'
                                # e.g., ['com', 'amazonaws', 'eu-west-3', 'ecr', 'api'] -> 'ECR API'
                                svc_parts = parts[3:]  # Everything after region
                                friendly_service = ' '.join(p.upper() for p in svc_parts)

                vpc_endpoints.append({
                    'id': ep['VpcEndpointId'],
                    'name': ep_name,
                    'serviceName': service_name,
                    'friendlyServiceName': friendly_service,
                    'type': ep.get('VpcEndpointType', 'Unknown'),  # Gateway or Interface
                    'state': ep.get('State', 'unknown'),
                    'subnetIds': ep.get('SubnetIds', []),
                    'routeTableIds': ep.get('RouteTableIds', []),
                    'securityGroupIds': [sg['GroupId'] for sg in ep.get('Groups', [])],
                    'privateDnsEnabled': ep.get('PrivateDnsEnabled', False),
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#EndpointDetails:vpcEndpointId={ep['VpcEndpointId']}"
                    )
                })

            result['routing']['vpcEndpoints'] = vpc_endpoints

        except Exception as e:
            result['routing']['error'] = str(e)

        # ===== CONNECTIVITY (VPC Peering, VPN, TGW) =====
        try:
            # VPC Peering Connections
            peerings = ec2.describe_vpc_peering_connections(
                Filters=[{'Name': 'status-code', 'Values': ['active']}]
            )
            vpc_peerings = []
            for p in peerings.get('VpcPeeringConnections', []):
                accepter = p.get('AccepterVpcInfo', {})
                requester = p.get('RequesterVpcInfo', {})

                # Check if this VPC is involved
                if accepter.get('VpcId') != vpc_id and requester.get('VpcId') != vpc_id:
                    continue

                # Determine peer VPC info
                peer_vpc = accepter if requester.get('VpcId') == vpc_id else requester
                p_name = next((t['Value'] for t in p.get('Tags', []) if t['Key'] == 'Name'), '')

                vpc_peerings.append({
                    'id': p['VpcPeeringConnectionId'],
                    'name': p_name,
                    'status': p['Status']['Code'],
                    'peerVpc': {
                        'vpcId': peer_vpc.get('VpcId'),
                        'cidr': peer_vpc.get('CidrBlock'),
                        'accountId': peer_vpc.get('OwnerId'),
                        'region': peer_vpc.get('Region', self.region)
                    },
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#PeeringConnectionDetails:vpcPeeringConnectionId={p['VpcPeeringConnectionId']}"
                    )
                })

            result['connectivity']['vpcPeerings'] = vpc_peerings

            # VPN Connections
            vpn_connections = []
            try:
                vpn_gateways = ec2.describe_vpn_gateways(
                    Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]},
                             {'Name': 'state', 'Values': ['available']}]
                )
                if vpn_gateways.get('VpnGateways'):
                    vgw_ids = [vg['VpnGatewayId'] for vg in vpn_gateways['VpnGateways']]
                    vpn_conns = ec2.describe_vpn_connections(
                        Filters=[{'Name': 'state', 'Values': ['available']}]
                    )
                    for vpn in vpn_conns.get('VpnConnections', []):
                        if vpn.get('VpnGatewayId') not in vgw_ids:
                            continue

                        vpn_name = next((t['Value'] for t in vpn.get('Tags', []) if t['Key'] == 'Name'), '')
                        tunnels = []
                        for tun in vpn.get('VgwTelemetry', []):
                            tunnels.append({
                                'status': tun.get('Status'),
                                'statusMessage': tun.get('StatusMessage'),
                                'outsideIpAddress': tun.get('OutsideIpAddress'),
                                'lastStatusChange': tun.get('LastStatusChange').isoformat() if tun.get('LastStatusChange') else None
                            })

                        vpn_connections.append({
                            'id': vpn['VpnConnectionId'],
                            'name': vpn_name,
                            'state': vpn['State'],
                            'vpnGatewayId': vpn['VpnGatewayId'],
                            'customerGatewayId': vpn.get('CustomerGatewayId'),
                            'tunnels': tunnels,
                            'consoleUrl': build_sso_console_url(
                                self.config.sso_portal_url, account_id,
                                f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#VpnConnectionDetails:vpnConnectionId={vpn['VpnConnectionId']}"
                            )
                        })
            except Exception:
                pass

            result['connectivity']['vpnConnections'] = vpn_connections

            # Transit Gateway Attachments
            tgw_attachments = []
            try:
                tgw_response = ec2.describe_transit_gateway_vpc_attachments(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]},
                             {'Name': 'state', 'Values': ['available', 'pending']}]
                )
                for att in tgw_response.get('TransitGatewayVpcAttachments', []):
                    att_name = next((t['Value'] for t in att.get('Tags', []) if t['Key'] == 'Name'), '')
                    tgw_attachments.append({
                        'id': att['TransitGatewayAttachmentId'],
                        'name': att_name,
                        'transitGatewayId': att['TransitGatewayId'],
                        'transitGatewayOwnerId': att.get('TransitGatewayOwnerId'),
                        'state': att['State'],
                        'subnetIds': att.get('SubnetIds', []),
                        'consoleUrl': build_sso_console_url(
                            self.config.sso_portal_url, account_id,
                            f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#TransitGatewayAttachmentDetails:transitGatewayAttachmentId={att['TransitGatewayAttachmentId']}"
                        )
                    })
            except Exception:
                pass

            result['connectivity']['transitGatewayAttachments'] = tgw_attachments

        except Exception as e:
            result['connectivity']['error'] = str(e)

        # ===== SECURITY (Security Groups & NACLs) =====
        try:
            # Get Security Groups - only those associated with services if provided
            sg_filter = [{'Name': 'vpc-id', 'Values': [vpc_id]}]
            if service_security_groups:
                sg_filter.append({'Name': 'group-id', 'Values': service_security_groups})

            sg_response = ec2.describe_security_groups(Filters=sg_filter)
            security_groups = []

            for sg in sg_response.get('SecurityGroups', []):
                # Parse inbound rules
                inbound_rules = []
                for rule in sg.get('IpPermissions', []):
                    protocol = rule.get('IpProtocol', '-1')
                    from_port = rule.get('FromPort', 'All')
                    to_port = rule.get('ToPort', 'All')

                    # Get sources (CIDR or Security Group)
                    sources = []
                    for ip_range in rule.get('IpRanges', []):
                        sources.append({
                            'type': 'cidr',
                            'value': ip_range.get('CidrIp'),
                            'description': ip_range.get('Description', '')
                        })
                    for sg_ref in rule.get('UserIdGroupPairs', []):
                        sources.append({
                            'type': 'security-group',
                            'value': sg_ref.get('GroupId'),
                            'description': sg_ref.get('Description', '')
                        })
                    for pl in rule.get('PrefixListIds', []):
                        sources.append({
                            'type': 'prefix-list',
                            'value': pl.get('PrefixListId'),
                            'description': pl.get('Description', '')
                        })

                    inbound_rules.append({
                        'protocol': protocol,
                        'fromPort': from_port,
                        'toPort': to_port,
                        'sources': sources
                    })

                # Parse outbound rules
                outbound_rules = []
                for rule in sg.get('IpPermissionsEgress', []):
                    protocol = rule.get('IpProtocol', '-1')
                    from_port = rule.get('FromPort', 'All')
                    to_port = rule.get('ToPort', 'All')

                    destinations = []
                    for ip_range in rule.get('IpRanges', []):
                        destinations.append({
                            'type': 'cidr',
                            'value': ip_range.get('CidrIp'),
                            'description': ip_range.get('Description', '')
                        })
                    for sg_ref in rule.get('UserIdGroupPairs', []):
                        destinations.append({
                            'type': 'security-group',
                            'value': sg_ref.get('GroupId'),
                            'description': sg_ref.get('Description', '')
                        })

                    outbound_rules.append({
                        'protocol': protocol,
                        'fromPort': from_port,
                        'toPort': to_port,
                        'destinations': destinations
                    })

                security_groups.append({
                    'id': sg['GroupId'],
                    'name': sg['GroupName'],
                    'description': sg.get('Description', ''),
                    'inboundRules': inbound_rules,
                    'outboundRules': outbound_rules,
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#SecurityGroup:groupId={sg['GroupId']}"
                    )
                })

            result['security']['securityGroups'] = security_groups

            # Get NACLs
            nacl_response = ec2.describe_network_acls(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            nacls = []
            for nacl in nacl_response.get('NetworkAcls', []):
                nacl_name = next((t['Value'] for t in nacl.get('Tags', []) if t['Key'] == 'Name'), '')

                # Get subnet associations
                subnet_associations = [a['SubnetId'] for a in nacl.get('Associations', []) if a.get('SubnetId')]

                # Parse rules
                inbound_rules = []
                outbound_rules = []
                for entry in nacl.get('Entries', []):
                    rule_info = {
                        'ruleNumber': entry['RuleNumber'],
                        'protocol': entry['Protocol'],
                        'action': entry['RuleAction'],
                        'cidr': entry.get('CidrBlock', entry.get('Ipv6CidrBlock', '')),
                        'portRange': f"{entry.get('PortRange', {}).get('From', 'All')}-{entry.get('PortRange', {}).get('To', 'All')}" if entry.get('PortRange') else 'All'
                    }
                    if entry['Egress']:
                        outbound_rules.append(rule_info)
                    else:
                        inbound_rules.append(rule_info)

                nacls.append({
                    'id': nacl['NetworkAclId'],
                    'name': nacl_name,
                    'isDefault': nacl.get('IsDefault', False),
                    'subnetAssociations': subnet_associations,
                    'inboundRules': sorted(inbound_rules, key=lambda x: x['ruleNumber']),
                    'outboundRules': sorted(outbound_rules, key=lambda x: x['ruleNumber']),
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/vpc/home?region={self.region}#NetworkAclDetails:networkAclId={nacl['NetworkAclId']}"
                    )
                })

            result['security']['nacls'] = nacls

        except Exception as e:
            result['security']['error'] = str(e)

        return result

    def get_security_group(self, env: str, sg_id: str) -> dict:
        """Get detailed Security Group information including rules"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.account_id
        ec2 = self._get_ec2_client(env)

        try:
            response = ec2.describe_security_groups(GroupIds=[sg_id])
            if not response.get('SecurityGroups'):
                return {'error': f'Security Group {sg_id} not found'}

            sg = response['SecurityGroups'][0]

            # Get name from tags
            sg_name = sg.get('GroupName', '')
            for tag in sg.get('Tags', []):
                if tag['Key'] == 'Name':
                    sg_name = tag['Value']
                    break

            # Parse inbound rules
            inbound_rules = []
            for rule in sg.get('IpPermissions', []):
                rule_info = self._parse_sg_rule(rule, 'inbound', account_id)
                inbound_rules.extend(rule_info)

            # Parse outbound rules
            outbound_rules = []
            for rule in sg.get('IpPermissionsEgress', []):
                rule_info = self._parse_sg_rule(rule, 'outbound', account_id)
                outbound_rules.extend(rule_info)

            # Collect all referenced SG IDs to resolve their names
            all_rules = inbound_rules + outbound_rules
            sg_ids_to_resolve = set()
            for r in all_rules:
                if r.get('sourceType') == 'security-group' and r.get('sourceSgId'):
                    sg_ids_to_resolve.add(r['sourceSgId'])

            # Batch lookup SG names
            sg_names_map = {}
            if sg_ids_to_resolve:
                try:
                    sg_response = ec2.describe_security_groups(GroupIds=list(sg_ids_to_resolve))
                    for ref_sg in sg_response.get('SecurityGroups', []):
                        ref_sg_id = ref_sg['GroupId']
                        # Get name from tags or use GroupName
                        ref_name = ref_sg.get('GroupName', ref_sg_id)
                        for tag in ref_sg.get('Tags', []):
                            if tag['Key'] == 'Name':
                                ref_name = tag['Value']
                                break
                        sg_names_map[ref_sg_id] = ref_name
                except Exception:
                    pass  # If we can't resolve, just use IDs

            # Enrich rules with SG names
            for r in all_rules:
                if r.get('sourceType') == 'security-group' and r.get('sourceSgId'):
                    sg_ref_id = r['sourceSgId']
                    if sg_ref_id in sg_names_map:
                        r['sourceSgName'] = sg_names_map[sg_ref_id]
                    else:
                        r['sourceSgName'] = sg_ref_id  # Fallback to ID

            return {
                'id': sg['GroupId'],
                'name': sg_name,
                'groupName': sg.get('GroupName'),
                'description': sg.get('Description', ''),
                'vpcId': sg.get('VpcId'),
                'inboundRules': inbound_rules,
                'outboundRules': outbound_rules,
                'consoleUrl': build_sso_console_url(
                    self.config.sso_portal_url, account_id,
                    f"https://{self.region}.console.aws.amazon.com/ec2/v2/home?region={self.region}#SecurityGroup:groupId={sg_id}"
                )
            }

        except Exception as e:
            return {'error': str(e)}

    def _parse_sg_rule(self, rule: dict, direction: str, account_id: str = None) -> list:
        """Parse a security group rule into readable format"""
        results = []

        # Get protocol
        protocol = rule.get('IpProtocol', '-1')
        if protocol == '-1':
            protocol_display = 'All'
        elif protocol == '6':
            protocol_display = 'TCP'
        elif protocol == '17':
            protocol_display = 'UDP'
        elif protocol == '1':
            protocol_display = 'ICMP'
        else:
            protocol_display = protocol.upper()

        # Get port range
        from_port = rule.get('FromPort')
        to_port = rule.get('ToPort')
        if protocol == '-1':
            port_range = 'All'
        elif from_port == to_port:
            port_range = str(from_port) if from_port else 'All'
        else:
            port_range = f"{from_port}-{to_port}"

        # Get sources/destinations (CIDR ranges)
        for ip_range in rule.get('IpRanges', []):
            results.append({
                'direction': direction,
                'protocol': protocol_display,
                'portRange': port_range,
                'source': ip_range.get('CidrIp', ''),
                'description': ip_range.get('Description', '')
            })

        # IPv6 ranges
        for ip_range in rule.get('Ipv6Ranges', []):
            results.append({
                'direction': direction,
                'protocol': protocol_display,
                'portRange': port_range,
                'source': ip_range.get('CidrIpv6', ''),
                'description': ip_range.get('Description', '')
            })

        # Security group references
        for group_pair in rule.get('UserIdGroupPairs', []):
            sg_ref_id = group_pair.get('GroupId', '')
            sg_ref_display = sg_ref_id
            if group_pair.get('UserId') and group_pair.get('UserId') != sg_ref_id.split('-')[0]:
                sg_ref_display = f"{group_pair.get('UserId')}/{sg_ref_id}"

            # Build console URL for referenced SG
            sg_console_url = None
            if sg_ref_id and account_id:
                sg_console_url = build_sso_console_url(
                    self.config.sso_portal_url, account_id,
                    f"https://{self.region}.console.aws.amazon.com/ec2/v2/home?region={self.region}#SecurityGroup:groupId={sg_ref_id}"
                )

            results.append({
                'direction': direction,
                'protocol': protocol_display,
                'portRange': port_range,
                'source': sg_ref_display,
                'sourceSgId': sg_ref_id,
                'sourceSgConsoleUrl': sg_console_url,
                'sourceType': 'security-group',
                'description': group_pair.get('Description', '')
            })

        # Prefix lists
        for prefix in rule.get('PrefixListIds', []):
            results.append({
                'direction': direction,
                'protocol': protocol_display,
                'portRange': port_range,
                'source': prefix.get('PrefixListId', ''),
                'sourceType': 'prefix-list',
                'description': prefix.get('Description', '')
            })

        # If no sources, add empty entry (should not happen normally)
        if not results:
            results.append({
                'direction': direction,
                'protocol': protocol_display,
                'portRange': port_range,
                'source': '',
                'description': ''
            })

        return results


# Register the provider
ProviderFactory.register_network_provider('vpc', VPCProvider)
