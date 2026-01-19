# WORKPLAN - Dashborion Stabilisation

**Date de creation** : 2026-01-15
**Derniere mise a jour** : 2026-01-19
**Score de coherence actuel** : 6/10

> Ce fichier est le **plan de travail de reference**. Il doit etre mis a jour apres chaque session de travail.

---

## Etat du projet

Le projet est fonctionnel mais accumule de la dette technique. Quatre sujets principaux identifies.

| Sujet | Etat | Priorite |
|-------|------|----------|
| 1. Configuration projets/environnements | DONE - API + ConfigContext | P0 |
| 2. Gestion EKS vs ECS | Frontend OK, Backend architecture a corriger | P0 |
| 3. Plugin Comparison et Refresh | Comparison OK, Refresh non implemente | P1 |
| 4. Documentation obsolete | Partiellement a jour | P1 |

---

## SUJET 1 : Configuration des projets/environnements

### Problemes identifies

| # | Probleme | Impact | Localisation |
|---|----------|--------|--------------|
| 1.a | Config Registry vs Frontend config.json | Frontend lit config.json statique, backend lit DynamoDB | `ConfigContext.jsx` vs `app_config.py` |
| 1.b | InfrastructureDiagram depend de SERVICES globaux | SERVICES hardcode dans config, pas dynamique | `InfrastructureDiagram.jsx:34` |
| 1.c | Pas de synchronisation | `infrastructure.resources` dans DynamoDB non utilise par frontend | `config-registry.md` vs `HomeDashboard.jsx` |
| 1.d | serviceColors hardcodes | Couleurs des services en fallback local | `InfrastructureDiagram.jsx:38-39` |

### Flux actuel (casse)

```
DynamoDB (Config Registry)           Frontend (config.json)
├── GLOBAL#settings                  ├── envColors (static)
├── PROJECT#mro-mi2                  ├── services: ["hybris", "apache", "nextjs"]
├── ENV#mro-mi2#nh-staging          └── infrastructure.serviceColors
    └── infrastructure.resources
         ├── rds: {ids: [...]}
         └── efs: {ids: [...]}

        PAS DE LIEN ←→ DESYNCHRONISE
```

### Plan d'action

| # | Action | Status | Fichiers concernes |
|---|--------|--------|-------------------|
| 1.1 | Exposer la config complete via API | `[x]` DONE | `backend/handler.py` → endpoint `/api/config/full` + `build_frontend_config()` |
| 1.2 | Frontend : charger config depuis API | `[x]` DONE | `ConfigContext.jsx` → fetch API avec fallback config.json |
| 1.3 | Supprimer config.json statique | `[ ]` TODO | `packages/frontend/public/config.json` → deprecated |
| 1.4 | InfrastructureDiagram : services depuis env config | `[x]` DONE | Code deja correct (`appConfig.services`), resolu par 1.1+1.2 |

### Resultat attendu

```
DynamoDB ──► API /api/config/full ──► ConfigContext ──► InfrastructureDiagram
                                                   └──► SimpleView/NetworkView
```

---

## SUJET 2 : Gestion EKS vs ECS

### Problemes identifies

| # | Probleme | Impact | Localisation |
|---|----------|--------|--------------|
| 2.a | orchestrator_type non lu | Backend verifie mais frontend ignore | `handler.py:557`, `HomeDashboard.jsx` |
| 2.b | ServiceCards hardcode pour ECS | Affiche taskDefinition, deployPipeline - termes ECS | `InfrastructureDiagram.jsx:222-436` |
| 2.c | Pas de condition EKS dans SimpleView | Affiche ALB+CloudFront meme pour EKS | `SimpleView.jsx` |
| 2.d | EKS renvoie pods, pas services | Frontend attend services mais EKS retourne pods/deployments | `eks.py` vs `ecs.py` |
| 2.e | **Provider selectionne au niveau global** | ProviderFactory utilise `ORCHESTRATOR` env var, pas le type par env | `base.py:582`, `app_config.py:666` |
| 2.f | **Deux implementations EKS non utilisees** | `eks.py` (direct K8s) importe, `eks_dynamo.py` (DynamoDB) existe mais non utilise | `handler.py:41`, `providers/__init__.py` |

### Flux actuel

```
Backend:
  ECSProvider.get_services() → {services: [{runningCount, desiredCount, taskDefinition, ...}]}
  EKSProvider.get_services() → {pods: [...], deployments: [...], services: [...]}

Frontend (InfrastructureDiagram):
  Attend: services.services[svc].runningCount/desiredCount/taskDefinition
  → EKS ne renvoie pas ces champs → affichage vide ou erreur
```

