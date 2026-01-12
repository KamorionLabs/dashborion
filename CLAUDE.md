# CLAUDE.md - Dashborion

## Project Overview

**Dashborion** is an open-source multi-cloud infrastructure dashboard with CLI for visualizing and managing ECS, EKS, and CI/CD pipelines.

- **License**: MIT
- **Languages**: Python (CLI/Backend), JavaScript/React (Frontend)
- **Cloud**: AWS (primary), extensible architecture
- **Compute**: ECS (Fargate & EC2), EKS/Kubernetes

---

## Architecture

```
dashborion/
├── frontend/              # React dashboard (Vite + Tailwind)
│   ├── src/
│   │   ├── components/    # UI components (services, infrastructure, pipelines)
│   │   ├── utils/         # API utilities, helpers
│   │   └── App.jsx        # Main application with routing
│   └── public/
│       └── config.json    # Runtime configuration
│
├── backend/               # Lambda API backend (Python)
│   ├── handler.py         # Lambda entry point, API routing
│   ├── config.py          # Configuration and discovery
│   ├── providers/         # Data providers
│   │   ├── ci/            # CI/CD: CodePipeline, ArgoCD, Jenkins, etc.
│   │   ├── infrastructure/# AWS resources: ECS, EKS, RDS, etc.
│   │   └── events/        # CloudTrail, ECS events
│   └── utils/             # Shared utilities
│
├── cli/                   # CLI tool (dashborion-cli)
│   └── dashborion/
│       ├── cli.py         # Click-based CLI entry point
│       ├── commands/      # CLI commands (services, infra, diagram, k8s)
│       ├── collectors/    # Data collectors (AWS, Kubernetes)
│       ├── generators/    # Diagram generators
│       └── publishers/    # Confluence publisher
│
├── terraform/             # Infrastructure as Code (Terraform modules)
│   └── modules/
│       ├── sst-deploy-role/      # SST/Pulumi deployment role
│       ├── sst-lambda-role/      # Lambda execution role
│       └── cross-account-roles/  # Cross-account access roles
│
├── sst.config.ts          # SST v3 configuration (3 deployment modes)
├── infra.config.json      # Deployment settings (mode, aws region/profile)
│
├── docs/                  # Documentation
└── examples/              # Example configurations
```

---

## Development Setup

### Frontend

```bash
cd frontend
npm install
npm run dev          # Development server (localhost:5173)
npm run build        # Production build
```

### Backend (Local)

```bash
cd backend
pip install -r requirements.txt
# Use SAM CLI for local testing
sam local start-api
```

### CLI

```bash
cd cli
pip install -e .     # Install in development mode
dashborion --help
```

---

## Key Components

### Frontend Components

| Component | Location | Description |
|-----------|----------|-------------|
| `CollapsibleSection` | `components/common/` | Reusable collapsible panel |
| `ServiceDetails` | `components/services/` | ECS/EKS service details |
| `PipelineDetails` | `components/pipelines/` | Build/deploy pipeline view |
| `ALBDetails` | `components/infrastructure/` | Load balancer details |
| `RDSDetails` | `components/infrastructure/` | Database details |
| `CloudFrontDetails` | `components/infrastructure/` | CDN distribution details |

### Backend Providers

| Provider | Location | Description |
|----------|----------|-------------|
| `ECSProvider` | `providers/infrastructure/` | ECS clusters, services, tasks |
| `EKSProvider` | `providers/infrastructure/` | EKS clusters, workloads |
| `CodePipelineProvider` | `providers/ci/` | AWS CodePipeline |
| `ArgoCDProvider` | `providers/ci/` | ArgoCD applications |
| `InfrastructureProvider` | `providers/infrastructure/` | ALB, RDS, ElastiCache, etc. |

### CLI Commands

| Command | Description |
|---------|-------------|
| `dashborion services list` | List services in an environment |
| `dashborion services describe <service>` | Service details |
| `dashborion infra show` | Infrastructure overview |
| `dashborion diagram generate` | Generate architecture diagram |
| `dashborion diagram publish` | Publish to Confluence |
| `dashborion k8s pods` | List Kubernetes pods |
| `dashborion k8s services` | List Kubernetes services |

---

## Authentication

### Web Dashboard (SAML SSO via API Gateway)

SAML SSO authentication is handled at the API Gateway level (not Lambda@Edge).

