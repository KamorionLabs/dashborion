# Dashborion Features

This document describes the feature flag system and optional features available in Dashborion.

## Feature Flags

Dashborion uses feature flags to enable/disable functionality at both global and project levels.

### Configuration

Features can be configured at two levels:

**Global level** (applies to all projects):
```json
{
  "features": {
    "pipelines": true,
    "comparison": true,
    "refresh": false
  }
}
```

**Project level** (overrides global for specific project):
```json
{
  "projects": {
    "my-project": {
      "features": {
        "comparison": false
      }
    }
  }
}
```

### Available Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `ecs` | `true` | Enable ECS container monitoring |
| `eks` | `true` | Enable EKS/Kubernetes monitoring |
| `pipelines` | `false` | Enable CI/CD pipeline views |
| `infrastructure` | `true` | Enable infrastructure diagrams (ALB, RDS, etc.) |
| `events` | `true` | Enable events timeline |
| `actions` | `false` | Enable operational actions (deploy, scale, etc.) |
| `comparison` | `false` | Enable environment comparison view (opt-in) |
| `refresh` | `false` | Enable refresh/migration operations view (NOT IMPLEMENTED) |

> **Note**: `comparison` is an **opt-in** feature - disabled by default.
> **Warning**: `refresh` is **not implemented** - the flag exists but the feature does not. See `docs/WORKPLAN.md`.

### Resolution Logic

For each feature, the effective value is determined using nullish coalescing (`??`):

```javascript
effectiveValue = projectFeatures.flag ?? globalFeatures.flag ?? defaultValue
```

1. Check project-level `features.{flag}` - if explicitly set (not `undefined`), use that value
2. Otherwise, check global `features.{flag}` - if explicitly set, use that value
3. Otherwise, use the default value (see table above)

---

## Environment Comparison Feature

The comparison feature allows comparing configurations and state between two environments (e.g., Legacy vs New Horizon, Staging vs Production).

### Enabling

```json
{
  "features": {
    "comparison": true
  }
}
```

### Routes

| Route | Description |
|-------|-------------|
| `/:project/comparison` | Comparison page with environment selectors |
| `/:project/comparison/:sourceEnv/:destEnv` | Comparison between specific environments |

### API Endpoints

```
GET /api/{project}/comparison/config
    Returns comparison configuration including available pairs

GET /api/{project}/comparison/{sourceEnv}/{destEnv}/summary
    Returns overall comparison summary with all check types

GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}
    Returns detailed comparison for a specific check type

GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}/history
    Returns historical comparison data
```

### Data Source

Comparison data is read from a DynamoDB table (configurable via `COMPARISON_TABLE` env var, defaults to `ops-dashboard-shared-state`).

The table schema expects:
- **Partition Key (pk)**: `{domain}#{target}` (e.g., `mro#mi2-ppd-comparison`)
- **Sort Key (sk)**: `check:{checkType}:current` (e.g., `check:k8s-pods-compare:current`)

### Check Types

Default comparison check types:

| Category | Check Type | Label |
|----------|------------|-------|
| **Kubernetes** | `k8s-pods-compare` | Pods |
| | `k8s-services-compare` | Services |
| | `k8s-ingress-compare` | Ingress |
| | `k8s-pvc-compare` | PVC |
| | `k8s-secrets-compare` | Secrets |
| **Configuration** | `config-sm-compare` | Secrets Manager |
| | `config-ssm-compare` | SSM Parameters |
| **Network** | `net-dns-compare` | DNS |
| | `net-alb-compare` | ALB |
| | `net-cloudfront-compare` | CloudFront |
| | `net-sg-compare` | Security Groups |

### Auto-detection of Comparison Pairs

When no explicit comparison configuration is provided, Dashborion auto-detects comparison pairs from environment names:

- Environments starting with `legacy-` are treated as source
- Environments starting with `nh-` are treated as destination
- Pairs are created for matching base environments (e.g., `legacy-preprod` + `nh-preprod`)

### Explicit Configuration (Optional)

For advanced use cases, you can explicitly configure comparison pairs in the project config:

```json
{
  "projects": {
    "my-project": {
      "comparison": {
        "enabled": true,
        "pairs": [
          {
            "id": "preprod-legacy-vs-nh",
            "label": "Preprod: Legacy vs NH",
            "source": {
              "env": "legacy-preprod",
              "label": "Legacy"
            },
            "destination": {
              "env": "nh-preprod",
              "label": "New Horizon"
            },
            "stateKey": {
              "domain": "mro",
              "target": "mi2-ppd-comparison",
              "tableName": "ops-dashboard-shared-state",
              "region": "eu-central-1"
            }
          }
        ]
      }
    }
  }
}
```

### UI Components

The comparison view includes:

1. **Environment Selectors**: Dropdown menus to select source and destination environments
2. **Quick Pair Buttons**: Shortcuts to configured comparison pairs
3. **Hero Summary**: Visual overview with:
   - Animated donut charts showing sync percentage for source/destination
   - Animated flow connector showing overall sync status
   - Category breakdown with progress bars
