# Architecture technique

Stack 100% gratuite/open-source : Docker (local) + BigQuery Free Tier (cloud) + GitHub Actions (CI/CD).

```
┌────────────────────────── SOURCES (Docker local) ──────────────────────────┐
│  MySQL (CRM)   MongoDB (Logs)   APIs externes   Générateurs Python          │
│                                  (Réel / Budget / Forecast / Centres coûts) │
└───────────────┬──────────────────────────────────────────┬────────────────┘
                │ extract (Python)                          │ veille (n8n)
                ▼                                            ▼
   ┌─────────────────────────┐                    ┌───────────────────────┐
   │ Data Contracts           │                    │ n8n : collecte web     │
   │ JSON Schema + Dead-Letter│                    │ Finance / Bourse / IA  │
   │ Anonymisation RGPD       │                    └──────────┬─────────────┘
   └────────────┬─────────────┘                                │
                ▼                                              ▼
   ┌─────────────────────────┐                    ┌───────────────────────┐
   │ MinIO (Bronze, S3-compat)│                    │ Ollama (résumé IA      │
   └────────────┬─────────────┘                    │ locale, gratuit)       │
                │ load (Python / dbt seeds)         └──────────┬─────────────┘
                ▼                                              │ distribution
   ┌───────────────────────────────────────────┐               ▼
   │ BigQuery (Silver/Gold) — source de vérité   │     ┌───────────────────┐
   │ dbt-core : écarts Réel/Budget, allocations,  │     │ Discord/Slack/Email│
   │ analytiques, MDM, RLS + masking (Policy Tags)│     │ (direction)         │
   │ partitionnement + rétention (FinOps)         │     └───────────────────┘
   └───────────────┬───────────────┬─────────────┘
        read-only   │               │  read-only (déclenche reverse ETL)
                    ▼               ▼
   ┌────────────────────┐   ┌──────────────────────────┐
   │ BI (Power BI /       │   │ n8n : liasse de clôture    │
   │ Looker Studio)        │   │ mensuelle (Excel) → Drive   │
   │ TdB PDG/CG/RH/FinOps  │   │ + alerting dépassement      │
   └────────────────────┘   │ budgétaire (Discord/Slack)  │
                              └──────────────────────────┘

   ┌───────────────────────────────────────────┐
   │ MLOps (lit BigQuery en lecture seule)       │
   │ - Forecasting métier (Python)               │
   │ - Data Drift (Evidently AI)                 │
   │ - Chatbot BI Text-to-SQL (Ollama)            │
   └───────────────────────────────────────────┘

   CI/CD (GitHub Actions) : dbt docs → GitHub Pages à chaque merge
                             n8n notifie les changements de schéma
```

## Règle d'or

n8n et la BI ne lisent **jamais** la donnée brute (Bronze/MinIO ou sources). Ils
consomment uniquement les tables Gold exposées par dbt sur BigQuery, en lecture
seule. Toute écriture vers un système externe (Excel, Drive, alerte) part de
Gold, jamais de la source.

## Environnements dbt

- **dev** → Postgres local (`docker-compose`, port `5434`)
- **prod** → BigQuery (service account, clé jamais commit — voir `.env.example`)

Bascule via `--target` dans `profiles.yml`.
