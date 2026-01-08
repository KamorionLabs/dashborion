"""
AWS Application Load Balancer Provider implementation.
"""

from typing import List, Optional
from urllib.parse import quote

from providers.base import LoadBalancerProvider, ProviderFactory
from config import DashboardConfig
from utils.aws import get_cross_account_client, build_sso_console_url


class ALBProvider(LoadBalancerProvider):
    """
    AWS Application Load Balancer implementation of the load balancer provider.
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
        return get_cross_account_client('elbv2', env_config.account_id, env_config.region)

    def get_load_balancer(self, env: str, services: List[str] = None) -> dict:
        """Get ALB info with target groups filtered by services

        Args:
            env: Environment name
            services: List of service names to filter target groups (e.g., ['backend', 'frontend', 'cms'])
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.account_id
        elbv2 = self._get_elbv2_client(env)

        alb_name = f"{self.project}-{env}-alb"

        try:
            albs = elbv2.describe_load_balancers()
            for alb in albs.get('LoadBalancers', []):
                if alb['LoadBalancerName'] == alb_name:
                    alb_arn = alb['LoadBalancerArn']
                    alb_info = {
                        'name': alb['LoadBalancerName'],
                        'arn': alb_arn,
                        'dnsName': alb['DNSName'],
                        'state': alb['State']['Code'],
                        'type': alb['Type'],
                        'scheme': alb['Scheme'],
                        'securityGroups': alb.get('SecurityGroups', []),  # List of SG IDs
                        'listeners': [],
                        'targetGroups': [],
                        'rules': [],
                        'consoleUrl': build_sso_console_url(
                            self.config.sso_portal_url, account_id,
                            f"https://{self.region}.console.aws.amazon.com/ec2/home?region={self.region}#LoadBalancer:loadBalancerArn={quote(alb_arn, safe='')}"
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

                    # Target Groups - filter by services list if provided
                    tgs = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
                    services_to_match = services or ['backend', 'frontend', 'cms']  # Fallback for backwards compatibility

                    for tg in tgs.get('TargetGroups', []):
                        tg_arn = tg['TargetGroupArn']
                        tg_name = tg['TargetGroupName']

                        # Detect which service this target group belongs to
                        service_name = None
                        for svc in services_to_match:
                            if svc in tg_name:
                                service_name = svc
                                break

                        # Skip target groups that don't match any of our services
                        if services and service_name is None:
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
                                f"https://{self.region}.console.aws.amazon.com/ec2/home?region={self.region}#TargetGroup:targetGroupArn={quote(tg_arn, safe='')}"
                            )
                        })
                    return alb_info

            return None

        except Exception as e:
            return {'error': str(e)}


# Register the provider
ProviderFactory.register_loadbalancer_provider('alb', ALBProvider)
