# CLI to API Migration Inventory

This document provides a complete inventory of CLI commands, their current data sources, and the corresponding API endpoints needed for migration.

## Current Architecture

### CLI Data Flow (Current - Direct Access)

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI Commands                              │
│  services | infra | k8s | pipelines | diagram               │
└───────────────────────────┬─────────────────────────────────┘
                            │ Direct calls
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐      ┌──────────────┐    ┌─────────────┐
   │ boto3   │      │ kubernetes   │    │  diagrams   │
   │ ECS/EKS │      │ Python API   │    │   library   │
   │ RDS/ALB │      │              │    │             │
   └─────────┘      └──────────────┘    └─────────────┘
```

### Target Architecture (API-First)

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI Commands                              │
│  services | infra | k8s | pipelines | diagram               │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP via api_client.py
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 Dashborion API Gateway                       │
│  /api/{project}/services | infrastructure | events | ...    │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐      ┌──────────────┐    ┌─────────────┐
   │Provider │      │  Provider    │    │  Provider   │
   │ECS/EKS  │      │Infrastructure│    │  Diagram    │
   └─────────┘      └──────────────┘    └─────────────┘
```

---

## CLI Commands Inventory

### 1. Services Commands (`cli/dashborion/commands/services.py`)

| CLI Command | Current Collector | API Endpoint | Status |
|-------------|------------------|--------------|--------|
| `services list -e ENV` | `ECSCollector.list_services()` / `EKSCollector.list_services()` | `GET /api/{project}/services/{env}` | **Exists** |
| `services describe SERVICE -e ENV` | `ECSCollector.describe_service()` / `EKSCollector.describe_service()` | `GET /api/{project}/services/{env}/{service}` | **Exists** |
| `services tasks SERVICE -e ENV` | `ECSCollector.list_tasks()` / `EKSCollector.list_pods()` | `GET /api/{project}/tasks/{env}/{service}` | Partial |
| `services logs SERVICE -e ENV` | `ECSCollector.stream_logs()` / `EKSCollector.stream_logs()` | `GET /api/{project}/logs/{env}/{service}` | **Exists** |
| `services deploy SERVICE -e ENV` | `ECSCollector.force_deploy()` / `EKSCollector.restart_deployment()` | `POST /api/{project}/actions/deploy/{env}/{service}/reload` | **Exists** |

**Current Collectors Used:**
- `cli/dashborion/collectors/ecs.py` - Direct boto3 ECS calls
- `cli/dashborion/collectors/eks.py` - Direct boto3 EKS + K8s API calls

---

### 2. Infrastructure Commands (`cli/dashborion/commands/infra.py`)

| CLI Command | Current Collector | API Endpoint | Status |
|-------------|------------------|--------------|--------|
| `infra show -e ENV` | `InfrastructureCollector.get_*()` | `GET /api/{project}/infrastructure/{env}` | **Exists** |
| `infra alb -e ENV` | `InfrastructureCollector.get_load_balancers()` | `GET /api/{project}/infrastructure/{env}/alb` | Partial |
| `infra rds -e ENV` | `InfrastructureCollector.get_databases()` | `GET /api/{project}/infrastructure/{env}/rds` | Partial |
| `infra redis -e ENV` | `InfrastructureCollector.get_caches()` | `GET /api/{project}/infrastructure/{env}/redis` | Partial |
| `infra cloudfront -e ENV` | `InfrastructureCollector.get_cloudfront_distributions()` | `GET /api/{project}/infrastructure/{env}/cloudfront` | Partial |
| `infra network -e ENV` | `InfrastructureCollector.get_network_topology()` | `GET /api/{project}/infrastructure/{env}/routing` | **Exists** |
| `infra security-groups -e ENV` | `InfrastructureCollector.get_security_groups()` | `GET /api/{project}/infrastructure/{env}/security-group/{sg_id}` | **Exists** |

**Current Collector Used:**
- `cli/dashborion/collectors/infrastructure.py` - Direct boto3 calls (ELBv2, RDS, ElastiCache, CloudFront, EC2)

---

### 3. Kubernetes Commands (`cli/dashborion/commands/k8s.py`)

