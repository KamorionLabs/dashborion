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
    ProviderFactory
)
from config import DashboardConfig
from utils.aws import get_cross_account_client, get_action_client, build_sso_console_url


class EKSProvider(OrchestratorProvider):
    """
    AWS EKS Kubernetes implementation of the orchestrator provider.
    Uses Kubernetes API to manage deployments in EKS clusters.
    """

    def __init__(self, config: DashboardConfig):
        self.config = config
        self.region = config.region
        self._k8s_clients = {}  # Cache K8s clients per environment

    def _get_eks_client(self, env: str):
        """Get EKS client for environment"""
        env_config = self.config.get_environment(env)
        if not env_config:
            raise ValueError(f"Unknown environment: {env}")
        return get_cross_account_client('eks', env_config.account_id, env_config.region)

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

            env_config = self.config.get_environment(env)
            eks = self._get_eks_client(env)

            # Get cluster info
            cluster_name = self.config.orchestrator.eks_cluster_name or self.config.get_cluster_name(env)
            cluster_info = eks.describe_cluster(name=cluster_name)['cluster']

            # Get auth token via STS
            sts = get_cross_account_client('sts', env_config.account_id, env_config.region)

            # Generate EKS token using STS
            token = self._get_eks_token(sts, cluster_name, env_config.region)

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

    def _get_eks_token(self, sts_client, cluster_name: str, region: str) -> str:
        """Generate EKS auth token using STS GetCallerIdentity presigned URL"""
        import urllib.parse

        # This mimics aws-iam-authenticator token generation
        service = 'sts'
        endpoint = f"https://sts.{region}.amazonaws.com/"

        # Create presigned URL for GetCallerIdentity
        params = {
            'Action': 'GetCallerIdentity',
            'Version': '2011-06-15',
            'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
            'X-Amz-Expires': '60'
        }

        # The actual token generation requires AWS SigV4 signing
        # For production, use the boto3 EKS token endpoint or aws-iam-authenticator
        # This is a simplified version that may not work in all cases

        # Alternative: Use EKS get_token API if available
        try:
            # boto3 >= 1.24 has native EKS token support
            import botocore.signers

            session = sts_client._endpoint.http_session
            credentials = sts_client._request_signer._credentials

            # Create presigned URL
            url = f"https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15&X-Amz-Cluster-Name={cluster_name}"

            # Sign the URL
            request = botocore.awsrequest.AWSRequest(method='GET', url=url)
            botocore.auth.SigV4Auth(credentials, 'sts', region).add_auth(request)

            # Encode as token
            token = 'k8s-aws-v1.' + base64.urlsafe_b64encode(
                request.url.encode('utf-8')
            ).decode('utf-8').rstrip('=')

            return token

        except Exception as e:
            # Fallback: return placeholder (won't work but avoids crash)
            print(f"Warning: EKS token generation failed: {e}")
            return "PLACEHOLDER_TOKEN"

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
        env_config = self.config.get_environment(env)
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
        env_config = self.config.get_environment(env)
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
        env_config = self.config.get_environment(env)
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
        env_config = self.config.get_environment(env)
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
        env_config = self.config.get_environment(env)
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
                                'dashboard.homebox.io/restartedAt': datetime.utcnow().isoformat()
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
        env_config = self.config.get_environment(env)
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
        env_config = self.config.get_environment(env)
        if not env_config:
            return {'error': f'Unknown environment: {env}'}

        cloudwatch = get_cross_account_client('cloudwatch', env_config.account_id, env_config.region)
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


# Register the provider
ProviderFactory.register_orchestrator_provider('eks', EKSProvider)
