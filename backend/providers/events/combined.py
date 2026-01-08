"""
Combined Events Provider - Aggregates events from multiple sources.
Sources: CodePipeline, ECS, CloudFront, CloudTrail
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import boto3

from providers.base import EventsProvider, Event, ProviderFactory
from config import DashboardConfig
from utils.aws import get_cross_account_client


class CombinedEventsProvider(EventsProvider):
    """
    Aggregates events from multiple sources:
    - CodePipeline (build/deploy)
    - ECS Service Events (rollbacks, deployments)
    - CloudFront Invalidations
    - CloudTrail (user attribution)
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

    def get_events(self, env: str, hours: int = 24, event_types: List[str] = None, services: List[str] = None) -> dict:
        """Get aggregated events timeline for an environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        account_id = env_config.account_id
        events = []
        start_time = datetime.utcnow() - timedelta(hours=hours)

        # Default event types
        if event_types is None:
            event_types = ['build', 'deploy', 'reload', 'scale', 'rollback', 'rds', 'cache']

        try:
            # 1. CodePipeline Events
            if 'build' in event_types or 'deploy' in event_types:
                events.extend(self._get_pipeline_events(env, start_time, event_types))

            # 2. ECS Service Events
            if any(t in event_types for t in ['rollback', 'scale', 'deploy']):
                events.extend(self._get_ecs_events(env, env_config, start_time, event_types))

            # 3. CloudFront Invalidations
            if 'cache' in event_types:
                events.extend(self._get_cloudfront_events(env, env_config, start_time))

            # Deduplicate and sort
            events = self._deduplicate_events(events)
            events.sort(key=lambda x: x.get('timestamp') or '', reverse=True)

            # Filter by services if specified
            if services:
                events = [e for e in events if e.get('service') in services]

            return {
                'environment': env,
                'events': events[:100],
                'count': len(events),
                'startTime': start_time.isoformat() + 'Z',
                'endTime': datetime.utcnow().isoformat() + 'Z'
            }

        except Exception as e:
            return {'error': str(e)}

    def _get_pipeline_events(self, env: str, start_time: datetime, event_types: List[str]) -> List[dict]:
        """Get CodePipeline events"""
        events = []
        codepipeline = boto3.client('codepipeline', region_name=self.region)

        try:
            pipelines_response = codepipeline.list_pipelines()
            project_pipelines = [
                p['name'] for p in pipelines_response.get('pipelines', [])
                if p['name'].startswith(self.project)
            ]

            for pipeline_name in project_pipelines:
                try:
                    is_build = self.config.naming_pattern.build_pipeline.replace('{project}', '').replace('{service}', '') in pipeline_name or '-build-' in pipeline_name
                    is_deploy = env in pipeline_name and ('-deploy-' in pipeline_name or 'deploy' in pipeline_name.lower())

                    if is_build and 'build' not in event_types:
                        continue
                    if is_deploy and 'deploy' not in event_types:
                        continue
                    if not is_build and not is_deploy:
                        continue

                    # Extract service name
                    service = self._extract_service_from_pipeline(pipeline_name, is_build)

                    # Get executions
                    executions = []
                    next_token = None
                    for _ in range(3):  # Max 3 pages
                        params = {'pipelineName': pipeline_name, 'maxResults': 100}
                        if next_token:
                            params['nextToken'] = next_token
                        response = codepipeline.list_pipeline_executions(**params)
                        executions.extend(response.get('pipelineExecutionSummaries', []))

                        if executions and executions[-1].get('startTime'):
                            oldest = executions[-1]['startTime']
                            if oldest.replace(tzinfo=None) < start_time:
                                break

                        next_token = response.get('nextToken')
                        if not next_token:
                            break

                    for exec in executions:
                        exec_time = exec.get('startTime')
                        if not exec_time or exec_time.replace(tzinfo=None) < start_time:
                            continue

                        duration = None
                        if exec.get('lastUpdateTime') and exec.get('status') != 'InProgress':
                            duration = int((exec['lastUpdateTime'] - exec['startTime']).total_seconds())

                        # Trigger info
                        trigger_type = exec.get('trigger', {}).get('triggerType', 'Unknown')
                        trigger_mode = 'Auto' if trigger_type in ['WebhookV2', 'Webhook', 'CloudWatchEvent'] else 'Manuel'

                        event = {
                            'id': f"pipeline-{exec.get('pipelineExecutionId', '')[:12]}",
                            'type': 'build' if is_build else 'deploy',
                            'timestamp': exec_time.isoformat() + 'Z' if exec_time else None,
                            'service': service,
                            'status': exec.get('status', 'Unknown').lower(),
                            'duration': duration,
                            'user': None,
                            'actorType': 'pipeline' if trigger_mode == 'Auto' else None,
                            'details': {
                                'executionId': exec.get('pipelineExecutionId'),
                                'pipeline': pipeline_name,
                                'trigger': trigger_type,
                                'triggerMode': trigger_mode
                            }
                        }

                        # Add source revision
                        if exec.get('sourceRevisions'):
                            rev = exec['sourceRevisions'][0]
                            commit_sha = rev.get('revisionId', '')
                            event['details']['commit'] = commit_sha[:8]
                            event['details']['commitFull'] = commit_sha

                            # Parse commit message
                            revision_summary = rev.get('revisionSummary', '')
                            if revision_summary.startswith('{'):
                                try:
                                    summary_json = json.loads(revision_summary)
                                    event['details']['commitMessage'] = summary_json.get('CommitMessage', '')[:100]
                                    if summary_json.get('AuthorDisplayName'):
                                        event['details']['commitAuthor'] = summary_json.get('AuthorDisplayName')
                                        if trigger_mode == 'Auto':
                                            event['user'] = summary_json.get('AuthorDisplayName')
                                except:
                                    event['details']['commitMessage'] = revision_summary[:100]
                            else:
                                event['details']['commitMessage'] = revision_summary[:100]

                            # GitHub URL
                            if commit_sha and not commit_sha.startswith('sha256:'):
                                github_org = self.config.github_org or 'HOMEBOXDEV'
                                repo_pattern = self.config.ci_provider.config.get('repo_pattern', '{project}-{service}')
                                repo = repo_pattern.replace('{project}', self.project).replace('{service}', service)
                                event['details']['commitUrl'] = f"https://github.com/{github_org}/{repo}/commit/{commit_sha}"

                        events.append(event)

                except Exception as e:
                    print(f"Error fetching pipeline {pipeline_name}: {e}")
                    continue

            # Enrich build events with ECR info
            self._enrich_with_ecr(events)

        except Exception as e:
            print(f"Error fetching pipeline events: {e}")

        return events

    def _extract_service_from_pipeline(self, pipeline_name: str, is_build: bool) -> str:
        """Extract service name from pipeline name"""
        # Try pattern matching
        for svc in ['backend', 'frontend', 'cms']:
            if svc in pipeline_name.lower():
                return svc

        # Fallback: parse from pattern
        if is_build:
            parts = pipeline_name.replace(f'{self.project}-build-', '').replace('-arm64', '')
        else:
            parts = pipeline_name.replace(f'{self.project}-deploy-', '').rsplit('-', 1)
            parts = parts[0] if parts else pipeline_name

        return parts

    def _enrich_with_ecr(self, events: List[dict]):
        """Enrich build events with ECR image info"""
        try:
            ecr = boto3.client('ecr', region_name=self.region)
            for event in events:
                if event['type'] == 'build' and event['status'] == 'succeeded':
                    service = event.get('service', '')
                    commit_sha = event.get('details', {}).get('commitFull', '')
                    if service and commit_sha:
                        try:
                            repo_name = self.config.get_ecr_repo(self.project, service)
                            response = ecr.describe_images(
                                repositoryName=repo_name,
                                imageIds=[{'imageTag': commit_sha}]
                            )
                            if response.get('imageDetails'):
                                img = response['imageDetails'][0]
                                event['details']['imageTag'] = commit_sha[:8]
                                event['details']['imageDigest'] = img.get('imageDigest', '')[:19]
                        except:
                            event['details']['imageTag'] = commit_sha[:8] if commit_sha else None
        except Exception as e:
            print(f"ECR enrichment error: {e}")

    def _get_ecs_events(self, env: str, env_config, start_time: datetime, event_types: List[str]) -> List[dict]:
        """Get ECS service events"""
        events = []

        try:
            cluster_name = self.config.get_cluster_name(self.project, env)
            ecs = get_cross_account_client('ecs', env_config.account_id, env_config.region)

            for svc_name in env_config.services:
                try:
                    service_name = self.config.get_service_name(self.project, env, svc_name)
                    svc_response = ecs.describe_services(
                        cluster=cluster_name,
                        services=[service_name]
                    )

                    if not svc_response['services']:
                        continue

                    svc = svc_response['services'][0]

                    # Build deployment lookup
                    deployment_info = self._build_deployment_info(svc)

                    # Group events by deployment
                    deployment_groups = self._group_ecs_events(svc, start_time)

                    # Convert groups to events
                    for dep_id, group in deployment_groups.items():
                        event = self._convert_deployment_group(dep_id, group, svc_name, deployment_info, event_types)
                        if event:
                            events.append(event)

                except Exception as e:
                    print(f"Error fetching ECS events for {svc_name}: {e}")
                    continue

        except Exception as e:
            print(f"Error fetching ECS events: {e}")

        return events

    def _build_deployment_info(self, svc: dict) -> dict:
        """Build lookup of deployment info"""
        deployment_created_at = {}
        deployment_task_def = {}
        primary_task_def = None
        active_task_def = None

        for dep in svc.get('deployments', []):
            dep_id_full = dep.get('id', '')
            if '/' in dep_id_full:
                dep_id = dep_id_full.split('/')[-1]
                deployment_created_at[dep_id] = dep.get('createdAt')
                task_def_arn = dep.get('taskDefinition', '')
                if task_def_arn:
                    task_def_name = task_def_arn.split('/')[-1] if '/' in task_def_arn else task_def_arn
                    deployment_task_def[dep_id] = task_def_name
                    if dep.get('status') == 'PRIMARY':
                        primary_task_def = task_def_name
                    elif dep.get('status') == 'ACTIVE':
                        active_task_def = task_def_name

        return {
            'created_at': deployment_created_at,
            'task_def': deployment_task_def,
            'primary': primary_task_def,
            'active': active_task_def
        }

    def _group_ecs_events(self, svc: dict, start_time: datetime) -> dict:
        """Group ECS events by deployment"""
        groups = {}

        for event in svc.get('events', []):
            event_time = event.get('createdAt')
            if not event_time or event_time.replace(tzinfo=None) < start_time:
                continue

            message = event.get('message', '')
            msg_lower = message.lower()

            # Extract deployment ID
            match = re.search(r'ecs-svc/(\d+)', message)
            deployment_id = match.group(1) if match else f"ts-{int(event_time.timestamp() // 300)}"

            # Classify step
            step_label = self._get_step_label(msg_lower)
            if step_label == 'info' and 'rollback' not in msg_lower and 'failed' not in msg_lower:
                continue

            if deployment_id not in groups:
                groups[deployment_id] = {
                    'events': [],
                    'first_time': event_time,
                    'last_time': event_time,
                    'found_dep_ids': set()
                }

            if match:
                groups[deployment_id]['found_dep_ids'].add(match.group(1))

            groups[deployment_id]['events'].append({
                'step': step_label,
                'message': message[:150],
                'timestamp': event_time.isoformat() + 'Z',
                'id': event.get('id', '')[:12]
            })

            if event_time < groups[deployment_id]['first_time']:
                groups[deployment_id]['first_time'] = event_time
            if event_time > groups[deployment_id]['last_time']:
                groups[deployment_id]['last_time'] = event_time

        return groups

    def _get_step_label(self, msg_lower: str) -> str:
        """Get step label from message"""
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

    def _convert_deployment_group(self, dep_id: str, group: dict, service: str, deployment_info: dict, event_types: List[str]) -> Optional[dict]:
        """Convert deployment group to event"""
        steps = sorted(group['events'], key=lambda x: x['timestamp'], reverse=True)
        step_labels = [s['step'] for s in steps]

        # Determine type and status
        if 'rolling_back' in step_labels or 'failed' in step_labels:
            event_type = 'rollback'
            status = 'failed'
            summary = 'Deployment rollback'
        elif 'steady_state' in step_labels:
            deployment_steps = {'started_tasks', 'stopped_tasks', 'registered_targets', 'deregistered_targets'}
            if len(steps) == 1 and not any(s in step_labels for s in deployment_steps):
                return None
            event_type = 'deploy'
            status = 'succeeded'
            summary = 'Deployment completed'
        elif 'started_tasks' in step_labels or 'stopped_tasks' in step_labels:
            event_type = 'deploy'
            status = 'in_progress'
            summary = 'Deployment in progress'
        else:
            return None

        if event_type not in event_types:
            return None

        # Get actual deployment ID
        actual_dep_id = dep_id if not dep_id.startswith('ts-') else None
        if not actual_dep_id and group.get('found_dep_ids'):
            actual_dep_id = next(iter(group['found_dep_ids']), None)

        # Calculate duration
        event_timestamp = deployment_info['created_at'].get(dep_id) or group['first_time']
        duration = None
        if len(steps) > 1:
            duration = int((group['last_time'] - event_timestamp).total_seconds())

        return {
            'id': f"ecs-{dep_id[:12]}",
            'type': event_type,
            'timestamp': event_timestamp.isoformat() + 'Z',
            'service': service,
            'status': status,
            'duration': duration,
            'user': None,
            'details': {
                'summary': summary,
                'deploymentId': actual_dep_id,
                'taskDefinition': deployment_info['task_def'].get(actual_dep_id) if actual_dep_id else deployment_info['primary'],
                'previousTaskDefinition': deployment_info['active'],
                'stepCount': len(steps),
                'triggerMode': 'Auto',
                'lastEventTime': group['last_time'].isoformat() + 'Z'
            },
            'steps': steps if len(steps) > 1 else None
        }

    def _get_cloudfront_events(self, env: str, env_config, start_time: datetime) -> List[dict]:
        """Get CloudFront invalidation events"""
        events = []

        try:
            cloudfront = get_cross_account_client('cloudfront', env_config.account_id)

            # Find distribution for this environment
            distributions = cloudfront.list_distributions()
            domain_suffix = f"{env}.{self.project}"

            cf_id = None
            for dist in distributions.get('DistributionList', {}).get('Items', []):
                aliases = dist.get('Aliases', {}).get('Items', [])
                if any(domain_suffix in alias for alias in aliases):
                    cf_id = dist['Id']
                    break

            if cf_id:
                invalidations = cloudfront.list_invalidations(
                    DistributionId=cf_id,
                    MaxItems='20'
                ).get('InvalidationList', {}).get('Items', [])

                for inv in invalidations:
                    inv_time = inv.get('CreateTime')
                    if not inv_time or inv_time.replace(tzinfo=None) < start_time:
                        continue

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
                        'user': None,
                        'details': {
                            'invalidationId': inv['Id'],
                            'paths': paths[:5]
                        }
                    })

        except Exception as e:
            print(f"Error fetching CloudFront events: {e}")

        return events

    def _deduplicate_events(self, events: List[dict]) -> List[dict]:
        """Deduplicate events by service+time window"""
        seen = {}

        for event in sorted(events, key=lambda x: x.get('timestamp') or '', reverse=True):
            ts = event.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(ts.replace('Z', ''))
                time_bucket = int(dt.timestamp() // 300)  # 5 min windows
            except:
                time_bucket = 0

            key = (event.get('type'), event.get('service'), time_bucket)

            if key in seen:
                existing = seen[key]
                # Keep the one with more info (commit, steps)
                has_commit = bool(event.get('details', {}).get('commit'))
                has_steps = bool(event.get('steps'))
                existing_has_commit = bool(existing.get('details', {}).get('commit'))
                existing_has_steps = bool(existing.get('steps'))

                # Merge info
                if has_commit and not existing_has_commit:
                    existing['details']['commit'] = event['details'].get('commit')
                    existing['details']['commitFull'] = event['details'].get('commitFull')
                    existing['details']['commitMessage'] = event['details'].get('commitMessage')
                if has_steps and not existing_has_steps:
                    existing['steps'] = event.get('steps')
            else:
                seen[key] = event

        return list(seen.values())

    def enrich_events(self, events_data: dict, env: str = None) -> dict:
        """Enrich events with CloudTrail user info"""
        try:
            events = events_data.get('events', [])
            if not events:
                return events_data

            # Get time range
            timestamps = [e.get('timestamp') for e in events if e.get('timestamp')]
            if not timestamps:
                return events_data

            start_time = None
            for ts in timestamps:
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', ''))
                    if start_time is None or dt < start_time:
                        start_time = dt
                except:
                    continue

            if not start_time:
                start_time = datetime.utcnow() - timedelta(hours=24)

            end_time = datetime.utcnow()

            # Collect CloudTrail events
            trail_events = []

            # Shared services account
            try:
                cloudtrail_ss = boto3.client('cloudtrail', region_name=self.region)
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

            # Environment account
            if env:
                env_config = self.config.get_environment(self.project, env)
                if env_config:
                    try:
                        cloudtrail_env = get_cross_account_client('cloudtrail', env_config.account_id, env_config.region)
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
                        print(f"CloudTrail cross-account lookup failed: {e}")

            # Build actor lookup
            actor_lookup = self._build_actor_lookup(trail_events)

            # Enrich events
            enriched_count = 0
            for event in events:
                if event.get('user'):
                    continue

                event_type = event.get('type', '')
                service = event.get('service', '')
                timestamp = event.get('timestamp', '')

                try:
                    ts = datetime.fromisoformat(timestamp.replace('Z', ''))
                    time_bucket = int(ts.timestamp() // 300)

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

    def _build_actor_lookup(self, trail_events: list) -> dict:
        """Build actor lookup from CloudTrail events"""
        actor_lookup = {}

        for trail_event in trail_events:
            try:
                ct_detail = json.loads(trail_event.get('CloudTrailEvent', '{}'))
                event_time = trail_event.get('EventTime')
                if not event_time:
                    continue

                time_bucket = int(event_time.timestamp() // 300)
                actor_name, actor_type = self._extract_actor(ct_detail)
                if not actor_name:
                    continue

                req_params = ct_detail.get('requestParameters', {})
                ct_event_name = ct_detail.get('eventName', '')
                actor_info = {'name': actor_name, 'type': actor_type}

                priority = 1 if actor_type in ('human', 'dashboard') else 2 if ct_event_name == 'StartPipelineExecution' else 3

                def maybe_add(key, info, prio):
                    existing = actor_lookup.get(key)
                    if not existing or prio < existing[1]:
                        actor_lookup[key] = (info, prio)

                if ct_event_name == 'StartPipelineExecution':
                    resource_name = req_params.get('name', '')
                    for svc in ['backend', 'frontend', 'cms']:
                        if svc in resource_name.lower():
                            if 'build' in resource_name.lower():
                                maybe_add(('build', svc, time_bucket), actor_info, priority)
                            elif 'deploy' in resource_name.lower() and actor_type in ('human', 'dashboard'):
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

        return {k: v[0] for k, v in actor_lookup.items()}

    def _extract_actor(self, ct_detail: dict) -> tuple:
        """Extract actor from CloudTrail event"""
        user_identity = ct_detail.get('userIdentity', {})
        user_arn = user_identity.get('arn', '')
        user_type = user_identity.get('type', '')
        username = user_identity.get('userName', '')

        if user_type == 'AWSService':
            return ('AWS', 'service')

        if 'assumed-role' in user_arn:
            parts = user_arn.split('/')
            if len(parts) >= 3:
                role_name = parts[-2] if len(parts) >= 2 else ''
                session_name = parts[-1]

                if '@' in session_name:
                    return (session_name, 'human')

                if session_name.startswith('dashboard-'):
                    email = session_name.replace('dashboard-', '').replace('-at-', '@').replace('-dot-', '.')
                    return (email, 'dashboard')

                if 'dashboard' in role_name.lower() and 'lambda' in role_name.lower():
                    return ('Dashboard', 'dashboard')

                if 'eventbridge' in role_name.lower():
                    return ('EventBridge', 'eventbridge')

                if len(session_name) == 32 and all(c in '0123456789abcdef' for c in session_name.lower()):
                    return ('EventBridge', 'eventbridge')

                if 'codebuild' in role_name.lower():
                    return ('CodeBuild', 'pipeline')

                if 'codepipeline' in role_name.lower():
                    return ('Pipeline', 'pipeline')

        if username:
            if '@' in username:
                return (username, 'human')
            if not username.startswith('AWSReserved'):
                return (username, 'human')

        return (None, None)


# Register the provider
ProviderFactory.register_events_provider('combined', CombinedEventsProvider)
