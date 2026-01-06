"""
AWS CodePipeline CI/CD Provider implementation.
"""

import boto3
import json
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

from providers.base import (
    CIProvider,
    Pipeline,
    PipelineStage,
    PipelineExecution,
    ContainerImage,
    ProviderFactory
)
from config import DashboardConfig
from utils.aws import get_cross_account_client, build_sso_console_url


class CodePipelineProvider(CIProvider):
    """
    AWS CodePipeline implementation of the CI provider.
    Handles build and deploy pipelines in shared-services account.
    """

    def __init__(self, config: DashboardConfig):
        self.config = config
        self.region = config.region
        self.shared_account = config.shared_services_account
        self.github_org = config.github_org

    def _get_codepipeline_client(self):
        """Get CodePipeline client for shared-services account"""
        return boto3.client('codepipeline', region_name=self.region)

    def _get_codebuild_client(self):
        """Get CodeBuild client for shared-services account"""
        return boto3.client('codebuild', region_name=self.region)

    def _get_logs_client(self):
        """Get CloudWatch Logs client"""
        return boto3.client('logs', region_name=self.region)

    def _get_ecr_client(self):
        """Get ECR client"""
        return boto3.client('ecr', region_name=self.region)

    def get_build_pipeline(self, service: str) -> Pipeline:
        """Get build pipeline information for a service"""
        pipeline_name = self.config.get_build_pipeline_name(service)
        return self._get_pipeline_info('build', pipeline_name, service)

    def get_deploy_pipeline(self, env: str, service: str) -> Pipeline:
        """Get deploy pipeline information for a service in an environment"""
        pipeline_name = self.config.get_deploy_pipeline_name(env, service)
        return self._get_pipeline_info('deploy', pipeline_name, service, env)

    def _get_pipeline_info(self, pipeline_type: str, pipeline_name: str, service: str, env: str = None) -> Pipeline:
        """Get pipeline information"""
        codepipeline = self._get_codepipeline_client()

        try:
            # Get pipeline state
            state = codepipeline.get_pipeline_state(name=pipeline_name)

            # Get executions
            executions = self.get_pipeline_executions(pipeline_name)

            # Build stages
            stages = []
            for stage in state.get('stageStates', []):
                stages.append(PipelineStage(
                    name=stage['stageName'],
                    status=stage.get('latestExecution', {}).get('status', 'Unknown').lower()
                ))

            # Get build logs for build pipelines
            build_logs = None
            if pipeline_type == 'build':
                build_logs = self.get_build_logs(service)

            console_url = build_sso_console_url(
                self.config.sso_portal_url,
                self.shared_account,
                f"https://{self.region}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline_name}/view?region={self.region}"
            )

            return Pipeline(
                name=pipeline_name,
                pipeline_type=pipeline_type,
                service=service,
                environment=env,
                version=state.get('pipelineVersion'),
                stages=stages,
                last_execution=executions[0] if executions else None,
                executions=executions,
                console_url=console_url,
                build_logs=build_logs
            )

        except codepipeline.exceptions.PipelineNotFoundException:
            return Pipeline(
                name=pipeline_name,
                pipeline_type=pipeline_type,
                service=service,
                environment=env,
                console_url=None
            )

    def get_pipeline_executions(self, pipeline_name: str, max_results: int = 5) -> List[PipelineExecution]:
        """Get recent executions for a pipeline"""
        codepipeline = self._get_codepipeline_client()

        try:
            response = codepipeline.list_pipeline_executions(
                pipelineName=pipeline_name,
                maxResults=max_results
            )

            executions = []
            for exec_summary in response.get('pipelineExecutionSummaries', []):
                exec_id = exec_summary['pipelineExecutionId']

                # Calculate duration
                duration = None
                if exec_summary.get('lastUpdateTime') and exec_summary.get('startTime'):
                    if exec_summary.get('status') != 'InProgress':
                        duration = int((exec_summary['lastUpdateTime'] - exec_summary['startTime']).total_seconds())

                # Extract commit info
                commit_sha = None
                commit_message = None
                commit_author = None
                commit_url = None

                if exec_summary.get('sourceRevisions'):
                    rev = exec_summary['sourceRevisions'][0]
                    commit_sha = rev.get('revisionId', '')

                    # Parse revision summary (may be JSON from GitHub)
                    revision_summary = rev.get('revisionSummary', '')
                    if revision_summary.startswith('{'):
                        try:
                            summary_json = json.loads(revision_summary)
                            commit_message = summary_json.get('CommitMessage', '')[:100]
                            commit_author = summary_json.get('AuthorDisplayName')
                        except:
                            commit_message = revision_summary[:100]
                    else:
                        commit_message = revision_summary[:100] if revision_summary else None

                    # Build GitHub URL if we have org configured
                    if commit_sha and self.github_org and not commit_sha.startswith('sha256:'):
                        # Extract service from pipeline name
                        service = pipeline_name.replace(f'{self.config.project_name}-build-', '')
                        repo_name = self.config.get_ecr_repo(service)
                        commit_url = f"https://github.com/{self.github_org}/{repo_name}/commit/{commit_sha}"

                # Determine trigger type
                trigger = exec_summary.get('trigger', {})
                trigger_type = trigger.get('triggerType', 'Unknown')

                console_url = build_sso_console_url(
                    self.config.sso_portal_url,
                    self.shared_account,
                    f"https://{self.region}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline_name}/executions/{exec_id}/timeline?region={self.region}"
                )

                executions.append(PipelineExecution(
                    execution_id=exec_id,
                    status=exec_summary.get('status', 'Unknown').lower(),
                    started_at=exec_summary.get('startTime'),
                    finished_at=exec_summary.get('lastUpdateTime'),
                    duration_seconds=duration,
                    commit_sha=commit_sha[:8] if commit_sha else None,
                    commit_message=commit_message,
                    commit_author=commit_author,
                    commit_url=commit_url,
                    console_url=console_url,
                    trigger_type=trigger_type
                ))

            return executions

        except Exception as e:
            print(f"Error getting pipeline executions: {e}")
            return []

    def trigger_build(self, service: str, user_email: str, image_tag: str = None, source_revision: str = None) -> dict:
        """Trigger a build pipeline"""
        pipeline_name = self.config.get_build_pipeline_name(service)

        try:
            # Use STS assume-role with email in RoleSessionName for CloudTrail attribution
            sanitized_email = user_email.replace('@', '-at-').replace('.', '-dot-')[:64] if user_email else 'unknown'
            session_name = f"dashboard-{sanitized_email}"

            # Get action role ARN from environment
            import os
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
                    region_name=self.region,
                    aws_access_key_id=credentials['AccessKeyId'],
                    aws_secret_access_key=credentials['SecretAccessKey'],
                    aws_session_token=credentials['SessionToken']
                )
            else:
                codepipeline = self._get_codepipeline_client()

            # Build parameters
            params = {
                'name': pipeline_name,
                'variables': [
                    {'name': 'ImageTag', 'value': image_tag or 'latest'},
                    {'name': 'TriggeredBy', 'value': user_email or 'unknown'}
                ]
            }

            # Add source revision if provided
            if source_revision:
                params['sourceRevisions'] = [{
                    'actionName': 'SourceCode',
                    'revisionType': 'COMMIT_ID',
                    'revisionValue': source_revision
                }]

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

    def trigger_deploy(self, env: str, service: str, user_email: str) -> dict:
        """Trigger a deploy pipeline"""
        pipeline_name = self.config.get_deploy_pipeline_name(env, service)

        try:
            sanitized_email = user_email.replace('@', '-at-').replace('.', '-dot-')[:64] if user_email else 'unknown'
            session_name = f"dashboard-{sanitized_email}"

            import os
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
                    region_name=self.region,
                    aws_access_key_id=credentials['AccessKeyId'],
                    aws_secret_access_key=credentials['SecretAccessKey'],
                    aws_session_token=credentials['SessionToken']
                )
            else:
                codepipeline = self._get_codepipeline_client()

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

    def get_build_logs(self, service: str, execution_id: str = None) -> List[dict]:
        """Get build logs for a service"""
        codebuild = self._get_codebuild_client()
        logs_client = self._get_logs_client()

        try:
            # CodeBuild project naming pattern
            build_project = f"{self.config.project_name}-build-{service}-arm64"

            builds = codebuild.list_builds_for_project(
                projectName=build_project,
                sortOrder='DESCENDING'
            )

            if not builds.get('ids'):
                return []

            latest_build = codebuild.batch_get_builds(ids=[builds['ids'][0]])['builds'][0]
            log_group = latest_build.get('logs', {}).get('groupName')
            log_stream = latest_build.get('logs', {}).get('streamName')

            if not log_group or not log_stream:
                return []

            log_events = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                limit=100,
                startFromHead=False
            )

            logs = []
            for event in log_events.get('events', []):
                logs.append({
                    'timestamp': datetime.utcfromtimestamp(event['timestamp'] / 1000).isoformat() + 'Z',
                    'message': event['message'].strip()
                })

            return logs

        except Exception as e:
            return [{'timestamp': datetime.utcnow().isoformat() + 'Z', 'message': f'Error fetching logs: {str(e)}'}]

    def get_images(self, service: str) -> List[ContainerImage]:
        """Get container images for a service from ECR"""
        ecr = self._get_ecr_client()
        repo_name = self.config.get_ecr_repo(service)

        try:
            # Fetch all images with pagination
            all_images = []
            paginator = ecr.get_paginator('describe_images')
            for page in paginator.paginate(repositoryName=repo_name):
                all_images.extend(page['imageDetails'])

            # Sort by push date descending and take top 10
            sorted_images = sorted(
                all_images,
                key=lambda x: x.get('imagePushedAt', datetime.min),
                reverse=True
            )[:10]

            images = []
            for img in sorted_images:
                size_bytes = img.get('imageSizeInBytes', 0)
                images.append(ContainerImage(
                    digest=img['imageDigest'],
                    tags=img.get('imageTags', []),
                    pushed_at=img.get('imagePushedAt'),
                    size_bytes=size_bytes,
                    size_mb=round(size_bytes / 1024 / 1024, 2) if size_bytes else None
                ))

            return images

        except ecr.exceptions.RepositoryNotFoundException:
            return []


# Register the provider
ProviderFactory.register_ci_provider('codepipeline', CodePipelineProvider)