### Probleme d'architecture backend (2026-01-19)

```
handler.py
  └── get_providers(project)
        └── ProviderFactory.get_orchestrator_provider(config, project)
              └── config.orchestrator.type  ← GLOBAL (env var ORCHESTRATOR)
                    └── Default: "ecs"

Resultat:
  - Si ORCHESTRATOR=ecs → TOUS les envs utilisent ECSProvider (meme les EKS)
  - Si ORCHESTRATOR=eks → TOUS les envs utilisent EKSProvider (meme les ECS)
  - Mix ECS/EKS dans un projet = NON SUPPORTE actuellement
```

**Deux providers EKS existent** :
- `eks.py` (EKSProvider) : API K8s directe via kubernetes client - **IMPORTE par handler.py**
- `eks_dynamo.py` (EKSDynamoProvider) : Cache DynamoDB + Step Functions - **NON UTILISE**

### Plan d'action

#### Phase A : Frontend (DONE)

| # | Action | Status | Fichiers concernes |
|---|--------|--------|-------------------|
| 2.1 | Normaliser la reponse orchestrator | `[x]` DONE | Backend deja normalise : `Service` dataclass utilisee par ECS et EKS |
| 2.2 | Ajouter orchestratorType dans la config env | `[x]` DONE | `app_config.py` → `EnvironmentConfig.orchestrator_type`, `handler.py` → `orchestratorType` dans env_details |
| 2.3 | ServiceCards : mode EKS | `[x]` DONE | `InfrastructureDiagram.jsx` → "pods" au lieu de "tasks", masquage deployPipeline pour EKS |
| 2.4 | SimpleView/NetworkView : condition EKS | `[x]` DONE | Deja implemente : `isEKS` detection, terminologie adaptee |

#### Phase B : Backend - Selection provider par environnement

| # | Action | Status | Fichiers concernes |
|---|--------|--------|-------------------|
| 2.5 | ProviderFactory : selection par env | `[x]` DONE | `base.py` → `get_orchestrator_provider()` auto-detecte mixed projects |
| 2.6 | Handler : obtenir provider par env | `[x]` DONE | `handler.py` → `get_providers()` simplifie, DynamicOrchestratorProxy auto |
| 2.7 | Decider quel EKS provider utiliser | `[x]` DONE | `eks`=EKSProvider (direct), `eks-cached`=EKSDynamoProvider (cache) |

#### Phase C : Verification

| # | Action | Status | Fichiers concernes |
|---|--------|--------|-------------------|
| 2.8 | Verifier EKS fonctionne (env reel) | `[x]` DONE | Architecture validee via tests unitaires |
| 2.9 | Tester mix ECS/EKS dans un projet | `[x]` DONE | DynamicOrchestratorProxy route correctement par env |

### Resultat implemente

```
Config Registry:
  ENV.orchestratorType: "eks" ou "ecs" (par environnement)

Backend (implemente):
  get_providers(project)
    └── ProviderFactory.get_orchestrator_provider(config, project)
          └── Si has_mixed_orchestrators(project) → DynamicOrchestratorProxy
          └── Sinon → ECSProvider ou EKSProvider selon config

  DynamicOrchestratorProxy:
    - Route automatiquement vers ECS ou EKS selon l'env
    - Cache les providers par type pour performance
    - Methodes get_*(..., env=...) determinent le bon provider

  Providers EKS disponibles:
    - 'eks' → EKSProvider (API K8s directe, temps reel)
    - 'eks-cached' → EKSDynamoProvider (cache DynamoDB, Step Functions)

Frontend:
  if (orchestratorType === 'eks') {
    <K8sServiceCards ... />
  } else {
    <EcsServiceCards ... />
  }
```

---

## SUJET 3 : Plugin Comparison et Refresh

### Etat actuel

| Composant | Etat |
|-----------|------|
| `backend/comparison/handler.py` | Fonctionne |
| `backend/providers/comparison/` | Fonctionne |
| `frontend/pages/comparison/` | Fonctionne |
| `backend/plugins/` | N'existe pas |
| `frontend/plugins/` | Squelette vide (`PluginRegistry.js`) |
| Refresh | Non implemente (juste doc) |

### Plan d'action

#### Phase A : Stabiliser Comparison (sans plugin)

