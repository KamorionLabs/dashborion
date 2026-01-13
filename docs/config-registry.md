# Specification : Config Registry

**Date** : 2026-01-12
**Status** : Implemented
**Version** : 2.1
**Location** : dashborion (opensource)

---

## 1. Contexte

Le Config Registry fait partie de **Dashborion** (pas de terraform-aws-ops).

C'est la source de verite pour :
- Projects et environments
- Clusters EKS
- Accounts AWS (cross-account roles)
- Feature flags
- Comparison groups
- Checkers params

**terraform-aws-ops** lit cette config via une Lambda `resolve-config`.

---

## 2. Ce qui reste dans infra.config.json

Le fichier `infra.config.json` ne garde que les **settings de bootstrap** necessaires au deploiement SST :

```json
{
  "mode": "standalone | semi-managed | managed",

  "aws": {
    "region": "eu-central-1",
    "profile": "my-profile"
  },

  "managed": {
    "lambda": {
      "roleArn": "arn:aws:iam::xxx:role/existing-role",
      "securityGroupIds": ["sg-xxx"],
      "subnetIds": ["subnet-xxx"]
    }
  },

  "frontend": {
    "s3Bucket": "existing-bucket",
    "cloudfrontDistributionId": "EXXX",
    "cloudfrontDomain": "dashboard.example.com",
    "certificateArn": "arn:aws:acm:...",
    "originAccessControlId": "EXXX"
  },

  "apiGateway": {
    "domain": "api.example.com",
    "route53ZoneId": "ZXXX"
  },

  "auth": {
    "provider": "saml | oidc | simple | none",
    "saml": {
      "entityId": "my-dashboard",
      "idpMetadataFile": "idp-metadata/my-idp.xml"
    },
    "kmsKeyArn": "arn:aws:kms:xxx:key/xxx",
    "sessionTtlSeconds": 28800,
    "cookieDomain": ".example.com"
  },

  "configRegistry": {
    "tableName": "dashborion-{stage}-config"
  },

  "opsIntegration": {
    "provider": "terraform-aws-ops",
    "accountId": "025922408720",
    "stateTableName": "ops-dashboard-state",
    "stepFunctionPrefix": "ops-dashboard"
  },

  "naming": {
    "convention": "custom",
    "app": "dashborion",
    "owner": "ops",
    "prefixes": {
      "lambda": "fct",
      "table": "ddb",
      "api": "api"
    }
  },

  "tags": {
    "rubix_Application": "dashborion",
    "rubix_Owner": "DevOps"
  }
}
```

> **Note** : SST cree toujours la table DynamoDB Config Registry. Plus de fallback SSM.

---

## 3. Ce qui va dans DynamoDB (Config Registry)

### 3.1 Table

**Table:** `dashborion-{stage}-config`

Creee par SST dans dashborion (packages/api ou infra/).

### 3.2 Schema

| pk | sk | Description |
|----|-----|-------------|
| `GLOBAL` | `settings` | Feature flags, comparison groups |
| `GLOBAL` | `cluster:{clusterId}` | Cluster EKS |
| `GLOBAL` | `aws-account:{accountId}` | AWS Account + roles |
| `PROJECT` | `{projectId}` | Project definition |
| `ENV` | `{projectId}#{envId}` | Environment config |

### 3.3 Item: GLOBAL#settings

```json
{
  "pk": "GLOBAL",
  "sk": "settings",
  "features": {
    "pipelines": true,
    "comparison": true,
    "refresh": true,
    "admin": true
  },
  "comparison": {
    "groups": [
      { "prefix": "legacy-", "label": "Legacy", "role": "source" },
      { "prefix": "nh-", "label": "New Horizon", "role": "destination" }
    ],
    "refreshThresholdSeconds": 300
  },
  "updatedAt": "2026-01-12T10:00:00Z",
  "updatedBy": "admin@example.com",
  "version": 1
}
```

### 3.4 Item: GLOBAL#cluster:{clusterId}

```json
{
  "pk": "GLOBAL",
  "sk": "cluster:nh-staging",
  "clusterId": "nh-staging",
  "name": "k8s-dig-stg-webshop",
  "displayName": "NH Staging",
  "region": "eu-central-1",
  "accountId": "281127105461",
  "version": "1.29",
  "updatedAt": "2026-01-12T10:00:00Z",
  "updatedBy": "admin@example.com"
}
```

