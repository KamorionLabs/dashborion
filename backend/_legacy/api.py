"""
Dashboard API Lambda Handler
Provides endpoints for ECS services, pipelines, and metrics
"""

import json
import os
import boto3
from datetime import datetime, timedelta
from functools import lru_cache
from urllib.parse import quote

# Environment variables
ENVIRONMENTS = json.loads(os.environ.get('ENVIRONMENTS', '{}'))
SHARED_SERVICES_ACCOUNT = os.environ.get('SHARED_SERVICES_ACCOUNT', '')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'myapp')
REGION = os.environ.get('AWS_REGION_DEFAULT', os.environ.get('AWS_REGION', 'eu-west-3'))
SSO_PORTAL_URL = os.environ.get('SSO_PORTAL_URL', '')


def build_sso_console_url(account_id: str, destination_url: str) -> str:
    """Build SSO console shortcut URL for Identity Center"""
    if not SSO_PORTAL_URL:
        return destination_url
    encoded_destination = quote(destination_url, safe='')
    return f"{SSO_PORTAL_URL}/#/console?account_id={account_id}&destination={encoded_destination}"


def get_cross_account_client(service: str, account_id: str):
    """Get boto3 client with cross-account role assumption"""
    if account_id == SHARED_SERVICES_ACCOUNT:
        return boto3.client(service, region_name=REGION)

    sts = boto3.client('sts')
    role_arn = f"arn:aws:iam::{account_id}:role/{PROJECT_NAME}-dashboard-read-role"

    assumed = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='dashboard-api'
    )

    credentials = assumed['Credentials']
    return boto3.client(
        service,
        region_name=REGION,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )


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


def get_resource_tags(client, resource_arn: str) -> list:
    """Get tags for an AWS resource using the tagging API"""
    try:
        response = client.list_tags_for_resource(ResourceArn=resource_arn)
        return response.get('TagList', []) or response.get('Tags', [])
    except Exception:
        return []


