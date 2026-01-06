"""Générateur de diagramme d'architecture."""

from datetime import datetime
from diagrams import Diagram, Cluster, Edge, Node
from diagrams.aws.network import CloudFront, ELB, APIGateway, VPC, PrivateSubnet, PublicSubnet
from diagrams.aws.compute import EC2, Lambda
from diagrams.aws.database import RDS
from diagrams.k8s.compute import Pod
from diagrams.k8s.network import Service

from typing import Dict, List, Optional

from rubix_diagram.config.settings import EDGE_STYLES, GRAPH_ATTR
from rubix_diagram.config.components import SERVICE_RELATIONS

from rubix_diagram.generators.diagram_utils import (
    get_service_base_name,
    group_services_by_type,
    find_service_by_type,
    create_node_or_pod_label,
    prepare_nodes_and_pods_by_az,
    group_ingress_rules,
    format_hosts_for_display,
    get_namespace_graph_attr
)

def generate_diagram(regions_info: Dict[str, dict], output_file: str) -> None:
    """
    Génère le diagramme d'architecture multi-région.
    
    Args:
        regions_info: Dictionnaire contenant les informations de chaque région
            {
                'region_name': {
                    'k8s_info': dict,
                    'rds_info': dict,
                    'apigw_info': dict,
                    'lambda_info': dict,
                    'vpc_info': dict
                }
            }
        output_file: Nom du fichier de sortie
    """
    generation_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    diagram_title = f"{output_file} - generated on {generation_time}"
    
    with Diagram(
        diagram_title,
        filename=output_file,
        show=False,
        direction="LR",
        graph_attr=GRAPH_ATTR
    ):
        # CloudFront global
        cloudfront = CloudFront("CloudFront")
        
        # Créer un dictionnaire pour stocker les éléments de chaque région
        region_elements = {}
        
        # Traiter chaque région
        for region, region_info in regions_info.items():
            k8s_info = region_info.get('k8s_info', {})
            rds_info = region_info.get('rds_info', {})
            apigw_info = region_info.get('apigw_info', {})
            lambda_info = region_info.get('lambda_info', {})
            vpc_info = region_info.get('vpc_info', {})
            
            with Cluster(f"AWS Region: {region}"):
                # Stocker les éléments de la région
                region_elements[region] = {
                    'gateways': {},
                    'lambdas': {},
                    'nginx': [],
                    'albs': {},
                    'pods': {},
                    'services': {},
                    'rds': {}
                }

                # NBS INFRA MUTUALIZED ACCOUNT
                with Cluster("NBS INFRA MUTUALIZED AWS ACCOUNT"):
                    nbs_alb = ELB("public ALB")
                    with Cluster("Nginx ASG"):
                        nginx_nodes = [
                            EC2("nginx-rp-0"),
                            EC2("nginx-rp-1")
                        ]
                        region_elements[region]['nginx'] = nginx_nodes

                # NBS RUBIX ACCOUNT
                with Cluster("NBS RUBIX AWS ACCOUNT"):
                    # Section API Gateway
                    if apigw_info:
                        with Cluster("API Gateway"):
                            for api_id, api_info in apigw_info.items():
                                api_label = f"{api_info['name']}\n{api_info['endpoint']}"
                                gateway_node = APIGateway(api_label)
                                region_elements[region]['gateways'][api_id] = {
                                    'node': gateway_node,
                                    'resources': api_info.get('resources', [])
                                }
                    if lambda_info:
                        for lambda_name, lambda_detail in lambda_info.items():
                            if lambda_detail.get('subnet_ids', []) == []:
                                if lambda_name not in region_elements[region]['lambdas']:
                                    region_elements[region]['lambdas'][lambda_name] = Lambda(lambda_name)

                    if vpc_info:
                        with Cluster(f"VPC: {vpc_info['name']}"):
                            # Créer les ALB
                            alb_mapping = _create_albs_from_ingress(k8s_info)
                            region_elements[region]['albs'].update(alb_mapping)

                            # Organiser les subnets par AZ
                            subnets_by_az = {}
                            for subnet_id, subnet in vpc_info['subnets'].items():
                                az = subnet['az']
                                if az not in subnets_by_az:
                                    subnets_by_az[az] = {'public': [], 'private': []}
                                subnet_type = 'public' if subnet['is_public'] else 'private'
                                subnets_by_az[az][subnet_type].append((subnet_id, subnet))

                            nodes_by_az, pods_by_node_ns = prepare_nodes_and_pods_by_az(k8s_info, region)

                            # Traiter chaque AZ
                            for az in sorted(subnets_by_az.keys()):
                                with Cluster(f"AZ: {az}"):
                                    # Traiter les subnets publics
                                    for subnet_id, subnet in sorted(subnets_by_az[az]['public']):
                                        subnet_name = f"Public Subnet\n{subnet['name']}\n{subnet['cidr']}"
                                        with Cluster(subnet_name):
                                            pass

                                    # Traiter les subnets privés
                                    for subnet_id, subnet in sorted(subnets_by_az[az]['private']):
                                        subnet_name = f"Private Subnet\n{subnet['name']}\n{subnet['cidr']}"
                                        with Cluster(subnet_name):
                                            _process_subnet_resources(
                                                subnet_id, az, nodes_by_az, pods_by_node_ns,
                                                k8s_info, apigw_info, lambda_info, rds_info,
                                                region_elements[region]
                                            )

                            # Services K8s
                            with Cluster("K8S Services", graph_attr={"rank": "same"}):
                                for namespace in k8s_info['namespaces']:
                                    ns_graph_attr = get_namespace_graph_attr(namespace)
                                    with Cluster(f"Namespace: {namespace}", graph_attr=ns_graph_attr):
                                        grouped_services = group_services_by_type(k8s_info['services'][namespace])
                                        for group_name, services in grouped_services.items():
                                            if services:
                                                with Cluster(group_name):
                                                    for svc_name, svc_info in services:
                                                        region_elements[region]['services'][f"{namespace}/{svc_name}"] = Service(svc_name)

                # Ajouter les connexions pour cette région
                _add_region_connections(
                    region_elements[region],
                    cloudfront,
                    nbs_alb,
                    nginx_nodes,
                    k8s_info,
                    rds_info
                )

        # Ajouter les connexions inter-régions
        _add_cross_region_connections(region_elements)