### 3.5 Item: GLOBAL#aws-account:{accountId}

```json
{
  "pk": "GLOBAL",
  "sk": "aws-account:281127105461",
  "accountId": "281127105461",
  "displayName": "NH Staging",
  "readRoleArn": "arn:aws:iam::281127105461:role/iam-dig-stg-dashboard-read",
  "actionRoleArn": "arn:aws:iam::281127105461:role/iam-dig-stg-dashboard-write",
  "defaultRegion": "eu-central-1",
  "updatedAt": "2026-01-12T10:00:00Z",
  "updatedBy": "admin@example.com"
}
```

### 3.6 Item: PROJECT#{projectId}

```json
{
  "pk": "PROJECT",
  "sk": "mro-mi2",
  "projectId": "mro-mi2",
  "displayName": "DIG MRO MI2",
  "description": "MRO MI2 - Orexad France",
  "status": "active",
  "idpGroupMapping": {
    "mro-mi2-admins": { "role": "admin", "environment": "*" },
    "mro-mi2-viewers": { "role": "viewer", "environment": "*" }
  },
  "features": {
    "pipelines": true,
    "comparison": true
  },
  "pipelines": {
    "enabled": true,
    "providers": [
      {
        "type": "azure-devops",
        "category": "both",
        "organization": "rubix-group",
        "project": "NewHorizon-IaC",
        "services": ["hybris", "apache", "nextjs"]
      }
    ]
  },
  "topology": { ... },
  "updatedAt": "2026-01-12T10:00:00Z",
  "updatedBy": "admin@example.com",
  "version": 1
}
```

### 3.7 Item: ENV#{projectId}#{envId}

```json
{
  "pk": "ENV",
  "sk": "mro-mi2#nh-staging",
  "projectId": "mro-mi2",
  "envId": "nh-staging",
  "displayName": "NH Staging",

  "accountId": "281127105461",
  "region": "eu-central-1",

  "kubernetes": {
    "clusterId": "nh-staging",
    "clusterName": "k8s-dig-stg-webshop",
    "namespace": "rubix-mro-mi2-staging"
  },

  "readRoleArn": null,
  "actionRoleArn": null,

  "status": "deployed",
  "enabled": true,

  "checkers": {
    "secretProviderType": "external-secrets",
    "secretPatterns": ["/digital/stg/app/mro-mi2/*"],

    "ssmPathPrefixes": ["/digital/stg/"],
    "smSecretPatterns": ["/digital/stg/app/mro-mi2/*", "/digital/stg/infra/*"],

    "hostedZoneId": "Z0958769182PISZL4XPF8",
    "dnsDomainsSource": {
      "type": "tfvars",
      "repository": "NewHorizon-IaC-Webshop",
      "project": "NewHorizon-IaC",
      "branch": "master",
      "cloudfrontPath": "stacks/cloudfront/env/stg/terraform.tfvars",
      "eksPath": "stacks/eks/env/stg/terraform.tfvars"
    },

    "albTags": {
      "rubix_Environment": "stg",
      "rubix_Application": "webshop-mi2"
    },
    "cloudfrontTags": {
      "rubix_Environment": "stg"
    },
    "sgTags": {
      "rubix_Environment": "stg"
    },

    "rdsClusterIdentifier": "rds-dig-stg-mro-mi2",
    "efsFileSystemId": "fs-xxx",

    "applicationComponents": [
      {
        "name": "hybris",
        "podSelector": "app=hybris",
        "healthChecks": ["solr", "db", "startup"]
      }
    ]
  },

  "discoveryTags": {
    "rubix_Environment": "stg",
    "rubix_Application": "webshop-mi2"
  },

  "databases": ["aurora-mysql"],

  "updatedAt": "2026-01-12T10:00:00Z",
  "updatedBy": "admin@example.com",
  "version": 1
}
```

---

## 4. API Endpoints (dans Dashborion)

### 4.1 Settings

```
GET  /api/config/settings
PUT  /api/config/settings
```

### 4.2 Projects

```
GET    /api/config/projects
GET    /api/config/projects/:projectId
POST   /api/config/projects
PUT    /api/config/projects/:projectId
DELETE /api/config/projects/:projectId
```

### 4.3 Environments

```
GET    /api/config/projects/:projectId/environments
GET    /api/config/projects/:projectId/environments/:envId
POST   /api/config/projects/:projectId/environments
PUT    /api/config/projects/:projectId/environments/:envId
DELETE /api/config/projects/:projectId/environments/:envId
PATCH  /api/config/projects/:projectId/environments/:envId/checkers
```

