# Checklist rotation des secrets avant exposition réseau

À exécuter **avant** de rendre un service de ce projet accessible au-delà de
cette machine (déploiement cloud, tunnel public, partage réseau local).
Tant que tout reste sur `localhost`, les valeurs par défaut de `.env` sont
acceptables (dette technique assumée, voir `docs/DETTE-TECHNIQUE.md`).

## Secrets applicatifs (`.env`)

- [ ] `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD` — remplacer `changeme`
- [ ] `MONGO_PASSWORD` — remplacer `changeme`
- [ ] `MINIO_ROOT_PASSWORD` — remplacer `changeme123`
- [ ] `POSTGRES_PASSWORD` — remplacer `changeme`
- [ ] `N8N_ADMIN_PASSWORD` — remplacer `ChangeMe123!`, réinitialiser via
      l'UI n8n (`/rest/owner/setup` ne fonctionne qu'une fois)
- [ ] `ANONYMIZATION_SALT` — regénérer (`python -c "import secrets;
      print(secrets.token_hex(16))"`) — **change le résultat des hash
      d'anonymisation déjà en base**, à ne faire qu'une fois avant mise en
      prod, pas après

## Secrets cloud (GCP)

- [ ] Vérifier qu'aucune clé de compte de service (`~/.gcp/*.json`) n'a été
      commit par erreur : `git log --all --full-history -- '*.json'` sur
      les dossiers `governance/`, racine, `.gcp` ne doit rien remonter
      hors du repo (ces clés ne sont jamais dans le repo par construction,
      mais vérifier après tout `git add -A`)
- [ ] Faire tourner les clés des comptes de service si la machine de dev a
      été partagée ou compromise : `gcloud iam service-accounts keys list`
      puis `gcloud iam service-accounts keys delete` sur les anciennes
- [ ] Limiter `roles/bigquery.dataOwner` et `roles/bigquery.securityAdmin`
      du compte `dbt-loader` si le pipeline prod tourne en continu sans
      besoin de recréer des RLS/Policy Tags (rôles utilisés une fois au
      setup, pas à chaque `dbt build`)

## Avant tout partage du repo (public ou avec Baptiste)

- [ ] `git status` propre, `.env` non suivi (vérifier `.gitignore`)
- [ ] `docker exec bv-minio-bronze mc admin user list local` — pas de
      credentials MinIO par défaut si le bucket devient accessible
      au-delà de `localhost`
- [ ] Relire `docs/DATA-CONTRACTS.md` : les données restent synthétiques
      (aucune donnée personnelle réelle), donc pas de risque RGPD au
      partage — à revalider si un jour de vraies données remplacent les
      données générées
