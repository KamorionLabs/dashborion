"""
AWS ECS Fargate Orchestrator Provider implementation.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from providers.base import (
    OrchestratorProvider,
    Service,
    ServiceDetails,
    ServiceTask,
    ServiceDeployment,
    TaskDefinitionDiff,
    ProviderFactory
)
from config import DashboardConfig
from utils.aws import get_cross_account_client, get_action_client, build_sso_console_url


def matches_discovery_tags(resource_tags: list, discovery_tags: dict) -> bool:
    """
    Check if a resource's tags match all the discovery tags.
    resource_tags: List of {'Key': 'x', 'Value': 'y'} or {'key': 'x', 'value': 'y'}
    discovery_tags: Dict of {tag_key: tag_value} to match
    Returns True if ALL discovery_tags are present in resource_tags.
    """
    if not discovery_tags:
        return True  # No tags to match = match all
    if not resource_tags:
        return False

    # Normalize resource tags to dict (handle both AWS tag formats)
    resource_tag_dict = {}
    for tag in resource_tags:
        key = tag.get('Key') or tag.get('key')
        value = tag.get('Value') or tag.get('value')
        if key:
            resource_tag_dict[key] = value

    # Check if all discovery tags match
    for tag_key, tag_value in discovery_tags.items():
        if resource_tag_dict.get(tag_key) != tag_value:
            return False
    return True


class ECSProvider(OrchestratorProvider):
    """
    AWS ECS Fargate implementation of the orchestrator provider.
    """

    def __init__(self, config: DashboardConfig):
        self.config = config
        self.region = config.region

    def _get_ecs_client(self, env: str):
        """Get ECS client for environment"""
        env_config = self.config.get_environment(env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client('ecs', env_config.account_id, env_config.region)

    def _get_logs_client(self, env: str):
        """Get CloudWatch Logs client for environment"""
        env_config = self.config.get_environment(env)
        return get_cross_account_client('logs', env_config.account_id, env_config.region)

    def _get_cloudwatch_client(self, env: str):
        """Get CloudWatch client for environment"""
        env_config = self.config.get_environment(env)
        return get_cross_account_client('cloudwatch', env_config.account_id, env_config.region)

    def _get_secretsmanager_client(self, env: str):
        """Get Secrets Manager client for environment"""
        env_config = self.config.get_environment(env)
        return get_cross_account_client('secretsmanager', env_config.account_id, env_config.region)

    def _get_secret_name(self, secretsmanager, secret_arn: str, cache: dict) -> str:
        """Get the clean secret name (without suffix) from ARN using describe_secret"""
        if secret_arn in cache:
            return cache[secret_arn]
        try:
            response = secretsmanager.describe_secret(SecretId=secret_arn)
            name = response.get('Name', secret_arn)
            cache[secret_arn] = name
            return name
        except Exception:
            # Fallback to ARN if describe fails
            cache[secret_arn] = secret_arn
            return secret_arn

    def get_services(self, env: str) -> Dict[str, Service]:
        """Get all services for an environment"""
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        result = {}
        for service_name in env_config.services:
            try:
                result[service_name] = self.get_service(env, service_name)
            except Exception as e:
                result[service_name] = Service(
                    name=self.config.get_service_name(env, service_name),
                    service=service_name,
                    environment=env,
                    cluster_name=self.config.get_cluster_name(env),
                    status='error',
                    desired_count=0,
                    running_count=0
                )

        return result

    def get_service(self, env: str, service: str) -> Service:
        """Get service information"""
        env_config = self.config.get_environment(env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        ecs = self._get_ecs_client(env)
        cluster_name = self.config.get_cluster_name(env)
        service_name = self.config.get_service_name(env, service)

        # Get service info
        services_response = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )

        if not services_response['services']:
            raise ValueError(f"Service not found: {service_name}")

        svc = services_response['services'][0]

        # Get task definition
        task_def = ecs.describe_task_definition(
            taskDefinition=svc['taskDefinition']
        )['taskDefinition']

        # Get tasks
        tasks = self._get_service_tasks(ecs, cluster_name, service_name, svc['taskDefinition'])

        # Get deployments
        deployments = self._format_deployments(svc['deployments'])

        # Check for latest diff
        latest_diff = self._get_latest_diff(ecs, task_def)

        # Build task definition info
        container = task_def['containerDefinitions'][0]
        task_def_info = {
            'family': task_def['family'],
            'revision': task_def['revision'],
            'cpu': int(task_def['cpu']),
            'memory': int(task_def['memory']),
            'image': container['image'],
            'latestDiff': latest_diff
        }

        console_url = build_sso_console_url(
            self.config.sso_portal_url,
            env_config.account_id,
            f"https://{self.region}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}?region={self.region}"
        )

        return Service(
            name=service_name,
            service=service,
            environment=env,
            cluster_name=cluster_name,
            status=svc['status'],
            desired_count=svc['desiredCount'],
            running_count=svc['runningCount'],
            pending_count=svc['pendingCount'],
            tasks=tasks,
            deployments=deployments,
            task_definition=task_def_info,
            latest_diff=latest_diff,
            console_url=console_url,
            account_id=env_config.account_id
        )

    def _get_service_tasks(self, ecs, cluster_name: str, service_name: str, current_task_def: str) -> List[ServiceTask]:
        """Get tasks for a service"""
        # Get running and pending tasks
        task_arns_running = ecs.list_tasks(
            cluster=cluster_name,
            serviceName=service_name,
            desiredStatus='RUNNING'
        ).get('taskArns', [])

        task_arns_pending = ecs.list_tasks(
            cluster=cluster_name,
            serviceName=service_name,
            desiredStatus='PENDING'
        ).get('taskArns', [])

        all_task_arns = task_arns_running + task_arns_pending
        if not all_task_arns:
            return []

        task_details = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=all_task_arns,
            include=['TAGS']
        )['tasks']

        current_revision = current_task_def.split(':')[-1]
        tasks = []

        for task in task_details:
            task_revision = task['taskDefinitionArn'].split(':')[-1]

            # Extract AZ and subnet from ENI
            az = None
            subnet_id = None
            for attachment in task.get('attachments', []):
                if attachment.get('type') == 'ElasticNetworkInterface':
                    for detail in attachment.get('details', []):
                        if detail.get('name') == 'subnetId':
                            subnet_id = detail.get('value')
                        elif detail.get('name') == 'availabilityZone':
                            az = detail.get('value')

            if not az:
                az = task.get('availabilityZone')

            tasks.append(ServiceTask(
                task_id=task['taskArn'].split('/')[-1],
                status=task['lastStatus'].lower(),
                desired_status=task.get('desiredStatus', 'RUNNING').lower(),
                health=task.get('healthStatus', 'UNKNOWN').lower(),
                revision=task_revision,
                is_latest=task_revision == current_revision,
                az=az,
                subnet_id=subnet_id,
                cpu=task.get('cpu'),
                memory=task.get('memory'),
                started_at=task.get('startedAt'),
                stopped_at=task.get('stoppedAt')
            ))

        return tasks

    def _format_deployments(self, deployments: list) -> List[ServiceDeployment]:
        """Format ECS deployments"""
        result = []
        for d in deployments:
            task_def = d['taskDefinition'].split('/')[-1]
            result.append(ServiceDeployment(
                deployment_id=d.get('id', '').split('/')[-1] if d.get('id') else '',
                status=d['status'].lower(),
                task_definition=task_def,
                revision=task_def.split(':')[-1],
                desired_count=d['desiredCount'],
                running_count=d['runningCount'],
                pending_count=d.get('pendingCount', 0),
                rollout_state=d.get('rolloutState'),
                rollout_reason=d.get('rolloutStateReason'),
                created_at=d.get('createdAt'),
                updated_at=d.get('updatedAt')
            ))
        return result

    def _get_latest_diff(self, ecs, task_def: dict) -> Optional[TaskDefinitionDiff]:
        """Check if current revision is latest and compute diff if not"""
        try:
            task_def_list = ecs.list_task_definitions(
                familyPrefix=task_def['family'],
                sort='DESC',
                maxResults=1
            )

            if not task_def_list.get('taskDefinitionArns'):
                return None

            latest_arn = task_def_list['taskDefinitionArns'][0]
            latest_revision = int(latest_arn.split(':')[-1])
            current_revision = task_def['revision']

            if latest_revision <= current_revision:
                return None

            # Fetch latest task definition
            latest_task_def = ecs.describe_task_definition(
                taskDefinition=latest_arn
            )['taskDefinition']

            return self._compute_task_def_diff(task_def, latest_task_def)

        except Exception as e:
            print(f"Error computing task def diff: {e}")
            return None

    def _compute_task_def_diff(self, from_td: dict, to_td: dict) -> Optional[TaskDefinitionDiff]:
        """Compute diff between two task definitions"""
        if from_td['revision'] == to_td['revision']:
            return None

        from_container = from_td['containerDefinitions'][0]
        to_container = to_td['containerDefinitions'][0]
        changes = []

        # Image diff
        from_image = from_container['image']
        to_image = to_container['image']
        if from_image != to_image:
            from_tag = from_image.split(':')[-1] if ':' in from_image else 'latest'
            to_tag = to_image.split(':')[-1] if ':' in to_image else 'latest'
            changes.append({
                'field': 'image',
                'label': 'Image',
                'from': from_tag[:12],
                'to': to_tag[:12]
            })

        # CPU diff
        if int(from_td['cpu']) != int(to_td['cpu']):
            changes.append({
                'field': 'cpu',
                'label': 'CPU',
                'from': f"{int(from_td['cpu'])} units",
                'to': f"{int(to_td['cpu'])} units"
            })

        # Memory diff
        if int(from_td['memory']) != int(to_td['memory']):
            changes.append({
                'field': 'memory',
                'label': 'Memory',
                'from': f"{int(from_td['memory'])} MB",
                'to': f"{int(to_td['memory'])} MB"
            })

        # Environment variables diff
        from_env = {e['name']: e['value'] for e in from_container.get('environment', [])}
        to_env = {e['name']: e['value'] for e in to_container.get('environment', [])}

        added_vars = set(to_env.keys()) - set(from_env.keys())
        removed_vars = set(from_env.keys()) - set(to_env.keys())
        changed_vars = [k for k in from_env if k in to_env and from_env[k] != to_env[k]]

        if added_vars:
            changes.append({
                'field': 'env_added',
                'label': 'Env Added',
                'from': '-',
                'to': ', '.join(sorted(added_vars)[:5]) + ('...' if len(added_vars) > 5 else '')
            })
        if removed_vars:
            changes.append({
                'field': 'env_removed',
                'label': 'Env Removed',
                'from': ', '.join(sorted(removed_vars)[:5]) + ('...' if len(removed_vars) > 5 else ''),
                'to': '-'
            })
        if changed_vars:
            changes.append({
                'field': 'env_changed',
                'label': 'Env Changed',
                'from': str(len(changed_vars)),
                'to': ', '.join(sorted(changed_vars)[:5]) + ('...' if len(changed_vars) > 5 else '')
            })

        # Secrets diff
        from_secrets = {s['name'] for s in from_container.get('secrets', [])}
        to_secrets = {s['name'] for s in to_container.get('secrets', [])}

        if from_secrets != to_secrets:
            added_secrets = to_secrets - from_secrets
            removed_secrets = from_secrets - to_secrets
            if added_secrets or removed_secrets:
                changes.append({
                    'field': 'secrets',
                    'label': 'Secrets',
                    'from': f"{len(from_secrets)} secrets",
                    'to': f"{len(to_secrets)} secrets (+{len(added_secrets)}/-{len(removed_secrets)})"
                })

        if not changes:
            return None

        return TaskDefinitionDiff(
            from_revision=str(from_td['revision']),
            to_revision=str(to_td['revision']),
            changes=changes
        )

    def get_service_details(self, env: str, service: str) -> ServiceDetails:
        """Get detailed service information including logs and env vars"""
        # Get basic service info first
        svc = self.get_service(env, service)

        env_config = self.config.get_environment(env)
        ecs = self._get_ecs_client(env)
        logs = self._get_logs_client(env)
        secretsmanager = self._get_secretsmanager_client(env)
        secret_name_cache = {}  # Cache to avoid repeated API calls

        cluster_name = self.config.get_cluster_name(env)
        service_name = self.config.get_service_name(env, service)

        # Get task definition details
        services_response = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        svc_data = services_response['services'][0]

        # Get current task definition (the one deployed)
        task_def = ecs.describe_task_definition(
            taskDefinition=svc_data['taskDefinition']
        )['taskDefinition']

        # Get latest task definition (most recent revision in family)
        task_family = task_def['family']
        try:
            latest_task_def = ecs.describe_task_definition(
                taskDefinition=task_family
            )['taskDefinition']
        except:
            latest_task_def = task_def

        container = task_def['containerDefinitions'][0]
        latest_container = latest_task_def['containerDefinitions'][0]

        # Format latest task definition info
        latest_task_def_info = {
            'family': latest_task_def['family'],
            'revision': latest_task_def['revision'],
            'cpu': int(latest_task_def['cpu']),
            'memory': int(latest_task_def['memory']),
            'image': latest_container['image']
        }

        # Extract environment variables
        env_vars = []
        for e in container.get('environment', []):
            name = e.get('name', '')
            value = e.get('value', '')
            # Mask sensitive values
            if any(secret in name.upper() for secret in ['SECRET', 'PASSWORD', 'KEY', 'TOKEN', 'CREDENTIAL']):
                value = '***MASKED***'
            env_vars.append({'name': name, 'value': value, 'type': 'plain'})

        # Get secrets references (extract useful part of ARN like: secret-name:field)
        secrets = []
        for s in container.get('secrets', []):
            value_from = s.get('valueFrom', '')
            secret_name = None
            field_name = None
            # Extract part after ':secret:' and remove trailing colons
            # ARN format: arn:aws:secretsmanager:region:account:secret:name-suffix:field::
            if ':secret:' in value_from:
                secret_part = value_from.split(':secret:')[1].rstrip(':')
                # Extract secret ARN (without field) and field name
                if ':' in secret_part:
                    secret_id_with_suffix = secret_part.split(':')[0]
                    field_name = secret_part.split(':')[1] if len(secret_part.split(':')) > 1 else None
                else:
                    secret_id_with_suffix = secret_part
                # Build the full ARN for describe_secret call
                arn_prefix = value_from.split(':secret:')[0] + ':secret:'
                secret_arn = arn_prefix + secret_id_with_suffix
                # Get the clean secret name via SDK
                secret_name = self._get_secret_name(secretsmanager, secret_arn, secret_name_cache)
                # Display format: clean-name:field
                value_from_display = f"{secret_name}:{field_name}" if field_name else secret_name
                if len(value_from_display) > 50:
                    value_from_display = value_from_display[:50] + '...'
            else:
                value_from_display = value_from[:50] + '...' if len(value_from) > 50 else value_from
            secrets.append({
                'name': s.get('name'),
                'valueFrom': value_from_display,
                'secretName': secret_name,
                'type': 'secret'
            })

        # Combine and sort all variables alphabetically
        all_vars = env_vars + secrets
        all_vars = sorted(all_vars, key=lambda x: x['name'])

        # Get recent logs
        log_group = self.config.get_log_group(env, service)
        recent_logs = self._get_recent_logs(logs, log_group)

        # Get ECS events
        ecs_events = []
        for event in svc_data.get('events', [])[:10]:
            ecs_events.append({
                'id': event.get('id'),
                'createdAt': event['createdAt'].isoformat() if event.get('createdAt') else None,
                'message': event.get('message', '')
            })

        # Detect deployment state
        deployment_state = 'stable'
        is_rolling_back = False

        last_rollback = next((e for e in ecs_events if 'rolling back' in e.get('message', '').lower()), None)
        last_steady = next((e for e in ecs_events if 'reached a steady state' in e.get('message', '').lower()), None)

        if last_rollback:
            if last_steady:
                is_rolling_back = last_rollback.get('createdAt', '') > last_steady.get('createdAt', '')
            else:
                is_rolling_back = True

        if is_rolling_back:
            deployment_state = 'rolling_back'
        elif any(d.rollout_state == 'IN_PROGRESS' for d in svc.deployments):
            deployment_state = 'in_progress'
        elif any(d.rollout_state == 'FAILED' for d in svc.deployments if d.status == 'primary'):
            deployment_state = 'failed'

        # Build console URLs
        console_urls = {
            'service': svc.console_url,
            'logs': build_sso_console_url(
                self.config.sso_portal_url,
                env_config.account_id,
                f"https://{self.region}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}/logs?region={self.region}"
            ),
            'taskDefinitions': build_sso_console_url(
                self.config.sso_portal_url,
                env_config.account_id,
                f"https://{self.region}.console.aws.amazon.com/ecs/v2/task-definitions/{task_def['family']}?region={self.region}"
            ),
            'ssoPortalUrl': self.config.sso_portal_url,
            'accountId': env_config.account_id,
            'region': self.region
        }

        return ServiceDetails(
            name=svc.name,
            service=svc.service,
            environment=env,
            cluster_name=svc.cluster_name,
            status=svc.status,
            desired_count=svc.desired_count,
            running_count=svc.running_count,
            pending_count=svc.pending_count,
            tasks=svc.tasks,
            deployments=svc.deployments,
            task_definition=svc.task_definition,
            latest_diff=svc.latest_diff,
            console_url=svc.console_url,
            account_id=svc.account_id,
            environment_variables=[v for v in all_vars if v['type'] == 'plain'],
            secrets=[v for v in all_vars if v['type'] == 'secret'],
            recent_logs=recent_logs,
            ecs_events=ecs_events,
            deployment_state=deployment_state,
            is_rolling_back=is_rolling_back,
            console_urls=console_urls,
            latest_task_definition=latest_task_def_info
        )

    def _get_recent_logs(self, logs_client, log_group: str, limit: int = 100) -> List[dict]:
        """Get recent logs from CloudWatch"""
        try:
            streams = logs_client.describe_log_streams(
                logGroupName=log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=3
            )

            recent_logs = []
            for stream in streams.get('logStreams', [])[:2]:
                events = logs_client.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream['logStreamName'],
                    limit=50,
                    startFromHead=False
                )
                for event in events.get('events', []):
                    recent_logs.append({
                        'timestamp': datetime.utcfromtimestamp(event['timestamp'] / 1000).isoformat() + 'Z',
                        'message': event['message'][:500],
                        'stream': stream['logStreamName'].split('/')[-1][:12]
                    })

            # Sort chronologically
            recent_logs = sorted(recent_logs, key=lambda x: x['timestamp'])[-limit:]
            return recent_logs

        except logs_client.exceptions.ResourceNotFoundException:
            return []
        except Exception as e:
            return [{'error': str(e)}]

    def get_task_details(self, env: str, service: str, task_id: str) -> dict:
        """Get detailed task information"""
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        ecs = self._get_ecs_client(env)
        logs = self._get_logs_client(env)

        cluster_name = self.config.get_cluster_name(env)
        service_name = self.config.get_service_name(env, service)

        try:
            task_arn = f"arn:aws:ecs:{env_config.region}:{env_config.account_id}:task/{cluster_name}/{task_id}"
            task_response = ecs.describe_tasks(
                cluster=cluster_name,
                tasks=[task_arn],
                include=['TAGS']
            )

            if not task_response.get('tasks'):
                return {'error': f'Task not found: {task_id}'}

            task = task_response['tasks'][0]
            task_def_arn = task['taskDefinitionArn']

            # Get task definition
            task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)['taskDefinition']
            container = task_def['containerDefinitions'][0]

            # Environment variables
            env_vars = []
            for e in container.get('environment', []):
                name = e.get('name', '')
                value = e.get('value', '')
                if any(secret in name.upper() for secret in ['SECRET', 'PASSWORD', 'KEY', 'TOKEN', 'CREDENTIAL']):
                    value = '***MASKED***'
                env_vars.append({'name': name, 'value': value})

            # Secrets
            secrets_refs = []
            for s in container.get('secrets', []):
                secrets_refs.append({
                    'name': s.get('name'),
                    'valueFrom': s.get('valueFrom', '')[:30] + '...' if len(s.get('valueFrom', '')) > 30 else s.get('valueFrom', '')
                })

            # Get placement info
            az = task.get('availabilityZone')
            subnet_id = None
            private_ip = None
            eni_id = None

            for attachment in task.get('attachments', []):
                if attachment.get('type') == 'ElasticNetworkInterface':
                    for detail in attachment.get('details', []):
                        if detail.get('name') == 'subnetId':
                            subnet_id = detail.get('value')
                        elif detail.get('name') == 'availabilityZone':
                            az = detail.get('value')
                        elif detail.get('name') == 'privateIPv4Address':
                            private_ip = detail.get('value')
                        elif detail.get('name') == 'networkInterfaceId':
                            eni_id = detail.get('value')

            # Get logs
            log_group = self.config.get_log_group(env, service)
            log_stream = f"ecs/{service}/{task_id}"
            task_logs = self._get_task_logs(logs, log_group, log_stream)

            # Container info
            container_info = None
            for c in task.get('containers', []):
                if c.get('name') == container['name']:
                    container_info = {
                        'name': c.get('name'),
                        'image': c.get('image'),
                        'imageDigest': c.get('imageDigest'),
                        'lastStatus': c.get('lastStatus'),
                        'healthStatus': c.get('healthStatus'),
                        'cpu': c.get('cpu'),
                        'memory': c.get('memory')
                    }
                    break

            # Console URLs
            console_urls = {
                'task': build_sso_console_url(
                    self.config.sso_portal_url,
                    env_config.account_id,
                    f"https://{self.region}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/tasks/{task_id}?region={self.region}"
                ),
                'ecsExec': build_sso_console_url(
                    self.config.sso_portal_url,
                    env_config.account_id,
                    f"https://{self.region}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/tasks/{task_id}/exec?region={self.region}"
                )
            }

            return {
                'taskId': task_id,
                'taskArn': task_arn,
                'service': service,
                'serviceName': service_name,
                'cluster': cluster_name,
                'status': task.get('lastStatus'),
                'desiredStatus': task.get('desiredStatus'),
                'health': task.get('healthStatus', 'UNKNOWN'),
                'revision': task_def_arn.split(':')[-1],
                'placement': {
                    'az': az,
                    'subnetId': subnet_id,
                    'privateIp': private_ip,
                    'eniId': eni_id
                },
                'resources': {
                    'cpu': task.get('cpu'),
                    'memory': task.get('memory'),
                    'ephemeralStorage': task.get('ephemeralStorage', {}).get('sizeInGiB')
                },
                'container': container_info,
                'environmentVariables': env_vars,
                'secrets': secrets_refs,
                'logs': task_logs,
                'consoleUrls': console_urls,
                'accountId': env_config.account_id,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {'error': f'Failed to get task details: {str(e)}'}

    def _get_task_logs(self, logs_client, log_group: str, log_stream: str) -> List[dict]:
        """Get logs for a specific task"""
        try:
            log_events = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                limit=50,
                startFromHead=False
            )
            logs = []
            for event in log_events.get('events', []):
                logs.append({
                    'timestamp': datetime.utcfromtimestamp(event['timestamp'] / 1000).isoformat() + 'Z',
                    'message': event['message'][:500]
                })
            return logs
        except logs_client.exceptions.ResourceNotFoundException:
            return [{'error': f'Log stream not found: {log_stream}'}]
        except Exception as e:
            return [{'error': f'Failed to get logs: {str(e)}'}]

    def get_service_logs(self, env: str, service: str, lines: int = 50) -> List[dict]:
        """Get recent logs for a service"""
        logs = self._get_logs_client(env)
        log_group = self.config.get_log_group(env, service)
        return self._get_recent_logs(logs, log_group, lines)

    def scale_service(self, env: str, service: str, replicas: int, user_email: str) -> dict:
        """Scale service to specified replica count"""
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        cluster_name = self.config.get_cluster_name(env)
        service_name = self.config.get_service_name(env, service)

        try:
            ecs = get_action_client('ecs', env_config.account_id, user_email, env_config.region)

            response = ecs.update_service(
                cluster=cluster_name,
                service=service_name,
                desiredCount=replicas
            )

            action_name = 'stop' if replicas == 0 else 'start'
            return {
                'success': True,
                'service': service_name,
                'desiredCount': replicas,
                'triggeredBy': user_email,
                'action': action_name
            }
        except Exception as e:
            return {'error': str(e), 'service': service_name}

    def force_deployment(self, env: str, service: str, user_email: str) -> dict:
        """Force a new deployment (reload)"""
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        cluster_name = self.config.get_cluster_name(env)
        service_name = self.config.get_service_name(env, service)

        try:
            ecs = get_action_client('ecs', env_config.account_id, user_email, env_config.region)

            response = ecs.update_service(
                cluster=cluster_name,
                service=service_name,
                forceNewDeployment=True
            )

            return {
                'success': True,
                'service': service_name,
                'deploymentId': response['service']['deployments'][0]['id'],
                'triggeredBy': user_email,
                'action': 'force-new-deployment'
            }
        except Exception as e:
            return {'error': str(e), 'service': service_name}

    def get_infrastructure(self, env: str, discovery_tags: dict = None, services: list = None,
                            domain_config: dict = None, databases: list = None, caches: list = None) -> dict:
        """Get infrastructure topology for an environment (CloudFront, ALB, S3, ECS, RDS, Redis, Network)

        Args:
            env: Environment name (staging, preprod, production)
            discovery_tags: Dict of {tag_key: tag_value} to filter resources
            services: List of service names to look for
            domain_config: Dict with domain patterns
            databases: List of database types to look for (e.g., ["postgres", "mysql"])
            caches: List of cache types to look for (e.g., ["redis"])
        """
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        # Default values for backwards compatibility
        # Note: services list comes from frontend config, no fallback on DashboardConfig
        services = services or ['backend', 'frontend', 'cms']  # Default services if not specified
        databases = databases if databases is not None else ['postgres']
        caches = caches if caches is not None else ['redis']

        account_id = env_config.account_id
        elbv2 = get_cross_account_client('elbv2', account_id, env_config.region)
        cloudfront = get_cross_account_client('cloudfront', account_id)
        s3 = get_cross_account_client('s3', account_id, env_config.region)
        ecs = self._get_ecs_client(env)
        rds = get_cross_account_client('rds', account_id, env_config.region)
        elasticache = get_cross_account_client('elasticache', account_id, env_config.region)
        ec2 = get_cross_account_client('ec2', account_id, env_config.region)

        cluster_name = self.config.get_cluster_name(env)
        domain_suffix = f"{env}.{self.config.project_name}.kamorion.cloud"

        # Domain patterns - use domain_config or fallback to defaults
        if domain_config and domain_config.get('domains'):
            domains_map = domain_config.get('domains', {})
            result_domains = {}
            for svc, prefix in domains_map.items():
                result_domains[svc] = f"https://{prefix}.{domain_suffix}"
        else:
            # Fallback to hardcoded patterns for backwards compatibility
            result_domains = {
                'frontend': f"https://fr.{domain_suffix}",
                'backend': f"https://back.{domain_suffix}",
                'cms': f"https://cms.{domain_suffix}"
            }

        result = {
            'environment': env,
            'accountId': account_id,
            'domains': result_domains,
            'cloudfront': None,
            'alb': None,
            's3Buckets': [],
            'services': {},
            'rds': None,
            'redis': None,
            'network': None,
            'orchestrator': 'ecs'
        }

        cloudfront_s3_origins = set()

        # Extract domain prefixes from domain_config for precise CloudFront matching
        domain_prefixes = None
        if domain_config and domain_config.get('domains'):
            domain_prefixes = list(domain_config['domains'].values())

        # CloudFront
        try:
            result['cloudfront'] = self._get_cloudfront_info(cloudfront, domain_suffix, account_id, domain_prefixes)
            if result['cloudfront'] and 'origins' in result['cloudfront']:
                for origin in result['cloudfront'].get('origins', []):
                    if origin.get('type') == 's3':
                        bucket_name = origin['domainName'].split('.s3.')[0]
                        cloudfront_s3_origins.add(bucket_name)
        except Exception as e:
            result['cloudfront'] = {'error': str(e)}

        # ALB (filter target groups by services list)
        try:
            result['alb'] = self._get_alb_info(elbv2, env, account_id, services)
        except Exception as e:
            result['alb'] = {'error': str(e)}

        # S3 Buckets (CloudFront origins only)
        try:
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

        # ECS Services with tasks by AZ
        try:
            result['services'] = self._get_services_for_infrastructure(ecs, env, cluster_name, account_id, services)
        except Exception as e:
            result['services'] = {'error': str(e)}

        # RDS (filtered by discovery_tags and database type)
        try:
            result['rds'] = self._get_rds_info(rds, env, account_id, discovery_tags, databases)
        except Exception as e:
            result['rds'] = {'error': str(e)}

        # ElastiCache Redis (filtered by discovery_tags and cache type)
        if caches:  # Only fetch if caches are requested
            try:
                result['redis'] = self._get_redis_info(elasticache, env, account_id, discovery_tags, caches)
            except Exception as e:
                result['redis'] = {'error': str(e)}

        # VPC/Network
        try:
            result['network'] = self._get_network_info(ec2, env, account_id)
        except Exception as e:
            result['network'] = {'error': str(e)}

        return result

    def _get_cloudfront_info(self, cloudfront, domain_suffix: str, account_id: str, domain_prefixes: list = None) -> dict:
        """Get CloudFront distribution info

        Args:
            cloudfront: CloudFront client
            domain_suffix: e.g., 'staging.homebox.kamorion.cloud'
            account_id: AWS account ID
            domain_prefixes: List of domain prefixes to match (e.g., ['fr', 'back', 'cms'] for kanbios)
                            If provided, only match distributions with aliases matching {prefix}.{domain_suffix}
        """
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

    def _get_alb_info(self, elbv2, env: str, account_id: str, services: list = None) -> dict:
        """Get ALB info

        Args:
            elbv2: ELBv2 client
            env: Environment name
            account_id: AWS account ID
            services: List of service names to filter target groups (e.g., ['backend', 'frontend', 'cms'])
        """
        from urllib.parse import quote
        alb_name = f"{self.config.project_name}-{env}-alb"

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

    def _get_services_for_infrastructure(self, ecs, env: str, cluster_name: str, account_id: str, services: list = None) -> dict:
        """Get ECS services with task details for infrastructure view"""
        env_config = self.config.get_environment(env)
        services_result = {}

        # Use provided services list or fall back to env_config.services
        service_list = services or env_config.services

        for svc_name in service_list:
            try:
                service_name = self.config.get_service_name(env, svc_name)
                svc_response = ecs.describe_services(cluster=cluster_name, services=[service_name])

                if not svc_response['services']:
                    continue

                s = svc_response['services'][0]
                current_revision = s['taskDefinition'].split(':')[-1]

                # Get all tasks
                all_task_arns = []
                for status in ['RUNNING', 'PENDING']:
                    task_arns = ecs.list_tasks(
                        cluster=cluster_name,
                        serviceName=service_name,
                        desiredStatus=status
                    ).get('taskArns', [])
                    all_task_arns.extend(task_arns)

                tasks = []
                tasks_by_az = {}
                if all_task_arns:
                    task_details = ecs.describe_tasks(cluster=cluster_name, tasks=all_task_arns)['tasks']
                    for task in task_details:
                        task_revision = task['taskDefinitionArn'].split(':')[-1]
                        az = None
                        subnet_id = None

                        for attachment in task.get('attachments', []):
                            if attachment.get('type') == 'ElasticNetworkInterface':
                                for detail in attachment.get('details', []):
                                    if detail.get('name') == 'subnetId':
                                        subnet_id = detail.get('value')
                                    elif detail.get('name') == 'availabilityZone':
                                        az = detail.get('value')
                        if not az:
                            az = task.get('availabilityZone')

                        task_info = {
                            'taskId': task['taskArn'].split('/')[-1][:8],
                            'fullId': task['taskArn'].split('/')[-1],
                            'status': task['lastStatus'],
                            'desiredStatus': task.get('desiredStatus', 'RUNNING'),
                            'health': task.get('healthStatus', 'UNKNOWN'),
                            'revision': task_revision,
                            'isLatest': task_revision == current_revision,
                            'az': az,
                            'startedAt': task.get('startedAt', '').isoformat() if task.get('startedAt') else None
                        }
                        tasks.append(task_info)

                        if az:
                            if az not in tasks_by_az:
                                tasks_by_az[az] = []
                            tasks_by_az[az].append(task_info)

                # Deployments
                deployments = [{
                    'status': d['status'],
                    'taskDefinition': d['taskDefinition'].split('/')[-1],
                    'revision': d['taskDefinition'].split(':')[-1],
                    'desiredCount': d['desiredCount'],
                    'runningCount': d['runningCount'],
                    'pendingCount': d.get('pendingCount', 0),
                    'rolloutState': d.get('rolloutState'),
                    'rolloutStateReason': d.get('rolloutStateReason'),
                    'isPrimary': d['status'] == 'PRIMARY'
                } for d in s['deployments']]

                is_rolling = len(deployments) > 1 or any(d['status'] == 'ACTIVE' for d in deployments if d['status'] != 'PRIMARY')

                services_result[svc_name] = {
                    'name': service_name,
                    'status': s['status'],
                    'runningCount': s['runningCount'],
                    'desiredCount': s['desiredCount'],
                    'pendingCount': s.get('pendingCount', 0),
                    'health': 'healthy' if s['runningCount'] == s['desiredCount'] and s['desiredCount'] > 0 else 'unhealthy',
                    'currentRevision': current_revision,
                    'tasks': tasks,
                    'tasksByAz': tasks_by_az,
                    'deployments': deployments,
                    'isRollingUpdate': is_rolling,
                    'consoleUrl': build_sso_console_url(
                        self.config.sso_portal_url, account_id,
                        f"https://{self.region}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}?region={self.region}"
                    )
                }
            except Exception as e:
                services_result[svc_name] = {'error': str(e)}

        return services_result

    def _get_rds_info(self, rds, env: str, account_id: str, discovery_tags: dict = None, databases: list = None) -> dict:
        """Get RDS database info (filtered by discovery_tags and database type)"""
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
            tags_match = matches_discovery_tags(db_tags, discovery_tags) if discovery_tags else (self.config.project_name in db_id and env in db_id)

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

    def _get_redis_info(self, elasticache, env: str, account_id: str, discovery_tags: dict = None, caches: list = None) -> dict:
        """Get ElastiCache Redis/Valkey info (filtered by discovery_tags and cache type)"""
        caches = caches or ['redis']
        clusters = elasticache.describe_cache_clusters(ShowCacheNodeInfo=True)
        for cluster in clusters.get('CacheClusters', []):
            cluster_id = cluster['CacheClusterId']
            cache_engine = cluster['Engine'].lower()

            # Check if this cache type is in our requested list
            engine_matches = False
            for cache_type in caches:
                if cache_type.lower() in cache_engine or cache_engine in cache_type.lower() or \
                   (cache_type.lower() == 'redis' and cache_engine == 'valkey'):
                    engine_matches = True
                    break
            if not engine_matches:
                continue

            # Get ElastiCache tags and check if they match discovery_tags
            try:
                cluster_arn = cluster['ARN']
                tag_response = elasticache.list_tags_for_resource(ResourceName=cluster_arn)
                cache_tags = tag_response.get('TagList', [])
            except Exception:
                cache_tags = []

            # Check if discovery_tags match (or fallback to name-based matching)
            tags_match = matches_discovery_tags(cache_tags, discovery_tags) if discovery_tags else (self.config.project_name in cluster_id and env in cluster_id)

            if not tags_match:
                continue

            # Get replication group info if available
            repl_group_id = cluster.get('ReplicationGroupId')
            repl_group_info = None
            if repl_group_id:
                try:
                    repl_groups = elasticache.describe_replication_groups(ReplicationGroupId=repl_group_id)
                    if repl_groups.get('ReplicationGroups'):
                        repl_group_info = repl_groups['ReplicationGroups'][0]
                except:
                    pass

            cache_nodes = cluster.get('CacheNodes', [])
            endpoint = None
            if repl_group_info and repl_group_info.get('ConfigurationEndpoint'):
                endpoint = repl_group_info['ConfigurationEndpoint']
            elif repl_group_info and repl_group_info.get('NodeGroups'):
                endpoint = repl_group_info['NodeGroups'][0].get('PrimaryEndpoint')
            elif cache_nodes:
                endpoint = cache_nodes[0].get('Endpoint')

            nodes_by_az = {}
            for node in cache_nodes:
                az = node.get('CustomerAvailabilityZone') or cluster.get('PreferredAvailabilityZone')
                if az:
                    if az not in nodes_by_az:
                        nodes_by_az[az] = []
                    nodes_by_az[az].append({
                        'id': node.get('CacheNodeId'),
                        'status': node.get('CacheNodeStatus'),
                        'endpoint': node.get('Endpoint', {}).get('Address')
                    })

            multi_az = False
            if repl_group_info:
                multi_az = repl_group_info.get('MultiAZ', 'disabled') == 'enabled'
                if not multi_az and len(nodes_by_az) > 1:
                    multi_az = True

            return {
                'clusterId': cluster_id,
                'replicationGroupId': repl_group_id,
                'engine': cluster['Engine'],
                'engineVersion': cluster['EngineVersion'],
                'cacheNodeType': cluster['CacheNodeType'],
                'status': cluster['CacheClusterStatus'],
                'numCacheNodes': cluster.get('NumCacheNodes', 0),
                'multiAz': multi_az,
                'nodesByAz': nodes_by_az,
                'endpoint': {
                    'address': endpoint.get('Address') if endpoint else None,
                    'port': endpoint.get('Port') if endpoint else None
                } if endpoint else None,
                'preferredAvailabilityZone': cluster.get('PreferredAvailabilityZone'),
                'snapshotRetentionLimit': cluster.get('SnapshotRetentionLimit', 0),
                'snapshotWindow': cluster.get('SnapshotWindow'),
                'maintenanceWindow': cluster.get('PreferredMaintenanceWindow'),
                'transitEncryption': cluster.get('TransitEncryptionEnabled', False),
                'atRestEncryption': cluster.get('AtRestEncryptionEnabled', False),
                'authTokenEnabled': cluster.get('AuthTokenEnabled', False),
                'securityGroups': [sg['SecurityGroupId'] for sg in cluster.get('SecurityGroups', [])],
                'parameterGroup': cluster.get('CacheParameterGroup', {}).get('CacheParameterGroupName'),
                'consoleUrl': build_sso_console_url(
                    self.config.sso_portal_url, account_id,
                    f"https://{self.region}.console.aws.amazon.com/elasticache/home?region={self.region}#/redis/{cluster_id}"
                )
            }
        return None

    def _get_network_info(self, ec2, env: str, account_id: str) -> dict:
        """Get VPC and network info"""
        vpc_name = f"{self.config.project_name}-{env}"

        vpcs = ec2.describe_vpcs(
            Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}]
        )

        if not vpcs.get('Vpcs'):
            return None

        vpc = vpcs['Vpcs'][0]
        vpc_id = vpc['VpcId']

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

        # NAT Gateway
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

    def get_routing_details(self, env: str, service_security_groups: list = None) -> dict:
        """Get detailed routing and security information (called on demand via toggle)"""
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.get('account_id')
        ec2 = self._get_ec2_client(env)

        # Get VPC ID
        vpc_name = f"{self.config.project_name}-{env}"
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

    def get_metrics(self, env: str, service: str) -> dict:
        """Get service metrics (CPU, memory)"""
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        cloudwatch = self._get_cloudwatch_client(env)
        cluster_name = self.config.get_cluster_name(env)
        service_name = self.config.get_service_name(env, service)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=6)

        metrics_data = {}

        # CPU Utilization
        cpu_response = cloudwatch.get_metric_statistics(
            Namespace='AWS/ECS',
            MetricName='CPUUtilization',
            Dimensions=[
                {'Name': 'ClusterName', 'Value': cluster_name},
                {'Name': 'ServiceName', 'Value': service_name}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,
            Statistics=['Average']
        )

        metrics_data['cpu'] = sorted([
            {'timestamp': dp['Timestamp'].isoformat(), 'value': round(dp['Average'], 2)}
            for dp in cpu_response['Datapoints']
        ], key=lambda x: x['timestamp'])

        # Memory Utilization
        memory_response = cloudwatch.get_metric_statistics(
            Namespace='AWS/ECS',
            MetricName='MemoryUtilization',
            Dimensions=[
                {'Name': 'ClusterName', 'Value': cluster_name},
                {'Name': 'ServiceName', 'Value': service_name}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,
            Statistics=['Average']
        )

        metrics_data['memory'] = sorted([
            {'timestamp': dp['Timestamp'].isoformat(), 'value': round(dp['Average'], 2)}
            for dp in memory_response['Datapoints']
        ], key=lambda x: x['timestamp'])

        return {
            'environment': env,
            'service': service,
            'timeRange': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat()
            },
            'metrics': metrics_data,
            'accountId': env_config.account_id
        }


# Register the provider
ProviderFactory.register_orchestrator_provider('ecs', ECSProvider)
