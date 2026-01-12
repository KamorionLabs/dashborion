"""
AWS EKS Kubernetes Orchestrator Provider implementation.
Uses Kubernetes API via boto3 EKS token and kubernetes client.
"""

import base64
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from providers.base import (
    OrchestratorProvider,
    Service,
    ServiceDetails,
    ServiceTask,
    ServiceDeployment,
    K8sNode,
    K8sService,
    K8sIngress,
    K8sIngressRule,
    K8sPod,
    K8sDeployment,
    K8sPersistentVolume,
    K8sPersistentVolumeClaim,
    ProviderFactory
)
from app_config import DashboardConfig
from utils.aws import get_cross_account_client, get_action_client, build_sso_console_url
from utils.instance_specs import format_instance_type


class EKSProvider(OrchestratorProvider):
    """
    AWS EKS Kubernetes implementation of the orchestrator provider.
    Uses Kubernetes API to manage deployments in EKS clusters.
    """

    def __init__(self, config: DashboardConfig, project: str):
        self.config = config
        self.project = project
        self.region = config.region
        self._k8s_clients = {}  # Cache K8s clients per environment

    def _get_eks_client(self, env: str):
        """Get EKS client for environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client(
            'eks', env_config.account_id, env_config.region,
            project=self.project, env=env
        )

    def _get_k8s_client(self, env: str):
        """
        Get Kubernetes client for EKS cluster.
        Uses EKS token for authentication.
        """
        if env in self._k8s_clients:
            return self._k8s_clients[env]

        try:
            # Import kubernetes client - must be installed in Lambda layer
            from kubernetes import client as k8s_client
            from kubernetes.client import Configuration

            env_config = self.config.get_environment(self.project, env)
            eks = self._get_eks_client(env)

            # Get cluster info - use env-specific cluster name from config
            cluster_name = env_config.cluster_name or self.config.get_cluster_name(self.project, env)
            cluster_info = eks.describe_cluster(name=cluster_name)['cluster']

            # Generate EKS token with assumed role credentials
            # Store env name in env_config for token generation
            env_config.env_name = env
            token = self._get_eks_token(env_config, cluster_name, env_config.region)

            # Configure K8s client
            configuration = Configuration()
            configuration.host = cluster_info['endpoint']
            configuration.verify_ssl = True
            configuration.ssl_ca_cert = self._write_ca_cert(cluster_info['certificateAuthority']['data'])
            configuration.api_key = {"authorization": f"Bearer {token}"}

            api_client = k8s_client.ApiClient(configuration)
            self._k8s_clients[env] = {
                'apps': k8s_client.AppsV1Api(api_client),
                'core': k8s_client.CoreV1Api(api_client),
                'cluster_name': cluster_name,
                'namespace': env_config.namespace or self.config.orchestrator.default_namespace
            }

            return self._k8s_clients[env]

        except ImportError:
            raise RuntimeError("kubernetes package not installed. Add to Lambda layer.")
        except Exception as e:
            raise RuntimeError(f"Failed to create K8s client: {e}")

    def _get_eks_token(self, env_config, cluster_name: str, region: str) -> str:
        """Generate EKS auth token using STS GetCallerIdentity presigned URL

        This implements the same token generation as aws-iam-authenticator.
        Uses STS presigned URL with x-k8s-aws-id header for cluster identification.
        """
        import boto3
        import datetime
        import hashlib
        import hmac
        import urllib.parse

        try:
            # Get assumed role credentials for the target account
            role_arn = self.config.get_read_role_arn_for_env(self.project, env_config.env_name, env_config.account_id)
            if not role_arn:
                role_arn = self.config.get_read_role_arn(env_config.account_id)

            if not role_arn:
                raise ValueError(f"No read role ARN configured for account {env_config.account_id}")

            # Assume role to get temporary credentials
            sts = boto3.client('sts')
            assumed = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName='dashborion-eks-token'
            )
            creds = assumed['Credentials']
            access_key = creds['AccessKeyId']
            secret_key = creds['SecretAccessKey']
            session_token = creds['SessionToken']

            # SigV4 signing for presigned URL
            method = 'GET'
            service = 'sts'
            host = f'sts.{region}.amazonaws.com'
            endpoint = f'https://{host}/'

            # Current time
            t = datetime.datetime.utcnow()
            amz_date = t.strftime('%Y%m%dT%H%M%SZ')
            date_stamp = t.strftime('%Y%m%d')

            # Canonical request components
            canonical_uri = '/'
            algorithm = 'AWS4-HMAC-SHA256'
            credential_scope = f'{date_stamp}/{region}/{service}/aws4_request'

            # Headers to sign - must include x-k8s-aws-id for EKS
            headers_to_sign = {
                'host': host,
                'x-k8s-aws-id': cluster_name
            }
            signed_headers = ';'.join(sorted(headers_to_sign.keys()))
            canonical_headers = ''.join(f'{k}:{v}\n' for k, v in sorted(headers_to_sign.items()))

            # Build canonical querystring (alphabetically sorted, includes auth params except signature)
            query_params = {
                'Action': 'GetCallerIdentity',
                'Version': '2011-06-15',
                'X-Amz-Algorithm': algorithm,
                'X-Amz-Credential': f'{access_key}/{credential_scope}',
                'X-Amz-Date': amz_date,
                'X-Amz-Expires': '60',
                'X-Amz-Security-Token': session_token,
                'X-Amz-SignedHeaders': signed_headers,
            }
            canonical_querystring = '&'.join(
                f'{urllib.parse.quote(k, safe="")}={urllib.parse.quote(v, safe="")}'
                for k, v in sorted(query_params.items())
            )

            # Payload hash (empty for GET with presigned URL uses UNSIGNED-PAYLOAD)
            payload_hash = 'UNSIGNED-PAYLOAD'

            # Build canonical request
            canonical_request = f'{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}'
            canonical_request_hash = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()

            # Create string to sign
            string_to_sign = f'{algorithm}\n{amz_date}\n{credential_scope}\n{canonical_request_hash}'

            # Calculate signature
            def sign(key, msg):
                return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

            k_date = sign(('AWS4' + secret_key).encode('utf-8'), date_stamp)
            k_region = sign(k_date, region)
            k_service = sign(k_region, service)
            k_signing = sign(k_service, 'aws4_request')
            signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

            # Build presigned URL (same order as canonical querystring + signature at end)
            presigned_url = f'{endpoint}?{canonical_querystring}&X-Amz-Signature={signature}'

            # Encode as k8s-aws token format
            token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(
                presigned_url.encode('utf-8')
            ).decode('utf-8').rstrip('=')

            return token

        except Exception as e:
            print(f"Error generating EKS token: {e}")
            import traceback
            traceback.print_exc()
            raise ValueError(f"Failed to generate EKS token: {e}")

    def _write_ca_cert(self, ca_data: str) -> str:
        """Write CA cert to temp file and return path"""
        import tempfile
        import os

        ca_cert = base64.b64decode(ca_data)

        # Write to /tmp (Lambda writable directory)
        cert_path = '/tmp/eks-ca.crt'
        with open(cert_path, 'wb') as f:
            f.write(ca_cert)

        return cert_path

    def get_services(self, env: str) -> Dict[str, Service]:
        """Get all services (deployments) for an environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        result = {}
        for service_name in env_config.services:
            try:
                result[service_name] = self.get_service(env, service_name)
            except Exception as e:
                print(f"Error getting service {service_name}: {e}")
                result[service_name] = Service(
                    name=service_name,
                    service=service_name,
                    environment=env,
                    cluster_name=self.config.get_cluster_name(env),
                    status='error',
                    desired_count=0,
                    running_count=0
                )

        return result

    def get_service(self, env: str, service: str) -> Service:
        """Get service (deployment) information"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            apps_api = k8s['apps']
            core_api = k8s['core']
            namespace = k8s['namespace']
            cluster_name = k8s['cluster_name']

            # Get deployment
            deployment_name = self.config.get_service_name(env, service)
            deployment = apps_api.read_namespaced_deployment(deployment_name, namespace)

            # Get pods for this deployment
            label_selector = f"app={service}"
            pods = core_api.list_namespaced_pod(namespace, label_selector=label_selector)

            tasks = []
            for pod in pods.items:
                # Determine pod status
                phase = pod.status.phase.lower()
                status = 'running' if phase == 'running' else 'pending' if phase == 'pending' else 'stopped'

                # Get container status
                health = 'unknown'
                if pod.status.container_statuses:
                    container = pod.status.container_statuses[0]
                    if container.ready:
                        health = 'healthy'
                    elif container.state.waiting:
                        health = 'unhealthy'

                tasks.append(ServiceTask(
                    task_id=pod.metadata.name,
                    status=status,
                    desired_status='running',
                    health=health,
                    revision=pod.metadata.labels.get('pod-template-hash', ''),
                    is_latest=True,  # Would need to compare with deployment template
                    az=pod.spec.node_name,  # Node name, not AZ
                    private_ip=pod.status.pod_ip,
                    cpu=pod.spec.containers[0].resources.requests.get('cpu', '') if pod.spec.containers[0].resources.requests else None,
                    memory=pod.spec.containers[0].resources.requests.get('memory', '') if pod.spec.containers[0].resources.requests else None,
                    started_at=pod.status.start_time
                ))

            # Build deployment info
            deployments = [ServiceDeployment(
                deployment_id=deployment.metadata.uid,
                status='primary',
                task_definition=deployment.spec.template.spec.containers[0].image,
                revision=str(deployment.metadata.generation),
                desired_count=deployment.spec.replicas or 0,
                running_count=deployment.status.ready_replicas or 0,
                pending_count=(deployment.status.replicas or 0) - (deployment.status.ready_replicas or 0),
                rollout_state='COMPLETED' if deployment.status.ready_replicas == deployment.spec.replicas else 'IN_PROGRESS'
            )]

            console_url = build_sso_console_url(
                self.config.sso_portal_url,
                env_config.account_id,
                f"https://{self.region}.console.aws.amazon.com/eks/home?region={self.region}#/clusters/{cluster_name}/workloads?namespace={namespace}"
            )

            return Service(
                name=deployment_name,
                service=service,
                environment=env,
                cluster_name=cluster_name,
                status='ACTIVE' if deployment.status.ready_replicas else 'INACTIVE',
                desired_count=deployment.spec.replicas or 0,
                running_count=deployment.status.ready_replicas or 0,
                pending_count=(deployment.status.replicas or 0) - (deployment.status.ready_replicas or 0),
                tasks=tasks,
                deployments=deployments,
                task_definition={
                    'image': deployment.spec.template.spec.containers[0].image,
                    'revision': str(deployment.metadata.generation)
                },
                console_url=console_url,
                account_id=env_config.account_id
            )

        except Exception as e:
            raise ValueError(f"Failed to get service {service}: {e}")

    def get_service_details(self, env: str, service: str) -> ServiceDetails:
        """Get detailed service information"""
        svc = self.get_service(env, service)

        try:
            k8s = self._get_k8s_client(env)
            apps_api = k8s['apps']
            core_api = k8s['core']
            namespace = k8s['namespace']

            deployment_name = self.config.get_service_name(env, service)
            deployment = apps_api.read_namespaced_deployment(deployment_name, namespace)

            # Extract environment variables
            env_vars = []
            container = deployment.spec.template.spec.containers[0]
            if container.env:
                for e in container.env:
                    value = e.value or ''
                    name = e.name
                    # Mask sensitive values
                    if any(secret in name.upper() for secret in ['SECRET', 'PASSWORD', 'KEY', 'TOKEN']):
                        value = '***MASKED***'
                    env_vars.append({'name': name, 'value': value, 'type': 'plain'})

            # Extract secrets from envFrom
            secrets = []
            if container.env_from:
                for env_from in container.env_from:
                    if env_from.secret_ref:
                        secrets.append({
                            'name': env_from.secret_ref.name,
                            'type': 'secret'
                        })

            # Get recent events
            events = core_api.list_namespaced_event(
                namespace,
                field_selector=f"involvedObject.name={deployment_name}"
            )

            ecs_events = []
            for event in events.items[:10]:
                ecs_events.append({
                    'id': event.metadata.uid,
                    'createdAt': event.last_timestamp.isoformat() if event.last_timestamp else None,
                    'message': event.message
                })

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
                console_url=svc.console_url,
                account_id=svc.account_id,
                environment_variables=env_vars,
                secrets=secrets,
                ecs_events=ecs_events,
                deployment_state='stable' if svc.running_count == svc.desired_count else 'in_progress'
            )

        except Exception as e:
            # Return basic service info on error
            return ServiceDetails(
                name=svc.name,
                service=svc.service,
                environment=env,
                cluster_name=svc.cluster_name,
                status=svc.status,
                desired_count=svc.desired_count,
                running_count=svc.running_count,
                tasks=svc.tasks,
                deployments=svc.deployments
            )

    def get_task_details(self, env: str, service: str, task_id: str) -> dict:
        """Get detailed pod information"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            k8s = self._get_k8s_client(env)
            core_api = k8s['core']
            namespace = k8s['namespace']

            pod = core_api.read_namespaced_pod(task_id, namespace)

            # Get pod logs
            logs = []
            try:
                log_content = core_api.read_namespaced_pod_log(
                    task_id,
                    namespace,
                    tail_lines=50
                )
                for line in log_content.split('\n'):
                    if line:
                        logs.append({
                            'timestamp': datetime.utcnow().isoformat() + 'Z',
                            'message': line[:500]
                        })
            except Exception as e:
                logs = [{'error': str(e)}]

            # Extract container info
            container = pod.spec.containers[0]
            container_status = pod.status.container_statuses[0] if pod.status.container_statuses else None

            return {
                'taskId': task_id,
                'service': service,
                'cluster': k8s['cluster_name'],
                'namespace': namespace,
                'status': pod.status.phase,
                'health': 'healthy' if container_status and container_status.ready else 'unhealthy',
                'placement': {
                    'node': pod.spec.node_name,
                    'ip': pod.status.pod_ip
                },
                'resources': {
                    'cpu': container.resources.requests.get('cpu', '') if container.resources.requests else None,
                    'memory': container.resources.requests.get('memory', '') if container.resources.requests else None
                },
                'container': {
                    'name': container.name,
                    'image': container.image,
                    'status': container_status.state if container_status else None
                },
                'logs': logs,
                'accountId': env_config.account_id,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {'error': f'Failed to get pod details: {str(e)}'}

    def get_service_logs(self, env: str, service: str, lines: int = 50) -> List[dict]:
        """Get recent logs for a service (from all pods)"""
        try:
            k8s = self._get_k8s_client(env)
            core_api = k8s['core']
            namespace = k8s['namespace']

            # Get pods for this service
            label_selector = f"app={service}"
            pods = core_api.list_namespaced_pod(namespace, label_selector=label_selector)

            logs = []
            for pod in pods.items[:3]:  # Limit to 3 pods
                try:
                    log_content = core_api.read_namespaced_pod_log(
                        pod.metadata.name,
                        namespace,
                        tail_lines=lines // 3
                    )
                    for line in log_content.split('\n'):
                        if line:
                            logs.append({
                                'timestamp': datetime.utcnow().isoformat() + 'Z',
                                'message': line[:500],
                                'pod': pod.metadata.name[:12]
                            })
                except:
                    continue

            return logs[-lines:]  # Return last N lines

        except Exception as e:
            return [{'error': str(e)}]

    def scale_service(self, env: str, service: str, replicas: int, user_email: str) -> dict:
        """Scale deployment to specified replica count"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            k8s = self._get_k8s_client(env)
            apps_api = k8s['apps']
            namespace = k8s['namespace']

            deployment_name = self.config.get_service_name(env, service)

            # Patch deployment replicas
            body = {'spec': {'replicas': replicas}}
            apps_api.patch_namespaced_deployment_scale(
                deployment_name,
                namespace,
                body
            )

            action_name = 'stop' if replicas == 0 else 'start'
            return {
                'success': True,
                'deployment': deployment_name,
                'desiredCount': replicas,
                'triggeredBy': user_email,
                'action': action_name
            }

        except Exception as e:
            return {'error': str(e)}

    def force_deployment(self, env: str, service: str, user_email: str) -> dict:
        """Force a rollout restart"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            k8s = self._get_k8s_client(env)
            apps_api = k8s['apps']
            namespace = k8s['namespace']

            deployment_name = self.config.get_service_name(env, service)

            # Patch deployment to trigger rollout (add annotation)
            body = {
                'spec': {
                    'template': {
                        'metadata': {
                            'annotations': {
                                'dashborion.io/restartedAt': datetime.utcnow().isoformat()
                            }
                        }
                    }
                }
            }

            apps_api.patch_namespaced_deployment(
                deployment_name,
                namespace,
                body
            )

            return {
                'success': True,
                'deployment': deployment_name,
                'triggeredBy': user_email,
                'action': 'rollout-restart'
            }

        except Exception as e:
            return {'error': str(e)}

    def get_infrastructure(self, env: str) -> dict:
        """Get infrastructure topology for an environment"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        try:
            eks = self._get_eks_client(env)
            cluster_name = self.config.orchestrator.eks_cluster_name or self.config.get_cluster_name(env)

            cluster = eks.describe_cluster(name=cluster_name)['cluster']

            return {
                'environment': env,
                'accountId': env_config.account_id,
                'orchestrator': 'eks',
                'cluster': {
                    'name': cluster_name,
                    'version': cluster['version'],
                    'status': cluster['status'],
                    'endpoint': cluster['endpoint'],
                    'platformVersion': cluster.get('platformVersion')
                },
                'network': {
                    'vpcId': cluster['resourcesVpcConfig']['vpcId'],
                    'subnets': cluster['resourcesVpcConfig']['subnetIds'],
                    'securityGroups': cluster['resourcesVpcConfig']['securityGroupIds']
                },
                'consoleUrl': build_sso_console_url(
                    self.config.sso_portal_url,
                    env_config.account_id,
                    f"https://{self.region}.console.aws.amazon.com/eks/home?region={self.region}#/clusters/{cluster_name}"
                )
            }

        except Exception as e:
            return {'error': str(e)}

    def get_metrics(self, env: str, service: str) -> dict:
        """Get service metrics from CloudWatch Container Insights"""
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        cloudwatch = get_cross_account_client(
            'cloudwatch', env_config.account_id, env_config.region,
            project=self.project, env=env
        )
        cluster_name = self.config.orchestrator.eks_cluster_name or self.config.get_cluster_name(env)
        namespace = env_config.namespace or self.config.orchestrator.default_namespace

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=6)

        metrics_data = {}

        # CPU Utilization from Container Insights
        try:
            cpu_response = cloudwatch.get_metric_statistics(
                Namespace='ContainerInsights',
                MetricName='pod_cpu_utilization',
                Dimensions=[
                    {'Name': 'ClusterName', 'Value': cluster_name},
                    {'Name': 'Namespace', 'Value': namespace},
                    {'Name': 'PodName', 'Value': service}
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
        except:
            metrics_data['cpu'] = []

        # Memory Utilization
        try:
            memory_response = cloudwatch.get_metric_statistics(
                Namespace='ContainerInsights',
                MetricName='pod_memory_utilization',
                Dimensions=[
                    {'Name': 'ClusterName', 'Value': cluster_name},
                    {'Name': 'Namespace', 'Value': namespace},
                    {'Name': 'PodName', 'Value': service}
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
        except:
            metrics_data['memory'] = []

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

    def get_nodes(self, env: str, include_metrics: bool = True, include_pods: bool = False, namespace: str = None) -> List[K8sNode]:
        """
        Get all nodes in the EKS cluster with instance specs.

        Args:
            env: Environment name
            include_metrics: Whether to fetch node metrics from metrics.k8s.io API
            include_pods: Whether to include pods running on each node
            namespace: Filter pods by namespace (default: all namespaces)

        Returns:
            List of K8sNode with instance details
        """
        from providers.base import K8sNodePod

        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            core_api = k8s['core']

            # Get nodes
            nodes_response = core_api.list_node()

            # Get metrics if requested
            metrics_by_node = {}
            pod_metrics_by_name = {}
            if include_metrics:
                try:
                    from kubernetes.client import CustomObjectsApi
                    custom_api = CustomObjectsApi(core_api.api_client)
                    metrics_list = custom_api.list_cluster_custom_object(
                        group="metrics.k8s.io",
                        version="v1beta1",
                        plural="nodes"
                    )
                    metrics_by_node = {
                        item['metadata']['name']: item['usage']
                        for item in metrics_list.get('items', [])
                    }

                    # Also get pod metrics if we need pods
                    if include_pods:
                        try:
                            if namespace:
                                pod_metrics_list = custom_api.list_namespaced_custom_object(
                                    group="metrics.k8s.io",
                                    version="v1beta1",
                                    namespace=namespace,
                                    plural="pods"
                                )
                            else:
                                pod_metrics_list = custom_api.list_cluster_custom_object(
                                    group="metrics.k8s.io",
                                    version="v1beta1",
                                    plural="pods"
                                )
                            for item in pod_metrics_list.get('items', []):
                                pod_name = item['metadata']['name']
                                pod_ns = item['metadata']['namespace']
                                # Sum container metrics
                                total_cpu = 0
                                total_memory = 0
                                for container in item.get('containers', []):
                                    usage = container.get('usage', {})
                                    if usage.get('cpu'):
                                        # Parse cpu (e.g., "100m" or "1")
                                        cpu_str = usage['cpu']
                                        if cpu_str.endswith('n'):
                                            total_cpu += int(cpu_str[:-1]) / 1000000
                                        elif cpu_str.endswith('m'):
                                            total_cpu += int(cpu_str[:-1])
                                        else:
                                            total_cpu += int(cpu_str) * 1000
                                    if usage.get('memory'):
                                        # Parse memory (e.g., "128Mi" or "1Gi")
                                        mem_str = usage['memory']
                                        if mem_str.endswith('Ki'):
                                            total_memory += int(mem_str[:-2]) * 1024
                                        elif mem_str.endswith('Mi'):
                                            total_memory += int(mem_str[:-2]) * 1024 * 1024
                                        elif mem_str.endswith('Gi'):
                                            total_memory += int(mem_str[:-2]) * 1024 * 1024 * 1024
                                        else:
                                            total_memory += int(mem_str)
                                pod_metrics_by_name[f"{pod_ns}/{pod_name}"] = {
                                    'cpu': f"{int(total_cpu)}m",
                                    'memory': f"{total_memory // (1024*1024)}Mi"
                                }
                        except Exception as e:
                            print(f"Warning: Could not fetch pod metrics: {e}")
                except Exception as e:
                    print(f"Warning: Could not fetch node metrics: {e}")

            # Get pods grouped by node if requested
            pods_by_node = {}
            if include_pods:
                try:
                    if namespace:
                        pods_response = core_api.list_namespaced_pod(namespace)
                    else:
                        pods_response = core_api.list_pod_for_all_namespaces()

                    for pod in pods_response.items:
                        node_name = pod.spec.node_name
                        if not node_name:
                            continue

                        if node_name not in pods_by_node:
                            pods_by_node[node_name] = []

                        # Determine component from labels
                        labels = pod.metadata.labels or {}
                        component = labels.get('app') or labels.get('app.kubernetes.io/name') or labels.get('component')

                        # Get container requests
                        requests_cpu = None
                        requests_memory = None
                        if pod.spec.containers:
                            container = pod.spec.containers[0]
                            if container.resources and container.resources.requests:
                                requests_cpu = container.resources.requests.get('cpu')
                                requests_memory = container.resources.requests.get('memory')

                        # Get ready status
                        ready = False
                        if pod.status.container_statuses:
                            ready = all(cs.ready for cs in pod.status.container_statuses)

                        # Get restarts
                        restarts = 0
                        if pod.status.container_statuses:
                            restarts = sum(cs.restart_count for cs in pod.status.container_statuses)

                        # Get pod metrics if available
                        pod_key = f"{pod.metadata.namespace}/{pod.metadata.name}"
                        pod_metrics = pod_metrics_by_name.get(pod_key, {})

                        pods_by_node[node_name].append(K8sNodePod(
                            name=pod.metadata.name,
                            namespace=pod.metadata.namespace,
                            component=component,
                            status=pod.status.phase,
                            ready=ready,
                            restarts=restarts,
                            requests_cpu=requests_cpu,
                            requests_memory=requests_memory,
                            usage_cpu=pod_metrics.get('cpu'),
                            usage_memory=pod_metrics.get('memory')
                        ))
                except Exception as e:
                    print(f"Warning: Could not fetch pods: {e}")

            # Get EC2 client for subnet info
            ec2 = get_cross_account_client(
                'ec2', env_config.account_id, env_config.region,
                project=self.project, env=env
            )

            nodes = []
            for node in nodes_response.items:
                labels = node.metadata.labels or {}
                instance_type = labels.get('node.kubernetes.io/instance-type', 'unknown')
                zone = labels.get('topology.kubernetes.io/zone')
                region = labels.get('topology.kubernetes.io/region', env_config.region)
                nodegroup = labels.get('eks.amazonaws.com/nodegroup', 'unknown')

                # Extract instance ID from provider ID
                instance_id = None
                subnet_id = None
                provider_id = node.spec.provider_id
                if provider_id and provider_id.startswith('aws:///'):
                    instance_id = provider_id.split('/')[-1]
                    # Get subnet from EC2
                    try:
                        instance_info = ec2.describe_instances(InstanceIds=[instance_id])
                        if instance_info['Reservations']:
                            subnet_id = instance_info['Reservations'][0]['Instances'][0].get('SubnetId')
                    except Exception:
                        pass

                # Determine node status
                status = "Unknown"
                for condition in node.status.conditions or []:
                    if condition.type == "Ready":
                        status = "Ready" if condition.status == "True" else "NotReady"
                        break

                # Get metrics for this node
                node_metrics = metrics_by_node.get(node.metadata.name, {})

                # Enrich instance type with specs from Pricing API
                instance_type_display = instance_type
                try:
                    instance_type_display = format_instance_type(instance_type, region)
                except Exception:
                    pass  # Fallback to plain instance type

                # Get pods for this node
                node_pods = pods_by_node.get(node.metadata.name, [])

                # Get capacity pods
                capacity_pods = None
                allocatable_pods = None
                if node.status.capacity:
                    capacity_pods = int(node.status.capacity.get('pods', 0))
                if node.status.allocatable:
                    allocatable_pods = int(node.status.allocatable.get('pods', 0))

                nodes.append(K8sNode(
                    name=node.metadata.name,
                    instance_type=instance_type,
                    instance_type_display=instance_type_display,
                    zone=zone,
                    region=region,
                    nodegroup=nodegroup,
                    status=status,
                    capacity_cpu=node.status.capacity.get('cpu', '') if node.status.capacity else None,
                    capacity_memory=node.status.capacity.get('memory', '') if node.status.capacity else None,
                    capacity_pods=capacity_pods,
                    allocatable_cpu=node.status.allocatable.get('cpu', '') if node.status.allocatable else None,
                    allocatable_memory=node.status.allocatable.get('memory', '') if node.status.allocatable else None,
                    allocatable_pods=allocatable_pods,
                    usage_cpu=node_metrics.get('cpu'),
                    usage_memory=node_metrics.get('memory'),
                    pod_count=len(node_pods),
                    subnet_id=subnet_id,
                    instance_id=instance_id,
                    labels=labels,
                    pods=node_pods
                ))

            return nodes

        except Exception as e:
            raise ValueError(f"Failed to get nodes: {e}")

    def get_k8s_services(self, env: str, namespace: str = None, components: List[str] = None) -> List[K8sService]:
        """
        Get Kubernetes Services (ClusterIP, LoadBalancer, etc.)

        Args:
            env: Environment name
            namespace: Optional namespace filter (defaults to config namespace)
            components: Optional list of component names to filter by

        Returns:
            List of K8sService
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            core_api = k8s['core']
            ns = namespace or k8s['namespace']

            services_response = core_api.list_namespaced_service(ns)

            services = []
            for svc in services_response.items:
                svc_name = svc.metadata.name

                # Filter by components if specified
                if components and not any(comp in svc_name for comp in components):
                    continue

                # Parse ports
                ports = []
                if svc.spec.ports:
                    for port in svc.spec.ports:
                        ports.append({
                            'name': port.name,
                            'port': port.port,
                            'targetPort': str(port.target_port) if port.target_port else None,
                            'protocol': port.protocol,
                            'nodePort': port.node_port
                        })

                # Get external IP for LoadBalancer
                external_ip = None
                if svc.spec.type == 'LoadBalancer' and svc.status.load_balancer:
                    ingress = svc.status.load_balancer.ingress
                    if ingress:
                        external_ip = ingress[0].hostname or ingress[0].ip

                services.append(K8sService(
                    name=svc_name,
                    namespace=ns,
                    service_type=svc.spec.type,
                    cluster_ip=svc.spec.cluster_ip,
                    external_ip=external_ip,
                    ports=ports,
                    selector=dict(svc.spec.selector) if svc.spec.selector else {},
                    labels=dict(svc.metadata.labels) if svc.metadata.labels else {}
                ))

            return services

        except Exception as e:
            raise ValueError(f"Failed to get services: {e}")

    def get_ingresses(self, env: str, namespace: str = None) -> List[K8sIngress]:
        """
        Get Kubernetes Ingresses with rules and load balancer info.

        Args:
            env: Environment name
            namespace: Optional namespace filter (defaults to config namespace)

        Returns:
            List of K8sIngress
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            ns = namespace or k8s['namespace']

            # Get NetworkingV1Api for ingresses
            from kubernetes import client as k8s_client
            networking_api = k8s_client.NetworkingV1Api(k8s['core'].api_client)

            ingresses_response = networking_api.list_namespaced_ingress(ns)

            ingresses = []
            for ing in ingresses_response.items:
                # Parse rules
                rules = []
                if ing.spec.rules:
                    for rule in ing.spec.rules:
                        host = rule.host or '*'
                        if rule.http and rule.http.paths:
                            for path in rule.http.paths:
                                service_name = None
                                service_port = None
                                if path.backend.service:
                                    service_name = path.backend.service.name
                                    if path.backend.service.port:
                                        service_port = path.backend.service.port.number or path.backend.service.port.name

                                rules.append(K8sIngressRule(
                                    host=host,
                                    path=path.path or '/',
                                    path_type=path.path_type or 'Prefix',
                                    service_name=service_name,
                                    service_port=service_port
                                ))

                # Parse TLS
                tls = []
                if ing.spec.tls:
                    for tls_config in ing.spec.tls:
                        tls.append({
                            'hosts': tls_config.hosts or [],
                            'secretName': tls_config.secret_name
                        })

                # Get load balancer info
                lb_hostname = None
                lb_ip = None
                if ing.status and ing.status.load_balancer and ing.status.load_balancer.ingress:
                    lb_ingress = ing.status.load_balancer.ingress[0]
                    lb_hostname = lb_ingress.hostname
                    lb_ip = lb_ingress.ip

                # Get ingress class
                ingress_class = None
                if ing.spec.ingress_class_name:
                    ingress_class = ing.spec.ingress_class_name
                elif ing.metadata.annotations:
                    ingress_class = ing.metadata.annotations.get('kubernetes.io/ingress.class')

                ingresses.append(K8sIngress(
                    name=ing.metadata.name,
                    namespace=ns,
                    ingress_class=ingress_class,
                    rules=rules,
                    tls=tls,
                    load_balancer_hostname=lb_hostname,
                    load_balancer_ip=lb_ip,
                    annotations=dict(ing.metadata.annotations) if ing.metadata.annotations else {},
                    labels=dict(ing.metadata.labels) if ing.metadata.labels else {}
                ))

            return ingresses

        except Exception as e:
            raise ValueError(f"Failed to get ingresses: {e}")

    def get_namespaces(self, env: str) -> List[str]:
        """
        Get list of namespaces in the cluster.

        Args:
            env: Environment name

        Returns:
            List of namespace names
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            core_api = k8s['core']

            namespaces = core_api.list_namespace()
            return [ns.metadata.name for ns in namespaces.items]

        except Exception as e:
            raise ValueError(f"Failed to get namespaces: {e}")

    def get_pods(self, env: str, namespace: str = None, selector: str = None) -> List[K8sPod]:
        """
        Get Kubernetes pods.

        Args:
            env: Environment name
            namespace: Optional namespace filter (None for config namespace)
            selector: Optional label selector

        Returns:
            List of K8sPod
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            core_api = k8s['core']
            ns = namespace or k8s['namespace']

            # List pods
            if ns:
                pods_response = core_api.list_namespaced_pod(
                    ns,
                    label_selector=selector
                )
            else:
                pods_response = core_api.list_pod_for_all_namespaces(
                    label_selector=selector
                )

            pods = []
            for pod in pods_response.items:
                # Calculate age
                age = None
                if pod.metadata.creation_timestamp:
                    delta = datetime.utcnow().replace(tzinfo=None) - pod.metadata.creation_timestamp.replace(tzinfo=None)
                    if delta.days > 0:
                        age = f"{delta.days}d"
                    elif delta.seconds >= 3600:
                        age = f"{delta.seconds // 3600}h"
                    else:
                        age = f"{delta.seconds // 60}m"

                # Calculate ready status
                ready_count = 0
                total_count = 0
                restarts = 0
                containers = []

                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        total_count += 1
                        if cs.ready:
                            ready_count += 1
                        restarts += cs.restart_count or 0
                        containers.append({
                            'name': cs.name,
                            'ready': cs.ready,
                            'restarts': cs.restart_count,
                            'image': cs.image
                        })
                elif pod.spec.containers:
                    total_count = len(pod.spec.containers)

                pods.append(K8sPod(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace,
                    status=pod.status.phase,
                    ready=f"{ready_count}/{total_count}",
                    restarts=restarts,
                    age=age,
                    ip=pod.status.pod_ip,
                    node=pod.spec.node_name,
                    containers=containers,
                    labels=dict(pod.metadata.labels) if pod.metadata.labels else {},
                    annotations=dict(pod.metadata.annotations) if pod.metadata.annotations else {}
                ))

            return pods

        except Exception as e:
            raise ValueError(f"Failed to get pods: {e}")

    def get_deployments(self, env: str, namespace: str = None) -> List[K8sDeployment]:
        """
        Get Kubernetes deployments.

        Args:
            env: Environment name
            namespace: Optional namespace filter

        Returns:
            List of K8sDeployment
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            apps_api = k8s['apps']
            ns = namespace or k8s['namespace']

            # List deployments
            if ns:
                deployments_response = apps_api.list_namespaced_deployment(ns)
            else:
                deployments_response = apps_api.list_deployment_for_all_namespaces()

            deployments = []
            for deploy in deployments_response.items:
                # Calculate age
                age = None
                if deploy.metadata.creation_timestamp:
                    delta = datetime.utcnow().replace(tzinfo=None) - deploy.metadata.creation_timestamp.replace(tzinfo=None)
                    if delta.days > 0:
                        age = f"{delta.days}d"
                    elif delta.seconds >= 3600:
                        age = f"{delta.seconds // 3600}h"
                    else:
                        age = f"{delta.seconds // 60}m"

                # Get image from first container
                image = None
                if deploy.spec.template.spec.containers:
                    image = deploy.spec.template.spec.containers[0].image

                ready_replicas = deploy.status.ready_replicas or 0
                replicas = deploy.spec.replicas or 0

                deployments.append(K8sDeployment(
                    name=deploy.metadata.name,
                    namespace=deploy.metadata.namespace,
                    ready=f"{ready_replicas}/{replicas}",
                    available=deploy.status.available_replicas or 0,
                    up_to_date=deploy.status.updated_replicas or 0,
                    age=age,
                    image=image,
                    replicas=replicas,
                    strategy=deploy.spec.strategy.type if deploy.spec.strategy else None,
                    labels=dict(deploy.metadata.labels) if deploy.metadata.labels else {}
                ))

            return deployments

        except Exception as e:
            raise ValueError(f"Failed to get deployments: {e}")

    def get_pod_logs(self, env: str, pod: str, namespace: str = 'default',
                    container: str = None, tail: int = 100, since: str = None) -> str:
        """
        Get logs from a specific pod.

        Args:
            env: Environment name
            pod: Pod name
            namespace: Namespace
            container: Optional container name
            tail: Number of lines
            since: Duration string (e.g., '1h', '30m') - not implemented yet

        Returns:
            Log content as string
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            core_api = k8s['core']

            kwargs = {
                'tail_lines': tail
            }
            if container:
                kwargs['container'] = container

            log_content = core_api.read_namespaced_pod_log(
                pod,
                namespace,
                **kwargs
            )

            return log_content

        except Exception as e:
            raise ValueError(f"Failed to get pod logs: {e}")

    def describe_k8s_resource(self, env: str, resource_type: str, name: str,
                              namespace: str = 'default') -> dict:
        """
        Describe a Kubernetes resource.

        Args:
            env: Environment name
            resource_type: Type (pod, service, deployment, ingress, node)
            name: Resource name
            namespace: Namespace

        Returns:
            Resource details dict
        """
        env_config = self.config.get_environment(self.project, env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")

        try:
            k8s = self._get_k8s_client(env)
            core_api = k8s['core']
            apps_api = k8s['apps']

            if resource_type == 'pod':
                resource = core_api.read_namespaced_pod(name, namespace)
                return {
                    'kind': 'Pod',
                    'name': resource.metadata.name,
                    'namespace': resource.metadata.namespace,
                    'uid': resource.metadata.uid,
                    'labels': dict(resource.metadata.labels) if resource.metadata.labels else {},
                    'annotations': dict(resource.metadata.annotations) if resource.metadata.annotations else {},
                    'status': resource.status.phase,
                    'podIP': resource.status.pod_ip,
                    'hostIP': resource.status.host_ip,
                    'nodeName': resource.spec.node_name,
                    'containers': [
                        {
                            'name': c.name,
                            'image': c.image,
                            'ports': [{'containerPort': p.container_port, 'protocol': p.protocol} for p in (c.ports or [])],
                            'resources': {
                                'requests': dict(c.resources.requests) if c.resources and c.resources.requests else {},
                                'limits': dict(c.resources.limits) if c.resources and c.resources.limits else {}
                            }
                        }
                        for c in resource.spec.containers
                    ],
                    'conditions': [
                        {'type': c.type, 'status': c.status, 'reason': c.reason}
                        for c in (resource.status.conditions or [])
                    ]
                }

            elif resource_type == 'service':
                resource = core_api.read_namespaced_service(name, namespace)
                return {
                    'kind': 'Service',
                    'name': resource.metadata.name,
                    'namespace': resource.metadata.namespace,
                    'type': resource.spec.type,
                    'clusterIP': resource.spec.cluster_ip,
                    'ports': [
                        {'port': p.port, 'targetPort': str(p.target_port), 'protocol': p.protocol, 'nodePort': p.node_port}
                        for p in (resource.spec.ports or [])
                    ],
                    'selector': dict(resource.spec.selector) if resource.spec.selector else {},
                    'labels': dict(resource.metadata.labels) if resource.metadata.labels else {}
                }

            elif resource_type == 'deployment':
                resource = apps_api.read_namespaced_deployment(name, namespace)
                return {
                    'kind': 'Deployment',
                    'name': resource.metadata.name,
                    'namespace': resource.metadata.namespace,
                    'replicas': resource.spec.replicas,
                    'readyReplicas': resource.status.ready_replicas,
                    'availableReplicas': resource.status.available_replicas,
                    'strategy': resource.spec.strategy.type if resource.spec.strategy else None,
                    'selector': dict(resource.spec.selector.match_labels) if resource.spec.selector and resource.spec.selector.match_labels else {},
                    'template': {
                        'containers': [
                            {
                                'name': c.name,
                                'image': c.image,
                                'resources': {
                                    'requests': dict(c.resources.requests) if c.resources and c.resources.requests else {},
                                    'limits': dict(c.resources.limits) if c.resources and c.resources.limits else {}
                                }
                            }
                            for c in resource.spec.template.spec.containers
                        ]
                    },
                    'conditions': [
                        {'type': c.type, 'status': c.status, 'reason': c.reason, 'message': c.message}
                        for c in (resource.status.conditions or [])
                    ]
                }

            elif resource_type == 'node':
                resource = core_api.read_node(name)
                return {
                    'kind': 'Node',
                    'name': resource.metadata.name,
                    'labels': dict(resource.metadata.labels) if resource.metadata.labels else {},
                    'capacity': dict(resource.status.capacity) if resource.status.capacity else {},
                    'allocatable': dict(resource.status.allocatable) if resource.status.allocatable else {},
                    'conditions': [
                        {'type': c.type, 'status': c.status, 'reason': c.reason}
                        for c in (resource.status.conditions or [])
                    ],
                    'nodeInfo': {
                        'kubeletVersion': resource.status.node_info.kubelet_version,
                        'osImage': resource.status.node_info.os_image,
                        'containerRuntimeVersion': resource.status.node_info.container_runtime_version,
                        'architecture': resource.status.node_info.architecture
                    } if resource.status.node_info else {}
                }

            elif resource_type == 'ingress':
                from kubernetes import client as k8s_client
                networking_api = k8s_client.NetworkingV1Api(core_api.api_client)
                resource = networking_api.read_namespaced_ingress(name, namespace)
                return {
                    'kind': 'Ingress',
                    'name': resource.metadata.name,
                    'namespace': resource.metadata.namespace,
                    'ingressClass': resource.spec.ingress_class_name,
                    'rules': [
                        {
                            'host': rule.host,
                            'paths': [
                                {
                                    'path': path.path,
                                    'pathType': path.path_type,
                                    'backend': {
                                        'service': path.backend.service.name if path.backend.service else None,
                                        'port': path.backend.service.port.number if path.backend.service and path.backend.service.port else None
                                    }
                                }
                                for path in (rule.http.paths if rule.http else [])
                            ]
                        }
                        for rule in (resource.spec.rules or [])
                    ],
                    'tls': [
                        {'hosts': tls.hosts, 'secretName': tls.secret_name}
                        for tls in (resource.spec.tls or [])
                    ],
                    'loadBalancer': {
                        'hostname': resource.status.load_balancer.ingress[0].hostname if resource.status.load_balancer and resource.status.load_balancer.ingress else None,
                        'ip': resource.status.load_balancer.ingress[0].ip if resource.status.load_balancer and resource.status.load_balancer.ingress else None
                    }
                }

            else:
                raise ValueError(f"Unknown resource type: {resource_type}")

        except Exception as e:
            raise ValueError(f"Failed to describe {resource_type} {name}: {e}")


# Register the provider
ProviderFactory.register_orchestrator_provider('eks', EKSProvider)
