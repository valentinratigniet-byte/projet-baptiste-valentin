# Dette technique critique

Ledger des raccourcis pris volontairement (ou découverts en cours de route),
avec leur plafond connu et le sprint qui les solde. Mis à jour à chaque fin
de sprint (voir Definition of Done, `ROADMAP.md`).

| # | Où | Raccourci pris | Plafond connu (ce qui casse) | Mise à niveau | Sprint cible |
|---|----|-----------------|-------------------------------|----------------|---------------|
| 1 | `data-generation/generate_cg_data.py` | Volumétrie "portfolio" (~4 400 ventes) alors que le CA simulé (11,3M€) suggère une vraie PME/ETI | Si présenté comme cas réel sans cette précision, le volume de lignes ne tient pas la comparaison avec une vraie volumétrie CG | Limite assumée pour une démo — augmenter le volume seulement si un test de charge/partitionnement BigQuery le justifie | Pas de sprint dédié — limite assumée, à mentionner explicitement dans le README si le repo est montré comme référence |
| 2 | `dbt_cg/models/marts/fct_allocation_couts.sql` | Ventile le CA du centre "Non affecté", pas des "charges indirectes" comme prévu au départ — le modèle Réel (`fct_ventes_reel`) ne contient que du chiffre d'affaires, aucune charge réelle n'existe pour être ventilée | Le nom du modèle et l'intitulé roadmap ("allocations de charges") ne correspondent pas exactement à ce qu'il fait | Limite assumée et documentée dans `docs/DBT.md` — nécessiterait un vrai flux "charges réelles" (comptabilité fournisseurs), hors périmètre actuel | Pas de sprint dédié — limite assumée |
| 3 | `n8n` (`alerting-depassement-budgetaire`, `notification-schema-change`) | Pas de vraie intégration Discord/Slack — s'arrête à un nœud `NoOp` nommé "prêt à brancher" | Aucune alerte n'est réellement envoyée à un humain tant qu'un vrai webhook n'est pas branché | Remplacer le nœud `NoOp` final par un `HTTP Request` vers une vraie URL de webhook (1 nœud) — nécessite un serveur Discord/Slack à brancher | Pas de sprint dédié — dépend d'un compte externe |
| 4 | `n8n` (`cloture-mensuelle`) | Dépose sur MinIO plutôt que Google Drive comme prévu au cahier des charges — pas de compte Google/OAuth disponible pour ce portfolio | Le fichier XLSX n'atterrit pas réellement sur un Drive partagé | Remplacer le nœud S3 par un nœud Google Drive (même position) une fois un compte disponible | Pas de sprint dédié — dépend d'un compte externe |
| 5 | `docs/GOUVERNANCE.md` (RLS + Policy Tags) | Appliqués sur 1 seule table (`fct_ecarts_reel_budget`) sur les 11 marts existants — choix de profondeur plutôt que de largeur | Les 10 autres marts (dont `fct_budget`, `fct_forecast`) restent lisibles par n'importe quel principal ayant `bigquery.dataViewer` sur le dataset | Généraliser le même patron (row access policy + policy tag) aux autres tables sensibles — mécanique une fois le patron validé | Sprint 9 (BI), quand les dashboards RH/Finance imposeront un vrai périmètre par profil sur plus de tables |
| 6 | Comptes de service `*-viewer` | RH/Finance/Direction/PDG sont des comptes de service, pas de vrais comptes Google Workspace par utilisateur (compte Gmail personnel, pas d'org) | Ne prouve pas qu'un *vrai humain* connecté avec son compte Google verrait le même résultat — seulement que le mécanisme IAM/RLS fonctionne pour des principals distincts | Migrer vers des groupes Google Workspace si ce projet rejoint une organisation avec des comptes utilisateurs réels | Pas de sprint dédié — dépend d'un Workspace, hors de portée d'un compte Gmail perso |

## Résolu ce sprint (Sprint 6)

- ~~Aucun CI~~ → `.github/workflows/ci.yml` : pipeline complet (générateurs + `demo()` + data contracts + migration ERP + `dbt build`, services MySQL/Mongo/MinIO/Postgres) à chaque push. **Vérifié réellement** sur GitHub Actions, pas juste écrit : premier run vert du premier coup
- ~~Cible BigQuery non fonctionnelle~~ → projet GCP dédié `bv-dataplatform`, RLS + Policy Tags appliqués et **prouvés par requête réelle** avec 4 comptes de service (`governance/`)
- ~~Pas de checklist rotation des secrets~~ → `docs/SECRETS-CHECKLIST.md` livré (les mots de passe par défaut restent en l'état tant que rien n'est exposé, conformément à la checklist elle-même)
- ~~`dbt docs` non publié~~ → `.github/workflows/dbt-docs.yml`, publié sur https://valentinratigniet-byte.github.io/projet-baptiste-valentin/ (GitHub Pages activé, build via Actions)
- ~~Scripts `governance/` exigeaient `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH` positionnée à la main~~ (trouvé en écrivant ce sprint) → variable `GRPC_CA_BUNDLE` dans `.env`, appliquée automatiquement par les scripts

## Résolu Sprint 5 (rappel)

- ~~Workflow n8n non versionné~~ → `n8n/workflows/*.json` + script d'import, testé après réimport complet sur instance vierge
- ~~Réconciliation client à 54% de précision~~ → SIRET ajouté, précision 80,2% (F1 89,0%)
- ~~`update-ca-certificates` insuffisant pour n8n~~ → `NODE_EXTRA_CA_CERTS`
- ~~`fix-local-ssl.ps1` échouait sur conteneurs non-root~~ → `-u root`

## Résolu Sprint 4 (rappel)

- ~~`ingest_to_bronze.py` sans self-check~~ → `demo()` ajouté
- ~~`migrate_erp_to_target.py` lisait le CSV brut en parallèle du data contract~~ → lit désormais Bronze (MinIO)
- ~~Bug de reproductibilité `demo()`/`main()`~~ → re-seed explicite
- ~~Réel et Budget sans compte commun~~ → `gen_fact_budget` budgète aussi le CA

## Résolu Sprint 3 (rappel)

- ~~Détection SSL Avast uniquement~~ → `scripts/fix-local-ssl.ps1` généralisé
- ~~Générateurs sans self-check~~ → `demo()` sur les 4 scripts d'origine

## Règle du jeu

- Chaque nouveau raccourci pris pendant un sprint doit être ajouté ici avant
  de clore le sprint (Definition of Done).
- Une ligne n'est retirée du tableau que quand elle est réellement soldée
  (code écrit, testé) — pas quand elle est simplement reportée.
