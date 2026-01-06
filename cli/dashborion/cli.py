#!/usr/bin/env python3

"""Entry point diagram generator with CLI and YAML config support"""

import argparse
import yaml
import os
import sys
from typing import Dict, List, Optional

from rubix_diagram.config.components import DEFAULT_COMPONENTS
from rubix_diagram.config.settings import AWS_DEFAULT_REGION
from rubix_diagram.collectors.aws import AWSResourceCollector
from rubix_diagram.collectors.kubernetes import KubernetesInfoCollector
from rubix_diagram.generators.diagram import generate_diagram
from rubix_diagram.publishers.confluence import ConfluencePublisher

def validate_config(config: Dict) -> None:
    """
    Valide la configuration du fichier YAML.
    
    Args:
        config (Dict): Configuration à valider
    
    Raises:
        ValueError: Si la configuration est invalide
    """
    # Vérifier les clés requises au niveau racine
    if 'diagrams' not in config:
        raise ValueError("Configuration manquante : diagrams")
    
    # Valider chaque configuration de diagramme
    for idx, diagram_config in enumerate(config.get('diagrams', []), 1):
        if 'name' not in diagram_config:
            raise ValueError(f"Diagramme {idx} : La clé 'name' est obligatoire")

        if 'regions' not in diagram_config:
            raise ValueError(f"Diagramme {idx} : La clé 'regions' est obligatoire")

        # Valider chaque région
        for region, region_config in diagram_config['regions'].items():
            if not isinstance(region_config, dict):
                raise ValueError(
                    f"Diagramme {diagram_config['name']}, région {region} : "
                    f"La configuration de la région doit être un dictionnaire"
                )
            
            # Vérifier les clés requises pour chaque région
            required_keys = ['context', 'namespaces']
            for key in required_keys:
                if key not in region_config:
                    raise ValueError(
                        f"Diagramme {diagram_config['name']}, région {region} : "
                        f"La clé '{key}' est obligatoire"
                    )

            # Vérifier que namespaces est une liste non vide
            if not isinstance(region_config['namespaces'], list) or not region_config['namespaces']:
                raise ValueError(
                    f"Diagramme {diagram_config['name']}, région {region} : "
                    f"'namespaces' doit être une liste non vide"
                )

            # Vérifier les types optionnels
            if 'components' in region_config and not isinstance(region_config['components'], list):
                raise ValueError(
                    f"Diagramme {diagram_config['name']}, région {region} : "
                    f"'components' doit être une liste"
                )

            if 'rds_clusters' in region_config and not isinstance(region_config['rds_clusters'], list):
                raise ValueError(
                    f"Diagramme {diagram_config['name']}, région {region} : "
                    f"'rds_clusters' doit être une liste"
                )

            if 'api_gateways' in region_config and not isinstance(region_config['api_gateways'], list):
                raise ValueError(
                    f"Diagramme {diagram_config['name']}, région {region} : "
                    f"'api_gateways' doit être une liste"
                )

def _get_region_from_context(context: str) -> str:
    """
    Extrait la région depuis un ARN de contexte EKS.
    
    Args:
        context (str): ARN du cluster EKS
        
    Returns:
        str: Code de la région
        
    Exemple:
        >>> _get_region_from_context("arn:aws:eks:eu-west-3:123456789012:cluster/mon-cluster")
        'eu-west-3'
    """
    try:
        return context.split(':')[3]
    except (IndexError, AttributeError):
        return None

