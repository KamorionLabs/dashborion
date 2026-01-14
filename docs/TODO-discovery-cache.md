# TODO: Discovery Cache (DynamoDB)

**Date**: 2026-01-13
**Status**: À implémenter plus tard
**Priority**: Medium

---

## Contexte

Le Discovery Lambda permet de découvrir les ressources AWS dans les comptes cross-account.
Actuellement, chaque appel fait un vrai call AWS. Pour éviter de spammer les APIs AWS et partager les résultats entre admins, on veut ajouter un cache DynamoDB.

---

## Solution proposée

### Schema DynamoDB

Utiliser la même table Config Registry (`dashborion-{stage}-config`) :

```
pk: DISCOVERY#{accountId}
sk: {resourceType}:{region}
data: {
  resources: [...],
  count: N
}
discoveredAt: "2026-01-13T10:30:00Z"
discoveredBy: "admin@example.com"
ttl: 1736765400  (Unix timestamp, auto-delete après 10 min)
```

### Comportement

1. **GET /api/config/discovery/{accountId}/{resourceType}**
   - Check DynamoDB cache d'abord
   - Si cache valide (< TTL), retourner directement
   - Sinon, appeler AWS, stocker en cache, retourner

2. **Force refresh**
   - Ajouter query param `?force=true` pour bypasser le cache

3. **UI**
   - Afficher "Discovered X min ago" si depuis cache
   - Bouton "Refresh" pour forcer un nouveau discovery

### TTL recommandé

- **10 minutes** par défaut
- Configurable via settings si besoin

---

## Fichiers à modifier

1. `backend/discovery/handler.py` - Ajouter logique cache
2. `backend/discovery/cache.py` - Nouveau module cache
3. `packages/frontend/src/hooks/useDiscovery.js` - Supprimer cache frontend, afficher timestamp

---

## Avantages

- Partage entre admins (admin A découvre, admin B voit le résultat)
- Réduit les appels AWS (coût, rate limiting)
- Audit trail (qui a découvert quoi, quand)
- TTL auto via DynamoDB (pas de cleanup manuel)

---

## Notes

Le cache frontend actuel (`useDiscovery.js`) est temporaire et sera supprimé quand on implémentera cette solution.
