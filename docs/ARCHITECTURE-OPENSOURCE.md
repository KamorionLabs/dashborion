# Dashborion - Architecture Opensource

> Document de reference pour la restructuration de Dashborion en projet opensource.

## Vision

Dashborion est un dashboard d'operations pour monitorer et gerer des infrastructures cloud. L'objectif est de le rendre :
- **Modulaire** : Composants independants et extensibles
- **Distribuable** : Packages npm versiones
- **Configuration-driven** : Configuration declarative des projets et environnements
- **Extensible** : Plugins frontend pour widgets/pages, providers Python pour donnees

## Etat Actuel (2026-01-08)

### Packages Implementes

| Package | Status | Description |
|---------|--------|-------------|
| `@dashborion/core` | **Done** | Types, interfaces, configuration TypeScript |
| `@dashborion/frontend` | **Done** | React app avec systeme de plugins frontend |
| `@dashborion/auth` | **Done** | Lambda@Edge SAML/OIDC |
| `@dashborion/sst` | **Done** | SST Component Pulumi |
| `packages/backend` | **Done** | Backend Python (Lambda) avec providers |

### Systeme de Plugins Frontend

Le frontend utilise une architecture modulaire avec :
- **PluginRegistry** : Singleton pour enregistrer les plugins
- **PluginContext** : React Context pour acceder aux plugins
- **PluginRouter** : Router dynamique base sur react-router-dom
- **WidgetRenderer** : Rendu des widgets dans les pages

#### Plugins builtin

| Plugin | Routes | Description |
|--------|--------|-------------|
| `aws-ecs` | `/:project/:env/services/*` | Services ECS, tasks, logs |
| `aws-cicd` | `/:project/:env/pipelines/*` | CodePipeline, GitHub Actions |
| `aws-infra` | `/:project/:env/infrastructure/*` | ALB, RDS, ElastiCache |

### URLs Disponibles

```
/:project/:env                              # Dashboard
/:project/:env/services                     # Liste services ECS
/:project/:env/services/:service            # Detail service
/:project/:env/services/:service/logs       # Logs service
/:project/:env/services/:service/tasks      # Tasks service
/:project/:env/pipelines                    # Liste pipelines
/:project/:env/pipelines/:pipeline          # Detail pipeline
/:project/:env/infrastructure               # Vue infrastructure
/:project/:env/infrastructure/alb
/:project/:env/infrastructure/rds
/:project/:env/infrastructure/redis
/:project/:env/infrastructure/cloudfront
```

## Architecture Cible

### Packages NPM

```
@dashborion/sst              # SST Component principal
@dashborion/core             # Types, interfaces, SDK pour plugins
@dashborion/frontend         # React app (buildee dans @dashborion/sst)
@dashborion/auth             # Lambda@Edge handlers (SAML, OIDC)
packages/backend/            # Backend Python (Lambda)
```

### Structure du Monorepo