| CLI Command | Current Collector | API Endpoint | Status |
|-------------|------------------|--------------|--------|
| `k8s pods -c CONTEXT -n NS` | `KubernetesCollector.get_pods()` | `GET /api/{project}/k8s/{env}/pods` | **Missing** |
| `k8s services -c CONTEXT -n NS` | `KubernetesCollector.get_services()` | `GET /api/{project}/k8s/{env}/services` | **Missing** |
| `k8s deployments -c CONTEXT -n NS` | `KubernetesCollector.get_deployments()` | `GET /api/{project}/k8s/{env}/deployments` | **Missing** |
| `k8s ingresses -c CONTEXT -n NS` | `KubernetesCollector.get_ingresses()` | `GET /api/{project}/k8s/{env}/ingresses` | **Missing** |
| `k8s nodes -c CONTEXT` | `KubernetesCollector.get_nodes()` | `GET /api/{project}/k8s/{env}/nodes` | **Missing** |
| `k8s logs POD -c CONTEXT -n NS` | `KubernetesCollector.stream_logs()` | `GET /api/{project}/k8s/{env}/logs/{pod}` | **Missing** |
| `k8s describe TYPE NAME -c CONTEXT` | `KubernetesCollector.describe()` | `GET /api/{project}/k8s/{env}/{type}/{name}` | **Missing** |

**Current Collector Used:**
- `cli/dashborion/collectors/k8s_cli.py` - Direct kubernetes Python client

**Note:** K8s commands use direct `--context` parameter instead of environment mapping. API needs to resolve context from project/env config.

---

### 4. Pipelines Commands (`cli/dashborion/commands/pipelines.py`)

| CLI Command | Current Collector | API Endpoint | Status |
|-------------|------------------|--------------|--------|
| `pipelines list` | `CodePipelineCollector.list_pipelines()` | `GET /api/{project}/pipelines/list` | **Missing** |
| `pipelines status PIPELINE` | `CodePipelineCollector.get_pipeline_status()` | `GET /api/{project}/pipelines/{type}/{service}` | **Exists** |
| `pipelines logs PIPELINE` | `CodePipelineCollector.stream_logs()` | `GET /api/{project}/pipelines/{type}/{service}/logs` | **Missing** |
| `pipelines trigger PIPELINE` | `CodePipelineCollector.start_execution()` | `POST /api/{project}/actions/build/{service}` | **Exists** |
| `pipelines images SERVICE` | `ECRCollector.list_images()` | `GET /api/{project}/images/{service}` | **Exists** |

**Current Collectors Used:**
- `cli/dashborion/collectors/codepipeline.py` - Direct boto3 CodePipeline
- `cli/dashborion/collectors/argocd.py` - Direct ArgoCD API
- `cli/dashborion/collectors/jenkins.py` - Direct Jenkins API
- `cli/dashborion/collectors/ecr.py` - Direct boto3 ECR

---

### 5. Diagram Commands (`cli/dashborion/commands/diagram.py`)

| CLI Command | Current Collector | API Endpoint | Status |
|-------------|------------------|--------------|--------|
| `diagram generate -e ENV` | `DiagramGenerator` + collectors | `POST /api/{project}/diagram/{env}/generate` | **Missing** |
| `diagram generate -c CONFIG.yaml` | `generate_diagrams_from_yaml()` | `POST /api/{project}/diagram/generate` | **Missing** |
| `diagram publish -f FILE` | `ConfluencePublisher.publish_diagram()` | `POST /api/{project}/diagram/publish` | **Missing** |
| `diagram list-templates` | Static list | `GET /api/diagram/templates` | **Missing** |

**Current Dependencies:**
- `cli/dashborion/generators/diagram.py` - Uses `diagrams` library
- `cli/dashborion/publishers/confluence.py` - Direct Confluence API

---

## Backend API Endpoints (Current)

### Existing Routes in `backend/handler.py`

| Route | Method | Description | Provider |
|-------|--------|-------------|----------|
| `/api/health` | GET | Health check | - |
| `/api/config` | GET | Dashboard configuration | - |
| `/api/{project}/services` | GET | List all environments | OrchestratorProvider |
| `/api/{project}/services/{env}` | GET | List services in env | OrchestratorProvider |
| `/api/{project}/services/{env}/{service}` | GET | Service details | OrchestratorProvider |
| `/api/{project}/details/{env}/{service}` | GET | Extended service details | OrchestratorProvider |
| `/api/{project}/pipelines/{type}/{service}/{env?}` | GET | Pipeline info | CIProvider |
| `/api/{project}/images/{service}` | GET | ECR images | CIProvider |
| `/api/{project}/metrics/{env}/{service}` | GET | Service metrics | OrchestratorProvider |
| `/api/{project}/infrastructure/{env}` | GET | Infrastructure overview | InfrastructureAggregator |
| `/api/{project}/infrastructure/{env}/routing` | GET | Network routing | InfrastructureAggregator |
| `/api/{project}/infrastructure/{env}/enis` | GET | ENI details | InfrastructureAggregator |
| `/api/{project}/infrastructure/{env}/security-group/{sg_id}` | GET | Security group rules | InfrastructureAggregator |
| `/api/{project}/tasks/{env}/{service}/{task_id}` | GET | Task details | OrchestratorProvider |
| `/api/{project}/logs/{env}/{service}` | GET | Service logs | OrchestratorProvider |
| `/api/{project}/events/{env}` | GET | Events timeline | EventsProvider |
| `/api/{project}/actions/build/{service}` | POST | Trigger build | CIProvider |
| `/api/{project}/actions/deploy/{env}/{service}/{action}` | POST | Deploy/restart/scale | OrchestratorProvider |
| `/api/{project}/actions/rds/{env}/{action}` | POST | RDS start/stop | DatabaseProvider |
| `/api/{project}/actions/cloudfront/{env}/invalidate` | POST | Invalidate cache | CDNProvider |

