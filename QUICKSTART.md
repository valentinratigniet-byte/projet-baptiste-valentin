# Démarrage rapide

Roadmap simple pour faire tourner le projet tel qu'il existe aujourd'hui
(Sprint 1 terminé). Pour le plan de développement complet, voir
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Prérequis

- Docker Desktop installé et lancé
- Python 3.12 (`python --version`)

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

4. **Si les appels HTTPS d'un conteneur échouent** (ex: `ollama pull` avec une
   erreur de certificat) — antivirus/proxy qui intercepte le HTTPS sur cette
   machine :
   ```powershell
   ./scripts/fix-local-ssl.ps1
   docker restart bv-ollama   # ou le conteneur concerné
   ```

5. **Créer l'environnement Python** (isolé, ne touche pas aux autres projets)
   ```bash
   python -m venv .venv
   ./.venv/Scripts/python.exe -m pip install -r requirements.txt
   ```
   Si `pip install` échoue avec une erreur SSL : `./.venv/Scripts/python.exe -m pip install pip-system-certs` puis relancer.

6. **Générer et charger les données**
   ```bash
   ./.venv/Scripts/python.exe data-generation/generate_cg_data.py
   ./.venv/Scripts/python.exe data-generation/generate_logs_mongo.py
   ```

7. **Vérifier que ça tourne**
   - MinIO console : http://localhost:9001
   - n8n : http://localhost:5678 (identifiants dans `.env`)
   - Ollama : `curl http://localhost:11434/api/tags`
   - MySQL : `docker exec bv-mysql-crm mysql -u crm_user -p<mot de passe> crm -e "SELECT COUNT(*) FROM fact_ventes_reel;"`

8. **Tout arrêter** (les données restent dans les volumes Docker)
   ```bash
   docker compose down
   ```

## En cas de blocage

Voir [`docs/DETTE-TECHNIQUE.md`](docs/DETTE-TECHNIQUE.md) — les limites
connues du projet à ce stade y sont listées (ex: le correctif SSL est
spécifique à cette machine).
