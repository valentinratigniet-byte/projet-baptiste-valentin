# Data Platform — Contrôle de Gestion & Pilotage d'entreprise

Projet binôme Baptiste / Valentin. Simulation end-to-end de la data platform
et du DataOps d'une entreprise multi-millions d'euros, stack 100% gratuite.

- [`QUICKSTART.md`](QUICKSTART.md) — démarrer le projet en 8 étapes simples
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — schéma du pipeline
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — plan de développement complet (10 sprints)
- [`docs/MCD.md`](docs/MCD.md) — modèle conceptuel Réel/Budget/Forecast
- [`docs/DETTE-TECHNIQUE.md`](docs/DETTE-TECHNIQUE.md) — raccourcis pris et leur plafond connu
- [`docs/REFONTE-ERP.md`](docs/REFONTE-ERP.md) — diagnostic, mapping et migration de l'ERP legacy simulé
- [`docs/DATA-CONTRACTS.md`](docs/DATA-CONTRACTS.md) — contrats JSON Schema, DLQ et classification RGPD

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
> <conteneur>` pour qu'il recharge son pool de certificats.

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

Un premier workflow de test existe (`Test - Webhook vers log`, actif) :
`POST http://localhost:5678/webhook/test-log` déclenche un node `Set` qui
horodate la réception — sert de gabarit pour les workflows du Sprint 5
(reverse ETL, alerting, veille).

## Ollama

Modèle `llama3.2:1b` déjà tiré (petit modèle local, suffisant pour prototyper
le résumé de veille et le chatbot Text-to-SQL des sprints suivants) :

```bash
curl http://localhost:11434/api/generate -d '{"model":"llama3.2:1b","prompt":"Bonjour","stream":false}'
```

## ERP legacy & migration

```bash
./.venv/Scripts/python.exe erp-legacy/generate_erp_legacy_export.py
./.venv/Scripts/python.exe erp-legacy/migrate_erp_to_target.py
```

Simule un export ERP legacy (2 500 lignes, avant le CRM), le nettoie, le
réconcilie avec le CRM par fuzzy matching et le charge dans Postgres
(schéma `erp_migre`). Détail complet, résultats chiffrés et limites
connues : [`docs/REFONTE-ERP.md`](docs/REFONTE-ERP.md).

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