---

## Missing API Endpoints

### Required for Full CLI Coverage

| Endpoint | Method | Purpose | Priority |
|----------|--------|---------|----------|
| `/api/{project}/k8s/{env}/pods` | GET | List K8s pods | High |
| `/api/{project}/k8s/{env}/services` | GET | List K8s services | High |
| `/api/{project}/k8s/{env}/deployments` | GET | List K8s deployments | High |
| `/api/{project}/k8s/{env}/ingresses` | GET | List K8s ingresses | High |
| `/api/{project}/k8s/{env}/nodes` | GET | List K8s nodes | High |
| `/api/{project}/k8s/{env}/logs/{pod}` | GET | Pod logs | Medium |
| `/api/{project}/k8s/{env}/{type}/{name}` | GET | Describe resource | Medium |
| `/api/{project}/pipelines/list` | GET | List all pipelines | Medium |
| `/api/{project}/pipelines/{name}/logs` | GET | Pipeline logs | Low |
| `/api/{project}/diagram/{env}/generate` | POST | Generate diagram | Medium |
| `/api/{project}/diagram/publish` | POST | Publish to Confluence | Low |
| `/api/diagram/templates` | GET | List diagram templates | Low |

---

## Current Collectors to Remove

After migration, these direct collectors will be replaced by API calls:

| Collector | File | Replacement |
|-----------|------|-------------|
| ECSCollector | `collectors/ecs.py` | API `/services/*` |
| EKSCollector | `collectors/eks.py` | API `/services/*` + `/k8s/*` |
| KubernetesCollector | `collectors/k8s_cli.py` | API `/k8s/*` |
| InfrastructureCollector | `collectors/infrastructure.py` | API `/infrastructure/*` |
| CodePipelineCollector | `collectors/codepipeline.py` | API `/pipelines/*` |
| ArgoCDCollector | `collectors/argocd.py` | API `/pipelines/*` |
| JenkinsCollector | `collectors/jenkins.py` | API `/pipelines/*` |
| ECRCollector | `collectors/ecr.py` | API `/images/*` |
| DiagramGenerator | `generators/diagram.py` | API `/diagram/*` |

---

## API Client (`utils/api_client.py`)

The API client already exists and supports:
- Bearer token authentication (device flow)
- AWS SigV4 identity proof authentication

**Current usage:** Only for auth endpoints.
**Target usage:** All CLI data operations.

```python
from dashborion.utils.api_client import get_api_client

client = get_api_client()

# Current (auth only)
response = client.get('/api/auth/whoami')

# Target (all operations)
response = client.get('/api/myproject/services/staging')
response = client.get('/api/myproject/infrastructure/production')
response = client.post('/api/myproject/actions/deploy/staging/backend/reload')
```

---

## Migration Steps

### Phase 1: Add Missing API Endpoints

1. Add K8s resource endpoints in `handler.py`
2. Add pipeline list endpoint
3. Add diagram generation endpoints

### Phase 2: Create API-Based Collector

Create a single unified collector that uses the API:

```python
# cli/dashborion/collectors/api.py

class APICollector:
    """Unified collector using Dashborion API."""

    def __init__(self, client: APIClient, project: str):
        self.client = client
        self.project = project

    def list_services(self, env: str) -> List[dict]:
        response = self.client.get(f'/api/{self.project}/services/{env}')
        response.raise_for_status()
        return response.json().get('services', {})

    def get_infrastructure(self, env: str) -> dict:
        response = self.client.get(f'/api/{self.project}/infrastructure/{env}')
        response.raise_for_status()
        return response.json()

    def get_pods(self, env: str, namespace: str = None) -> List[dict]:
        params = {'namespace': namespace} if namespace else {}
        response = self.client.get(f'/api/{self.project}/k8s/{env}/pods', params=params)
        response.raise_for_status()
        return response.json().get('pods', [])

    # ... etc for all operations
```

### Phase 3: Update CLI Commands

Replace collector imports with API collector:

```python
# Before
from dashborion.collectors.ecs import ECSCollector
collector = ECSCollector(session)
services = collector.list_services(cluster)

# After
from dashborion.collectors.api import APICollector
from dashborion.utils.api_client import get_api_client
collector = APICollector(get_api_client(), project)
services = collector.list_services(env)
```

