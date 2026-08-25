# Data Platform — Contrôle de Gestion & Pilotage d'entreprise

Projet binôme Baptiste / Valentin. Simulation end-to-end de la data platform
et du DataOps d'une entreprise multi-millions d'euros, stack 100% gratuite.

- [`STATUS.md`](STATUS.md) — **état des lieux** : où en est le projet, ce qui tourne, dette ouverte
- [`QUICKSTART.md`](QUICKSTART.md) — démarrer le projet étape par étape
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — schéma du pipeline
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — plan de développement complet (10 sprints)
- [`docs/MCD.md`](docs/MCD.md) — modèle conceptuel Réel/Budget/Forecast
- [`docs/DETTE-TECHNIQUE.md`](docs/DETTE-TECHNIQUE.md) — raccourcis pris et leur plafond connu
- [`docs/REFONTE-ERP.md`](docs/REFONTE-ERP.md) — diagnostic, mapping et migration de l'ERP legacy simulé
- [`docs/DATA-CONTRACTS.md`](docs/DATA-CONTRACTS.md) — contrats JSON Schema, DLQ et classification RGPD
- [`docs/DBT.md`](docs/DBT.md) — entrepôt dbt : couches, MDM, écarts Réel/Budget, allocations, tests
- [`docs/N8N.md`](docs/N8N.md) — les 5 workflows, réconciliation SIRET, piège SSL Node.js
- [`docs/GOUVERNANCE.md`](docs/GOUVERNANCE.md) — RLS + Policy Tags BigQuery, prouvés par requête réelle
- [`docs/SECRETS-CHECKLIST.md`](docs/SECRETS-CHECKLIST.md) — rotation des secrets avant exposition réseau
- [`docs/MLOPS.md`](docs/MLOPS.md) — forecasting, détection de drift, chatbot BI Text-to-SQL
- [`docs/TRACABILITE-KPI.md`](docs/TRACABILITE-KPI.md) — outil interactif de traçabilité KPI + fiche ERP native
- [`docs/BI.md`](docs/BI.md) — 4 tableaux de bord (PDG, CG, RH, FinOps), preuve RLS/masking en direct
- [`docs/BI-POWERBI.md`](docs/BI-POWERBI.md) — rapport Power BI Pilotage CG, modèle sémantique, RLS testée
- **Doc dbt en ligne** : https://valentinratigniet-byte.github.io/projet-baptiste-valentin/

## Démarrer l'infra locale

```bash
cp .env.example .env   # puis éditer les mots de passe
docker compose up -d
```

Services : MySQL `3306`, MongoDB `27017`, MinIO `9000`/console `9001`,
Postgres (dbt dev) `5434`, n8n `5678`, Ollama `11434`.

> Sur cette machine, **Avast** (Web/Mail Shield) intercepte le HTTPS avec son
> propre certificat racine. Ça casse `pip install` (fixé par `pip-system-certs`,
> voir ci-dessous) et les appels HTTPS sortants des conteneurs (ex: Ollama qui
> télécharge un modèle). Pour les conteneurs : `./scripts/fix-local-ssl.ps1`
> (auto-détecte Avast ; `-List` pour identifier le bon certificat sur une
> autre machine, `-CertPattern "..."` pour le cibler), puis `docker restart
> <conteneur>` pour qu'il recharge son pool de certificats. **n8n en plus** :
> Node.js a son propre magasin de certificats (`NODE_EXTRA_CA_CERTS`, déjà
> configuré dans `docker-compose.yml`) — voir [`docs/N8N.md`](docs/N8N.md).

## Environnement Python

Venv dédié à ce projet (isolé de `portfolio-data`), Python 3.12 (le 3.9 système
a un bug qui bloque dbt) :

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Génération des données de contrôle de gestion

```bash
./.venv/Scripts/python.exe data-generation/generate_cg_data.py
```

Génère les dimensions + Réel/Budget/Forecast, charge `dim_client`,
`dim_produit`, `fact_ventes_reel` dans MySQL (CRM), et écrit
`dim_centre_cout`, `dim_compte`, `dim_version_budget`, `fact_budget`,
`fact_forecast` en CSV dans `data-generation/output/` (simule un export
Finance, ingéré en Bronze via les data contracts — voir plus bas).

```bash
./.venv/Scripts/python.exe data-generation/generate_logs_mongo.py
```

Génère des logs applicatifs (login/vues produit/panier/achat/erreurs,
cohérents avec les IDs clients/produits MySQL) dans MongoDB
(`logs.app_events`).

## n8n

Compte owner créé au setup, identifiants dans `.env`
(`N8N_ADMIN_EMAIL`/`N8N_ADMIN_PASSWORD`). Interface : http://localhost:5678

```bash
./.venv/Scripts/python.exe n8n/import_workflows.py
```

Importe les 5 workflows versionnés (`n8n/workflows/*.json`) : clôture
mensuelle, alerting budgétaire, veille stratégique, notification de
changement de schéma, webhook de test. Recrée les credentials Postgres/MinIO
automatiquement. Détail, limites et résultats réels :
[`docs/N8N.md`](docs/N8N.md).

## Ollama

Modèle `llama3.2:1b` déjà tiré (petit modèle local, suffisant pour le résumé
de veille et le chatbot Text-to-SQL du Sprint 7, `docs/MLOPS.md`) :

```bash
curl http://localhost:11434/api/generate -d '{"model":"llama3.2:1b","prompt":"Bonjour","stream":false}'
```

## ERP legacy & migration

```bash
./.venv/Scripts/python.exe erp-legacy/generate_erp_legacy_export.py
```

