"""
ArgoCD CD Provider implementation.

Connects to ArgoCD API to retrieve application status, sync history, and trigger syncs.
Used for deploy pipelines - ArgoCD is a CD (Continuous Delivery) tool, not CI.
"""

import os
import json
import requests
from datetime import datetime
from typing import List, Optional, Dict, Any

from providers.base import (
    CIProvider,
    Pipeline,
    PipelineStage,
    PipelineExecution,
    ContainerImage,
    ProviderFactory
)
from app_config import DashboardConfig


class ArgoCDProvider(CIProvider):
    """
    ArgoCD implementation of the CI provider (used for CD/deploy).

    Configuration (from project config or environment):
    - argocd_url: Base URL of ArgoCD API (e.g., https://argocd.example.com)
    - argocd_token_secret: AWS Secrets Manager secret name for API token
    - app_name_pattern: Pattern for app names (default: {env}-{service})
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

        # ArgoCD configuration from environment or config
        self.argocd_url = os.environ.get('ARGOCD_URL', '').rstrip('/')
        self._argocd_token = None
        self._token_secret_name = os.environ.get('ARGOCD_TOKEN_SECRET', '')

        # Session for connection reuse
        self._session = None

    def _get_argocd_token(self) -> str:
        """Get ArgoCD API token from Secrets Manager"""
        if self._argocd_token:
            return self._argocd_token

        # Try environment variable first (for local dev)
        env_token = os.environ.get('ARGOCD_TOKEN')
        if env_token:
            self._argocd_token = env_token
            return self._argocd_token

        # Otherwise, fetch from Secrets Manager
        if self._token_secret_name:
            import boto3
            secrets = boto3.client('secretsmanager', region_name=self.region)
            try:
                response = secrets.get_secret_value(SecretId=self._token_secret_name)
                secret_data = json.loads(response['SecretString'])
                self._argocd_token = secret_data.get('token', secret_data.get('api_token', ''))
            except Exception as e:
                print(f"Error fetching ArgoCD token from Secrets Manager: {e}")
                self._argocd_token = ''

        return self._argocd_token or ''

    def _get_session(self) -> requests.Session:
        """Get authenticated requests session"""
        if self._session is None:
            self._session = requests.Session()
            token = self._get_argocd_token()
            if token:
                self._session.headers['Authorization'] = f'Bearer {token}'
            self._session.headers['Content-Type'] = 'application/json'
            self._session.timeout = 30
        return self._session

    def _argocd_api_call(self, path: str, method: str = 'GET', **kwargs) -> Optional[Dict]:
        """Make an ArgoCD API call"""
        if not self.argocd_url:
            return None

        url = f"{self.argocd_url}/api/v1/{path.lstrip('/')}"
        session = self._get_session()

        try:
            if method == 'GET':
                response = session.get(url, **kwargs)
            elif method == 'POST':
                response = session.post(url, **kwargs)
            else:
                return None

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            print(f"ArgoCD API error: {e}")
            return None
        except Exception as e:
            print(f"ArgoCD request error: {e}")
            return None

    def _get_app_name(self, service: str, env: str = None) -> str:
        """
        Get the ArgoCD application name for a service.

        Uses project's pipeline config if available, otherwise uses default pattern.
        Pattern: {env}-{service} or from config appName
        """
        # Get from project config if available
        project_config = self.config.get_project_config(self.project)
        if project_config and project_config.get('pipelines', {}).get('services', {}).get(service):
            service_config = project_config['pipelines']['services'][service]
            deploy_config = service_config.get('deploy', {})
            if deploy_config.get('provider') == 'argocd' and deploy_config.get('appName'):
                return deploy_config['appName']

        # Default pattern
        if env:
            return f"{env}-{service}"
        return service

    def _map_argocd_status(self, sync_status: str, health_status: str, operation_phase: str = None) -> str:
        """Map ArgoCD status to standard status"""
        # If there's an active operation
        if operation_phase:
            if operation_phase in ('Running', 'Pending'):
                return 'in_progress'
            elif operation_phase == 'Succeeded':
                return 'succeeded'
            elif operation_phase in ('Failed', 'Error'):
                return 'failed'
            elif operation_phase == 'Terminating':
                return 'cancelled'

        # Use health status as primary indicator
        if health_status == 'Healthy':
            return 'succeeded'
        elif health_status == 'Degraded':
            return 'failed'
        elif health_status == 'Progressing':
            return 'in_progress'
        elif health_status in ('Missing', 'Unknown'):
            return 'unknown'

        # Fallback to sync status
        if sync_status == 'Synced':
            return 'succeeded'
        elif sync_status == 'OutOfSync':
            return 'pending'

        return 'unknown'

    def get_build_pipeline(self, service: str) -> Pipeline:
        """
        Get build pipeline information.

        ArgoCD is a CD tool, not CI. Return empty pipeline for builds.
        Use Jenkins or another CI tool for builds.
        """
        return Pipeline(
            name=f"{service}-build",
            pipeline_type='build',
            service=service,
            environment=None,
            console_url=None
        )

    def get_deploy_pipeline(self, env: str, service: str) -> Pipeline:
        """Get deploy pipeline (ArgoCD application) information"""
        app_name = self._get_app_name(service, env)

        # Get application details
        app_data = self._argocd_api_call(f"applications/{app_name}")

        if not app_data:
            return Pipeline(
                name=app_name,
                pipeline_type='deploy',
                service=service,
                environment=env,
                console_url=f"{self.argocd_url}/applications/{app_name}" if self.argocd_url else None
            )

        # Parse application status
        status = app_data.get('status', {})
        sync_status = status.get('sync', {}).get('status', 'Unknown')
        health_status = status.get('health', {}).get('status', 'Unknown')
        operation = status.get('operationState', {})
        operation_phase = operation.get('phase')

        # Build stages from resources
        stages = self._build_stages_from_resources(status.get('resources', []))

        # Get sync history for executions
        history = status.get('history', [])
        executions = self._parse_sync_history(history, app_name)

        # Build console URL
        console_url = f"{self.argocd_url}/applications/{app_name}" if self.argocd_url else None

        # Determine current version (revision)
        current_revision = status.get('sync', {}).get('revision', '')[:8] if status.get('sync', {}).get('revision') else None

        return Pipeline(
            name=app_name,
            pipeline_type='deploy',
            service=service,
            environment=env,
            version=current_revision,
            stages=stages,
            last_execution=executions[0] if executions else None,
            executions=executions[:5],
            console_url=console_url
        )

    def _build_stages_from_resources(self, resources: List[Dict]) -> List[PipelineStage]:
        """Build pipeline stages from ArgoCD resources"""
        stages = []
        resource_types = {}

        # Group resources by kind
        for resource in resources:
            kind = resource.get('kind', 'Unknown')
            health = resource.get('health', {}).get('status', 'Unknown')

            if kind not in resource_types:
                resource_types[kind] = {'total': 0, 'healthy': 0}
            resource_types[kind]['total'] += 1
            if health == 'Healthy':
                resource_types[kind]['healthy'] += 1

        # Create stages from resource types
        for kind, counts in resource_types.items():
            if counts['healthy'] == counts['total']:
                status = 'succeeded'
            elif counts['healthy'] > 0:
                status = 'in_progress'
            else:
                status = 'pending'

            stages.append(PipelineStage(
                name=f"{kind} ({counts['healthy']}/{counts['total']})",
                status=status
            ))

        return stages

    def _parse_sync_history(self, history: List[Dict], app_name: str) -> List[PipelineExecution]:
        """Parse ArgoCD sync history into PipelineExecution objects"""
        executions = []

        for entry in sorted(history, key=lambda x: x.get('id', 0), reverse=True):
            revision = entry.get('revision', '')
            deployed_at = entry.get('deployedAt')
            source = entry.get('source', {})

            # Parse timestamp
            started_at = None
            if deployed_at:
                try:
                    started_at = datetime.fromisoformat(deployed_at.replace('Z', '+00:00'))
                except:
                    pass

            executions.append(PipelineExecution(
                execution_id=str(entry.get('id', '')),
                status='succeeded',  # History only shows successful syncs
                started_at=started_at,
                finished_at=started_at,  # ArgoCD doesn't track duration
                duration_seconds=None,
                commit_sha=revision[:8] if revision else None,
                commit_message=None,
                commit_author=entry.get('initiatedBy', {}).get('username'),
                commit_url=None,
                console_url=f"{self.argocd_url}/applications/{app_name}?view=timeline" if self.argocd_url else None,
                trigger_type='argocd_sync'
            ))

        return executions

    def get_pipeline_executions(self, pipeline_name: str, max_results: int = 5) -> List[PipelineExecution]:
        """Get recent executions (sync history) for an ArgoCD application"""
        app_data = self._argocd_api_call(f"applications/{pipeline_name}")

        if not app_data:
            return []

        history = app_data.get('status', {}).get('history', [])
        return self._parse_sync_history(history, pipeline_name)[:max_results]

    def trigger_build(self, service: str, user_email: str, image_tag: str = None, source_revision: str = None) -> dict:
        """
        Trigger a build.

        ArgoCD is a CD tool, not CI. Builds should be triggered via Jenkins or another CI tool.
        """
        return {
            'error': 'ArgoCD is a CD tool. Use Jenkins or another CI provider for builds.',
            'service': service
        }

    def trigger_deploy(self, env: str, service: str, user_email: str) -> dict:
        """Trigger a deploy (ArgoCD sync)"""
        app_name = self._get_app_name(service, env)

        # Check if app exists first
        app_data = self._argocd_api_call(f"applications/{app_name}")
        if not app_data:
            return {'error': f'Application not found: {app_name}', 'application': app_name}

        try:
            # Trigger sync
            response = self._argocd_api_call(
                f"applications/{app_name}/sync",
                method='POST',
                json={
                    'revision': '',  # Use HEAD
                    'prune': False,
                    'dryRun': False,
                    'strategy': {
                        'hook': {}  # Default strategy
                    }
                }
            )

            return {
                'success': True,
                'application': app_name,
                'service': service,
                'environment': env,
                'triggeredBy': user_email,
                'message': 'Sync triggered successfully'
            }

        except Exception as e:
            return {'error': str(e), 'application': app_name}

    def get_build_logs(self, service: str, execution_id: str = None) -> List[dict]:
        """
        Get build logs.

        ArgoCD doesn't have build logs - it's a CD tool.
        Returns empty list.
        """
        return []

    def get_images(self, service: str) -> List[ContainerImage]:
        """
        Get container images.

        ArgoCD doesn't manage images directly.
        Returns empty list - use ECR or registry provider.
        """
        return []


# Register the provider
ProviderFactory.register_ci_provider('argocd', ArgoCDProvider)
