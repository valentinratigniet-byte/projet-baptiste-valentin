# Hub n8n (Sprint 5)

5 workflows versionnés dans `n8n/workflows/*.json`, importables sur une
instance n8n fraîche via `n8n/import_workflows.py` (résout la dette
technique #1 — les workflows étaient créés à la main via l'API, jamais
versionnés). Chaque workflow a été testé de bout en bout, y compris après
un réimport complet sur instance vierge (workflows + credentials supprimés,
réimportés, retestés — les 5 passent).

## Workflows

| Workflow | Déclencheur | Ce qu'il fait |
|---|---|---|
| `test-webhook-vers-log` | `POST /webhook/test-log` | Gabarit de test (Sprint 1) |
| `cloture-mensuelle` | `POST /webhook/trigger-cloture-mensuelle` | Lit `fct_ecarts_reel_budget` (Postgres) → génère un XLSX → dépose sur MinIO (`gold-exports/cloture/`) |
| `alerting-depassement-budgetaire` | `POST /webhook/trigger-alerting-budget` | Détecte les écarts \|écart_pct\| > 20% → formate une alerte par ligne |
| `veille-strategique` | `POST /webhook/trigger-veille` | Collecte Hacker News (tech/IA) + taux de change (Frankfurter API) → résumé Ollama (`llama3.2:1b`) → dépose sur MinIO (`veille/`) |
| `notification-schema-change` | `POST /webhook/trigger-schema-change` | Formate une notification de changement de schéma dbt |

**Règle d'or respectée** : tous les accès Postgres se font sur `public_marts`
(Gold), jamais sur `raw`/`erp_migre` ni sur les sources (MySQL/Mongo).

## Points d'intégration volontairement laissés en placeholder

Pas de vrai compte Discord/Slack/Drive disponible pour ce portfolio — plutôt
que fabriquer une fausse intégration, chaque point d'intégration externe
s'arrête à un nœud clairement nommé, prêt à recevoir la vraie cible en un
seul changement :

- **Reverse ETL** : dépose sur MinIO (`gold-exports/`) au lieu de Google
  Drive (pas d'OAuth Google configuré). Le nœud S3 pointe MinIO comme
  n'importe quel stockage S3-compatible — le remplacer par un nœud Google
  Drive quand un compte est disponible.
- **Alerting** et **notification schéma** : s'arrêtent à un nœud `NoOp`
  nommé "prêt à brancher Discord/Slack/CI" plutôt que d'appeler une URL de
  webhook inventée qui échouerait silencieusement.
- **Veille** : le résumé Ollama (modèle 1B, choisi pour la légèreté locale)
  reste générique/peu informatif comparé à un vrai LLM — limite de qualité
  du modèle, pas du pipeline (voir exemple réel ci-dessous).

## Piège SSL, round 2 (Node.js ≠ OpenSSL)

`scripts/fix-local-ssl.ps1` (Sprint 1) corrige les clients OpenSSL/curl via
`update-ca-certificates`. **Node.js (donc n8n) a son propre magasin de
certificats et ignore le magasin système** : la veille (appels HTTPS vers
Hacker News/Frankfurter) échouait avec `UNABLE_TO_VERIFY_LEAF_SIGNATURE`
malgré le certificat Avast installé côté OS. Fix : variable d'env
`NODE_EXTRA_CA_CERTS` sur le service `n8n` (`docker-compose.yml`), pointée
vers le même fichier que `fix-local-ssl.ps1` installe déjà. Absent = juste
un warning Node au démarrage, pas un crash — dégrade proprement sur une
machine sans interception HTTPS locale.

Découvert au passage : `update-ca-certificates` échoue silencieusement sur
le conteneur n8n (tourne en user `node`, pas root) — `fix-local-ssl.ps1`
utilise maintenant `docker exec -u root`.

## Exemple réel (résumé de veille, `llama3.2:1b`)

```
Voici un résumé en 3 phrases maximum de la veille suivante pour un dirigeant
d'entreprise : "Notre croissance est en constante évolution, nous allons
continuer à investir dans les dernières technologies pour rester à la
pointe du marché."
```

Générique plutôt que vraiment ancré dans les titres Hacker News collectés —
limite assumée d'un modèle 1B. Piste testée au Sprint 7 (chatbot
Text-to-SQL) : un modèle plus gros (`llama3.2:3b`) donne des réponses plus
justes mais prend 169s par question sur ce matériel (CPU seul, pas de GPU
passé au conteneur) contre 1-3s pour le 1B — inutilisable en interactif.
Le 1B a été gardé, voir `docs/MLOPS.md`.

## Réconciliation client : le SIRET change la donne (dette #5/#6)

Ajout d'un champ `siret` au CRM et au référentiel legacy (`~20% manquant
côté legacy`, dette assumée). `migrate_erp_to_target.py` tente d'abord un
match SIRET exact avant de retomber sur le fuzzy-match nom :

| | Avant (nom seul) | Après (SIRET puis nom) |
|---|---|---|
| Précision | 54,0% | **80,2%** |
| Rappel | 100% | 100% |
| F1 | 70,1% | **89,0%** |

Le golden record `dim_client` (Sprint 4) passe de 5 à **7** clients
legacy-only correctement isolés. Le reste (~20%) reste plafonné par le
SIRET manquant, assumé et documenté plutôt que masqué (dette #5 conservée,
jamais annoncée comme "résolue à 100%").
