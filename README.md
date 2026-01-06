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

### CLI Tool (`dashborion`)

```bash
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

#### Terraform Modules

The `terraform/modules/` directory provides IAM roles for SST deployment:

| Module | Description |
|--------|-------------|
| `sst-deploy-role` | IAM role for SST/Pulumi to deploy resources |
| `sst-lambda-role` | Lambda execution role with dashboard permissions |
| `cross-account-roles` | Read/action roles for cross-account access |

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
├── frontend/              # React dashboard application
│   ├── src/
│   │   ├── components/    # UI components
│   │   ├── utils/         # Utilities and helpers
│   │   └── App.jsx        # Main application
│   └── public/
│       └── config.json    # Runtime configuration
│
├── backend/               # Lambda API backend
│   ├── handler.py         # Lambda entry point
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
│       ├── cli.py         # Main CLI entry point
│       ├── commands/      # CLI commands
│       ├── collectors/    # AWS/K8s data collectors
│       ├── generators/    # Diagram generators
│       └── publishers/    # Confluence, etc.
│
├── terraform/             # Infrastructure as Code
│   └── modules/
│       ├── sst-deploy-role/      # SST deployment IAM role
│       ├── sst-lambda-role/      # Lambda execution role
│       └── cross-account-roles/  # Cross-account access roles
│
├── sst.config.ts          # SST v3 configuration (Pulumi-based)
├── infra.config.json      # Deployment configuration (mode, AWS settings)
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

### Web Dashboard

- **SSO via CloudFront**: Uses Lambda@Edge for SAML/OIDC authentication
- Supports AWS Identity Center, Okta, Azure AD, etc.

### CLI

- **AWS SigV4**: Uses AWS credentials from profiles
- Specify profile: `--profile myprofile`
- Uses `~/.aws/credentials` or environment variables

## API Reference

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