def _process_subnet_resources(subnet_id, az, nodes_by_az, pods_by_node_ns, k8s_info, apigw_info, lambda_info, rds_info, elements):
    """Process les ressources d'un subnet."""
    # Nodes EKS et pods
    if az in nodes_by_az:
        for node_name, node_info in nodes_by_az[az]:
            if node_info.get('subnet_id') == subnet_id:
                node_label = create_node_or_pod_label(
                    node_name,
                    node_info['nodegroup'],
                    node_info['instance_type']
                )
                with Cluster(node_label):
                    if node_name in pods_by_node_ns:
                        for namespace in k8s_info['namespaces']:
                            if namespace in pods_by_node_ns[node_name]:
                                ns_graph_attr = get_namespace_graph_attr(namespace)
                                with Cluster(f"Namespace: {namespace}", graph_attr=ns_graph_attr):
                                    for pod_name, pod_info in pods_by_node_ns[node_name][namespace]:
                                        if pod_info['component']:
                                            pod_label = create_node_or_pod_label(
                                                pod_name,
                                                resources=pod_info.get('resources', {})
                                            )
                                            elements['pods'][f"{namespace}/{pod_name}"] = Pod(pod_label)

    # Lambdas dans ce subnet
    if lambda_info:
        for lambda_name, lambda_detail in lambda_info.items():
            if subnet_id in lambda_detail.get('subnet_ids', []):
                if lambda_name not in elements['lambdas']:
                    elements['lambdas'][lambda_name] = Lambda(lambda_name)

    # RDS
    if rds_info:
        for cluster_id, cluster_info in rds_info.items():
            if az in cluster_info.get('instances_by_az', {}):
                with Cluster(f"RDS Cluster - {cluster_id}"):
                    for instance in cluster_info['instances_by_az'][az]:
                        if instance.get('subnet_id') == subnet_id:
                            label = (
                                f"{instance['identifier']}\n"
                                f"{instance['role']}\n"
                                f"{instance['class']}\n"
                                f"{instance['engine_version']}"
                            )
                            elements['rds'][instance['identifier']] = RDS(label)

