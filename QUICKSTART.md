# Démarrage rapide

Séquence complète pour rejouer le projet de A à Z tel qu'il existe
aujourd'hui (**10/10 sprints terminés**). Pour le plan de développement
détaillé sprint par sprint, voir [`docs/ROADMAP.md`](docs/ROADMAP.md).

Les étapes 1 à 12 tournent 100% en local (Docker), sans compte cloud —
c'est la seule partie strictement nécessaire pour voir tourner le pipeline
et la BI. Les étapes 13 à 15 (BigQuery, MLOps, Power BI) sont **optionnelles**
et nécessitent respectivement un projet GCP avec facturation et Power BI
Desktop — chacune le précise.

## Prérequis

- Docker Desktop installé et lancé
- Python 3.12 (`python --version`)

## Ordre important

Les étapes 6 à 8 doivent s'exécuter **dans cet ordre exact** : chacune lit
ce que la précédente a écrit (générateurs → data contracts/Bronze →
migration ERP → chargement `raw` → dbt). Changer l'ordre fait planter une
étape sur des données manquantes.

## Étapes

1. **Récupérer le projet** (clone Git ou dézipper l'archive) puis se placer
   dans le dossier `projet-baptiste-valentin/`.

2. **Copier la config**
   ```bash
   cp .env.example .env
   ```
   Éditer `.env` si besoin (mots de passe par défaut suffisants en local).

3. **Démarrer l'infrastructure**
   ```bash
   docker compose up -d
   docker compose ps   # tout doit être "healthy" ou "Up"
   ```
   Premier lancement = téléchargement des images, peut prendre quelques minutes.

4. **Si les appels HTTPS d'un conteneur échouent** (ex: `ollama pull`, ou le
   workflow de veille n8n) — antivirus/proxy qui intercepte le HTTPS sur
   cette machine :
   ```powershell
   ./scripts/fix-local-ssl.ps1 -Containers bv-ollama
   ./scripts/fix-local-ssl.ps1 -Containers bv-n8n
   docker restart bv-ollama bv-n8n
   ```
   n8n (Node.js) a en plus besoin de `NODE_EXTRA_CA_CERTS` (déjà dans
   `docker-compose.yml`) — voir [`docs/N8N.md`](docs/N8N.md) si ça persiste.

5. **Créer l'environnement Python** (isolé, ne touche pas aux autres projets)
   ```bash
   python -m venv .venv
   ./.venv/Scripts/python.exe -m pip install -r requirements.txt
   ```
   Si `pip install` échoue avec une erreur SSL : `./.venv/Scripts/python.exe -m pip install pip-system-certs` puis relancer.

6. **Générer les données sources**
   ```bash
   ./.venv/Scripts/python.exe data-generation/generate_cg_data.py
   ./.venv/Scripts/python.exe data-generation/generate_logs_mongo.py
   ./.venv/Scripts/python.exe erp-legacy/generate_erp_legacy_export.py
   ```

7. **Valider (contrats JSON Schema + RGPD), migrer l'ERP, charger l'entrepôt**
   ```bash
   ./.venv/Scripts/python.exe data-contracts/ingest_to_bronze.py      # Bronze + DLQ
   ./.venv/Scripts/python.exe erp-legacy/migrate_erp_to_target.py     # lit Bronze -> erp_migre
   ./.venv/Scripts/python.exe data-contracts/load_bronze_to_raw.py    # Bronze -> Postgres (raw)
   ```

8. **Construire l'entrepôt dbt**
   ```bash
   cd dbt_cg && DBT_PROFILES_DIR=. ../.venv/Scripts/dbt.exe build
   ```
   68 tests doivent passer. Les marts (`fct_ecarts_reel_budget`, `dim_client`
   golden record, etc.) sont dans le schéma `public_marts` de Postgres.

9. **Importer et activer les workflows n8n**
   ```bash
   ./.venv/Scripts/python.exe n8n/import_workflows.py
   ```
   Recrée les credentials (Postgres, MinIO) et importe les 5 workflows,
   déjà activés.

