"""
AWS Application Load Balancer Provider implementation.

Supports:
- Tag-based discovery (EKS/NewHorizon style)
- Name-based discovery (ECS/legacy style)
- Ingress-based discovery for EKS (AWS Load Balancer Controller)
"""

from typing import List, Optional, Dict
from urllib.parse import quote

from providers.base import LoadBalancerProvider, ProviderFactory
from app_config import DashboardConfig
from utils.aws import get_cross_account_client, build_sso_console_url


class ALBProvider(LoadBalancerProvider):
    """
    AWS Application Load Balancer implementation of the load balancer provider.

    Discovery order:
    1. If discovery_tags provided, find ALB by tags
    2. If ingress_hostnames provided (EKS), find ALB by DNS name from Ingress
    3. Fallback to naming convention: {project}-{env}-alb
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

    def _get_elbv2_client(self, env: str):
        """Get ELBv2 client for environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client(
            'elbv2', env_config.account_id, env_config.region,
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

    def _find_alb_by_tags(self, env: str, discovery_tags: Dict[str, str]) -> Optional[str]:
        """Find ALB ARN by tags using Resource Groups Tagging API"""
        if not discovery_tags:
            return None

        try:
            tagging = self._get_resourcegroupstaggingapi_client(env)

            # Build tag filters
            tag_filters = [{'Key': k, 'Values': [v]} for k, v in discovery_tags.items()]

            response = tagging.get_resources(
                ResourceTypeFilters=['elasticloadbalancing:loadbalancer'],
                TagFilters=tag_filters
            )

            # Return first matching ALB ARN
            for resource in response.get('ResourceTagMappingList', []):
                arn = resource['ResourceARN']
                # Filter for ALBs (application load balancers)
                if '/app/' in arn:
                    return arn

            return None
        except Exception as e:
            print(f"Tag-based ALB discovery failed: {e}")
            return None

    def _find_alb_by_dns(self, env: str, dns_name: str) -> Optional[dict]:
        """Find ALB by DNS name (from Ingress load balancer hostname)"""
        if not dns_name:
            return None

        try:
            elbv2 = self._get_elbv2_client(env)
            albs = elbv2.describe_load_balancers()

            for alb in albs.get('LoadBalancers', []):
                if alb.get('DNSName') == dns_name or dns_name in alb.get('DNSName', ''):
                    return alb

            return None
        except Exception as e:
            print(f"DNS-based ALB discovery failed: {e}")
            return None

    def _find_alb_by_name(self, env: str, name_pattern: str = None) -> Optional[dict]:
        """Find ALB by naming convention"""
        try:
            elbv2 = self._get_elbv2_client(env)
            alb_name = name_pattern or f"{self.project}-{env}-alb"

            albs = elbv2.describe_load_balancers()
            for alb in albs.get('LoadBalancers', []):
                if alb['LoadBalancerName'] == alb_name:
                    return alb

            return None
        except Exception as e:
            print(f"Name-based ALB discovery failed: {e}")
            return None

    def get_load_balancer(self, env: str, services: List[str] = None,
                          discovery_tags: Dict[str, str] = None,
                          ingress_hostname: str = None) -> dict:
        """Get ALB info with target groups filtered by services

        Args:
            env: Environment name
            services: List of service names to filter target groups (e.g., ['backend', 'frontend', 'cms'])
            discovery_tags: Dict of tags to find ALB (e.g., {'rubix_Environment': 'stg'})
            ingress_hostname: DNS hostname from K8s Ingress (for EKS discovery)
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.account_id
        region = env_config.region
        elbv2 = self._get_elbv2_client(env)

        try:
            alb = None
            discovery_method = None

            # 1. Try tag-based discovery first
            if discovery_tags:
                alb_arn = self._find_alb_by_tags(env, discovery_tags)
                if alb_arn:
                    response = elbv2.describe_load_balancers(LoadBalancerArns=[alb_arn])
                    if response.get('LoadBalancers'):
                        alb = response['LoadBalancers'][0]
                        discovery_method = 'tags'

            # 2. Try Ingress hostname discovery (EKS)
            if not alb and ingress_hostname:
                alb = self._find_alb_by_dns(env, ingress_hostname)
                if alb:
                    discovery_method = 'ingress'

            # 3. Fallback to naming convention
            if not alb:
                alb = self._find_alb_by_name(env)
                if alb:
                    discovery_method = 'naming'

            if not alb:
                return None

            alb_arn = alb['LoadBalancerArn']
            alb_info = {
                'name': alb['LoadBalancerName'],
                'arn': alb_arn,
                'dnsName': alb['DNSName'],
                'state': alb['State']['Code'],
                'status': 'active' if alb['State']['Code'] == 'active' else alb['State']['Code'],
                'type': alb['Type'],
                'scheme': alb['Scheme'],
                'securityGroups': alb.get('SecurityGroups', []),
                'vpcId': alb.get('VpcId'),
                'availabilityZones': [az['ZoneName'] for az in alb.get('AvailabilityZones', [])],
                'listeners': [],
                'targetGroups': [],
                'rules': [],
                'discoveryMethod': discovery_method,
                'consoleUrl': build_sso_console_url(
                    self.config.sso_portal_url, account_id,
                    f"https://{region}.console.aws.amazon.com/ec2/home?region={region}#LoadBalancer:loadBalancerArn={quote(alb_arn, safe='')}"
                )
            }

            # Listeners
            listeners = elbv2.describe_listeners(LoadBalancerArn=alb_arn)
            for listener in listeners.get('Listeners', []):
                listener_arn = listener['ListenerArn']
                alb_info['listeners'].append({
                    'arn': listener_arn,
                    'port': listener['Port'],
                    'protocol': listener['Protocol']
                })

                if listener['Port'] == 443:
                    rules = elbv2.describe_rules(ListenerArn=listener_arn)
                    for rule in rules.get('Rules', []):
                        if rule['IsDefault']:
                            continue
                        conditions = []
                        for cond in rule.get('Conditions', []):
                            if cond.get('HostHeaderConfig'):
                                conditions.extend(cond['HostHeaderConfig'].get('Values', []))
                            elif cond.get('PathPatternConfig'):
                                conditions.extend(cond['PathPatternConfig'].get('Values', []))

                        target_group_arn = None
                        for action in rule.get('Actions', []):
                            if action['Type'] == 'forward':
                                target_group_arn = action.get('TargetGroupArn')

                        alb_info['rules'].append({
                            'priority': rule['Priority'],
                            'conditions': conditions,
                            'targetGroupArn': target_group_arn
                        })

            # Target Groups - get all for this ALB
            tgs = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
            services_to_match = services if services else None

            for tg in tgs.get('TargetGroups', []):
                tg_arn = tg['TargetGroupArn']
                tg_name = tg['TargetGroupName']

                # Detect which service this target group belongs to
                service_name = None
                if services_to_match:
                    for svc in services_to_match:
                        if svc in tg_name.lower():
                            service_name = svc
                            break
                    # Skip target groups that don't match any of our services if filtering
                    if service_name is None:
                        continue

                health = elbv2.describe_target_health(TargetGroupArn=tg_arn)
                healthy_count = sum(1 for t in health.get('TargetHealthDescriptions', []) if t['TargetHealth']['State'] == 'healthy')
                unhealthy_count = sum(1 for t in health.get('TargetHealthDescriptions', []) if t['TargetHealth']['State'] == 'unhealthy')
                total = len(health.get('TargetHealthDescriptions', []))

                alb_info['targetGroups'].append({
                    'name': tg_name,
                    'arn': tg_arn,
                    'port': tg['Port'],
                    'protocol': tg['Protocol'],
                    'targetType': tg.get('TargetType', 'instance'),
                    'healthCheckPath': tg.get('HealthCheckPath', '/'),
                    'service': service_name,
                    'health': {
                        'healthy': healthy_count,
                        'unhealthy': unhealthy_count,
                        'total': total,
                        'status': 'healthy' if healthy_count == total and total > 0 else 'unhealthy' if unhealthy_count > 0 else 'unknown'
                    },
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{region}.console.aws.amazon.com/ec2/home?region={region}#TargetGroup:targetGroupArn={quote(tg_arn, safe='')}"
                    )
                })

            return alb_info

        except Exception as e:
            return {'error': str(e)}


# Register the provider
ProviderFactory.register_loadbalancer_provider('alb', ALBProvider)
