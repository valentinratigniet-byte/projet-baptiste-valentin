# Démarrage rapide

Roadmap simple pour faire tourner le projet tel qu'il existe aujourd'hui
(Sprints 1 à 8 terminés). Pour le plan de développement complet, voir
[`docs/ROADMAP.md`](docs/ROADMAP.md).

Les étapes 1 à 11 ci-dessous tournent 100% en local (Docker), sans compte
cloud. La partie BigQuery (Sprint 6, RLS/Policy Tags) est **optionnelle**
et nécessite un vrai projet GCP avec facturation — voir
[`docs/GOUVERNANCE.md`](docs/GOUVERNANCE.md) si tu veux la reproduire.

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

11. **Tout arrêter** (les données restent dans les volumes Docker)
    ```bash
    docker compose down
    ```

## En cas de blocage

Voir [`docs/DETTE-TECHNIQUE.md`](docs/DETTE-TECHNIQUE.md) — les limites
connues du projet à ce stade y sont listées (ex: le correctif SSL est
spécifique à cette machine).
