# Investigation: Affichage Infrastructure dans EKS Dashboard

## Contexte

Après déploiement du dashboard Dashborion chez Rubix (environnements staging), plusieurs problèmes d'affichage ont été identifiés.

### Problème initial : Tags trop génériques

Les `discoveryTags` étaient trop génériques (`rubix_Environment: stg`), matchant potentiellement plusieurs ressources AWS dans le même compte.

**Solution appliquée** : Ajout du tag `rubix_Application` dans `discoveryTags` pour chaque projet MRO dans `infra.config.json`.

```json
"discoveryTags": {
  "rubix_Environment": "stg",
  "rubix_Application": "webshop-mi2"
}
```

### Problèmes identifiés (2026-01-12)

Sur mro-mi2-nh-staging :
1. **CloudFront** : Non affiché (7 distributions existent)
2. **Load Balancer** : "0 targets" (ALB partagé existe)
3. **Data Stores** : "No data stores" (RDS/EFS existent avec bons tags)
4. **SVG** : Noeuds workloads positionnés hors de la box visible

---

## Root Cause #1 : Format des Ingresses (CORRIGÉ)

### Découverte

Les ingresses sont stockés dans DynamoDB comme un **dictionnaire** par type :

```json
{
  "ingresses": {
    "bo": { "name": "rubix-mro-mi2-staging-bo-ingress", "loadBalancer": {"hostname": "..."} },
    "private": { "name": "rubix-mro-mi2-staging-private-ingress", ... },
    "unknown": { "name": "rubix-mro-mi2-staging-ingress", ... }
  }
}
```

Le code `get_ingresses()` attendait une **liste** :

```python
# Ancien code (buggy)
ingresses_data = result.data.get('ingresses', [])
for ing_data in ingresses_data:  # Échoue si dict
```

### Correction appliquée

Fichier : `backend/providers/orchestrator/eks_dynamo.py`

```python
def get_ingresses(self, env: str, namespace: str = None, force_refresh: bool = False):
    result = self._get_data_with_refresh('ingress', env, namespace=namespace, force_refresh=force_refresh)

    if result.status in (DataStatus.ERROR, DataStatus.NO_DATA) or not result.data:
        return [], result

    ingresses_raw = result.data.get('ingresses', [])

    # Handle both dict format (by type: bo, private, unknown) and list format
    if isinstance(ingresses_raw, dict):
        ingresses_data = list(ingresses_raw.values())
    else:
        ingresses_data = ingresses_raw
```

---

## Root Cause #2 : Champ LoadBalancer Hostname (CORRIGÉ)

### Découverte

Le hostname du load balancer est stocké dans une structure **imbriquée** :

```json
{
  "loadBalancer": {
    "hostname": "k8s-rubixmro-xxxxxxx.eu-central-1.elb.amazonaws.com"
  }
}
```

Le code cherchait un champ **plat** `loadBalancerHostname`.

### Correction appliquée

```python
# Extract load balancer hostname from nested structure or flat field
lb_data = ing_data.get('loadBalancer', {})
lb_hostname = lb_data.get('hostname') if isinstance(lb_data, dict) else None
if not lb_hostname:
    lb_hostname = ing_data.get('loadBalancerHostname')
```

---

## Root Cause #3 : Champ Ingress Class (CORRIGÉ)

### Découverte

Le champ ingress class est stocké comme `class`, pas `ingressClass`.

### Correction appliquée

```python
ingress_class=ing_data.get('class') or ing_data.get('ingressClass'),
```

---

## Impact des corrections

### Attendu après redéploiement

| Composant | Avant | Après | Mécanisme |
|-----------|-------|-------|-----------|
| **ALB** | 0 targets | Devrait fonctionner | Découverte via hostname ingress |
| **RDS/Aurora** | Non affiché | Devrait fonctionner | Tags corrects (`rubix_Application: webshop-mi2`) |
| **EFS** | Non affiché | Devrait fonctionner | Tags corrects |

