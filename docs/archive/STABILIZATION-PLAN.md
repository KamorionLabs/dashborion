---
  ANALYSE DASHBORION - PLAN D'ACTION PAR SUJET

  Etat du projet : Score de coherence 6/10

  Le projet est fonctionnel mais accumule de la dette technique. Voici les 4 sujets identifies :

  ---
  SUJET 1 : Configuration des projets/environnements et InfrastructureDiagram

  Problemes identifies
  ┌──────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────────┐
  │                     Probleme                     │                                     Impact                                      │              Localisation               │
  ├──────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────┤
  │ Config Registry vs Frontend config.json          │ Le frontend lit config.json statique, le backend lit DynamoDB                   │ ConfigContext.jsx vs app_config.py      │
  ├──────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────┤
  │ InfrastructureDiagram depend de SERVICES globaux │ SERVICES est une liste hardcodee dans config, pas dynamique                     │ InfrastructureDiagram.jsx:34            │
  ├──────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────┤
  │ Pas de synchronisation                           │ Les infrastructure.resources dans DynamoDB ne sont pas utilises par le frontend │ config-registry.md vs HomeDashboard.jsx │
  ├──────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────┤
  │ serviceColors hardcodes                          │ Couleurs des services en fallback local                                         │ InfrastructureDiagram.jsx:38-39         │
  └──────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────────┘
  Flux actuel (casse)

  DynamoDB (Config Registry)           Frontend (config.json)
  ├── GLOBAL#settings                  ├── envColors (static)
  ├── PROJECT#mro-mi2                  ├── services: ["hybris", "apache", "nextjs"]
  ├── ENV#mro-mi2#nh-staging          └── infrastructure.serviceColors
      └── infrastructure.resources
           ├── rds: {ids: [...]}
           └── efs: {ids: [...]}

          PAS DE LIEN ←→ DESYNCHRONISE

  Plan d'action
  ┌─────┬────────────────────────────────────────────────────┬────────┬───────────────────────────────────────────────────────────────────┐
  │  #  │                       Action                       │ Effort │                             Fichiers                              │
  ├─────┼────────────────────────────────────────────────────┼────────┼───────────────────────────────────────────────────────────────────┤
  │ 1.1 │ Exposer la config complete via API                 │ 2h     │ backend/config/handler.py → nouvel endpoint /api/config/full      │
  ├─────┼────────────────────────────────────────────────────┼────────┼───────────────────────────────────────────────────────────────────┤
  │ 1.2 │ Frontend : charger config depuis API               │ 3h     │ ConfigContext.jsx → fetch /api/config/full au lieu de config.json │
  ├─────┼────────────────────────────────────────────────────┼────────┼───────────────────────────────────────────────────────────────────┤
  │ 1.3 │ Supprimer config.json statique                     │ 1h     │ packages/frontend/public/config.json → deprecated                 │
  ├─────┼────────────────────────────────────────────────────┼────────┼───────────────────────────────────────────────────────────────────┤
  │ 1.4 │ InfrastructureDiagram : services depuis env config │ 2h     │ Lire env_config.services au lieu de SERVICES global               │
  └─────┴────────────────────────────────────────────────────┴────────┴───────────────────────────────────────────────────────────────────┘
  Resultat attendu

  DynamoDB ──► API /api/config/full ──► ConfigContext ──► InfrastructureDiagram
                                                       └──► SimpleView/NetworkView

  ---
  SUJET 2 : Gestion EKS vs ECS (partiellement cassee)

  Problemes identifies
  ┌──────────────────────────────────────┬──────────────────────────────────────────────────────────────┬───────────────────────────────────┐
  │               Probleme               │                            Impact                            │           Localisation            │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ orchestrator_type non lu             │ Le backend verifie orchestrator_type mais le frontend ignore │ handler.py:557, HomeDashboard.jsx │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ ServiceCards hardcode pour ECS       │ Affiche taskDefinition, deployPipeline - termes ECS          │ InfrastructureDiagram.jsx:222-436 │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ Pas de condition EKS dans SimpleView │ Affiche ALB+CloudFront meme pour EKS                         │ SimpleView.jsx                    │
  ├──────────────────────────────────────┼──────────────────────────────────────────────────────────────┼───────────────────────────────────┤
  │ EKS renvoie pods, pas services       │ Frontend attend services mais EKS retourne pods/deployments  │ eks.py vs ecs.py                  │
  └──────────────────────────────────────┴──────────────────────────────────────────────────────────────┴───────────────────────────────────┘
  Flux actuel

  Backend:
    ECSProvider.get_services() → {services: [{runningCount, desiredCount, taskDefinition, ...}]}
    EKSProvider.get_services() → {pods: [...], deployments: [...], services: [...]}

  Frontend (InfrastructureDiagram):
    Attend: services.services[svc].runningCount/desiredCount/taskDefinition
    → EKS ne renvoie pas ces champs → affichage vide ou erreur

  Plan d'action
  ┌─────┬─────────────────────────────────────────────┬────────┬─────────────────────────────────────────────────────────┐
  │  #  │                   Action                    │ Effort │                        Fichiers                         │
  ├─────┼─────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────┤
  │ 2.1 │ Normaliser la reponse orchestrator          │ 4h     │ eks.py : mapper deployments vers format services        │
  ├─────┼─────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────┤
  │ 2.2 │ Ajouter orchestratorType dans la config env │ 1h     │ config-registry.md → champ `ENV.orchestratorType: "ecs" │
  ├─────┼─────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────┤
  │ 2.3 │ ServiceCards : mode EKS                     │ 3h     │ Variante avec replicas, podStatus, pas taskDefinition   │
  ├─────┼─────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────┤
  │ 2.4 │ SimpleView/NetworkView : condition EKS      │ 2h     │ Masquer ALB si EKS (ou afficher Ingress/LoadBalancer)   │
  ├─────┼─────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────┤
  │ 2.5 │ Tests de bout en bout                       │ 2h     │ Tester avec un env EKS reel                             │
  └─────┴─────────────────────────────────────────────┴────────┴─────────────────────────────────────────────────────────┘
  Resultat attendu

  Config Registry:
    ENV.orchestratorType: "eks"

  Backend:
    EKSProvider.get_services() → format normalise comme ECS

  Frontend:
    if (orchestratorType === 'eks') {
      <K8sServiceCards ... />
    } else {
      <EcsServiceCards ... />
    }

  ---
  SUJET 3 : Plugin Comparison et Refresh

  Problemes identifies
  ┌──────────────────────────────────────────┬──────────────────────────────────────────────┬───────────────────────────────────────────┐
  │                 Probleme                 │                    Impact                    │               Localisation                │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────┼───────────────────────────────────────────┤
  │ Comparison fonctionne mais pas en plugin │ Code integre dans le core, pas modulaire     │ backend/comparison/, frontend/comparison/ │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────┼───────────────────────────────────────────┤
  │ Refresh non implemente                   │ Planifie dans FEATURES.md mais aucun code    │ docs/FEATURES.md:201-228                  │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────┼───────────────────────────────────────────┤
  │ Plugin system propose, pas implemente    │ Architecture documentee mais pas codee       │ DASHBORION_PLUGIN_ARCHITECTURE_REPORT.md  │
  ├──────────────────────────────────────────┼──────────────────────────────────────────────┼───────────────────────────────────────────┤
  │ Pas de feature flag effectif             │ features.comparison existe mais mal connecte │ app_config.py vs HomeDashboard.jsx        │
  └──────────────────────────────────────────┴──────────────────────────────────────────────┴───────────────────────────────────────────┘
  Etat actuel

  Core integre:
    backend/comparison/handler.py        ← fonctionne
    backend/providers/comparison/        ← fonctionne
    frontend/pages/comparison/           ← fonctionne

  Plugin system:
    backend/plugins/                     ← N'EXISTE PAS
    frontend/plugins/                    ← Squelette vide (PluginRegistry.js)

  Refresh:
    RIEN ← juste doc

  Plan d'action

  Phase A : Stabiliser Comparison (sans plugin)
  ┌─────┬───────────────────────────────────────────────┬────────┬─────────────────────────────────────────────────────────────┐
  │  #  │                    Action                     │ Effort │                          Fichiers                           │
  ├─────┼───────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────┤
  │ 3.1 │ Verifier feature flag comparison              │ 2h     │ handler.py → check config.features.comparison avant routing │
  ├─────┼───────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────┤
  │ 3.2 │ Frontend : masquer nav comparison si disabled │ 1h     │ AppRouter.jsx / navigation                                  │
  ├─────┼───────────────────────────────────────────────┼────────┼─────────────────────────────────────────────────────────────┤
  │ 3.3 │ Documenter le flux comparison                 │ 2h     │ Mettre a jour CLAUDE.md section Comparison                  │
  └─────┴───────────────────────────────────────────────┴────────┴─────────────────────────────────────────────────────────────┘
  Phase B : Implementer Refresh (sans plugin)
  ┌─────┬────────────────────────────┬────────┬─────────────────────────────────────────────────────┐
  │  #  │           Action           │ Effort │                      Fichiers                       │
  ├─────┼────────────────────────────┼────────┼─────────────────────────────────────────────────────┤
  │ 3.4 │ Backend : handler refresh  │ 4h     │ backend/refresh/handler.py - trigger Step Functions │
  ├─────┼────────────────────────────┼────────┼─────────────────────────────────────────────────────┤
  │ 3.5 │ Backend : provider refresh │ 3h     │ providers/refresh/step_functions.py                 │
  ├─────┼────────────────────────────┼────────┼─────────────────────────────────────────────────────┤
  │ 3.6 │ Frontend : RefreshPage     │ 6h     │ pages/refresh/RefreshPage.jsx                       │
  ├─────┼────────────────────────────┼────────┼─────────────────────────────────────────────────────┤
  │ 3.7 │ Feature flag refresh       │ 1h     │ Check features.refresh                              │
  └─────┴────────────────────────────┴────────┴─────────────────────────────────────────────────────┘
  Phase C : Plugin system (futur, optionnel)
  ┌──────┬───────────────────────────────┬────────┬──────────────────────────────┐
  │  #   │            Action             │ Effort │           Fichiers           │
  ├──────┼───────────────────────────────┼────────┼──────────────────────────────┤
  │ 3.8  │ Backend plugin loader         │ 8h     │ backend/plugins/loader.py    │
  ├──────┼───────────────────────────────┼────────┼──────────────────────────────┤
  │ 3.9  │ Frontend plugin loader        │ 6h     │ frontend/plugins/loader.ts   │
  ├──────┼───────────────────────────────┼────────┼──────────────────────────────┤
  │ 3.10 │ Extraire comparison en plugin │ 4h     │ Move comparison/ vers plugin │
  └──────┴───────────────────────────────┴────────┴──────────────────────────────┘
  Recommandation

  Ne pas implementer le plugin system maintenant. Garder comparison/refresh dans le core. Complexite non justifiee pour un seul client.

  ---
  SUJET 4 : Documentation obsolete

  Documents a mettre a jour
  ┌───────────────────────────────────────────────┬────────────────────────┬────────────────────────────────────────────────────────┐
  │                   Document                    │          Etat          │                       Problemes                        │
  ├───────────────────────────────────────────────┼────────────────────────┼────────────────────────────────────────────────────────┤
  │ CLAUDE.md                                     │ Partiellement obsolete │ Mentionne config.json comme source, pas DynamoDB       │
  ├───────────────────────────────────────────────┼────────────────────────┼────────────────────────────────────────────────────────┤
  │ docs/ARCHITECTURE-OPENSOURCE.md               │ A jour                 │ OK                                                     │
  ├───────────────────────────────────────────────┼────────────────────────┼────────────────────────────────────────────────────────┤
  │ docs/config-registry.md                       │ A jour                 │ OK                                                     │
  ├───────────────────────────────────────────────┼────────────────────────┼────────────────────────────────────────────────────────┤
  │ docs/FEATURES.md                              │ Incomplet              │ Refresh marque "Planned" mais decrit comme fonctionnel │
  ├───────────────────────────────────────────────┼────────────────────────┼────────────────────────────────────────────────────────┤
  │ docs/coherence-analysis-2026-01-12.md         │ A jour                 │ Bon diagnostic, actions non faites                     │
  ├───────────────────────────────────────────────┼────────────────────────┼────────────────────────────────────────────────────────┤
  │ docs/DASHBORION_PLUGIN_ARCHITECTURE_REPORT.md │ Obsolete               │ Architecture proposee jamais implementee               │
  ├───────────────────────────────────────────────┼────────────────────────┼────────────────────────────────────────────────────────┤
  │ cli/README.md                                 │ A jour                 │ OK                                                     │
  └───────────────────────────────────────────────┴────────────────────────┴────────────────────────────────────────────────────────┘
  Plan d'action
  ┌─────┬───────────────────────────────────────────┬────────┬────────────────────────────────────────────┐
  │  #  │                  Action                   │ Effort │                  Fichiers                  │
  ├─────┼───────────────────────────────────────────┼────────┼────────────────────────────────────────────┤
  │ 4.1 │ Mettre a jour CLAUDE.md                   │ 2h     │ Remplacer config.json par Config Registry  │
  ├─────┼───────────────────────────────────────────┼────────┼────────────────────────────────────────────┤
  │ 4.2 │ Mettre a jour FEATURES.md                 │ 1h     │ Marquer Refresh comme "Not implemented"    │
  ├─────┼───────────────────────────────────────────┼────────┼────────────────────────────────────────────┤
  │ 4.3 │ Supprimer ou archiver plugin architecture │ 30min  │ Deplacer vers docs/archive/                │
  ├─────┼───────────────────────────────────────────┼────────┼────────────────────────────────────────────┤
  │ 4.4 │ Creer docs/api-reference.md               │ 3h     │ Documenter tous les endpoints backend      │
  ├─────┼───────────────────────────────────────────┼────────┼────────────────────────────────────────────┤
  │ 4.5 │ Ajouter section EKS vs ECS                │ 1h     │ Documenter les differences de comportement │
  └─────┴───────────────────────────────────────────┴────────┴────────────────────────────────────────────┘
  ---
  PRIORITES ET PLANNING

  Phase 1 : Stabilisation critique (1 semaine)
  ┌──────────┬───────────────┬────────────────────┬──────────────┐
  │ Priorite │     Sujet     │      Actions       │ Effort total │
  ├──────────┼───────────────┼────────────────────┼──────────────┤
  │ P0       │ EKS/ECS       │ 2.1, 2.2, 2.3, 2.4 │ 10h          │
  ├──────────┼───────────────┼────────────────────┼──────────────┤
  │ P0       │ Config        │ 1.1, 1.2           │ 5h           │
  ├──────────┼───────────────┼────────────────────┼──────────────┤
  │ P1       │ Documentation │ 4.1, 4.2, 4.3      │ 3.5h         │
  └──────────┴───────────────┴────────────────────┴──────────────┘
  Total Phase 1 : ~18h

  Phase 2 : Ameliorations (2 semaines)
  ┌──────────┬───────────────┬───────────────┬──────────────┐
  │ Priorite │     Sujet     │    Actions    │ Effort total │
  ├──────────┼───────────────┼───────────────┼──────────────┤
  │ P1       │ Config        │ 1.3, 1.4      │ 3h           │
  ├──────────┼───────────────┼───────────────┼──────────────┤
  │ P1       │ Comparison    │ 3.1, 3.2, 3.3 │ 5h           │
  ├──────────┼───────────────┼───────────────┼──────────────┤
  │ P2       │ Documentation │ 4.4, 4.5      │ 4h           │
  ├──────────┼───────────────┼───────────────┼──────────────┤
  │ P2       │ EKS/ECS       │ 2.5           │ 2h           │
  └──────────┴───────────────┴───────────────┴──────────────┘
  Total Phase 2 : ~14h

  Phase 3 : Nouvelles features (a planifier)
  ┌──────────┬───────────────┬────────────────────┬──────────────┐
  │ Priorite │     Sujet     │      Actions       │ Effort total │
  ├──────────┼───────────────┼────────────────────┼──────────────┤
  │ P2       │ Refresh       │ 3.4, 3.5, 3.6, 3.7 │ 14h          │
  ├──────────┼───────────────┼────────────────────┼──────────────┤
  │ P3       │ Plugin system │ 3.8, 3.9, 3.10     │ 18h          │
  └──────────┴───────────────┴────────────────────┴──────────────┘
  ---
  SYNTHESE

  ETAT ACTUEL:
    Config:     Frontend deconnecte du backend (config.json vs DynamoDB)
    EKS/ECS:    Frontend casse pour EKS, ServiceCards hardcode pour ECS
    Comparison: Fonctionne mais pas modulaire
    Refresh:    Non implemente
    Docs:       Partiellement obsoletes

  ACTIONS PRIORITAIRES:
    1. Normaliser EKS/ECS (backend + frontend)
    2. Connecter frontend au Config Registry
    3. Mettre a jour la documentation

  NE PAS FAIRE:
    - Plugin system (over-engineering pour un seul client)
    - Refactoring massif (handler.py 1524 lignes → peut attendre)

  Veux-tu que je commence par un sujet en particulier ?
