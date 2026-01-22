"""
Jenkins CI/CD Provider implementation.

Connects to Jenkins API to retrieve job status, build history, and logs.
Supports triggering builds for services configured with Jenkins.
"""

import os
import json
import requests
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import quote

from providers.base import (
    CIProvider,
    Pipeline,
    PipelineStage,
    PipelineExecution,
    ContainerImage,
    ProviderFactory
)
from app_config import DashboardConfig


class JenkinsProvider(CIProvider):
    """
    Jenkins implementation of the CI provider.

    Configuration (from global CI Provider or project config):
    - jenkins_url: Base URL of Jenkins (e.g., https://jenkins.example.com)
    - jenkins_user: Username for API authentication
    - jenkins_token: API token for authentication
    - job_path_pattern: Pattern for job paths (default: {project}/{env}/deploy-{service})
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region

        # Jenkins configuration - loaded lazily from Secrets Manager or config
        self._jenkins_url = None
        self._jenkins_user = None
        self._jenkins_token = None
        self._credentials_loaded = False

        # Get token secret name from config, global settings, or env var fallback
        self._token_secret_name = self._resolve_token_secret_name()

        # Session for connection reuse
        self._session = None

    @classmethod
    def from_provider_config(cls, config: DashboardConfig, provider_config: Dict[str, Any]) -> 'JenkinsProvider':
        """
        Create a JenkinsProvider from a global CI Provider configuration.

        Args:
            config: Dashboard config
            provider_config: CI Provider config dict with url, user, token

        Returns:
            JenkinsProvider instance with credentials pre-loaded
        """
        instance = cls.__new__(cls)
        instance.config = config
        instance.project = '__global__'
        instance.region = config.region

        # Set credentials directly from provider config
        instance._jenkins_url = (provider_config.get('url') or '').rstrip('/')
        instance._jenkins_user = provider_config.get('user') or ''
        instance._jenkins_token = provider_config.get('token') or ''
        instance._credentials_loaded = True
        instance._token_secret_name = None
        instance._session = None

        return instance

    def _resolve_token_secret_name(self) -> str:
        """
        Resolve Jenkins token secret name from multiple sources:
        1. ci_provider.jenkins_token_secret (explicit config)
        2. DynamoDB global settings: {secretsPrefix}/jenkins-token
        3. Environment variable JENKINS_TOKEN_SECRET
        """
        # 1. Check explicit config
        if self.config.ci_provider and self.config.ci_provider.jenkins_token_secret:
            return self.config.ci_provider.jenkins_token_secret

        # 2. Check env var (could be set explicitly)
        env_secret = os.environ.get('JENKINS_TOKEN_SECRET', '')
        if env_secret:
            return env_secret

        # 3. Build from global settings secretsPrefix
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb', region_name=self.region)
            table_name = os.environ.get('CONFIG_TABLE_NAME', 'ddb-dashborion-shared-config')
            table = dynamodb.Table(table_name)
            response = table.get_item(Key={'pk': 'GLOBAL', 'sk': 'settings'})
            item = response.get('Item', {})
            prefix = item.get('secretsPrefix', '/dashborion').rstrip('/')
            return f"{prefix}/jenkins-token"
        except Exception as e:
            print(f"Error fetching secretsPrefix from DynamoDB: {e}")
            return '/dashborion/jenkins-token'

    @property
    def jenkins_url(self) -> str:
        """Get Jenkins URL (lazy load from Secrets Manager or env)"""
        if not self._credentials_loaded:
            self._load_credentials()
        return self._jenkins_url or ''

    @property
    def jenkins_user(self) -> str:
        """Get Jenkins user (lazy load from Secrets Manager or env)"""
        if not self._credentials_loaded:
            self._load_credentials()
        return self._jenkins_user or ''

    def _load_credentials(self):
        """Load Jenkins credentials from Secrets Manager, config, or environment variables."""
        if self._credentials_loaded:
            return

        self._credentials_loaded = True

        # First try Secrets Manager if secret name is configured
        if self._token_secret_name:
            try:
                import boto3
                secrets = boto3.client('secretsmanager', region_name=self.region)
                response = secrets.get_secret_value(SecretId=self._token_secret_name)
                secret_data = json.loads(response['SecretString'])

                self._jenkins_url = secret_data.get('url', '').rstrip('/')
                self._jenkins_user = secret_data.get('user', '')
                self._jenkins_token = secret_data.get('token', secret_data.get('api_token', ''))

                if self._jenkins_url and self._jenkins_user and self._jenkins_token:
                    print(f"Jenkins credentials loaded from Secrets Manager: {self._token_secret_name}")
                    return
            except Exception as e:
                print(f"Error loading Jenkins credentials from Secrets Manager: {e}")

        # Fall back to config values (from DynamoDB Config Registry)
        if self.config.ci_provider:
            self._jenkins_url = self._jenkins_url or (self.config.ci_provider.jenkins_url or '').rstrip('/')
            self._jenkins_user = self._jenkins_user or self.config.ci_provider.jenkins_user or ''

        # Final fallback to environment variables
        self._jenkins_url = self._jenkins_url or os.environ.get('JENKINS_URL', '').rstrip('/')
        self._jenkins_user = self._jenkins_user or os.environ.get('JENKINS_USER', '')
        self._jenkins_token = self._jenkins_token or os.environ.get('JENKINS_TOKEN', '')

    def _get_jenkins_token(self) -> str:
        """Get Jenkins API token from Secrets Manager"""
        if self._jenkins_token:
            return self._jenkins_token

        # Try environment variable first (for local dev)
        env_token = os.environ.get('JENKINS_TOKEN')
        if env_token:
            self._jenkins_token = env_token
            return self._jenkins_token

        # Otherwise, fetch from Secrets Manager
        if self._token_secret_name:
            import boto3
            secrets = boto3.client('secretsmanager', region_name=self.region)
            try:
                response = secrets.get_secret_value(SecretId=self._token_secret_name)
                secret_data = json.loads(response['SecretString'])
                self._jenkins_token = secret_data.get('token', secret_data.get('api_token', ''))
            except Exception as e:
                print(f"Error fetching Jenkins token from Secrets Manager: {e}")
                self._jenkins_token = ''

        return self._jenkins_token or ''

    def _get_session(self) -> requests.Session:
        """Get authenticated requests session"""
        if self._session is None:
            self._session = requests.Session()
            if self.jenkins_user and self._get_jenkins_token():
                self._session.auth = (self.jenkins_user, self._get_jenkins_token())
            self._session.headers['Content-Type'] = 'application/json'
            self._session.timeout = 30
        return self._session

    def _jenkins_api_call(self, path: str, method: str = 'GET', **kwargs) -> Optional[Dict]:
        """Make a Jenkins API call"""
        if not self.jenkins_url:
            return None

        url = f"{self.jenkins_url}/{path.lstrip('/')}"
        session = self._get_session()

        try:
            if method == 'GET':
                response = session.get(url, **kwargs)
            elif method == 'POST':
                response = session.post(url, **kwargs)
            else:
                return None

            response.raise_for_status()

            # Return JSON for API calls, text for logs
            if 'api/json' in path:
                return response.json()
            return {'text': response.text}

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            print(f"Jenkins API error: {e}")
            return None
        except Exception as e:
            print(f"Jenkins request error: {e}")
            return None

    def _get_job_path(self, service: str, env: str = None, pipeline_type: str = 'build') -> str:
        """
        Get the Jenkins job path for a service.

        Uses project's pipeline config if available, otherwise uses default pattern.
        Pattern: RubixDeployment/EKS/{ENV}/deploy-{service}
        """
        # Get from project config if available
        project_config = self.config.get_project_config(self.project)
        if project_config and project_config.get('pipelines', {}).get('services', {}).get(service):
            service_config = project_config['pipelines']['services'][service]
            category_config = service_config.get(pipeline_type, {})
            if category_config.get('provider') == 'jenkins' and category_config.get('jobPath'):
                return category_config['jobPath']

        # Default pattern for Rubix
        if env:
            env_upper = env.upper().replace('-', '_')
            return f"RubixDeployment/EKS/{env_upper}/deploy-{service}"
        return f"RubixDeployment/build-{service}"

    def _encode_job_path(self, job_path: str) -> str:
        """Encode job path for Jenkins API (prefix with job/ and replace / with /job/)"""
        if not job_path:
            return ''
        parts = job_path.split('/')
        # Jenkins API expects: job/Folder1/job/Folder2/job/JobName
        return 'job/' + '/job/'.join(parts)

    def _map_jenkins_status(self, result: str, building: bool = False) -> str:
        """Map Jenkins result to standard status"""
        if building:
            return 'in_progress'

        status_map = {
            'SUCCESS': 'succeeded',
            'FAILURE': 'failed',
            'UNSTABLE': 'failed',
            'ABORTED': 'cancelled',
            'NOT_BUILT': 'pending',
            None: 'pending'
        }
        return status_map.get(result, 'unknown')

    def get_build_pipeline(self, service: str) -> Pipeline:
        """Get build pipeline information for a service"""
        job_path = self._get_job_path(service, pipeline_type='build')
        return self._get_pipeline_info('build', job_path, service)

    def get_deploy_pipeline(self, env: str, service: str) -> Pipeline:
        """Get deploy pipeline information for a service in an environment"""
        job_path = self._get_job_path(service, env, pipeline_type='deploy')
        return self._get_pipeline_info('deploy', job_path, service, env)

    def _get_pipeline_info(self, pipeline_type: str, job_path: str, service: str, env: str = None) -> Pipeline:
        """Get pipeline information from Jenkins"""
        encoded_path = self._encode_job_path(job_path)

        # Get job info
        job_data = self._jenkins_api_call(f"{encoded_path}/api/json?depth=1")

        if not job_data:
            return Pipeline(
                name=job_path,
                pipeline_type=pipeline_type,
                service=service,
                environment=env,
                console_url=f"{self.jenkins_url}/job/{encoded_path.replace('/job/', '/')}" if self.jenkins_url else None
            )

        # Get executions (builds)
        executions = self._parse_builds(job_data.get('builds', [])[:5], job_path)

        # Build console URL
        console_url = job_data.get('url', f"{self.jenkins_url}/job/{encoded_path.replace('/job/', '/')}")

        # Get last build info
        last_build = job_data.get('lastBuild')
        last_execution = None
        if last_build and executions:
            last_execution = executions[0]

        return Pipeline(
            name=job_path,
            pipeline_type=pipeline_type,
            service=service,
            environment=env,
            version=None,
            stages=[],  # Jenkins pipelines have stages but require deeper API call
            last_execution=last_execution,
            executions=executions,
            console_url=console_url
        )

    def _parse_builds(self, builds: List[Dict], job_path: str) -> List[PipelineExecution]:
        """Parse Jenkins builds into PipelineExecution objects"""
        executions = []
        encoded_path = self._encode_job_path(job_path)

        for build in builds:
            build_number = build.get('number')
            result = build.get('result')
            building = build.get('building', False)

            # Parse timestamps
            timestamp = build.get('timestamp')
            started_at = datetime.utcfromtimestamp(timestamp / 1000) if timestamp else None
            duration = build.get('duration', 0)
            duration_seconds = duration // 1000 if duration and not building else None
            finished_at = None
            if started_at and duration_seconds:
                finished_at = datetime.utcfromtimestamp((timestamp + duration) / 1000)

            # Parse changeset for commit info
            commit_sha = None
            commit_message = None
            commit_author = None
            commit_url = None

            changesets = build.get('changeSets', [])
            if changesets:
                for changeset in changesets:
                    items = changeset.get('items', [])
                    if items:
                        first_commit = items[0]
                        commit_sha = first_commit.get('commitId', '')[:8]
                        commit_message = first_commit.get('msg', '')[:100]
                        author_info = first_commit.get('author', {})
                        commit_author = author_info.get('fullName') or author_info.get('id')
                        break

            # Parse trigger/cause
            trigger_type = 'unknown'
            actions = build.get('actions', [])
            for action in actions:
                if action is None:
                    continue
                causes = action.get('causes', [])
                for cause in causes:
                    short_desc = cause.get('shortDescription', '').lower()
                    if 'manually' in short_desc or 'user' in short_desc:
                        trigger_type = 'manual'
                    elif 'scm' in short_desc or 'push' in short_desc or 'commit' in short_desc:
                        trigger_type = 'webhook'
                    elif 'timer' in short_desc or 'schedule' in short_desc:
                        trigger_type = 'scheduled'
                    elif 'upstream' in short_desc:
                        trigger_type = 'upstream'
                    break

            console_url = build.get('url', f"{self.jenkins_url}/job/{encoded_path.replace('/job/', '/')}/{build_number}")

            executions.append(PipelineExecution(
                execution_id=str(build_number),
                status=self._map_jenkins_status(result, building),
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                commit_sha=commit_sha,
                commit_message=commit_message,
                commit_author=commit_author,
                commit_url=commit_url,
                console_url=console_url,
                trigger_type=trigger_type
            ))

        return executions

    def get_pipeline_executions(self, pipeline_name: str, max_results: int = 5) -> List[PipelineExecution]:
        """Get recent executions for a pipeline"""
        encoded_path = self._encode_job_path(pipeline_name)

        # Get job with builds
        job_data = self._jenkins_api_call(
            f"{encoded_path}/api/json?tree=builds[number,result,building,timestamp,duration,changeSets[items[commitId,msg,author[fullName,id]]],actions[causes[shortDescription]]]{{0,{max_results}}}"
        )

        if not job_data:
            return []

        return self._parse_builds(job_data.get('builds', []), pipeline_name)

    def trigger_build(self, service: str, user_email: str, image_tag: str = None, source_revision: str = None) -> dict:
        """Trigger a build pipeline"""
        job_path = self._get_job_path(service, pipeline_type='build')
        return self._trigger_job(job_path, service, user_email, {
            'IMAGE_TAG': image_tag or 'latest',
            'SOURCE_REVISION': source_revision or '',
            'TRIGGERED_BY': user_email or 'dashboard'
        })

    def trigger_deploy(self, env: str, service: str, user_email: str) -> dict:
        """Trigger a deploy pipeline"""
        job_path = self._get_job_path(service, env, pipeline_type='deploy')
        return self._trigger_job(job_path, service, user_email, {
            'ENVIRONMENT': env,
            'TRIGGERED_BY': user_email or 'dashboard'
        })

    def _trigger_job(self, job_path: str, service: str, user_email: str, params: Dict[str, str]) -> dict:
        """Trigger a Jenkins job with parameters"""
        encoded_path = self._encode_job_path(job_path)

        # Check if job exists first
        job_data = self._jenkins_api_call(f"{encoded_path}/api/json")
        if not job_data:
            return {'error': f'Job not found: {job_path}', 'pipeline': job_path}

        # Determine if job has parameters
        has_params = any(
            action.get('parameterDefinitions')
            for action in job_data.get('actions', [])
            if action and 'parameterDefinitions' in action
        )

        try:
            if has_params:
                # Build with parameters
                response = self._jenkins_api_call(
                    f"{encoded_path}/buildWithParameters",
                    method='POST',
                    params=params
                )
            else:
                # Simple build
                response = self._jenkins_api_call(
                    f"{encoded_path}/build",
                    method='POST'
                )

            # Jenkins returns 201 with queue location
            return {
                'success': True,
                'pipeline': job_path,
                'service': service,
                'triggeredBy': user_email,
                'message': 'Build triggered successfully'
            }

        except Exception as e:
            return {'error': str(e), 'pipeline': job_path}

    def get_build_logs(self, service: str, execution_id: str = None) -> List[dict]:
        """Get build logs for a service"""
        job_path = self._get_job_path(service, pipeline_type='build')
        encoded_path = self._encode_job_path(job_path)

        # Get latest build if no execution_id
        build_number = execution_id or 'lastBuild'

        # Get console output
        response = self._jenkins_api_call(f"{encoded_path}/{build_number}/consoleText")

        if not response or 'text' not in response:
            return []

        # Parse log lines (last 100 lines)
        lines = response['text'].split('\n')[-100:]
        logs = []

        for line in lines:
            if line.strip():
                logs.append({
                    'timestamp': datetime.utcnow().isoformat() + 'Z',  # Jenkins console doesn't have timestamps by default
                    'message': line.rstrip()
                })

        return logs

    def get_images(self, service: str) -> List[ContainerImage]:
        """
        Get container images for a service from registry.

        For Jenkins, images are typically stored in ECR after build.
        This method delegates to ECR if available, otherwise returns empty.
        """
        # Jenkins doesn't manage images directly - check if we can access ECR
        ecr_repo = self.config.get_ecr_repo(self.project, service) if hasattr(self.config, 'get_ecr_repo') else None

        if not ecr_repo:
            return []

        try:
            import boto3
            ecr = boto3.client('ecr', region_name=self.region)

            # Fetch images from ECR
            all_images = []
            paginator = ecr.get_paginator('describe_images')
            for page in paginator.paginate(repositoryName=ecr_repo):
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

        except Exception as e:
            print(f"Error fetching images from ECR: {e}")
            return []


    # =========================================================================
    # Discovery and Parameter Methods (for Admin UI and CLI)
    # =========================================================================

    def discover_jobs(
        self,
        folder_path: Optional[str] = None,
        include_params: bool = True,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Discover jobs in a Jenkins folder with optional parameter definitions.

        Args:
            folder_path: Folder path (e.g., 'RubixDeployment/EKS/STAGING')
            include_params: Include parameter definitions for each job
            limit: Maximum number of jobs to return

        Returns:
            Dict with 'jobs', 'folders', 'currentPath'
        """
        if folder_path:
            encoded_path = self._encode_job_path(folder_path)
            path = f"{encoded_path}/api/json"
        else:
            path = "api/json"

        # Request jobs with basic info and optionally parameter definitions
        if include_params:
            tree = f"jobs[name,url,_class,color,lastBuild[number,result,timestamp],property[parameterDefinitions[name,type,defaultParameterValue[value],choices,description]]]{{0,{limit}}}"
        else:
            tree = f"jobs[name,url,_class,color,lastBuild[number,result,timestamp]]{{0,{limit}}}"

        data = self._jenkins_api_call(f"{path}?tree={tree}")

        if not data:
            return {
                'jobs': [],
                'folders': [],
                'currentPath': folder_path or '',
                'error': f"Path not found: {folder_path}" if folder_path else None
            }

        jobs = []
        folders = []

        for item in data.get('jobs', []):
            item_class = item.get('_class', '')
            name = item.get('name', '')

            # Build full path
            full_path = f"{folder_path}/{name}" if folder_path else name

            if 'Folder' in item_class or 'OrganizationFolder' in item_class:
                folders.append({
                    'name': name,
                    'fullPath': full_path,
                    'type': 'folder',
                })
            else:
                job_info = {
                    'name': name,
                    'fullPath': full_path,
                    'type': self._get_job_type(item_class),
                    'url': item.get('url'),
                }

                # Add last build info
                last_build = item.get('lastBuild')
                if last_build:
                    job_info['lastBuild'] = {
                        'number': last_build.get('number'),
                        'result': last_build.get('result'),
                        'timestamp': last_build.get('timestamp'),
                    }

                # Add parameter definitions if requested
                if include_params:
                    params = []
                    for prop in item.get('property', []):
                        if not prop:
                            continue
                        for param_def in prop.get('parameterDefinitions', []):
                            param = {
                                'name': param_def.get('name'),
                                'type': self._get_param_type(param_def.get('type', '')),
                                'default': param_def.get('defaultParameterValue', {}).get('value') if param_def.get('defaultParameterValue') else None,
                                'description': param_def.get('description', ''),
                            }
                            if param_def.get('choices'):
                                param['choices'] = param_def['choices']
                            params.append(param)
                    if params:
                        job_info['parameters'] = params

                jobs.append(job_info)

        return {
            'jobs': jobs,
            'folders': folders,
            'currentPath': folder_path or '',
        }

    def _get_job_type(self, class_name: str) -> str:
        """Convert Jenkins class to readable job type."""
        if 'WorkflowJob' in class_name:
            return 'pipeline'
        elif 'FreeStyleProject' in class_name:
            return 'freestyle'
        elif 'WorkflowMultiBranchProject' in class_name:
            return 'multibranch'
        elif 'MatrixProject' in class_name:
            return 'matrix'
        return 'job'

    def _get_param_type(self, type_class: str) -> str:
        """Convert Jenkins parameter class to readable type."""
        type_class = type_class.replace('ParameterDefinition', '')
        mappings = {
            'String': 'string',
            'Boolean': 'boolean',
            'Choice': 'choice',
            'Password': 'password',
            'Text': 'text',
            'File': 'file',
        }
        for key, value in mappings.items():
            if key in type_class:
                return value
        return 'string'

    def get_job_with_params(self, job_path: str) -> Dict[str, Any]:
        """
        Get job details including parameter definitions.

        Args:
            job_path: Full job path (e.g., 'RubixDeployment/EKS/STAGING/deploy-hybris')

        Returns:
            Dict with job info and 'parameters' list
        """
        encoded_path = self._encode_job_path(job_path)
        tree = "name,fullName,url,description,buildable,property[parameterDefinitions[name,type,defaultParameterValue[value],choices,description]]"

        data = self._jenkins_api_call(f"{encoded_path}/api/json?tree={tree}")

        if not data:
            return {'error': f"Job not found: {job_path}"}

        # Extract parameter definitions
        parameters = []
        for prop in data.get('property', []):
            if not prop:
                continue
            for param_def in prop.get('parameterDefinitions', []):
                param = {
                    'name': param_def.get('name'),
                    'type': self._get_param_type(param_def.get('type', '')),
                    'default': param_def.get('defaultParameterValue', {}).get('value') if param_def.get('defaultParameterValue') else None,
                    'description': param_def.get('description', ''),
                }
                if param_def.get('choices'):
                    param['choices'] = param_def['choices']
                parameters.append(param)

        return {
            'name': data.get('name'),
            'fullPath': data.get('fullName'),
            'url': data.get('url'),
            'description': data.get('description', ''),
            'buildable': data.get('buildable', True),
            'parameters': parameters,
        }

    def get_builds_filtered(
        self,
        job_path: str,
        filter_params: Optional[Dict[str, str]] = None,
        limit: int = 20,
        result_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get build history with parameter values, optionally filtered.

        Args:
            job_path: Full job path
            filter_params: Filter builds by parameter values (e.g., {'Webshop': 'MI2'})
            limit: Maximum builds to return
            result_filter: Filter by result (SUCCESS, FAILURE, UNSTABLE)

        Returns:
            List of builds with parameters
        """
        encoded_path = self._encode_job_path(job_path)

        # Request more builds than limit to account for filtering
        fetch_limit = limit * 3 if filter_params else limit
        tree = f"allBuilds[number,result,building,timestamp,duration,url,actions[_class,parameters[name,value],causes[shortDescription,userId,userName]]]{{0,{fetch_limit}}}"

        data = self._jenkins_api_call(f"{encoded_path}/api/json?tree={tree}")

        if not data:
            return []

        builds = []
        for build in data.get('allBuilds', []):
            # Extract parameters
            params = {}
            causes = []
            for action in build.get('actions', []):
                if not action:
                    continue
                if action.get('_class') == 'hudson.model.ParametersAction':
                    for p in action.get('parameters', []):
                        params[p['name']] = p['value']
                elif 'CauseAction' in action.get('_class', ''):
                    for cause in action.get('causes', []):
                        causes.append({
                            'description': cause.get('shortDescription', ''),
                            'userId': cause.get('userId'),
                            'userName': cause.get('userName'),
                        })

            # Apply result filter
            result = build.get('result')
            if result_filter and result != result_filter:
                continue

            # Apply parameter filter
            if filter_params:
                match = True
                for key, value in filter_params.items():
                    param_value = params.get(key, '')
                    # Support comma-separated values (e.g., Webshop: "MI1,MI2,MI3")
                    if ',' in str(param_value):
                        param_values = [v.strip() for v in str(param_value).split(',')]
                        if value not in param_values:
                            match = False
                            break
                    elif str(param_value) != str(value):
                        match = False
                        break
                if not match:
                    continue

            # Format timestamp
            timestamp = build.get('timestamp')
            dt = None
            if timestamp:
                dt = datetime.utcfromtimestamp(timestamp / 1000)

            # Format duration
            duration_ms = build.get('duration', 0)
            duration_formatted = self._format_duration(duration_ms) if duration_ms else '-'

            builds.append({
                'number': build.get('number'),
                'result': result,
                'building': build.get('building', False),
                'timestamp': timestamp,
                'datetime': dt.isoformat() if dt else None,
                'duration': duration_ms // 1000 if duration_ms else None,
                'durationFormatted': duration_formatted,
                'url': build.get('url'),
                'parameters': params,
                'causes': causes,
            })

            if len(builds) >= limit:
                break

        return builds

    def _format_duration(self, ms: int) -> str:
        """Format duration in milliseconds to human readable."""
        if not ms:
            return '-'
        seconds = ms // 1000
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        seconds = seconds % 60
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}h {minutes}m"

    def get_parameter_values(
        self,
        job_path: str,
        param_name: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get unique values used for a parameter across recent builds.

        Args:
            job_path: Full job path
            param_name: Parameter name to analyze
            limit: Number of recent builds to analyze

        Returns:
            List of unique values with usage count, sorted by frequency
        """
        builds = self.get_builds_filtered(job_path, limit=limit)

        value_counts = {}
        for build in builds:
            value = build['parameters'].get(param_name)
            if value:
                # Handle comma-separated values
                if ',' in str(value):
                    for v in str(value).split(','):
                        v = v.strip()
                        value_counts[v] = value_counts.get(v, 0) + 1
                else:
                    value_counts[str(value)] = value_counts.get(str(value), 0) + 1

        # Sort by frequency (most used first)
        sorted_values = sorted(value_counts.items(), key=lambda x: -x[1])

        return [{'value': v, 'count': c} for v, c in sorted_values]


# Register the provider
ProviderFactory.register_ci_provider('jenkins', JenkinsProvider)