```
dashborion/
├── packages/
│   ├── core/                    # @dashborion/core
│   │   ├── src/
│   │   │   ├── types/           # Types TypeScript partages
│   │   │   ├── interfaces/      # Interfaces pour plugins
│   │   │   └── config/          # Schema de configuration
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   ├── frontend/                # @dashborion/frontend
│   │   ├── src/
│   │   │   ├── components/      # Composants React
│   │   │   ├── pages/           # Pages (Dashboard)
│   │   │   ├── hooks/           # React hooks
│   │   │   ├── shell/           # Shell layout (Header, Sidebar)
│   │   │   ├── plugins/         # Systeme de plugins frontend
│   │   │   │   ├── PluginRegistry.js
│   │   │   │   ├── PluginContext.jsx
│   │   │   │   ├── PluginRouter.jsx
│   │   │   │   ├── WidgetRenderer.jsx
│   │   │   │   └── builtin/     # Plugins integres
│   │   │   │       ├── aws-ecs/
│   │   │   │       ├── aws-cicd/
│   │   │   │       └── aws-infra/
│   │   │   └── api/             # Client API
│   │   ├── package.json
│   │   └── vite.config.ts
│   │
│   ├── backend/                 # Backend Python
│   │   ├── handler.py           # Lambda handler principal
│   │   ├── config.py            # Configuration
│   │   ├── auth/                # Auth handlers
│   │   ├── providers/           # Providers AWS
│   │   │   ├── orchestrator/    # ECS, EKS
│   │   │   ├── ci/              # CodePipeline, GitHub Actions
│   │   │   ├── infrastructure/  # ALB, RDS, ElastiCache, CloudFront
│   │   │   └── events/          # Combined events
│   │   └── utils/               # AWS utilities
│   │
│   ├── auth/                    # @dashborion/auth
│   │   ├── src/
│   │   │   ├── handlers/        # Lambda@Edge handlers
│   │   │   └── utils/           # SAML, crypto, cookies
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── sst/                     # @dashborion/sst
│       ├── src/
│       │   ├── Dashborion.ts    # SST Component principal
│       │   ├── types.ts         # Types SST
│       │   └── index.ts         # Exports
│       ├── package.json
│       └── tsconfig.json
│
├── cli/                         # CLI dashborion (optionnel)
│   └── dashborion/              # Package Python
│
├── examples/
│   └── myapp/                 # Exemple multi-account
│       ├── sst.config.ts
│       └── infra.config.json
│
├── docs/
│   └── ARCHITECTURE-OPENSOURCE.md
│
├── backend/                     # Backend source (symlink ou copie)
├── handler.py                   # Entry point Lambda
├── sst.config.ts                # Config SST principal
├── pnpm-workspace.yaml
├── turbo.json
└── package.json
```

## Architecture

### Flux de Configuration

```
┌─────────────────────────────────────────────────────────────────┐
│                     DashborionConfig                            │
│   (projects, environments, crossAccountRoles, features)         │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│   SST/Pulumi    │ │    Frontend     │ │    Backend (Python)     │
│                 │ │  (React + Vite) │ │      (Lambda)           │
│ - Domain/CDN    │ │                 │ │                         │
│ - Certificates  │ │ Plugins builtin:│ │ Providers:              │
│ - Lambda@Edge   │ │ - aws-ecs       │ │ - orchestrator/ecs.py   │
│ - API Gateway   │ │ - aws-cicd      │ │ - ci/codepipeline.py    │
│ - IAM Roles     │ │ - aws-infra     │ │ - infrastructure/rds.py │
│                 │ │                 │ │ - events/events.py      │
└─────────────────┘ └─────────────────┘ └─────────────────────────┘
```

## Interfaces et Types

### Configuration Principale (Actuelle)

```typescript
// @dashborion/core/src/config/types.ts

export type AuthProvider = 'saml' | 'oidc' | 'none';

export interface AuthConfig {
  provider: AuthProvider;
  saml?: { entityId: string; idpMetadataFile?: string; };
  oidc?: { issuer: string; clientId: string; clientSecret?: string; scopes?: string[]; };
  sessionTtlSeconds?: number;
  cookieDomain?: string;
}

export interface EnvironmentConfig {
  accountId: string;
  region: string;
  clusterName?: string;    // ECS cluster name
  eksClusterName?: string; // EKS cluster name
  namespace?: string;      // K8s namespace
  services?: string[];     // Service filter (optional)
  infrastructure?: InfrastructureConfig;
}

export interface InfrastructureResourceConfig {
  ids?: string[];
  tags?: Record<string, string>;
}

export interface InfrastructureConfig {
  defaultTags?: Record<string, string>;
  domainConfig?: { domains?: Record<string, string>; pattern?: string };
  resources?: Record<string, InfrastructureResourceConfig>;
}

export interface ProjectConfig {
  displayName: string;
  description?: string;
  environments: Record<string, EnvironmentConfig>;
  idpGroupMapping?: Record<string, string[]>;
}

export interface CrossAccountRole {
  readRoleArn: string;
  actionRoleArn?: string;
}

export interface FeatureFlags {
  ecs?: boolean;
  eks?: boolean;
  pipelines?: boolean;
  infrastructure?: boolean;
  events?: boolean;
  actions?: boolean;
}

/**
 * Configuration principale Dashborion
 * Partagee entre SST, Frontend et Backend
 */
export interface DashborionConfig {
  projects: Record<string, ProjectConfig>;
  crossAccountRoles: Record<string, CrossAccountRole>;
  sharedServicesAccount?: string;
  region?: string;
  ciProvider?: CiProviderConfig;
  orchestrator?: OrchestratorConfig;
  namingPatterns?: NamingPatterns;
  features?: FeatureFlags;
  theme?: ThemeConfig;
  ssoPortalUrl?: string;
  github?: { owner: string; defaultBranch?: string; };
}
```

