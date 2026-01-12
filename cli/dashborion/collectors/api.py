"""
Unified API Collector for Dashborion CLI

All data operations go through the Dashborion API instead of direct AWS/K8s calls.
This ensures consistent behavior between CLI and Web interfaces.

Usage:
    from dashborion.collectors.api import APICollector
    from dashborion.utils.api_client import get_api_client

    collector = APICollector(get_api_client(), project='myproject')
    services = collector.list_services('staging')
"""

from typing import Dict, List, Optional, Any
from dashborion.utils.api_client import APIClient


class APICollectorError(Exception):
    """Raised when API collector encounters an error."""
    pass


class APICollector:
    """
    Unified collector that fetches all data via Dashborion API.

    Replaces direct collectors:
    - ECSCollector
    - EKSCollector
    - KubernetesCollector
    - InfrastructureCollector
    - CodePipelineCollector
    - ECRCollector
    """

    def __init__(self, client: APIClient, project: str):
        """
        Initialize API collector.

        Args:
            client: Configured APIClient instance
            project: Project name for API routes
        """
        self.client = client
        self.project = project

    def _handle_response(self, response, error_context: str = "API call") -> dict:
        """Handle API response and raise errors if needed."""
        try:
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and 'error' in data:
                raise APICollectorError(f"{error_context}: {data['error']}")
            return data
        except Exception as e:
            if hasattr(response, 'text'):
                raise APICollectorError(f"{error_context} failed: {response.status_code} - {response.text}")
            raise APICollectorError(f"{error_context} failed: {e}")

    # =========================================================================
    # SERVICES OPERATIONS
    # =========================================================================

    def list_services(self, env: str) -> Dict[str, dict]:
        """
        List all services in an environment.

        Args:
            env: Environment name (staging, production, etc.)

        Returns:
            Dict mapping service names to service summary data
        """
        response = self.client.get(f'/api/{self.project}/services/{env}')
        data = self._handle_response(response, f"list services in {env}")
        return data.get('services', {})

    def describe_service(self, env: str, service: str) -> dict:
        """
        Get detailed information about a service.

        Args:
            env: Environment name
            service: Service name

        Returns:
            Service details dict
        """
        response = self.client.get(f'/api/{self.project}/services/{env}/{service}')
        return self._handle_response(response, f"describe service {service}")

    def get_service_details(self, env: str, service: str) -> dict:
        """
        Get extended service details (env vars, secrets, logs).

        Args:
            env: Environment name
            service: Service name

        Returns:
            Extended service details dict
        """
        response = self.client.get(f'/api/{self.project}/details/{env}/{service}')
        return self._handle_response(response, f"get details for {service}")

    def get_service_logs(self, env: str, service: str, tail: int = 100) -> List[dict]:
        """
        Get recent logs for a service.

        Args:
            env: Environment name
            service: Service name
            tail: Number of log lines

        Returns:
            List of log entries
        """
        response = self.client.get(
            f'/api/{self.project}/logs/{env}/{service}',
            params={'tail': tail}
        )
        data = self._handle_response(response, f"get logs for {service}")
        return data.get('logs', [])

    def get_task_details(self, env: str, service: str, task_id: str) -> dict:
        """
        Get details for a specific task/pod.

        Args:
            env: Environment name
            service: Service name
            task_id: Task or pod ID

        Returns:
            Task details dict
        """
        response = self.client.get(f'/api/{self.project}/tasks/{env}/{service}/{task_id}')
        return self._handle_response(response, f"get task {task_id}")

    def get_metrics(self, env: str, service: str) -> dict:
        """
        Get metrics for a service.

        Args:
            env: Environment name
            service: Service name

        Returns:
            Metrics dict
        """
        response = self.client.get(f'/api/{self.project}/metrics/{env}/{service}')
        return self._handle_response(response, f"get metrics for {service}")

    # =========================================================================
    # KUBERNETES OPERATIONS
    # =========================================================================

    def get_pods(self, env: str, namespace: Optional[str] = None,
                 selector: Optional[str] = None) -> List[dict]:
        """
        List Kubernetes pods.

        Args:
            env: Environment name
            namespace: Optional namespace filter (None for all)
            selector: Optional label selector

        Returns:
            List of pod dicts
        """
        params = {}
        if namespace:
            params['namespace'] = namespace
        if selector:
            params['selector'] = selector

        response = self.client.get(f'/api/{self.project}/k8s/{env}/pods', params=params)
        data = self._handle_response(response, f"list pods in {env}")
        return data.get('pods', [])

    def get_k8s_services(self, env: str, namespace: Optional[str] = None) -> List[dict]:
        """
        List Kubernetes services.

        Args:
            env: Environment name
            namespace: Optional namespace filter

        Returns:
            List of service dicts
        """
        params = {'namespace': namespace} if namespace else {}
        response = self.client.get(f'/api/{self.project}/k8s/{env}/services', params=params)
        data = self._handle_response(response, f"list k8s services in {env}")
        return data.get('services', [])

    def get_deployments(self, env: str, namespace: Optional[str] = None) -> List[dict]:
        """
        List Kubernetes deployments.

        Args:
            env: Environment name
            namespace: Optional namespace filter

        Returns:
            List of deployment dicts
        """
        params = {'namespace': namespace} if namespace else {}
        response = self.client.get(f'/api/{self.project}/k8s/{env}/deployments', params=params)
        data = self._handle_response(response, f"list deployments in {env}")
        return data.get('deployments', [])

    def get_ingresses(self, env: str, namespace: Optional[str] = None) -> List[dict]:
        """
        List Kubernetes ingresses.

        Args:
            env: Environment name
            namespace: Optional namespace filter

        Returns:
            List of ingress dicts
        """
        params = {'namespace': namespace} if namespace else {}
        response = self.client.get(f'/api/{self.project}/k8s/{env}/ingresses', params=params)
        data = self._handle_response(response, f"list ingresses in {env}")
        return data.get('ingresses', [])

    def get_nodes(self, env: str) -> List[dict]:
        """
        List Kubernetes nodes.

        Args:
            env: Environment name

        Returns:
            List of node dicts
        """
        response = self.client.get(f'/api/{self.project}/k8s/{env}/nodes')
        data = self._handle_response(response, f"list nodes in {env}")
        return data.get('nodes', [])

    def get_pod_logs(self, env: str, pod: str, namespace: str = 'default',
                     container: Optional[str] = None, tail: int = 100,
                     since: Optional[str] = None) -> str:
        """
        Get logs from a specific pod.

        Args:
            env: Environment name
            pod: Pod name
            namespace: Namespace
            container: Optional container name
            tail: Number of lines
            since: Duration string (e.g., '1h', '30m')

        Returns:
            Log content as string
        """
        params = {
            'namespace': namespace,
            'tail': tail
        }
        if container:
            params['container'] = container
        if since:
            params['since'] = since

        response = self.client.get(f'/api/{self.project}/k8s/{env}/logs/{pod}', params=params)
        data = self._handle_response(response, f"get logs for pod {pod}")
        return data.get('logs', '')

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
        params = {'namespace': namespace}
        response = self.client.get(
            f'/api/{self.project}/k8s/{env}/{resource_type}/{name}',
            params=params
        )
        return self._handle_response(response, f"describe {resource_type} {name}")

    # =========================================================================
    # INFRASTRUCTURE OPERATIONS
    # =========================================================================

    def get_infrastructure(self, env: str, discovery_tags: Optional[dict] = None,
                          services: Optional[List[str]] = None,
                          databases: Optional[List[str]] = None,
                          caches: Optional[List[str]] = None) -> dict:
        """
        Get infrastructure overview for an environment.

        Args:
            env: Environment name
            discovery_tags: Optional tags for resource discovery
            services: Optional list of service names to filter
            databases: Optional list of database identifiers
            caches: Optional list of cache cluster IDs

        Returns:
            Infrastructure overview dict
        """
        import json
        params = {}
        if discovery_tags:
            params['discoveryTags'] = json.dumps(discovery_tags)
        if services:
            params['services'] = ','.join(services)
        if databases:
            params['databases'] = ','.join(databases)
        if caches:
            params['caches'] = ','.join(caches)

        response = self.client.get(f'/api/{self.project}/infrastructure/{env}', params=params)
        return self._handle_response(response, f"get infrastructure for {env}")

    def get_load_balancers(self, env: str, name_filter: Optional[str] = None) -> List[dict]:
        """
        Get Application Load Balancers.

        Args:
            env: Environment name
            name_filter: Optional name filter

        Returns:
            List of ALB dicts
        """
        infra = self.get_infrastructure(env)
        albs = infra.get('loadBalancers', [])
        if name_filter:
            albs = [alb for alb in albs if name_filter in alb.get('name', '')]
        return albs

    def get_databases(self, env: str, identifier_filter: Optional[str] = None) -> List[dict]:
        """
        Get RDS databases.

        Args:
            env: Environment name
            identifier_filter: Optional identifier filter

        Returns:
            List of database dicts
        """
        infra = self.get_infrastructure(env)
        dbs = infra.get('databases', [])
        if identifier_filter:
            dbs = [db for db in dbs if identifier_filter in db.get('identifier', '')]
        return dbs

    def get_caches(self, env: str) -> List[dict]:
        """
        Get ElastiCache clusters.

        Args:
            env: Environment name

        Returns:
            List of cache dicts
        """
        infra = self.get_infrastructure(env)
        return infra.get('caches', [])

    def get_cloudfront_distributions(self, env: str,
                                     distribution_id: Optional[str] = None) -> List[dict]:
        """
        Get CloudFront distributions.

        Args:
            env: Environment name
            distribution_id: Optional distribution ID filter

        Returns:
            List of distribution dicts
        """
        infra = self.get_infrastructure(env)
        distributions = infra.get('distributions', [])
        if distribution_id:
            distributions = [d for d in distributions if d.get('id') == distribution_id]
        return distributions

    def get_vpcs(self, env: str) -> List[dict]:
        """
        Get VPCs.

        Args:
            env: Environment name

        Returns:
            List of VPC dicts
        """
        infra = self.get_infrastructure(env)
        return infra.get('vpcs', [])

    def get_routing_details(self, env: str,
                           security_groups: Optional[List[str]] = None) -> dict:
        """
        Get network routing details.

        Args:
            env: Environment name
            security_groups: Optional security group IDs to include

        Returns:
            Routing details dict
        """
        params = {}
        if security_groups:
            params['securityGroups'] = ','.join(security_groups)

        response = self.client.get(
            f'/api/{self.project}/infrastructure/{env}/routing',
            params=params
        )
        return self._handle_response(response, f"get routing for {env}")

    def get_security_group(self, env: str, sg_id: str) -> dict:
        """
        Get security group rules.

        Args:
            env: Environment name
            sg_id: Security group ID

        Returns:
            Security group details dict
        """
        response = self.client.get(
            f'/api/{self.project}/infrastructure/{env}/security-group/{sg_id}'
        )
        return self._handle_response(response, f"get security group {sg_id}")

    def get_enis(self, env: str, vpc_id: Optional[str] = None,
                 subnet_id: Optional[str] = None,
                 search_ip: Optional[str] = None) -> List[dict]:
        """
        Get ENI details.

        Args:
            env: Environment name
            vpc_id: Optional VPC ID filter
            subnet_id: Optional subnet ID filter
            search_ip: Optional IP to search for

        Returns:
            List of ENI dicts
        """
        params = {}
        if vpc_id:
            params['vpcId'] = vpc_id
        if subnet_id:
            params['subnetId'] = subnet_id
        if search_ip:
            params['searchIp'] = search_ip

        response = self.client.get(
            f'/api/{self.project}/infrastructure/{env}/enis',
            params=params
        )
        data = self._handle_response(response, f"get ENIs for {env}")
        return data.get('enis', [])

    # =========================================================================
    # PIPELINE OPERATIONS
    # =========================================================================

    def list_pipelines(self, env: Optional[str] = None,
                      provider: Optional[str] = None,
                      pipeline_type: Optional[str] = None,
                      prefix: Optional[str] = None) -> List[dict]:
        """
        List CI/CD pipelines.

        Args:
            env: Optional environment name
            provider: CI/CD provider (codepipeline, argocd, jenkins, etc.)
            pipeline_type: Optional type filter (build, deploy)
            prefix: Optional pipeline name prefix

        Returns:
            List of pipeline dicts
        """
        params = {}
        if prefix:
            params['prefix'] = prefix
        if pipeline_type:
            params['type'] = pipeline_type
        if provider:
            params['provider'] = provider
        if env:
            params['env'] = env

        response = self.client.get(f'/api/{self.project}/pipelines/list', params=params)
        data = self._handle_response(response, "list pipelines")
        return data.get('pipelines', [])

    def get_pipeline(self, pipeline_type: str, service: str,
                    env: Optional[str] = None) -> dict:
        """
        Get pipeline details.

        Args:
            pipeline_type: Pipeline type (build, deploy)
            service: Service name
            env: Environment (required for deploy pipelines)

        Returns:
            Pipeline details dict
        """
        path = f'/api/{self.project}/pipelines/{pipeline_type}/{service}'
        if env:
            path += f'/{env}'

        response = self.client.get(path)
        return self._handle_response(response, f"get pipeline for {service}")

    def get_pipeline_status(self, env: Optional[str], pipeline_name: str,
                           provider: Optional[str] = None) -> dict:
        """
        Get pipeline status and history.

        Args:
            env: Optional environment name
            pipeline_name: Pipeline name
            provider: CI/CD provider

        Returns:
            Pipeline status dict
        """
        params = {}
        if provider:
            params['provider'] = provider
        if env:
            params['env'] = env

        response = self.client.get(
            f'/api/{self.project}/pipelines/status/{pipeline_name}',
            params=params
        )
        return self._handle_response(response, f"get pipeline status for {pipeline_name}")

    def get_pipeline_logs(self, env: Optional[str], pipeline_name: str,
                         execution_id: Optional[str] = None,
                         tail: int = 100) -> Any:
        """
        Get pipeline execution logs.

        Args:
            env: Optional environment name
            pipeline_name: Pipeline name
            execution_id: Optional execution ID
            tail: Number of log lines

        Returns:
            Logs (string, list, or dict)
        """
        params = {'tail': tail}
        if execution_id:
            params['executionId'] = execution_id
        if env:
            params['env'] = env

        response = self.client.get(
            f'/api/{self.project}/pipelines/logs/{pipeline_name}',
            params=params
        )
        return self._handle_response(response, f"get logs for pipeline {pipeline_name}")

    def trigger_pipeline(self, env: Optional[str], pipeline_name: str,
                        provider: Optional[str] = None,
                        wait: bool = False) -> dict:
        """
        Trigger a pipeline execution.

        Args:
            env: Optional environment name
            pipeline_name: Pipeline name
            provider: CI/CD provider
            wait: Wait for completion

        Returns:
            Trigger result dict
        """
        body = {'wait': wait}
        if provider:
            body['provider'] = provider
        if env:
            body['env'] = env

        response = self.client.post(
            f'/api/{self.project}/pipelines/trigger/{pipeline_name}',
            json_data=body
        )
        return self._handle_response(response, f"trigger pipeline {pipeline_name}")

    def get_images(self, service: str, limit: int = 10) -> List[dict]:
        """
        Get ECR images for a service.

        Args:
            service: Service name
            limit: Max images to return

        Returns:
            List of image dicts
        """
        response = self.client.get(
            f'/api/{self.project}/images/{service}',
            params={'limit': limit}
        )
        data = self._handle_response(response, f"get images for {service}")
        return data.get('images', [])

    def list_ecr_images(self, env: Optional[str], service: str,
                       limit: int = 10) -> List[dict]:
        """
        List ECR images for a service.

        Args:
            env: Optional environment name (for filtering)
            service: Service name
            limit: Max images to return

        Returns:
            List of image dicts
        """
        params = {'limit': limit}
        if env:
            params['env'] = env

        response = self.client.get(
            f'/api/{self.project}/images/{service}',
            params=params
        )
        data = self._handle_response(response, f"list images for {service}")
        return data.get('images', [])

    # =========================================================================
    # EVENTS OPERATIONS
    # =========================================================================

    def get_events(self, env: str, hours: int = 24,
                  event_types: Optional[List[str]] = None,
                  services: Optional[List[str]] = None) -> dict:
        """
        Get events timeline.

        Args:
            env: Environment name
            hours: Hours to look back (1-168)
            event_types: Optional event type filter
            services: Optional services filter

        Returns:
            Events dict
        """
        params = {'hours': min(max(hours, 1), 168)}
        if event_types:
            params['types'] = ','.join(event_types)
        if services:
            params['services'] = ','.join(services)

        response = self.client.get(f'/api/{self.project}/events/{env}', params=params)
        return self._handle_response(response, f"get events for {env}")

    # =========================================================================
    # ACTION OPERATIONS
    # =========================================================================

    def deploy_service(self, env: str, service: str, action: str = 'reload',
                      image_tag: Optional[str] = None) -> dict:
        """
        Deploy or restart a service.

        Args:
            env: Environment name
            service: Service name
            action: Action type (reload, latest, stop, start)
            image_tag: Optional image tag for 'latest' action

        Returns:
            Action result dict
        """
        body = {}
        if image_tag:
            body['imageTag'] = image_tag

        response = self.client.post(
            f'/api/{self.project}/actions/deploy/{env}/{service}/{action}',
            json_data=body
        )
        return self._handle_response(response, f"{action} service {service}")

    def trigger_build(self, service: str, image_tag: str = 'latest',
                     source_revision: str = '') -> dict:
        """
        Trigger a build pipeline.

        Args:
            service: Service name
            image_tag: Image tag to use
            source_revision: Optional source revision

        Returns:
            Build trigger result dict
        """
        response = self.client.post(
            f'/api/{self.project}/actions/build/{service}',
            json_data={
                'imageTag': image_tag,
                'sourceRevision': source_revision
            }
        )
        return self._handle_response(response, f"trigger build for {service}")

    def scale_service(self, env: str, service: str, desired_count: int) -> dict:
        """
        Scale a service.

        Args:
            env: Environment name
            service: Service name
            desired_count: Desired replica count

        Returns:
            Scale result dict
        """
        action = 'start' if desired_count > 0 else 'stop'
        response = self.client.post(
            f'/api/{self.project}/actions/deploy/{env}/{service}/{action}',
            json_data={'desiredCount': desired_count}
        )
        return self._handle_response(response, f"scale service {service} to {desired_count}")

    def invalidate_cloudfront(self, env: str, distribution_id: str,
                             paths: List[str] = None) -> dict:
        """
        Invalidate CloudFront cache.

        Args:
            env: Environment name
            distribution_id: CloudFront distribution ID
            paths: Paths to invalidate (default: ['/*'])

        Returns:
            Invalidation result dict
        """
        response = self.client.post(
            f'/api/{self.project}/actions/cloudfront/{env}/invalidate',
            json_data={
                'distributionId': distribution_id,
                'paths': paths or ['/*']
            }
        )
        return self._handle_response(response, f"invalidate CloudFront {distribution_id}")

    def control_rds(self, env: str, action: str) -> dict:
        """
        Start or stop RDS database.

        Args:
            env: Environment name
            action: Action (start, stop)

        Returns:
            RDS control result dict
        """
        response = self.client.post(f'/api/{self.project}/actions/rds/{env}/{action}')
        return self._handle_response(response, f"{action} RDS in {env}")

    # =========================================================================
    # DIAGRAM OPERATIONS
    # =========================================================================

    def generate_diagram(self, env: str, output_format: str = 'png',
                        namespaces: Optional[List[str]] = None,
                        include_rds: bool = False,
                        include_elasticache: bool = False,
                        include_cloudfront: bool = False) -> dict:
        """
        Generate architecture diagram.

        Args:
            env: Environment name
            output_format: Output format (png, svg, pdf)
            namespaces: Kubernetes namespaces to include
            include_rds: Include RDS databases
            include_elasticache: Include ElastiCache clusters
            include_cloudfront: Include CloudFront distributions

        Returns:
            Dict with 'data' containing base64 encoded diagram
        """
        body = {
            'env': env,
            'outputFormat': output_format,
            'namespaces': namespaces or ['default'],
            'includeRds': include_rds,
            'includeElasticache': include_elasticache,
            'includeCloudfront': include_cloudfront
        }
        response = self.client.post(
            f'/api/{self.project}/diagram/generate',
            json_data=body
        )
        return self._handle_response(response, "generate diagram")

    def publish_diagram(self, diagram_data: str, file_format: str,
                       confluence_page: str, title: Optional[str] = None,
                       space: Optional[str] = None) -> dict:
        """
        Publish diagram to Confluence.

        Args:
            diagram_data: Base64 encoded diagram content
            file_format: File format (png, svg, pdf)
            confluence_page: Confluence page ID
            title: Optional page title
            space: Optional space key

        Returns:
            Publish result dict
        """
        response = self.client.post(
            f'/api/{self.project}/diagram/publish',
            json_data={
                'diagramData': diagram_data,
                'format': file_format,
                'confluencePage': confluence_page,
                'title': title,
                'space': space
            }
        )
        return self._handle_response(response, "publish diagram to Confluence")

    def list_diagram_templates(self) -> List[dict]:
        """
        List available diagram templates.

        Returns:
            List of template dicts
        """
        response = self.client.get(f'/api/{self.project}/diagram/templates')
        data = self._handle_response(response, "list diagram templates")
        return data.get('templates', [])