### Problèmes corrigés additionnels

| Problème | Root Cause | Correction |
|----------|------------|------------|
| **CloudFront multi-distributions** | `_find_distribution_by_tags()` retournait seulement la 1ère distribution | Retourne maintenant toutes les distributions + agrégation |
| **SVG positionnement** | `layerIdx` utilisait l'index complet du tableau, `workloadsWidth` basé sur layers actifs | Utilisation de `compactIdx` pour layers actifs uniquement |

---

## Données DynamoDB vérifiées

### mro-mi2#nh-staging - Ingresses

```bash
aws dynamodb get-item \
  --table-name ops-dashboard-shared-state \
  --key '{"pk": {"S": "mro-mi2#nh-staging"}, "sk": {"S": "check:k8s:ingress:current"}}' \
  --profile shared-services/AWSAdministratorAccess --region eu-central-1
```

**Résultat** : 3 ingresses trouvés (bo, private, unknown) avec hostnames ALB valides.

### mro-mi2#nh-staging - Services

**Résultat** : 13 services K8s trouvés

### Tags AWS vérifiés

| Resource | Tags | Découvrable |
|----------|------|-------------|
| CloudFront (7 dist.) | `rubix_Application: webshop-mi2` | Oui (mais seule la 1ère retournée) |
| ALB | `rubix_Application: webshop` (générique) | Non via tags, oui via ingress hostname |
| RDS Aurora | `rubix_Application: webshop-mi2` | Oui |
| EFS | `rubix_Application: Hybris` | Oui (si discoveryTags incluent Hybris) |

---

## Architecture du flux - Découverte ALB

```
DynamoDB                    Backend                           AWS
────────                    ───────                           ───
check:k8s:ingress:current   EKSDynamoProvider.get_ingresses()
  │                              │
  │ ingresses: {                 │ Extrait loadBalancer.hostname
  │   bo: {loadBalancer: {...}}, │ = "k8s-rubixmro-xxx.elb.amazonaws.com"
  │   ...                        │
  │ }                            ↓
  │                         InfrastructureAggregator
  │                              │
  │                              │ ingress_hostname passé à ALBProvider
  │                              ↓
  │                         ALBProvider.get_load_balancer()
  │                              │
  │                              │ Découverte par DNS name
  │                              ↓
  └─────────────────────────────────────────────────────────► describe_load_balancers()
                                                              filter: DNSName = hostname
```

---

## Fichiers modifiés

| Fichier | Action | Description |
|---------|--------|-------------|
| `backend/providers/orchestrator/eks_dynamo.py` | **MODIFIÉ** | Fix get_ingresses() pour format dict + hostname imbriqué |
| `backend/providers/infrastructure/cloudfront.py` | **MODIFIÉ** | Support multi-distributions (retourne liste + agrégation) |
| `packages/frontend/src/components/infrastructure/SimpleView.jsx` | **MODIFIÉ** | Fix positionnement SVG avec compactIdx |
| `infra.config.json` | Modifié | Ajout `rubix_Application` dans discoveryTags |

---

## Prochaines étapes

1. **Redéployer le backend et frontend** pour appliquer les corrections
2. **Vérifier** que ALB, RDS, EFS, CloudFront s'affichent correctement
3. **Vérifier** que les noeuds workloads sont positionnés dans la box visible

---

## Historique

| Date | Action |
|------|--------|
| 2026-01-12 | Investigation initiale - tags trop génériques |
| 2026-01-12 | Découverte root cause #1 : format ingresses dict vs list |
| 2026-01-12 | Découverte root cause #2 : loadBalancer.hostname imbriqué |
| 2026-01-12 | Correction appliquée à eks_dynamo.py |
| 2026-01-12 | Fix CloudFront multi-distributions (cloudfront.py) |
| 2026-01-12 | Fix SVG positionnement (SimpleView.jsx - compactIdx) |

---

*Document mis à jour le 2026-01-12 - Toutes les corrections appliquées.*
