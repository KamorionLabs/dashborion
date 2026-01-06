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
├── terraform/             # Infrastructure as Code
│   ├── api_gateway.tf     # API Gateway configuration
│   ├── lambda.tf          # Lambda functions
│   ├── cloudfront.tf      # CloudFront distribution
│   └── ...
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

### Web Dashboard

- **SSO**: CloudFront Lambda@Edge with SAML/OIDC
- Supports AWS Identity Center, Okta, Azure AD

### CLI

- **AWS SigV4**: Uses AWS credentials from profiles
- **Profile support**: `--profile <profile>` flag
- Uses `~/.aws/credentials` or environment variables

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

### Dashboard (Terraform)

```bash
cd terraform
terraform init
terraform plan -var="project_name=my-dashboard"
terraform apply
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
