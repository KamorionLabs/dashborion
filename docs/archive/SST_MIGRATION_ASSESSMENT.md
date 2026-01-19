# SST Migration Assessment

Date: 2025-01-12

## Context

Dashborion utilise actuellement SST v3 pour le deploiement. Des problemes de stabilite ont ete observes.

## Problemes rencontres avec SST

### Race Condition - Concurrent Map Writes

```
fatal error: concurrent map writes
github.com/sst/sst/v3/pkg/runtime/python.(*PythonRuntime).Build
```

**Cause** : SST construit les Lambdas Python en parallele pour optimiser la vitesse, mais plusieurs goroutines ecrivent simultanement dans la meme map sans synchronisation.

**Impact** :
- Crash aleatoire pendant le deploiement
- Necessite de relancer manuellement (`sst unlock` puis retry)
- Le frontend est souvent deja uploade avant le crash, donc pas de perte de travail

### Autres problemes observes

- Lock non libere apres crash (necessite `sst unlock`)
- Profil AWS pas toujours correctement herite du config
- Messages d'erreur parfois peu explicites

## Analyse des alternatives

| Option | Stabilite | Integration Rubix IaC | Complexite | Build frontend |
|--------|-----------|----------------------|------------|----------------|
| **SST (actuel)** | Moyenne | Faible | Simple | Integre |
| **OpenTofu pur** | Haute | Excellente | Moyenne | Separe |
| **AWS CDK** | Haute | Faible | Moyenne | Separe |
| **Pulumi** | Haute | Faible | Moyenne | Separe |

### SST (actuel)

**Avantages** :
- Deploiement simple en une commande
- Build frontend integre (Vite)
- Gestion automatique CloudFront invalidation
- Hot reload en dev (`sst dev`)

**Inconvenients** :
- SST v3 encore jeune, bugs de concurrence
- Pas aligne avec l'ecosysteme Terraform/OpenTofu Rubix
- State proprietaire (pas compatible Terraform)
- Debugging difficile en cas de probleme

### OpenTofu (recommande)

**Avantages** :
- Stable, mature, bien teste
- Aligne avec les patterns IaC NewHorizon
- State standard S3 + DynamoDB lock
- Ecosysteme de modules existant
- Reproductible et deterministe

**Inconvenients** :
- Build frontend separe (script ou CI/CD)
- Packaging Lambda plus verbeux
- Pas de hot reload natif

### AWS CDK

**Avantages** :
- Abstractions Lambda pratiques
- Support AWS natif

**Inconvenients** :
- CloudFormation sous le capot (lent, limites)
- Differente philosophie que Terraform
- Debugging stack CloudFormation penible

### Pulumi

**Avantages** :
- API similaire CDK
- Multi-cloud

**Inconvenients** :
- State management different
- Pas aligne avec strategie Rubix
- Courbe d'apprentissage

## Recommandation

**Migrer vers OpenTofu** pour aligner Dashborion avec le reste de l'infrastructure NewHorizon.

### Architecture cible

```
dashborion/
├── packages/
│   ├── frontend/          # React app (inchange)
│   └── backend/           # Lambdas Python (inchange)
├── terraform/
│   ├── providers.tf       # AWS provider, backend S3
│   ├── variables.tf
│   ├── frontend.tf        # S3 bucket, CloudFront, OAC
│   ├── api.tf             # API Gateway HTTP
│   ├── lambdas.tf         # Lambda functions
│   ├── dynamodb.tf        # Tables
│   └── outputs.tf
└── scripts/
    └── deploy.sh          # Build frontend + tofu apply
```

### Plan de migration

#### Phase 1 : Infrastructure OpenTofu

1. Creer `terraform/` avec les ressources equivalentes :
   - S3 bucket pour frontend (existe deja, importer)
   - CloudFront distribution (existe deja, importer)
   - API Gateway HTTP
   - Lambda functions avec packaging
   - DynamoDB tables

2. Utiliser `tofu import` pour importer les ressources existantes

#### Phase 2 : Build Pipeline

1. Script `scripts/deploy.sh` :
   ```bash
   #!/bin/bash
   set -e

   STAGE=${1:-dev}

   # Build frontend
   cd packages/frontend
   npm run build

   # Sync to S3
   aws s3 sync dist/ s3://${BUCKET_NAME}/ --delete

   # Invalidate CloudFront
   aws cloudfront create-invalidation \
     --distribution-id ${CF_DIST_ID} \
     --paths "/*"

   # Deploy infra
   cd ../../terraform
   tofu apply -var="stage=${STAGE}" -auto-approve
   ```

2. Integration CI/CD Azure DevOps (optionnel)

#### Phase 3 : Nettoyage

1. Supprimer `.sst/` et configuration SST
2. Mettre a jour README
3. Documenter le nouveau workflow

### Effort estime

- Phase 1 : 2-3 jours (creation Terraform + import)
- Phase 2 : 1 jour (scripts de deploiement)
- Phase 3 : 0.5 jour (nettoyage)

**Total : ~4 jours de travail**

### Risques

| Risque | Mitigation |
|--------|------------|
| Import Terraform rate | Tester sur stage `dev` d'abord |
| Regression fonctionnelle | Comparer les outputs avant/apres |
| Downtime | Import ne modifie pas les ressources |

## Decision

- [ ] Rester sur SST (accepter l'instabilite occasionnelle)
- [ ] Migrer vers OpenTofu (recommande)
- [ ] Autre option

## References

- [SST v3 Documentation](https://sst.dev/)
- [OpenTofu Documentation](https://opentofu.org/docs/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [NewHorizon-IaC-AWS patterns](../../../rubix/NewHorizon-IaC-AWS/)
