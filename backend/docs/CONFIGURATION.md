# Dashborion Configuration Reference

Configuration is loaded from **SSM Parameter Store** (recommended) or environment variables.

---

## Configuration Locations (Important)

When modifying configuration schema or adding new fields, changes must be synchronized across **3 locations**:

| Location | Files | Description |
|----------|-------|-------------|
| **Feature Code** | `backend/{feature}/handler.py`, `packages/frontend/src/pages/*.jsx` | Backend handlers and frontend pages that use the config |
| **Admin UI** | `packages/frontend/src/pages/admin/EnvironmentForm.jsx`, etc. | Admin forms for editing configuration |
| **CLI** | `cli/dashborion/commands/config_registry.py` | CLI migration and import/export commands |

### Environment Configuration Format (v2.2)

The current flat format for environments:

```json
{
  "projectId": "my-project",
  "envId": "staging",
  "displayName": "Staging",
  "accountId": "123456789012",
  "region": "eu-central-1",
  "clusterName": "my-cluster",
  "namespace": "my-namespace",
  "services": ["service1", "service2"],
  "readRoleArn": "arn:aws:iam::...",
  "actionRoleArn": "arn:aws:iam::...",
  "status": "active",
  "enabled": true,
  "infrastructure": {
    "defaultTags": {"Environment": "staging"},
    "domainConfig": {"domains": {"frontend": "fr", "backend": "back"}},
    "resources": {
      "rds": { "ids": ["my-db"], "tags": {} },
      "redis": { "ids": ["my-cache"], "tags": {} },
      "alb": { "ids": ["arn:aws:elasticloadbalancing:..."], "tags": {} }
    }
  },
  "checkers": {}
}
```

**Key fields:**
- `clusterName`, `namespace`: Flat fields for EKS orchestrator
- `services`: Array for ECS orchestrator services
- `infrastructure.defaultTags`: Fallback tags for AWS resource discovery
- `infrastructure.resources.<resource>.ids`: Explicit AWS resource IDs (take precedence)
- `infrastructure.resources.<resource>.tags`: Tags for resource discovery when no IDs are set
- `infrastructure.domainConfig`: Optional domain mapping for frontend links and CloudFront filtering

## Configuration Storage

### SSM Parameter Store (Recommended)

Since v2.x, large configurations (`PROJECTS`, `CROSS_ACCOUNT_ROLES`) are stored in SSM Parameter Store to avoid Lambda's 4KB environment variable limit.

**Structure:**
```
{prefix}/projects/{project-id}     # One parameter per project
{prefix}/cross-account-roles       # Cross-account IAM roles
```

**Required environment variable:**
```bash
CONFIG_SSM_PREFIX=/dashborion/myorg  # SSM prefix for this deployment
```

**IAM permissions required:**
```json
{
  "Effect": "Allow",
  "Action": [
    "ssm:GetParameter",
    "ssm:GetParameters",
    "ssm:GetParametersByPath"
  ],
  "Resource": "arn:aws:ssm:*:*:parameter/dashborion/*"
}
```

### infra.config.json

The SSM prefix is configured in `infra.config.json`:

```json
{
  "ssm": {
    "prefix": "/dashborion/myorg"
  }
}
```

