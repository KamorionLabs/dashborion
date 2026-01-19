# Proposition : Unification ECS / Kubernetes

> **Status** : Proposition - À implémenter ultérieurement
> **Date** : 2025-01-11

## Contexte

La CLI Dashborion supporte deux orchestrateurs :
- **ECS** (Fargate/EC2) - utilisé par Homebox
- **EKS/Kubernetes** - utilisé par Rubix

Actuellement, certaines commandes sont spécifiques à un orchestrateur (`k8s pods` ne fonctionne pas sur ECS).

## Parallèles ECS vs Kubernetes

| Concept | ECS | Kubernetes | Terme unifié proposé |
|---------|-----|------------|---------------------|
| Unité de déploiement | Service | Deployment | **workload** ou **service** |
| Instance d'exécution | Task | Pod | **instance** ou **task** |
| Définition | Task Definition | Deployment spec | **definition** |
| Conteneur | Container | Container | container |
| Groupe logique | Cluster | Namespace | **namespace** (ou tags ECS) |
| Point d'entrée réseau | Target Group + ALB | Service + Ingress | **endpoint** |
| Scaling | Service desired count | HPA / replicas | replicas |

## Proposition d'architecture unifiée

### Niveau API - Endpoints abstraits

```
/api/{project}/workloads/{env}              # Liste services ECS ou deployments K8s
/api/{project}/workloads/{env}/{name}       # Détails
/api/{project}/instances/{env}              # Liste tasks ECS ou pods K8s
/api/{project}/instances/{env}/{id}         # Détails instance
/api/{project}/instances/{env}/{id}/logs    # Logs
```

### Niveau CLI - Commandes unifiées

```bash
# Commandes agnostiques (fonctionnent ECS et EKS)
dashborion workloads list                    # ou garder 'services list'
dashborion workloads describe <name>
dashborion workloads scale <name> -r 3
dashborion workloads restart <name>
dashborion workloads logs <name>

dashborion instances list                    # tasks ECS / pods K8s
dashborion instances list -w <workload>      # filtrer par workload
dashborion instances describe <id>
dashborion instances logs <id>

# Commandes orchestrator-specific (avancées)
dashborion k8s ingresses list                # K8s only
dashborion k8s configmaps list               # K8s only
dashborion ecs task-definitions list         # ECS only
```

### Structure de réponse normalisée

```python
# Workload (service ECS ou deployment K8s)
{
    "name": "api-gateway",
    "type": "ecs-service" | "k8s-deployment",
    "status": "running" | "degraded" | "stopped",
    "desired": 3,
    "running": 3,
    "available": 3,
    "image": "123456.dkr.ecr.../api:v1.2.3",
    "createdAt": "2024-01-10T...",
    "updatedAt": "2024-01-11T...",
    # Champs spécifiques exposés de manière uniforme
    "cpu": "512",        # ECS: cpu units, K8s: requests.cpu
    "memory": "1024",    # ECS: MB, K8s: requests.memory
    "endpoints": [...]   # Target groups ou Services
}

# Instance (task ECS ou pod K8s)
{
    "id": "abc123...",   # Task ID ou Pod name
    "name": "api-gateway-abc123",
    "workload": "api-gateway",
    "status": "running" | "pending" | "stopped",
    "ip": "10.0.1.23",
    "startedAt": "2024-01-11T...",
    "restarts": 0,
    "containers": [
        {"name": "main", "status": "running", "image": "..."}
    ]
}
```

## Plan d'implémentation

### Phase 1 : Backend - Aggregator unifié
1. Créer `providers/aggregators/workloads.py`
2. Normaliser les réponses ECS/EKS
3. Ajouter les nouveaux endpoints

### Phase 2 : CLI - Commandes unifiées
1. Option A : Renommer `services` → `workloads`
2. Option B : Garder `services` comme terme unifié
3. Ajouter alias pour compatibilité

### Phase 3 : Documentation
1. Mettre à jour l'aide des commandes
2. Documenter les différences ECS/EKS

## Questions ouvertes

- [ ] Garder `services` ou passer à `workloads` ?
- [ ] Comment gérer les namespaces K8s vs tags ECS ?
- [ ] Faut-il un flag `--raw` pour voir les données brutes orchestrator-specific ?

## Références

- [ECS Concepts](https://docs.aws.amazon.com/ecs/latest/developerguide/Welcome.html)
- [Kubernetes Concepts](https://kubernetes.io/docs/concepts/)
