# Dette technique critique

Ledger des raccourcis pris volontairement (ou découverts en cours de route),
avec leur plafond connu et le sprint qui les solde. Mis à jour à chaque fin
de sprint (voir Definition of Done, `ROADMAP.md`).

| # | Où | Raccourci pris | Plafond connu (ce qui casse) | Mise à niveau | Sprint cible |
|---|----|-----------------|-------------------------------|----------------|---------------|
| 1 | Workflow n8n `Test - Webhook vers log` | Créé à la main via l'API REST brute (contournement du bug `webhookId` manquant), jamais exporté en JSON versionné | Si le conteneur `n8n` est recréé sans le volume `n8n_data` (ou sur la machine de Baptiste), le workflow disparaît et il faut refaire toutes les étapes manuelles (owner setup, création, activation) | Exporter le workflow en JSON dans `n8n/workflows/`, écrire un script d'import au démarrage (`n8n import:workflow`) | Sprint 5 (Hub n8n) |
| 2 | Repo entier | Aucun CI (GitHub Actions) — rien ne vérifie automatiquement les générateurs Python ni les futurs modèles dbt | Une régression peut être mergée sans détection avant la prod BigQuery | Pipeline CI : lint + `demo()` des générateurs + `dbt build` sur cible dev à chaque push | Sprint 6 (en même temps que le CI/CD `dbt docs`) |
| 3 | `.env` | Mots de passe par défaut faibles (`changeme`, `ChangeMe123!`) | Acceptable tant que tout reste en local ; devient un risque réel si l'infra est exposée au-delà de cette machine | Rotation systématique avant toute exposition réseau (checklist, pas de code à écrire) | Avant toute exposition — checklist Sprint 10 |
| 4 | `data-generation/generate_cg_data.py` | Volumétrie "portfolio" (~4 400 ventes) alors que le CA simulé (11,3M€) suggère une vraie PME/ETI | Si présenté comme cas réel sans cette précision, le volume de lignes ne tient pas la comparaison avec une vraie volumétrie CG | Limite assumée pour une démo — augmenter le volume seulement si un test de charge/partitionnement BigQuery le justifie (Sprint 6, FinOps) | Pas de sprint dédié — limite assumée, à mentionner explicitement dans le README si le repo est montré comme référence |
| 5 | `data-generation/generate_cg_data.py`, `erp-legacy/generate_erp_legacy_export.py` | Ni le CRM ni l'export ERP legacy ne portent d'identifiant métier stable (SIRET) — voir `docs/REFONTE-ERP.md` §4 | La réconciliation client fuzzy-match plafonne à 54% de précision (100% de rappel) : ~46% des rapprochements client restent structurellement invérifiables (homonymes réels dans le CRM, ex. 4 clients distincts nommés "Bonnin") | Ajouter un champ SIRET aux deux générateurs pour permettre un second critère de désambiguïsation | Sprint 4 (MDM) |
| 6 | `erp-legacy/migrate_erp_to_target.py` | `choices_inv = {v: k for ...}` écrase silencieusement les collisions de noms normalisés identiques (dernier client_id gagne) — commentaire "collisions improbables" non vérifié formellement | Contribue au plafond de précision de la dette #5 ; masque la vraie cause si jamais elle change | Documenté et quantifié dans `docs/REFONTE-ERP.md` — corrigé par la dette #5 (SIRET), pas par ce script | Sprint 4 (MDM), avec #5 |
| 7 | `data-contracts/ingest_to_bronze.py` | Aucun `demo()`/self-check, contrairement aux 4 générateurs (dette #2 d'origine, soldée partout ailleurs) | Une régression sur un schéma ou un lecteur de source peut faire chuter silencieusement le taux d'acceptation d'un flux | Ajouter un `demo()` : au moins un flux avec 0 rejet attendu (ex. `crm/dim_client`) et le flux ERP avec ~2% de rejets attendus | Sprint 4 |
| 8 | `erp-legacy/migrate_erp_to_target.py` | Lit directement le CSV brut ERP (`erp-legacy/exports/`), en parallèle de `data-contracts/ingest_to_bronze.py` qui valide/rejette le même flux — les deux pipelines ne sont pas branchés ensemble | La migration peut charger dans `erp_migre` des lignes que le data contract aurait rejetées (actuellement inoffensif : les 51 lignes à date invalide sont de toute façon flaggées `ligne_valide=false` des deux côtés, mais la redondance est fragile si les deux logiques divergent) | Faire lire `migrate_erp_to_target.py` depuis `bronze/erp_legacy/vente_ligne_brute/` (MinIO) plutôt que depuis le CSV source directement | Sprint 4 (en même temps que les modèles dbt qui consommeront Bronze) |

## Résolu ce sprint (Sprint 3)

- ~~Détection SSL Avast uniquement~~ → `scripts/fix-local-ssl.ps1` généralisé (`-CertPattern`, `-List` pour identifier le bon certificat sur une autre machine)
- ~~Générateurs sans self-check~~ → `demo()` ajouté sur les 4 scripts de `data-generation/` et `erp-legacy/` (garde le bug d'ID hardcodé de ne plus se reproduire silencieusement)

## Règle du jeu

- Chaque nouveau raccourci pris pendant un sprint doit être ajouté ici avant
  de clore le sprint (Definition of Done).
- Une ligne n'est retirée du tableau que quand elle est réellement soldée
  (code écrit, testé) — pas quand elle est simplement reportée.
