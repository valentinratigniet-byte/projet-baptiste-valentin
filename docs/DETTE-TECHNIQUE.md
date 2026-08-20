# Dette technique critique

Ledger des raccourcis pris volontairement (ou découverts en cours de route),
avec leur plafond connu et le sprint qui les solde. Mis à jour à chaque fin
de sprint (voir Definition of Done, `ROADMAP.md`).

| # | Où | Raccourci pris | Plafond connu (ce qui casse) | Mise à niveau | Sprint cible |
|---|----|-----------------|-------------------------------|----------------|---------------|
| 1 | Workflow n8n `Test - Webhook vers log` | Créé à la main via l'API REST brute (contournement du bug `webhookId` manquant), jamais exporté en JSON versionné | Si le conteneur `n8n` est recréé sans le volume `n8n_data` (ou sur la machine de Baptiste), le workflow disparaît et il faut refaire toutes les étapes manuelles (owner setup, création, activation) | Exporter le workflow en JSON dans `n8n/workflows/`, écrire un script d'import au démarrage (`n8n import:workflow`) | Sprint 5 (Hub n8n) |
| 2 | Repo entier | Aucun CI (GitHub Actions) — rien ne vérifie automatiquement les générateurs Python ni les modèles dbt (`dbt build`, 68 tests, tourne seulement en local) | Une régression peut être mergée sans détection avant la prod BigQuery | Pipeline CI : lint + `demo()` des générateurs + `dbt build` sur cible dev à chaque push | Sprint 6 (en même temps que le CI/CD `dbt docs`) |
| 3 | `.env` | Mots de passe par défaut faibles (`changeme`, `ChangeMe123!`) | Acceptable tant que tout reste en local ; devient un risque réel si l'infra est exposée au-delà de cette machine | Rotation systématique avant toute exposition réseau (checklist, pas de code à écrire) | Avant toute exposition — checklist Sprint 10 |
| 4 | `data-generation/generate_cg_data.py` | Volumétrie "portfolio" (~4 400 ventes) alors que le CA simulé (11,3M€) suggère une vraie PME/ETI | Si présenté comme cas réel sans cette précision, le volume de lignes ne tient pas la comparaison avec une vraie volumétrie CG | Limite assumée pour une démo — augmenter le volume seulement si un test de charge/partitionnement BigQuery le justifie (Sprint 6, FinOps) | Pas de sprint dédié — limite assumée, à mentionner explicitement dans le README si le repo est montré comme référence |
| 5 | `data-generation/generate_cg_data.py`, `erp-legacy/generate_erp_legacy_export.py` | Ni le CRM ni l'export ERP legacy ne portent d'identifiant métier stable (SIRET) — voir `docs/REFONTE-ERP.md` §4 | La réconciliation client fuzzy-match plafonne à 54% de précision (100% de rappel) : ~46% des rapprochements client restent structurellement invérifiables (homonymes réels dans le CRM, ex. 4 clients distincts nommés "Bonnin"). Effet visible au Sprint 4 : `dim_client` golden record ne retrouve que 5 clients legacy-only sur les 25 générés, les 20 autres étant rapprochés à tort | Ajouter un champ SIRET aux deux générateurs pour permettre un second critère de désambiguïsation | **Reporté à Sprint 5** — non traité ce sprint, la priorité est allée à brancher dbt sur le modèle existant |
| 6 | `erp-legacy/migrate_erp_to_target.py` | `choices_inv = {v: k for ...}` écrase silencieusement les collisions de noms normalisés identiques (dernier client_id gagne) — commentaire "collisions improbables" non vérifié formellement | Contribue au plafond de précision de la dette #5 ; masque la vraie cause si jamais elle change | Documenté et quantifié dans `docs/REFONTE-ERP.md` et `docs/DBT.md` — corrigé par la dette #5 (SIRET), pas par ce script | Sprint 5, avec #5 |
| 7 | `dbt_cg/models/marts/fct_allocation_couts.sql` | Ventile le CA du centre "Non affecté", pas des "charges indirectes" comme prévu au départ — le modèle Réel (`fct_ventes_reel`) ne contient que du chiffre d'affaires, aucune charge réelle n'existe pour être ventilée | Le nom du modèle et l'intitulé roadmap ("allocations de charges") ne correspondent pas exactement à ce qu'il fait | Limite assumée et documentée dans `docs/DBT.md` — nécessiterait un vrai flux "charges réelles" (comptabilité fournisseurs) pour être corrigé, hors périmètre actuel | Pas de sprint dédié — limite assumée |
| 8 | `dbt_cg/profiles.yml` | Cible `prod` (BigQuery) structurellement présente mais non fonctionnelle : pas de `dbt-bigquery` installé, pas de projet GCP | Aucun run réel possible sur `prod` avant ce sprint | Installer `dbt-bigquery`, créer le projet GCP, générer la clé de service (suit `docs/ARCHITECTURE.md`) | Sprint 6 (Gouvernance & FinOps, quand BigQuery entre en jeu) |

## Résolu ce sprint (Sprint 4)

- ~~`ingest_to_bronze.py` sans self-check~~ → `demo()` ajouté (dim_client 0 rejet attendu, ERP ~2% attendu)
- ~~`migrate_erp_to_target.py` lit le CSV brut en parallèle du data contract~~ → lit désormais `bronze/erp_legacy/vente_ligne_brute/` (MinIO) ; les 51 lignes à date invalide sont filtrées en amont par le contrat, plus par la migration
- ~~Bug de reproductibilité découvert en ajoutant les `demo()`~~ (nouveau, trouvé et corrigé ce sprint) : `demo()` consommait l'état aléatoire global avant `main()`, faisant diverger les données réellement chargées de ce que `demo()` avait vérifié. Corrigé par un re-seed explicite en entrée de chaque fonction, dans les 3 générateurs concernés
- ~~Réel et Budget ne partageaient aucun compte commun~~ (root cause trouvée en construisant `fct_ecarts_reel_budget`, pas contournée) : le générateur ne budgétait que les charges. `gen_fact_budget` budgète désormais aussi le CA des centres commerciaux

## Résolu Sprint 3 (rappel)

- ~~Détection SSL Avast uniquement~~ → `scripts/fix-local-ssl.ps1` généralisé (`-CertPattern`, `-List`)
- ~~Générateurs sans self-check~~ → `demo()` sur les 4 scripts d'origine

## Règle du jeu

- Chaque nouveau raccourci pris pendant un sprint doit être ajouté ici avant
  de clore le sprint (Definition of Done).
- Une ligne n'est retirée du tableau que quand elle est réellement soldée
  (code écrit, testé) — pas quand elle est simplement reportée.