def compute_task_def_diff(from_task_def, to_task_def):
    """Compute diff between two task definitions (from -> to)"""
    if from_task_def['revision'] == to_task_def['revision']:
        return None

    from_container = from_task_def['containerDefinitions'][0]
    to_container = to_task_def['containerDefinitions'][0]

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
    if int(from_task_def['cpu']) != int(to_task_def['cpu']):
        changes.append({
            'field': 'cpu',
            'label': 'CPU',
            'from': f"{int(from_task_def['cpu'])} units",
            'to': f"{int(to_task_def['cpu'])} units"
        })

    # Memory diff
    if int(from_task_def['memory']) != int(to_task_def['memory']):
        changes.append({
            'field': 'memory',
            'label': 'Memory',
            'from': f"{int(from_task_def['memory'])} MB",
            'to': f"{int(to_task_def['memory'])} MB"
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

    if changes:
        return {
            'fromRevision': from_task_def['revision'],
            'toRevision': to_task_def['revision'],
            'changes': changes
        }
    return None


def get_task_definition_diffs(env, items):
    """
    Compute diffs for a list of task definition pairs.
    items: [{ family: str, fromRevision: int, toRevision: int }, ...]
    Returns: { "family:fromRev-toRev": { diff object } or null, ... }
    """
    account_id = ENVIRONMENTS.get(env, {}).get('account_id')
    if not account_id:
        return {'error': f'Unknown environment: {env}'}

    try:
        ecs = get_cross_account_client('ecs', account_id)
        results = {}

        for item in items[:10]:  # Limit to 10 items per request
            family = item.get('family')
            from_rev = item.get('fromRevision')
            to_rev = item.get('toRevision')

            if not family or not from_rev or not to_rev:
                continue

            key = f"{family}:{from_rev}-{to_rev}"

            try:
                # Fetch both task definitions
                from_td = ecs.describe_task_definition(
                    taskDefinition=f"{family}:{from_rev}"
                )['taskDefinition']

                to_td = ecs.describe_task_definition(
                    taskDefinition=f"{family}:{to_rev}"
                )['taskDefinition']

                # Compute diff
                diff = compute_task_def_diff(from_td, to_td)
                results[key] = diff

            except Exception as e:
                print(f"Error computing diff for {key}: {e}")
                results[key] = None

        return {'diffs': results}

    except Exception as e:
        print(f"Error in get_task_definition_diffs: {e}")
        return {'error': str(e)}


def get_service_info(env: str, service: str) -> dict:
    """Get ECS service information"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    cluster_name = f"{PROJECT_NAME}-{env}-cluster"
    service_name = f"{PROJECT_NAME}-{env}-{service}"

    ecs = get_cross_account_client('ecs', account_id)

    # Get service info
    services = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )

    if not services['services']:
        return {'error': f'Service not found: {service_name}'}

    svc = services['services'][0]

    # Get task definition
    task_def = ecs.describe_task_definition(
        taskDefinition=svc['taskDefinition']
    )['taskDefinition']

    # Get ALL tasks (running + pending for rolling update visibility)
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

    tasks = []
    if all_task_arns:
        task_details = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=all_task_arns,
            include=['TAGS']
        )['tasks']

        # Get current task definition revision
        current_revision = svc['taskDefinition'].split(':')[-1]

        for task in task_details:
            task_revision = task['taskDefinitionArn'].split(':')[-1]
            # Determine AZ from task's attachment (ENI)
            az = None
            subnet_id = None
            for attachment in task.get('attachments', []):
                if attachment.get('type') == 'ElasticNetworkInterface':
                    for detail in attachment.get('details', []):
                        if detail.get('name') == 'subnetId':
                            subnet_id = detail.get('value')
                        elif detail.get('name') == 'availabilityZone':
                            az = detail.get('value')

            # Fallback: try to get AZ from container instance if Fargate doesn't provide it
            if not az and task.get('availabilityZone'):
                az = task.get('availabilityZone')

            tasks.append({
                'taskId': task['taskArn'].split('/')[-1],
                'status': task['lastStatus'],
                'desiredStatus': task.get('desiredStatus', 'RUNNING'),
                'health': task.get('healthStatus', 'UNKNOWN'),
                'startedAt': task.get('startedAt', '').isoformat() if task.get('startedAt') else None,
                'stoppedAt': task.get('stoppedAt', '').isoformat() if task.get('stoppedAt') else None,
                'revision': task_revision,
                'isLatest': task_revision == current_revision,
                'az': az,
                'subnetId': subnet_id,
                'cpu': task.get('cpu'),
                'memory': task.get('memory')
            })

    # Get container image info
    container = task_def['containerDefinitions'][0]
    image = container['image']

    # Check if current revision is latest, and compute diff if not
    latest_diff = None
    try:
        # List all task definitions for this family
        task_def_list = ecs.list_task_definitions(
            familyPrefix=task_def['family'],
            sort='DESC',
            maxResults=1
        )
        if task_def_list.get('taskDefinitionArns'):
            latest_arn = task_def_list['taskDefinitionArns'][0]
            latest_revision = int(latest_arn.split(':')[-1])
            current_revision_num = task_def['revision']

            if latest_revision > current_revision_num:
                # Fetch latest task definition
                latest_task_def = ecs.describe_task_definition(
                    taskDefinition=latest_arn
                )['taskDefinition']
                latest_container = latest_task_def['containerDefinitions'][0]

                # Compute diff
                diff = {
                    'currentRevision': current_revision_num,
                    'latestRevision': latest_revision,
                    'changes': []
                }

                # Image diff
                current_image = image
                latest_image = latest_container['image']
                if current_image != latest_image:
                    # Extract tag from image
                    current_tag = current_image.split(':')[-1] if ':' in current_image else 'latest'
                    latest_tag = latest_image.split(':')[-1] if ':' in latest_image else 'latest'
                    diff['changes'].append({
                        'field': 'image',
                        'label': 'Image',
                        'current': current_tag[:12],
                        'latest': latest_tag[:12]
                    })

                # CPU diff
                if int(task_def['cpu']) != int(latest_task_def['cpu']):
                    diff['changes'].append({
                        'field': 'cpu',
                        'label': 'CPU',
                        'current': f"{int(task_def['cpu'])} units",
                        'latest': f"{int(latest_task_def['cpu'])} units"
                    })

                # Memory diff
                if int(task_def['memory']) != int(latest_task_def['memory']):
                    diff['changes'].append({
                        'field': 'memory',
                        'label': 'Memory',
                        'current': f"{int(task_def['memory'])} MB",
                        'latest': f"{int(latest_task_def['memory'])} MB"
                    })

                # Environment variables diff
                current_env = {e['name']: e['value'] for e in container.get('environment', [])}
                latest_env = {e['name']: e['value'] for e in latest_container.get('environment', [])}

                added_vars = set(latest_env.keys()) - set(current_env.keys())
                removed_vars = set(current_env.keys()) - set(latest_env.keys())
                changed_vars = [k for k in current_env if k in latest_env and current_env[k] != latest_env[k]]

                if added_vars:
                    diff['changes'].append({
                        'field': 'env_added',
                        'label': 'Env Added',
                        'current': '-',
                        'latest': ', '.join(sorted(added_vars)[:5]) + ('...' if len(added_vars) > 5 else '')
                    })
                if removed_vars:
                    diff['changes'].append({
                        'field': 'env_removed',
                        'label': 'Env Removed',
                        'current': ', '.join(sorted(removed_vars)[:5]) + ('...' if len(removed_vars) > 5 else ''),
                        'latest': '-'
                    })
                if changed_vars:
                    diff['changes'].append({
                        'field': 'env_changed',
                        'label': 'Env Changed',
                        'current': str(len(changed_vars)),
                        'latest': ', '.join(sorted(changed_vars)[:5]) + ('...' if len(changed_vars) > 5 else '')
                    })

                # Secrets diff
                current_secrets = {s['name'] for s in container.get('secrets', [])}
                latest_secrets = {s['name'] for s in latest_container.get('secrets', [])}

                if current_secrets != latest_secrets:
                    added_secrets = latest_secrets - current_secrets
                    removed_secrets = current_secrets - latest_secrets
                    if added_secrets or removed_secrets:
                        diff['changes'].append({
                            'field': 'secrets',
                            'label': 'Secrets',
                            'current': f"{len(current_secrets)} secrets",
                            'latest': f"{len(latest_secrets)} secrets (+{len(added_secrets)}/-{len(removed_secrets)})"
                        })

                if diff['changes']:
                    latest_diff = diff
    except Exception as e:
        print(f"Error computing task def diff: {e}")

    return {
        'environment': env,
        'service': service,
        'serviceName': service_name,
        'clusterName': cluster_name,
        'status': svc['status'],
        'desiredCount': svc['desiredCount'],
        'runningCount': svc['runningCount'],
        'pendingCount': svc['pendingCount'],
        'taskDefinition': {
            'family': task_def['family'],
            'revision': task_def['revision'],
            'cpu': int(task_def['cpu']),
            'memory': int(task_def['memory']),
            'image': image,
            'latestDiff': latest_diff
        },
        'tasks': tasks,
        'deployments': [{
            'status': d['status'],
            'taskDefinition': d['taskDefinition'].split('/')[-1],
            'desiredCount': d['desiredCount'],
            'runningCount': d['runningCount'],
            'createdAt': d['createdAt'].isoformat() if d.get('createdAt') else None,
            'updatedAt': d['updatedAt'].isoformat() if d.get('updatedAt') else None
        } for d in svc['deployments']],
        'consoleUrl': build_sso_console_url(
            account_id,
            f"https://{REGION}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}?region={REGION}"
        ),
        'accountId': account_id
    }


def get_task_details(env: str, service: str, task_id: str) -> dict:
    """Get detailed task information including env vars, logs, and ECS Exec URL"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    cluster_name = f"{PROJECT_NAME}-{env}-cluster"
    service_name = f"{PROJECT_NAME}-{env}-{service}"
    task_family = f"{PROJECT_NAME}-{env}-{service}"

    ecs = get_cross_account_client('ecs', account_id)
    logs = get_cross_account_client('logs', account_id)

    # Get task details
    try:
        task_arn = f"arn:aws:ecs:{REGION}:{account_id}:task/{cluster_name}/{task_id}"
        task_response = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=[task_arn],
            include=['TAGS']
        )

        if not task_response.get('tasks'):
            return {'error': f'Task not found: {task_id}'}

        task = task_response['tasks'][0]
        task_def_arn = task['taskDefinitionArn']

        # Get task definition for env vars
        task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)['taskDefinition']
        container = task_def['containerDefinitions'][0]

        # Build environment variables list (filter secrets)
        env_vars = []
        for e in container.get('environment', []):
            name = e.get('name', '')
            value = e.get('value', '')
            # Mask sensitive values
            if any(secret in name.upper() for secret in ['SECRET', 'PASSWORD', 'KEY', 'TOKEN', 'CREDENTIAL']):
                value = '***MASKED***'
            env_vars.append({'name': name, 'value': value})

        # Get secrets references (from Secrets Manager/SSM)
        secrets_refs = []
        for s in container.get('secrets', []):
            secrets_refs.append({
                'name': s.get('name'),
                'valueFrom': s.get('valueFrom', '').split(':')[-1][:30] + '...' if len(s.get('valueFrom', '')) > 30 else s.get('valueFrom', '')
            })

        # Get AZ and subnet from ENI
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

        # Get container info
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
                    'memory': c.get('memory'),
                    'memoryReservation': c.get('memoryReservation'),
                    'exitCode': c.get('exitCode'),
                    'reason': c.get('reason'),
                    'networkBindings': c.get('networkBindings', []),
                    'networkInterfaces': c.get('networkInterfaces', [])
                }
                break

        # Get logs for this specific task
        # Log group format: /ecs/{PROJECT_NAME}-{env}/{service}
        log_group = f"/ecs/{PROJECT_NAME}-{env}/{service}"
        # Log stream format for awslogs: {prefix}/{container_name}/{task_id}
        log_stream = f"ecs/{service}/{task_id}"

        task_logs = []
        try:
            log_events = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                limit=50,
                startFromHead=False
            )
            for event in log_events.get('events', []):
                task_logs.append({
                    'timestamp': datetime.utcfromtimestamp(event['timestamp'] / 1000).isoformat() + 'Z',
                    'message': event['message'][:500]  # Truncate long messages
                })
        except logs.exceptions.ResourceNotFoundException:
            task_logs = [{'error': f'Log stream not found: {log_stream}'}]
        except Exception as e:
            task_logs = [{'error': f'Failed to get logs: {str(e)}'}]

        # Build console URLs
        task_console_url = build_sso_console_url(
            account_id,
            f"https://{REGION}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/tasks/{task_id}?region={REGION}"
        )

        # ECS Exec URL (new feature)
        ecs_exec_url = build_sso_console_url(
            account_id,
            f"https://{REGION}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/tasks/{task_id}/exec?region={REGION}"
        )

        logs_console_url = build_sso_console_url(
            account_id,
            f"https://{REGION}.console.aws.amazon.com/cloudwatch/home?region={REGION}#logsV2:log-groups/log-group/{log_group.replace('/', '$252F')}/log-events/{log_stream.replace('/', '$252F')}"
        )

        # Determine task status details
        current_revision = task_def_arn.split(':')[-1]

        return {
            'taskId': task_id,
            'taskArn': task_arn,
            'service': service,
            'serviceName': service_name,
            'cluster': cluster_name,
            'status': task.get('lastStatus'),
            'desiredStatus': task.get('desiredStatus'),
            'health': task.get('healthStatus', 'UNKNOWN'),
            'revision': current_revision,
            'taskDefinitionArn': task_def_arn,
            'startedAt': task.get('startedAt', '').isoformat() if task.get('startedAt') else None,
            'stoppedAt': task.get('stoppedAt', '').isoformat() if task.get('stoppedAt') else None,
            'stoppedReason': task.get('stoppedReason'),
            'stopCode': task.get('stopCode'),
            'connectivity': task.get('connectivity'),
            'connectivityAt': task.get('connectivityAt', '').isoformat() if task.get('connectivityAt') else None,
            'pullStartedAt': task.get('pullStartedAt', '').isoformat() if task.get('pullStartedAt') else None,
            'pullStoppedAt': task.get('pullStoppedAt', '').isoformat() if task.get('pullStoppedAt') else None,
            'launchType': task.get('launchType'),
            'platformVersion': task.get('platformVersion'),
            'platformFamily': task.get('platformFamily'),
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
            'enableExecuteCommand': task.get('enableExecuteCommand', False),
            'consoleUrls': {
                'task': task_console_url,
                'ecsExec': ecs_exec_url,
                'logs': logs_console_url,
                'service': build_sso_console_url(
                    account_id,
                    f"https://{REGION}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}?region={REGION}"
                )
            },
            'accountId': account_id,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {'error': f'Failed to get task details: {str(e)}'}


def get_service_details(env: str, service: str) -> dict:
    """Get detailed service information including task definitions, env vars, and logs"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    cluster_name = f"{PROJECT_NAME}-{env}-cluster"
    service_name = f"{PROJECT_NAME}-{env}-{service}"
    task_family = f"{PROJECT_NAME}-{env}-{service}"
    secret_name = f"{PROJECT_NAME}/{env}/{service}"

    ecs = get_cross_account_client('ecs', account_id)
    logs = get_cross_account_client('logs', account_id)

    # Get service info
    services = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )

    if not services['services']:
        return {'error': f'Service not found: {service_name}'}

    svc = services['services'][0]

    # Extract ECS service events (for rollback detection)
    ecs_events = []
    for event in svc.get('events', [])[:10]:  # Last 10 events
        ecs_events.append({
            'id': event.get('id'),
            'createdAt': event['createdAt'].isoformat() if event.get('createdAt') else None,
            'message': event.get('message', '')
        })

    # Detect rollback from events - but check if a successful deployment happened after
    last_rollback_event = next((e for e in ecs_events if 'rolling back' in e.get('message', '').lower()), None)
    last_steady_event = next((e for e in ecs_events if 'reached a steady state' in e.get('message', '').lower()), None)

    # Only consider rollback active if it's more recent than the last successful deployment
    is_rolling_back = False
    if last_rollback_event:
        if last_steady_event:
            # Compare timestamps - events are sorted by time desc, so compare index or timestamps
            rollback_time = last_rollback_event.get('createdAt', '')
            steady_time = last_steady_event.get('createdAt', '')
            # If rollback is more recent than steady state, it's still rolling back
            is_rolling_back = rollback_time > steady_time
        else:
            # No steady state event found, rollback is active
            is_rolling_back = True

    # Get current task definition (used by service)
    current_task_def = ecs.describe_task_definition(
        taskDefinition=svc['taskDefinition']
    )['taskDefinition']

    # Get latest task definition (by family)
    try:
        latest_task_def = ecs.describe_task_definition(
            taskDefinition=task_family
        )['taskDefinition']
    except:
        latest_task_def = current_task_def

    # Compute diff between current and latest if different
    def compute_task_def_diff(current, latest):
        if current['revision'] == latest['revision']:
            return None

        current_container = current['containerDefinitions'][0]
        latest_container = latest['containerDefinitions'][0]

        changes = []

        # Image diff
        current_image = current_container['image']
        latest_image = latest_container['image']
        if current_image != latest_image:
            current_tag = current_image.split(':')[-1] if ':' in current_image else 'latest'
            latest_tag = latest_image.split(':')[-1] if ':' in latest_image else 'latest'
            changes.append({
                'field': 'image',
                'label': 'Image',
                'current': current_tag[:12],
                'latest': latest_tag[:12]
            })

        # CPU diff
        if int(current['cpu']) != int(latest['cpu']):
            changes.append({
                'field': 'cpu',
                'label': 'CPU',
                'current': f"{int(current['cpu'])} units",
                'latest': f"{int(latest['cpu'])} units"
            })

        # Memory diff
        if int(current['memory']) != int(latest['memory']):
            changes.append({
                'field': 'memory',
                'label': 'Memory',
                'current': f"{int(current['memory'])} MB",
                'latest': f"{int(latest['memory'])} MB"
            })

        # Environment variables diff
        current_env = {e['name']: e['value'] for e in current_container.get('environment', [])}
        latest_env = {e['name']: e['value'] for e in latest_container.get('environment', [])}

        added_vars = set(latest_env.keys()) - set(current_env.keys())
        removed_vars = set(current_env.keys()) - set(latest_env.keys())
        changed_vars = [k for k in current_env if k in latest_env and current_env[k] != latest_env[k]]

        if added_vars:
            changes.append({
                'field': 'env_added',
                'label': 'Env Added',
                'current': '-',
                'latest': ', '.join(sorted(added_vars)[:5]) + ('...' if len(added_vars) > 5 else '')
            })
        if removed_vars:
            changes.append({
                'field': 'env_removed',
                'label': 'Env Removed',
                'current': ', '.join(sorted(removed_vars)[:5]) + ('...' if len(removed_vars) > 5 else ''),
                'latest': '-'
            })
        if changed_vars:
            changes.append({
                'field': 'env_changed',
                'label': 'Env Changed',
                'current': str(len(changed_vars)),
                'latest': ', '.join(sorted(changed_vars)[:5]) + ('...' if len(changed_vars) > 5 else '')
            })

        # Secrets diff
        current_secrets = {s['name'] for s in current_container.get('secrets', [])}
        latest_secrets = {s['name'] for s in latest_container.get('secrets', [])}

        if current_secrets != latest_secrets:
            added_secrets = latest_secrets - current_secrets
            removed_secrets = current_secrets - latest_secrets
            if added_secrets or removed_secrets:
                changes.append({
                    'field': 'secrets',
                    'label': 'Secrets',
                    'current': f"{len(current_secrets)} secrets",
                    'latest': f"{len(latest_secrets)} secrets (+{len(added_secrets)}/-{len(removed_secrets)})"
                })

        if changes:
            return {
                'currentRevision': current['revision'],
                'latestRevision': latest['revision'],
                'changes': changes
            }
        return None

    task_def_diff = compute_task_def_diff(current_task_def, latest_task_def)

    def extract_env_vars(task_def):
        """Extract environment variables from task definition"""
        container = task_def['containerDefinitions'][0]
        env_vars = []

        # Regular environment variables
        for e in container.get('environment', []):
            env_vars.append({
                'name': e['name'],
                'value': e['value'],
                'type': 'plain'
            })

        # Secrets (from Secrets Manager or SSM)
        for s in container.get('secrets', []):
            env_vars.append({
                'name': s['name'],
                'valueFrom': s['valueFrom'],
                'type': 'secret'
            })

        return sorted(env_vars, key=lambda x: x['name'])

    def format_task_def(task_def, is_current=False, latest_diff=None):
        """Format task definition info"""
        container = task_def['containerDefinitions'][0]
        result = {
            'arn': task_def['taskDefinitionArn'],
            'family': task_def['family'],
            'revision': task_def['revision'],
            'cpu': int(task_def['cpu']),
            'memory': int(task_def['memory']),
            'image': container['image'],
            'imageTag': container['image'].split(':')[-1] if ':' in container['image'] else 'latest',
            'environmentVariables': extract_env_vars(task_def),
            'isCurrent': is_current,
            'consoleUrl': build_sso_console_url(
                account_id,
                f"https://{REGION}.console.aws.amazon.com/ecs/v2/task-definitions/{task_def['family']}/{task_def['revision']}?region={REGION}"
            )
        }
        if latest_diff:
            result['latestDiff'] = latest_diff
        return result

    # Get deployments with timestamps
    deployments = []
    for d in svc['deployments']:
        deployments.append({
            'status': d['status'],
            'taskDefinition': d['taskDefinition'].split('/')[-1],
            'desiredCount': d['desiredCount'],
            'runningCount': d['runningCount'],
            'pendingCount': d['pendingCount'],
            'createdAt': d['createdAt'].isoformat() if d.get('createdAt') else None,
            'updatedAt': d['updatedAt'].isoformat() if d.get('updatedAt') else None,
            'rolloutState': d.get('rolloutState', 'UNKNOWN'),
            'rolloutStateReason': d.get('rolloutStateReason', '')
        })

    # Get last deployment time (most recent PRIMARY deployment)
    last_deploy = None
    for d in svc['deployments']:
        if d['status'] == 'PRIMARY':
            last_deploy = d['updatedAt'].isoformat() if d.get('updatedAt') else d['createdAt'].isoformat() if d.get('createdAt') else None
            break

    # Get recent logs - log group format: /ecs/myapp-staging/backend
    log_group = f"/ecs/{PROJECT_NAME}-{env}/{service}"
    recent_logs = []
    try:
        # Get log streams sorted by last event time
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=3
        )

        # Get logs from the most recent streams
        for stream in streams.get('logStreams', [])[:2]:
            events = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=stream['logStreamName'],
                limit=50,
                startFromHead=False
            )
            for event in events.get('events', []):
                recent_logs.append({
                    'timestamp': datetime.utcfromtimestamp(event['timestamp'] / 1000).isoformat() + 'Z',
                    'message': event['message'][:500],  # Truncate long messages
                    'stream': stream['logStreamName'].split('/')[-1][:12]  # Task ID prefix
                })

        # Sort by timestamp chronologically (oldest first, newest at bottom for tail behavior)
        recent_logs = sorted(recent_logs, key=lambda x: x['timestamp'])[-100:]
    except logs.exceptions.ResourceNotFoundException:
        recent_logs = []
    except Exception as e:
        recent_logs = [{'error': str(e)}]

    # Build secret URLs
    secret_console_url = build_sso_console_url(
        account_id,
        f"https://{REGION}.console.aws.amazon.com/secretsmanager/secret?name={quote(secret_name, safe='')}&region={REGION}"
    )

    # Logs console URL - use ECS service logs view instead of CloudWatch directly
    logs_console_url = build_sso_console_url(
        account_id,
        f"https://{REGION}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}/logs?region={REGION}"
    )

    # Get deploy pipeline info with logs if in progress
    deploy_pipeline = get_deploy_pipeline_info(env, service, include_logs=True)

    # Determine overall deployment state
    primary_deployment = next((d for d in deployments if d['status'] == 'PRIMARY'), None)
    deployment_state = 'stable'
    if is_rolling_back:
        deployment_state = 'rolling_back'
    elif any(d['rolloutState'] == 'IN_PROGRESS' for d in deployments):
        deployment_state = 'in_progress'
    elif primary_deployment and primary_deployment.get('rolloutState') == 'FAILED':
        deployment_state = 'failed'

    return {
        'environment': env,
        'service': service,
        'serviceName': service_name,
        'clusterName': cluster_name,
        'accountId': account_id,
        'status': svc['status'],
        'desiredCount': svc['desiredCount'],
        'runningCount': svc['runningCount'],
        'lastDeployment': last_deploy,
        'deploymentState': deployment_state,
        'isRollingBack': is_rolling_back,
        'lastRollbackEvent': last_rollback_event,
        'ecsEvents': ecs_events,
        'currentTaskDefinition': format_task_def(current_task_def, is_current=True, latest_diff=task_def_diff),
        'latestTaskDefinition': format_task_def(latest_task_def, is_current=False),
        'isLatest': current_task_def['revision'] == latest_task_def['revision'],
        'ecsDeployments': deployments,
        'deployPipeline': deploy_pipeline if 'error' not in deploy_pipeline else None,
        'recentLogs': recent_logs,
        'secretName': secret_name,
        'consoleUrls': {
            'service': build_sso_console_url(
                account_id,
                f"https://{REGION}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}?region={REGION}"
            ),
            'secret': secret_console_url,
            'logs': logs_console_url,
            'taskDefinitions': build_sso_console_url(
                account_id,
                f"https://{REGION}.console.aws.amazon.com/ecs/v2/task-definitions/{task_family}?region={REGION}"
            )
        }
    }


def get_service_logs(env: str, service: str) -> dict:
    """Get service logs only (lightweight endpoint for tailing)"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    log_group = f"/ecs/{PROJECT_NAME}-{env}/{service}"

    logs = get_cross_account_client('logs', account_id)

    recent_logs = []
    try:
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=3
        )

        # Get logs from the most recent streams
        for stream in streams.get('logStreams', [])[:2]:
            events = logs.get_log_events(
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

        # Sort by timestamp chronologically (oldest first, newest at bottom for tail behavior)
        recent_logs = sorted(recent_logs, key=lambda x: x['timestamp'])[-100:]
    except logs.exceptions.ResourceNotFoundException:
        recent_logs = []
    except Exception as e:
        return {'error': str(e), 'logs': []}

    return {
        'environment': env,
        'service': service,
        'logs': recent_logs
    }


def get_pipeline_info(pipeline_type: str, service: str, env: str = None) -> dict:
    """Get CodePipeline information"""
    codepipeline = boto3.client('codepipeline', region_name=REGION)
    codebuild = boto3.client('codebuild', region_name=REGION)
    logs_client = boto3.client('logs', region_name=REGION)

    # GitHub repository info (from CodeStar connection)
    GITHUB_ORG = 'example-org'
    GITHUB_REPO = f'{PROJECT_NAME}-{service}'

    if pipeline_type == 'build':
        pipeline_name = f"{PROJECT_NAME}-build-{service}"
    else:
        pipeline_name = f"{PROJECT_NAME}-deploy-{service}-{env}"

    try:
        # Get pipeline state
        state = codepipeline.get_pipeline_state(name=pipeline_name)

        # Get last execution
        executions = codepipeline.list_pipeline_executions(
            pipelineName=pipeline_name,
            maxResults=5
        )

        stages = []
        for stage in state.get('stageStates', []):
            stages.append({
                'name': stage['stageName'],
                'status': stage.get('latestExecution', {}).get('status', 'Unknown')
            })

        # Format executions with console URLs and commit info
        execution_list = []
        for exec_summary in executions.get('pipelineExecutionSummaries', []):
            exec_id = exec_summary['pipelineExecutionId']
            exec_data = {
                'executionId': exec_id,
                'status': exec_summary['status'],
                'startTime': exec_summary.get('startTime', '').isoformat() if exec_summary.get('startTime') else None,
                'lastUpdateTime': exec_summary.get('lastUpdateTime', '').isoformat() if exec_summary.get('lastUpdateTime') else None,
                'consoleUrl': build_sso_console_url(
                    SHARED_SERVICES_ACCOUNT,
                    f"https://{REGION}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline_name}/executions/{exec_id}/timeline?region={REGION}"
                )
            }

            # Get source revision for build pipeline
            if pipeline_type == 'build' and exec_summary.get('sourceRevisions'):
                rev = exec_summary['sourceRevisions'][0]
                full_commit = rev.get('revisionId', '')
                exec_data['commit'] = full_commit[:8]
                exec_data['commitFull'] = full_commit
                # Direct GitHub link instead of CodePipeline URL
                exec_data['commitUrl'] = f"https://github.com/{GITHUB_ORG}/{GITHUB_REPO}/commit/{full_commit}"
                try:
                    summary = json.loads(rev.get('revisionSummary', '{}'))
                    exec_data['commitMessage'] = summary.get('CommitMessage', '')
                except:
                    pass

            execution_list.append(exec_data)

        last_execution = execution_list[0] if execution_list else None

        # Fetch build logs for build pipelines
        build_logs = []
        if pipeline_type == 'build':
            try:
                # CodeBuild project naming: {project}-build-{service}-arm64
                build_project = f"{PROJECT_NAME}-build-{service}-arm64"
                builds = codebuild.list_builds_for_project(
                    projectName=build_project,
                    sortOrder='DESCENDING'
                )
                if builds.get('ids'):
                    latest_build = codebuild.batch_get_builds(ids=[builds['ids'][0]])['builds'][0]
                    log_group = latest_build.get('logs', {}).get('groupName')
                    log_stream = latest_build.get('logs', {}).get('streamName')

                    if log_group and log_stream:
                        log_events = logs_client.get_log_events(
                            logGroupName=log_group,
                            logStreamName=log_stream,
                            limit=100,
                            startFromHead=False
                        )
                        for event in log_events.get('events', []):
                            build_logs.append({
                                'timestamp': datetime.utcfromtimestamp(event['timestamp'] / 1000).isoformat() + 'Z',
                                'message': event['message'].strip()
                            })
            except Exception as e:
                build_logs = [{'timestamp': datetime.utcnow().isoformat() + 'Z', 'message': f'Error fetching logs: {str(e)}'}]

        return {
            'pipelineName': pipeline_name,
            'pipelineType': pipeline_type,
            'service': service,
            'environment': env,
            'version': state.get('pipelineVersion'),
            'stages': stages,
            'lastExecution': last_execution,
            'executions': execution_list,
            'buildLogs': build_logs if build_logs else None,
            'consoleUrl': build_sso_console_url(
                SHARED_SERVICES_ACCOUNT,
                f"https://{REGION}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline_name}/view?region={REGION}"
            )
        }
    except codepipeline.exceptions.PipelineNotFoundException:
        return {'error': f'Pipeline not found: {pipeline_name}'}


def get_ecr_images(service: str) -> dict:
    """Get ECR image information"""
    ecr = boto3.client('ecr', region_name=REGION)
    repo_name = f"{PROJECT_NAME}-{service}"

    try:
        # Fetch all images with pagination to ensure we get the most recent
        all_images = []
        paginator = ecr.get_paginator('describe_images')
        for page in paginator.paginate(repositoryName=repo_name):
            all_images.extend(page['imageDetails'])

        # Sort by push date descending and take top 10
        sorted_images = sorted(all_images, key=lambda x: x.get('imagePushedAt', datetime.min), reverse=True)[:10]

        image_list = []
        for img in sorted_images:
            image_list.append({
                'digest': img['imageDigest'],
                'tags': img.get('imageTags', []),
                'pushedAt': img['imagePushedAt'].isoformat() if img.get('imagePushedAt') else None,
                'sizeBytes': img.get('imageSizeInBytes', 0),
                'sizeMB': round(img.get('imageSizeInBytes', 0) / 1024 / 1024, 2)
            })

        return {
            'repositoryName': repo_name,
            'images': image_list,
            'consoleUrl': build_sso_console_url(
                SHARED_SERVICES_ACCOUNT,
                f"https://{REGION}.console.aws.amazon.com/ecr/repositories/private/{SHARED_SERVICES_ACCOUNT}/{repo_name}?region={REGION}"
            )
        }
    except ecr.exceptions.RepositoryNotFoundException:
        return {'error': f'Repository not found: {repo_name}'}


def get_metrics(env: str, service: str) -> dict:
    """Get CloudWatch metrics for a service"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    cluster_name = f"{PROJECT_NAME}-{env}-cluster"
    service_name = f"{PROJECT_NAME}-{env}-{service}"

    cloudwatch = get_cross_account_client('cloudwatch', account_id)

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
        'consoleUrl': build_sso_console_url(
            account_id,
            f"https://{REGION}.console.aws.amazon.com/cloudwatch/home?region={REGION}#metricsV2:graph=~();query=~'*7bAWS*2fECS*2cClusterName*2cServiceName*7d*20{service_name}"
        ),
        'accountId': account_id
    }


def get_infrastructure_info(env: str, discovery_tags: dict = None, services: list = None, domain_config: dict = None, databases: list = None, caches: list = None) -> dict:
    """
    Get infrastructure topology for an environment (CloudFront, ALB, S3, ECS, RDS, Redis, Network)

    Args:
        env: Environment name (staging, preprod, production)
        discovery_tags: Dict of {tag_key: tag_value} to filter resources (e.g., {"Project": "myapp", "DevTeam": "myteam"})
        services: List of service names to look for (e.g., ["backend", "frontend", "cms"])
        domain_config: Dict with domain patterns (e.g., {"pattern": "...", "domains": {"frontend": "fr", ...}})
        databases: List of database types to look for (e.g., ["postgres", "mysql"])
        caches: List of cache types to look for (e.g., ["redis"])
    """
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    # Default values for backwards compatibility
    services = services or config.get('services', ['backend', 'frontend', 'cms'])
    discovery_tags = discovery_tags or {}
    databases = databases if databases is not None else ['postgres']
    caches = caches if caches is not None else ['redis']

    account_id = config['account_id']
    elbv2 = get_cross_account_client('elbv2', account_id)
    cloudfront = get_cross_account_client('cloudfront', account_id)
    s3 = get_cross_account_client('s3', account_id)
    ecs = get_cross_account_client('ecs', account_id)
    rds = get_cross_account_client('rds', account_id)
    elasticache = get_cross_account_client('elasticache', account_id)
    ec2 = get_cross_account_client('ec2', account_id)

    alb_name = f"{PROJECT_NAME}-{env}-alb"
    cluster_name = f"{PROJECT_NAME}-{env}-cluster"

    # Domain patterns - use config or fallback to defaults
    if domain_config and domain_config.get('domains'):
        domains_map = domain_config.get('domains', {})
        domain_suffix = f"{env}.{PROJECT_NAME}.kamorion.cloud"
        result_domains = {}
        for svc, prefix in domains_map.items():
            result_domains[svc] = f"https://{prefix}.{domain_suffix}"
    else:
        # Fallback to hardcoded patterns for backwards compatibility
        domain_suffix = f"{env}.{PROJECT_NAME}.kamorion.cloud"
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
        'network': None
    }

    # Track S3 origins from CloudFront for filtering
    cloudfront_s3_origins = set()

    # Get CloudFront distribution
    try:
        distributions = cloudfront.list_distributions()
        for dist in distributions.get('DistributionList', {}).get('Items', []):
            aliases = dist.get('Aliases', {}).get('Items', [])
            # Find the distribution for this env
            if any(domain_suffix in alias for alias in aliases):
                dist_id = dist['Id']
                result['cloudfront'] = {
                    'id': dist_id,
                    'domainName': dist['DomainName'],
                    'aliases': aliases,
                    'status': dist['Status'],
                    'enabled': dist['Enabled'],
                    'origins': [],
                    'cacheBehaviors': [],
                    'webAclId': None,
                    'consoleUrl': build_sso_console_url(
                        account_id,
                        f"https://console.aws.amazon.com/cloudfront/v4/home#/distributions/{dist_id}"
                    )
                }
                # Get origins
                for origin in dist.get('Origins', {}).get('Items', []):
                    origin_domain = origin['DomainName']
                    origin_type = 'alb' if 'elb.amazonaws.com' in origin_domain else 's3' if 's3.' in origin_domain else 'custom'
                    result['cloudfront']['origins'].append({
                        'id': origin['Id'],
                        'domainName': origin_domain,
                        'type': origin_type,
                        'path': origin.get('OriginPath', '')
                    })
                    # Track S3 bucket names from origins
                    if origin_type == 's3':
                        # Extract bucket name from domain like "bucket-name.s3.eu-west-3.amazonaws.com"
                        bucket_name = origin_domain.split('.s3.')[0]
                        cloudfront_s3_origins.add(bucket_name)

                # Get full distribution config for WAF and behaviors
                try:
                    dist_config = cloudfront.get_distribution(Id=dist_id)
                    dist_detail = dist_config.get('Distribution', {}).get('DistributionConfig', {})

                    # WAF Web ACL
                    web_acl = dist_detail.get('WebACLId', '')
                    if web_acl:
                        result['cloudfront']['webAclId'] = web_acl

                    # Default cache behavior
                    default_behavior = dist_detail.get('DefaultCacheBehavior', {})
                    if default_behavior:
                        result['cloudfront']['cacheBehaviors'].append({
                            'pathPattern': 'Default (*)',
                            'targetOriginId': default_behavior.get('TargetOriginId'),
                            'viewerProtocolPolicy': default_behavior.get('ViewerProtocolPolicy'),
                            'defaultTTL': default_behavior.get('DefaultTTL', 0),
                            'compress': default_behavior.get('Compress', False),
                            'lambdaEdge': len(default_behavior.get('LambdaFunctionAssociations', {}).get('Items', [])) > 0
                        })

                    # Additional cache behaviors
                    for behavior in dist_detail.get('CacheBehaviors', {}).get('Items', []):
                        result['cloudfront']['cacheBehaviors'].append({
                            'pathPattern': behavior.get('PathPattern'),
                            'targetOriginId': behavior.get('TargetOriginId'),
                            'viewerProtocolPolicy': behavior.get('ViewerProtocolPolicy'),
                            'defaultTTL': behavior.get('DefaultTTL', 0),
                            'compress': behavior.get('Compress', False),
                            'lambdaEdge': len(behavior.get('LambdaFunctionAssociations', {}).get('Items', [])) > 0
                        })
                except Exception:
                    pass  # If get_distribution fails, we still have basic info
                break
    except Exception as e:
        result['cloudfront'] = {'error': str(e)}

    # Get ALB info
    try:
        albs = elbv2.describe_load_balancers()
        for alb in albs.get('LoadBalancers', []):
            if alb['LoadBalancerName'] == alb_name:
                alb_arn = alb['LoadBalancerArn']
                result['alb'] = {
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
                        account_id,
                        f"https://{REGION}.console.aws.amazon.com/ec2/home?region={REGION}#LoadBalancer:loadBalancerArn={quote(alb_arn, safe='')}"
                    )
                }

                # Get listeners
                listeners = elbv2.describe_listeners(LoadBalancerArn=alb_arn)
                for listener in listeners.get('Listeners', []):
                    listener_arn = listener['ListenerArn']
                    result['alb']['listeners'].append({
                        'arn': listener_arn,
                        'port': listener['Port'],
                        'protocol': listener['Protocol']
                    })

                    # Get rules for HTTPS listener
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

                            result['alb']['rules'].append({
                                'priority': rule['Priority'],
                                'conditions': conditions,
                                'targetGroupArn': target_group_arn
                            })

                # Get target groups
                tgs = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
                for tg in tgs.get('TargetGroups', []):
                    tg_arn = tg['TargetGroupArn']
                    tg_name = tg['TargetGroupName']

                    # Get health status
                    health = elbv2.describe_target_health(TargetGroupArn=tg_arn)
                    healthy_count = sum(1 for t in health.get('TargetHealthDescriptions', []) if t['TargetHealth']['State'] == 'healthy')
                    unhealthy_count = sum(1 for t in health.get('TargetHealthDescriptions', []) if t['TargetHealth']['State'] == 'unhealthy')
                    total = len(health.get('TargetHealthDescriptions', []))

                    # Determine service name from target group name
                    service_name = None
                    for svc in services:
                        if svc in tg_name:
                            service_name = svc
                            break

                    result['alb']['targetGroups'].append({
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
                            account_id,
                            f"https://{REGION}.console.aws.amazon.com/ec2/home?region={REGION}#TargetGroup:targetGroupArn={quote(tg_arn, safe='')}"
                        )
                    })
                break
    except Exception as e:
        result['alb'] = {'error': str(e)}

    # Get S3 buckets (only those served by CloudFront)
    try:
        buckets = s3.list_buckets()
        for bucket in buckets.get('Buckets', []):
            bucket_name = bucket['Name']
            # Only show buckets that are CloudFront origins
            if bucket_name in cloudfront_s3_origins:
                bucket_type = 'frontend' if 'frontend' in bucket_name else 'cms-public' if 'cms-public' in bucket_name else 'assets' if 'assets' in bucket_name else 'other'
                result['s3Buckets'].append({
                    'name': bucket_name,
                    'type': bucket_type,
                    'createdAt': bucket['CreationDate'].isoformat() if bucket.get('CreationDate') else None,
                    'consoleUrl': build_sso_console_url(
                        account_id,
                        f"https://s3.console.aws.amazon.com/s3/buckets/{bucket_name}?region={REGION}"
                    )
                })
    except Exception as e:
        result['s3Buckets'] = [{'error': str(e)}]

    # Get ECS services with detailed task info for AZ visualization
    try:
        cluster_arn = f"arn:aws:ecs:{REGION}:{account_id}:cluster/{cluster_name}"
        for service in services:
            service_name = f"{PROJECT_NAME}-{env}-{service}"
            try:
                svc = ecs.describe_services(cluster=cluster_name, services=[service_name])
                if svc['services']:
                    s = svc['services'][0]
                    current_revision = s['taskDefinition'].split(':')[-1]

                    # Get all tasks (running + pending for rolling update visibility)
                    all_task_arns = []
                    for status in ['RUNNING', 'PENDING']:
                        task_arns = ecs.list_tasks(
                            cluster=cluster_name,
                            serviceName=service_name,
                            desiredStatus=status
                        ).get('taskArns', [])
                        all_task_arns.extend(task_arns)

                    # Get task details with AZ info
                    tasks = []
                    tasks_by_az = {}
                    if all_task_arns:
                        task_details = ecs.describe_tasks(cluster=cluster_name, tasks=all_task_arns)['tasks']
                        for task in task_details:
                            task_revision = task['taskDefinitionArn'].split(':')[-1]
                            az = None
                            subnet_id = None

                            # Get AZ from ENI attachment
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
                                'taskId': task['taskArn'].split('/')[-1][:8],  # Short ID
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

                            # Group by AZ
                            if az:
                                if az not in tasks_by_az:
                                    tasks_by_az[az] = []
                                tasks_by_az[az].append(task_info)

                    # Get deployments info for rolling update status
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

                    # Determine if rolling update is in progress
                    is_rolling = len(deployments) > 1 or any(d['status'] == 'ACTIVE' for d in deployments if d['status'] != 'PRIMARY')

                    result['services'][service] = {
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
                            account_id,
                            f"https://{REGION}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}?region={REGION}"
                        )
                    }
            except Exception as e:
                result['services'][service] = {'error': str(e)}
    except Exception as e:
        result['services'] = {'error': str(e)}

    # Get RDS database info (filtered by discovery_tags and database type)
    try:
        db_instances = rds.describe_db_instances()
        for db in db_instances.get('DBInstances', []):
            db_id = db['DBInstanceIdentifier']
            db_engine = db['Engine'].lower()

            # Check if this database type is in our requested list
            # Map engine names: postgresql -> postgres, mysql -> mysql
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

            # Check if discovery_tags match (or fallback to name-based matching for backwards compatibility)
            tags_match = matches_discovery_tags(db_tags, discovery_tags) if discovery_tags else (PROJECT_NAME in db_id and env in db_id)

            if tags_match:
                result['rds'] = {
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
                        account_id,
                        f"https://{REGION}.console.aws.amazon.com/rds/home?region={REGION}#database:id={db_id};is-cluster=false"
                    )
                }
                break
    except Exception as e:
        result['rds'] = {'error': str(e)}

    # Get ElastiCache Redis/Valkey info (filtered by discovery_tags and cache type)
    # Skip if no caches are requested for this project
    if caches:
        try:
            clusters = elasticache.describe_cache_clusters(ShowCacheNodeInfo=True)
            for cluster in clusters.get('CacheClusters', []):
                cluster_id = cluster['CacheClusterId']
                cache_engine = cluster['Engine'].lower()

                # Check if this cache type is in our requested list
                # Map engine names: redis/valkey -> redis
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

                # Check if discovery_tags match (or fallback to name-based matching for backwards compatibility)
                tags_match = matches_discovery_tags(cache_tags, discovery_tags) if discovery_tags else (PROJECT_NAME in cluster_id and env in cluster_id)

                if not tags_match:
                    continue
                # Get replication group info for more details
                repl_group_id = cluster.get('ReplicationGroupId')
                repl_group_info = None
                if repl_group_id:
                    try:
                        repl_groups = elasticache.describe_replication_groups(ReplicationGroupId=repl_group_id)
                        if repl_groups.get('ReplicationGroups'):
                            repl_group_info = repl_groups['ReplicationGroups'][0]
                    except Exception:
                        pass

                cache_nodes = cluster.get('CacheNodes', [])
                endpoint = None
                if repl_group_info and repl_group_info.get('ConfigurationEndpoint'):
                    endpoint = repl_group_info['ConfigurationEndpoint']
                elif repl_group_info and repl_group_info.get('NodeGroups'):
                    primary_endpoint = repl_group_info['NodeGroups'][0].get('PrimaryEndpoint')
                    endpoint = primary_endpoint
                elif cache_nodes:
                    endpoint = cache_nodes[0].get('Endpoint')

                # Get node placement by AZ
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

                # Check for multi-AZ from replication group
                multi_az = False
                if repl_group_info:
                    multi_az = repl_group_info.get('MultiAZ', 'disabled') == 'enabled'
                    # Also check if there are nodes in multiple AZs
                    if not multi_az and len(nodes_by_az) > 1:
                        multi_az = True

                result['redis'] = {
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
                        account_id,
                        f"https://{REGION}.console.aws.amazon.com/elasticache/home?region={REGION}#/redis/{cluster_id}"
                    )
                }
                break
        except Exception as e:
            result['redis'] = {'error': str(e)}

    # Get VPC, Subnets, and NAT Gateway info
    try:
        vpc_name = f"{PROJECT_NAME}-{env}"

        # Find VPC by tag Name
        vpcs = ec2.describe_vpcs(
            Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}]
        )

        if vpcs.get('Vpcs'):
            vpc = vpcs['Vpcs'][0]
            vpc_id = vpc['VpcId']

            # Get all subnets for this VPC
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
                # Fallback: try to detect from name if Type tag not found
                if subnet_type == 'unknown' and subnet_name:
                    if 'private' in subnet_name.lower():
                        subnet_type = 'private'
                    elif 'public' in subnet_name.lower():
                        subnet_type = 'public'
                    elif 'database' in subnet_name.lower() or 'db' in subnet_name.lower():
                        subnet_type = 'database'

                if az not in subnets_by_az:
                    subnets_by_az[az] = []

                subnets_by_az[az].append({
                    'id': subnet['SubnetId'],
                    'name': subnet_name,
                    'cidr': subnet['CidrBlock'],
                    'type': subnet_type,
                    'availableIps': subnet['AvailableIpAddressCount']
                })

            # Get NAT Gateways
            nat_gateways = ec2.describe_nat_gateways(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'state', 'Values': ['available']}
                ]
            )

            nat_info = []
            for nat in nat_gateways.get('NatGateways', []):
                nat_name = ''
                for tag in nat.get('Tags', []):
                    if tag['Key'] == 'Name':
                        nat_name = tag['Value']
                        break

                public_ip = None
                for addr in nat.get('NatGatewayAddresses', []):
                    if addr.get('PublicIp'):
                        public_ip = addr['PublicIp']
                        break

                nat_info.append({
                    'id': nat['NatGatewayId'],
                    'name': nat_name,
                    'publicIp': public_ip,
                    'subnetId': nat['SubnetId'],
                    'az': nat.get('AvailabilityZone', next((s['AvailabilityZone'] for s in subnets_response.get('Subnets', []) if s['SubnetId'] == nat['SubnetId']), None)),
                    'state': nat['State'],
                    'consoleUrl': build_sso_console_url(
                        account_id,
                        f"https://{REGION}.console.aws.amazon.com/vpc/home?region={REGION}#NatGatewayDetails:natGatewayId={nat['NatGatewayId']}"
                    )
                })

            result['network'] = {
                'vpc': {
                    'id': vpc_id,
                    'name': vpc_name,
                    'cidr': vpc['CidrBlock'],
                    'state': vpc['State'],
                    'consoleUrl': build_sso_console_url(
                        account_id,
                        f"https://{REGION}.console.aws.amazon.com/vpc/home?region={REGION}#VpcDetails:VpcId={vpc_id}"
                    )
                },
                'availabilityZones': sorted(subnets_by_az.keys()),
                'subnets': subnets_by_az,
                'natGateways': nat_info,
                'egressIps': [nat['publicIp'] for nat in nat_info if nat.get('publicIp')]
            }
    except Exception as e:
        result['network'] = {'error': str(e)}

    return result


def get_deploy_pipeline_info(env: str, service: str, include_logs: bool = False) -> dict:
    """Get deployment pipeline information for a service in an environment"""
    codepipeline = boto3.client('codepipeline', region_name=REGION)
    codebuild = boto3.client('codebuild', region_name=REGION)
    logs_client = boto3.client('logs', region_name=REGION)
    pipeline_name = f"{PROJECT_NAME}-deploy-{service}-{env}"

    try:
        # Get pipeline state
        state = codepipeline.get_pipeline_state(name=pipeline_name)

        # Get last 5 executions
        executions = codepipeline.list_pipeline_executions(
            pipelineName=pipeline_name,
            maxResults=5
        )

        stages = []
        for stage in state.get('stageStates', []):
            stages.append({
                'name': stage['stageName'],
                'status': stage.get('latestExecution', {}).get('status', 'Unknown')
            })

        # Format all executions with console URLs
        execution_list = []
        for exec_summary in executions.get('pipelineExecutionSummaries', []):
            exec_id = exec_summary['pipelineExecutionId']
            execution_list.append({
                'id': exec_id,
                'status': exec_summary['status'],
                'startTime': exec_summary.get('startTime', '').isoformat() if exec_summary.get('startTime') else None,
                'lastUpdateTime': exec_summary.get('lastUpdateTime', '').isoformat() if exec_summary.get('lastUpdateTime') else None,
                'consoleUrl': build_sso_console_url(
                    SHARED_SERVICES_ACCOUNT,
                    f"https://{REGION}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline_name}/executions/{exec_id}/timeline?region={REGION}"
                )
            })

        last_execution = execution_list[0] if execution_list else None

        # If deployment is in progress, get CodeBuild logs
        build_logs = []
        if include_logs and last_execution and last_execution['status'] == 'InProgress':
            try:
                # Get the CodeBuild project name (deploy projects have -prepare suffix)
                build_project = f"{PROJECT_NAME}-deploy-{service}-{env}-prepare"

                # Get latest build
                builds = codebuild.list_builds_for_project(
                    projectName=build_project,
                    sortOrder='DESCENDING'
                )

                if builds.get('ids'):
                    build_info = codebuild.batch_get_builds(ids=[builds['ids'][0]])
                    if build_info.get('builds'):
                        build = build_info['builds'][0]
                        log_group = build.get('logs', {}).get('groupName')
                        log_stream = build.get('logs', {}).get('streamName')

                        if log_group and log_stream:
                            log_events = logs_client.get_log_events(
                                logGroupName=log_group,
                                logStreamName=log_stream,
                                limit=50,
                                startFromHead=False
                            )
                            for event in log_events.get('events', []):
                                build_logs.append({
                                    'timestamp': datetime.utcfromtimestamp(event['timestamp'] / 1000).isoformat() + 'Z',
                                    'message': event['message'].strip()
                                })
            except Exception as e:
                build_logs = [{'timestamp': datetime.utcnow().isoformat() + 'Z', 'message': f'Error fetching logs: {str(e)}'}]

        return {
            'pipelineName': pipeline_name,
            'environment': env,
            'service': service,
            'version': state.get('pipelineVersion'),
            'stages': stages,
            'lastExecution': last_execution,
            'executions': execution_list,
            'buildLogs': build_logs if build_logs else None,
            'consoleUrl': build_sso_console_url(
                SHARED_SERVICES_ACCOUNT,
                f"https://{REGION}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline_name}/view?region={REGION}"
            )
        }
    except codepipeline.exceptions.PipelineNotFoundException:
        return {'error': f'Pipeline not found: {pipeline_name}'}
    except Exception as e:
        return {'error': str(e)}


def get_env_services(env: str) -> dict:
    """Get services for a single environment only"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    result = {
        'accountId': config['account_id'],
        'services': {},
        'timestamp': datetime.utcnow().isoformat(),
        'config': {
            'ssoPortalUrl': SSO_PORTAL_URL,
            'region': REGION,
            'projectName': PROJECT_NAME
        }
    }

    for service in config['services']:
        try:
            info = get_service_info(env, service)
            if 'error' not in info:
                # Get deploy pipeline info
                deploy_pipeline = get_deploy_pipeline_info(env, service)

                result['services'][service] = {
                    'status': info['status'],
                    'health': 'HEALTHY' if info['runningCount'] == info['desiredCount'] else 'UNHEALTHY',
                    'runningCount': info['runningCount'],
                    'desiredCount': info['desiredCount'],
                    'taskDefinition': info['taskDefinition']['revision'],
                    'image': info['taskDefinition']['image'].split(':')[-1],
                    'deployPipeline': deploy_pipeline if 'error' not in deploy_pipeline else None
                }
            else:
                result['services'][service] = {'error': info['error']}
        except Exception as e:
            result['services'][service] = {'error': str(e)}

    return result