### Phase 4: Remove Direct Collectors

Delete the following files after migration:
- `collectors/ecs.py`
- `collectors/eks.py`
- `collectors/k8s_cli.py`
- `collectors/infrastructure.py`
- `collectors/codepipeline.py`
- `collectors/argocd.py`
- `collectors/jenkins.py`
- `collectors/ecr.py`

Keep:
- `collectors/api.py` (new unified collector)
- `collectors/aws.py` (AWS specs only - can be moved to backend)
- `collectors/kubernetes.py` (if needed for diagram generation)

---

## rubix-diagrams Integration

### Components to Merge from `~/work/akiros/nbs/rubix-diagrams`

| Component | Source | Target | Notes |
|-----------|--------|--------|-------|
| `KubernetesInfoCollector` | `rubix_diagram/collectors/kubernetes.py` | Backend provider | Move to backend |
| `AWSResourceCollector` | `rubix_diagram/collectors/aws.py` | Backend provider | Move to backend |
| `DiagramGenerator` | `rubix_diagram/generators/diagram.py` | Backend provider | Move to backend |
| `ConfluencePublisher` | `rubix_diagram/publishers/confluence.py` | Backend provider | Move to backend |

### New Backend Provider Structure

```
backend/providers/diagram/
├── __init__.py
├── generator.py        # Diagram generation using diagrams library
├── publisher.py        # Confluence publishing
└── templates/          # Diagram templates (agnostic)
    ├── multi-tier.py
    ├── serverless.py
    └── kubernetes.py
```

### Configuration Changes

Replace hardcoded Rubix structure with configurable templates:

```yaml
# config.yaml
diagram:
  templates:
    multi-tier:
      accounts:
        - name: "shared-infra"
          role: "entry-point"
        - name: "workload"
          role: "compute"
      layers:
        - cloudfront
        - alb
        - compute
        - database
```

---

## Migration Status (Completed 2026-01-11)

All CLI commands have been migrated to use the Dashborion API instead of direct AWS/K8s calls.

### Completed Tasks

1. **API Collector Created** (`cli/dashborion/collectors/api.py`)
   - Unified collector class for all API operations
   - Methods for services, k8s, infrastructure, pipelines, diagrams

2. **K8s API Endpoints Added** (`backend/handler.py`)
   - `GET /api/{project}/k8s/{env}/pods`
   - `GET /api/{project}/k8s/{env}/services`
   - `GET /api/{project}/k8s/{env}/deployments`
   - `GET /api/{project}/k8s/{env}/ingresses`
   - `GET /api/{project}/k8s/{env}/nodes`
   - `GET /api/{project}/k8s/{env}/namespaces`
   - `GET /api/{project}/k8s/{env}/logs/{pod}`
   - `GET /api/{project}/k8s/{env}/{type}/{name}`

3. **Diagram API Endpoints Added** (`backend/handler.py`)
   - `GET /api/{project}/diagram/templates`
   - `POST /api/{project}/diagram/generate`
   - `POST /api/{project}/diagram/publish`

4. **CLI Commands Migrated**
   - `services.py` - Using APICollector
   - `infra.py` - Using APICollector
   - `k8s.py` - Using APICollector (--context deprecated, use --env)
   - `pipelines.py` - Using APICollector
   - `diagram.py` - Using APICollector

5. **EKS Provider Enhanced** (`backend/providers/orchestrator/eks.py`)
   - Added get_pods(), get_deployments(), get_pod_logs(), describe_k8s_resource()

### Files Modified

| File | Changes |
|------|---------|
| `cli/dashborion/collectors/api.py` | Created - Unified API collector |
| `cli/dashborion/commands/services.py` | Migrated to API |
| `cli/dashborion/commands/infra.py` | Migrated to API |
| `cli/dashborion/commands/k8s.py` | Migrated to API |
| `cli/dashborion/commands/pipelines.py` | Migrated to API |
| `cli/dashborion/commands/diagram.py` | Migrated to API |
| `backend/handler.py` | Added K8s and diagram endpoints |
| `backend/providers/orchestrator/eks.py` | Added K8s methods |
| `backend/providers/base.py` | Added K8sPod, K8sDeployment dataclasses |

### Summary

| Category | Commands | Status |
|----------|----------|--------|
| Services | 8 | ✅ Migrated |
| Infrastructure | 10 | ✅ Migrated |
| Kubernetes | 8 | ✅ Migrated |
| Pipelines | 5 | ✅ Migrated |
| Diagram | 3 | ✅ Migrated |
| **Total** | **34** | **All Complete** |

### Next Steps (Optional)

1. Remove deprecated direct collectors (ecs.py, eks.py, k8s_cli.py, etc.)
2. Add more diagram templates
3. Integrate rubix-diagrams diagram generators into backend
