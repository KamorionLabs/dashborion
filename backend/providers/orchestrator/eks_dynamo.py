"""
AWS EKS DynamoDB Provider - Hybrid provider for K8s state.

Reads K8s state data from DynamoDB (cached by Step Functions) and automatically
triggers Step Functions for fresh data when cache is missing or expired.

Implements OrchestratorProvider interface for compatibility with Dashborion.

Data format in DynamoDB:
- pk: {project}#{env} (e.g., 'mro-mi2#nh-staging')
- sk: check:k8s:{type}:current (e.g., 'check:k8s:pods:current')
- Cluster-wide: pk: _cluster#{cluster_name}, sk: check:k8s:nodes:current
"""

import os
import json
import time
import boto3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from providers.base import (
    OrchestratorProvider,
    Service,
    ServiceDetails,
    ServiceTask,
    ServiceDeployment,
    K8sNode,
    K8sNodePod,
    K8sService,
    K8sIngress,
    K8sIngressRule,
    K8sPod,
    K8sDeployment,
    ProviderFactory,
)
from app_config import DashboardConfig


# DynamoDB table name
TABLE_NAME = os.environ.get('OPS_DASHBOARD_TABLE', 'ops-dashboard-shared-state')

# Default cache TTL in seconds (1 hour)
DEFAULT_CACHE_TTL_SECONDS = 3600

# Step Function execution timeout
SFN_EXECUTION_TIMEOUT = 120


class DataStatus(Enum):
    """Status of data retrieval"""
    OK = "ok"
    REFRESHING = "refreshing"
    STALE = "stale"
    ERROR = "error"
    NO_DATA = "no_data"


@dataclass
class DataResult:
    """Result of data fetch operation"""
    status: DataStatus
    data: Any = None
    error: Optional[str] = None
    last_updated: Optional[str] = None
    is_stale: bool = False
    refresh_triggered: bool = False

    def to_dict(self) -> dict:
        return {
            'status': self.status.value,
            'data': self.data,
            'error': self.error,
            'last_updated': self.last_updated,
            'is_stale': self.is_stale,
            'refresh_triggered': self.refresh_triggered,
        }


# Check type to Step Function name mapping
CHECK_TYPE_TO_SFN = {
    'pods': 'k8s-pods-readiness-checker',
    'services': 'k8s-services-checker',
    'ingress': 'k8s-ingress-status-checker',
    'pvc': 'k8s-pvc-status-checker',
    'secrets': 'k8s-secrets-sync-checker',
    'nodes': 'k8s-nodes-checker',
}


def _convert_decimals(obj):
    """Convert Decimal objects to int/float for JSON serialization"""
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj


