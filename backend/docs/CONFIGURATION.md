# Dashborion Configuration Reference

Configuration is loaded from environment variables as JSON strings.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AWS_REGION_DEFAULT` | No | Default AWS region (default: `eu-west-3`) |
| `SHARED_SERVICES_ACCOUNT` | Yes | AWS account ID for shared services (ECR, etc.) |
| `SSO_PORTAL_URL` | Yes | AWS SSO portal URL for console links |
| `PROJECTS` | Yes | JSON object defining projects and environments |
| `CROSS_ACCOUNT_ROLES` | Yes | JSON object mapping account IDs to IAM roles |
| `NAMING_PATTERN` | No | JSON object for resource naming patterns |
| `CI_PROVIDER` | No | JSON object for CI/CD provider config |
| `ORCHESTRATOR` | No | JSON object for container orchestrator config |
| `GITHUB_ORG` | No | GitHub organization for commit links |

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

In SST, these are typically set in `sst.config.ts`:

```typescript
const config = {
  region: "eu-central-1",
  sharedServicesAccount: "999999999999",
  ssoPortalUrl: "https://my-sso.awsapps.com/start",
  projects: { /* ... */ },
  crossAccountRoles: { /* ... */ }
};

// Pass to Lambda
new Function(stack, "ApiHandler", {
  environment: {
    AWS_REGION_DEFAULT: config.region,
    SHARED_SERVICES_ACCOUNT: config.sharedServicesAccount,
    SSO_PORTAL_URL: config.ssoPortalUrl,
    PROJECTS: JSON.stringify(config.projects),
    CROSS_ACCOUNT_ROLES: JSON.stringify(config.crossAccountRoles),
    // ...
  }
});
```