def _add_rds_cluster_connections(rds_info, rds_region_elements):
    """
    Ajoute les connexions de réplication entre les instances RDS d'un même cluster.
    
    Args:
        rds_info (dict): Informations sur les clusters RDS
        rds_region_elements (dict): Éléments de la région, notamment les nœuds RDS
    """
    # Parcourir chaque cluster RDS
    for cluster_id, cluster_info in rds_info.items():
        # Collecter les instances de ce cluster qui sont dans region_elements
        cluster_instances = []
        
        # Parcourir toutes les instances du cluster
        for az, instances in cluster_info.get('instances_by_az', {}).items():
            for instance in instances:
                instance_identifier = instance['identifier']
                
                # Vérifier si l'instance existe dans region_elements['rds']
                if instance_identifier in rds_region_elements:
                    cluster_instances.append({
                        'identifier': instance_identifier,
                        'role': instance['role'],
                        'node': rds_region_elements[instance_identifier]
                    })
        
        # Séparer les instances Writer et Reader
        writer_instances = [
            inst for inst in cluster_instances 
            if any(role in inst['role'].lower() for role in ['writer', 'primary', 'master'])
        ]
        reader_instances = [
            inst for inst in cluster_instances 
            if any(role in inst['role'].lower() for role in ['reader', 'replica', 'secondary'])
        ]
        
        # Créer les connexions de réplication
        for writer in writer_instances:
            for reader in reader_instances:
                writer['node'] >> Edge(
                    label="Replication", 
                    color="darkgreen", 
                    style="dashed", 
                    constraint="false"
                ) >> reader['node']

def _add_region_connections(region_elements, cloudfront, nbs_alb, nginx_nodes, k8s_info, rds_info):
    """Ajoute les connexions pour une région."""
    # API Gateway vers Lambda
    for api_id, gateway_info in region_elements['gateways'].items():
        gateway_node = gateway_info['node']
        lambda_paths = {}
        
        # Pour chaque ressource de l'API Gateway
        for resource in gateway_info['resources']:
            lambda_name = resource.get('lambda_name')
            if lambda_name and lambda_name in region_elements['lambdas']:
                if lambda_name not in lambda_paths:
                    lambda_paths[lambda_name] = []
                lambda_paths[lambda_name].append(
                    f"{resource['method']} {resource['path']}"
                )
        
        # Créer les connexions vers les Lambdas
        for lambda_name, paths in lambda_paths.items():
            edge_label = "\n".join(paths)
            gateway_node >> Edge(label=edge_label, **EDGE_STYLES['lambda']) >> region_elements['lambdas'][lambda_name]

    # Layout invisibles
    _add_invisible_layout_edges(region_elements['pods'], region_elements['services'])

    # Relations entre services
    for namespace in k8s_info.get('namespaces', {}):
        _add_service_relationships(
            {k: v for k, v in region_elements['services'].items() if k.startswith(f"{namespace}/")},
            {k: v for k, v in region_elements['pods'].items() if k.startswith(f"{namespace}/")},
            k8s_info['pods'][namespace],
            k8s_info['services'][namespace]
        )

    _add_rds_cluster_connections(rds_info, region_elements['rds'])

    # Connexions Ingress
    _add_ingress_connections(
        cloudfront, nbs_alb, nginx_nodes,
        region_elements['services'],
        region_elements['rds'],
        k8s_info,
        region_elements['albs']
    )