**Architecture**:
- CloudFront serves static frontend from S3 (no Lambda@Edge)
- API Gateway handles SAML authentication endpoints
- Frontend calls API directly using `VITE_API_URL`

**SAML Endpoints** (on API Gateway):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/saml/login` | GET | Initiates SAML flow, redirects to IdP |
| `/api/auth/saml/acs` | POST | Assertion Consumer Service, validates SAML response |
| `/api/auth/saml/metadata` | GET | SP metadata XML for IdP configuration |

**Configuration** (`infra.config.json`):
```json
{
  "auth": {
    "enabled": true,
    "provider": "saml",
    "saml": {
      "entityId": "dashborion-{stage}",
      "idpMetadataFile": "idp-metadata/dashboard.xml"
    },
    "sessionTtlSeconds": 3600
  }
}
```

**IdP Configuration** (AWS Identity Center, Entra ID, Okta, etc.):

| Parameter | Value |
|-----------|-------|
| ACS URL | `https://{api-domain}/api/auth/saml/acs` |
| SP Entity ID | `dashborion-{stage}` |
| SP Metadata URL | `https://{api-domain}/api/auth/saml/metadata` |

**AWS Identity Center attribute mappings** (critical for RBAC):
- `Subject` -> `${user:email}` (emailAddress format)
- `email` -> `${user:email}`
- `displayName` -> `${user:name}`
- `memberOf` -> `${user:groups}` (required for RBAC)

### CLI

Three authentication methods:

| Method | Command | Token Storage |
|--------|---------|---------------|
| Device Flow | `dashborion auth login` | Yes (`~/.dashborion/`) |
| SSO Exchange | `dashborion auth login --use-sso` | Yes |
| SigV4 (per-request) | `dashborion --sigv4 <cmd>` | No |

**Device Flow**: Opens browser for SSO authentication, stores token locally.

**SSO Exchange**: Exchanges AWS SSO session for Dashborion token.

**SigV4 (Vault-style STS Identity Proof)**: Signs each request with AWS credentials.
- Uses HashiCorp Vault's IAM auth technique
- Client signs GetCallerIdentity request, server forwards to STS
- Email extracted from Identity Center session name
- Works with HTTP API v2 + REQUEST authorizer

```bash
# Examples
dashborion auth login                    # Device flow
dashborion auth login --use-sso          # SSO exchange
dashborion --sigv4 auth whoami           # SigV4 per-request
AWS_PROFILE=my-profile dashborion --sigv4 services list
```

---

## Configuration

### Dashboard (`config.json`)

```json
{
  "projects": [
    {
      "id": "my-project",
      "name": "My Project",
      "environments": ["staging", "production"],
      "services": ["backend", "frontend"],
      "infrastructure": {
        "discoveryTags": {
          "Project": "my-project"
        }
      }
    }
  ]
}
```

### CLI (`~/.dashborion/config.yaml`)

```yaml
default_profile: myprofile
default_region: eu-west-3

environments:
  staging:
    type: ecs
    cluster: my-staging-cluster
    aws_profile: myprofile
    aws_region: eu-west-3

  production:
    type: ecs
    cluster: my-prod-cluster
    aws_profile: prod-profile

  eks-staging:
    type: eks
    context: arn:aws:eks:eu-west-3:123456789:cluster/my-eks
    namespaces:
      - staging
      - common
```

---

## API Endpoints

### Services

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/services/{env}` | GET | List services |
| `/api/services/{env}/{service}` | GET | Service details |
| `/api/services/{env}/{service}/tasks` | GET | Service tasks |
| `/api/services/{env}/{service}/logs` | GET | Service logs |
| `/api/services/{env}/{service}/deploy` | POST | Force deployment |

### Infrastructure

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/infrastructure/{env}` | GET | Infrastructure overview |
| `/api/infrastructure/{env}/alb` | GET | ALB details |
| `/api/infrastructure/{env}/rds` | GET | RDS details |
| `/api/infrastructure/{env}/redis` | GET | ElastiCache details |
| `/api/infrastructure/{env}/cloudfront` | GET | CloudFront details |
| `/api/infrastructure/{env}/network` | GET | Network topology |

