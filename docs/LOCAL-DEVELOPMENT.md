# Local Development with LocalStack

Guide pour developper Dashborion en local avec LocalStack.

## Prerequis

- Docker Desktop
- Node.js 20+
- pnpm
- awslocal (optionnel) : `pip install awscli-local`

## Quick Start

```bash
# 1. Demarrer LocalStack + deployer SST + seeder la config
pnpm local:start

# 2. Demarrer le frontend
cd packages/frontend && pnpm dev
```

Le frontend sera disponible sur http://localhost:5173

## Commandes detaillees

### Gestion LocalStack

```bash
# Demarrer LocalStack
pnpm local:up

# Voir les logs
pnpm local:logs

# Arreter LocalStack
pnpm local:down
```

### Deploiement SST

```bash
# Deployer sur LocalStack
pnpm local:deploy

# Seeder les donnees de demo
pnpm local:seed
```

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────┐
│  Frontend       │     │           LocalStack                  │
│  (Vite)         │────▶│  ┌────────────────────────────────┐  │
│  localhost:5173 │     │  │  API Gateway (emule)           │  │
└─────────────────┘     │  │  localhost:4566                │  │
                        │  └────────────────────────────────┘  │
                        │                │                     │
                        │  ┌─────────────┴─────────────────┐  │
                        │  │           Lambda               │  │
                        │  │  (handlers Python)            │  │
                        │  └───────────────────────────────┘  │
                        │                │                     │
                        │  ┌─────────────┴─────────────────┐  │
                        │  │          DynamoDB              │  │
                        │  │  - dashborion-local-config    │  │
                        │  │  - dashborion-local-state     │  │
                        │  └───────────────────────────────┘  │
                        └──────────────────────────────────────┘
```

## Configuration

### Variables d'environnement

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCALSTACK_ENDPOINT` | `http://localhost:4566` | URL LocalStack |
| `LOCALSTACK_DEBUG` | `0` | Activer debug LocalStack |
| `AWS_REGION` | `eu-west-3` | Region AWS simulee |

### Frontend Proxy

Le frontend Vite utilise la variable `VITE_API_URL` pour le proxy API.

Apres `pnpm local:deploy`, recuperer l'URL de l'API dans l'output :

```
✔  Complete
   apiUrl: https://xxxxxxxxxx.execute-api.localhost.localstack.cloud:4566/
```

Puis demarrer le frontend avec cette URL :

```bash
cd packages/frontend
VITE_API_URL=https://xxxxxxxxxx.execute-api.localhost.localstack.cloud:4566 pnpm dev
```

Ou creer un fichier `.env.local` :

```bash
# packages/frontend/.env.local
VITE_API_URL=https://xxxxxxxxxx.execute-api.localhost.localstack.cloud:4566
```

## Donnees de demo

Le script `seed-localstack.sh` cree :

- **Project**: `demo-project` avec 3 services (api, web, worker)
- **Environments**: dev, staging, production
- **AWS Account**: 000000000000 (local)

Pour personnaliser les donnees, modifier `scripts/seed-localstack.sh`.

## Troubleshooting

### LocalStack ne demarre pas

```bash
# Verifier que Docker est lance
docker ps

# Verifier les logs LocalStack
docker logs dashborion-localstack
```

### Erreur "Table not found"

Les tables DynamoDB sont creees par SST. Executez d'abord :

```bash
pnpm local:deploy
```

### SST echoue avec LocalStack

1. Verifier que LocalStack est pret :
   ```bash
   curl http://localhost:4566/_localstack/health
   ```

2. Verifier les services actifs :
   ```bash
   curl http://localhost:4566/_localstack/health | jq '.services'
   ```

### Reinitialiser LocalStack

```bash
pnpm local:down
rm -rf .localstack/
pnpm local:start
```

## Differences avec Production

| Aspect | Local | Production |
|--------|-------|------------|
| Auth | Desactive | SAML/OIDC |
| KMS | Emule (non chiffre) | AWS KMS |
| Custom Domain | Non | Route53 + ACM |
| CloudFront | Non | CDN distribue |
| Cross-account | Non | Roles IAM |

## Limitations connues

1. **Lambda cold starts** : Plus lents qu'en production (Docker)
2. **API Gateway** : Pas de custom domain, URLs generees
3. **Authorizers** : Auth desactivee par defaut
4. **Cross-account** : Les roles IAM ne fonctionnent pas

## Workflow recommande

1. Developper les handlers Python localement avec tests unitaires
2. Tester l'integration avec LocalStack
3. Deployer sur un stage AWS (dev/staging) pour tests E2E
4. Deployer en production

## Ressources

- [LocalStack Documentation](https://docs.localstack.cloud/)
- [SST v3 Documentation](https://sst.dev/docs/)
- [Pulumi AWS Provider](https://www.pulumi.com/registry/packages/aws/)