def generate_diagrams_from_yaml(yaml_path: str, push_to_confluence=None, confluence_config_path=None) -> None:
    """
    Génère des diagrammes à partir d'un fichier de configuration YAML.
    """
    # Charger le fichier YAML
    try:
        with open(yaml_path, 'r') as file:
            config = yaml.safe_load(file)
    except (IOError, yaml.YAMLError) as e:
        print(f"Erreur lors de la lecture du fichier YAML : {e}")
        sys.exit(1)
    
    # Valider la configuration
    try:
        validate_config(config)
    except ValueError as e:
        print(f"Erreur de configuration : {e}")
        sys.exit(1)
    
    # Générer chaque diagramme
    for diagram_config in config.get('diagrams', []):
        print(f"Configuration du diagramme : {diagram_config}")
        output = diagram_config['name']

        # Initialiser le collecteur AWS une seule fois pour toutes les régions
        aws_collector = None
        aws_profile = diagram_config.get('aws_profile')  # Profile commun à toutes les régions
        if aws_profile:
            print(f"Initialisation du collecteur AWS avec le profil {aws_profile}")
            aws_collector = AWSResourceCollector(profile_name=aws_profile)

        # Collecter les informations pour chaque région
        regions_info = {}
        for region, region_config in diagram_config['regions'].items():
            print(f"Traitement de la région {region}")

            # Collecter les informations AWS si nécessaire
            rds_info = None
            if region_config.get('rds_clusters') and aws_collector:
                print(f"Collecte des informations RDS pour la région {region}")
                rds_info = aws_collector.get_clusters_info(region_config['rds_clusters'], region)

            # Collecter les informations APIGW si spécifiées
            apigw_info = None
            if region_config.get('api_gateways') and aws_collector:
                print(f"Collecte des informations API Gateway pour la région {region}")
                apigw_info = aws_collector.get_api_gateway_info(region_config['api_gateways'], region=region)

            # Collecter les informations VPC
            vpc_info = None
            if aws_collector and region_config.get('vpc_id'):
                print(f"Collecte des informations VPC pour la région {region}")
                vpc_info = aws_collector.get_vpc_subnets(region_config['vpc_id'], region)

            # Stocker les informations de la région
            #regions_info[region] = {
            #    'k8s_info': k8s_info,
            #    'rds_info': rds_info,
            #    'apigw_info': apigw_info,
            #    'vpc_info': vpc_info
            #}

        # Récupérer toutes les ressources collectées
        regions_info = aws_collector.get_resources_by_region()

        # Ajouter les informations Kubernetes pour chaque région
        for region, region_config in diagram_config['regions'].items():
            print(f"Collecte des informations Kubernetes pour la région {region} / context {region_config['context']}")
            # Collecter les informations Kubernetes
            k8s_collector = KubernetesInfoCollector(
                region_config['context'],
                region_config['namespaces'],
                region_config.get('components', DEFAULT_COMPONENTS),
                aws_collector=aws_collector
            )
            k8s_info = {
                'namespaces': k8s_collector.namespaces,
                'pods': k8s_collector.get_pods(),
                'nodes': k8s_collector.get_nodes(),
                'services': k8s_collector.get_services(),
                'ingresses': k8s_collector.get_ingresses()
            }
            regions_info[region]['k8s_info'] = k8s_info

        # Générer le diagramme avec toutes les régions
        print(f"Génération du diagramme {output}")
        generate_diagram(regions_info, output)

        # Publication sur Confluence si demandé
        if push_to_confluence:
            try:
                publisher = ConfluencePublisher.from_env_or_config(
                    confluence_config_path,
                    aws_collector=aws_collector
                )
                
                output_filename = f"{output}.png"
                page_title = f"Diagram - {output}"
                
                parent_page_id = diagram_config.get('confluence_parent_page_id', None)
                publisher.publish_diagram(
                    file_path=output_filename,
                    title=page_title,
                    parent_page_id=parent_page_id,
                    regions_info=regions_info  # Passage des informations de toutes les régions
                )
                    
            except ValueError as e:
                print(f"Error with Confluence configuration: {e}")
                sys.exit(1)
            except Exception as e:
                print(f"Error publishing to Confluence: {e}")
                sys.exit(1)

def publish_diagrams_from_yaml(k8s_info, rds_info, yaml_path, confluence_config):
    """
    Publie plusieurs diagrammes à partir d'un fichier de configuration YAML.
    
    Args:
        yaml_path (str): Chemin vers le fichier de configuration des diagrammes
        confluence_config (dict): Configuration Confluence
    """
    # Charger la configuration des diagrammes
    with open(yaml_path, 'r') as file:
        diagram_config = yaml.safe_load(file)
    
    # Initialiser le client Confluence
    publisher = ConfluencePublisher(
        url=confluence_config['url'],
        username=confluence_config['username'],
        password=confluence_config['password'],
        space_key=confluence_config['space_key']
    )

    # Parent page ID optionnel
    parent_page_id = confluence_config.get('parent_page_id')

    # Publier chaque diagramme
    for diagram in diagram_config.get('diagrams', []):
        # Construire le chemin complet du fichier
        output_filename = diagram.get('output', 'aws-k8s-diagram') + '.png'
        
        # Titre de la page basé sur le contexte et le namespace
        page_title = f"Diagram - {diagram['output']}"
        
        # Publier le diagramme
        publisher.publish_diagram(
            file_path=output_filename, 
            title=page_title, 
            parent_page_id=parent_page_id,
            k8s_info=k8s_info,
            rds_info=rds_info
        )

