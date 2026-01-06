"""Utilitaires pour la génération de diagrammes d'architecture."""

def get_service_base_name(full_name):
    """
    Extrait le nom de base du service.
    
    Args:
        full_name (str): Nom complet du service (peut inclure le namespace)
    
    Returns:
        str: Nom de base du service
    """
    # Extraire le nom du service s'il contient un namespace
    service_name = full_name.split('/')[-1]
    
    base_names = ['apache', 'nextjs', 'haproxy', 'hybris-fo', 'hybris-bo']
    for base in base_names:
        if base in service_name:
            return base
    return None

def group_services_by_type(services):
    """
    Groupe les services par type.
    
    Args:
        services (dict): Dictionnaire des services à grouper
    
    Returns:
        dict: Services groupés par type
    """
    service_groups = {
        'Web Services': [],
        'App Services': [],
        'Backend Services': []
    }
    
    for svc_name, svc_info in services.items():
        if 'apache' in svc_name or 'nextjs' in svc_name:
            service_groups['Web Services'].append((svc_name, svc_info))
        elif 'haproxy' in svc_name or 'hybris-fo' in svc_name:
            service_groups['App Services'].append((svc_name, svc_info))
        elif 'hybris-bo' in svc_name:
            service_groups['Backend Services'].append((svc_name, svc_info))
    
    return service_groups

def find_service_by_type(service_elements, service_type):
    """
    Trouve un service par son type.
    
    Args:
        service_elements (dict): Dictionnaire des éléments de service
        service_type (str): Type de service à rechercher
    
    Returns:
        Service: Service trouvé ou None
    """
    for svc_name, svc in service_elements.items():
        # Extraire le nom du service sans le namespace
        service_name = svc_name.split('/')[-1]
        if service_type in service_name:
            return svc
    return None

def create_node_or_pod_label(name, nodegroup=None, instance_type=None, resources=None):
    """
    Crée une étiquette pour un nœud ou un pod avec des informations détaillées.
    
    Args:
        name (str): Nom du nœud ou du pod
        nodegroup (str, optional): Groupe de nœuds
        instance_type (str, optional): Type d'instance
        resources (dict, optional): Ressources (requests et limits)
    
    Returns:
        str: Étiquette formatée
    """
    # Construire la partie nodegroup et instance_type
    additional_info = []
    if nodegroup:
        additional_info.append(f"({nodegroup})")
    if instance_type:
        additional_info.append(str(instance_type))
    
    # Ajouter les informations sur les ressources si disponibles
    cpu_info = ""
    mem_info = ""
    if resources:
        requests = resources.get('requests', {})
        limits = resources.get('limits', {})
        
        req_cpu = requests.get('cpu', '')
        req_memory = requests.get('memory', '')
        lim_cpu = limits.get('cpu', '')
        lim_memory = limits.get('memory', '')
        
        if req_cpu and lim_cpu:
            cpu_info = f"\nCPU: {req_cpu}/{lim_cpu}"
        if req_memory and lim_memory:
            mem_info = f"\nMEM: {req_memory}/{lim_memory}"
    
    # Combiner toutes les informations
    label = f"{name}"
    if additional_info:
        label += f"\n{' '.join(additional_info)}"
    label += f"{cpu_info}{mem_info}"
    return label

def prepare_nodes_and_pods_by_az(k8s_info, aws_region):
    """
    Prépare les nœuds et pods organisés par zone de disponibilité.
    
    Args:
        k8s_info (dict): Informations Kubernetes contenant les namespaces
        aws_region (str): Région AWS
    
    Returns:
        tuple: Dictionnaires des nœuds et pods par AZ
    """
    nodes_by_az = {f'{aws_region}a': [], f'{aws_region}b': []}
    pods_by_node_ns = {}  # {node_name: {namespace: [(pod_name, pod_info)]}}
    
    # Répartir les nœuds par AZ
    for node_name, node_info in k8s_info['nodes'].items():
        az = node_info['zone']
        if az in nodes_by_az:
            nodes_by_az[az].append((node_name, node_info))
    
    # Répartir les pods par nœud et par namespace
    for namespace in k8s_info['namespaces']:
        for pod_name, pod_info in k8s_info['pods'][namespace].items():
            node_name = pod_info['node_name']
            if node_name not in pods_by_node_ns:
                pods_by_node_ns[node_name] = {}
            if namespace not in pods_by_node_ns[node_name]:
                pods_by_node_ns[node_name][namespace] = []
            pods_by_node_ns[node_name][namespace].append((pod_name, pod_info))
    
    return nodes_by_az, pods_by_node_ns

