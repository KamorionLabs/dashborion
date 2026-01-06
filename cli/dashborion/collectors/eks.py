"""EKS collector for Dashborion CLI"""

from typing import Dict, List, Optional, Any


class EKSCollector:
    """Collect data from AWS EKS via kubectl"""

    def __init__(self, session, context: Optional[str] = None):
        self.session = session
        self.context = context
        self._k8s_client = None

    @property
    def k8s_client(self):
        """Lazy load Kubernetes client"""
        if self._k8s_client is None:
            from kubernetes import client, config

            if self.context:
                config.load_kube_config(context=self.context)
            else:
                config.load_kube_config()

            self._k8s_client = client
        return self._k8s_client

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get EKS cluster status"""
        try:
            v1 = self.k8s_client.CoreV1Api()

            # Get nodes
            nodes = v1.list_node()
            ready_nodes = sum(
                1 for node in nodes.items
                for condition in node.status.conditions
                if condition.type == 'Ready' and condition.status == 'True'
            )

            # Get namespaces
            namespaces = v1.list_namespace()

            # Get pods count
            pods = v1.list_pod_for_all_namespaces()
            running_pods = sum(1 for pod in pods.items if pod.status.phase == 'Running')

            return {
                'context': self.context,
                'nodes': {
                    'total': len(nodes.items),
                    'ready': ready_nodes,
                },
                'namespaces': len(namespaces.items),
                'pods': {
                    'total': len(pods.items),
                    'running': running_pods,
                },
            }

        except Exception as e:
            return {'error': str(e)}

    def list_services(self, namespaces: List[str]) -> List[Dict[str, Any]]:
        """List deployments as services"""
        services = []

        try:
            apps_v1 = self.k8s_client.AppsV1Api()

            for ns in namespaces:
                deployments = apps_v1.list_namespaced_deployment(namespace=ns)

                for deploy in deployments.items:
                    services.append({
                        'name': deploy.metadata.name,
                        'namespace': ns,
                        'status': 'running' if deploy.status.ready_replicas else 'pending',
                        'runningCount': deploy.status.ready_replicas or 0,
                        'desiredCount': deploy.spec.replicas or 0,
                        'availableReplicas': deploy.status.available_replicas or 0,
                        'image': deploy.spec.template.spec.containers[0].image if deploy.spec.template.spec.containers else None,
                    })

        except Exception as e:
            return [{'error': str(e)}]

        return services

    def describe_service(self, name: str, namespace: str = 'default') -> Dict[str, Any]:
        """Get detailed deployment information"""
        try:
            apps_v1 = self.k8s_client.AppsV1Api()
            v1 = self.k8s_client.CoreV1Api()

            deploy = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)

            # Get associated pods
            selector = deploy.spec.selector.match_labels
            label_selector = ','.join(f"{k}={v}" for k, v in selector.items())
            pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)

            return {
                'name': deploy.metadata.name,
                'namespace': namespace,
                'replicas': deploy.spec.replicas,
                'readyReplicas': deploy.status.ready_replicas,
                'availableReplicas': deploy.status.available_replicas,
                'conditions': [
                    {
                        'type': c.type,
                        'status': c.status,
                        'reason': c.reason,
                        'message': c.message,
                    }
                    for c in (deploy.status.conditions or [])
                ],
                'containers': [
                    {
                        'name': c.name,
                        'image': c.image,
                        'ports': [{'containerPort': p.container_port} for p in (c.ports or [])],
                    }
                    for c in deploy.spec.template.spec.containers
                ],
                'pods': [
                    {
                        'name': pod.metadata.name,
                        'status': pod.status.phase,
                        'ip': pod.status.pod_ip,
                        'nodeName': pod.spec.node_name,
                    }
                    for pod in pods.items
                ],
            }

        except Exception as e:
            return {'error': str(e)}

    def list_pods(self, service: str, namespace: str = 'default') -> List[Dict[str, Any]]:
        """List pods for a deployment"""
        try:
            apps_v1 = self.k8s_client.AppsV1Api()
            v1 = self.k8s_client.CoreV1Api()

            deploy = apps_v1.read_namespaced_deployment(name=service, namespace=namespace)

            selector = deploy.spec.selector.match_labels
            label_selector = ','.join(f"{k}={v}" for k, v in selector.items())
            pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)

            return [
                {
                    'name': pod.metadata.name,
                    'status': pod.status.phase,
                    'ip': pod.status.pod_ip,
                    'nodeName': pod.spec.node_name,
                    'startTime': pod.status.start_time,
                    'restarts': sum(cs.restart_count for cs in (pod.status.container_statuses or [])),
                }
                for pod in pods.items
            ]

        except Exception as e:
            return [{'error': str(e)}]

    def stream_logs(self, service: str, namespace: str = 'default',
                    tail: int = 100, follow: bool = False, since: Optional[str] = None):
        """Stream logs from pods"""
        import click

        try:
            v1 = self.k8s_client.CoreV1Api()
            apps_v1 = self.k8s_client.AppsV1Api()

            # Get pods for the deployment
            deploy = apps_v1.read_namespaced_deployment(name=service, namespace=namespace)
            selector = deploy.spec.selector.match_labels
            label_selector = ','.join(f"{k}={v}" for k, v in selector.items())
            pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)

            if not pods.items:
                click.echo(f"No pods found for {service}", err=True)
                return

            # Get logs from first pod
            pod = pods.items[0]

            kwargs = {
                'name': pod.metadata.name,
                'namespace': namespace,
                'tail_lines': tail,
            }

            if since:
                import re
                match = re.match(r'(\d+)([hdm])', since)
                if match:
                    value, unit = int(match.group(1)), match.group(2)
                    seconds = value * (3600 if unit == 'h' else 60 if unit == 'm' else 86400)
                    kwargs['since_seconds'] = seconds

            if follow:
                kwargs['follow'] = True
                w = v1.read_namespaced_pod_log(**kwargs, _preload_content=False)
                for line in w.stream():
                    click.echo(line.decode('utf-8').rstrip())
            else:
                logs = v1.read_namespaced_pod_log(**kwargs)
                click.echo(logs)

        except Exception as e:
            click.echo(f"Error: {e}", err=True)

    def restart_deployment(self, name: str, namespace: str = 'default',
                           image: Optional[str] = None) -> Dict[str, Any]:
        """Restart a deployment"""
        try:
            from datetime import datetime

            apps_v1 = self.k8s_client.AppsV1Api()

            # Patch the deployment to trigger a rollout restart
            patch = {
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

            if image:
                # Update the image
                deploy = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
                containers = deploy.spec.template.spec.containers
                if containers:
                    patch['spec']['template']['spec'] = {
                        'containers': [{'name': containers[0].name, 'image': image}]
                    }

            apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)

            return {'success': True}

        except Exception as e:
            return {'success': False, 'error': str(e)}