def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(description='Generate AWS/K8s architecture diagram')
    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')

    # Sous-commande pour la génération de diagramme individuel
    single_parser = subparsers.add_parser('single', help='Générer un diagramme unique')
    single_parser.add_argument('--context', required=True,
                              help='Kubernetes context')
    single_parser.add_argument('--namespaces', nargs='+', required=True,
                              help='List of Kubernetes namespaces')
    single_parser.add_argument('--output', default='aws-k8s-diagram',
                              help='Output filename (without extension)')
    single_parser.add_argument('--components', nargs='+',
                              help=f'List of components to include (default: {DEFAULT_COMPONENTS})')
    single_parser.add_argument('--aws-rds-clusters', nargs='+',
                              help='RDS clusters identifiers')
    single_parser.add_argument('--aws-api-gateways', nargs='+',
                              help='API Gateway identifiers')
    single_parser.add_argument('--aws-profile',
                              help='AWS profile to use')
    single_parser.add_argument('--aws-region', default=AWS_DEFAULT_REGION,
                              help=f'AWS region to use (default: {AWS_DEFAULT_REGION})')
    single_parser.add_argument('--vpc-id',
                              help='AWS VPC ID to use for subnet information')

    # Sous-commande pour la génération de diagrammes à partir d'un fichier YAML
    yaml_parser = subparsers.add_parser('from_yaml', help='Générer des diagrammes à partir d\'un fichier YAML')
    yaml_parser.add_argument('--config', help='Chemin vers le fichier de configuration YAML')
    yaml_parser.add_argument('--push_to_confluence', help='Publier les diagrammes sur confluence')
    yaml_parser.add_argument('--confluence_config', help='Fichier de configuration Confluence')

    # Parser les arguments
    args = parser.parse_args()

    # Logique de génération de diagramme
    if args.command == 'single':
        print(f"Génération du diagramme pour {args.context}/{args.output} - SINGLE")
        # Use default if not specified
        components = args.components if args.components else DEFAULT_COMPONENTS

        # Initialize AWS collector first if AWS profile is specified
        aws_collector = None
        if args.aws_profile:
            aws_collector = AWSResourceCollector(
                profile_name=args.aws_profile, 
                region=args.aws_region
            )

        # Initialize Kubernetes collector with AWS collector
        k8s_collector = KubernetesInfoCollector(
            args.context, 
            args.namespaces, 
            components,
            aws_collector=aws_collector
        )
        
        k8s_info = {
            'namespaces': k8s_collector.namespaces,
            'pods': k8s_collector.get_pods(),
            'nodes': k8s_collector.get_nodes(),
            'services': k8s_collector.get_services(),
            'ingresses': k8s_collector.get_ingresses()
        }

        # Collect RDS cluster information if specified
        rds_info = None
        if args.aws_rds_clusters and aws_collector:
            rds_info = aws_collector.get_clusters_info(args.aws_rds_clusters)

        # Collect API Gateway information if specified
        apigw_info = None
        if args.aws_api_gateways and aws_collector:
            apigw_info = aws_collector.get_api_gateway_info(args.aws_api_gateways)

        # Get VPC information
        vpc_info = None
        if aws_collector:
            vpc_info = aws_collector.get_vpc_subnets(args.vpc_id if hasattr(args, 'vpc_id') else None)

        # Generate diagram
        generate_diagram(k8s_info, rds_info, apigw_info, vpc_info, args.aws_region, args.output)

    elif args.command == 'from_yaml':
        print(f"Génération des diagrammes à partir du fichier YAML : {args.config}")
        # Générer des diagrammes à partir du fichier YAML
        generate_diagrams_from_yaml(args.config, args.push_to_confluence, args.confluence_config)
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