### Pipelines

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipelines/build/{service}` | GET | Build pipeline status |
| `/api/pipelines/deploy/{env}/{service}` | GET | Deploy pipeline status |
| `/api/images/{service}` | GET | ECR images |

### Comparison (Environment Sync)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/{project}/comparison/config` | GET | Available comparison pairs |
| `/api/{project}/comparison/{sourceEnv}/{destEnv}/summary` | GET | Comparison summary with execution status |
| `/api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}` | GET | Detailed comparison for a check type |
| `/api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}/history` | GET | Historical comparison data |
| `/api/{project}/comparison/{sourceEnv}/{destEnv}/trigger` | POST | Trigger comparison orchestrator |
| `/api/{project}/comparison/{sourceEnv}/{destEnv}/status` | GET | Execution status |

---

## Comparison Feature

The Comparison feature provides visual environment synchronization monitoring between source and destination environments.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend (React)                                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │ ComparisonPage  │  │ HeroSummary     │  │ SimpleView      │         │
│  │ (main page)     │  │ (donut charts)  │  │ (non-tech view) │         │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘         │
│           └────────────────────┼────────────────────┘                   │
│                                │                                         │
│  ┌─────────────────────────────┴─────────────────────────────┐         │
│  │ ComparisonCard, SyncStatusRing, SyncFlowConnector         │         │
│  └───────────────────────────────────────────────────────────┘         │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ API calls
┌──────────────────────────────────▼──────────────────────────────────────┐
│  Backend (Lambda)                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ comparison/handler.py - Routes and permission checks                 ││
│  └──────────────────────────────────┬──────────────────────────────────┘│
│                                     │                                    │
│  ┌──────────────────────────────────┴──────────────────────────────────┐│
│  │ providers/comparison/                                                ││
│  │ ├── dynamodb.py - DynamoDBComparisonProvider (read comparison data) ││
│  │ └── orchestrator.py - ComparisonOrchestratorProvider (trigger SF)   ││
│  └─────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────┐
│  Step Functions (ops-dashboard-*)                                        │
│  ├── k8s-pods-compare, k8s-services-compare, k8s-ingress-compare       │
│  ├── k8s-pvc-compare, k8s-secrets-compare                               │
│  ├── config-sm-compare (Secrets Manager), config-ssm-compare (SSM)     │
│  └── Orchestrator: ops-dashboard-comparison-orchestrator                │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────┐
│  DynamoDB (ops-dashboard-shared-state)                                   │
│  pk: {project}#comparison:{sourceEnv}:{destEnv}                         │
│  sk: check:{category}:{type}:current                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Frontend Components

| Component | Location | Description |
|-----------|----------|-------------|
| `ComparisonPage` | `components/comparison/` | Main page with view selector |
| `HeroSummary` | `components/comparison/` | Overview with animated donut charts |
| `SimpleView` | `components/comparison/` | Simplified view for non-technical users |
| `ReadinessView` | `components/comparison/` | Full technical details |
| `ComparisonCard` | `components/comparison/` | Individual check card with progress bar |
| `SyncStatusRing` | `components/comparison/` | Animated SVG donut chart |
| `SyncFlowConnector` | `components/comparison/` | Animated flow line between environments |
| `ViewSelector` | `components/comparison/` | Toggle between Simple/Technical views |

### Backend Providers

| Provider | Location | Description |
|----------|----------|-------------|
| `DynamoDBComparisonProvider` | `providers/comparison/dynamodb.py` | Read comparison data from DynamoDB |
| `ComparisonOrchestratorProvider` | `providers/comparison/orchestrator.py` | Trigger Step Function orchestrator |

### Key Features

**Auto-refresh**: When `shouldAutoRefresh` is true (data stale or pending checks), frontend automatically triggers comparison.

**Execution tracking**: Prevents duplicate Step Function executions via DynamoDB state.

**View modes**:
- **Simple View**: Big status indicator, category summary bars, friendly for non-technical users
- **Technical View**: Full grid of comparison cards, detailed metrics

**Status indicators**:
- **synced** (green): Environments match
- **differs** (yellow): Minor differences
- **critical** (red): Major differences
- **incomplete** (orange): Missing data, needs trigger

### Configuration (`infra.config.json`)

```json
{
  "projects": {
    "my-project": {
      "comparison": {
        "refreshThresholdSeconds": 3600
      }
    }
  },
  "comparison": {
    "groups": [
      { "prefix": "src-", "label": "Source", "role": "source" },
      { "prefix": "dst-", "label": "Destination", "role": "destination" }
    ]
  }
}
```

---

## Conventions

### Code Style

