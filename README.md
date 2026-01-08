# Dashborion

**Multi-cloud infrastructure dashboard with CLI** - Visualize and manage ECS, EKS, and CI/CD pipelines.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![Node](https://img.shields.io/badge/node-18+-green.svg)

## Overview

Dashborion is a comprehensive infrastructure visualization and management tool that provides:

- **Web Dashboard**: Real-time infrastructure monitoring with SSO authentication
- **CLI Tool**: Command-line interface with AWS SigV4 authentication
- **Diagram Generation**: Automatic architecture diagram creation with Confluence publishing

### Supported Platforms

| Compute | CI/CD | Cloud |
|---------|-------|-------|
| AWS ECS (Fargate & EC2) | AWS CodePipeline | AWS |
| AWS EKS | ArgoCD | - |
| Kubernetes | Jenkins | - |
| - | GitLab CI | - |
| - | Bitbucket Pipelines | - |

## Features

### Web Dashboard

- **Services View**: ECS/EKS services, tasks, deployments, logs
- **Infrastructure View**: ALB, RDS, ElastiCache, CloudFront, VPC, Security Groups
- **Pipelines View**: Build and deploy pipelines, ECR images
- **Events Timeline**: CloudTrail, ECS events, deployments
- **Network View**: ENIs, subnets, route tables, security group rules
- **Actions**: Force deploy, cache invalidation, start/stop RDS
- **Native SSO**: Built-in SAML authentication via Lambda@Edge (no external module)
- **Multi-tenant Authorization**: RBAC with project/environment granularity
- **Deep-linkable URLs**: Bookmark and share specific views, services, and resources

### CLI Tool (`dashborion`)

```bash
# Authentication (Device Flow or AWS SSO)
dashborion auth login              # Opens browser for SSO
dashborion auth login --use-sso    # Reuse AWS SSO session
dashborion auth whoami             # Show current user
dashborion auth logout

# List services
dashborion services list --env staging --profile myprofile

# Show service details
dashborion services describe backend --env production

# Infrastructure overview
dashborion infra show --env staging --output json

# Generate architecture diagram
dashborion diagram generate --env staging --output architecture.png

# Kubernetes resources (EKS)
dashborion k8s pods --context arn:aws:eks:... --namespace staging
dashborion k8s services --context ... --output table

# Publish diagram to Confluence
dashborion diagram publish --env staging --confluence-page 12345
```

### Diagram Generation

- Automatic architecture diagrams using [diagrams](https://diagrams.mingrammer.com/)
- AWS resources visualization (ALB, RDS, API Gateway, VPC)
- Kubernetes resources (Pods, Services, Ingresses, Nodes)
- Confluence integration for documentation

## Installation

### CLI Installation

```bash
# Via pip
pip install dashborion-cli

# Via Homebrew (macOS/Linux)
brew tap KamorionLabs/tap
brew install dashborion-cli
```

### Dashboard Deployment

The dashboard uses **SST v3** (built on Pulumi) for deployment with three modes:

| Mode | Frontend | Backend | Use Case |
|------|----------|---------|----------|
| **Standalone** | SST creates S3 + CloudFront | SST creates Lambda + IAM role | Development, quick demos |
| **Semi-managed** | SST creates S3 + CloudFront | Lambda uses Terraform-managed IAM role | Production with managed Lambda role |
| **Managed** | SST syncs to existing S3 + CloudFront | Lambda uses Terraform-managed IAM role | Full IaC control |

#### Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Copy and configure infra.config.json
cp infra.config.example.json infra.config.json
# Edit mode, aws.region, aws.profile as needed

# 3. Deploy
npx sst deploy --stage production
```

#### Configuration (`infra.config.json`)

```json
{
  "mode": "standalone",
  "aws": {
    "region": "eu-west-3",
    "profile": "myprofile/AdministratorAccess"
  }
}
```

For **semi-managed** or **managed** modes, additional configuration is required:

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

#### Authentication Configuration

Enable native SAML authentication via Lambda@Edge:

```json
{
  "auth": {
    "enabled": true,
    "provider": "saml",
    "saml": {
      "entityId": "dashborion",
      "idpMetadataUrl": "https://portal.sso.eu-west-3.amazonaws.com/saml/metadata/..."
    },
    "sessionTtlSeconds": 3600,
    "cookieDomain": ".example.com"
  },
  "authorization": {
    "enabled": true,
    "defaultRole": "viewer",
    "requireMfaForProduction": true
  }
}
```

#### Terraform Modules

The `terraform/modules/` directory provides IAM roles for SST deployment:

| Module | Description |
|--------|-------------|
| `sst-deploy-role` | IAM role for SST/Pulumi to deploy resources |
| `sst-lambda-role` | Lambda execution role with dashboard permissions |
| `cross-account-roles` | Read/action roles for cross-account access |
| `dashborion-auth-infra` | DynamoDB tables for auth (permissions, audit, tokens, device_codes) |

```bash
# Deploy Terraform modules first (for semi-managed/managed modes)
cd terraform
terraform init
terraform apply
```

## Quick Start

### CLI Setup

1. Configure AWS credentials:
```bash
aws configure --profile myprofile
```

2. Create a configuration file `~/.dashborion/config.yaml`:
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
    aws_region: eu-west-3

  eks-staging:
    type: eks
    context: arn:aws:eks:eu-west-3:123456789:cluster/my-eks
    namespaces:
      - staging
      - common
    aws_profile: myprofile
```

3. Run commands:
```bash
dashborion services list --env staging
dashborion infra show --env production --output table
```

### Dashboard Setup

1. Configure deployment:
```bash
cp infra.config.example.json infra.config.json
# Edit mode, aws.region, aws.profile
```

2. Deploy with SST:
```bash
npm install
npx sst deploy --stage production
```

3. (Optional) For semi-managed/managed modes, deploy Terraform modules first:
```bash
cd terraform/modules
# Deploy sst-deploy-role, sst-lambda-role, cross-account-roles
terraform init && terraform apply
```

4. Configure SSO (optional):
   - Set up AWS Identity Center or any SAML provider
   - Configure CloudFront Lambda@Edge for authentication

5. Access the dashboard at the URL output by SST

## Project Structure

```
dashborion/
├── auth/                  # Lambda@Edge authentication (TypeScript)
│   ├── src/
│   │   ├── handlers/      # protect.ts, acs.ts, metadata.ts
│   │   └── utils/         # crypto.ts, saml.ts, session.ts
│   └── scripts/
│       └── bundle.js      # Lambda@Edge bundler
│
├── frontend/              # React dashboard application
│   ├── src/
│   │   ├── components/    # UI components
│   │   ├── hooks/         # useAuth.js, etc.
│   │   ├── pages/         # DeviceAuth.jsx (CLI verification)
│   │   ├── utils/         # Utilities and helpers
│   │   └── App.jsx        # Main application
│   └── public/
│       └── config.json    # Runtime configuration
│
├── backend/               # Lambda API backend
│   ├── handler.py         # Lambda entry point
│   ├── auth/              # Authorization module
│   │   ├── middleware.py  # Request authorization
│   │   ├── decorators.py  # @require_permission
│   │   ├── permissions.py # Permission checking
│   │   ├── device_flow.py # RFC 8628 Device Authorization
│   │   ├── handlers.py    # Auth API endpoints
│   │   └── models.py      # AuthContext, Permission, Role
│   ├── routes/            # API route handlers
│   ├── providers/         # Data providers
│   │   ├── ci/            # CI/CD providers (CodePipeline, ArgoCD, etc.)
│   │   ├── infrastructure/# Infrastructure providers (ECS, EKS, etc.)
│   │   └── events/        # Event providers
│   └── utils/             # Backend utilities
│
├── cli/                   # CLI tool
│   └── dashborion/
│       ├── __init__.py
│       ├── main.py        # Main CLI entry point
│       ├── commands/      # CLI commands
│       │   └── auth.py    # login, logout, whoami, status, token
│       ├── collectors/    # AWS/K8s data collectors
│       ├── generators/    # Diagram generators
│       └── publishers/    # Confluence, etc.
│
├── terraform/             # Infrastructure as Code
│   └── modules/
│       ├── sst-deploy-role/       # SST deployment IAM role
│       ├── sst-lambda-role/       # Lambda execution role
│       ├── cross-account-roles/   # Cross-account access roles
│       └── dashborion-auth-infra/ # Auth DynamoDB tables
│
├── sst.config.ts          # SST v3 configuration (Pulumi-based)
├── infra.config.json      # Deployment configuration (mode, AWS, auth)
│
├── docs/                  # Documentation
└── examples/              # Example configurations
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AWS_PROFILE` | AWS profile to use | No (uses default) |
| `AWS_REGION` | AWS region | No (uses config) |
| `DASHBORION_CONFIG` | Path to config file | No |
| `CONFLUENCE_URL` | Confluence base URL | For publishing |
| `CONFLUENCE_USERNAME` | Confluence username | For publishing |
| `CONFLUENCE_TOKEN` | Confluence API token | For publishing |

### Dashboard Configuration (`config.json`)

```json
{
  "projects": [
    {
      "id": "my-project",
      "name": "My Project",
      "environments": ["staging", "production"],
      "services": ["backend", "frontend", "api"],
      "infrastructure": {
        "discoveryTags": {
          "Project": "my-project"
        }
      }
    }
  ]
}
```

## Authentication

### Web Dashboard (Native SSO)

Built-in SAML authentication via Lambda@Edge:

- **Lambda@Edge protect**: Validates session cookie, redirects to IdP if needed
- **SAML ACS handler**: Processes SAML assertion, creates encrypted session cookie
- **Session security**: AES-256-GCM encrypted cookies with IP validation
- **Supported IdPs**: AWS Identity Center, Okta, Azure AD, any SAML 2.0 provider

### CLI Authentication

Two authentication methods:

**1. Device Flow (default)** - Opens browser for SSO authentication:
```bash
dashborion auth login

# Output:
# To authenticate, visit: https://dashboard.example.com/auth/device
# And enter code: ABCD-1234
# Opening browser...
# Waiting for authentication...
# Successfully authenticated!
```

**2. AWS SSO** - Reuse existing AWS SSO session:
```bash
# First, authenticate with AWS SSO
aws sso login --profile myprofile

# Then exchange for Dashborion token
dashborion auth login --use-sso
```

**Token management:**
```bash
dashborion auth whoami     # Show current user and token expiry
dashborion auth status     # Check if authenticated (exit code 0/1)
dashborion auth token      # Print access token (for scripting)
dashborion auth logout     # Revoke token and delete credentials
```

Credentials stored in `~/.dashborion/credentials.json` with 600 permissions.

### Authorization (RBAC)

Multi-tenant permission model with three roles:

| Role | Permissions |
|------|-------------|
| `viewer` | Read-only: view services, logs, metrics, infrastructure |
| `operator` | Viewer + deploy, scale, restart, invalidate cache |
| `admin` | Operator + start/stop RDS, manage permissions |

Permissions are scoped by project and environment:
- `viewer` on `homebox/production`
- `operator` on `homebox/staging`
- `admin` on `bigmat/*` (all environments)

IdP group mapping pattern: `dashborion-{project}-{role}` (e.g., `dashborion-homebox-operator`)

## Deep-Linking URLs

The dashboard supports deep-linkable URLs for bookmarking and sharing specific views:

### URL Structure

```
/:project/:env?param1=value1&param2=value2
```

### Available Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `view` | string | View mode: simple, network, routing | `?view=network` |
| `service` | string | Selected ECS service | `?service=backend` |
| `resource` | string | Infrastructure resource type | `?resource=rds` |
| `id` | string | Resource ID | `?resource=subnet&id=subnet-abc123` |
| `pipeline` | string | Build pipeline for a service | `?pipeline=backend` |
| `logs` | string | Comma-separated log tabs | `?logs=backend,frontend` |
| `events` | boolean | Show events timeline | `?events=true` |
| `hours` | number | Events time filter | `?hours=48` |
| `types` | string | Event type filter | `?types=deploy,build` |

### Examples

```
# Service details panel
/homebox/staging?service=backend

# Network view with subnet selected
/homebox/staging?view=network&resource=subnet&id=subnet-0abc123

# Logs panel with multiple tabs
/homebox/staging?logs=backend,frontend,cms

# Events timeline with filters
/homebox/staging?events=true&hours=48&types=deploy,error

# Build pipeline details
/homebox/staging?pipeline=backend
```

## API Reference

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/device/code` | POST | Request device code (CLI login) |
| `/api/auth/device/token` | POST | Exchange device code for token |
| `/api/auth/device/verify` | POST | Verify device code (web page) |
| `/api/auth/token/refresh` | POST | Refresh access token |
| `/api/auth/token/revoke` | POST | Revoke access token |
| `/api/auth/sso/exchange` | POST | Exchange AWS credentials for token |
| `/api/auth/me` | GET | Get current user info |
| `/api/auth/whoami` | GET | Get auth status and user details |

### Services

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/services/{env}` | GET | List services |
| `/api/services/{env}/{service}` | GET | Service details |
| `/api/services/{env}/{service}/tasks` | GET | Service tasks |
| `/api/services/{env}/{service}/logs` | GET | Service logs |

### Infrastructure

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/infrastructure/{env}` | GET | Infrastructure overview |
| `/api/infrastructure/{env}/alb` | GET | ALB details |
| `/api/infrastructure/{env}/rds` | GET | RDS details |
| `/api/infrastructure/{env}/security-group/{id}` | GET | Security group rules |

### Pipelines

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipelines/build/{service}` | GET | Build pipeline status |
| `/api/pipelines/deploy/{env}/{service}` | GET | Deploy pipeline status |
| `/api/images/{service}` | GET | ECR images |

## Development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
pip install -r requirements.txt
# Use SAM or serverless for local development
```

### CLI

```bash
cd cli
pip install -e .
dashborion --help
```

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Developed by [Kamorion](https://kamorion.com) - Cloud & DevOps Consulting

Based on production infrastructure tooling used across multiple enterprise clients.
