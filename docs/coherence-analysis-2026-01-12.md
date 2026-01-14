# Rapport d'analyse de cohérence - Dashborion Front/Back

**Date** : 2026-01-12
**Auteur** : Claude (analyse automatisée)
**Score de cohérence** : 6/10

---

## Résumé exécutif

Le projet est fonctionnel mais présente des problèmes structurels qui freinent la maintenabilité. Les deux points critiques identifiés :
1. L'endpoint `/api/{project}/infrastructure/{env}` est monolithique
2. Plusieurs fichiers dépassent 1000 lignes et nécessitent un découpage

---

## 1. Fichiers volumineux à découper

### Frontend (priorité haute)

| Fichier | Lignes | Problème | Recommandation |
|---------|--------|----------|----------------|
| `HomeDashboard.jsx` | **1446** | Orchestre TOUS les appels API (services, pipelines, images, infra, events) | Extraire en hooks : `useServices`, `useInfrastructure`, `usePipelines`, `useEvents` |
| `RoutingDetails.jsx` | **1406** | Mélange logique d'appel API + rendu | Séparer en `useRouting` hook + composants visuels |
| `ServiceDetailsPanel.jsx` | 808 | Acceptable mais dense | Extraire les sections metrics/logs en sous-composants |
| `RoutingView.jsx` | 757 | Redondance avec RoutingDetails | Fusionner ou partager la logique via hook |
| `ComparisonPage.jsx` | 647 | Logique de comparaison inline | Extraire en `useComparison` |

### Backend (priorité haute)

| Fichier | Lignes | Problème | Recommandation |
|---------|--------|----------|----------------|
| `providers/orchestrator/ecs.py` | **2002** | Provider ECS monolithique | Découper : `ecs_services.py`, `ecs_tasks.py`, `ecs_logs.py`, `ecs_metrics.py` |
| `handler.py` | **1524** | Routing centralisé avec if/elif géant | Router vers handlers spécialisés (pattern FastAPI/Flask blueprints) |
| `providers/orchestrator/eks.py` | **1478** | Même problème qu'ECS | Découper en modules (pods, nodes, deployments, ingress) |
| `providers/orchestrator/eks_dynamo.py` | 1157 | Cache DynamoDB EKS | Acceptable, logique cohérente |
| `auth/user_management.py` | 1004 | RBAC dense | Extraire : `permissions.py`, `audit.py`, `users.py` |

---

## 2. Analyse de l'endpoint Infrastructure

### Problème principal : endpoint monolithique

```
GET /api/{project}/infrastructure/{env}
```

Cet endpoint retourne **TOUT** en un seul appel :

```python
# InfrastructureAggregator (578 lignes)
return {
    'cloudfront': cdn_provider.get_distribution(),
    'alb': loadbalancer_provider.get_load_balancer(),
    'rds': database_provider.get_database_status(),
    'redis': cache_provider.get_cache_cluster(),
    'network': network_provider.get_network_info(),
    'workloads': orchestrator.get_services(),
    'efs': efs.describe_file_systems(),
    's3Buckets': s3.list_buckets()
}
```

### Conséquences

1. **Fragilité** : Si un provider timeout (ex: RDS cross-account) → tout l'appel échoue
2. **Performance** : Temps de réponse = max(tous les providers) au lieu de paralléliser côté client
3. **Gaspillage** : Frontend redessine tout même si seul CloudFront a changé
4. **Pas de cache granulaire** : Impossible d'invalider juste les données RDS

### Sub-endpoints existants (bonne pratique)

Le backend expose déjà des endpoints granulaires pour certaines ressources :

```
GET /api/{project}/infrastructure/{env}/routing        ✅ Existe
GET /api/{project}/infrastructure/{env}/enis           ✅ Existe
GET /api/{project}/infrastructure/{env}/security-group/{id}  ✅ Existe
```

**Mais il manque** :
```
GET /api/{project}/infrastructure/{env}/cloudfront     ❌ N'existe pas
GET /api/{project}/infrastructure/{env}/alb            ❌ N'existe pas
GET /api/{project}/infrastructure/{env}/rds            ❌ N'existe pas
GET /api/{project}/infrastructure/{env}/redis          ❌ N'existe pas
GET /api/{project}/infrastructure/{env}/efs            ❌ N'existe pas
GET /api/{project}/infrastructure/{env}/s3             ❌ N'existe pas
```

---

## 3. Incohérences Front/Back

### 3.1 Duplication de code frontend

`HomeDashboard.jsx` contient ~300 lignes dupliquées entre :
- `fetchInfrastructure()` (ligne 590)
- `refreshInfrastructure()` (ligne 638)

Même logique, mêmes query params, même state update.

### 3.2 Nommage incohérent

| Backend | Frontend | Status |
|---------|----------|--------|
| `workloads` | `services` | Backend retourne les deux (alias), frontend utilise `services` |
| `redis` | `redis` | OK |
| `orchestrator` | N/A | Frontend ne l'utilise pas explicitement |

### 3.3 Pas de hook réutilisable

Chaque composant redéfinit sa propre logique de fetch :

```javascript
// HomeDashboard.jsx
const fetchInfrastructure = async (env) => { ... }

// RoutingDetails.jsx
const fetchRouting = async () => { ... }

// TaskDetails.jsx
const fetchEni = async (ip) => { ... }
```

Aucun `useInfrastructure()` hook partagé → pas de cache commun, pas d'invalidation centralisée.

---

## 4. Recommandations

### Court terme (1-2 jours)

1. **Créer `useInfrastructure.js`** hook réutilisable :
```javascript
export const useInfrastructure = (projectId, env) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async () => { ... }, [projectId, env]);
  const refresh = fetch; // DRY

  return { data, loading, fetch, refresh };
};
```