SST automatically creates SSM parameters from the `projects` and `crossAccountRoles` sections.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CONFIG_SSM_PREFIX` | **Yes** | SSM parameter prefix (e.g., `/dashborion/myorg`) |
| `AWS_REGION_DEFAULT` | No | Default AWS region (default: `eu-west-3`) |
| `SHARED_SERVICES_ACCOUNT` | Yes | AWS account ID for shared services (ECR, etc.) |
| `SSO_PORTAL_URL` | Yes | AWS SSO portal URL for console links |
| `NAMING_PATTERN` | No | JSON object for resource naming patterns |
| `CI_PROVIDER` | No | JSON object for CI/CD provider config |
| `ORCHESTRATOR` | No | JSON object for container orchestrator config |
| `GITHUB_ORG` | No | GitHub organization for commit links |

> **Note:** `PROJECTS` and `CROSS_ACCOUNT_ROLES` are no longer passed as environment variables. They are loaded from SSM at runtime.

---

## PROJECTS Configuration

The `PROJECTS` variable defines all monitored projects and their environments.

### Schema

```json
{
  "project-name": {
    "displayName": "Human Readable Name",
    "environments": {
      "env-name": {
        "accountId": "123456789012",
        "region": "eu-central-1",
        "services": ["service1", "service2"],
        "clusterName": "optional-cluster-override",
        "namespace": "kubernetes-namespace",
        "readRoleArn": "arn:aws:iam::123456789012:role/read-role",
        "actionRoleArn": "arn:aws:iam::123456789012:role/action-role",
        "status": "active"
      }
    },
    "idpGroupMapping": {
      "admin": ["idp-group-1"],
      "readonly": ["idp-group-2"]
    }
  }
}
```

### Environment Fields

| Field | Required | Description |
|-------|----------|-------------|
| `accountId` | Yes | AWS account ID |
| `region` | No | AWS region (inherits from `AWS_REGION_DEFAULT`) |
| `services` | Yes | List of service names to monitor |
| `clusterName` | No | Override ECS/EKS cluster name (default: `{project}-{env}`) |
| `namespace` | No | Kubernetes namespace (EKS only) |
| `readRoleArn` | No | Override IAM role for read operations |
| `actionRoleArn` | No | Override IAM role for write operations |
| `status` | No | Environment status (`active`, `deployed`, `planned`) |

### Role Resolution Priority

When accessing AWS resources, the dashboard resolves IAM roles in this order:

1. **Environment-level** `readRoleArn` / `actionRoleArn` (highest priority)
2. **Account-level** role from `CROSS_ACCOUNT_ROLES[accountId]`
3. **No role** - uses Lambda execution role (same-account only)

This allows reusing existing IAM roles (e.g., Step Functions roles) instead of creating new dashboard-specific roles.

### Example: Multi-Account with Role Override

```json
{
  "webshop": {
    "displayName": "Webshop E-commerce",
    "environments": {
      "staging": {
        "accountId": "111111111111",
        "region": "eu-central-1",
        "services": ["frontend", "backend", "cms"]
      },
      "production": {
        "accountId": "222222222222",
        "region": "eu-central-1",
        "services": ["frontend", "backend", "cms"]
      },
      "legacy-staging": {
        "accountId": "333333333333",
        "region": "eu-central-1",
        "services": ["hybris"],
        "clusterName": "legacy-eks-cluster",
        "namespace": "hybris",
        "readRoleArn": "arn:aws:iam::333333333333:role/step_function_eks_nonprod"
      },
      "legacy-production": {
        "accountId": "333333333333",
        "region": "eu-central-1",
        "services": ["hybris"],
        "clusterName": "legacy-eks-cluster",
        "namespace": "hybris-prod",
        "readRoleArn": "arn:aws:iam::333333333333:role/step_function_eks_prod"
      }
    }
  }
}
```

In this example:
- `staging` and `production` use roles from `CROSS_ACCOUNT_ROLES`
- `legacy-staging` and `legacy-production` share the same AWS account but use different IAM roles per environment

---

## CROSS_ACCOUNT_ROLES Configuration

Defines IAM roles for cross-account access, indexed by AWS account ID.

### Schema

```json
{
  "123456789012": {
    "readRoleArn": "arn:aws:iam::123456789012:role/DashboardReadRole",
    "actionRoleArn": "arn:aws:iam::123456789012:role/DashboardActionRole"
  },
  "987654321098": {
    "readRoleArn": "arn:aws:iam::987654321098:role/DashboardReadRole",
    "actionRoleArn": "arn:aws:iam::987654321098:role/DashboardActionRole"
  }
}
```

### Role Types

| Role | Purpose | Required Permissions |
|------|---------|---------------------|
| `readRoleArn` | Read-only operations | ECS/EKS describe, CloudWatch logs, S3 read |
| `actionRoleArn` | Write operations | ECS update service, deploy, restart tasks |

### IAM Trust Policy

Both roles must trust the Lambda execution role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::DASHBOARD_ACCOUNT:role/DashboardLambdaRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

---

## Topology Configuration

The `topology` section defines the application architecture for the infrastructure diagram. It enables customization of how components are displayed and connected.

### Schema

```json
{
  "topology": {
    "components": {
      "component-id": {
        "type": "service-type",
        "layer": "layer-name",
        "label": "Display Label",
        "group": "optional-group"
      }
    },
    "connections": [
      { "from": "component-a", "to": "component-b", "protocol": "https" }
    ],
    "layers": ["layer1", "layer2", "layer3"]
  }
}
```

### Component Types

| Type | Description | Orchestrator |
|------|-------------|--------------|
| `cdn` | Content Delivery Network (CloudFront) | Both |
| `loadbalancer` | Application Load Balancer | Both |
| `ecs-service` | ECS Fargate Service | ECS |
| `k8s-deployment` | Kubernetes Deployment | EKS |
| `k8s-statefulset` | Kubernetes StatefulSet | EKS |
| `rds` | RDS/Aurora Database | Both |
| `elasticache` | ElastiCache (Redis/Memcached) | Both |
| `efs` | Elastic File System | Both |
| `s3` | S3 Bucket | Both |

### Layers

Layers define the vertical position of components in the diagram:

| Layer | Description | Typical Components |
|-------|-------------|-------------------|
| `edge` | Internet-facing CDN | CloudFront |
| `ingress` | Load balancing | ALB, Ingress |
| `frontend` | User-facing services | Next.js, React |
| `proxy` | Reverse proxies | Apache, HAProxy, Nginx |
| `application` | Business logic | Backend services |
| `search` | Search engines | Solr, Elasticsearch |
| `data` | Data persistence | RDS, Redis, EFS |

### Example: ECS Application

```json
{
  "topology": {
    "components": {
      "cloudfront": { "type": "cdn", "layer": "edge", "label": "CloudFront" },
      "alb": { "type": "loadbalancer", "layer": "ingress", "label": "ALB" },
      "frontend": { "type": "ecs-service", "layer": "frontend", "label": "Frontend" },
      "backend": { "type": "ecs-service", "layer": "application", "label": "Backend API" },
      "cms": { "type": "ecs-service", "layer": "application", "label": "CMS" },
      "rds": { "type": "rds", "layer": "data", "label": "Aurora PostgreSQL" },
      "redis": { "type": "elasticache", "layer": "data", "label": "Redis Cache" }
    },
    "connections": [
      { "from": "cloudfront", "to": "alb", "protocol": "https" },
      { "from": "alb", "to": "frontend", "protocol": "http" },
      { "from": "alb", "to": "backend", "protocol": "http" },
      { "from": "frontend", "to": "backend", "protocol": "http" },
      { "from": "backend", "to": "rds", "protocol": "jdbc" },
      { "from": "backend", "to": "redis", "protocol": "redis" },
      { "from": "cms", "to": "rds", "protocol": "jdbc" }
    ],
    "layers": ["edge", "ingress", "frontend", "application", "data"]
  }
}
```

### Example: EKS Application (Hybris)

```json
{
  "topology": {
    "components": {
      "cloudfront": { "type": "cdn", "layer": "edge", "label": "CloudFront" },
      "alb": { "type": "loadbalancer", "layer": "ingress", "label": "ALB" },
      "nextjs": { "type": "k8s-deployment", "layer": "frontend", "label": "Next.JS" },
      "apache": { "type": "k8s-deployment", "layer": "proxy", "label": "Apache" },
      "haproxy": { "type": "k8s-deployment", "layer": "proxy", "label": "HAProxy" },
      "hybris-fo": { "type": "k8s-deployment", "layer": "application", "label": "Hybris FO" },
      "hybris-bo": { "type": "k8s-deployment", "layer": "application", "label": "Hybris BO", "group": "backoffice" },
      "solr-follower": { "type": "k8s-statefulset", "layer": "search", "label": "Solr Follower" },
      "solr-leader": { "type": "k8s-statefulset", "layer": "search", "label": "Solr Leader", "group": "backoffice" },
      "aurora": { "type": "rds", "layer": "data", "label": "Aurora" },
      "efs": { "type": "efs", "layer": "data", "label": "EFS" }
    },
    "connections": [
      { "from": "cloudfront", "to": "alb", "protocol": "https" },
      { "from": "alb", "to": "nextjs", "protocol": "http" },
      { "from": "nextjs", "to": "apache", "protocol": "http" },
      { "from": "apache", "to": "haproxy", "protocol": "http" },
      { "from": "haproxy", "to": "hybris-fo", "protocol": "http" },
      { "from": "hybris-fo", "to": "solr-follower", "protocol": "solr" },
      { "from": "hybris-fo", "to": "aurora", "protocol": "jdbc" },
      { "from": "hybris-fo", "to": "efs", "protocol": "nfs" }
    ],
    "layers": ["edge", "ingress", "frontend", "proxy", "application", "search", "data"]
  }
}
```

### Placement

The `topology` section can be placed at:

1. **Project level** - applies to all environments of the project
2. **Environment level** - overrides project-level topology for a specific environment

```json
{
  "projects": {
    "myproject": {
      "topology": { /* project-level */ },
      "environments": {
        "staging": {
          "topology": { /* environment-level override */ }
        }
      }
    }
  }
}
```

---

## NAMING_PATTERN Configuration

Customize resource naming conventions. Supports placeholders: `{project}`, `{env}`, `{service}`.

### Schema

```json
{
  "cluster": "{project}-{env}",
  "service": "{project}-{env}-{service}",
  "task_family": "{project}-{env}-{service}",
  "build_pipeline": "{project}-build-{service}",
  "deploy_pipeline": "{project}-deploy-{service}-{env}",
  "log_group": "/ecs/{project}-{env}/{service}",
  "secret": "{project}/{env}/{service}",
  "ecr_repo": "{project}-{service}",
  "db_identifier": "{project}-{env}"
}
```

All patterns are optional; defaults are shown above.

---

## CI_PROVIDER Configuration

### CodePipeline (default)

```json
{
  "type": "codepipeline"
}
```

### GitHub Actions

```json
{
  "type": "github_actions",
  "config": {
    "owner": "my-org",
    "repo_pattern": "{project}-{service}",
    "token_secret": "arn:aws:secretsmanager:region:account:secret:github-token"
  }
}
```

### Bitbucket Pipelines

```json
{
  "type": "bitbucket",
  "config": {
    "workspace": "my-workspace"
  }
}
```

### ArgoCD

```json
{
  "type": "argocd",
  "config": {
    "api_url": "https://argocd.example.com",
    "token_secret": "arn:aws:secretsmanager:region:account:secret:argocd-token"
  }
}
```

---

## ORCHESTRATOR Configuration

### ECS (default)

```json
{
  "type": "ecs"
}
```

### EKS

```json
{
  "type": "eks",
  "config": {
    "cluster_name": "optional-default-cluster",
    "namespace": "default"
  }
}
```

---

## Per-Project Pipelines Configuration (v2.x)

Since v2.x, pipelines are configured per-project with support for multiple providers.

### Schema

```json
{
  "projects": {
    "my-project": {
      "pipelines": {
        "enabled": true,
        "providers": [
          {
            "type": "codepipeline",
            "category": "build",
            "accountId": "123456789012",
            "region": "eu-west-3",
            "services": ["frontend", "backend"],
            "displayName": "CodePipeline (shared-services)"
          }
        ]
      }
    }
  }
}
```

### Provider Types

| Type | Description | Required Fields |
|------|-------------|-----------------|
| `codepipeline` | AWS CodePipeline | `accountId`, `region`, `services` |
| `azure-devops` | Azure DevOps Pipelines | `organization`, `project`, `services` |
| `github-actions` | GitHub Actions | `owner`, `services` |
| `bitbucket` | Bitbucket Pipelines | `workspace`, `services` |
| `argocd` | ArgoCD (GitOps) | `url`, `services` |
| `jenkins` | Jenkins CI | `url`, `services` |

### Categories

| Category | Description |
|----------|-------------|
| `build` | Build/CI pipelines (shown in Build Pipelines section) |
| `deploy` | Deployment pipelines (GitOps, CD) |
| `both` | Combined build and deploy |

### Examples

#### CodePipeline (AWS)

```json
{
  "pipelines": {
    "enabled": true,
    "providers": [
      {
        "type": "codepipeline",
        "category": "build",
        "accountId": "501994300510",
        "region": "eu-west-3",
        "services": ["frontend", "backend", "cms"],
        "displayName": "CodePipeline"
      }
    ]
  }
}
```

#### Azure DevOps

```json
{
  "pipelines": {
    "enabled": true,
    "providers": [
      {
        "type": "azure-devops",
        "category": "build",
        "organization": "my-org",
        "project": "MyProject",
        "services": ["api", "worker"],
        "pipelinePattern": "{service}-build"
      }
    ]
  }
}
```

#### Multiple Providers

```json
{
  "pipelines": {
    "enabled": true,
    "providers": [
      {
        "type": "codepipeline",
        "category": "build",
        "accountId": "123456789012",
        "region": "eu-west-3",
        "services": ["frontend", "backend"]
      },
      {
        "type": "argocd",
        "category": "deploy",
        "url": "https://argocd.example.com",
        "services": ["frontend", "backend"],
        "appPattern": "{service}-{env}"
      }
    ]
  }
}
```

#### Disabled Pipelines

```json
{
  "pipelines": {
    "enabled": false
  }
}
```

---

## Complete Example

```bash
export AWS_REGION_DEFAULT="eu-central-1"
export SHARED_SERVICES_ACCOUNT="999999999999"
export SSO_PORTAL_URL="https://my-sso.awsapps.com/start"