4. **Comparison Cards**: Grid of cards for each check type showing:
   - Sync status (synced/differs/critical/pending)
   - Progress bar
   - Source/destination counts
   - Synced/missing/differs breakdown

### Status Values

| Status | Description | Color |
|--------|-------------|-------|
| `synced` | All items match between source and destination | Green |
| `differs` | Some differences detected | Yellow |
| `critical` | Unexpected differences or errors | Red |
| `pending` | No data available yet | Gray |
| `error` | Error fetching comparison data | Red |

---

## Refresh Feature (NOT IMPLEMENTED)

> **Status**: Cette feature est documentee mais **n'est pas implementee**. Seule la specification existe.
> Voir `docs/WORKPLAN.md` pour le plan d'implementation eventuel (Phase 3, actions 3.4-3.7).

The refresh feature would allow triggering and monitoring migration/refresh operations.

### Enabling (quand implemente)

```json
{
  "features": {
    "refresh": true
  }
}
```

### Routes (specifiees, non implementees)

| Route | Description | Status |
|-------|-------------|--------|
| `/:project/refresh` | Refresh operations dashboard | NOT IMPLEMENTED |
| `/:project/refresh/:operation` | Specific operation details | NOT IMPLEMENTED |

### Capabilities (specifiees, non implementees)

- Trigger Step Function executions for refresh operations
- Monitor running operations
- View operation history
- Rollback capabilities

### Implementation Required

Pour implementer cette feature :
1. `backend/refresh/handler.py` - Handler API
2. `providers/refresh/step_functions.py` - Provider Step Functions
3. `frontend/pages/refresh/RefreshPage.jsx` - Page frontend
4. Feature flag check dans le routing

---

## Navigation

When multiple features are enabled, a navigation bar appears in the header with links to:

- **Dashboard**: Main infrastructure/services view
- **Comparison**: Environment comparison view (if `comparison: true`)
- **Refresh**: Refresh operations view (if `refresh: true`)

The navigation automatically adapts based on enabled features - if only Dashboard is available, no navigation is shown.

---

## Backend Provider

### DynamoDBComparisonProvider

The comparison backend uses a configurable DynamoDB provider:

```python
from providers.comparison import DynamoDBComparisonProvider

provider = DynamoDBComparisonProvider(
    table_name='ops-dashboard-shared-state',  # Optional, uses env var
    region='eu-central-1',                    # Optional, uses env var
    check_types=[...],                        # Optional, custom check types
    check_type_labels={...},                  # Optional, custom labels
    check_type_categories={...},              # Optional, custom grouping
)

# Get summary for all check types
summary = provider.get_comparison_summary(
    domain='mro',
    target='mi2-ppd-comparison',
    source_label='Legacy',
    destination_label='New Horizon',
)

# Get detail for specific check type
detail = provider.get_comparison_detail(
    domain='mro',
    target='mi2-ppd-comparison',
    check_type='k8s-pods-compare',
)

# Get history
history = provider.get_comparison_history(
    domain='mro',
    target='mi2-ppd-comparison',
    check_type='k8s-pods-compare',
    limit=50,
)
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPARISON_TABLE` | `ops-dashboard-shared-state` | DynamoDB table name |
| `OPS_DASHBOARD_TABLE` | `ops-dashboard-shared-state` | Fallback table name |
| `AWS_REGION` | `eu-central-1` | AWS region for DynamoDB |

---

## Frontend Components

### SyncStatusRing

Animated donut chart showing sync percentage:

```jsx
import { SyncStatusRing } from '../components/comparison';

<SyncStatusRing
  percentage={85}
  status="synced"  // synced | differs | critical | pending
  size={140}
  strokeWidth={10}
  label="Synced"
  sublabel="Legacy"
  animate={true}
/>
```

### SyncFlowConnector

Animated flow line between source and destination:

```jsx
import { SyncFlowConnector } from '../components/comparison';

<SyncFlowConnector
  status="synced"
  percentage={85}
  width={200}
  height={60}
  showPercentage={true}
  label="Migration progress"
/>
```

### ComparisonCard

Card showing comparison status for a check type:

```jsx
import { ComparisonCard } from '../components/comparison';

<ComparisonCard
  checkType="k8s-pods-compare"
  label="Pods"
  status="synced"
  sourceCount={15}
  destinationCount={15}
  syncedCount={14}
  differsCount={0}
  onlySourceCount={1}
  onlyDestinationCount={0}
  syncPercentage={93}
  lastUpdated="2025-01-11T10:30:00Z"
  sourceLabel="Legacy"
  destinationLabel="New Horizon"
  onClick={() => openDetail('k8s-pods-compare')}
/>
```

### HeroSummary

Overview section with donut charts and category breakdown:

```jsx
import { HeroSummary } from '../components/comparison';

<HeroSummary
  sourceLabel="Legacy"
  destinationLabel="New Horizon"
  overallStatus="differs"
  overallSyncPercentage={85}
  categories={{
    kubernetes: { total: 5, synced: 4 },
    configuration: { total: 2, synced: 2 },
    network: { total: 4, synced: 2 },
  }}
  lastUpdated="2025-01-11T10:30:00Z"
/>
```
