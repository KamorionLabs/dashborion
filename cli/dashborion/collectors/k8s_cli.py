"""Kubernetes collector for Dashborion CLI (direct kubectl access)"""

from typing import Dict, List, Optional, Any
from datetime import datetime


class KubernetesCollector:
    """Direct Kubernetes API access via kubectl configuration for CLI commands"""

    def __init__(self, context: str):
        self.context = context
        self._core_v1 = None
        self._apps_v1 = None
        self._networking_v1 = None

    def _load_config(self):
        """Load Kubernetes configuration"""
        from kubernetes import client, config

        config.load_kube_config(context=self.context)

        self._core_v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()
        self._networking_v1 = client.NetworkingV1Api()

    @property
    def core_v1(self):
        if self._core_v1 is None:
            self._load_config()
        return self._core_v1

    @property
    def apps_v1(self):
        if self._apps_v1 is None:
            self._load_config()
        return self._apps_v1

    @property
    def networking_v1(self):
        if self._networking_v1 is None:
            self._load_config()
        return self._networking_v1

    def _calculate_age(self, timestamp) -> str:
        """Calculate age from timestamp"""
        if not timestamp:
            return '-'

        now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.utcnow()
        delta = now - timestamp

        if delta.days > 0:
            return f"{delta.days}d"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h"
        minutes = (delta.seconds % 3600) // 60
        return f"{minutes}m"

    def get_pods(self, namespace: Optional[str] = None,
                 selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pods"""
        pods = []

        try:
            kwargs = {}
            if selector:
                kwargs['label_selector'] = selector

            if namespace:
                pod_list = self.core_v1.list_namespaced_pod(namespace=namespace, **kwargs)
            else:
                pod_list = self.core_v1.list_pod_for_all_namespaces(**kwargs)

            for pod in pod_list.items:
                ready_containers = 0
                total_containers = len(pod.spec.containers)
                restarts = 0

                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        if cs.ready:
                            ready_containers += 1
                        restarts += cs.restart_count

                pods.append({
                    'name': pod.metadata.name,
                    'namespace': pod.metadata.namespace,
                    'status': pod.status.phase,
                    'ready': f"{ready_containers}/{total_containers}",
                    'restarts': restarts,
                    'age': self._calculate_age(pod.metadata.creation_timestamp),
                    'ip': pod.status.pod_ip,
                    'node': pod.spec.node_name,
                })

        except Exception as e:
            return [{'error': str(e)}]

        return pods

    def get_services(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get services"""
        services = []

        try:
            if namespace:
                svc_list = self.core_v1.list_namespaced_service(namespace=namespace)
            else:
                svc_list = self.core_v1.list_service_for_all_namespaces()

            for svc in svc_list.items:
                ports = []
                for port in (svc.spec.ports or []):
                    port_str = f"{port.port}"
                    if port.node_port:
                        port_str += f":{port.node_port}"
                    port_str += f"/{port.protocol}"
                    ports.append(port_str)

                services.append({
                    'name': svc.metadata.name,
                    'namespace': svc.metadata.namespace,
                    'type': svc.spec.type,
                    'clusterIP': svc.spec.cluster_ip,
                    'externalIP': ','.join(svc.spec.external_i_ps or []) or '-',
                    'ports': ','.join(ports),
                    'age': self._calculate_age(svc.metadata.creation_timestamp),
                })

        except Exception as e:
            return [{'error': str(e)}]

        return services

    def get_deployments(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get deployments"""
        deployments = []

        try:
            if namespace:
                deploy_list = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            else:
                deploy_list = self.apps_v1.list_deployment_for_all_namespaces()

            for deploy in deploy_list.items:
                ready = deploy.status.ready_replicas or 0
                desired = deploy.spec.replicas or 0

                deployments.append({
                    'name': deploy.metadata.name,
                    'namespace': deploy.metadata.namespace,
                    'ready': f"{ready}/{desired}",
                    'upToDate': deploy.status.updated_replicas or 0,
                    'available': deploy.status.available_replicas or 0,
                    'age': self._calculate_age(deploy.metadata.creation_timestamp),
                })

        except Exception as e:
            return [{'error': str(e)}]

        return deployments

    def get_ingresses(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get ingresses"""
        ingresses = []

        try:
            if namespace:
                ing_list = self.networking_v1.list_namespaced_ingress(namespace=namespace)
            else:
                ing_list = self.networking_v1.list_ingress_for_all_namespaces()

            for ing in ing_list.items:
                hosts = []
                if ing.spec.rules:
                    for rule in ing.spec.rules:
                        if rule.host:
                            hosts.append(rule.host)

                addresses = []
                if ing.status.load_balancer and ing.status.load_balancer.ingress:
                    for lb in ing.status.load_balancer.ingress:
                        if lb.hostname:
                            addresses.append(lb.hostname)
                        elif lb.ip:
                            addresses.append(lb.ip)

                ingress_class = ing.spec.ingress_class_name
                if not ingress_class and ing.metadata.annotations:
                    ingress_class = ing.metadata.annotations.get('kubernetes.io/ingress.class')

                ingresses.append({
                    'name': ing.metadata.name,
                    'namespace': ing.metadata.namespace,
                    'ingressClass': ingress_class or '-',
                    'hosts': ','.join(hosts) if hosts else '-',
                    'address': ','.join(addresses) if addresses else '-',
                    'age': self._calculate_age(ing.metadata.creation_timestamp),
                })

        except Exception as e:
            return [{'error': str(e)}]

        return ingresses

    def get_nodes(self) -> List[Dict[str, Any]]:
        """Get nodes"""
        nodes = []

        try:
            node_list = self.core_v1.list_node()

            for node in node_list.items:
                status = 'Unknown'
                for condition in (node.status.conditions or []):
                    if condition.type == 'Ready':
                        status = 'Ready' if condition.status == 'True' else 'NotReady'
                        break

                roles = []
                for label in (node.metadata.labels or {}):
                    if label.startswith('node-role.kubernetes.io/'):
                        role = label.split('/')[-1]
                        roles.append(role)

                labels = node.metadata.labels or {}
                instance_type = labels.get(
                    'node.kubernetes.io/instance-type',
                    labels.get('beta.kubernetes.io/instance-type', '-')
                )
                zone = labels.get(
                    'topology.kubernetes.io/zone',
                    labels.get('failure-domain.beta.kubernetes.io/zone', '-')
                )

                nodes.append({
                    'name': node.metadata.name,
                    'status': status,
                    'roles': ','.join(roles) if roles else '<none>',
                    'age': self._calculate_age(node.metadata.creation_timestamp),
                    'version': node.status.node_info.kubelet_version if node.status.node_info else '-',
                    'instanceType': instance_type,
                    'zone': zone,
                })

        except Exception as e:
            return [{'error': str(e)}]

        return nodes

    def describe(self, resource_type: str, name: str, namespace: str = 'default') -> Dict[str, Any]:
        """Describe a resource"""
        try:
            if resource_type == 'pod':
                obj = self.core_v1.read_namespaced_pod(name=name, namespace=namespace)
                return {'name': obj.metadata.name, 'status': obj.status.phase, 'ip': obj.status.pod_ip}
            elif resource_type == 'service':
                obj = self.core_v1.read_namespaced_service(name=name, namespace=namespace)
                return {'name': obj.metadata.name, 'type': obj.spec.type, 'clusterIP': obj.spec.cluster_ip}
            elif resource_type == 'deployment':
                obj = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
                return {'name': obj.metadata.name, 'replicas': obj.spec.replicas}
            else:
                return {'error': f'Unknown resource type: {resource_type}'}
        except Exception as e:
            return {'error': str(e)}

    def stream_logs(self, pod: str, namespace: str = 'default',
                    container: Optional[str] = None, tail: int = 100,
                    follow: bool = False, since: Optional[str] = None):
        """Stream pod logs"""
        import click
        import re

        try:
            kwargs = {'name': pod, 'namespace': namespace, 'tail_lines': tail}

            if container:
                kwargs['container'] = container

            if since:
                match = re.match(r'(\d+)([hdm])', since)
                if match:
                    value, unit = int(match.group(1)), match.group(2)
                    if unit == 'h':
                        kwargs['since_seconds'] = value * 3600
                    elif unit == 'm':
                        kwargs['since_seconds'] = value * 60
                    elif unit == 'd':
                        kwargs['since_seconds'] = value * 86400

            if follow:
                kwargs['follow'] = True
                w = self.core_v1.read_namespaced_pod_log(**kwargs, _preload_content=False)
                for line in w.stream():
                    click.echo(line.decode('utf-8').rstrip())
            else:
                logs = self.core_v1.read_namespaced_pod_log(**kwargs)
                click.echo(logs)

        except Exception as e:
            click.echo(f"Error: {e}", err=True)
