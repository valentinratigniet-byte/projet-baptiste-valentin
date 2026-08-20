# Dette technique critique

Ledger des raccourcis pris volontairement (ou découverts en cours de route),
avec leur plafond connu et le sprint qui les solde. Mis à jour à chaque fin
de sprint (voir Definition of Done, `ROADMAP.md`).

| # | Où | Raccourci pris | Plafond connu (ce qui casse) | Mise à niveau | Sprint cible |
|---|----|-----------------|-------------------------------|----------------|---------------|
| 1 | `scripts/fix-local-ssl.ps1` | Détecte uniquement le root CA "Avast Web/Mail Shield" par nom exact | Si Baptiste a un autre antivirus/proxy qui intercepte le HTTPS (ou pas d'interception du tout), le script ne fait rien pour lui | Généraliser la détection (tout root CA hors magasin Microsoft par défaut) + documenter la procédure manuelle équivalente | Sprint 2 |
| 2 | `data-generation/generate_cg_data.py`, `generate_logs_mongo.py` | Aucun test/self-check — un bug d'ID de compte hardcodé (26 au lieu de 16) est passé jusqu'au dry-run manuel | Un futur refactor peut réintroduire un bug silencieux (montants à zéro, jointures vides) sans qu'aucun signal ne le remonte | Ajouter un `demo()`/assert minimal par générateur : IDs dans les bornes attendues, sommes non nulles, pas de NULL inattendu | Sprint 3 (avec les data contracts — même logique de validation) |
| 3 | Workflow n8n `Test - Webhook vers log` | Créé à la main via l'API REST brute (contournement du bug `webhookId` manquant), jamais exporté en JSON versionné | Si le conteneur `n8n` est recréé sans le volume `n8n_data` (ou sur la machine de Baptiste), le workflow disparaît et il faut refaire toutes les étapes manuelles (owner setup, création, activation) | Exporter le workflow en JSON dans `n8n/workflows/`, écrire un script d'import au démarrage (`n8n import:workflow`) | Sprint 5 (Hub n8n) |
| 4 | Repo entier | Aucun CI (GitHub Actions) — rien ne vérifie automatiquement les générateurs Python ni les futurs modèles dbt | Une régression peut être mergée sans détection avant la prod BigQuery | Pipeline CI : lint + `demo()` des générateurs + `dbt build` sur cible dev à chaque push | Sprint 6 (en même temps que le CI/CD `dbt docs`) |
| 5 | `.env` | Mots de passe par défaut faibles (`changeme`, `ChangeMe123!`) | Acceptable tant que tout reste en local ; devient un risque réel si l'infra est exposée au-delà de cette machine | Rotation systématique avant toute exposition réseau (checklist, pas de code à écrire) | Avant toute exposition — checklist Sprint 10 |
| 6 | `data-generation/generate_cg_data.py` | Volumétrie "portfolio" (~4 400 ventes) alors que le CA simulé (11,3M€) suggère une vraie PME/ETI | Si présenté comme cas réel sans cette précision, le volume de lignes ne tient pas la comparaison avec une vraie volumétrie CG | Limite assumée pour une démo — augmenter le volume seulement si un test de charge/partitionnement BigQuery le justifie (Sprint 6, FinOps) | Pas de sprint dédié — limite assumée, à mentionner explicitement dans le README si le repo est montré comme référence |

## Règle du jeu

- Chaque nouveau raccourci pris pendant un sprint doit être ajouté ici avant
  de clore le sprint (Definition of Done).
- Une ligne n'est retirée du tableau que quand elle est réellement soldée
  (code écrit, testé) — pas quand elle est simplement reportée.
