"""AWS resource collector."""

import sys
import traceback
import json
import boto3
from typing import Dict, List, Optional
from rubix_diagram.config.settings import AWS_DEFAULT_REGION

class AWSSpecsFetcher:
    """Classe de base pour récupérer les spécifications des instances via l'API Pricing."""
    
    def __init__(self, session: boto3.Session = None):
        """
        Initialise le fetcher avec une région et optionnellement une session boto3.
        
        Args:
            region: Région AWS
            session: Session boto3 existante (optionnelle)
        """
        self._session = session or boto3.Session()
        # L'API pricing n'est disponible qu'en us-east-1
        self.pricing_client = self._session.client('pricing', region_name='us-east-1')
        self._specs_cache = {}

    def _normalize_instance_type(self, instance_type: str) -> str:
        """
        Normalise le type d'instance en retirant le préfixe 'db.' si présent.
        """
        return instance_type.replace('db.', '')

    def _get_normalized_specs(self, instance_type: str, region: str, service_code: str, product_family: str) -> dict:
        """
        Récupère les spécifications normalisées d'une instance.
        
        Args:
            instance_type: Type d'instance (avec ou sans préfixe db.)
            service_code: Code du service AWS (AmazonEC2 ou AmazonRDS)
            product_family: Famille de produit
        """
        normalized_type = self._normalize_instance_type(instance_type)
        
        # Vérifier d'abord dans le cache
        if normalized_type in self._specs_cache:
            return self._specs_cache[normalized_type]

        # Déterminer le type à utiliser pour la requête API
        query_type = instance_type if service_code == 'AmazonRDS' else normalized_type

        filters = [
            {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': query_type},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': product_family},
            {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region},
        ]

        try:
            response = self.pricing_client.get_products(
                ServiceCode=service_code,
                Filters=filters
            )

            if not response['PriceList']:
                if service_code == 'AmazonRDS':
                    # Si pas de résultat pour RDS, essayer avec EC2
                    return self._get_normalized_specs(normalized_type, 'AmazonEC2', 'Compute Instance')
                raise ValueError(f"Aucune spécification trouvée pour {instance_type}")

            price_item = json.loads(response['PriceList'][0])
            attributes = price_item['product']['attributes']

            specs = {
                'vcpu': int(attributes.get('vcpu', 0)),
                'memory_gib': float(attributes.get('memory', '0').split(' ')[0]),
                'network_performance': attributes.get('networkPerformance', ''),
                'architecture': attributes.get('processorArchitecture', ''),
                'processor_features': attributes.get('processorFeatures', '')
            }

            # Stocker dans le cache avec le type normalisé
            self._specs_cache[normalized_type] = specs
            return specs

        except Exception as e:
            raise ValueError(f"Erreur lors de la récupération des specs pour {instance_type}: {str(e)}")

    def get_instance_specs(self, instance_type: str, region: str, for_rds: bool = False) -> dict:
        """
        Point d'entrée public pour récupérer les spécifications d'une instance.
        
        Args:
            instance_type: Type d'instance (avec ou sans préfixe db.)
            for_rds: True si c'est pour une instance RDS
        """
        service_code = 'AmazonRDS' if for_rds else 'AmazonEC2'
        product_family = 'Database Instance' if for_rds else 'Compute Instance'
        
        return self._get_normalized_specs(instance_type, region, service_code, product_family)

