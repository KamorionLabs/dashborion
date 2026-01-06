"""
GitHub Actions CI/CD Provider implementation.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Optional

from providers.base import (
    CIProvider,
    Pipeline,
    PipelineStage,
    PipelineExecution,
    ContainerImage,
    ProviderFactory
)
from config import DashboardConfig


class GitHubActionsProvider(CIProvider):
    """
    GitHub Actions implementation of the CI provider.
    Uses GitHub REST API to interact with workflows.
    """

    def __init__(self, config: DashboardConfig):
        self.config = config
        self.github_owner = config.ci_provider.github_owner
        self.repo_pattern = config.ci_provider.github_repo_pattern
        self.token_secret = config.ci_provider.github_token_secret
        self._token = None

    def _get_token(self) -> str:
        """Get GitHub token from Secrets Manager"""
        if self._token:
            return self._token

        if not self.token_secret:
            raise ValueError("GitHub token secret not configured")

        import boto3
        secrets = boto3.client('secretsmanager', region_name=self.config.region)
        response = secrets.get_secret_value(SecretId=self.token_secret)
        secret_value = json.loads(response['SecretString'])
        self._token = secret_value.get('GITHUB_TOKEN', secret_value.get('token'))
        return self._token

    def _get_repo_name(self, service: str) -> str:
        """Get repository name from pattern"""
        return self.repo_pattern.format(
            project=self.config.project_name,
            service=service
        )

    def _api_request(self, endpoint: str, method: str = 'GET', data: dict = None) -> dict:
        """Make GitHub API request"""
        token = self._get_token()
        url = f"https://api.github.com{endpoint}"

        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Dashboard-API'
        }

        req_data = json.dumps(data).encode() if data else None
        request = urllib.request.Request(url, data=req_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            raise Exception(f"GitHub API error {e.code}: {error_body}")

    def get_build_pipeline(self, service: str) -> Pipeline:
        """Get build workflow information for a service"""
        repo = self._get_repo_name(service)

        try:
            # Get workflows for the repo
            workflows = self._api_request(f"/repos/{self.github_owner}/{repo}/actions/workflows")

            # Find build workflow (commonly named 'build', 'ci', or 'docker')
            build_workflow = None
            for wf in workflows.get('workflows', []):
                name_lower = wf['name'].lower()
                if any(kw in name_lower for kw in ['build', 'ci', 'docker', 'release']):
                    build_workflow = wf
                    break

            if not build_workflow:
                # Use first workflow if no build workflow found
                build_workflow = workflows.get('workflows', [{}])[0]

            workflow_id = build_workflow.get('id')
            if not workflow_id:
                return Pipeline(
                    name=f"{repo}-build",
                    pipeline_type='build',
                    service=service
                )

            # Get recent runs
            runs = self._api_request(
                f"/repos/{self.github_owner}/{repo}/actions/workflows/{workflow_id}/runs?per_page=5"
            )

            executions = []
            for run in runs.get('workflow_runs', []):
                duration = None
                if run.get('updated_at') and run.get('created_at'):
                    try:
                        start = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
                        end = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
                        duration = int((end - start).total_seconds())
                    except:
                        pass

                executions.append(PipelineExecution(
                    execution_id=str(run['id']),
                    status=self._map_status(run.get('conclusion', run.get('status'))),
                    started_at=datetime.fromisoformat(run['created_at'].replace('Z', '+00:00')) if run.get('created_at') else None,
                    finished_at=datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00')) if run.get('updated_at') else None,
                    duration_seconds=duration,
                    commit_sha=run.get('head_sha', '')[:8],
                    commit_message=run.get('head_commit', {}).get('message', '')[:100],
                    commit_author=run.get('head_commit', {}).get('author', {}).get('name'),
                    commit_url=f"https://github.com/{self.github_owner}/{repo}/commit/{run.get('head_sha', '')}",
                    console_url=run.get('html_url'),
                    trigger_type=run.get('event', 'unknown')
                ))

            return Pipeline(
                name=build_workflow.get('name', f"{repo}-build"),
                pipeline_type='build',
                service=service,
                stages=[],  # GitHub Actions doesn't have stages like CodePipeline
                last_execution=executions[0] if executions else None,
                executions=executions,
                console_url=f"https://github.com/{self.github_owner}/{repo}/actions/workflows/{build_workflow.get('path', '').split('/')[-1]}"
            )

        except Exception as e:
            print(f"Error getting GitHub workflow: {e}")
            return Pipeline(
                name=f"{repo}-build",
                pipeline_type='build',
                service=service
            )

    def get_deploy_pipeline(self, env: str, service: str) -> Pipeline:
        """Get deploy workflow information for a service in an environment"""
        repo = self._get_repo_name(service)

        try:
            workflows = self._api_request(f"/repos/{self.github_owner}/{repo}/actions/workflows")

            # Find deploy workflow (commonly named 'deploy', 'cd', or includes env name)
            deploy_workflow = None
            for wf in workflows.get('workflows', []):
                name_lower = wf['name'].lower()
                if any(kw in name_lower for kw in ['deploy', 'cd', env.lower()]):
                    deploy_workflow = wf
                    break

            if not deploy_workflow:
                return Pipeline(
                    name=f"{repo}-deploy-{env}",
                    pipeline_type='deploy',
                    service=service,
                    environment=env
                )

            workflow_id = deploy_workflow.get('id')

            # Get recent runs
            runs = self._api_request(
                f"/repos/{self.github_owner}/{repo}/actions/workflows/{workflow_id}/runs?per_page=5"
            )

            executions = []
            for run in runs.get('workflow_runs', []):
                # Filter by environment if possible (via deployment environments)
                run_env = run.get('environment')
                if run_env and run_env.lower() != env.lower():
                    continue

                duration = None
                if run.get('updated_at') and run.get('created_at'):
                    try:
                        start = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
                        end = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
                        duration = int((end - start).total_seconds())
                    except:
                        pass

                executions.append(PipelineExecution(
                    execution_id=str(run['id']),
                    status=self._map_status(run.get('conclusion', run.get('status'))),
                    started_at=datetime.fromisoformat(run['created_at'].replace('Z', '+00:00')) if run.get('created_at') else None,
                    finished_at=datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00')) if run.get('updated_at') else None,
                    duration_seconds=duration,
                    commit_sha=run.get('head_sha', '')[:8],
                    commit_message=run.get('head_commit', {}).get('message', '')[:100],
                    commit_author=run.get('head_commit', {}).get('author', {}).get('name'),
                    commit_url=f"https://github.com/{self.github_owner}/{repo}/commit/{run.get('head_sha', '')}",
                    console_url=run.get('html_url'),
                    trigger_type=run.get('event', 'unknown')
                ))

            return Pipeline(
                name=deploy_workflow.get('name', f"{repo}-deploy-{env}"),
                pipeline_type='deploy',
                service=service,
                environment=env,
                stages=[],
                last_execution=executions[0] if executions else None,
                executions=executions,
                console_url=f"https://github.com/{self.github_owner}/{repo}/actions/workflows/{deploy_workflow.get('path', '').split('/')[-1]}"
            )

        except Exception as e:
            print(f"Error getting GitHub deploy workflow: {e}")
            return Pipeline(
                name=f"{repo}-deploy-{env}",
                pipeline_type='deploy',
                service=service,
                environment=env
            )

    def _map_status(self, gh_status: str) -> str:
        """Map GitHub status to standard status"""
        status_map = {
            'success': 'succeeded',
            'failure': 'failed',
            'cancelled': 'cancelled',
            'skipped': 'cancelled',
            'in_progress': 'in_progress',
            'queued': 'pending',
            'pending': 'pending',
            'waiting': 'pending'
        }
        return status_map.get(gh_status, 'unknown')

    def get_pipeline_executions(self, pipeline_name: str, max_results: int = 5) -> List[PipelineExecution]:
        """Get recent executions for a pipeline"""
        # This is handled in get_build_pipeline and get_deploy_pipeline
        # as GitHub API requires repo + workflow info
        return []

    def trigger_build(self, service: str, user_email: str, image_tag: str = None, source_revision: str = None) -> dict:
        """Trigger a build workflow"""
        repo = self._get_repo_name(service)

        try:
            # Get workflows to find build workflow
            workflows = self._api_request(f"/repos/{self.github_owner}/{repo}/actions/workflows")

            build_workflow = None
            for wf in workflows.get('workflows', []):
                name_lower = wf['name'].lower()
                if any(kw in name_lower for kw in ['build', 'ci', 'docker']):
                    build_workflow = wf
                    break

            if not build_workflow:
                return {'error': 'No build workflow found', 'service': service}

            workflow_id = build_workflow['id']

            # Trigger workflow dispatch
            self._api_request(
                f"/repos/{self.github_owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
                method='POST',
                data={
                    'ref': 'main',  # or configurable default branch
                    'inputs': {
                        'image_tag': image_tag or 'latest',
                        'triggered_by': user_email or 'unknown'
                    }
                }
            )

            return {
                'success': True,
                'workflow': build_workflow['name'],
                'service': service,
                'imageTag': image_tag,
                'triggeredBy': user_email
            }

        except Exception as e:
            return {'error': str(e), 'service': service}

    def trigger_deploy(self, env: str, service: str, user_email: str) -> dict:
        """Trigger a deploy workflow"""
        repo = self._get_repo_name(service)

        try:
            workflows = self._api_request(f"/repos/{self.github_owner}/{repo}/actions/workflows")

            deploy_workflow = None
            for wf in workflows.get('workflows', []):
                name_lower = wf['name'].lower()
                if any(kw in name_lower for kw in ['deploy', 'cd', env.lower()]):
                    deploy_workflow = wf
                    break

            if not deploy_workflow:
                return {'error': f'No deploy workflow found for {env}', 'service': service}

            workflow_id = deploy_workflow['id']

            self._api_request(
                f"/repos/{self.github_owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
                method='POST',
                data={
                    'ref': 'main',
                    'inputs': {
                        'environment': env,
                        'triggered_by': user_email or 'unknown'
                    }
                }
            )

            return {
                'success': True,
                'workflow': deploy_workflow['name'],
                'service': service,
                'environment': env,
                'triggeredBy': user_email,
                'action': 'deploy-latest'
            }

        except Exception as e:
            return {'error': str(e), 'service': service}

    def get_build_logs(self, service: str, execution_id: str = None) -> List[dict]:
        """Get build logs for a service"""
        repo = self._get_repo_name(service)

        try:
            # Get recent workflow runs
            runs = self._api_request(
                f"/repos/{self.github_owner}/{repo}/actions/runs?per_page=1"
            )

            if not runs.get('workflow_runs'):
                return []

            run_id = execution_id or runs['workflow_runs'][0]['id']

            # Get jobs for this run
            jobs = self._api_request(
                f"/repos/{self.github_owner}/{repo}/actions/runs/{run_id}/jobs"
            )

            logs = []
            for job in jobs.get('jobs', []):
                # Get logs URL (requires downloading)
                logs.append({
                    'timestamp': job.get('started_at', datetime.utcnow().isoformat()) + 'Z',
                    'message': f"Job '{job['name']}': {job.get('conclusion', job.get('status', 'unknown'))}"
                })

                # Add step summaries
                for step in job.get('steps', []):
                    logs.append({
                        'timestamp': step.get('started_at', datetime.utcnow().isoformat()),
                        'message': f"  Step '{step['name']}': {step.get('conclusion', step.get('status', 'unknown'))}"
                    })

            return logs

        except Exception as e:
            return [{'timestamp': datetime.utcnow().isoformat() + 'Z', 'message': f'Error fetching logs: {str(e)}'}]

    def get_images(self, service: str) -> List[ContainerImage]:
        """Get container images from GitHub Container Registry (ghcr.io)"""
        repo = self._get_repo_name(service)

        try:
            # Get packages for the repo
            packages = self._api_request(
                f"/orgs/{self.github_owner}/packages/container/{repo}/versions"
            )

            images = []
            for pkg in packages[:10]:  # Limit to 10
                images.append(ContainerImage(
                    digest=pkg.get('name', ''),
                    tags=pkg.get('metadata', {}).get('container', {}).get('tags', []),
                    pushed_at=datetime.fromisoformat(pkg['created_at'].replace('Z', '+00:00')) if pkg.get('created_at') else None
                ))

            return images

        except Exception as e:
            print(f"Error getting GHCR images: {e}")
            return []


# Register the provider
ProviderFactory.register_ci_provider('github_actions', GitHubActionsProvider)