Simule un export ERP legacy (2 500 lignes, avant le CRM). Diagnostic
complet : [`docs/REFONTE-ERP.md`](docs/REFONTE-ERP.md). La migration
proprement dite (`erp-legacy/migrate_erp_to_target.py`) se lance après les
data contracts — voir la chaîne complète ci-dessous.

## Data contracts, qualité & RGPD

```bash
./.venv/Scripts/python.exe data-contracts/ingest_to_bronze.py
```

Valide chaque flux (CRM, logs, Finance, ERP legacy) contre son contrat
JSON Schema, anonymise le seul champ réellement personnel identifié
(`responsable` d'un centre de coût), et route vers MinIO : conforme →
`bronze/<flux>/`, rejeté → `rejects/<flux>/` avec le motif. Détail des 10
contrats et de la classification RGPD :
[`docs/DATA-CONTRACTS.md`](docs/DATA-CONTRACTS.md).

```bash
docker exec bv-minio-bronze mc ls local/bronze --recursive
```

## Entrepôt dbt (marts Contrôle de Gestion)

Chaîne complète, dans l'ordre (chaque étape dépend de la précédente) :

```bash
./.venv/Scripts/python.exe data-contracts/ingest_to_bronze.py      # Bronze + DLQ
./.venv/Scripts/python.exe erp-legacy/migrate_erp_to_target.py     # lit Bronze -> erp_migre
./.venv/Scripts/python.exe data-contracts/load_bronze_to_raw.py    # Bronze -> Postgres schéma raw
cd dbt_cg && DBT_PROFILES_DIR=. ../.venv/Scripts/dbt.exe build
```

21 modèles (staging + marts), 68 tests dbt. Écarts Réel/Budget, MDM golden
record client, allocations analytiques : détail et chiffres réels dans
[`docs/DBT.md`](docs/DBT.md).

## Gouvernance BigQuery (RLS + masking)

```bash
./.venv/Scripts/python.exe governance/sync_marts_to_bigquery.py
./.venv/Scripts/python.exe governance/apply_rls_and_masking.py
./.venv/Scripts/python.exe governance/test_acces_par_profil.py
```

Projet GCP dédié `bv-dataplatform`. Row-Level Security + Policy Tags sur
`fct_ecarts_reel_budget`, prouvés par requête réelle avec 4 comptes de
service (RH/Finance/Direction/PDG) — RH voit 0 ligne et se fait refuser la
colonne sensible, les 3 autres voient tout. Détail complet, chiffres réels,
3 root causes trouvées en route (dont un 3ᵉ piège SSL, côté gRPC) :
[`docs/GOUVERNANCE.md`](docs/GOUVERNANCE.md).

## MLOps (forecasting, drift, chatbot BI)

```bash
./.venv/Scripts/python.exe mlops/forecast.py            # -> marts.ml_forecast_reel
./.venv/Scripts/python.exe mlops/drift_detection.py      # -> mlops/reports/drift_report.html
./.venv/Scripts/python.exe mlops/chatbot/text_to_sql.py  # chatbot Text-to-SQL interactif (Ollama + BigQuery)
```

Lissage de Holt sur `fct_ecarts_reel_budget`, détection de drift (Evidently
AI), chatbot Text-to-SQL avec dry_run avant exécution. Chiffres réels et
limites (dette #8) : [`docs/MLOPS.md`](docs/MLOPS.md).

## Traçabilité KPI

Ouvrir [`traceability/index.html`](traceability/index.html) (aucune
dépendance, aucun serveur) : clic sur n'importe quelle source/colonne/modèle
→ remonte le lignage jusqu'à la donnée brute, plus une fiche ERP native en
lecture seule pour les tables issues de la migration Sprint 2. Régénérer
après un `dbt run`/`dbt test` : voir [`docs/TRACABILITE-KPI.md`](docs/TRACABILITE-KPI.md).

## Tableaux de bord BI

Ouvrir [`dashboards/index.html`](dashboards/index.html) (aucune dépendance,
aucun serveur) : 4 onglets (Exécutif/PDG, Contrôle de gestion, RH &
Opérationnel, FinOps/Audit), données réelles régénérées par
`dashboards/scripts/export_dashboard_data.py`. Détail et chiffres complets :
[`docs/BI.md`](docs/BI.md).

## Rapport Power BI

`dashboards/powerbi/dbt_cg.pbix` (rapport **Pilotage CG**, 4 pages :
Vue direction, Contrôle de gestion, RH & Opérationnel, FinOps/Audit).
Modèle sémantique construit avec Valentin (14 tables, 17 mesures DAX,
RLS 4 rôles testée par requête réelle), visuels conçus par Valentin.
Captures dans `dashboards/powerbi/outputs/`, détail complet dans
[`docs/BI-POWERBI.md`](docs/BI-POWERBI.md).

## Tests end-to-end

```bash
./.venv/Scripts/python.exe tests/test_e2e_pipeline.py
```

Rejoue tout le pipeline (source → Bronze → raw → Gold dbt → BI → reverse
ETL n8n) sur les services Docker locaux et vérifie le résultat réel à
chaque étape (lignes chargées, `dbt build` 47/47 tests, marts non vides,
fichier XLSX effectivement déposé sur MinIO par le webhook n8n) — pas
seulement que les commandes rendent la main sans erreur.

## CI/CD

- **CI** (`.github/workflows/ci.yml`) : pipeline complet (générateurs,
  self-checks, data contracts, migration ERP, `dbt build`) à chaque push,
  sur services MySQL/Mongo/MinIO/Postgres éphémères.
- **dbt docs** (`.github/workflows/dbt-docs.yml`) : publié sur GitHub Pages
  à chaque changement dans `dbt_cg/`.
