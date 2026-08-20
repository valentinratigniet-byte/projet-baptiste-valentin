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

Modèle `llama3.2:1b` déjà tiré (petit modèle local, suffisant pour prototyper
le résumé de veille et le chatbot Text-to-SQL des sprints suivants) :

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