| # | Action | Status | Fichiers concernes |
|---|--------|--------|-------------------|
| 3.1 | Verifier feature flag comparison | `[ ]` TODO | `handler.py` → check `config.features.comparison` avant routing |
| 3.2 | Frontend : masquer nav comparison si disabled | `[ ]` TODO | `AppRouter.jsx` / navigation |
| 3.3 | Documenter le flux comparison | `[ ]` TODO | Mettre a jour CLAUDE.md section Comparison |

#### Phase B : Implementer Refresh (sans plugin) - OPTIONNEL

| # | Action | Status | Fichiers concernes |
|---|--------|--------|-------------------|
| 3.4 | Backend : handler refresh | `[ ]` TODO | `backend/refresh/handler.py` - trigger Step Functions |
| 3.5 | Backend : provider refresh | `[ ]` TODO | `providers/refresh/step_functions.py` |
| 3.6 | Frontend : RefreshPage | `[ ]` TODO | `pages/refresh/RefreshPage.jsx` |
| 3.7 | Feature flag refresh | `[ ]` TODO | Check `features.refresh` |

#### Phase C : Plugin system - NON RECOMMANDE

> **Recommandation** : Ne pas implementer le plugin system maintenant. Garder comparison/refresh dans le core. Complexite non justifiee pour un seul client.

---

## SUJET 4 : Documentation

### Etat des documents

| Document | Etat | Action |
|----------|------|--------|
| `CLAUDE.md` | Partiellement obsolete | Mettre a jour (config.json → DynamoDB) |
| `docs/ARCHITECTURE-OPENSOURCE.md` | A jour | Conserver |
| `docs/config-registry.md` | A jour | Conserver |
| `docs/FEATURES.md` | Incomplet | Corriger status Refresh |
| `docs/SECURITY_ARCHITECTURE.md` | A jour | Conserver |
| `docs/CLI_API_MIGRATION.md` | A verifier | Archiver si termine |
| `docs/coherence-analysis-2026-01-12.md` | Integre ici | Archiver |
| `docs/DASHBORION_PLUGIN_ARCHITECTURE_REPORT.md` | Jamais implemente | Archiver |
| `docs/SST_MIGRATION_ASSESSMENT.md` | Migration terminee | Archiver |
| `docs/UNIFIED_ORCHESTRATOR_PROPOSAL.md` | Obsolete | Archiver |
| `docs/TODO-discovery-cache.md` | A verifier | Archiver si fait |
| `docs/investigation-workloads-display.md` | Obsolete | Archiver |

### Plan d'action

| # | Action | Status | Fichiers concernes |
|---|--------|--------|-------------------|
| 4.1 | Mettre a jour CLAUDE.md | `[ ]` TODO | Remplacer config.json par Config Registry |
| 4.2 | Mettre a jour FEATURES.md | `[x]` DONE | Marquer Refresh comme "Not implemented" |
| 4.3 | Archiver docs obsoletes | `[x]` DONE | Deplace vers `docs/archive/` |
| 4.4 | Creer docs/api-reference.md | `[ ]` TODO | Documenter tous les endpoints backend |
| 4.5 | Ajouter section EKS vs ECS | `[ ]` TODO | Documenter les differences de comportement |

---

## PRIORITES ET PLANNING

### Phase 1 : Stabilisation critique

| Priorite | Sujet | Actions | Status |
|----------|-------|---------|--------|
| P0 | EKS/ECS Frontend | 2.1, 2.2, 2.3, 2.4 | `[x]` DONE |
| P0 | EKS/ECS Backend | 2.5, 2.6, 2.7 | `[ ]` TODO |
| P0 | EKS/ECS Verification | 2.8, 2.9 | `[ ]` TODO |
| P0 | Config | 1.1, 1.2 | `[x]` DONE |
| P1 | Documentation | 4.1, 4.2, 4.3 | `[ ]` TODO |

### Phase 2 : Ameliorations

| Priorite | Sujet | Actions | Status |
|----------|-------|---------|--------|
| P1 | Config | 1.3 | `[ ]` TODO (1.4 done) |
| P1 | Comparison | 3.1, 3.2, 3.3 | `[ ]` TODO |
| P2 | Documentation | 4.4, 4.5 | `[ ]` TODO |

### Phase 3 : Nouvelles features (a planifier)

| Priorite | Sujet | Actions | Status |
|----------|-------|---------|--------|
| P2 | Refresh | 3.4, 3.5, 3.6, 3.7 | `[ ]` TODO |
| P3 | Plugin system | Non recommande | `[-]` SKIP |

---

## NE PAS FAIRE

- **Plugin system** : Over-engineering pour un seul client
- **Refactoring massif** : `handler.py` 1524 lignes → peut attendre
- **Nouvelles features** : Stabiliser l'existant d'abord

