"""Kubernetes information collector."""

import os
import sys
import yaml
from kubernetes import client, config
from kubernetes.client import CustomObjectsApi
from kubernetes.config import kube_config
from rubix_diagram.config.components import DEFAULT_COMPONENTS

class KubernetesInfoCollector:
    def __init__(self, context, namespaces, components=None, aws_collector=None):
        try:
            print(f"\nDébut initialisation client Kubernetes:")
            print(f"Context demandé: {context}")
            
            # Définir le chemin explicite du kubeconfig
            kube_config_path = os.path.expanduser('~/.kube/config')
            print(f"Utilisation du kubeconfig: {kube_config_path}")

            if not os.path.exists(kube_config_path):
                print(f"ATTENTION: Le fichier {kube_config_path} n'existe pas!")
                # Chercher dans d'autres emplacements possibles
                alt_paths = ['/root/.kube/config', './kubeconfig']
                for path in alt_paths:
                    if os.path.exists(path):
                        print(f"Fichier de config trouvé à: {path}")
                        kube_config_path = path
                        break

            # Charger la configuration
            print(f"Chargement de la configuration avec le contexte {context}")
            config.load_kube_config(
                config_file=kube_config_path,
                context=context
            )

            # Vérifier la configuration chargée
            api_client = client.ApiClient()
            print(f"Configuration chargée - endpoint: {api_client.configuration.host}")

            # Initialiser les clients
            print("Initialisation des clients API...")
            self.v1 = client.CoreV1Api(api_client=api_client)
            self.networking = client.NetworkingV1Api(api_client=api_client)
            self.custom = CustomObjectsApi(api_client=api_client)
            
            # Test d'accès basique
            print("Test d'accès à l'API Kubernetes...")
            try:
                api_response = self.v1.list_namespace()
                print(f"Accès API réussi - {len(api_response.items)} namespaces trouvés")
            except Exception as e:
                print(f"Erreur lors du test d'accès à l'API: {e}")
                if hasattr(e, 'status') and hasattr(e, 'reason'):
                    print(f"Status: {e.status}, Reason: {e.reason}")
                # Afficher la configuration active pour le debug
                print("\nConfiguration active:")
                print(f"Host: {api_client.configuration.host}")
                print(f"API Key: {'Présent' if api_client.configuration.api_key else 'Absent'}")
                print(f"Verify SSL: {api_client.configuration.verify_ssl}")
                if hasattr(api_client.configuration, 'ssl_ca_cert'):
                    print(f"SSL CA Cert: {api_client.configuration.ssl_ca_cert}")

            self.namespaces = namespaces
            self.components = components if components else DEFAULT_COMPONENTS
            self.aws_collector = aws_collector
            
            print("Initialisation terminée")
        except Exception as e:
            print(f"Erreur critique lors de l'initialisation du client Kubernetes: {e}")
            if hasattr(e, 'status') and hasattr(e, 'reason'):
                print(f"Status: {e.status}, Reason: {e.reason}")
            sys.exit(1)

    def _matches_pod_components(self, name):
        """Partial match for pods."""
        matches = any(component in name for component in self.components)
        #print(f"Checking pod {name} against components {self.components} -> matches: {matches}")
        return matches

    def _matches_service_components(self, name):
        """Exact match for services."""
        return name in self.components

    def _get_pod_resources(self, pod):
        """Extrait les resources d'un pod en gérant les cas None."""
        resources = {}
        try:
            container = pod.spec.containers[0]
            if container.resources:
                requests = container.resources.requests or {}
                limits = container.resources.limits or {}
                resources = {
                    'requests': {
                        'cpu': requests.get('cpu', ''),
                        'memory': requests.get('memory', '')
                    },
                    'limits': {
                        'cpu': limits.get('cpu', ''),
                        'memory': limits.get('memory', '')
                    }
                }
        except (AttributeError, IndexError) as e:
            print(f"Warning: Could not get resources for pod {pod.metadata.name}: {e}")
            resources = {
                'requests': {'cpu': '', 'memory': ''},
                'limits': {'cpu': '', 'memory': ''}
            }
        return resources

    def get_pods(self):
        """Get pods corresponding to components."""
        try:
            pods_by_ns = {}
            for ns in self.namespaces:
                #print(f"\nChecking namespace: {ns}")
                pods = self.v1.list_namespaced_pod(ns)
                matched_pods = {
                    pod.metadata.name: {
                        'node_name': pod.spec.node_name,
                        'labels': pod.metadata.labels,
                        'status': pod.status.phase,
                        'component': next((c for c in self.components if c in pod.metadata.name), None),
                        'resources': self._get_pod_resources(pod)
                    } for pod in pods.items
                    if self._matches_pod_components(pod.metadata.name)
                }
                #print(f"Found {len(matched_pods)} matching pods in namespace {ns}")
                pods_by_ns[ns] = matched_pods
            return pods_by_ns
        except Exception as e:
            print(f"Error getting pods: {e}")
            return {}

    def get_nodes(self):
        """Get nodes information with AWS instance specifications."""
        try:
            nodes = self.v1.list_node()
            # Récupération des métriques via l'API metrics.k8s.io
            try:
                metrics_list = self.custom.list_cluster_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    plural="nodes"
                )
                metrics_by_node = {
                    item['metadata']['name']: item['usage']
                    for item in metrics_list.get('items', [])
                }
            except Exception as e:
                print(f"Warning: Could not get metrics: {e}")
                metrics_by_node = {}

            nodes_info = {}
            for node in nodes.items:
                instance_id = None
                subnet_id = None
                provider_id = node.spec.provider_id
                instance_type = node.metadata.labels.get('node.kubernetes.io/instance-type')
                region = node.metadata.labels.get('topology.kubernetes.io/region')
                
                # Si on a un collecteur AWS, on enrichit l'information de l'instance
                if self.aws_collector:
                    if instance_type:
                        formatted_instance_type = self.aws_collector.format_instance_specs(instance_type, region)
                    if provider_id and provider_id.startswith('aws:///'):
                        instance_id = provider_id.split('/')[-1]
                        subnet_id = self.aws_collector.get_instance_subnet(instance_id, region)
                else:
                    formatted_instance_type = instance_type
                    instance_id = provider_id

                nodes_info[node.metadata.name] = {
                    'instance_type': formatted_instance_type,
                    'zone': node.metadata.labels.get('topology.kubernetes.io/zone'),
                    'nodegroup': node.metadata.labels.get('eks.amazonaws.com/nodegroup', 'unknown'),
                    'labels': node.metadata.labels,
                    'capacity': {
                        'cpu': node.status.capacity.get('cpu', ''),
                        'memory': node.status.capacity.get('memory', '')
                    },
                    'allocatable': {
                        'cpu': node.status.allocatable.get('cpu', ''),
                        'memory': node.status.allocatable.get('memory', '')
                    },
                    'usage': metrics_by_node.get(node.metadata.name, {}),
                    'subnet_id': subnet_id
                }
            return nodes_info
        except Exception as e:
            print(f"Error getting nodes: {e}")
            return {}

    def get_services(self):
        """Get services corresponding to components."""
        try:
            services_by_ns = {}
            for ns in self.namespaces:
                services = self.v1.list_namespaced_service(ns)
                services_by_ns[ns] = {
                    svc.metadata.name: {
                        'selector': svc.spec.selector,
                        'type': svc.spec.type,
                        'ports': svc.spec.ports,
                        'component': svc.metadata.name if self._matches_service_components(svc.metadata.name) else None
                    } for svc in services.items
                    if self._matches_service_components(svc.metadata.name)
                }
            return services_by_ns
        except Exception as e:
            print(f"Error getting services: {e}")
            return {}

    def get_ingresses(self):
        """Récupère les règles d'ingress pour chaque namespace."""
        try:
            ingresses_by_ns = {}
            for ns in self.namespaces:
                ingresses = self.networking.list_namespaced_ingress(ns)
                ingresses_by_ns[ns] = {}
                for ing in ingresses.items:
                    rules = []
                    for rule in ing.spec.rules:
                        paths = []
                        if rule.http and rule.http.paths:
                            for path in rule.http.paths:
                                paths.append({
                                    'host': rule.host,
                                    'path': path.path,
                                    'service_name': path.backend.service.name,
                                    'service_port': path.backend.service.port.number
                                })
                        rules.extend(paths)
                    
                    # Récupérer le hostname du load balancer
                    hostname = None
                    if ing.status and ing.status.load_balancer and ing.status.load_balancer.ingress:
                        hostname = ing.status.load_balancer.ingress[0].hostname

                    ingresses_by_ns[ns][ing.metadata.name] = {
                        'rules': rules,
                        'annotations': ing.metadata.annotations or {},
                        'labels': ing.metadata.labels or {},
                        'hostname': hostname,  # Ajout du hostname
                        'name': ing.metadata.name  # Ajout du nom de l'ingress pour fallback
                    }
            return ingresses_by_ns
        except Exception as e:
            print(f"Error getting ingresses: {e}")
            return {}

