# Rapport - Architecture plugins Dashborion

## 1. Analyse du besoin

### Contexte
- Un **core unique** livre via **SST** (backend + frontend + loaders + contrats).
- **Terraform** reste utilise pour creer des ressources dediees (modes `managed` / `semi-managed` conserves).
- **Config Registry DynamoDB** est la **seule source de verite** (pas de fallback JSON).
- Les clients doivent pouvoir **etendre Dashborion** facilement, tout en **beneficiant des updates du core**.

### Exigences
- **Plugins full-stack** (backend + frontend) avec un **meme pluginId**.
- **Activation par projet** (project-level) via Config Registry.
- **Auto-discovery** + **feature flipping** via config.
- Plugins **publics ou prives**.
- Plugins cibles initiaux :
  - `aws-ops-comparison` (lie a `terraform-aws-ops`)
  - futur `aws-ops-refresh` (meme depot `terraform-aws-ops`)
- Repo client deploiement + plugin : `rubix/NewHorizon-IaC-AWS-Dasboard`.

### Enjeux
- Assurer la **compatibilite ascendante** lors des mises a jour du core.
- Eviter les forks et limiter la dette technique.
- Avoir un systeme d’extension **simple, declaratif et versionne**.

---

## 2. Architecture generale proposee

### Vue d’ensemble
- **Core** fournit :
  - Registre de plugins, loader backend/frontend, contrats, validation.
  - Plugins builtin (aws-ecs/infra/cicd) traites comme plugins standards.
- **Plugins clients** se chargent automatiquement si installes et actives.

### Activation effective (par projet)
- Resolution :
  1. `PROJECT.plugins.enabled/disabled`
  2. Defaults core (builtins)
- Le frontend obtient la **liste resolue** et la **config par plugin**.

---

## 3. Structure des fichiers (cible)

### Core (dans le repo Dashborion)
```
dashborion/
  backend/
    plugins/
      __init__.py
      loader.py           # auto-discovery + resolution config
      registry.py         # registre runtime
      interfaces.py       # contrats plugin backend
  packages/
    core/
      src/plugins/        # types partages, schema config plugins
    frontend/
      src/plugins/
        loader.ts         # auto-discovery frontend
        registry.ts       # registre runtime
        builtin/          # plugins builtin
  docs/
    DASHBORION_PLUGIN_ARCHITECTURE_REPORT.md
```

### Plugin full-stack (ex: repo terraform-aws-ops)
```
terraform-aws-ops/
  dashborion_plugins/
    aws_ops_comparison/
      __init__.py
      plugin.py
  frontend/
    aws-ops-comparison/
      index.ts
      routes.ts
      widgets.ts
  package.json
  pyproject.toml
```

### Repo client deploiement (ex: rubix/NewHorizon-IaC-AWS-Dasboard)
```
NewHorizon-IaC-AWS-Dasboard/
  dashborion/
    package.json          # dependances npm plugins
    requirements.txt      # dependances pip plugins
    infra.config.json     # bootstrap infra SST
```

---

## 4. Interfaces (contrats)

### 4.1 Backend plugin (Python)
```python
# backend/plugins/interfaces.py
from typing import Protocol

class BackendPlugin(Protocol):
    id: str
    api_version: str

    def register_routes(self, router, services) -> None:
        ...

    def register_actions(self, actions) -> None:
        ...

    def register_permissions(self, permissions) -> None:
        ...
```

Exemple d’implementation :
```python
# dashborion_plugins/aws_ops_comparison/plugin.py
class AwsOpsComparisonPlugin:
    id = "aws-ops-comparison"
    api_version = "1.2"

    def register_routes(self, router, services):
        router.get("/api/{project}/comparison/config", services.get_config)
        router.get("/api/{project}/comparison/{source}/{dest}/summary", services.get_summary)

    def register_actions(self, actions):
        pass

    def register_permissions(self, permissions):
        permissions.register("comparison:read")
```

### 4.2 Frontend plugin (TypeScript)
```ts
// packages/core/src/plugins/types.ts
export interface FrontendPlugin {
  id: string;
  apiVersion: string;
  registerFrontend(ctx: PluginContext): void;
}
```

```ts
// frontend/aws-ops-comparison/index.ts
export const dashborionPlugin = {
  id: "aws-ops-comparison",
  apiVersion: "1.2",
  registerFrontend({ registry }) {
    registry.registerPage({
      id: "comparison",
      path: "/:project/comparison",
      title: "Comparison",
      component: ComparisonPage,
    });
  },
};
```

---

## 5. Auto-discovery + feature flipping

### Backend (Python)
- **Auto-discovery** via `entry_points` + scan dossier `dashborion_plugins/*`.
- **Resolution** via Config Registry (project-level) :
  - `plugins.enabled` / `plugins.disabled`
  - `plugins.config` par pluginId

### Frontend (Vite)
- **Auto-discovery** build-time : `import.meta.glob`.
- **Activation runtime** via liste resolue renvoyee par l’API.

---

## 6. Configuration (Config Registry)

Exemple dans `PROJECT#{projectId}` :
```json
{
  "plugins": {
    "enabled": ["aws-ecs", "aws-infra", "aws-ops-comparison"],
    "disabled": ["aws-cicd"],
    "config": {
      "aws-ops-comparison": {
        "accountId": "025922408720",
        "stateTableName": "ops-dashboard-state",
        "stepFunctionPrefix": "ops-dashboard",
        "region": "eu-central-1"
      }
    }
  }
}
```

---

## 7. API exposee au frontend

Deux options acceptables :

1) **`/api/plugins`** (recommande)
- Retourne la liste resolue + config par plugin pour un projet.

2) **`/api/config`**
- Injecte `plugins` directement dans la config globale.

Le choix peut rester ouvert tant que la resolution est cote backend.

---

## 8. Exemple plugin : aws-ops-comparison

### Backend
- Endpoints exposes :
  - `/api/{project}/comparison/config`
  - `/api/{project}/comparison/{source}/{dest}/summary`
  - `/api/{project}/comparison/{source}/{dest}/{checkType}`
- Source : DynamoDB `ops-dashboard-state` via config plugin.

### Frontend
- Page `/ :project /comparison`
- Widgets (resume, breakdown, cards)
- Config lue via `/api/plugins` ou `/api/config`.

---

## 9. Compatibilite et updates core
- `apiVersion` obligatoire cote plugin.
- Core accepte un range (`1.x`) et refuse les versions incompatibles.
- Plugins clients declarent `peerDependencies` sur `@dashborion/core`.

---

## 10. Decision
- **Core unique via SST**
- **Config Registry uniquement**
- **Plugins full-stack, activation par projet**
- **aws-ops-comparison** et **aws-ops-refresh** resides dans `terraform-aws-ops`