def _add_cross_region_connections(region_elements):
    """
    Adds cross-region connections for API Gateway and ALB to Lambdas.
    """
    # For each source region
    for source_region, source_elements in region_elements.items():
        # Handle API Gateway cross-region
        for api_id, api_gateway in source_elements['gateways'].items():
            gateway_node = api_gateway['node']
            lambda_paths_by_region = {}
            
            # For each resource in the API Gateway
            for resource in api_gateway.get('resources', []):
                # Skip if no lambda_arn is present
                if not resource.get('lambda_arn'):
                    continue
                    
                # Extract region from Lambda ARN
                lambda_region = resource['lambda_arn'].split(':')[3]
                lambda_name = resource.get('lambda_name')
                
                # If Lambda is in another region
                if lambda_region != source_region and lambda_name:
                    if lambda_region not in lambda_paths_by_region:
                        lambda_paths_by_region[lambda_region] = {}
                    if lambda_name not in lambda_paths_by_region[lambda_region]:
                        lambda_paths_by_region[lambda_region][lambda_name] = []
                    
                    lambda_paths_by_region[lambda_region][lambda_name].append(
                        f"{resource['method']} {resource['path']}"
                    )
            
            # Create connections for each target region
            for target_region, lambda_paths in lambda_paths_by_region.items():
                if target_region in region_elements:
                    for lambda_name, paths in lambda_paths.items():
                        if lambda_name in region_elements[target_region]['lambdas']:
                            edge_label = "\n".join(paths)
                            gateway_node >> Edge(
                                label=f"Cross-region: {edge_label}",
                                **EDGE_STYLES['lambda']
                            ) >> region_elements[target_region]['lambdas'][lambda_name]

        # Handle ALB cross-region
        alb_lambda_paths_by_region = {}
        for alb_name, alb in source_elements['albs'].items():
            grouped_rules = group_ingress_rules(source_elements.get('k8s_info', {}).get('ingresses', {}))
            
            # For each namespace and service
            for ns, services in grouped_rules.items():
                for service_name, service_info in services.items():
                    # Skip if no lambda_arn is present
                    if not service_info.get('lambda_arn'):
                        continue
                        
                    # If service is Lambda and in another region
                    lambda_region = service_info['lambda_arn'].split(':')[3]
                    lambda_name = service_info.get('lambda_name')
                    
                    if lambda_region != source_region and lambda_name:
                        if lambda_region not in alb_lambda_paths_by_region:
                            alb_lambda_paths_by_region[lambda_region] = {}
                        if lambda_name not in alb_lambda_paths_by_region[lambda_region]:
                            alb_lambda_paths_by_region[lambda_region][lambda_name] = []
                        
                        alb_lambda_paths_by_region[lambda_region][lambda_name].append(
                            f"{service_info.get('hosts', ['*'])[0]} → {service_name}"
                        )
            
            # Create connections for each target region
            for target_region, lambda_paths in alb_lambda_paths_by_region.items():
                if target_region in region_elements:
                    for lambda_name, paths in lambda_paths.items():
                        if lambda_name in region_elements[target_region]['lambdas']:
                            edge_label = "\n".join(paths)
                            alb >> Edge(
                                label=f"Cross-region: {edge_label}",
                                **EDGE_STYLES['lambda']
                            ) >> region_elements[target_region]['lambdas'][lambda_name]

def _add_invisible_layout_edges(pod_elements, service_elements):
    """Ajoute des edges invisibles pour forcer la disposition."""
    invisible_edge = {"style": "invis", "constraint": "true", "weight": "100"}
    if pod_elements and service_elements:
        first_pod = list(pod_elements.values())[0]
        last_pod = list(pod_elements.values())[-1]
        first_service = list(service_elements.values())[0]

        first_pod >> Edge(**invisible_edge) >> first_service
        first_service >> Edge(**invisible_edge) >> last_pod

def _add_service_relationships(service_elements, pod_elements, pods_info, services_info):
    """Ajoute les relations entre services d'un même namespace."""
    for full_svc_name, svc_element in service_elements.items():
        namespace = full_svc_name.split('/')[0]
        base_name = get_service_base_name(full_svc_name)
        
        if base_name in SERVICE_RELATIONS:
            relation = SERVICE_RELATIONS[base_name]
            
            # Connect service to its pods within the same namespace
            matching_pods = [pod for pod_name, pod in pod_elements.items() 
                           if pod_name.startswith(f"{namespace}/") and base_name in pod_name]

            # Connect service to pods and pods to target services
            if matching_pods:
                svc_element >> Edge(**relation['style']) >> matching_pods
                
                if 'targets' in relation:
                    for target in relation['targets']:
                        target_service = next(
                            (svc for name, svc in service_elements.items()
                             if name.startswith(f"{namespace}/") and target in name),
                            None
                        )
                        if target_service:
                            matching_pods >> Edge(**relation['style']) >> target_service

def _create_alb_label(alb_name, ingresses):
    """Crée le label de l'ALB avec les règles d'ingress groupées."""
    # Grouper les règles
    grouped_rules = group_ingress_rules(ingresses)
    
    # Formater le label
    label_parts = [alb_name]
    
    for ns, services in grouped_rules.items():
        for service_name, service_info in services.items():
            hosts_display = format_hosts_for_display(service_info['hosts'], max_per_line=1)
            label_parts.append(f"{hosts_display} → {service_name}:{service_info['port']}")
    
    return "\n".join(label_parts)