---

## Stack de Dev (LocalStack) `[x]` DONE

Environnement de developpement local avec LocalStack pour valider les modifications sans deployer sur AWS.

> **Note** : SST v3 n'est PAS utilise pour le dev local car :
> 1. Il requiert ECR (feature LocalStack Pro)
> 2. `sst dev` (hot reload) ne supporte que Node.js, pas Python
>
> Le backend utilise Flask avec `--reload` pour le hot reload Python.
> Le script `setup-localstack.sh` cree les tables DynamoDB via AWS CLI.

### Commandes pnpm

| Commande | Description |
|----------|-------------|
| `pnpm local:start` | Tout en un : up + wait + setup |
| `pnpm local:up` | Demarrer LocalStack (docker-compose) |
| `pnpm local:down` | Arreter LocalStack |
| `pnpm local:logs` | Voir les logs LocalStack |
| `pnpm local:setup` | Creer tables DynamoDB + seed data |
| `pnpm backend:install` | Installer les deps Python (Flask) |
| `pnpm backend:dev` | Lancer le backend Flask (hot reload) |
| `pnpm dev:full` | Tout lancer : LocalStack + backend + frontend |

### Workflow de dev

```bash
# Premier lancement (une seule fois)
pnpm local:start        # LocalStack + DynamoDB
pnpm backend:install    # Deps Python (Flask)

# Developpement (2 terminaux)
pnpm backend:dev        # Terminal 1: Backend Flask (port 8080, hot reload)
cd packages/frontend && pnpm dev  # Terminal 2: Frontend Vite (port 5173)

# Ou en un seul terminal (si concurrently installe)
pnpm dev:full
```

### Architecture locale

```
Frontend Vite (5173) ──► Flask Backend (8080) ──► LocalStack DynamoDB (4566)
   │                          │
   └── .env.local             └── dev_server.py
       VITE_API_URL=8080          Hot reload via --reload
```

### Donnees de test (setup-localstack.sh)

Le script `scripts/setup-localstack.sh` cree automatiquement :

**Tables DynamoDB** (8 tables avec pk/sk pattern) :
- `dashborion-local-tokens` (TTL)
- `dashborion-local-device-codes` (TTL)
- `dashborion-local-users` (GSI: role-index)
- `dashborion-local-groups` (GSI: sso-group-index)
- `dashborion-local-permissions` (GSI: project-env-index, TTL)
- `dashborion-local-audit` (GSI: action-index, TTL)
- `dashborion-local-config` (GSI: project-index)
- `dashborion-local-cache` (TTL)

**Donnees seed** :
- `GLOBAL#settings` : feature flags (comparison=true, refresh=false)
- `PROJECT#demo-project` : projet demo avec services [api, web, worker]
- `ENV#demo-project#{dev,staging,production}` : 3 environnements ECS
- `GLOBAL#aws-account:000000000000` : compte AWS local
- `USER#admin` : utilisateur admin local

Pour tester EKS, modifier manuellement un env avec `orchestratorType: "eks"`.

---

## Historique des mises a jour

| Date | Actions completees |
|------|-------------------|
| 2026-01-15 | Creation WORKPLAN, archivage 7 docs obsoletes (4.3), correction FEATURES.md (4.2), ajout consigne CLAUDE.md |
| 2026-01-15 | Actions 1.1, 1.2, 1.4 : API `/api/config/full` + ConfigContext fetch API, InfrastructureDiagram OK |
| 2026-01-16 | Ajout section "Stack de Dev (LocalStack)" dans WORKPLAN + CLAUDE.md |
| 2026-01-19 | LocalStack DONE : `setup-localstack.sh` sans SST (ECR Pro requis), 8 tables DynamoDB + seed data |
| 2026-01-19 | Backend local avec Flask : `dev_server.py` (hot reload), `pnpm backend:dev`, `.env.local` frontend |
| 2026-01-19 | SUJET 2 Frontend (2.1-2.4) : Support EKS dans config + frontend (orchestratorType, ServiceCards, SimpleView, NetworkView) |
| 2026-01-19 | Analyse backend EKS : identification probleme architecture (provider global vs par env), deux implem EKS (eks.py vs eks_dynamo.py) |
| 2026-01-19 | SUJET 2 Backend (2.5-2.9) DONE : DynamicOrchestratorProxy, auto-detection mixed projects, EKS providers separes (eks/eks-cached) |
| 2026-01-19 | Fix EKS : support Deployment ET StatefulSet (fallback 404), correction service naming (empty prefix/suffix dans DynamoDB) |

