#!/usr/bin/env python3

"""Module for publishing diagrams to Confluence"""

import os
import yaml
from atlassian import Confluence
from datetime import datetime

from rubix_diagram.generators.diagram_utils import (
    group_ingress_rules,
    format_hosts_for_display
)

class ConfluencePublisher:
    @classmethod
    def from_env_or_config(cls, config_file=None, aws_collector=None):
        """
        Crée une instance de ConfluencePublisher à partir des variables d'environnement
        ou d'un fichier de configuration.
        """
        # Essayer d'abord les variables d'environnement
        config = {
            'url': os.environ.get('CONFLUENCE_URL'),
            'username': os.environ.get('CONFLUENCE_USERNAME'),
            'password': os.environ.get('CONFLUENCE_PASSWORD'),
            'space_key': os.environ.get('CONFLUENCE_SPACE_KEY'),
            'default_parent_page_id': os.environ.get('CONFLUENCE_DEFAULT_PARENT_PAGE_ID')
        }
        
        # Si certaines variables d'environnement sont manquantes et qu'un fichier est fourni
        missing_required = not all(config[k] for k in ['url', 'username', 'password', 'space_key'])
        if missing_required and config_file:
            try:
                with open(config_file, 'r') as file:
                    file_config = yaml.safe_load(file)
                    # Mettre à jour la config avec les valeurs du fichier
                    for key in config:
                        if not config[key] and key in file_config:
                            config[key] = file_config[key]
            except Exception as e:
                raise ValueError(f"Error reading Confluence config file: {e}")
        
        # Vérifier que tous les champs requis sont présents
        missing_fields = [f for f in ['url', 'username', 'password', 'space_key'] if not config[f]]
        if missing_fields:
            raise ValueError(
                "Missing Confluence configuration. Set these environment variables:\n"
                + "\n".join(f"- CONFLUENCE_{f.upper()}" for f in missing_fields)
                + "\nOr provide them in the configuration file."
            )
        
        # Créer l'instance avec tous les paramètres
        return cls(
            url=config['url'],
            username=config['username'],
            password=config['password'],
            space_key=config['space_key'],
            default_parent_page_id=config.get('default_parent_page_id'),
            aws_collector=aws_collector
        )

    def __init__(self, url, username, password, space_key, default_parent_page_id=None, aws_collector=None):
        """
        Initialise le client Confluence.
        
        Args:
            url (str): URL de l'instance Confluence
            username (str): Nom d'utilisateur
            password (str): Mot de passe ou token d'accès
            space_key (str): Clé de l'espace Confluence
            default_parent_page_id (str, optional): ID de la page parent par défaut
        """
        self.confluence = Confluence(
            url=url,
            username=username,
            password=password
        )
        self.space_key = space_key
        self.default_parent_page_id = default_parent_page_id
        self.aws_collector = aws_collector

    def format_subnet(self, subnet_id):
        if self.aws_collector and subnet_id:
            return self.aws_collector.format_subnet_display(subnet_id)
        return self.subnet_id or 'N/A'

    def format_subnet_list(self, subnet_ids):
        """Format une liste de subnets avec leurs CIDRs"""
        if not subnet_ids:
            return 'N/A'
        return '<br/>'.join(self.format_subnet(subnet_id) for subnet_id in subnet_ids)

    def create_summary_table(self, regions_info):
        """
        Creates an HTML summary table of resources by region.
        
        Args:
            regions_info (dict): Information for all regions
        
        Returns:
            str: Formatted HTML table for Confluence
        """
        table = ""

        # For each region
        for region, info in regions_info.items():
            k8s_info = info.get('k8s_info', {})
            rds_info = info.get('rds_info', {})
            apigw_info = info.get('apigw_info', {})
            lambda_info = info.get('lambda_info', {})

            table += f"<h1>Region: {region}</h1>"

            table += """
            <ac:structured-macro ac:name="info">
                <ac:rich-text-body>
            """

            # Nodes and Pods section
            if k8s_info:
                # Organize pods by node and namespace
                pods_by_node = {}
                for namespace in k8s_info.get('namespaces', []):
                    for pod_name, pod_info in k8s_info.get('pods', {}).get(namespace, {}).items():
                        node_name = pod_info['node_name']
                        if node_name not in pods_by_node:
                            pods_by_node[node_name] = {}
                        if namespace not in pods_by_node[node_name]:
                            pods_by_node[node_name][namespace] = []
                        pods_by_node[node_name][namespace].append((pod_name, pod_info))

                # Group nodes by nodegroup
                nodes_by_group = {}
                for node_name, node_info in k8s_info.get('nodes', {}).items():
                    nodegroup = node_info.get('nodegroup', 'unknown')
                    if nodegroup not in nodes_by_group:
                        nodes_by_group[nodegroup] = []
                    nodes_by_group[nodegroup].append((node_name, node_info))

                table += """
                    <h2>Nodes and Pods</h2>
                    <table>
                        <tr>
                            <th>Nodegroup</th>
                            <th>Node</th>
                            <th>Instance Type</th>
                            <th>Zone</th>
                            <th>Subnet</th>
                            <th>Namespace</th>
                            <th>Pods</th>
                            <th>Resources (requests/limits)</th>
                        </tr>
                """

                for nodegroup, nodes in sorted(nodes_by_group.items()):
                    first_nodegroup_row = True
                    total_nodegroup_rows = sum(
                        len(pods_by_node.get(node_name, {}).get(namespace, []))
                        for node_name, _ in nodes
                        for namespace in k8s_info.get('namespaces', [])
                    )

                    # For each node in the nodegroup
                    for node_name, node_info in sorted(nodes):
                        is_first_node = True
                        total_node_rows = sum(len(pods) for pods in pods_by_node.get(node_name, {}).values())
                        
                        if node_name in pods_by_node:
                            for namespace, pods in sorted(pods_by_node[node_name].items()):
                                for pod_name, pod_info in sorted(pods):
                                    resources = pod_info.get('resources', {})
                                    req_cpu = resources.get('requests', {}).get('cpu', 'N/A')
                                    req_mem = resources.get('requests', {}).get('memory', 'N/A')
                                    lim_cpu = resources.get('limits', {}).get('cpu', 'N/A')
                                    lim_mem = resources.get('limits', {}).get('memory', 'N/A')

                                    table += "<tr>"
                                    if first_nodegroup_row:
                                        table += f"""<td rowspan="{total_nodegroup_rows}">{nodegroup}</td>"""
                                        first_nodegroup_row = False

                                    if is_first_node:
                                        table += f"""
                                            <td rowspan="{total_node_rows}">{node_name}</td>
                                            <td rowspan="{total_node_rows}">{node_info['instance_type']}</td>
                                            <td rowspan="{total_node_rows}">{node_info['zone']}</td>
                                            <td rowspan="{total_node_rows}">{self.format_subnet(node_info.get('subnet_id'))}</td>
                                        """
                                        is_first_node = False
                                    
                                    table += f"""
                                        <td>{namespace}</td>
                                        <td>{pod_name}</td>
                                        <td>CPU: {req_cpu}/{lim_cpu}<br/>MEM: {req_mem}/{lim_mem}</td>
                                    </tr>"""

                table += "</table>"

                # Section Services
                table += """
                        <h2>Services</h2>
                        <table>
                            <tr>
                                <th>Namespace</th>
                                <th>Service</th>
                                <th>Type</th>
                            </tr>
                """
                
                for namespace in k8s_info['namespaces']:
                    for svc_name, svc_info in k8s_info['services'][namespace].items():
                        table += f"""
                            <tr>
                                <td>{namespace}</td>
                                <td>{svc_name}</td>
                                <td>{svc_info['type']}</td>
                            </tr>"""

                table += "</table>"

                # Section Ingress Rules
                table += """
                        <h2>Ingress Rules</h2>
                        <table>
                            <tr>
                                <th>Namespace</th>
                                <th>Service</th>
                                <th>Port</th>
                                <th>Hosts</th>
                            </tr>
                """
                
                # Grouper les règles d'ingress
                grouped_rules = group_ingress_rules(k8s_info['ingresses'])
                
                for namespace, services in grouped_rules.items():
                    is_first_ns = True
                    ns_rowspan = sum(1 for _ in services.items())
                    
                    for service_name, service_info in services.items():
                        table += "<tr>"
                        if is_first_ns:
                            table += f'<td rowspan="{ns_rowspan}">{namespace}</td>'
                            is_first_ns = False
                        
                        hosts_display = format_hosts_for_display(service_info['hosts'], 
                                                            max_per_line=2, 
                                                            make_link=True)
                        table += f"""
                            <td>{service_name}</td>
                            <td>{service_info['port']}</td>
                            <td>{hosts_display}</td>
                        </tr>"""

                table += "</table>"

            # Section API Gateway pour cette région
            if apigw_info:
                table += """
                    <h2>API Gateway Resources</h2>
                    <table>
                        <tr>
                            <th>API Name</th>
                            <th>Endpoint</th>
                            <th>Path</th>
                            <th>Method</th>
                            <th>Lambda Function</th>
                            <th>Lambda Region</th>
                            <th>Subnets</th>
                        </tr>
                """
                
                for api_id, api_info in apigw_info.items():
                    is_first_row = True
                    total_resources = len(api_info['resources'])
                    
                    for resource in api_info['resources']:
                        lambda_region = resource.get('lambda_arn', '').split(':')[3] if resource.get('lambda_arn') else 'N/A'
                        subnet_display = self.format_subnet_list(resource.get('lambda_subnet_ids', []))
                        
                        table += "<tr>"
                        if is_first_row:
                            table += f"""
                                <td rowspan="{total_resources}">{api_info['name']}</td>
                                <td rowspan="{total_resources}">{api_info['endpoint']}</td>
                            """
                            is_first_row = False
                            
                        table += f"""
                            <td>{resource['path']}</td>
                            <td>{resource['method']}</td>
                            <td>{resource['lambda_name']}</td>
                            <td>{lambda_region}</td>
                            <td>{subnet_display}</td>
                        </tr>"""

                table += "</table>"

            # Section RDS Clusters pour cette région
            if rds_info:
                table += """
                    <h2>RDS Clusters</h2>
                    <table>
                        <tr>
                            <th>Cluster ID</th>
                            <th>Instance</th>
                            <th>Class</th>
                            <th>Role</th>
                            <th>AZ</th>
                            <th>Subnet</th>
                            <th>Configuration</th>
                        </tr>
                """
                
                for cluster_id, cluster_data in rds_info.items():
                    is_first_row = True
                    total_instances = sum(len(instances) for instances in cluster_data.get('instances_by_az', {}).values())
                    
                    for az, instances in cluster_data.get('instances_by_az', {}).items():
                        for instance in instances:
                            table += "<tr>"
                            if is_first_row:
                                table += f'<td rowspan="{total_instances}">{cluster_id}</td>'
                                is_first_row = False
                            table += f"""
                                <td>{instance['identifier']}</td>
                                <td>{instance['class']}</td>
                                <td>{instance['role']}</td>
                                <td>{az}</td>
                                <td>{self.format_subnet(instance.get('subnet_id'))}</td>
                                <td>{instance.get('serverless_config', 'N/A')}</td>
                            </tr>"""

                table += "</table>"

            table += """
                </ac:rich-text-body>
            </ac:structured-macro>
            """
        
        return table

    def publish_diagram(self, file_path, title=None, parent_page_id=None, regions_info=None):
        """
        Publie un diagramme sur Confluence.
        
        Args:
            file_path (str): Chemin vers le fichier du diagramme
            title (str, optional): Titre de la page
            parent_page_id (str, optional): ID de la page parent
            regions_info (dict): Information de toutes les régions
        
        Returns:
            dict: Résultat de la publication
        """
        # Utiliser le nom du fichier comme titre si non spécifié
        if not title:
            title = os.path.splitext(os.path.basename(file_path))[0]
        
        # Générer le contenu HTML
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = os.path.basename(file_path)

        page_content = f"""
            <h1>{title}</h1>
            <p>Last updated: {current_time}</p>
        """
        
        page_content += f"""
            <ac:image>
                <ri:attachment ri:filename="{filename}">
                    <ri:timestamp>{int(datetime.now().timestamp() * 1000)}</ri:timestamp>
                </ri:attachment>
            </ac:image>
        """

        if regions_info:
            page_content += self.create_summary_table(regions_info)

        try:
            final_parent_page_id = parent_page_id or self.default_parent_page_id
            # Créer ou mettre à jour la page
            page = self.confluence.update_or_create(
                title=title,
                body=page_content,
                parent_id=final_parent_page_id,
                full_width=True
            )

            # Téléverser le fichier en pièce jointe
            attachment = self.confluence.attach_file(
                file_path, 
                name=filename,
                page_id=page['id']
            )

            print(f"Diagram '{title}' published successfully.")
            return page

        except Exception as e:
            print(f"Error publishing diagram: {e}")
            return None