def group_ingress_rules(ingresses_by_ns):
    """
    Regroupe les règles d'ingress par service de destination.
    
    Args:
        ingresses_by_ns (dict): Dictionnaire des ingress par namespace
        
    Returns:
        dict: Rules groupées par namespace et service
        {
            namespace: {
                service_name: {
                    'port': port,
                    'hosts': [(host, path), ...]
                }
            }
        }
    """
    grouped_rules = {}
    
    for ns, ingresses in ingresses_by_ns.items():
        grouped_rules[ns] = {}
        
        for ing_name, ing_info in ingresses.items():
            for rule in ing_info['rules']:
                service_name = rule['service_name']
                if service_name not in grouped_rules[ns]:
                    grouped_rules[ns][service_name] = {
                        'port': rule['service_port'],
                        'hosts': []
                    }
                
                host_path = (rule['host'], rule['path'])
                if host_path not in grouped_rules[ns][service_name]['hosts']:
                    grouped_rules[ns][service_name]['hosts'].append(host_path)
    
    return grouped_rules

def format_hosts_for_display(hosts, max_per_line=2, make_link=False):
    """
    Formate une liste de hosts pour l'affichage.
    
    Args:
        hosts (list): Liste de tuples (host, path)
        max_per_line (int): Nombre maximum de hosts par ligne
        make_link (bool): Si True, génère des liens HTML pour les hosts
        
    Returns:
        str: Hosts formatés pour l'affichage
    """
    formatted_hosts = []
    current_line = []
    
    for host, path in sorted(hosts, key=lambda x: x[0]):
        if make_link:
            # Génère un lien HTTPS pour le host
            host_str = f'<a href="https://{host}{path}" target="_blank">{host}{path}</a>'
        else:
            host_str = f"{host}{path}"
            
        current_line.append(host_str)
        
        if len(current_line) >= max_per_line:
            formatted_hosts.append(", ".join(current_line))
            current_line = []
    
    if current_line:
        formatted_hosts.append(", ".join(current_line))
    
    return "\n".join(formatted_hosts)

def get_namespace_color(namespace, index=0):
    """
    Retourne une couleur pour un namespace donné.
    Utilise une liste de couleurs distinctes et contrastées.
    
    Args:
        namespace (str): Nom du namespace
        index (int): Index de secours si le namespace n'est pas trouvé dans le mapping
        
    Returns:
        str: Code couleur HTML
    """
    # Couleurs pastels distinctes
    colors = [
        "#E6B3B3",  # Rose pâle
        "#B3D9B3",  # Vert pâle
        "#B3B3E6",  # Bleu pâle
        "#E6CCB3",  # Beige/Orange pâle
        "#CCB3E6",  # Violet pâle
        "#B3E6CC",  # Turquoise pâle
        "#E6E6B3",  # Jaune pâle
        "#FFB3B3",  # Corail pâle
        "#B3FFB3",  # Vert clair
        "#B3B3FF"   # Bleu clair
    ]
    
    # Utilisez le hash du namespace pour choisir une couleur de manière déterministe
    color_index = hash(namespace) % len(colors)
    return colors[color_index]

def get_namespace_graph_attr(namespace):
    """
    Retourne les attributs graphiques pour un cluster de namespace.
    
    Args:
        namespace (str): Nom du namespace
        
    Returns:
        dict: Attributs graphiques Graphviz
    """
    color = get_namespace_color(namespace)
    return {
        "style": "filled",
        "fillcolor": color,
        "fontcolor": "black",
        "color": color,
        "margin": "20"
    }