### 4.4 Clusters

```
GET    /api/config/clusters
GET    /api/config/clusters/:clusterId
POST   /api/config/clusters
PUT    /api/config/clusters/:clusterId
DELETE /api/config/clusters/:clusterId
```

### 4.5 AWS Accounts

```
GET    /api/config/aws-accounts
GET    /api/config/aws-accounts/:accountId
POST   /api/config/aws-accounts
PUT    /api/config/aws-accounts/:accountId
DELETE /api/config/aws-accounts/:accountId
```

### 4.6 Import/Export

```
GET  /api/config/export                    # Export complet JSON
POST /api/config/import                    # Import JSON (merge ou replace)
POST /api/config/validate                  # Valide sans sauvegarder
POST /api/config/migrate-from-json         # Migration depuis infra.config.json
```

### 4.7 Resolution (pour terraform-aws-ops)

```
GET /api/config/resolve/:projectId/:envId  # Retourne config complete pour checkers
```

---

## 5. Implementation dans Dashborion

### 5.1 Table DynamoDB (SST)

```typescript
// infra/dynamodb.ts
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";

export function createConfigTable(stack: Stack, naming: NamingService, tags: Record<string, string>) {
  // SST cree toujours la table
  return new dynamodb.Table(stack, "ConfigTable", {
    tableName: naming.dynamoTable("config"),
    partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
    sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
    billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
  });
}
```

### 5.2 API Routes (SST)

```typescript
// infra/api.ts
api.route("GET /api/config/settings", "packages/api/src/config/settings.get");
api.route("PUT /api/config/settings", "packages/api/src/config/settings.put");

api.route("GET /api/config/projects", "packages/api/src/config/projects.list");
api.route("GET /api/config/projects/{projectId}", "packages/api/src/config/projects.get");
api.route("POST /api/config/projects", "packages/api/src/config/projects.create");
api.route("PUT /api/config/projects/{projectId}", "packages/api/src/config/projects.update");
api.route("DELETE /api/config/projects/{projectId}", "packages/api/src/config/projects.delete");

// ... etc
```

### 5.3 Config Loader (DynamoDB only)

```python
# backend/app_config.py

def get_config() -> DashborionConfig:
    """Load config from DynamoDB. Raises ConfigNotInitializedError if not available."""
    table_name = os.environ.get('CONFIG_TABLE_NAME')
    if not table_name:
        raise ConfigNotInitializedError("CONFIG_TABLE_NAME not set")

    return load_from_dynamodb(table_name)
```

> **Note** : Plus de fallback JSON/SSM. DynamoDB est la seule source de config runtime.

---

## 6. Migration

### 6.1 CLI Command

```bash
dashborion config migrate \
  --from ./infra.config.json \
  --table dashborion-rubix-config \
  --dry-run

dashborion config migrate \
  --from ./infra.config.json \
  --table dashborion-rubix-config \
  --confirm
```

### 6.2 Mapping

| infra.config.json | DynamoDB |
|-------------------|----------|
| `projects.{id}` | `PROJECT#{id}` |
| `projects.{id}.environments.{env}` | `ENV#{id}#{env}` |
| `crossAccountRoles.{accountId}` | `GLOBAL#aws-account:{accountId}` |
| `features`, `comparison` | `GLOBAL#settings` |

### 6.3 Ce qui n'est PAS migre (reste dans JSON)

- `mode`
- `aws`
- `managed.lambda`
- `frontend`
- `apiGateway`
- `auth` (provider, idpMetadataFile, kmsKeyArn)
- `naming`
- `tags`
- `configRegistry`
- `opsIntegration`

---

## 7. Frontend Admin UI

Voir `architecture-vision.md` section 6.

---

## 8. Status Implementation

### Complete
- [x] Table DynamoDB config creee dans SST
- [x] API handlers /api/config/*
- [x] Config loader DynamoDB-only
- [x] CLI migration (`dashborion config migrate`)
- [x] Rubix migre (7 projects, 48 envs, 8 clusters, 5 accounts)
- [x] Homebox migre (2 projects, 5 envs, 3 accounts)

### A venir (Phase 2-3)
- [ ] Frontend Admin UI (voir architecture-vision.md)
- [ ] Lambda resolve-config dans terraform-aws-ops