def _parse_iso_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime"""
    if not timestamp_str:
        return None
    try:
        # Handle various ISO formats
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return None


def _is_data_stale(updated_at: str, ttl_seconds: int) -> bool:
    """Check if data is stale based on TTL"""
    if not updated_at:
        return True

    last_updated = _parse_iso_timestamp(updated_at)
    if not last_updated:
        return True

    # Make sure we compare timezone-aware datetimes
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_seconds = (now - last_updated).total_seconds()
    return age_seconds > ttl_seconds


class EKSDynamoProvider(OrchestratorProvider):
    """
    Hybrid provider for K8s state that reads from DynamoDB and automatically
    triggers Step Functions for data refresh when needed.

    Features:
    - Reads cached data from DynamoDB
    - Auto-refresh via Step Function if data missing or expired
    - Configurable cache TTL (default 1 hour)
    - Robust error handling with graceful degradation

    DynamoDB pk/sk format:
    - Namespace-scoped: {project}#{env} | check:k8s:{pods|services|pvc|ingress|secrets}:current
    - Cluster-wide: _cluster#{cluster_name} | check:k8s:nodes:current
    """

    def __init__(
        self,
        config: DashboardConfig = None,
        project: str = None,
        table_name: str = None,
        region: str = None,
        account_id: str = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        auto_refresh: bool = True,
    ):
        """
        Initialize the EKS DynamoDB provider.

        Args:
            config: Dashboard config (for ProviderFactory compatibility)
            project: Project name (e.g., 'mro-mi2')
            table_name: DynamoDB table name
            region: AWS region
            account_id: AWS account ID for Step Function ARNs
            cache_ttl_seconds: Cache TTL in seconds (default 3600 = 1 hour)
            auto_refresh: Auto-trigger Step Function refresh if data missing/stale
        """
        self.config = config
        self.project = project
        self.table_name = table_name or TABLE_NAME
        self.region = region or (config.region if config else None) or os.environ.get('AWS_REGION', 'eu-central-1')
        self.account_id = account_id or os.environ.get('AWS_ACCOUNT_ID')
        self.cache_ttl_seconds = cache_ttl_seconds
        self.auto_refresh = auto_refresh
        self._dynamodb = None
        self._sfn_client = None
        self._table = None

    @property
    def dynamodb(self):
        if self._dynamodb is None:
            self._dynamodb = boto3.resource('dynamodb', region_name=self.region)
        return self._dynamodb

    @property
    def table(self):
        if self._table is None:
            self._table = self.dynamodb.Table(self.table_name)
        return self._table

    @property
    def sfn_client(self):
        if self._sfn_client is None:
            self._sfn_client = boto3.client('stepfunctions', region_name=self.region)
        return self._sfn_client

    # =========================================================================
    # Key Building
    # =========================================================================

    def _build_pk(self, env: str) -> str:
        """Build partition key for namespace-scoped data"""
        return f"{self.project}#{env}"

    def _build_cluster_pk(self, cluster_name: str) -> str:
        """Build partition key for cluster-wide data"""
        return f"_cluster#{cluster_name}"

    def _build_sk(self, check_type: str) -> str:
        """Build sort key for current state"""
        return f"check:k8s:{check_type}:current"

    # =========================================================================
    # Config Helpers
    # =========================================================================

    def _get_cluster_name(self, env: str) -> Optional[str]:
        """Get cluster name from config for an environment"""
        if self.config:
            env_config = self.config.get_environment(self.project, env)
            if env_config:
                return env_config.cluster_name or self.config.get_cluster_name(self.project, env)
        return None

    def _get_namespace(self, env: str) -> str:
        """Get namespace from config for an environment"""
        if self.config:
            env_config = self.config.get_environment(self.project, env)
            if env_config and env_config.namespace:
                return env_config.namespace
        return 'hybris'  # Default namespace

    def _get_cross_account_role(self, env: str) -> Optional[str]:
        """Get cross-account role ARN from config.
        Uses config.get_read_role_arn_for_env() which resolves:
        1. environment.readRoleArn (if set)
        2. crossAccountRoles[accountId].readRoleArn (fallback)
        """
        if self.config:
            env_config = self.config.get_environment(self.project, env)
            if env_config:
                return self.config.get_read_role_arn_for_env(
                    self.project, env, env_config.account_id
                )
        return None

    # =========================================================================
    # DynamoDB Operations
    # =========================================================================

    def _get_item(self, pk: str, sk: str) -> Optional[Dict[str, Any]]:
        """Get item from DynamoDB and convert decimals"""
        try:
            response = self.table.get_item(Key={'pk': pk, 'sk': sk})
            if 'Item' in response:
                return _convert_decimals(response['Item'])
            return None
        except Exception as e:
            print(f"[EKSDynamoProvider] Error fetching {pk}/{sk}: {e}")
            return None

    # =========================================================================
    # Step Function Refresh
    # =========================================================================

    def _trigger_refresh(
        self,
        check_type: str,
        env: str,
        cluster_name: str,
        namespace: str,
        wait: bool = True,
    ) -> DataResult:
        """
        Trigger Step Function to refresh data.

        Args:
            check_type: Type of check (pods, services, etc.)
            env: Environment name
            cluster_name: EKS cluster name
            namespace: K8s namespace
            wait: Wait for completion (default True)

        Returns:
            DataResult with refreshed data or error
        """
        sfn_name = CHECK_TYPE_TO_SFN.get(check_type)
        if not sfn_name:
            return DataResult(
                status=DataStatus.ERROR,
                error=f"Unknown check type: {check_type}"
            )

        if not self.account_id:
            return DataResult(
                status=DataStatus.ERROR,
                error="AWS_ACCOUNT_ID not configured for Step Function execution"
            )

        sfn_arn = f"arn:aws:states:{self.region}:{self.account_id}:stateMachine:ops-dashboard-{sfn_name}"

        # Build Step Function input
        sfn_input = {
            'Project': self.project,
            'Env': env,
            'ClusterName': cluster_name,
            'Namespace': namespace,
        }

        # Add cross-account role if configured
        cross_account_role = self._get_cross_account_role(env)
        if cross_account_role:
            sfn_input['CrossAccountRoleArn'] = cross_account_role

        print(f"[EKSDynamoProvider] Triggering refresh: {sfn_name} with input {sfn_input}")

        try:
            response = self.sfn_client.start_execution(
                stateMachineArn=sfn_arn,
                input=json.dumps(sfn_input),
            )
            execution_arn = response['executionArn']
            print(f"[EKSDynamoProvider] Started execution: {execution_arn}")
        except Exception as e:
            print(f"[EKSDynamoProvider] Failed to start execution: {e}")
            return DataResult(
                status=DataStatus.ERROR,
                error=f"Failed to trigger refresh: {str(e)}"
            )

        if not wait:
            return DataResult(
                status=DataStatus.REFRESHING,
                refresh_triggered=True,
                error=f"Refresh triggered, execution: {execution_arn}"
            )

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < SFN_EXECUTION_TIMEOUT:
            try:
                status_response = self.sfn_client.describe_execution(executionArn=execution_arn)
                status = status_response['status']

                if status == 'SUCCEEDED':
                    # Parse output and extract data
                    output = json.loads(status_response.get('output', '{}'))
                    print(f"[EKSDynamoProvider] Execution succeeded")

                    # Return the payload from output
                    payload = output.get('Payload', output.get('payload', output))
                    return DataResult(
                        status=DataStatus.OK,
                        data=payload,
                        refresh_triggered=True,
                        last_updated=datetime.now(timezone.utc).isoformat(),
                    )

                elif status in ('FAILED', 'TIMED_OUT', 'ABORTED'):
                    error_msg = status_response.get('error', 'Unknown error')
                    cause = status_response.get('cause', '')
                    print(f"[EKSDynamoProvider] Execution {status}: {error_msg} - {cause}")
                    return DataResult(
                        status=DataStatus.ERROR,
                        error=f"Refresh failed: {status} - {error_msg}",
                        refresh_triggered=True,
                    )

                time.sleep(2)
            except Exception as e:
                print(f"[EKSDynamoProvider] Error checking execution status: {e}")
                time.sleep(2)

        return DataResult(
            status=DataStatus.ERROR,
            error=f"Refresh timed out after {SFN_EXECUTION_TIMEOUT}s",
            refresh_triggered=True,
        )

    # =========================================================================
    # Core Data Retrieval with Auto-Refresh
    # =========================================================================

    def _get_data_with_refresh(
        self,
        check_type: str,
        env: str,
        cluster_name: str = None,
        namespace: str = None,
        force_refresh: bool = False,
    ) -> DataResult:
        """
        Get data from DynamoDB with automatic refresh if needed.

        Logic:
        1. Try to fetch from DynamoDB
        2. If no data and auto_refresh enabled -> trigger Step Function
        3. If data is stale (>TTL) and auto_refresh enabled -> trigger refresh
        4. If data has error status -> return error but with data if available
        5. Return data with appropriate status

        Args:
            check_type: Type of check (pods, services, nodes, etc.)
            env: Environment name
            cluster_name: EKS cluster name (required for nodes)
            namespace: K8s namespace
            force_refresh: Force refresh even if data exists

        Returns:
            DataResult with data and status
        """
        # Resolve cluster name if not provided
        if not cluster_name:
            cluster_name = self._get_cluster_name(env)

        if not cluster_name:
            return DataResult(
                status=DataStatus.ERROR,
                error=f"Cluster name not configured for project={self.project}, env={env}"
            )

        # Resolve namespace
        if not namespace:
            namespace = self._get_namespace(env)

        # Build keys based on check type
        if check_type == 'nodes':
            pk = self._build_cluster_pk(cluster_name)
        else:
            pk = self._build_pk(env)
        sk = self._build_sk(check_type)

        print(f"[EKSDynamoProvider] Fetching {check_type}: pk={pk}, sk={sk}")

        # Fetch from DynamoDB
        item = self._get_item(pk, sk)

        # Check if we have data
        if item is None:
            print(f"[EKSDynamoProvider] No data found for {pk}/{sk}")
            if self.auto_refresh and not force_refresh:
                print(f"[EKSDynamoProvider] Auto-refreshing...")
                return self._trigger_refresh(check_type, env, cluster_name, namespace, wait=True)
            return DataResult(
                status=DataStatus.NO_DATA,
                error="No data available"
            )

        # Extract payload and metadata
        payload = item.get('payload', {})
        updated_at = item.get('updated_at')
        item_status = payload.get('status', 'unknown')

        # Check if data has error status
        if item_status == 'error':
            error_msg = payload.get('error') or payload.get('message') or 'Unknown error'
            print(f"[EKSDynamoProvider] Data has error status: {error_msg}")

            # If auto_refresh enabled, try to refresh
            if self.auto_refresh:
                print(f"[EKSDynamoProvider] Auto-refreshing due to error status...")
                refresh_result = self._trigger_refresh(check_type, env, cluster_name, namespace, wait=True)

                # If refresh succeeded, return fresh data
                if refresh_result.status == DataStatus.OK:
                    return refresh_result

                # If refresh failed, return original error data (don't lose context)
                print(f"[EKSDynamoProvider] Refresh failed: {refresh_result.error}")
                return DataResult(
                    status=DataStatus.ERROR,
                    data=payload,  # Return whatever data we have
                    error=f"{error_msg} (refresh failed: {refresh_result.error})",
                    last_updated=updated_at,
                    refresh_triggered=True,
                )

            return DataResult(
                status=DataStatus.ERROR,
                data=payload,  # Return whatever data we have
                error=error_msg,
                last_updated=updated_at,
            )

        # Check if data is stale
        is_stale = _is_data_stale(updated_at, self.cache_ttl_seconds)

        if force_refresh or (is_stale and self.auto_refresh):
            reason = "force_refresh" if force_refresh else "stale data"
            print(f"[EKSDynamoProvider] Refreshing due to {reason} (age > {self.cache_ttl_seconds}s)")
            refresh_result = self._trigger_refresh(check_type, env, cluster_name, namespace, wait=True)

            # If refresh succeeded, return fresh data
            if refresh_result.status == DataStatus.OK:
                return refresh_result

            # If refresh failed but we have stale data, return stale data with warning
            if payload:
                print(f"[EKSDynamoProvider] Refresh failed, returning stale data")
                return DataResult(
                    status=DataStatus.STALE,
                    data=payload,
                    error=f"Refresh failed: {refresh_result.error}. Returning stale data.",
                    last_updated=updated_at,
                    is_stale=True,
                    refresh_triggered=True,
                )

            return refresh_result

        # Return data (possibly stale if auto_refresh is disabled)
        return DataResult(
            status=DataStatus.OK if not is_stale else DataStatus.STALE,
            data=payload,
            last_updated=updated_at,
            is_stale=is_stale,
        )

    # =========================================================================
    # OrchestratorProvider Interface Implementation
    # =========================================================================

    def get_services(self, env: str) -> Dict[str, Service]:
        """
        Get all services for an environment.
        Returns Dict[str, Service] where key is service name.

        Uses K8s Services data (check:k8s:services:current) for service names,
        and pods data for detailed task information.
        """
        # Get K8s services data (primary source for service names)
        svc_result = self._get_data_with_refresh('services', env)

        if svc_result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not svc_result.data:
            # Fallback to pods-based detection if services data unavailable
            return self._get_services_from_pods(env)

        k8s_services = svc_result.data.get('services', [])
        if not k8s_services:
            return self._get_services_from_pods(env)

        # Get pods data for detailed task information
        pods_result = self._get_data_with_refresh('pods', env)
        pods_data = pods_result.data.get('pods', []) if pods_result.data else []

        # Build a map of selector -> pods for matching
        # K8s services use selectors to match pods
        pods_by_selector_value = {}
        for pod in pods_data:
            labels = pod.get('labels', {})
            # Index by app.kubernetes.io/name and app.kubernetes.io/instance
            for key in ['app.kubernetes.io/name', 'app.kubernetes.io/instance', 'app']:
                if key in labels:
                    selector_val = labels[key]
                    if selector_val not in pods_by_selector_value:
                        pods_by_selector_value[selector_val] = []
                    pods_by_selector_value[selector_val].append(pod)

        cluster_name = self._get_cluster_name(env) or 'unknown'
        services = {}

        for k8s_svc in k8s_services:
            svc_name = k8s_svc.get('name', '')
            if not svc_name:
                continue

            # Get endpoint counts from K8s service data
            endpoints = k8s_svc.get('endpoints', {})
            ready_count = endpoints.get('ready', 0)
            not_ready_count = endpoints.get('notReady', 0)
            total_count = ready_count + not_ready_count

            # Find matching pods using the service's selector
            selector = k8s_svc.get('selector', {})
            matching_pods = []

            # Try to match pods by selector values
            for selector_key, selector_val in selector.items():
                if selector_val in pods_by_selector_value:
                    for pod in pods_by_selector_value[selector_val]:
                        if pod not in matching_pods:
                            matching_pods.append(pod)
                    break  # Found matching pods, no need to try other selectors

            # Build tasks from matching pods
            tasks = []
            for pod in matching_pods:
                pod_status = pod.get('status', 'Unknown')
                tasks.append(ServiceTask(
                    task_id=pod.get('name', ''),
                    status='running' if pod_status == 'Running' else 'pending',
                    desired_status='running',
                    health='healthy' if pod_status == 'Running' else 'unhealthy',
                    az=pod.get('node'),
                    private_ip=pod.get('ip'),
                ))

            # Use pod count as desired if no endpoints info (headless services)
            if total_count == 0 and matching_pods:
                total_count = len(matching_pods)
                ready_count = sum(1 for p in matching_pods if p.get('status') == 'Running')

            services[svc_name] = Service(
                name=svc_name,
                service=svc_name,
                environment=env,
                cluster_name=cluster_name,
                status='ACTIVE' if ready_count > 0 else 'INACTIVE',
                desired_count=total_count,
                running_count=ready_count,
                pending_count=not_ready_count,
                tasks=tasks,
                selector=selector,
            )

        return services

    def _get_services_from_pods(self, env: str) -> Dict[str, Service]:
        """
        Fallback method: Get services by grouping pods.
        Used when K8s services data is unavailable.
        """
        result = self._get_data_with_refresh('pods', env)

        if result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not result.data:
            return {}

        pods_data = result.data.get('pods', [])

        # Group pods by extracting deployment/statefulset name from pod name
        services_map = {}
        for pod in pods_data:
            pod_name = pod.get('name', '')
            if not pod_name:
                continue

            # Extract component name from pod name
            # StatefulSet: hybris-bo-0 -> hybris-bo (last segment is number)
            # Deployment: apache-5688b6db9b-8ls7j -> apache (remove 2 last segments)
            parts = pod_name.rsplit('-', 2)
            if len(parts) >= 3 and parts[-1].isalnum() and not parts[-1].isdigit():
                # Deployment pattern: name-replicaset-pod
                component = parts[0]
            else:
                # StatefulSet pattern: name-index
                parts = pod_name.rsplit('-', 1)
                component = parts[0] if parts[-1].isdigit() else pod_name

            if not component:
                continue

            if component not in services_map:
                services_map[component] = {
                    'pods': [],
                    'ready_count': 0,
                    'total_count': 0,
                }

            services_map[component]['pods'].append(pod)
            services_map[component]['total_count'] += 1
            if pod.get('status') == 'Running':
                ready_str = pod.get('ready', '0/0')
                if '/' in ready_str:
                    ready, total = ready_str.split('/')
                    if ready == total and int(ready) > 0:
                        services_map[component]['ready_count'] += 1

        # Convert to Service objects
        cluster_name = self._get_cluster_name(env) or 'unknown'
        services = {}

        for svc_name, svc_data in services_map.items():
            desired = svc_data['total_count']
            running = svc_data['ready_count']

            tasks = []
            for pod in svc_data['pods']:
                tasks.append(ServiceTask(
                    task_id=pod.get('name', ''),
                    status='running' if pod.get('status') == 'Running' else 'pending',
                    desired_status='running',
                    health='healthy' if pod.get('status') == 'Running' else 'unhealthy',
                    az=pod.get('node'),
                    private_ip=pod.get('ip'),
                ))

            services[svc_name] = Service(
                name=svc_name,
                service=svc_name,
                environment=env,
                cluster_name=cluster_name,
                status='ACTIVE' if running > 0 else 'INACTIVE',
                desired_count=desired,
                running_count=running,
                pending_count=desired - running,
                tasks=tasks,
            )

        return services

    def get_service(self, env: str, service: str) -> Service:
        """Get service information for a specific service"""
        services = self.get_services(env)
        if service in services:
            return services[service]

        cluster_name = self._get_cluster_name(env) or 'unknown'
        return Service(
            name=service,
            service=service,
            environment=env,
            cluster_name=cluster_name,
            status='UNKNOWN',
            desired_count=0,
            running_count=0,
        )

    def get_service_details(self, env: str, service: str) -> ServiceDetails:
        """Get detailed service information"""
        svc = self.get_service(env, service)

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
            deployment_state='stable' if svc.running_count == svc.desired_count else 'in_progress',
        )

    def get_task_details(self, env: str, service: str, task_id: str) -> dict:
        """Get detailed pod information"""
        result = self._get_data_with_refresh('pods', env)

        if result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not result.data:
            return {'error': result.error or 'No data available'}

        pods_data = result.data.get('pods', [])

        for pod in pods_data:
            if pod.get('name') == task_id:
                return {
                    'taskId': task_id,
                    'service': service,
                    'status': pod.get('status'),
                    'ready': pod.get('ready'),
                    'restarts': pod.get('restarts', 0),
                    'node': pod.get('node'),
                    'ip': pod.get('ip'),
                    'containers': pod.get('containers', []),
                    'labels': pod.get('labels', {}),
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }

        return {'error': f'Pod {task_id} not found'}

    def get_service_logs(self, env: str, service: str, lines: int = 50) -> List[dict]:
        """Get recent logs - not available from DynamoDB cache"""
        return [{'message': 'Logs not available from DynamoDB cache. Use kubectl or CloudWatch.'}]

    def scale_service(self, env: str, service: str, replicas: int, user_email: str) -> dict:
        """Scale service - not supported via DynamoDB provider"""
        return {'error': 'Scaling not supported via DynamoDB provider. Use kubectl or ArgoCD.'}

    def force_deployment(self, env: str, service: str, user_email: str) -> dict:
        """Force deployment - not supported via DynamoDB provider"""
        return {'error': 'Force deployment not supported via DynamoDB provider. Use kubectl or ArgoCD.'}

    def get_infrastructure(self, env: str) -> dict:
        """Get infrastructure topology"""
        cluster_name = self._get_cluster_name(env)
        if not cluster_name:
            return {'error': f'Cluster name not configured for project={self.project}, env={env}'}

        result = self._get_data_with_refresh('nodes', env, cluster_name=cluster_name)

        nodes_summary = {}
        if result.status == DataStatus.OK and result.data:
            nodes_summary = result.data.get('summary', {})

        return {
            'environment': env,
            'orchestrator': 'eks',
            'cluster': {'name': cluster_name},
            'nodes': nodes_summary,
            'source': 'dynamodb_cache',
            'data_status': result.status.value,
            'last_updated': result.last_updated,
        }

    def get_metrics(self, env: str, service: str) -> dict:
        """Get service metrics - not available from DynamoDB cache"""
        return {
            'environment': env,
            'service': service,
            'message': 'Metrics not available from DynamoDB cache. Use CloudWatch.',
            'metrics': {},
        }

    # =========================================================================
    # Extended K8s Methods with Auto-Refresh
    # =========================================================================

    def get_pods(self, env: str, namespace: str = None, force_refresh: bool = False) -> Tuple[List[K8sPod], DataResult]:
        """
        Get pods from DynamoDB cache with auto-refresh.

        Returns:
            Tuple of (pods list, DataResult with metadata)
        """
        result = self._get_data_with_refresh('pods', env, namespace=namespace, force_refresh=force_refresh)

        if result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not result.data:
            return [], result

        pods_data = result.data.get('pods', [])
        pods = []

        for pod_data in pods_data:
            pods.append(K8sPod(
                name=pod_data.get('name', ''),
                namespace=pod_data.get('namespace', namespace or ''),
                status=pod_data.get('status', 'Unknown'),
                ready=pod_data.get('ready', '0/0'),
                restarts=pod_data.get('restarts', 0),
                age=pod_data.get('age'),
                ip=pod_data.get('ip'),
                node=pod_data.get('node'),
                containers=pod_data.get('containers', []),
                labels=pod_data.get('labels', {}),
                annotations=pod_data.get('annotations', {}),
            ))

        return pods, result

    def get_k8s_services(self, env: str, namespace: str = None, force_refresh: bool = False) -> Tuple[List[K8sService], DataResult]:
        """Get K8s services from DynamoDB cache with auto-refresh"""
        result = self._get_data_with_refresh('services', env, namespace=namespace, force_refresh=force_refresh)

        if result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not result.data:
            return [], result

        services_data = result.data.get('services', [])
        services = []

        for svc_data in services_data:
            services.append(K8sService(
                name=svc_data.get('name', ''),
                namespace=svc_data.get('namespace', namespace or ''),
                service_type=svc_data.get('type', 'ClusterIP'),
                cluster_ip=svc_data.get('clusterIP'),
                external_ip=svc_data.get('externalIP'),
                ports=svc_data.get('ports', []),
                selector=svc_data.get('selector', {}),
                labels=svc_data.get('labels', {}),
            ))

        return services, result

    def get_ingresses(self, env: str, namespace: str = None, force_refresh: bool = False) -> Tuple[List[K8sIngress], DataResult]:
        """Get ingresses from DynamoDB cache with auto-refresh"""
        result = self._get_data_with_refresh('ingress', env, namespace=namespace, force_refresh=force_refresh)

        if result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not result.data:
            return [], result

        ingresses_raw = result.data.get('ingresses', [])
        ingresses = []

        # Handle both dict format (by type: bo, private, unknown) and list format
        if isinstance(ingresses_raw, dict):
            ingresses_data = list(ingresses_raw.values())
        else:
            ingresses_data = ingresses_raw

        for ing_data in ingresses_data:
            rules = []
            for rule in ing_data.get('rules', []):
                rules.append(K8sIngressRule(
                    host=rule.get('host', '*'),
                    path=rule.get('path', '/'),
                    path_type=rule.get('pathType', 'Prefix'),
                    service_name=rule.get('serviceName'),
                    service_port=rule.get('servicePort'),
                ))

            # Extract load balancer hostname from nested structure or flat field
            lb_data = ing_data.get('loadBalancer', {})
            lb_hostname = lb_data.get('hostname') if isinstance(lb_data, dict) else None
            if not lb_hostname:
                lb_hostname = ing_data.get('loadBalancerHostname')

            ingresses.append(K8sIngress(
                name=ing_data.get('name', ''),
                namespace=ing_data.get('namespace', namespace or ''),
                ingress_class=ing_data.get('class') or ing_data.get('ingressClass'),
                rules=rules,
                tls=ing_data.get('tls', []),
                load_balancer_hostname=lb_hostname,
                load_balancer_ip=ing_data.get('loadBalancerIP'),
                annotations=ing_data.get('annotations', {}),
                labels=ing_data.get('labels', {}),
            ))

        return ingresses, result

    def get_nodes(
        self,
        env: str = None,
        include_metrics: bool = True,
        include_pods: bool = False,
        namespace: str = None,
        cluster_name: str = None,
        force_refresh: bool = False,
    ) -> List[K8sNode]:
        """
        Get nodes from DynamoDB cache with auto-refresh.

        Args:
            env: Environment name
            include_metrics: Ignored (metrics from cache)
            include_pods: Ignored (pods from cache)
            namespace: Ignored (nodes are cluster-wide)
            cluster_name: Optional cluster name override
            force_refresh: Force refresh even if cache is valid
        """
        # Resolve cluster name
        if not cluster_name and env:
            cluster_name = self._get_cluster_name(env)

        if not cluster_name:
            print(f"[EKSDynamoProvider.get_nodes] No cluster_name for project={self.project}, env={env}")
            return []

        result = self._get_data_with_refresh('nodes', env, cluster_name=cluster_name, force_refresh=force_refresh)

        if result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not result.data:
            print(f"[EKSDynamoProvider.get_nodes] No data: {result.status.value} - {result.error}")
            return []

        nodes_data = result.data.get('nodes', [])
        nodes = []

        for node_data in nodes_data:
            node_pods = []
            for pod in node_data.get('pods', []):
                node_pods.append(K8sNodePod(
                    name=pod.get('name', ''),
                    namespace=pod.get('namespace', ''),
                    component=pod.get('component'),
                    status=pod.get('status', 'Running'),
                    ready=pod.get('ready', True),
                    restarts=pod.get('restarts', 0),
                    requests_cpu=pod.get('requestsCpu'),
                    requests_memory=pod.get('requestsMemory'),
                    usage_cpu=pod.get('usageCpu'),
                    usage_memory=pod.get('usageMemory'),
                ))

            nodes.append(K8sNode(
                name=node_data.get('name', ''),
                instance_type=node_data.get('instanceType', 'unknown'),
                instance_type_display=node_data.get('instanceTypeDisplay'),
                zone=node_data.get('zone'),
                region=node_data.get('region'),
                nodegroup=node_data.get('nodegroup'),
                status=node_data.get('status', 'Unknown'),
                capacity_cpu=node_data.get('capacityCpu'),
                capacity_memory=node_data.get('capacityMemory'),
                capacity_pods=node_data.get('capacityPods'),
                allocatable_cpu=node_data.get('allocatableCpu'),
                allocatable_memory=node_data.get('allocatableMemory'),
                allocatable_pods=node_data.get('allocatablePods'),
                usage_cpu=node_data.get('usageCpu'),
                usage_memory=node_data.get('usageMemory'),
                pod_count=node_data.get('podCount', len(node_pods)),
                subnet_id=node_data.get('subnetId'),
                instance_id=node_data.get('instanceId'),
                labels=node_data.get('labels', {}),
                pods=node_pods,
            ))

        return nodes

    def get_pvcs(self, env: str, namespace: str = None, force_refresh: bool = False) -> Tuple[List[dict], DataResult]:
        """
        Get PersistentVolumeClaims from DynamoDB cache with auto-refresh.

        Returns:
            Tuple of (pvcs list, DataResult with metadata)

        Each PVC dict contains:
            name, namespace, status, volume, capacity, accessModes,
            storageClass, volumeMode, age, labels, efsConfig (if EFS)
        """
        result = self._get_data_with_refresh('pvc', env, namespace=namespace, force_refresh=force_refresh)

        if result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not result.data:
            return [], result

        pvcs_data = result.data.get('pvcs', [])
        return pvcs_data, result

    def get_efs_pvcs(self, env: str, namespace: str = None, force_refresh: bool = False) -> List[dict]:
        """
        Get EFS-backed PVCs from DynamoDB cache.

        Filters PVCs by storage class containing 'efs'.

        Returns:
            List of PVC dicts that use EFS storage
        """
        pvcs, result = self.get_pvcs(env, namespace=namespace, force_refresh=force_refresh)

        if not pvcs:
            return []

        # Filter PVCs that use EFS storage class
        efs_pvcs = [
            pvc for pvc in pvcs
            if pvc.get('storageClass', '').lower().startswith('efs')
        ]

        return efs_pvcs

    def get_k8s_summary(self, env: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Get summary of all K8s checks for an environment"""
        check_types = ['pods', 'services', 'ingress', 'pvc', 'secrets']

        summary = {
            'project': self.project,
            'env': env,
            'checks': {},
            'overall_status': 'ok',
            'last_updated': None,
        }

        for check_type in check_types:
            result = self._get_data_with_refresh(check_type, env, force_refresh=force_refresh)

            if result.status == DataStatus.OK and result.data:
                check_status = {
                    'status': result.data.get('status', 'unknown'),
                    'healthy': result.data.get('healthy', False),
                    'summary': result.data.get('summary', {}),
                    'issues_count': len(result.data.get('issues', [])),
                    'updated_at': result.last_updated,
                    'is_stale': result.is_stale,
                }
                summary['checks'][check_type] = check_status

                if result.data.get('status') == 'critical':
                    summary['overall_status'] = 'critical'
                elif result.data.get('status') == 'warning' and summary['overall_status'] != 'critical':
                    summary['overall_status'] = 'warning'

                if result.last_updated:
                    if summary['last_updated'] is None or result.last_updated > summary['last_updated']:
                        summary['last_updated'] = result.last_updated
            else:
                summary['checks'][check_type] = {
                    'status': result.status.value,
                    'healthy': None,
                    'error': result.error,
                }

        # Add nodes
        cluster_name = self._get_cluster_name(env)
        if cluster_name:
            result = self._get_data_with_refresh('nodes', env, cluster_name=cluster_name, force_refresh=force_refresh)

            if result.status == DataStatus.OK and result.data:
                summary['checks']['nodes'] = {
                    'status': result.data.get('status', 'unknown'),
                    'healthy': result.data.get('healthy', False),
                    'summary': result.data.get('summary', {}),
                    'issues_count': len(result.data.get('issues', [])),
                    'updated_at': result.last_updated,
                    'is_stale': result.is_stale,
                }
            else:
                summary['checks']['nodes'] = {
                    'status': result.status.value,
                    'healthy': None,
                    'error': result.error,
                }

        return summary

    # =========================================================================
    # Manual Refresh Methods
    # =========================================================================

    def refresh_all(self, env: str, namespace: str = None, wait: bool = True) -> Dict[str, DataResult]:
        """
        Refresh all check types for an environment.

        Returns:
            Dict mapping check_type to DataResult
        """
        cluster_name = self._get_cluster_name(env)
        if not cluster_name:
            return {'error': DataResult(status=DataStatus.ERROR, error='Cluster name not configured')}

        namespace = namespace or self._get_namespace(env)
        results = {}

        for check_type in CHECK_TYPE_TO_SFN.keys():
            print(f"[EKSDynamoProvider] Refreshing {check_type}...")
            results[check_type] = self._trigger_refresh(
                check_type, env, cluster_name, namespace, wait=wait
            )

        return results

    def refresh_check(
        self,
        check_type: str,
        env: str,
        namespace: str = None,
        wait: bool = True,
    ) -> DataResult:
        """
        Manually trigger a refresh for a specific check type.

        Args:
            check_type: Type of check (pods, services, nodes, etc.)
            env: Environment name
            namespace: K8s namespace (optional)
            wait: Wait for completion

        Returns:
            DataResult with status
        """
        cluster_name = self._get_cluster_name(env)
        if not cluster_name:
            return DataResult(status=DataStatus.ERROR, error='Cluster name not configured')

        namespace = namespace or self._get_namespace(env)
        return self._trigger_refresh(check_type, env, cluster_name, namespace, wait=wait)


# Register the provider with ProviderFactory
ProviderFactory.register_orchestrator_provider('eks', EKSDynamoProvider)