class AWSResourceCollector:
    def __init__(self, profile_name=None):
        """
        Initialise le collecteur de ressources AWS.
        
        Args:
            profile_name (str, optional): Nom du profil AWS à utiliser
        """
        try:
            self._session = boto3.Session(profile_name=profile_name)
            # Les clients seront initialisés à la demande par région
            self._clients = {}
            # Le specs fetcher est indépendant de la région (utilise us-east-1)
            self.specs_fetcher = AWSSpecsFetcher(session=self._session)

            # Dictionnaires pour stocker les ressources par région
            self._vpc_info = {}      # région -> vpc_info
            self._rds_info = {}      # région -> cluster_info
            self._apigw_info = {}    # région -> api_info
            self._lambda_info = {}   # région -> lambda_info
            
        except Exception as e:
            print(f"Error initializing AWS session: {e}")
            sys.exit(1)

    def _get_client(self, service: str, region: str):
        """
        Obtient un client AWS pour un service et une région donnés.
        
        Args:
            service (str): Nom du service AWS
            region (str): Région AWS
        """
        if region not in self._clients:
            self._clients[region] = {}
        
        if service not in self._clients[region]:
            self._clients[region][service] = self._session.client(service, region_name=region)
        
        return self._clients[region][service]

    def get_resources_by_region(self) -> Dict[str, Dict]:
        """
        Retourne toutes les ressources collectées, organisées par région.
        
        Returns:
            Dict[str, Dict]: Dictionnaire des ressources par région
            {
                'region': {
                    'vpc_info': {...},
                    'rds_info': {cluster_id: {...}},
                    'apigw_info': {api_id: {...}},
                    'lambda_info': {function_name: {...}}
                }
            }
        """
        # Récupérer l'ensemble des régions depuis toutes les ressources collectées
        regions = set().union(
            self._vpc_info.keys(),
            self._rds_info.keys(),
            self._apigw_info.keys(),
            self._lambda_info.keys()
        )
        
        # Construire le dictionnaire final
        result = {}
        for region in regions:
            result[region] = {
                'vpc_info': self._vpc_info.get(region),
                'rds_info': self._rds_info.get(region, {}),
                'apigw_info': self._apigw_info.get(region, {}),
                'lambda_info': self._lambda_info.get(region, {})
            }
        
        return result

    def format_subnet_display(self, subnet_id):
        """
        Formate l'affichage d'un subnet avec son CIDR.
        
        Args:
            subnet_id (str): ID du subnet
            
        Returns:
            str: Format 'subnet_id (cidr)' ou juste 'subnet_id' si pas d'info de CIDR,
                ou 'N/A' si pas de subnet_id
        """
        if not subnet_id:
            return 'N/A'
            
        # Utiliser le cache des subnets existant
        if not self._vpc_info:
            # Si le cache est vide, essayer de le remplir
            self.get_vpc_subnets()
            
        for region in self._vpc_info.keys():
            vpc_info = self._vpc_info.get(region)
            if vpc_info and 'subnets' in vpc_info:
                subnet_info = vpc_info['subnets'].get(subnet_id)
                if subnet_info:
                    return f"{subnet_id} ({subnet_info['cidr']})"
        if not subnet_info:
            return subnet_id

    def get_vpc_subnets(self, vpc_id: str, region: str) -> Dict:
        """
        Récupère les informations d'un VPC et ses subnets pour une région donnée.
        
        Args:
            vpc_id (str): ID du VPC
            region (str): Région AWS
        """
        ec2 = self._get_client('ec2', region)
        
        if region not in self._vpc_info:
            self._vpc_info[region] = {}
            
        try:
            # Récupérer d'abord les informations du VPC
            if not vpc_id:
                # Si pas de VPC spécifié, chercher le VPC par défaut
                vpcs = ec2.describe_vpcs(Filters=[{'Name': 'is-default', 'Values': ['true']}])['Vpcs']
                if not vpcs:
                    # Si pas de VPC par défaut, prendre le premier VPC trouvé
                    vpcs = ec2.describe_vpcs()['Vpcs']
                if not vpcs:
                    raise ValueError("No VPC found")
                vpc_id = vpcs[0]['VpcId']

            # Récupérer les informations détaillées du VPC
            vpc = ec2.describe_vpcs(VpcIds=[vpc_id])['Vpcs'][0]
            vpc_name = next((tag['Value'] for tag in vpc.get('Tags', []) 
                            if tag['Key'] == 'Name'), vpc_id)

            # Récupérer les subnets du VPC
            subnets = ec2.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['Subnets']
            
            # Organiser les subnets par ID
            subnet_info = {}
            for subnet in subnets:
                subnet_id = subnet['SubnetId']
                name = next((tag['Value'] for tag in subnet.get('Tags', []) 
                            if tag['Key'] == 'Name'), subnet_id)
                
                subnet_info[subnet_id] = {
                    'name': name,
                    'az': subnet['AvailabilityZone'],
                    'cidr': subnet['CidrBlock'],
                    'is_public': subnet.get('MapPublicIpOnLaunch', False),
                    'type': 'Public' if subnet.get('MapPublicIpOnLaunch', False) else 'Private'
                }
            
            # Construire la réponse complète
            vpc_info = {
                'vpc_id': vpc_id,
                'name': vpc_name,
                'cidr': vpc['CidrBlock'],
                'subnets': subnet_info
            }
                    
            self._vpc_info[region] = vpc_info
            return vpc_info
                
        except Exception as e:
            print(f"Error getting VPC and subnet information: {e}")
            return None

    def get_instance_subnet(self, instance_id, region):
        """
        Récupère le subnet d'une instance EC2.
        
        Args:
            instance_id (str): ID de l'instance
            
        Returns:
            str: ID du subnet
        """
        try:
            ec2 = self._get_client('ec2', region)
            instance = ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]
            return instance.get('SubnetId')
        except Exception as e:
            print(f"Error getting instance subnet for {instance_id}: {e}")
            return None

    def get_instance_specs(self, instance_type, region):
        """
        Récupère les spécifications d'un type d'instance EC2.
        
        Args:
            instance_type (str): Type d'instance EC2 (e.g. 't3.micro')
            
        Returns:
            tuple: (vCPU, memory_gb, architecture) ou None si non trouvé
        """
        try:
            specs = self.specs_fetcher.get_instance_specs(instance_type, region, for_rds=False)
            return (
                specs['vcpu'],
                specs['memory_gib'],
                specs['architecture']
            )
        except Exception as e:
            print(f"Error getting instance specs for {instance_type}: {e}")
            return None

    def get_rds_instance_specs(self, instance_class, region, engine):
        """
        Récupère les spécifications d'un type d'instance RDS.
        
        Args:
            instance_class (str): Type d'instance RDS (e.g. 'db.t3.medium')
            engine (str): Moteur de base de données
            
        Returns:
            tuple: (vCPU, memory_gb) ou None si non trouvé
        """
        try:
            specs = self.specs_fetcher.get_instance_specs(instance_class, region, for_rds=True)
            return (specs['vcpu'], specs['memory_gib'])
        except Exception as e:
            print(f"Error getting RDS instance specs for {instance_class}: {e}")
            return None

    def format_instance_specs(self, instance_type, region):
        """
        Formate les spécifications d'instance en chaîne lisible.
        
        Args:
            instance_type (str): Type d'instance EC2
            
        Returns:
            str: Description formatée (e.g. 't3.micro (2 vCPU, 1 GB, arm64)')
        """
        specs = self.get_instance_specs(instance_type, region)
        if not specs:
            return instance_type
            
        vcpu, memory_gb, arch = specs
        return f"{instance_type} ({vcpu} vCPU, {memory_gb:.1f} GB, {arch})"

    def format_rds_instance_specs(self, instance_class, region, engine):
        """
        Formate les spécifications d'instance RDS en chaîne lisible.
        
        Args:
            instance_class (str): Type d'instance RDS
            engine (str): Moteur de base de données
            
        Returns:
            str: Description formatée (e.g. 'db.r5.xlarge (4 vCPU, 32 GB)')
        """
        specs = self.get_rds_instance_specs(instance_class, region, engine)
        if not specs:
            return instance_class
            
        vcpu, memory_gb = specs
        return f"{instance_class} ({vcpu} vCPU, {memory_gb:.1f} GB)"

    def _get_subnet_by_az(self, db_subnet_group: dict, az: str) -> str:
        """
        Récupère l'ID du subnet correspondant à une AZ spécifique dans un groupe de subnets RDS.
        
        Args:
            db_subnet_group: Groupe de subnets RDS
            az: Zone de disponibilité recherchée
            
        Returns:
            str: ID du subnet ou None si non trouvé
        """
        try:
            subnets = db_subnet_group.get('Subnets', [])
            for subnet in subnets:
                subnet_az = subnet.get('SubnetAvailabilityZone', {}).get('Name')
                if subnet_az == az:
                    return subnet.get('SubnetIdentifier')
            return None
        except Exception as e:
            print(f"Error getting subnet for AZ {az}: {e}")
            return None

    def get_cluster_info(self, cluster_identifier, region):
        """Get RDS cluster information."""
        try:
            rds = self._get_client('rds', region)
            cluster_response = rds.describe_db_clusters(
                DBClusterIdentifier=cluster_identifier
            )
            
            if not cluster_response['DBClusters']:
                print(f"No cluster found with identifier: {cluster_identifier}")
                return None

            cluster = cluster_response['DBClusters'][0]
            writer_instance = cluster.get('DBClusterMembers', [])
            writer_instance = next((member['DBInstanceIdentifier'] 
                            for member in writer_instance 
                            if member.get('IsClusterWriter', False)), None)
            engine = cluster.get('Engine', 'N/A')
            engine_version = cluster.get('EngineVersion', 'N/A')

            # Récupérer les informations ServerlessV2 si elles existent
            serverless_config = cluster.get('ServerlessV2ScalingConfiguration', {})
            min_capacity = serverless_config.get('MinCapacity')
            max_capacity = serverless_config.get('MaxCapacity')
                
            instances_response = rds.describe_db_instances(
                Filters=[{
                    'Name': 'db-cluster-id',
                    'Values': [cluster_identifier]
                }]
            )

            instances_by_az = {}
            for instance in instances_response['DBInstances']:
                az = instance['AvailabilityZone']
                if az not in instances_by_az:
                    instances_by_az[az] = []

                instance_class = instance['DBInstanceClass']
                if serverless_config:
                    instance_class += f" ({min_capacity}-{max_capacity} ACU)"
                else:
                    # Ajouter les spécifications détaillées pour les instances non-serverless
                    instance_class = self.format_rds_instance_specs(instance_class, region, engine)

                # Trouver le subnet correspondant à l'AZ de l'instance
                subnet_id = self._get_subnet_by_az(
                    instance.get('DBSubnetGroup', {}),
                    az
                )

                instances_by_az[az].append({
                    'identifier': instance['DBInstanceIdentifier'],
                    'class': instance_class,
                    'role': 'Writer' if instance['DBInstanceIdentifier'] == writer_instance else 'Reader',
                    'engine_version': engine_version,
                    'status': instance['DBInstanceStatus'],
                    'subnet_id': subnet_id
                })

            return {
                'cluster_info': cluster,
                'instances_by_az': instances_by_az
            }

        except Exception as e:
            print(f"Error getting RDS cluster info: {e}")
            return None
    
    def get_clusters_info(self, cluster_identifiers: List[str], region: str) -> Dict:
        """
        Récupère les informations de plusieurs clusters RDS dans une région.
        
        Args:
            cluster_identifiers: Liste des identifiants de clusters
            region: Région AWS
        """

        clusters_info = {}
        
        for cluster_id in cluster_identifiers:
            cluster_info = self.get_cluster_info(cluster_id, region)
            if cluster_info:
                clusters_info[cluster_id] = cluster_info

        if region not in self._rds_info:
            self._rds_info[region] = {} 
        self._rds_info[region] = self._rds_info[region] | clusters_info
        return clusters_info

    def get_api_gateway_info(self, api_ids: List[str]=None, api_type: str=None, region: str=AWS_DEFAULT_REGION):
        """
        Récupère les informations sur les API Gateways et leurs intégrations.
        
        Args:
            api_ids (list, optional): Liste des IDs d'API à récupérer. Si None, récupère toutes les APIs.
            api_type (str, optional): Type d'API Gateway. 
                Peut être 'REST', 'HTTP', 'WEBSOCKET', ou None (pour tous les types)
            region (str): Région AWS
                
        Returns:
            dict: Informations des APIs par ID
            {
                'api_id': {
                    'name': str,
                    'description': str,
                    'type': str,
                    'stage': str,
                    'endpoint': str,
                    'resources': [
                        {
                            'path': str,
                            'method': str,
                            'integration_type': str,
                            'lambda_arn': str,
                            'lambda_name': str
                        }
                    ]
                }
            }
        """
        try:
            apis_info = {}
            
            # Initialiser les clients pour différents types d'API Gateway
            apigateway_v1 = self._get_client('apigateway', region)
            apigateway_v2 = self._get_client('apigatewayv2', region)

            # Sélectionner les méthodes appropriées en fonction du type d'API
            if api_type is None or api_type.upper() == 'REST':
                # Récupérer les REST APIs
                rest_apis = apigateway_v1.get_rest_apis()['items']
                for api in rest_apis:
                    if api_ids and api['id'] not in api_ids:
                        continue
                    
                    apis_info.update(self._process_rest_api(apigateway_v1, api))

            # Supporter les API Gateway V2 (HTTP, WebSocket)
            if api_type is None or api_type.upper() in ['HTTP', 'WEBSOCKET']:
                # Récupérer les APIs HTTP et WebSocket
                v2_apis = apigateway_v2.get_apis()['Items']
                for api in v2_apis:
                    if api_type and api['ProtocolType'].upper() != api_type.upper():
                        continue
                    if api_ids and api['ApiId'] not in api_ids:
                        continue
                    
                    apis_info.update(self._process_v2_api(apigateway_v2, api))

            if region not in self._apigw_info:
                self._apigw_info[region] = {}
            self._apigw_info[region] = self._apigw_info[region] | apis_info
            return apis_info
            
        except Exception as e:
            print(f"Error getting API Gateway info: {e}")
            return {}

    def get_lambda_info(self, function_identifier, region):
        """
        Récupère les informations détaillées d'une fonction Lambda.
        
        Args:
            function_identifier (str): Nom, ARN ou ARN partiel de la fonction Lambda
            region (str): Région AWS
            
        Returns:
            dict: Informations de la fonction Lambda incluant le subnet ou None si non trouvée
        """
        lambda_info = None
        try:
            # Si c'est un ARN, extraire le nom de la fonction
            if function_identifier.startswith('arn:aws:lambda:'):
                function_identifier = self._extract_function_name_from_arn(function_identifier)
                if not function_identifier:
                    return None

            lambda_client = self._get_client('lambda', region)
            function = lambda_client.get_function(FunctionName=function_identifier)
            config = function.get('Configuration', {})
            vpc_config = config.get('VpcConfig', {})
            
            lambda_info = {
                'exists': True,
                'name': config.get('FunctionName', function_identifier),
                'runtime': config.get('Runtime', 'unknown'),
                'subnet_ids': vpc_config.get('SubnetIds', []),
                'security_groups': vpc_config.get('SecurityGroupIds', [])
            }
        except lambda_client.exceptions.ResourceNotFoundException:
            lambda_info = {
                'exists': False,
                'name': function_identifier,
                'runtime': 'N/A',
                'subnet_ids': [],
                'security_groups': []
            }
        except Exception as e:
            print(f"Error getting Lambda info for {function_identifier}: {e}")
            print("Detailed error:")
            print(traceback.format_exc())
            if 'function' in locals():
                print(f"Lambda function response: {function}")
            lambda_info = None
        if region not in self._lambda_info:
            self._lambda_info[region] = {} 
        self._lambda_info[region].update({ function_identifier: lambda_info})
        return lambda_info

    def _extract_lambda_arn_from_uri(self, uri: str, api_type: str = 'REST') -> str:
        """
        Extrait l'ARN Lambda complet depuis l'URI d'intégration API Gateway.
        
        Args:
            uri: URI d'intégration API Gateway
            api_type: Type d'API ('REST' ou 'HTTP')
            
        Returns:
            str: ARN Lambda complet ou None
        """
        try:
            # Le format est le même pour les deux types d'API:
            # arn:aws:apigateway:REGION:lambda:path/2015-03-31/functions/LAMBDA_ARN/invocations
            parts = uri.split('/functions/')
            if len(parts) > 1:
                return parts[1].split('/invocations')[0]
            return None
        except Exception as e:
            print(f"Warning: Error extracting Lambda ARN from URI: {e}")
            return None

    def _extract_region_from_arn(self, arn: str) -> str:
        """
        Extrait la région depuis un ARN AWS.
        
        Args:
            arn: ARN complet du service AWS
            
        Returns:
            str: Code de la région ou None si non trouvé
            
        Examples:
            >>> _extract_region_from_arn("arn:aws:lambda:eu-west-1:123456789:function:my-function")
            'eu-west-1'
            >>> _extract_region_from_arn("arn:aws:eks:eu-central-1:123456789:cluster/my-cluster")
            'eu-central-1'
        """
        try:
            # Un ARN a toujours le format: arn:aws:service:region:account:resource
            parts = arn.split(':')
            if len(parts) >= 4:
                return parts[3]
            return None
        except Exception as e:
            print(f"Warning: Error extracting region from ARN: {e}")
            return None

    def _extract_function_name_from_arn(self, arn: str) -> str:
        """
        Extrait le nom de la fonction depuis un ARN Lambda.
        
        Args:
            arn: ARN Lambda complet (format: arn:aws:lambda:REGION:ACCOUNT:function:FUNCTION_NAME[:ALIAS])
            
        Returns:
            str: Nom de la fonction ou None
            
        Examples:
            >>> _extract_function_name_from_arn("arn:aws:lambda:eu-west-1:123456789:function:my-function")
            'my-function'
            >>> _extract_function_name_from_arn("arn:aws:lambda:eu-west-1:123456789:function:my-function:prod")
            'my-function'
        """
        try:
            # Découper l'ARN sur ':'
            parts = arn.split(':')
            # Le nom de la fonction est après "function:" et peut être suivi d'un alias
            if 'function' in parts:
                function_index = parts.index('function') + 1
                if function_index < len(parts):
                    return parts[function_index]
            return None
        except Exception as e:
            print(f"Warning: Error extracting function name from ARN: {e}")
            return None

    def _process_rest_api(self, apigateway_client, api):
        """
        Traite une API REST et extrait ses informations détaillées.
        """
        api_id = api['id']
        apis_info = {}

        try:
            stages = apigateway_client.get_stages(restApiId=api_id)
            resources = apigateway_client.get_resources(restApiId=api_id)['items']
            
            api_info = {
                'name': api['name'],
                'description': api.get('description', ''),
                'type': 'REST',
                'stage': stages['item'][0]['stageName'] if stages['item'] else '',
                'endpoint': f"https://{api_id}.execute-api.{apigateway_client.meta.region_name}.amazonaws.com",
                'resources': []
            }

            for resource in resources:
                if 'resourceMethods' in resource:
                    for method in resource['resourceMethods'].keys():
                        try:
                            integration = apigateway_client.get_integration(
                                restApiId=api_id,
                                resourceId=resource['id'],
                                httpMethod=method
                            )
                            
                            resource_info = {
                                'path': resource['path'],
                                'method': method,
                                'integration_type': integration.get('type', 'NONE'),
                                'lambda_arn': None,
                                'lambda_name': None,
                                'lambda_exists': False,
                                'lambda_subnet_ids': []
                            }

                            # Vérifier si c'est une intégration Lambda
                            if integration.get('type') == 'AWS_PROXY' and 'uri' in integration:
                                try:
                                    lambda_arn = self._extract_lambda_arn_from_uri(integration['uri'])
                                    lambda_region = self._extract_region_from_arn(lambda_arn)
                                    if lambda_arn:
                                        lambda_info = self.get_lambda_info(lambda_arn, region=lambda_region)
                                        
                                        if lambda_info:
                                            resource_info.update({
                                                'lambda_arn': lambda_arn,
                                                'lambda_name': lambda_info['name'],
                                                'lambda_exists': lambda_info['exists'],
                                                'lambda_subnet_ids': lambda_info['subnet_ids']
                                            })
                                except Exception as e:
                                    print(f"Warning: Error processing Lambda integration for {resource['path']} {method}: {e}")
                            
                            api_info['resources'].append(resource_info)
                        except apigateway_client.exceptions.NotFoundException:
                            print(f"Warning: No integration found for {resource['path']} {method}")
                        except Exception as e:
                            print(f"Warning: Could not get integration for {resource['path']} {method}: {e}")

            apis_info[api_id] = api_info
        except Exception as e:
            print(f"Error processing REST API {api_id}: {e}")

        return apis_info

    def _process_v2_api(self, apigateway_v2_client, api):
        """
        Traite une API V2 (HTTP ou WebSocket) et extrait ses informations détaillées.
        """
        api_id = api['ApiId']
        apis_info = {}

        try:
            stages = apigateway_v2_client.get_stages(ApiId=api_id)['Items']
            routes = apigateway_v2_client.get_routes(ApiId=api_id)['Items']
            
            api_info = {
                'name': api['Name'],
                'description': api.get('Description', ''),
                'type': api['ProtocolType'].upper(),
                'stage': stages[0]['StageName'] if stages else '',
                'endpoint': f"https://{api_id}.execute-api.{apigateway_v2_client.meta.region_name}.amazonaws.com",
                'resources': []
            }

            for route in routes:
                resource_info = {
                    'path': route['RouteKey'],
                    'method': route['RouteKey'].split()[0] if ' ' in route['RouteKey'] else 'ANY',
                    'integration_type': 'NONE',
                    'lambda_arn': None,
                    'lambda_name': None,
                    'lambda_exists': False,
                    'lambda_subnet_ids': []
                }

                # Vérifier si la route a une intégration
                if 'Target' in route:
                    try:
                        integration = apigateway_v2_client.get_integration(
                            ApiId=api_id,
                            IntegrationId=route['Target'].split('/')[-1]
                        )
                        
                        resource_info['integration_type'] = integration.get('IntegrationType', 'NONE')

                        # Vérifier si c'est une intégration Lambda
                        if integration.get('IntegrationType') == 'AWS_PROXY' and 'IntegrationUri' in integration:
                            try:
                                lambda_arn = self._extract_lambda_arn_from_uri(
                                    uri=integration['IntegrationUri'],
                                    api_type='HTTP'
                                )
                                lambda_region = self._extract_region_from_arn(lambda_arn)
                                if lambda_arn:
                                    lambda_info = self.get_lambda_info(lambda_arn, lambda_region)
                                    
                                    if lambda_info:
                                        resource_info.update({
                                            'lambda_arn': lambda_arn,
                                            'lambda_name': lambda_info['name'],
                                            'lambda_exists': lambda_info['exists'],
                                            'lambda_subnet_ids': lambda_info['subnet_ids']
                                        })
                            except Exception as e:
                                print(f"Warning: Error processing Lambda integration for route {route['RouteKey']}: {e}")
                    except apigateway_v2_client.exceptions.NotFoundException:
                        print(f"Warning: No integration found for route {route['RouteKey']}")
                    except Exception as e:
                        print(f"Warning: Could not get integration for route {route['RouteKey']}: {e}")

                api_info['resources'].append(resource_info)

            apis_info[api_id] = api_info
        except Exception as e:
            print(f"Error processing V2 API {api_id}: {e}")

        return apis_info