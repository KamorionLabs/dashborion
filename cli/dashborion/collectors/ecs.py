"""ECS collector for Dashborion CLI"""

import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


class ECSCollector:
    """Collect data from AWS ECS"""

    def __init__(self, session):
        self.session = session
        self.ecs = session.client('ecs')
        self.logs = session.client('logs')
        self.region = session.region_name

    def get_cluster_status(self, cluster: str) -> Dict[str, Any]:
        """Get cluster status overview"""
        try:
            response = self.ecs.describe_clusters(clusters=[cluster])
            if not response.get('clusters'):
                return {'error': f'Cluster {cluster} not found'}

            cluster_data = response['clusters'][0]

            # Get services count
            services = self.list_services(cluster)

            return {
                'name': cluster_data.get('clusterName'),
                'status': cluster_data.get('status'),
                'runningTasks': cluster_data.get('runningTasksCount', 0),
                'pendingTasks': cluster_data.get('pendingTasksCount', 0),
                'activeServices': cluster_data.get('activeServicesCount', 0),
                'registeredInstances': cluster_data.get('registeredContainerInstancesCount', 0),
                'capacityProviders': cluster_data.get('capacityProviders', []),
                'services': len(services),
            }

        except Exception as e:
            return {'error': str(e)}

    def list_services(self, cluster: str) -> List[Dict[str, Any]]:
        """List all services in a cluster"""
        services = []

        try:
            paginator = self.ecs.get_paginator('list_services')
            service_arns = []

            for page in paginator.paginate(cluster=cluster):
                service_arns.extend(page.get('serviceArns', []))

            if not service_arns:
                return services

            # Describe services in batches of 10
            for i in range(0, len(service_arns), 10):
                batch = service_arns[i:i + 10]
                response = self.ecs.describe_services(cluster=cluster, services=batch)

                for svc in response.get('services', []):
                    services.append({
                        'name': svc.get('serviceName'),
                        'status': svc.get('status'),
                        'runningCount': svc.get('runningCount', 0),
                        'desiredCount': svc.get('desiredCount', 0),
                        'pendingCount': svc.get('pendingCount', 0),
                        'launchType': svc.get('launchType', 'FARGATE'),
                        'taskDefinition': svc.get('taskDefinition', '').split('/')[-1],
                        'createdAt': svc.get('createdAt'),
                        'deployments': len(svc.get('deployments', [])),
                    })

        except Exception as e:
            return [{'error': str(e)}]

        return services

    def describe_service(self, cluster: str, service: str) -> Dict[str, Any]:
        """Get detailed service information"""
        try:
            response = self.ecs.describe_services(cluster=cluster, services=[service])

            if not response.get('services'):
                return {'error': f'Service {service} not found'}

            svc = response['services'][0]

            # Get task definition details
            task_def = None
            if svc.get('taskDefinition'):
                td_response = self.ecs.describe_task_definition(
                    taskDefinition=svc['taskDefinition']
                )
                td = td_response.get('taskDefinition', {})
                task_def = {
                    'family': td.get('family'),
                    'revision': td.get('revision'),
                    'cpu': td.get('cpu'),
                    'memory': td.get('memory'),
                    'containers': [
                        {
                            'name': c.get('name'),
                            'image': c.get('image'),
                            'cpu': c.get('cpu'),
                            'memory': c.get('memory'),
                            'essential': c.get('essential', True),
                        }
                        for c in td.get('containerDefinitions', [])
                    ]
                }

            return {
                'name': svc.get('serviceName'),
                'arn': svc.get('serviceArn'),
                'status': svc.get('status'),
                'runningCount': svc.get('runningCount', 0),
                'desiredCount': svc.get('desiredCount', 0),
                'pendingCount': svc.get('pendingCount', 0),
                'launchType': svc.get('launchType', 'FARGATE'),
                'platformVersion': svc.get('platformVersion'),
                'taskDefinition': task_def,
                'loadBalancers': svc.get('loadBalancers', []),
                'networkConfiguration': svc.get('networkConfiguration'),
                'deployments': [
                    {
                        'id': d.get('id'),
                        'status': d.get('status'),
                        'taskDefinition': d.get('taskDefinition', '').split('/')[-1],
                        'runningCount': d.get('runningCount', 0),
                        'desiredCount': d.get('desiredCount', 0),
                        'createdAt': d.get('createdAt'),
                        'rolloutState': d.get('rolloutState'),
                    }
                    for d in svc.get('deployments', [])
                ],
                'events': [
                    {
                        'message': e.get('message'),
                        'createdAt': e.get('createdAt'),
                    }
                    for e in svc.get('events', [])[:10]
                ],
                'createdAt': svc.get('createdAt'),
            }

        except Exception as e:
            return {'error': str(e)}

    def list_tasks(self, cluster: str, service: str) -> List[Dict[str, Any]]:
        """List tasks for a service"""
        tasks = []

        try:
            # List task ARNs
            response = self.ecs.list_tasks(cluster=cluster, serviceName=service)
            task_arns = response.get('taskArns', [])

            if not task_arns:
                return tasks

            # Describe tasks
            response = self.ecs.describe_tasks(cluster=cluster, tasks=task_arns)

            for task in response.get('tasks', []):
                task_id = task.get('taskArn', '').split('/')[-1]

                # Get container info
                containers = []
                for container in task.get('containers', []):
                    containers.append({
                        'name': container.get('name'),
                        'lastStatus': container.get('lastStatus'),
                        'healthStatus': container.get('healthStatus'),
                        'exitCode': container.get('exitCode'),
                    })

                # Get private IP
                private_ip = None
                for attachment in task.get('attachments', []):
                    for detail in attachment.get('details', []):
                        if detail.get('name') == 'privateIPv4Address':
                            private_ip = detail.get('value')
                            break

                tasks.append({
                    'taskId': task_id,
                    'taskArn': task.get('taskArn'),
                    'lastStatus': task.get('lastStatus'),
                    'desiredStatus': task.get('desiredStatus'),
                    'healthStatus': task.get('healthStatus'),
                    'launchType': task.get('launchType'),
                    'cpu': task.get('cpu'),
                    'memory': task.get('memory'),
                    'startedAt': task.get('startedAt'),
                    'stoppedAt': task.get('stoppedAt'),
                    'stoppedReason': task.get('stoppedReason'),
                    'privateIp': private_ip,
                    'containers': containers,
                })

        except Exception as e:
            return [{'error': str(e)}]

        return tasks

    def stream_logs(self, cluster: str, service: str, tail: int = 50,
                    follow: bool = False, since: Optional[str] = None):
        """Stream logs from CloudWatch"""
        import click

        # Determine log group name (common patterns)
        log_group_patterns = [
            f"/ecs/{cluster}/{service}",
            f"/ecs/{service}",
            f"/aws/ecs/{cluster}/{service}",
        ]

        log_group = None
        for pattern in log_group_patterns:
            try:
                self.logs.describe_log_groups(logGroupNamePrefix=pattern, limit=1)
                log_group = pattern
                break
            except Exception:
                continue

        if not log_group:
            click.echo(f"Could not find log group for {service}", err=True)
            return

        # Calculate start time
        start_time = None
        if since:
            # Parse duration like "1h", "30m", "2d"
            import re
            match = re.match(r'(\d+)([hdm])', since)
            if match:
                value, unit = int(match.group(1)), match.group(2)
                if unit == 'h':
                    start_time = datetime.utcnow() - timedelta(hours=value)
                elif unit == 'm':
                    start_time = datetime.utcnow() - timedelta(minutes=value)
                elif unit == 'd':
                    start_time = datetime.utcnow() - timedelta(days=value)

        # Get logs
        kwargs = {
            'logGroupName': log_group,
            'limit': tail,
            'interleaved': True,
        }

        if start_time:
            kwargs['startTime'] = int(start_time.timestamp() * 1000)

        try:
            response = self.logs.filter_log_events(**kwargs)

            for event in response.get('events', []):
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                message = event.get('message', '')
                click.echo(f"{timestamp.strftime('%H:%M:%S')} {message}")

            if follow:
                next_token = response.get('nextToken')
                while True:
                    time.sleep(2)
                    kwargs['nextToken'] = next_token
                    response = self.logs.filter_log_events(**kwargs)

                    for event in response.get('events', []):
                        timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                        message = event.get('message', '')
                        click.echo(f"{timestamp.strftime('%H:%M:%S')} {message}")

                    next_token = response.get('nextToken')

        except Exception as e:
            click.echo(f"Error fetching logs: {e}", err=True)

    def force_deploy(self, cluster: str, service: str, image: Optional[str] = None) -> Dict[str, Any]:
        """Force a new deployment"""
        try:
            kwargs = {
                'cluster': cluster,
                'service': service,
                'forceNewDeployment': True,
            }

            response = self.ecs.update_service(**kwargs)
            svc = response.get('service', {})

            # Find the new deployment
            deployments = svc.get('deployments', [])
            primary = next((d for d in deployments if d.get('status') == 'PRIMARY'), None)

            return {
                'success': True,
                'deploymentId': primary.get('id') if primary else None,
                'status': svc.get('status'),
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}