### Interface Plugin Frontend (Actuelle)

```typescript
// @dashborion/core/src/interfaces/frontend-plugin.ts

export type WidgetPosition = 'dashboard' | 'service-detail' | 'sidebar' | 'header' | 'bottom-panel';

export interface WidgetProps {
  projectId: string;
  environment: string;
  config: Record<string, unknown>;
  refreshKey?: number;
  onNavigate?: (path: string) => void;
  onShowDetails?: (data: unknown) => void;
}

export interface FrontendWidget {
  id: string;
  name: string;
  component: ComponentType<WidgetProps>;
  positions: WidgetPosition[];
  defaultSize?: { width: number; height: number };
  priority?: number;
}

export interface FrontendPage {
  id: string;
  path: string;
  title: string;
  component: ComponentType<PageProps>;
  icon?: ComponentType<{ className?: string }>;
  showInNav?: boolean;
  navOrder?: number;
  parentId?: string;
}

/**
 * Definition d'un plugin frontend
 */
export interface FrontendPluginDefinition {
  id: string;
  name: string;
  version: string;
  widgets?: FrontendWidget[];
  pages?: FrontendPage[];
  detailPanels?: FrontendDetailPanel[];
  navItems?: NavItem[];
  initialize?: (config: Record<string, unknown>) => Promise<void>;
  cleanup?: () => Promise<void>;
}
```

### Types de Donnees (Actuel)

```typescript
// @dashborion/core/src/interfaces/plugin.ts

// Types pour les services (ECS/K8s)
export type ServiceStatus = 'running' | 'stopped' | 'pending' | 'failed' | 'unknown';
export type HealthStatus = 'healthy' | 'unhealthy' | 'unknown';

export interface Service {
  id: string;
  name: string;
  status: ServiceStatus;
  desiredCount?: number;
  runningCount?: number;
  healthStatus?: HealthStatus;
}

export interface ServiceDetails extends Service {
  clusterName?: string;
  taskDefinition?: TaskDefinition;
  tasks?: Task[];
  deployments?: Deployment[];
  events?: ServiceEvent[];
  metrics?: ServiceMetrics;
}

// Types pour les pipelines
export type PipelineStatus = 'Succeeded' | 'Failed' | 'InProgress' | 'Stopped' | 'Unknown';

export interface Pipeline {
  name: string;
  pipelineType: 'build' | 'deploy';
  service?: string;
  environment?: string;
  lastExecution?: PipelineExecution;
}

// Types pour l'infrastructure
export type InfraResourceType = 'alb' | 'targetGroup' | 'rds' | 'elasticache' | 'cloudfront' | 'vpc' | 'subnet';

export interface InfraResource {
  type: InfraResourceType;
  id: string;
  name: string;
  status?: string;
  details?: Record<string, unknown>;
}
```

## SST Component

### Usage (Actuel)