def get_all_services() -> dict:
    """Get summary of all services across all environments"""
    result = {
        'environments': {},
        'timestamp': datetime.utcnow().isoformat(),
        'config': {
            'ssoPortalUrl': SSO_PORTAL_URL,
            'region': REGION,
            'projectName': PROJECT_NAME
        }
    }

    for env, config in ENVIRONMENTS.items():
        result['environments'][env] = {
            'accountId': config['account_id'],
            'services': {}
        }

        for service in config['services']:
            try:
                info = get_service_info(env, service)
                if 'error' not in info:
                    # Get deploy pipeline info
                    deploy_pipeline = get_deploy_pipeline_info(env, service)

                    result['environments'][env]['services'][service] = {
                        'status': info['status'],
                        'health': 'HEALTHY' if info['runningCount'] == info['desiredCount'] else 'UNHEALTHY',
                        'runningCount': info['runningCount'],
                        'desiredCount': info['desiredCount'],
                        'taskDefinition': info['taskDefinition']['revision'],
                        'image': info['taskDefinition']['image'].split(':')[-1],
                        'deployPipeline': deploy_pipeline if 'error' not in deploy_pipeline else None
                    }
                else:
                    result['environments'][env]['services'][service] = {'error': info['error']}
            except Exception as e:
                result['environments'][env]['services'][service] = {'error': str(e)}

    return result


