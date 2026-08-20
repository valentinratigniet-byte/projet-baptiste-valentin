# Dette technique critique

Ledger des raccourcis pris volontairement (ou découverts en cours de route),
avec leur plafond connu et le sprint qui les solde. Mis à jour à chaque fin
de sprint (voir Definition of Done, `ROADMAP.md`).

| # | Où | Raccourci pris | Plafond connu (ce qui casse) | Mise à niveau | Sprint cible |
|---|----|-----------------|-------------------------------|----------------|---------------|
| 1 | Repo entier | Aucun CI (GitHub Actions) — rien ne vérifie automatiquement les générateurs Python ni les modèles dbt (`dbt build`, 68 tests, tourne seulement en local) | Une régression peut être mergée sans détection avant la prod BigQuery | Pipeline CI : lint + `demo()` des générateurs + `dbt build` sur cible dev à chaque push | Sprint 6 (en même temps que le CI/CD `dbt docs`) |
| 2 | `.env` | Mots de passe par défaut faibles (`changeme`, `ChangeMe123!`) | Acceptable tant que tout reste en local ; devient un risque réel si l'infra est exposée au-delà de cette machine | Rotation systématique avant toute exposition réseau (checklist, pas de code à écrire) | Avant toute exposition — checklist Sprint 10 |
| 3 | `data-generation/generate_cg_data.py` | Volumétrie "portfolio" (~4 400 ventes) alors que le CA simulé (11,3M€) suggère une vraie PME/ETI | Si présenté comme cas réel sans cette précision, le volume de lignes ne tient pas la comparaison avec une vraie volumétrie CG | Limite assumée pour une démo — augmenter le volume seulement si un test de charge/partitionnement BigQuery le justifie (Sprint 6, FinOps) | Pas de sprint dédié — limite assumée, à mentionner explicitement dans le README si le repo est montré comme référence |
| 4 | `dbt_cg/models/marts/fct_allocation_couts.sql` | Ventile le CA du centre "Non affecté", pas des "charges indirectes" comme prévu au départ — le modèle Réel (`fct_ventes_reel`) ne contient que du chiffre d'affaires, aucune charge réelle n'existe pour être ventilée | Le nom du modèle et l'intitulé roadmap ("allocations de charges") ne correspondent pas exactement à ce qu'il fait | Limite assumée et documentée dans `docs/DBT.md` — nécessiterait un vrai flux "charges réelles" (comptabilité fournisseurs) pour être corrigé, hors périmètre actuel | Pas de sprint dédié — limite assumée |
| 5 | `dbt_cg/profiles.yml` | Cible `prod` (BigQuery) structurellement présente mais non fonctionnelle : pas de `dbt-bigquery` installé, pas de projet GCP | Aucun run réel possible sur `prod` avant ce sprint | Installer `dbt-bigquery`, créer le projet GCP, générer la clé de service (suit `docs/ARCHITECTURE.md`) | Sprint 6 (Gouvernance & FinOps, quand BigQuery entre en jeu) |
| 6 | `n8n` (`alerting-depassement-budgetaire`, `notification-schema-change`) | Pas de vraie intégration Discord/Slack — s'arrête à un nœud `NoOp` nommé "prêt à brancher" | Aucune alerte n'est réellement envoyée à un humain tant qu'un vrai webhook n'est pas branché | Remplacer le nœud `NoOp` final par un `HTTP Request` vers une vraie URL de webhook (1 nœud, pas de refonte) — nécessite juste que Baptiste/Valentin aient un serveur Discord/Slack à brancher | Pas de sprint dédié — dépend d'un compte externe, pas d'un manque de code |
| 7 | `n8n` (`cloture-mensuelle`) | Dépose sur MinIO plutôt que Google Drive comme prévu au cahier des charges — pas de compte Google/OAuth disponible pour ce portfolio | Le fichier XLSX n'atterrit pas réellement sur un Drive partagé | Remplacer le nœud S3 par un nœud Google Drive (même position dans le workflow) une fois un compte disponible | Pas de sprint dédié — dépend d'un compte externe |

## Résolu ce sprint (Sprint 5)

- ~~Workflow n8n créé à la main, jamais versionné~~ → 5 workflows exportés dans `n8n/workflows/*.json`, script `n8n/import_workflows.py` (recrée credentials + workflows, remappe les IDs). **Testé réellement** : tout supprimé (workflows + credentials) puis réimporté sur instance "vierge", les 5 webhooks retestés avec succès après coup — pas juste un script qui "devrait marcher"
- ~~Réconciliation client plafonnée à 54% de précision (pas de SIRET)~~ → champ `siret` ajouté au CRM et au référentiel legacy (~20% volontairement manquant côté legacy, dette de données assumée — pas une régression). Matching SIRET-d'abord, fuzzy-match-sinon : précision 54% → **80,2%**, F1 70,1% → **89,0%**. `dim_client` golden record : 5 → 7 clients legacy-only correctement isolés
- ~~`update-ca-certificates` insuffisant pour n8n~~ (nouveau, trouvé en câblant la veille) : Node.js a son propre magasin de certificats, ignore le magasin OS. Fix : `NODE_EXTRA_CA_CERTS` sur le service `n8n` (`docker-compose.yml`), documenté dans `docs/N8N.md`
- ~~`fix-local-ssl.ps1` échoue sur des conteneurs non-root~~ (nouveau, même cause) : n8n tourne en user `node` par défaut, `update-ca-certificates` a besoin de `-u root`

## Résolu Sprint 4 (rappel)

- ~~`ingest_to_bronze.py` sans self-check~~ → `demo()` ajouté
- ~~`migrate_erp_to_target.py` lisait le CSV brut en parallèle du data contract~~ → lit désormais Bronze (MinIO)
- ~~Bug de reproductibilité `demo()`/`main()`~~ → re-seed explicite dans les 3 générateurs
- ~~Réel et Budget sans compte commun~~ → `gen_fact_budget` budgète aussi le CA

## Résolu Sprint 3 (rappel)

- ~~Détection SSL Avast uniquement~~ → `scripts/fix-local-ssl.ps1` généralisé (`-CertPattern`, `-List`)
- ~~Générateurs sans self-check~~ → `demo()` sur les 4 scripts d'origine

## Règle du jeu

- Chaque nouveau raccourci pris pendant un sprint doit être ajouté ici avant
  de clore le sprint (Definition of Done).
- Une ligne n'est retirée du tableau que quand elle est réellement soldée
  (code écrit, testé) — pas quand elle est simplement reportée.