export PROJECTS='{
  "webshop": {
    "displayName": "Webshop Platform",
    "environments": {
      "int": {
        "accountId": "111111111111",
        "services": ["frontend", "backend"]
      },
      "stg": {
        "accountId": "222222222222",
        "services": ["frontend", "backend"]
      },
      "prd": {
        "accountId": "333333333333",
        "services": ["frontend", "backend"]
      }
    }
  }
}'

export CROSS_ACCOUNT_ROLES='{
  "111111111111": {
    "readRoleArn": "arn:aws:iam::111111111111:role/DashboardReadRole",
    "actionRoleArn": "arn:aws:iam::111111111111:role/DashboardActionRole"
  },
  "222222222222": {
    "readRoleArn": "arn:aws:iam::222222222222:role/DashboardReadRole",
    "actionRoleArn": "arn:aws:iam::222222222222:role/DashboardActionRole"
  },
  "333333333333": {
    "readRoleArn": "arn:aws:iam::333333333333:role/DashboardReadRole",
    "actionRoleArn": "arn:aws:iam::333333333333:role/DashboardActionRole"
  }
}'

export ORCHESTRATOR='{"type": "ecs"}'
export CI_PROVIDER='{"type": "codepipeline"}'
```

---

## SST Configuration

Configuration is managed via `infra.config.json`:

```json
{
  "mode": "managed",

  "ssm": {
    "prefix": "/dashborion/myapp"
  },

  "aws": {
    "region": "eu-central-1",
    "profile": "my-aws-profile"
  },

  "projects": {
    "myproject": {
      "displayName": "My Project",
      "environments": {
        "staging": {
          "accountId": "111111111111",
          "region": "eu-central-1",
          "services": ["frontend", "backend"]
        }
      }
    }
  },

  "crossAccountRoles": {
    "111111111111": {
      "readRoleArn": "arn:aws:iam::111111111111:role/DashboardReadRole",
      "actionRoleArn": "arn:aws:iam::111111111111:role/DashboardActionRole"
    }
  }
}
```

SST will automatically:
1. Create SSM parameters for each project under `{prefix}/projects/{project-id}`
2. Create SSM parameter for cross-account roles at `{prefix}/cross-account-roles`
3. Pass `CONFIG_SSM_PREFIX` to all Lambda environment variables
4. Add IAM permissions to read SSM parameters

### Deploying

```bash
# Set config directory (for external config)
export DASHBORION_CONFIG_DIR=/path/to/config

# Deploy
npx sst deploy --stage production
```

### Multiple Deployments

Each organization/deployment should use a unique SSM prefix. A single Dashborion deployment handles all projects and environments for that organization.

| Organization | SSM Prefix |
|--------------|------------|
| Org1 | `/dashborion/org1` |
| Org2 | `/dashborion/org2` |
| Demo | `/dashborion/demo` |