# =============================================================================
# ACTION FUNCTIONS - Trigger builds and deployments
# =============================================================================

def get_user_email(event: dict) -> str:
    """Extract user email from SSO header for CloudTrail attribution"""
    headers = event.get('headers', {})
    # Lambda@Edge adds this header from SSO token
    return headers.get('x-sso-user-email', headers.get('X-SSO-User-Email', 'unknown'))


def trigger_build(service: str, image_tag: str, source_revision: str, user_email: str) -> dict:
    """Trigger a build pipeline execution with user attribution via STS"""
    pipeline_name = f"{PROJECT_NAME}-build-{service}"

    try:
        # Use STS assume-role with email in RoleSessionName for CloudTrail attribution
        # This makes CloudTrail show "dashboard-user-at-example-dot-com" instead of "dashborion-api"
        sanitized_email = user_email.replace('@', '-at-').replace('.', '-dot-')[:64] if user_email else 'unknown'
        session_name = f"dashboard-{sanitized_email}"

        # Assume action role with user email in session name for CloudTrail attribution
        action_role_arn = os.environ.get('ACTION_ROLE_ARN')
        if action_role_arn:
            sts = boto3.client('sts')
            assumed = sts.assume_role(
                RoleArn=action_role_arn,
                RoleSessionName=session_name
            )
            credentials = assumed['Credentials']
            codepipeline = boto3.client(
                'codepipeline',
                region_name=REGION,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            # Fallback to Lambda role (no user attribution)
            codepipeline = boto3.client('codepipeline', region_name=REGION)

        # Build source revision overrides if provided
        source_revisions = []
        if source_revision:
            source_revisions = [{
                'actionName': 'SourceCode',
                'revisionType': 'COMMIT_ID',
                'revisionValue': source_revision
            }]

        # Start pipeline execution with variables
        params = {
            'name': pipeline_name,
            'variables': [
                {'name': 'ImageTag', 'value': image_tag or 'latest'},
                {'name': 'TriggeredBy', 'value': user_email or 'unknown'}
            ]
        }

        if source_revisions:
            params['sourceRevisions'] = source_revisions

        response = codepipeline.start_pipeline_execution(**params)

        return {
            'success': True,
            'executionId': response['pipelineExecutionId'],
            'pipeline': pipeline_name,
            'imageTag': image_tag,
            'triggeredBy': user_email
        }
    except Exception as e:
        return {'error': str(e), 'pipeline': pipeline_name}


def force_ecs_deployment(env: str, service: str, user_email: str) -> dict:
    """Force a new ECS deployment (reload to pick up new secrets)"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    cluster_name = f"{PROJECT_NAME}-{env}-cluster"
    service_name = f"{PROJECT_NAME}-{env}-{service}"

    try:
        # Use RoleSessionName for CloudTrail attribution
        session_name = f"dashboard-{user_email.replace('@', '-at-').replace('.', '-dot-')[:64]}"

        sts = boto3.client('sts')
        role_arn = f"arn:aws:iam::{account_id}:role/{PROJECT_NAME}-dashboard-action-role"

        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name
        )

        credentials = assumed['Credentials']
        ecs = boto3.client(
            'ecs',
            region_name=REGION,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )

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


def scale_service(env: str, service: str, desired_count: int, user_email: str) -> dict:
    """Scale ECS service to desired count (0 to stop, 1+ to start)"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    cluster_name = f"{PROJECT_NAME}-{env}-cluster"
    service_name = f"{PROJECT_NAME}-{env}-{service}"

    try:
        session_name = f"dashboard-{user_email.replace('@', '-at-').replace('.', '-dot-')[:64]}"

        sts = boto3.client('sts')
        role_arn = f"arn:aws:iam::{account_id}:role/{PROJECT_NAME}-dashboard-action-role"

        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name
        )

        credentials = assumed['Credentials']
        ecs = boto3.client(
            'ecs',
            region_name=REGION,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )

        response = ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=desired_count
        )

        action_name = 'stop' if desired_count == 0 else 'start'
        return {
            'success': True,
            'service': service_name,
            'desiredCount': desired_count,
            'triggeredBy': user_email,
            'action': action_name
        }
    except Exception as e:
        return {'error': str(e), 'service': service_name}