- **Python**: Black formatter, type hints where applicable
- **JavaScript**: ESLint, Prettier
- **Commits**: Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`)

### Naming

- **Components**: PascalCase (`ServiceDetails.jsx`)
- **Utilities**: camelCase (`fetchWithRetry.js`)
- **Python modules**: snake_case (`aws_collector.py`)

### API Responses

All API responses follow this structure:

```json
{
  "data": { ... },
  "error": null,
  "metadata": {
    "timestamp": "2024-01-01T00:00:00Z",
    "region": "eu-west-3"
  }
}
```

Error responses:

```json
{
  "data": null,
  "error": "Error message",
  "code": "ERROR_CODE"
}
```

---

## Deployment

### Dashboard (SST v3)

The dashboard uses **SST v3** (built on Pulumi) with three deployment modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| `standalone` | SST creates all resources (S3, CloudFront, Lambda, IAM) | Development, quick demos |
| `semi-managed` | SST creates frontend; Lambda uses Terraform-managed IAM role | Production with external role |
| `managed` | SST syncs to existing S3/CloudFront; Lambda uses external role | Full IaC control |

#### Quick Deploy

```bash
# 1. Configure
cp infra.config.example.json infra.config.json
# Edit mode, aws.region, aws.profile

# 2. Deploy
npm install
npx sst deploy --stage production

# Development mode
npx sst dev
```

#### Configuration File (`infra.config.json`)

```json
{
  "mode": "standalone",
  "aws": {
    "region": "eu-west-3",
    "profile": "myprofile/AdministratorAccess"
  }
}
```

For **semi-managed** or **managed** modes:

```json
{
  "mode": "semi-managed",
  "aws": { "region": "eu-west-3", "profile": "myprofile" },
  "lambda": { "roleArn": "arn:aws:iam::123456789012:role/dashborion-lambda-role" },
  "crossAccountRoles": {
    "staging": {
      "accountId": "111111111111",
      "readRoleArn": "arn:aws:iam::111111111111:role/dashborion-read-role",
      "actionRoleArn": "arn:aws:iam::111111111111:role/dashborion-action-role"
    }
  }
}
```

For **managed** mode (existing frontend infrastructure):

```json
{
  "mode": "managed",
  "aws": { "region": "eu-west-3", "profile": "myprofile" },
  "lambda": { "roleArn": "arn:aws:iam::123456789012:role/dashborion-lambda-role" },
  "frontend": {
    "s3Bucket": "my-dashboard-bucket",
    "cloudfrontDistributionId": "E1EXAMPLE",
    "cloudfrontDomain": "dashboard.example.com"
  }
}
```

#### Terraform Modules

| Module | Description |
|--------|-------------|
| `terraform/modules/sst-deploy-role/` | IAM role for SST/Pulumi deployment |
| `terraform/modules/sst-lambda-role/` | Lambda execution role with dashboard permissions |
| `terraform/modules/cross-account-roles/` | Read/action roles for cross-account access |

```bash
# Deploy Terraform modules (for semi-managed/managed modes)
cd terraform/modules/sst-deploy-role
terraform init
terraform apply -var="mode=semi-managed"
```

### CLI (pip)

```bash
pip install dashborion-cli
```

### CLI (Homebrew)

```bash
brew tap KamorionLabs/tap
brew install dashborion-cli
```

---

## Testing

### Frontend

```bash
cd frontend
npm test
npm run lint
```

### Backend

```bash
cd backend
pytest
```

### CLI

```bash
cd cli
pytest
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'feat: add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## Quick Reference

### Common Tasks

```bash
# List services in staging
dashborion services list --env staging --profile myprofile

# Show infrastructure
dashborion infra show --env production --output json

# Generate diagram
dashborion diagram generate --env staging --output architecture.png

# Publish to Confluence
dashborion diagram publish --env staging --confluence-page 12345

# Kubernetes resources
dashborion k8s pods --context my-cluster --namespace default
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `AWS_PROFILE` | AWS profile to use |
| `AWS_REGION` | AWS region |
| `DASHBORION_CONFIG` | Path to config file |
| `CONFLUENCE_URL` | Confluence base URL |
| `CONFLUENCE_USERNAME` | Confluence username |
| `CONFLUENCE_TOKEN` | Confluence API token |

---

*Developed by [Kamorion](https://kamorion.com) - Cloud & DevOps Consulting*