```typescript
// sst.config.ts

import { Dashborion } from '@dashborion/sst';

export default $config({
  app(input) {
    return {
      name: 'my-dashboard',
      home: 'aws',
    };
  },
  async run() {
    const dashboard = new Dashborion('Dashboard', {
      // Domaine du dashboard
      domain: 'dashboard.example.com',

      // Authentification SAML
      auth: {
        provider: 'saml',
        saml: {
          entityId: 'my-dashboard-sso',
        },
      },
      idpMetadataPath: './idp-metadata.xml',

      // Configuration Dashborion (projets, envs, features)
      config: {
        projects: {
          myapp: {
            displayName: 'My Application',
            environments: {
              staging: {
                accountId: '111111111111',
                region: 'eu-west-1',
                clusterName: 'myapp-staging',
              },
              production: {
                accountId: '222222222222',
                region: 'eu-west-1',
                clusterName: 'myapp-production',
              },
            },
          },
        },
        crossAccountRoles: {
          '111111111111': {
            readRoleArn: 'arn:aws:iam::111111111111:role/dashborion-read',
          },
          '222222222222': {
            readRoleArn: 'arn:aws:iam::222222222222:role/dashborion-read',
          },
        },
        features: {
          ecs: true,
          pipelines: true,
          infrastructure: true,
          events: true,
          actions: false, // Desactiver actions en prod
        },
        ssoPortalUrl: 'https://d-xxxxx.awsapps.com/start',
        github: {
          owner: 'myorg',
          defaultBranch: 'main',
        },
      },

      // Backend Python (optionnel, defauts fournis)
      backend: {
        codePath: './packages/backend',
        memorySize: 512,
        timeout: 30,
      },
    });

    return {
      url: dashboard.url,
      cloudfrontId: dashboard.cloudfrontId,
      apiUrl: dashboard.apiUrl,
    };
  },
});
```

### DashborionArgs (Types SST)

```typescript
// @dashborion/sst/src/types.ts

export interface DashborionArgs {
  domain: string;                    // Domaine du dashboard
  auth: AuthConfig;                  // Configuration authentification
  config: DashborionConfig;          // Configuration projets/envs
  mode?: DeploymentMode;             // 'standalone' | 'semi-managed' | 'managed'
  aws?: AwsConfig;                   // Region, profile
  external?: ExternalResources;      // Ressources externes (mode managed)
  backend?: BackendConfig;           // Config backend Python
  authLambda?: AuthLambdaConfig;     // Config Lambda@Edge auth
  frontendBuild?: FrontendBuildConfig; // Config build frontend
  idpMetadataPath?: string;          // Chemin vers metadata IDP (SAML)
}
```

### Architecture Deployee

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CloudFront                                 │
│                     (Custom domain + ACM cert)                         │
├─────────────────────────────────────────────────────────────────────────┤
│  Lambda@Edge (viewer-request)  │  Lambda@Edge (viewer-response)        │
│  - SAML authentication         │  - Security headers                   │
│  - Cookie validation           │  - Cache headers                      │
└─────────────────────────────────────────────────────────────────────────┘
                │                                  │
                ▼                                  ▼