def control_rds(env: str, action: str, user_email: str) -> dict:
    """Start or stop RDS database instance"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    db_identifier = f"{PROJECT_NAME}-{env}"

    try:
        session_name = f"dashboard-{user_email.replace('@', '-at-').replace('.', '-dot-')[:64]}"

        sts = boto3.client('sts')
        role_arn = f"arn:aws:iam::{account_id}:role/{PROJECT_NAME}-dashboard-action-role"

        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name
        )

        credentials = assumed['Credentials']
        rds = boto3.client(
            'rds',
            region_name=REGION,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )

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


def invalidate_cloudfront(env: str, distribution_id: str, paths: list, user_email: str) -> dict:
    """Create CloudFront cache invalidation"""
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']

    try:
        session_name = f"dashboard-{user_email.replace('@', '-at-').replace('.', '-dot-')[:64]}"

        sts = boto3.client('sts')
        role_arn = f"arn:aws:iam::{account_id}:role/{PROJECT_NAME}-dashboard-action-role"

        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name
        )

        credentials = assumed['Credentials']
        cloudfront = boto3.client(
            'cloudfront',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )

        import time
        caller_ref = f"dashboard-{int(time.time())}"

        response = cloudfront.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                'Paths': {
                    'Quantity': len(paths),
                    'Items': paths
                },
                'CallerReference': caller_ref
            }
        )

        invalidation = response['Invalidation']
        return {
            'success': True,
            'invalidationId': invalidation['Id'],
            'status': invalidation['Status'],
            'distributionId': distribution_id,
            'paths': paths,
            'triggeredBy': user_email
        }
    except Exception as e:
        return {'error': str(e), 'distributionId': distribution_id}


def trigger_deploy_pipeline(env: str, service: str, user_email: str) -> dict:
    """Trigger the deploy pipeline to update to latest task definition"""
    pipeline_name = f"{PROJECT_NAME}-deploy-{service}-{env}"

    try:
        session_name = f"dashboard-{user_email.replace('@', '-at-').replace('.', '-dot-')[:64]}"

        # Assume action role with user email in session name for CloudTrail attribution
        action_role_arn = os.environ.get('ACTION_ROLE_ARN')
        if action_role_arn:
            sts = boto3.client('sts')
            assumed = sts.assume_role(
                RoleArn=action_role_arn,
                RoleSessionName=session_name
            )
            credentials = assumed['Credentials']
            codepipeline = boto3.client(
                'codepipeline',
                region_name=REGION,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            codepipeline = boto3.client('codepipeline', region_name=REGION)

        response = codepipeline.start_pipeline_execution(name=pipeline_name)

        return {
            'success': True,
            'executionId': response['pipelineExecutionId'],
            'pipeline': pipeline_name,
            'triggeredBy': user_email,
            'action': 'deploy-latest'
        }
    except Exception as e:
        return {'error': str(e), 'pipeline': pipeline_name}


def get_environment_events(env: str, hours: int = 24, event_types: list = None, services: list = None) -> dict:
    """
    Get aggregated events timeline for an environment.
    Sources: CodePipeline, ECS Events, CloudTrail, CloudFront Invalidations

    Args:
        env: Environment name (staging, preprod, production)
        hours: Number of hours to look back
        event_types: List of event types to include (build, deploy, etc.)
        services: List of services to filter by (e.g., ['backend', 'frontend', 'cms'])
    """
    config = ENVIRONMENTS.get(env)
    if not config:
        return {'error': f'Unknown environment: {env}'}

    account_id = config['account_id']
    events = []
    start_time = datetime.utcnow() - timedelta(hours=hours)

    # Default event types if not specified
    if event_types is None:
        event_types = ['build', 'deploy', 'reload', 'scale', 'rollback', 'rds', 'cache']

    try:
        # =================================================================
        # 1. CODEPIPELINE EVENTS (Build & Deploy pipelines)
        # =================================================================
        if 'build' in event_types or 'deploy' in event_types:
            codepipeline = boto3.client('codepipeline', region_name=REGION)

            # Get all pipelines for this project
            pipelines_response = codepipeline.list_pipelines()
            project_pipelines = [p['name'] for p in pipelines_response.get('pipelines', [])
                                if p['name'].startswith(PROJECT_NAME)]

            for pipeline_name in project_pipelines:
                try:
                    # Determine if it's build or deploy
                    is_build = '-build-' in pipeline_name
                    is_deploy = '-deploy-' in pipeline_name and env in pipeline_name

                    if is_build and 'build' not in event_types:
                        continue
                    if is_deploy and 'deploy' not in event_types:
                        continue
                    if not is_build and not is_deploy:
                        continue

                    # Extract service name
                    if is_build:
                        # myapp-build-backend-arm64 -> backend
                        service = pipeline_name.replace(f'{PROJECT_NAME}-build-', '').replace('-arm64', '')
                    else:
                        # myapp-deploy-backend-staging -> backend
                        parts = pipeline_name.replace(f'{PROJECT_NAME}-deploy-', '').rsplit('-', 1)
                        service = parts[0] if parts else pipeline_name

                    # Get recent executions with pagination
                    # CodePipeline API max is 100 per page
                    executions = []
                    next_token = None
                    max_pages = 5  # Limit to 500 executions max to avoid timeout

                    for _ in range(max_pages):
                        params = {'pipelineName': pipeline_name, 'maxResults': 100}
                        if next_token:
                            params['nextToken'] = next_token

                        response = codepipeline.list_pipeline_executions(**params)
                        page_executions = response.get('pipelineExecutionSummaries', [])
                        executions.extend(page_executions)

                        # Check if we've gone past the time window
                        if page_executions:
                            oldest_in_page = page_executions[-1].get('startTime')
                            if oldest_in_page and oldest_in_page.replace(tzinfo=None) < start_time:
                                break  # No need to fetch more pages

                        next_token = response.get('nextToken')
                        if not next_token:
                            break

                    for exec in executions:
                        exec_time = exec.get('startTime')
                        if not exec_time or exec_time.replace(tzinfo=None) < start_time:
                            continue

                        # Calculate duration if completed
                        duration = None
                        if exec.get('lastUpdateTime') and exec.get('status') != 'InProgress':
                            duration = int((exec['lastUpdateTime'] - exec['startTime']).total_seconds())

                        # Determine trigger mode (Auto vs Manual)
                        trigger_type = exec.get('trigger', {}).get('triggerType', 'Unknown')
                        trigger_detail = exec.get('trigger', {}).get('triggerDetail', '')

                        # Auto triggers: webhook, CloudWatch events
                        auto_triggers = ['WebhookV2', 'Webhook', 'CloudWatchEvent', 'PutActionRevision']
                        # Manual triggers: console, CLI, API
                        manual_triggers = ['StartPipelineExecution', 'CreatePipeline']

                        if trigger_type in auto_triggers:
                            trigger_mode = 'Auto'
                        elif trigger_type in manual_triggers:
                            trigger_mode = 'Manuel'
                        else:
                            trigger_mode = trigger_type

                        # Determine actor type based on trigger
                        if trigger_mode == 'Auto':
                            actor_type = 'pipeline'  # Webhook or EventBridge
                        else:
                            actor_type = None  # Will be enriched by CloudTrail

                        event = {
                            'id': f"pipeline-{exec.get('pipelineExecutionId', '')[:12]}",
                            'type': 'build' if is_build else 'deploy',
                            'timestamp': exec_time.isoformat() + 'Z' if exec_time else None,
                            'service': service,
                            'status': exec.get('status', 'Unknown').lower(),
                            'duration': duration,
                            'user': None,
                            'actorType': actor_type,
                            'details': {
                                'executionId': exec.get('pipelineExecutionId'),
                                'pipeline': pipeline_name,
                                'trigger': trigger_type,
                                'triggerMode': trigger_mode
                            }
                        }

                        # Add source revision if available
                        if exec.get('sourceRevisions'):
                            rev = exec['sourceRevisions'][0]
                            commit_sha = rev.get('revisionId', '')
                            event['details']['commit'] = commit_sha[:8]
                            event['details']['commitFull'] = commit_sha
                            # Parse revisionSummary - may be JSON from GitHub
                            revision_summary = rev.get('revisionSummary', '')
                            if revision_summary.startswith('{'):
                                try:
                                    summary_json = json.loads(revision_summary)
                                    event['details']['commitMessage'] = summary_json.get('CommitMessage', '')[:100]
                                    event['details']['providerType'] = summary_json.get('ProviderType', 'GitHub')
                                    # Extract commit author if available
                                    if summary_json.get('AuthorDisplayName'):
                                        event['details']['commitAuthor'] = summary_json.get('AuthorDisplayName')
                                        # Use commit author as user for auto (webhook) builds
                                        if trigger_mode == 'Auto' and not event.get('user'):
                                            event['user'] = summary_json.get('AuthorDisplayName')
                                except:
                                    event['details']['commitMessage'] = revision_summary[:100]
                            else:
                                event['details']['commitMessage'] = revision_summary[:100]
                            # Build GitHub commit URL (only for real git commits, not ECR digests)
                            if commit_sha and not commit_sha.startswith('sha256:'):
                                event['details']['commitUrl'] = f"https://github.com/example/myapp-{service}/commit/{commit_sha}"
                            elif commit_sha and commit_sha.startswith('sha256:'):
                                # This is an ECR image digest, not a git commit - mark it as such
                                event['details']['isEcrDigest'] = True
                                event['details']['imageDigest'] = commit_sha[:19]  # sha256:abc123...

                        # Note: CloudTrail enrichment moved to separate /enrich endpoint for faster response
                        events.append(event)

                except Exception as e:
                    print(f"Error fetching pipeline {pipeline_name}: {e}")
                    continue

            # Enrich build events with ECR image info (tag and digest)
            try:
                ecr = boto3.client('ecr', region_name=REGION)
                for event in events:
                    if event['type'] == 'build' and event['status'] == 'succeeded':
                        service = event.get('service', '')
                        commit_sha = event.get('details', {}).get('commitFull', '')
                        if service and commit_sha:
                            try:
                                repo_name = f"{PROJECT_NAME}-{service}"
                                # Try to find image with full commit SHA tag
                                response = ecr.describe_images(
                                    repositoryName=repo_name,
                                    imageIds=[{'imageTag': commit_sha}]  # Full SHA, not truncated
                                )
                                if response.get('imageDetails'):
                                    img = response['imageDetails'][0]
                                    event['details']['imageTag'] = commit_sha[:8]
                                    event['details']['imageDigest'] = img.get('imageDigest', '')[:19]  # sha256:abc123...
                                    event['details']['imagePushedAt'] = img.get('imagePushedAt').isoformat() + 'Z' if img.get('imagePushedAt') else None
                                    event['details']['imageSizeBytes'] = img.get('imageSizeInBytes')
                            except Exception as ecr_err:
                                # Image not found or ECR error - continue without enrichment
                                event['details']['imageTag'] = commit_sha[:8] if commit_sha else None
                                print(f"ECR lookup failed for {service}: {ecr_err}")
            except Exception as e:
                print(f"ECR enrichment error: {e}")

        # =================================================================
        # 2. ECS SERVICE EVENTS (Rollbacks, deployments, failures)
        # =================================================================
        if 'rollback' in event_types or 'scale' in event_types or 'deploy' in event_types:
            ecs = get_cross_account_client('ecs', account_id)
            cluster_name = f"{PROJECT_NAME}-{env}-cluster"

            # Helper to extract deployment ID from ECS message
            def extract_deployment_id(message):
                import re
                # Match patterns like "ecs-svc/1234567890123456789" or "(deployment ecs-svc/...)"
                match = re.search(r'ecs-svc/(\d+)', message)
                return match.group(1) if match else None

            # Helper to get step label from message
            def get_step_label(message):
                msg_lower = message.lower()
                if 'started' in msg_lower and 'task' in msg_lower:
                    return 'started_tasks'
                elif 'stopped' in msg_lower and 'task' in msg_lower:
                    return 'stopped_tasks'
                elif 'registered' in msg_lower and 'target' in msg_lower:
                    return 'registered_targets'
                elif 'deregistered' in msg_lower and 'target' in msg_lower:
                    return 'deregistered_targets'
                elif 'steady state' in msg_lower:
                    return 'steady_state'
                elif 'rolling back' in msg_lower:
                    return 'rolling_back'
                elif 'failed' in msg_lower or 'unable' in msg_lower:
                    return 'failed'
                elif 'deployment completed' in msg_lower:
                    return 'completed'
                return 'info'

            for svc_name in ['backend', 'frontend', 'cms']:
                try:
                    service_name = f"{PROJECT_NAME}-{env}-{svc_name}"
                    svc_response = ecs.describe_services(
                        cluster=cluster_name,
                        services=[service_name]
                    )

                    if not svc_response['services']:
                        continue

                    svc = svc_response['services'][0]

                    # Build lookup of deployment info from actual deployments
                    deployment_created_at = {}  # deployment_id -> createdAt datetime
                    deployment_task_def = {}  # deployment_id -> task definition revision
                    primary_task_def = None  # Fallback for events without deployment ID
                    active_task_def = None  # Previous task def from ACTIVE deployment (during in-progress deploy)
                    for dep in svc.get('deployments', []):
                        dep_id_full = dep.get('id', '')  # e.g., "ecs-svc/9815633475107823784"
                        if '/' in dep_id_full:
                            dep_id = dep_id_full.split('/')[-1]  # Extract just the number
                            deployment_created_at[dep_id] = dep.get('createdAt')
                            # Extract task definition revision (e.g., "myapp-staging-backend:42" -> "42")
                            task_def_arn = dep.get('taskDefinition', '')
                            if task_def_arn:
                                # ARN format: arn:aws:ecs:region:account:task-definition/name:revision
                                task_def_name = task_def_arn.split('/')[-1] if '/' in task_def_arn else task_def_arn
                                deployment_task_def[dep_id] = task_def_name
                                # Keep PRIMARY deployment's task def as fallback
                                if dep.get('status') == 'PRIMARY':
                                    primary_task_def = task_def_name
                                # Track ACTIVE deployment (the old one being replaced during a deploy)
                                elif dep.get('status') == 'ACTIVE':
                                    active_task_def = task_def_name

                    # Collect all raw events first, grouped by deployment ID
                    deployment_groups = {}  # deployment_id -> list of events

                    # ECS describe_services returns max 100 events, take all of them
                    for event in svc.get('events', []):
                        event_time = event.get('createdAt')
                        if not event_time or event_time.replace(tzinfo=None) < start_time:
                            continue

                        message = event.get('message', '')
                        msg_lower = message.lower()

                        # Extract deployment ID
                        deployment_id = extract_deployment_id(message)
                        if not deployment_id:
                            # Use timestamp-based grouping (5 min window) for events without deployment ID
                            deployment_id = f"ts-{int(event_time.timestamp() // 300)}"

                        # Get step info
                        step_label = get_step_label(message)

                        # Skip uninteresting events
                        if step_label == 'info' and 'rollback' not in msg_lower and 'failed' not in msg_lower:
                            continue

                        # Add to deployment group
                        if deployment_id not in deployment_groups:
                            deployment_groups[deployment_id] = {
                                'events': [],
                                'service': svc_name,
                                'first_time': event_time,
                                'last_time': event_time,
                                'found_dep_ids': set()  # Track all deployment IDs found in this group
                            }

                        # Store deployment ID found from message (before grouping)
                        real_dep_id = extract_deployment_id(message)
                        if real_dep_id:
                            deployment_groups[deployment_id]['found_dep_ids'].add(real_dep_id)

                        deployment_groups[deployment_id]['events'].append({
                            'step': step_label,
                            'message': message[:150],
                            'timestamp': event_time.isoformat() + 'Z',
                            'id': event.get('id', '')[:12]
                        })

                        # Track time range
                        if event_time < deployment_groups[deployment_id]['first_time']:
                            deployment_groups[deployment_id]['first_time'] = event_time
                        if event_time > deployment_groups[deployment_id]['last_time']:
                            deployment_groups[deployment_id]['last_time'] = event_time

                    # Convert deployment groups to events
                    for dep_id, group in deployment_groups.items():
                        steps = sorted(group['events'], key=lambda x: x['timestamp'], reverse=True)

                        # Get actual deployment ID (either from group key or from found IDs)
                        actual_dep_id = dep_id if not dep_id.startswith('ts-') else None
                        if not actual_dep_id and group.get('found_dep_ids'):
                            # Use the first found deployment ID from this group
                            actual_dep_id = next(iter(group['found_dep_ids']), None)

                        # Determine overall status and type from steps
                        step_labels = [s['step'] for s in steps]
                        if 'rolling_back' in step_labels or 'failed' in step_labels:
                            event_type = 'rollback'
                            status = 'failed'
                            summary = 'Deployment rollback'
                        elif 'steady_state' in step_labels:
                            # Only consider as deployment if there are other deployment-related steps
                            # Skip standalone steady_state events (scaling, restart, etc.)
                            deployment_steps = {'started_tasks', 'stopped_tasks', 'registered_targets', 'deregistered_targets'}
                            if len(steps) == 1 and not any(s in step_labels for s in deployment_steps):
                                # Standalone steady_state event - skip it
                                continue
                            event_type = 'deploy'
                            status = 'succeeded'
                            summary = 'Deployment completed'
                        elif 'started_tasks' in step_labels or 'stopped_tasks' in step_labels:
                            event_type = 'deploy'
                            status = 'in_progress'
                            summary = 'Deployment in progress'
                        else:
                            # Skip uninteresting "info" events
                            continue

                        # Check if this event type is requested
                        if event_type not in event_types and not (event_type == 'deploy' and 'rollback' in event_types):
                            continue

                        # Get the real deployment createdAt if available, else use first event time
                        real_created_at = deployment_created_at.get(dep_id)
                        if real_created_at:
                            event_timestamp = real_created_at
                        else:
                            event_timestamp = group['first_time']

                        # Calculate duration from real start to last event
                        duration = None
                        if len(steps) > 1:
                            duration = int((group['last_time'] - event_timestamp).total_seconds())

                        events.append({
                            'id': f"ecs-{dep_id[:12]}",
                            'type': event_type,
                            'timestamp': event_timestamp.isoformat() + 'Z',  # Use real deployment createdAt
                            'service': svc_name,
                            'status': status,
                            'duration': duration,
                            'user': None,
                            'details': {
                                'summary': summary,
                                'deploymentId': actual_dep_id,
                                'taskDefinition': deployment_task_def.get(actual_dep_id) if actual_dep_id else primary_task_def,  # Use PRIMARY as fallback
                                'previousTaskDefinition': active_task_def,  # Previous task def from ACTIVE deployment (if still visible)
                                'stepCount': len(steps),
                                'triggerMode': 'Auto',  # ECS events are always triggered by pipeline/ECS
                                'lastEventTime': group['last_time'].isoformat() + 'Z'  # Keep last event time for reference
                            },
                            'steps': steps if len(steps) > 1 else None  # Include ALL steps
                        })

                except Exception as e:
                    print(f"Error fetching ECS events for {svc_name}: {e}")
                    continue

        # =================================================================
        # 3. CLOUDFRONT INVALIDATIONS
        # =================================================================
        if 'cache' in event_types:
            try:
                cloudfront = get_cross_account_client('cloudfront', account_id)
                infra = get_infrastructure_info(env)
                cf_id = infra.get('cloudfront', {}).get('id')

                if cf_id:
                    invalidations = cloudfront.list_invalidations(
                        DistributionId=cf_id,
                        MaxItems='20'
                    ).get('InvalidationList', {}).get('Items', [])

                    for inv in invalidations:
                        inv_time = inv.get('CreateTime')
                        if not inv_time or inv_time.replace(tzinfo=None) < start_time:
                            continue

                        # Get invalidation details for paths
                        try:
                            inv_detail = cloudfront.get_invalidation(
                                DistributionId=cf_id,
                                Id=inv['Id']
                            ).get('Invalidation', {})
                            paths = inv_detail.get('InvalidationBatch', {}).get('Paths', {}).get('Items', ['/*'])
                        except:
                            paths = ['/*']

                        events.append({
                            'id': f"cache-{inv['Id'][:12]}",
                            'type': 'cache',
                            'timestamp': inv_time.isoformat() + 'Z' if inv_time else None,
                            'service': 'cloudfront',
                            'status': inv.get('Status', 'Unknown').lower(),
                            'duration': None,
                            'user': None,  # Will be enriched by CloudTrail async
                            'details': {
                                'invalidationId': inv['Id'],
                                'paths': paths[:5]  # Limit to first 5 paths
                            }
                        })

            except Exception as e:
                print(f"Error fetching CloudFront invalidations: {e}")

        # =================================================================
        # 4. CLOUDTRAIL EVENTS (for user attribution - async enrichment)
        # =================================================================
        cloudtrail_events = []
        if any(t in event_types for t in ['reload', 'scale', 'rds']):
            try:
                cloudtrail = get_cross_account_client('cloudtrail', account_id)

                # Look up events for dashboard actions with pagination
                lookup_attrs = [
                    {'AttributeKey': 'EventSource', 'AttributeValue': 'ecs.amazonaws.com'},
                ]

                # CloudTrail lookup_events max is 50 per call, paginate up to 5 pages (250 events)
                all_ct_events = []
                next_token = None
                max_pages = 5

                for _ in range(max_pages):
                    params = {
                        'LookupAttributes': lookup_attrs,
                        'StartTime': start_time,
                        'EndTime': datetime.utcnow(),
                        'MaxResults': 50
                    }
                    if next_token:
                        params['NextToken'] = next_token

                    ct_response = cloudtrail.lookup_events(**params)
                    all_ct_events.extend(ct_response.get('Events', []))

                    next_token = ct_response.get('NextToken')
                    if not next_token:
                        break

                for ct_event in all_ct_events:
                    event_name = ct_event.get('EventName', '')
                    event_time = ct_event.get('EventTime')

                    if not event_time:
                        continue

                    # Parse CloudTrail event
                    try:
                        ct_detail = json.loads(ct_event.get('CloudTrailEvent', '{}'))
                    except:
                        ct_detail = {}

                    user_identity = ct_detail.get('userIdentity', {})
                    session_context = user_identity.get('sessionContext', {})
                    session_issuer = session_context.get('sessionIssuer', {})

                    # Extract user from session name (dashboard-user-at-example-com)
                    user = None
                    role_session_name = session_context.get('attributes', {}).get('mfaAuthenticated')
                    if 'dashboard-' in str(session_issuer.get('userName', '')):
                        # Try to extract email from assumed role session name
                        arn = ct_detail.get('userIdentity', {}).get('arn', '')
                        if '/dashboard-' in arn:
                            user_part = arn.split('/dashboard-')[-1]
                            user = user_part.replace('-at-', '@').replace('-', '.')

                    # Determine event type
                    request_params = ct_detail.get('requestParameters', {})

                    if event_name == 'UpdateService':
                        service_arn = request_params.get('service', '')
                        cluster = request_params.get('cluster', '')

                        # Check if it's for our environment
                        if env not in cluster:
                            continue

                        # Extract service name
                        svc_name = service_arn.split('/')[-1].replace(f'{PROJECT_NAME}-{env}-', '')

                        # Determine if scale or reload
                        if 'desiredCount' in request_params:
                            event_type = 'scale'
                            old_count = request_params.get('_oldDesiredCount')  # Not always available
                            new_count = request_params.get('desiredCount')
                            details = {
                                'newCount': new_count,
                                'action': 'stop' if new_count == 0 else 'start'
                            }
                        elif request_params.get('forceNewDeployment'):
                            event_type = 'reload'
                            details = {'action': 'force-new-deployment'}
                        else:
                            continue

                        if event_type not in event_types:
                            continue

                        events.append({
                            'id': f"ct-{ct_event.get('EventId', '')[:12]}",
                            'type': event_type,
                            'timestamp': event_time.isoformat() + 'Z' if event_time else None,
                            'service': svc_name,
                            'status': 'triggered',
                            'duration': None,
                            'user': user,
                            'details': details
                        })

            except Exception as e:
                print(f"Error fetching CloudTrail events: {e}")

        # =================================================================
        # 5. RDS EVENTS
        # =================================================================
        if 'rds' in event_types:
            try:
                rds = get_cross_account_client('rds', account_id)
                db_identifier = f"{PROJECT_NAME}-{env}"

                rds_events = rds.describe_events(
                    SourceIdentifier=db_identifier,
                    SourceType='db-instance',
                    Duration=min(hours * 60, 10080)  # Max 7 days in minutes
                ).get('Events', [])

                for rds_event in rds_events:
                    event_time = rds_event.get('Date')
                    if not event_time or event_time.replace(tzinfo=None) < start_time:
                        continue

                    message = rds_event.get('Message', '')
                    event_type = 'rds'
                    status = 'info'

                    # Classify RDS events
                    if 'stopped' in message.lower():
                        status = 'stopped'
                    elif 'started' in message.lower() or 'available' in message.lower():
                        status = 'started'
                    elif 'backup' in message.lower():
                        status = 'backup'

                    events.append({
                        'id': f"rds-{event_time.timestamp():.0f}",
                        'type': event_type,
                        'timestamp': event_time.isoformat() + 'Z' if event_time else None,
                        'service': 'rds',
                        'status': status,
                        'duration': None,
                        'user': None,
                        'details': {
                            'message': message[:200],
                            'category': rds_event.get('EventCategories', ['unknown'])[0] if rds_event.get('EventCategories') else 'unknown'
                        }
                    })

            except Exception as e:
                print(f"Error fetching RDS events: {e}")

        # Sort events by timestamp (most recent first)
        events.sort(key=lambda x: x.get('timestamp') or '', reverse=True)

        # Deduplicate: merge events from same deployment
        # Key = (service, type, time_bucket) - WITHOUT status to merge in_progress with succeeded
        # But keep 'rollback' separate from 'deploy'
        deduplicated = []
        seen = {}  # key -> event (keep best one)

        # Status priority: succeeded > failed > in_progress (prefer final state)
        status_priority = {'succeeded': 3, 'failed': 2, 'in_progress': 1, 'completed': 3}

        for event in events:
            service = event.get('service', '')
            event_type = event.get('type', '')
            event_status = event.get('status', '').lower()
            timestamp = event.get('timestamp', '')

            # Create time bucket (10 minute window) for dedup
            try:
                from datetime import datetime as dt
                ts = dt.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_bucket = int(ts.timestamp() // 600)  # 10 min buckets
            except:
                time_bucket = timestamp[:13] if timestamp else ''

            # Key WITHOUT status - merge in_progress with succeeded for same deployment
            key = (service, event_type, time_bucket)

            has_steps = event.get('steps') is not None
            has_commit = event.get('details', {}).get('commit') is not None
            current_priority = status_priority.get(event_status, 0)

            if key in seen:
                existing = seen[key]
                existing_has_steps = existing.get('steps') is not None
                existing_has_commit = existing.get('details', {}).get('commit') is not None
                existing_priority = status_priority.get(existing.get('status', '').lower(), 0)

                # Decide which event to keep based on completeness
                should_replace = False

                # 1. Prefer higher status priority (succeeded > in_progress)
                if current_priority > existing_priority:
                    should_replace = True
                # 2. Same status: prefer event with steps (ECS has more detail)
                elif current_priority == existing_priority and has_steps and not existing_has_steps:
                    should_replace = True

                if should_replace:
                    # Merge commit info from CodePipeline if the new event doesn't have it
                    if existing_has_commit and not has_commit:
                        if 'details' not in event:
                            event['details'] = {}
                        event['details']['commit'] = existing['details'].get('commit')
                        event['details']['commitFull'] = existing['details'].get('commitFull')
                        event['details']['commitMessage'] = existing['details'].get('commitMessage')
                        event['details']['commitUrl'] = existing['details'].get('commitUrl')
                        event['details']['commitAuthor'] = existing['details'].get('commitAuthor')
                        if existing.get('user'):
                            event['user'] = existing['user']
                    seen[key] = event
                else:
                    # Keep existing but merge steps from ECS if available
                    if has_steps and not existing_has_steps:
                        existing['steps'] = event.get('steps')
                        existing['details']['stepCount'] = event.get('details', {}).get('stepCount')
                continue

            seen[key] = event

        deduplicated = list(seen.values())
        # Re-sort by timestamp (dict may have changed order)
        deduplicated.sort(key=lambda x: x.get('timestamp') or '', reverse=True)

        # Filter by services if specified
        if services:
            deduplicated = [e for e in deduplicated if e.get('service') in services]

        # Note: CloudTrail enrichment moved to /api/events/{env}/enrich for faster response

        return {
            'environment': env,
            'events': deduplicated[:100],  # Limit to 100 events
            'count': len(deduplicated),
            'startTime': start_time.isoformat() + 'Z',
            'endTime': datetime.utcnow().isoformat() + 'Z'
        }

    except Exception as e:
        return {'error': str(e)}


def enrich_events_with_cloudtrail(events_data, env=None):
    """Enrich events with CloudTrail user info (called separately for async loading)"""
    try:
        events = events_data.get('events', [])
        if not events:
            return events_data

        # Get time range from events
        timestamps = [e.get('timestamp') for e in events if e.get('timestamp')]
        if not timestamps:
            return events_data

        # Parse timestamps to find range
        start_time = None
        end_time = datetime.utcnow()
        for ts in timestamps:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+00:00', ''))
                if start_time is None or dt < start_time:
                    start_time = dt
            except:
                continue

        if not start_time:
            start_time = datetime.utcnow() - timedelta(hours=24)

        # Helper to extract user/actor from CloudTrail event
        # Returns a tuple: (display_name, actor_type)
        # actor_type: 'human', 'dashboard', 'pipeline', 'eventbridge', 'service'
        def extract_actor_from_cloudtrail(ct_detail):
            user_identity = ct_detail.get('userIdentity', {})
            user_arn = user_identity.get('arn', '')
            user_type = user_identity.get('type', '')
            username = user_identity.get('userName', '')

            # AWS Service (internal)
            if user_type == 'AWSService':
                return ('AWS', 'service')

            # Check ARN for assumed roles
            if 'assumed-role' in user_arn:
                parts = user_arn.split('/')
                if len(parts) >= 3:
                    role_name = parts[-2] if len(parts) >= 2 else ''
                    session_name = parts[-1]

                    # SSO user (email in session name)
                    if '@' in session_name:
                        return (session_name, 'human')

                    # Dashboard action (dashboard-user-at-domain-com)
                    if session_name.startswith('dashboard-'):
                        email = session_name.replace('dashboard-', '').replace('-at-', '@').replace('-dot-', '.')
                        return (email, 'dashboard')

                    # Dashboard Lambda role
                    if 'dashboard' in role_name.lower() and 'lambda' in role_name.lower():
                        return ('Dashboard', 'dashboard')

                    # EventBridge trigger (UUID session name)
                    if 'eventbridge' in role_name.lower():
                        return ('EventBridge', 'eventbridge')

                    # UUID-style session (32 hex chars) - typically EventBridge
                    if len(session_name) == 32 and all(c in '0123456789abcdef' for c in session_name.lower()):
                        return ('EventBridge', 'eventbridge')

                    # CodeBuild role
                    if 'codebuild' in role_name.lower():
                        return ('CodeBuild', 'pipeline')

                    # CodePipeline role
                    if 'codepipeline' in role_name.lower():
                        return ('Pipeline', 'pipeline')

                    # Other service roles
                    if any(p in role_name.lower() for p in ['lambda', 'ecs-tasks', 'aws-service']):
                        return (role_name.split('-')[-2] if '-' in role_name else role_name, 'service')

                    # Unknown assumed role - show session name if reasonable
                    # Filter out: instance IDs, ECS task IDs, lambda IDs, and pure numeric IDs (execution IDs)
                    if not session_name.startswith(('i-', 'ecs-', 'lambda-')):
                        # Skip pure numeric session names (pipeline/build execution IDs) - not useful
                        if session_name.isdigit():
                            return (None, None)  # Will be resolved via StartPipelineExecution
                        # Skip long numeric-looking strings (timestamps, execution IDs like 1765822168210)
                        if len(session_name) > 10 and session_name.replace('-', '').isdigit():
                            return (None, None)  # Will be resolved via StartPipelineExecution
                        return (session_name, 'human')

            # Direct username (often SSO email)
            if username:
                if '@' in username:
                    return (username, 'human')
                if not username.startswith('AWSReserved'):
                    return (username, 'human')

            return (None, None)

        # Collect CloudTrail events from multiple sources
        trail_events = []

        # 1. Shared-services account (pipelines, builds)
        try:
            cloudtrail_ss = boto3.client('cloudtrail', region_name='eu-west-3')
            for event_name in ['StartPipelineExecution', 'StartBuild']:
                try:
                    response = cloudtrail_ss.lookup_events(
                        LookupAttributes=[{'AttributeKey': 'EventName', 'AttributeValue': event_name}],
                        StartTime=start_time,
                        EndTime=end_time,
                        MaxResults=30
                    )
                    trail_events.extend(response.get('Events', []))
                except:
                    continue
        except:
            pass

        # 2. Environment account (ECS UpdateService, etc.)
        if env and env in ENVIRONMENTS:
            try:
                account_id = ENVIRONMENTS[env]['account_id']
                cloudtrail_env = get_cross_account_client('cloudtrail', account_id)
                for event_name in ['UpdateService']:
                    try:
                        response = cloudtrail_env.lookup_events(
                            LookupAttributes=[{'AttributeKey': 'EventName', 'AttributeValue': event_name}],
                            StartTime=start_time,
                            EndTime=end_time,
                            MaxResults=30
                        )
                        trail_events.extend(response.get('Events', []))
                    except:
                        continue
            except Exception as e:
                print(f"CloudTrail cross-account lookup failed for {env}: {e}")

        # Build a lookup map: (event_type, service, timestamp_bucket) -> (user, actorType)
        # Priority: 1=human/dashboard (highest), 2=StartPipelineExecution, 3=UpdateService (lowest)
        actor_lookup = {}  # key -> (actor_info, priority)

        for trail_event in trail_events:
            try:
                ct_detail = json.loads(trail_event.get('CloudTrailEvent', '{}'))
                event_time = trail_event.get('EventTime')
                if not event_time:
                    continue

                time_bucket = int(event_time.timestamp() // 300)  # 5 min bucket

                # Extract actor using improved logic (returns tuple)
                actor_name, actor_type = extract_actor_from_cloudtrail(ct_detail)
                if not actor_name:
                    continue

                # Get resource name (pipeline or service)
                req_params = ct_detail.get('requestParameters', {})
                ct_event_name = ct_detail.get('eventName', '')

                actor_info = {'name': actor_name, 'type': actor_type}

                # Determine priority: human/dashboard > pipeline trigger > service role
                if actor_type in ('human', 'dashboard'):
                    priority = 1
                elif ct_event_name == 'StartPipelineExecution':
                    priority = 2
                else:
                    priority = 3  # UpdateService from codebuild

                def maybe_add(key, info, prio):
                    existing = actor_lookup.get(key)
                    if not existing or prio < existing[1]:  # Lower priority number = higher priority
                        actor_lookup[key] = (info, prio)

                if ct_event_name == 'StartPipelineExecution':
                    resource_name = req_params.get('name', '')
                    if 'build' in resource_name.lower():
                        for svc in ['backend', 'frontend', 'cms']:
                            if svc in resource_name.lower():
                                maybe_add(('build', svc, time_bucket), actor_info, priority)
                    elif 'deploy' in resource_name.lower():
                        # Only add user for deploy pipelines if manually triggered (human or dashboard)
                        # Skip webhook/eventbridge/pipeline triggers to avoid attributing auto-deploys
                        if actor_type in ('human', 'dashboard'):
                            for svc in ['backend', 'frontend', 'cms']:
                                if svc in resource_name.lower():
                                    maybe_add(('deploy', svc, time_bucket), actor_info, priority)
                elif ct_event_name == 'UpdateService':
                    service_name = req_params.get('service', '')
                    for svc in ['backend', 'frontend', 'cms']:
                        if svc in service_name.lower():
                            maybe_add(('deploy', svc, time_bucket), actor_info, priority)
                            maybe_add(('rollback', svc, time_bucket), actor_info, priority)
                            break
            except:
                continue

        # Convert lookup to just actor_info (remove priority)
        actor_lookup = {k: v[0] for k, v in actor_lookup.items()}

        # Enrich events with actor info
        enriched_count = 0
        for event in events:
            if event.get('user'):
                continue

            event_type = event.get('type', '')
            service = event.get('service', '')
            timestamp = event.get('timestamp', '')

            try:
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00').replace('+00:00', ''))
                time_bucket = int(ts.timestamp() // 300)

                # Search wider window: deploys can take 10-20 min from pipeline start to ECS update
                # Try current bucket first, then expand to ±20 minutes (±4 buckets)
                for offset in [0, -1, 1, -2, 2, -3, 3, -4, 4]:
                    key = (event_type, service, time_bucket + offset)
                    if key in actor_lookup:
                        actor_info = actor_lookup[key]
                        event['user'] = actor_info['name']
                        event['actorType'] = actor_info['type']
                        enriched_count += 1
                        break
            except:
                continue

        return {
            'events': events,
            'enrichedCount': enriched_count,
            'cloudTrailEventsFound': len(trail_events)
        }

    except Exception as e:
        return {'error': str(e), 'events': events_data.get('events', [])}


def lambda_handler(event, context):
    """Main Lambda handler"""
    print(f"Event: {json.dumps(event)}")

    # Handle API Gateway v2 (HTTP API)
    path = event.get('rawPath', event.get('path', '/'))
    method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', 'GET'))
    path_params = event.get('pathParameters', {}) or {}

    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-SSO-User-Email',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }

    # Handle CORS preflight
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    # Get user email from SSO header for actions
    user_email = get_user_email(event)

    try:
        # Route handling
        if path == '/api/services' or path == '/api/services/':
            result = get_all_services()
        elif path.startswith('/api/services/'):
            parts = path.split('/')
            if len(parts) == 4:
                # /api/services/{env} - get all services for one env
                env = parts[3]
                result = get_env_services(env)
            elif len(parts) >= 5:
                # /api/services/{env}/{service} - get specific service
                env = parts[3]
                service = parts[4]
                result = get_service_info(env, service)
            else:
                result = {'error': 'Invalid path. Use /api/services/{env} or /api/services/{env}/{service}'}
        elif path.startswith('/api/pipelines/'):
            parts = path.split('/')
            if len(parts) >= 5:
                pipeline_type = parts[3]  # build or deploy
                service = parts[4]
                env = parts[5] if len(parts) > 5 else None
                result = get_pipeline_info(pipeline_type, service, env)
            else:
                result = {'error': 'Invalid path'}
        elif path.startswith('/api/images/'):
            parts = path.split('/')
            if len(parts) >= 4:
                service = parts[3]
                result = get_ecr_images(service)
            else:
                result = {'error': 'Invalid path'}
        elif path.startswith('/api/metrics/'):
            parts = path.split('/')
            if len(parts) >= 5:
                env = parts[3]
                service = parts[4]
                result = get_metrics(env, service)
            else:
                result = {'error': 'Invalid path'}
        elif path.startswith('/api/details/'):
            parts = path.split('/')
            if len(parts) >= 5:
                env = parts[3]
                service = parts[4]
                result = get_service_details(env, service)
            else:
                result = {'error': 'Invalid path. Use /api/details/{env}/{service}'}
        elif path.startswith('/api/infrastructure/'):
            parts = path.split('/')
            if len(parts) >= 4:
                env = parts[3]
                # Parse query parameters for tag-based discovery
                query_params = event.get('queryStringParameters') or {}

                # Parse discoveryTags (JSON-encoded object)
                discovery_tags = None
                discovery_tags_str = query_params.get('discoveryTags', '')
                if discovery_tags_str:
                    try:
                        discovery_tags = json.loads(discovery_tags_str)
                    except json.JSONDecodeError:
                        discovery_tags = None

                # Parse services list (comma-separated)
                services_str = query_params.get('services', '')
                services_list = services_str.split(',') if services_str else None

                # Parse domain_config (JSON-encoded object)
                domain_config = None
                domain_config_str = query_params.get('domainConfig', '')
                if domain_config_str:
                    try:
                        domain_config = json.loads(domain_config_str)
                    except json.JSONDecodeError:
                        domain_config = None

                # Parse databases list (comma-separated)
                databases_str = query_params.get('databases', '')
                databases_list = databases_str.split(',') if databases_str else None

                # Parse caches list (comma-separated)
                caches_str = query_params.get('caches', '')
                caches_list = caches_str.split(',') if caches_str else None

                result = get_infrastructure_info(
                    env,
                    discovery_tags=discovery_tags,
                    services=services_list,
                    domain_config=domain_config,
                    databases=databases_list,
                    caches=caches_list
                )
            else:
                result = {'error': 'Invalid path. Use /api/infrastructure/{env}'}
        elif path.startswith('/api/tasks/'):
            parts = path.split('/')
            if len(parts) >= 6:
                # /api/tasks/{env}/{service}/{task_id}
                env = parts[3]
                service = parts[4]
                task_id = parts[5]
                result = get_task_details(env, service, task_id)
            else:
                result = {'error': 'Invalid path. Use /api/tasks/{env}/{service}/{task_id}'}
        elif path.startswith('/api/logs/'):
            parts = path.split('/')
            if len(parts) >= 5:
                # /api/logs/{env}/{service}
                env = parts[3]
                service = parts[4]
                result = get_service_logs(env, service)
            else:
                result = {'error': 'Invalid path. Use /api/logs/{env}/{service}'}
        # =================================================================
        # EVENTS TIMELINE ENDPOINT
        # =================================================================
        elif path.startswith('/api/events/'):
            parts = path.split('/')
            # /api/events/{env}/enrich - POST to enrich events with CloudTrail
            if len(parts) >= 5 and parts[4] == 'enrich':
                if method != 'POST':
                    result = {'error': 'Enrich endpoint requires POST with events in body'}
                else:
                    env = parts[3]
                    # Parse JSON body containing events
                    body = {}
                    if event.get('body'):
                        try:
                            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
                        except:
                            body = {}
                    result = enrich_events_with_cloudtrail(body, env=env)
            # /api/events/{env}/task-diff - POST to compute task definition diffs
            elif len(parts) >= 5 and parts[4] == 'task-diff':
                if method != 'POST':
                    result = {'error': 'Task-diff endpoint requires POST with items in body'}
                else:
                    env = parts[3]
                    # Parse JSON body containing items to diff
                    body = {}
                    if event.get('body'):
                        try:
                            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
                        except:
                            body = {}
                    items = body.get('items', [])
                    result = get_task_definition_diffs(env, items)
            elif len(parts) >= 4:
                # /api/events/{env}?hours=24&types=build,deploy&services=backend,frontend
                env = parts[3]
                # Parse query parameters
                query_params = event.get('queryStringParameters') or {}
                hours = int(query_params.get('hours', 24))
                hours = min(max(hours, 1), 168)  # 1h to 7 days
                types_str = query_params.get('types', '')
                event_types = types_str.split(',') if types_str else None
                services_str = query_params.get('services', '')
                services = services_str.split(',') if services_str else None
                result = get_environment_events(env, hours=hours, event_types=event_types, services=services)
            else:
                result = {'error': 'Invalid path. Use /api/events/{env}'}
        # =================================================================
        # ACTION ENDPOINTS (POST only)
        # =================================================================
        elif path.startswith('/api/actions/'):
            if method != 'POST':
                result = {'error': 'Actions require POST method'}
            else:
                parts = path.split('/')
                # Parse JSON body
                body = {}
                if event.get('body'):
                    import base64
                    body_str = event['body']
                    if event.get('isBase64Encoded'):
                        body_str = base64.b64decode(body_str).decode('utf-8')
                    body = json.loads(body_str) if body_str else {}

                if len(parts) >= 5 and parts[3] == 'build':
                    # POST /api/actions/build/{service}
                    service = parts[4]
                    image_tag = body.get('imageTag', 'latest')
                    source_revision = body.get('sourceRevision', '')
                    result = trigger_build(service, image_tag, source_revision, user_email)

                elif len(parts) >= 6 and parts[3] == 'deploy':
                    # POST /api/actions/deploy/{env}/{service}/{action}
                    env = parts[4]
                    service = parts[5]
                    action = parts[6] if len(parts) > 6 else 'reload'

                    if action == 'reload':
                        # Force new deployment (reload secrets)
                        result = force_ecs_deployment(env, service, user_email)
                    elif action == 'latest':
                        # Trigger deploy pipeline (update task def)
                        result = trigger_deploy_pipeline(env, service, user_email)
                    elif action == 'stop':
                        # Scale to 0 (stop service)
                        result = scale_service(env, service, 0, user_email)
                    elif action == 'start':
                        # Scale to N replicas (default 1)
                        desired_count = int(body.get('desiredCount', 1))
                        if desired_count < 1 or desired_count > 10:
                            result = {'error': 'desiredCount must be between 1 and 10'}
                        else:
                            result = scale_service(env, service, desired_count, user_email)
                    else:
                        result = {'error': f'Unknown action: {action}. Use reload, latest, stop or start'}
                elif len(parts) >= 5 and parts[3] == 'rds':
                    # POST /api/actions/rds/{env}/{action}
                    env = parts[4]
                    action = parts[5] if len(parts) > 5 else None
                    if action in ('stop', 'start'):
                        result = control_rds(env, action, user_email)
                    else:
                        result = {'error': 'Use stop or start for RDS action'}

                elif len(parts) >= 5 and parts[3] == 'cloudfront':
                    # POST /api/actions/cloudfront/{env}/invalidate
                    env = parts[4]
                    action = parts[5] if len(parts) > 5 else None
                    if action == 'invalidate':
                        distribution_id = body.get('distributionId')
                        paths = body.get('paths', ['/*'])
                        if not distribution_id:
                            result = {'error': 'distributionId is required'}
                        else:
                            result = invalidate_cloudfront(env, distribution_id, paths, user_email)
                    else:
                        result = {'error': 'Use invalidate for CloudFront action'}

                else:
                    result = {'error': 'Invalid action path'}

        elif path == '/api/health':
            result = {'status': 'ok', 'timestamp': datetime.utcnow().isoformat(), 'user': user_email}
        else:
            result = {'error': f'Unknown path: {path}'}

        status_code = 400 if 'error' in result else 200

        return {
            'statusCode': status_code,
            'headers': headers,
            'body': json.dumps(result, default=str)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }
