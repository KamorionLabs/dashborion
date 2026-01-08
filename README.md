<p align="center">
  <img src="docs/screenshots/logo-placeholder.png" alt="Dashborion Logo" width="200" />
</p>

<h1 align="center">Dashborion</h1>

<p align="center">
  <strong>Modern infrastructure operations dashboard for AWS ECS, EKS, and CI/CD pipelines</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#screenshots">Screenshots</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License" />
  <img src="https://img.shields.io/badge/python-3.9+-green.svg" alt="Python" />
  <img src="https://img.shields.io/badge/node-18+-green.svg" alt="Node" />
  <img src="https://img.shields.io/badge/SST-v3-orange.svg" alt="SST" />
  <img src="https://img.shields.io/badge/React-18-61dafb.svg" alt="React" />
</p>

---

## Overview

Dashborion is a comprehensive infrastructure visualization and operations tool designed for DevOps teams managing AWS workloads. It provides real-time visibility into ECS services, infrastructure components, CI/CD pipelines, and enables quick operational actions—all through a modern web interface and CLI.

### Why Dashborion?

- **Single pane of glass** - View services, infrastructure, pipelines, and events in one place
- **Deep AWS integration** - Native support for ECS, ALB, RDS, ElastiCache, CloudFront, VPC
- **Multi-environment** - Switch between staging, preprod, and production instantly
- **Actionable** - Deploy, restart, scale services, invalidate caches, control RDS
- **Shareable URLs** - Deep-link to any view, service, or resource for collaboration
- **Secure by default** - Native SAML SSO, RBAC, audit logging

---

## Screenshots

### Simple View
Overview of services, pipelines, and infrastructure status at a glance.

![Simple View](docs/screenshots/dashboard-simple-view.png)

### Network View
Detailed VPC topology with subnets, ENIs, security groups, and data stores.

![Network View](docs/screenshots/dashboard-network-view.png)

### Routing View
Route tables, NAT gateways, VPC endpoints, and subnet associations.

![Routing View](docs/screenshots/dashboard-routing-view.png)

---

## Features

### Web Dashboard

| Feature | Description |
|---------|-------------|
| **Services** | ECS services status, tasks, deployments, real-time logs |
| **Infrastructure** | ALB, RDS, ElastiCache, CloudFront, S3, VPC components |
| **Pipelines** | Build/deploy pipelines, ECR images, execution history |
| **Events Timeline** | CloudTrail, ECS events, deployments with filtering |
| **Network Explorer** | ENIs, security groups with expandable rules |
| **Quick Actions** | Deploy, restart, scale, invalidate cache, RDS control |
| **Deep-linking** | Bookmark and share any view or resource |
| **Native SSO** | Built-in SAML via Lambda@Edge (no external modules) |
| **RBAC** | Project/environment scoped roles (viewer, operator, admin) |

### CLI Tool

```bash
# Authentication
dashborion auth login              # Device flow (opens browser)
dashborion auth login --use-sso    # Reuse AWS SSO session
dashborion auth whoami             # Show current user

# Services
dashborion services list --env staging
dashborion services describe backend --env production

# Infrastructure
dashborion infra show --env staging --output json

# Diagrams
dashborion diagram generate --env staging --output architecture.png
dashborion diagram publish --confluence-page 12345
```

### Supported Platforms

| Compute | CI/CD | Storage |
|---------|-------|---------|
| AWS ECS Fargate | AWS CodePipeline | RDS PostgreSQL/MySQL |
| AWS ECS EC2 | AWS CodeBuild | ElastiCache (Redis/Valkey) |
| AWS EKS | ArgoCD | S3 |
| Kubernetes | GitHub Actions | CloudFront |

---

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.9+ (for CLI)
- AWS credentials configured

### Dashboard Deployment

```bash
# 1. Clone the repository
git clone https://github.com/KamorionLabs/dashborion.git
cd dashborion

# 2. Install dependencies
npm install

# 3. Configure deployment
cp infra.config.example.json infra.config.json
# Edit: mode, aws.region, aws.profile

# 4. Deploy with SST
npx sst deploy --stage production
```

### CLI Installation

```bash
# Via pip
pip install dashborion-cli

# Via Homebrew (macOS/Linux)
brew tap KamorionLabs/tap
brew install dashborion-cli
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CloudFront                                │
│                    (Lambda@Edge SSO)                             │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
          ▼                               ▼
┌─────────────────┐             ┌─────────────────┐
│   S3 (Frontend) │             │  API Gateway    │
│   React SPA     │             │  + Lambda       │
└─────────────────┘             └────────┬────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ▼                    ▼                    ▼
           ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
           │   Staging    │    │   Preprod    │    │  Production  │
           │   Account    │    │   Account    │    │   Account    │
           │  (ECS, RDS)  │    │  (ECS, RDS)  │    │  (ECS, RDS)  │
           └──────────────┘    └──────────────┘    └──────────────┘
```

### Deployment Modes

| Mode | Frontend | Backend | Use Case |
|------|----------|---------|----------|
| **Standalone** | SST creates S3 + CloudFront | SST creates Lambda + IAM | Dev, demos |
| **Semi-managed** | SST creates S3 + CloudFront | Lambda uses Terraform IAM role | Production |
| **Managed** | SST syncs to existing S3 + CloudFront | Lambda uses Terraform IAM role | Full IaC |

---

## Configuration

### Dashboard Config (`config.json`)

```json
{
  "projects": [{
    "id": "my-project",
    "name": "My Project",
    "environments": ["staging", "production"],
    "services": ["backend", "frontend", "api"],
    "infrastructure": {
      "discoveryTags": { "Project": "my-project" }
    }
  }]
}
```

### Authentication (`infra.config.json`)

```json
{
  "auth": {
    "enabled": true,
    "provider": "saml",
    "saml": {
      "entityId": "dashborion",
      "idpMetadataUrl": "https://portal.sso.region.amazonaws.com/saml/metadata/..."
    }
  },
  "authorization": {
    "enabled": true,
    "defaultRole": "viewer"
  }
}
```

---

## Deep-Linking

Share specific views and resources with bookmarkable URLs:

```
# Service details
/project/staging?service=backend

# Infrastructure resource
/project/staging?view=network&resource=subnet&id=subnet-abc123

# Route table with details panel
/project/staging?view=routing&resource=routeTable&id=rtb-xyz789

# Logs with multiple tabs
/project/staging?logs=backend,frontend

# Events timeline with filters
/project/staging?events=true&hours=48&types=deploy,error
```

| Parameter | Description | Example |
|-----------|-------------|---------|
| `view` | View mode | `simple`, `network`, `routing` |
| `service` | ECS service | `backend` |
| `resource` | Resource type | `subnet`, `routeTable`, `rds` |
| `id` | Resource ID | `subnet-abc123` |
| `logs` | Log tabs | `backend,frontend` |
| `events` | Show timeline | `true` |

---

## Project Structure

```
dashborion/
├── packages/
│   └── frontend/          # React dashboard (Vite + Tailwind)
├── backend/               # Lambda API (Python)
│   ├── routes/            # API endpoints
│   ├── providers/         # AWS data providers
│   └── auth/              # RBAC + Device Flow
├── cli/                   # CLI tool (Python)
│   └── dashborion/
│       ├── commands/      # CLI commands
│       ├── collectors/    # AWS/K8s data
│       └── generators/    # Diagram generation
├── terraform/             # IAM roles modules
│   └── modules/
├── sst.config.ts          # SST v3 deployment
└── infra.config.json      # Deployment configuration
```

---

## Authorization (RBAC)

| Role | Permissions |
|------|-------------|
| `viewer` | Read: services, logs, metrics, infrastructure |
| `operator` | + deploy, scale, restart, invalidate cache |
| `admin` | + start/stop RDS, manage permissions |

Permissions are scoped by project and environment:
- `viewer` on `project/production`
- `operator` on `project/staging`
- `admin` on `project/*`

IdP group mapping: `dashborion-{project}-{role}`

---

## API Reference

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/device/code` | POST | Request device code (CLI) |
| `/api/auth/device/token` | POST | Exchange for access token |
| `/api/auth/me` | GET | Current user info |

### Services
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/{project}/services/{env}` | GET | List services |
| `/api/{project}/services/{env}/{service}/tasks` | GET | Service tasks |
| `/api/{project}/services/{env}/{service}/logs` | GET | Service logs |

### Infrastructure
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/{project}/infrastructure/{env}` | GET | Full infrastructure |
| `/api/{project}/infrastructure/{env}/routing` | GET | VPC routing data |
| `/api/{project}/infrastructure/{env}/enis` | GET | Network interfaces |

---

## Development

```bash
# Frontend development
cd packages/frontend
npm install
npm run dev

# Backend (local Lambda)
cd backend
pip install -r requirements.txt
sam local start-api

# CLI development
cd cli
pip install -e .
dashborion --help
```

---

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md).

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Credits

Developed by [Kamorion](https://kamorion.com) - Cloud & DevOps Consulting

Built with production infrastructure experience across multiple enterprise clients.

<p align="center">
  <sub>Made with ❤️ for DevOps teams</sub>
</p>