┌───────────────────────────┐        ┌───────────────────────────────────┐
│       S3 Bucket           │        │       API Gateway                 │
│    (Frontend static)      │        │    (Backend proxy)                │
│                           │        │                                   │
│  - React SPA              │        │  /api/* → Lambda                  │
│  - Assets                 │        │                                   │
└───────────────────────────┘        └───────────────────────────────────┘
                                                   │
                                                   ▼
                                     ┌───────────────────────────────────┐
                                     │       Lambda (Python)             │
                                     │                                   │
                                     │  DASHBORION_CONFIG env var        │
                                     │  - Projects/Environments          │
                                     │  - Cross-account roles            │
                                     │  - Feature flags                  │
                                     │                                   │
                                     │  Providers:                       │
                                     │  - ECS (services, tasks, logs)    │
                                     │  - CodePipeline                   │
                                     │  - RDS, ElastiCache, ALB          │
                                     └───────────────────────────────────┘
```

## Migration depuis l'etat actuel

### Phase 1 : Restructurer en monorepo - **DONE**

- [x] Initialiser pnpm workspace + turborepo
- [x] Deplacer le code existant dans packages/
- [x] Extraire les types dans @dashborion/core
- [x] Configurer les builds

### Phase 2 : Systeme de plugins frontend - **DONE**

- [x] Creer PluginRegistry et PluginContext
- [x] Creer PluginRouter avec react-router-dom
- [x] Creer plugins builtin (aws-ecs, aws-cicd, aws-infra)
- [x] Implementer le routing par URLs

### Phase 3 : SST Component - **DONE**

- [x] Creer @dashborion/sst avec Pulumi
- [x] Deploiement frontend (S3 + CloudFront)
- [x] Deploiement backend (Lambda + API Gateway)
- [x] Configuration declarative (DashborionConfig)
- [x] Support domaine custom + certificat ACM
- [x] Lambda@Edge pour auth (structure, implementation a finaliser)

### Phase 4 : Coherence globale - **DONE**

- [x] Restructurer @dashborion/core (config vs frontend-plugin)
- [x] Supprimer ancienne interface DashborionPlugin
- [x] Unifier les types de configuration
- [x] Mettre a jour la documentation

### Phase 5 : Publier sur npm (TODO)

1. Configurer changesets pour versioning
2. CI/CD pour publish automatique
3. Documentation README pour chaque package
4. Exemple myapp mis a jour

## Migration MyApp

Apres finalisation, myapp utilisera :

```
myapp-infra/stacks/dashborion/
├── sst.config.ts              # Utilise @dashborion/sst
├── idp-metadata/
│   └── dashboard.xml
├── terraform.tf               # Route53 (reste en Terraform)
├── route53.tf
└── outputs.tf
```

```typescript
// sst.config.ts
import { Dashborion } from '@dashborion/sst';

export default $config({
  app: () => ({ name: 'dashborion', home: 'aws' }),
  async run() {
    const dashboard = new Dashborion('MyApp', {
      domain: 'dashboard.myapp.example.cloud',

      auth: {
        provider: 'saml',
        saml: {
          entityId: 'myapp-dashboard-sso',
        },
      },
      idpMetadataPath: './idp-metadata/dashboard.xml',

      config: {
        projects: {
          myapp: {
            displayName: 'MyApp',
            environments: {
              staging: {
                accountId: '702125625526',
                region: 'eu-west-3',
                clusterName: 'myapp-staging',
              },
              preprod: {
                accountId: '...',
                region: 'eu-west-3',
                clusterName: 'myapp-preprod',
              },
              production: {
                accountId: '...',
                region: 'eu-west-3',
                clusterName: 'myapp-production',
              },
            },
          },
        },
        crossAccountRoles: {
          '702125625526': {
            readRoleArn: 'arn:aws:iam::702125625526:role/myapp-dashboard-read',
          },
          // ... autres comptes
        },
        sharedServicesAccount: '501994300510',
        ciProvider: {
          type: 'codepipeline',
        },
        features: {
          ecs: true,
          pipelines: true,
          infrastructure: true,
          events: true,
          actions: true,
        },
        namingPatterns: {
          service: 'myapp-{env}-{service}-service',
          buildPipeline: 'myapp-{service}-pipeline',
          deployPipeline: 'myapp-deploy-{service}-pipeline',
        },
        ssoPortalUrl: 'https://d-806779789c.awsapps.com/start',
        github: {
          owner: 'example-org',
        },
      },
    });

    return {
      url: dashboard.url,
      cloudfrontId: dashboard.cloudfrontId,
    };
  },
});
```

## Prochaines Etapes

### Court terme

1. **Finaliser Lambda@Edge auth** - Implementation complete SAML/OIDC
2. **Tests d'integration** - Deploiement test sur un compte AWS
3. **Migration MyApp** - Convertir la config existante

### Moyen terme

1. **Publier sur npm** - Packages @dashborion/*
2. **Documentation utilisateur** - README, exemples
3. **CI/CD** - GitHub Actions pour publish

### Long terme

1. **Plugins tiers** - Architecture pour plugins externes
2. **Support EKS** - Provider Kubernetes
3. **Support multi-cloud** - GCP, Azure

## Questions Ouvertes

1. **Registry** : npm public ou GitHub Packages ?
2. **License** : MIT, Apache 2.0, autre ?
3. **Plugins payants** : Prevoir une architecture pour plugins enterprise ?

## Decisions Prises

| Decision | Choix | Raison |
|----------|-------|--------|
| Nommage packages | `@dashborion/*` | Standard npm scoped |
| Backend | Python (Lambda) | Existant, fonctionne bien |
| Frontend plugins | React builtin | Simplicite, pas de dynamic import |
| Configuration | Declarative YAML/JSON | Familier pour DevOps |
| Authentification | SAML/OIDC via Lambda@Edge | Integration enterprise |

---

*Document cree le 2026-01-07*
*Derniere mise a jour : 2026-01-08*