def _create_albs_from_ingress(k8s_info):
    """
    Crée les ALB à partir des ingresses.
    
    Args:
        k8s_info (dict): Informations Kubernetes

    Returns:
        dict: Mapping des ALB créés par leur nom
    """
    alb_mapping = {}
    
    for ns, ingresses in k8s_info['ingresses'].items():
        for ing_name, ing_info in ingresses.items():
            # Utiliser le hostname s'il existe, sinon le nom de l'ingress
            alb_name = ing_info.get('hostname') or ing_info['name']
            
            if alb_name not in alb_mapping:
                alb_mapping[alb_name] = ELB(alb_name)
    
    return alb_mapping

def _add_ingress_connections(cloudfront, nbs_alb, nginx_nodes, service_elements, rds_elements, k8s_info, alb_mapping):
    """Configure les connexions d'entrée avec les règles groupées."""

    # Si aucun ALB n'a été trouvé dans les ingress, créer un ALB par défaut
    if not alb_mapping:
        alb_mapping['private ALB'] = ELB('private ALB')

    # Connexions de base pour le front
    cloudfront >> Edge(**EDGE_STYLES['ingress']) >> nbs_alb
    nbs_alb >> Edge(**EDGE_STYLES['ingress']) >> nginx_nodes[0]
    nbs_alb >> Edge(**EDGE_STYLES['ingress']) >> nginx_nodes[1]

    # Connecter les nginx aux ALB
    for alb in alb_mapping.values():
        nginx_nodes[0] >> Edge(**EDGE_STYLES['ingress']) >> alb
        nginx_nodes[1] >> Edge(**EDGE_STYLES['ingress']) >> alb

    ingresses = k8s_info.get('ingresses', {})
    # Grouper les rules par service
    grouped_rules = group_ingress_rules(ingresses)

    # Connecter les ALB aux services en utilisant les groupes
    for ns, ingresses in ingresses.items():
        for ing_name, ing_info in ingresses.items():
            # Utiliser le hostname s'il existe, sinon utiliser l'ALB par défaut
            alb_name = ing_info.get('hostname', 'private ALB')
            alb = alb_mapping.get(alb_name) or next(iter(alb_mapping.values()))

            # Utiliser les règles groupées pour ce namespace
            for service_name, service_info in grouped_rules[ns].items():
                service_key = f"{ns}/{service_name}"
                if service_key in service_elements:
                    alb >> Edge(**EDGE_STYLES['ingress']) >> service_elements[service_key]

def create_legend(namespaces, edge_styles):
    """
    Crée un cluster de légende pour le diagramme.
    
    Args:
        diagram: Instance du diagramme principal
        namespaces (list): Liste des namespaces
        edge_styles (dict): Styles des connexions définis dans settings.EDGE_STYLES
    """
    legend_style = {
        "margin": "40",
        "fontsize": "13"
    }
    invisible_edge = {
        "style": "invis",
        "constraint": "true",
        "weight": "100"
    }

    with Cluster("Legend", graph_attr=legend_style):
        ns_anchor = None
        ct_anchor = None
        
        # Légende des namespaces
        with Cluster("Namespaces", graph_attr={"margin": "20"}):
            # Créer un petit Node pour chaque namespace
            for ns in namespaces:
                graph_attr = get_namespace_graph_attr(ns)
                with Cluster(ns, graph_attr=graph_attr):
                    node = Node("", shape="point", width="0", height="0")
                    if ns_anchor is None:
                        ns_anchor = node

        # Légende des connexions
        with Cluster("Connection Types", graph_attr={"margin": "20"}):
            for edge_name, edge_style in edge_styles.items():
                start = Node("", shape="point", width="0.1", height="0.1")
                end = Node("", shape="point", width="0.1", height="0.1")
                start >> Edge(label=edge_name, **edge_style) >> end
                if ct_anchor is None:
                    ct_anchor = start

        if ns_anchor and ct_anchor:
            ns_anchor >> Edge(**invisible_edge) >> ct_anchor