10. **Vérifier que ça tourne**
    - MinIO console : http://localhost:9001 (buckets `bronze`/`rejects`/`gold-exports`/`veille`)
    - n8n : http://localhost:5678 (identifiants dans `.env`)
    - Ollama : `curl http://localhost:11434/api/tags`
    - Postgres : `docker exec bv-postgres-dbtdev psql -U dbt_user -d dbt_dev -c "SELECT * FROM public_marts.fct_allocation_couts;"`
    - n8n : `curl -X POST http://localhost:5678/webhook/trigger-cloture-mensuelle`

11. **Traçabilité KPI** — ouvrir [`traceability/index.html`](traceability/index.html)
    directement dans un navigateur (aucun serveur requis, déjà généré depuis
    `dbt_cg`). Détail : [`docs/TRACABILITE-KPI.md`](docs/TRACABILITE-KPI.md).

12. **Tableaux de bord BI**
    ```bash
    ./.venv/Scripts/python.exe dashboards/scripts/export_dashboard_data.py
    ```
    Régénère les données depuis Postgres dev, puis ouvrir
    [`dashboards/index.html`](dashboards/index.html) (aucun serveur requis).
    L'onglet FinOps se dégrade silencieusement (best-effort) si l'étape 13
    (BigQuery) n'a pas été faite. Détail : [`docs/BI.md`](docs/BI.md).

## Optionnel — cloud & extensions (Sprints 6, 7, 9)

Tout ce qui suit dépend d'un projet GCP réel (facturation active) et n'est
donc pas requis pour voir tourner le pipeline. Skip si tu veux juste la
partie locale.

13. **Gouvernance BigQuery (RLS + masking)**
    ```bash
    ./.venv/Scripts/python.exe governance/sync_marts_to_bigquery.py
    ./.venv/Scripts/python.exe governance/apply_rls_and_masking.py
    ./.venv/Scripts/python.exe governance/test_acces_par_profil.py
    ```
    Nécessite un projet GCP dédié + `BQ_KEYFILE`/`BQ_PROJECT`/`BQ_DATASET`
    dans `.env` (comptes de service, voir `docs/GOUVERNANCE.md`) et le
    piège gRPC (`GRPC_CA_BUNDLE`) si les appels HTTPS échouent. Détail
    complet, IAM, chiffres réels : [`docs/GOUVERNANCE.md`](docs/GOUVERNANCE.md).

14. **MLOps** (forecasting + chatbot dépendent de l'étape 13 ; le drift non)
    ```bash
    ./.venv/Scripts/python.exe mlops/forecast.py            # -> marts.ml_forecast_reel (BigQuery)
    ./.venv/Scripts/python.exe mlops/drift_detection.py      # -> mlops/reports/drift_report.html (Postgres seul)
    ./.venv/Scripts/python.exe mlops/chatbot/text_to_sql.py  # chatbot interactif (Ollama + BigQuery)
    ```
    Détail, limites et chiffres réels : [`docs/MLOPS.md`](docs/MLOPS.md).

15. **Rapport Power BI** — `dashboards/powerbi/dbt_cg.pbix` est livré tel
    quel dans le repo (pas de script : construit à la main dans Power BI
    Desktop, connecté à Postgres dev `127.0.0.1:5434`/`dbt_dev`). L'ouvrir
    directement pour l'explorer, ou suivre
    [`docs/BI-POWERBI.md`](docs/BI-POWERBI.md) pour le refaire de zéro
    (modèle, mesures DAX, RLS).

## Vérification & arrêt

16. **Tests end-to-end** (rejoue tout le pipeline et vérifie le résultat
    réel à chaque étape, pas juste que les commandes rendent la main)
    ```bash
    ./.venv/Scripts/python.exe tests/test_e2e_pipeline.py
    ```

17. **Tout arrêter** (les données restent dans les volumes Docker)
    ```bash
    docker compose down
    ```

## En cas de blocage

Voir [`docs/DETTE-TECHNIQUE.md`](docs/DETTE-TECHNIQUE.md) — les limites
connues du projet à ce stade y sont listées (ex: le correctif SSL est
spécifique à cette machine).