2. **Documenter l'API** dans un fichier `docs/api-reference.md`

### Moyen terme (1 semaine)

3. **Découper `handler.py`** en sous-handlers :
```
backend/
├── handlers/
│   ├── infrastructure.py   # Routing /infrastructure/*
│   ├── services.py         # Routing /services/*
│   ├── pipelines.py        # Routing /pipelines/*
│   └── k8s.py              # Routing /k8s/*
└── handler.py              # Import et dispatch
```

4. **Ajouter sub-endpoints infrastructure** :
```python
# Dans handlers/infrastructure.py
@route('/api/{project}/infrastructure/{env}/cloudfront')
def get_cloudfront(project, env): ...

@route('/api/{project}/infrastructure/{env}/alb')
def get_alb(project, env): ...
```

5. **Découper `HomeDashboard.jsx`** (1446→~400 lignes) :
```
components/
├── dashboard/
│   ├── HomeDashboard.jsx      # Layout + composition
│   ├── ServiceSection.jsx     # Rendu services
│   ├── InfraSection.jsx       # Rendu infra
│   └── PipelineSection.jsx    # Rendu pipelines
hooks/
├── useServices.js
├── useInfrastructure.js
├── usePipelines.js
└── useEvents.js
```

### Long terme (optionnel)

6. **Migrer vers React Query** pour le caching et l'invalidation automatique
7. **Implémenter GraphQL** si la granularité des requêtes devient critique

---

## 5. Priorités suggérées

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 1 | Créer hook `useInfrastructure` | 2h | Élimine duplication, facilite tests |
| 2 | Ajouter endpoint `/infrastructure/{env}/cloudfront` | 1h | Permet refresh granulaire CloudFront |
| 3 | Ajouter endpoint `/infrastructure/{env}/alb` | 1h | Permet refresh granulaire ALB |
| 4 | Découper `handler.py` | 4h | Maintenabilité backend |
| 5 | Découper `HomeDashboard.jsx` | 4h | Maintenabilité frontend |
| 6 | Découper `ecs.py` et `eks.py` | 6h | Tests unitaires possibles |

---

## 6. Architecture actuelle vs cible

### Actuelle (monolithique)

```
Frontend (HomeDashboard)
  │
  └─► GET /api/{proj}/infrastructure/{env}  ─────► InfrastructureAggregator
                                                    ├─► CloudFront
                                                    ├─► ALB
                                                    ├─► RDS
                                                    ├─► Redis
                                                    ├─► Network
                                                    ├─► Workloads
                                                    ├─► EFS
                                                    └─► S3

  Si 1 provider fail → TOUT fail
```

### Cible (granulaire)

```
Frontend (HomeDashboard)
  │
  ├─► GET /infrastructure/{env}/cloudfront  ─► CloudFrontProvider
  ├─► GET /infrastructure/{env}/alb         ─► ALBProvider
  ├─► GET /infrastructure/{env}/rds         ─► RDSProvider
  ├─► GET /infrastructure/{env}/redis       ─► RedisProvider
  ├─► GET /infrastructure/{env}/network     ─► NetworkProvider
  ├─► GET /infrastructure/{env}/workloads   ─► OrchestratorProvider
  ├─► GET /infrastructure/{env}/efs         ─► EFSProvider
  └─► GET /infrastructure/{env}/s3          ─► S3Provider

  Appels parallèles, erreurs isolées, cache granulaire
```

---

## 7. Détail des fichiers analysés

### Frontend - Fichiers > 300 lignes

| Fichier | Lignes | Catégorie |
|---------|--------|-----------|
| `HomeDashboard.jsx` | 1446 | Page |
| `RoutingDetails.jsx` | 1406 | Component |
| `ServiceDetailsPanel.jsx` | 808 | Component |
| `RoutingView.jsx` | 757 | Component |
| `ComparisonPage.jsx` | 647 | Page |
| `EventsTimelinePanel.jsx` | 575 | Component |
| `NetworkView.jsx` | 563 | Component |
| `ComparisonDetailPanel.jsx` | 495 | Component |
| `SimpleView.jsx` | 493 | Component |
| `TaskDetails.jsx` | 465 | Component |
| `InfrastructureDiagram.jsx` | 417 | Component |
| `useAuth.jsx` | 381 | Hook |

### Backend - Fichiers > 300 lignes

| Fichier | Lignes | Catégorie |
|---------|--------|-----------|
| `providers/orchestrator/ecs.py` | 2002 | Provider |
| `handler.py` | 1524 | Router |
| `providers/orchestrator/eks.py` | 1478 | Provider |
| `providers/orchestrator/eks_dynamo.py` | 1157 | Cache |
| `auth/user_management.py` | 1004 | Auth |
| `providers/infrastructure/network.py` | 961 | Provider |
| `auth/handlers.py` | 878 | Auth |
| `auth/device_flow.py` | 780 | Auth |
| `providers/events/combined.py` | 719 | Provider |
| `infrastructure/handler.py` | 660 | Handler |
| `auth/admin_handlers.py` | 652 | Auth |
| `providers/base.py` | 618 | Base |
| `providers/aggregators/infrastructure.py` | 578 | Aggregator |

---

## Conclusion

Le projet Dashborion fonctionne mais accumule de la dette technique. Les refactorings prioritaires sont :

1. **Backend** : Ajouter des sub-endpoints granulaires pour `/infrastructure`
2. **Frontend** : Créer des hooks réutilisables et découper `HomeDashboard.jsx`
3. **Architecture** : Migrer vers des appels parallèles côté frontend

Ces changements amélioreront la résilience (erreurs isolées), la performance (parallélisme) et la maintenabilité (fichiers plus petits, logique centralisée).
