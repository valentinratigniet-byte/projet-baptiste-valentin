# État des lieux

Dernière mise à jour : Sprint 9 terminé (21/08/2026).

## Avancement

| Sprint | Sujet | Statut |
|---|---|---|
| 1 | Fondations (Docker, générateurs CG, n8n, Ollama) | ✅ terminé |
| 2 | Refonte ERP legacy → cible | ✅ terminé |
| 3 | Data contracts, qualité & RGPD | ✅ terminé |
| 4 | Entrepôt & transformation dbt | ✅ terminé |
| 5 | Hub n8n (reverse ETL, alerting, veille) | ✅ terminé |
| 6 | Gouvernance avancée & FinOps | ✅ terminé |
| 7 | MLOps (forecasting, drift, chatbot) | ✅ terminé |
| 8 | KPI Traçabilité interactive | ✅ terminé |
| 9 | BI (4 tableaux de bord) | ✅ terminé |
| 10 | Finition | ⬜ à venir |

Détail sprint par sprint avec les chiffres réels de chaque exécution :
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Ce qui tourne aujourd'hui (vérifié, pas déclaratif)

- **Infra locale** : `docker compose up -d` → MySQL, MongoDB, MinIO, Postgres, n8n, Ollama, tous healthy
- **Cloud** : projet GCP dédié `bv-dataplatform` (BigQuery, Data Catalog), distinct du portfolio solo
- **Données** : 4 442 ventes réelles (CRM) + 2 457 lignes ERP legacy migrées + 23 841 logs applicatifs + budget/forecast (2 232 / 1 674 lignes)
- **Qualité** : 10 contrats JSON Schema, ~35 400 lignes acceptées en Bronze, ~43 rejetées en DLQ
- **RGPD** : 1 champ personnel identifié et anonymisé ; raisons sociales clients volontairement non anonymisées (justifié dans `docs/DATA-CONTRACTS.md`)
- **Entrepôt** : `dbt_cg/`, 21 modèles, **68/68 tests PASS**, doc publiée sur [GitHub Pages](https://valentinratigniet-byte.github.io/projet-baptiste-valentin/)
- **n8n** : 5 workflows versionnés et importables, testés après réimport complet sur instance vierge
- **MDM** : réconciliation client SIRET + fuzzy-match — précision 80,2% (F1 89,0%)
- **Gouvernance BigQuery** : RLS + Policy Tags sur `fct_ecarts_reel_budget`, **prouvés par requête réelle** avec 4 comptes de service — RH : 0 ligne + colonne refusée, Finance/Direction/PDG : 2 240 lignes, 11 847 943,82€
- **CI/CD** : pipeline complet vert sur GitHub Actions à chaque push ; `dbt docs` auto-publié
- **MLOps** : forecasting Holt (statsmodels) sur `fct_ecarts_reel_budget` → `marts.ml_forecast_reel` ; détection de drift (Evidently AI) sur le flux CRM, 60% des colonnes suivies en dérive entre les deux moitiés chronologiques du jeu de données ; chatbot BI Text-to-SQL (Ollama local + BigQuery, `direction-viewer`, dry_run avant exécution) évalué à **60% d'execution accuracy** (10 questions, vérité terrain) — détail et chiffres complets dans [`docs/MLOPS.md`](docs/MLOPS.md)
- **Traçabilité KPI** : `traceability/index.html` (repris du prototype solo `projet-14-filiation`), 32 nœuds introspectés depuis `dbt_cg` (11 sources, 10 staging, 11 marts), 107 colonnes avec lignage colonne-à-colonne réel (sqlglot). Nouveau par rapport au prototype : `erp-fiche.html`, fiche ERP legacy cliquable en lecture seule (2 500 lignes, recherche par NUMPCE/CDCLI) liée depuis les nœuds sources `erp_migre` — détail dans [`docs/TRACABILITE-KPI.md`](docs/TRACABILITE-KPI.md)
- **BI** : `dashboards/index.html`, 4 tableaux de bord HTML/JS maison (Power BI/Looker Studio prévus au départ, mais aucun des deux n'est pilotable par API pour les visuels). CA réel 19,1 M€, écart Réel/Budget +1,03 M€, RLS+masking BigQuery prouvés en direct (rh-viewer : 0 ligne + colonne refusée ; Finance/Direction/PDG : 2 240 lignes, 11 847 943,82€), infobulles reliées à la traçabilité du Sprint 8 — détail dans [`docs/BI.md`](docs/BI.md)
- **BI Power BI** : rapport **Pilotage CG** (`dashboards/powerbi/dbt_cg.pbix`), construit par Valentin en autonomie dans Power BI Desktop avec le modèle sémantique préparé côté assistant (MCP `powerbi-modeling`, couche modèle uniquement). 4 pages (Vue direction, Contrôle de gestion, RH & Opérationnel, FinOps/Audit), 14 tables, 17 mesures DAX, RLS 4 rôles testée par requête réelle (piège DAX `COUNTROWS` sous filtre `FALSE()` → `BLANK` et non `0`, corrigé) — détail complet dans [`docs/BI-POWERBI.md`](docs/BI-POWERBI.md)

## Dette technique ouverte

Voir [`docs/DETTE-TECHNIQUE.md`](docs/DETTE-TECHNIQUE.md) — 8 lignes
ouvertes à ce stade (RLS/masking limité à 1 table sur 11 par choix de
profondeur, intégrations Discord/Slack/Drive en placeholder faute de
compte externe, chatbot sans routage RLS par profil, détection de drift
sur un seul run, etc.), chacune avec son plafond connu. Rien n'est caché :
plusieurs root causes ont été trouvées et corrigées en cours de route
plutôt que contournées — dont trois pièges SSL différents sur trois piles
réseau distinctes (OpenSSL, Node.js, gRPC) et une collision de variable
d'environnement avec un autre projet GCP sur la même machine.

## Historique des versions

Chaque sprint terminé est tagué comme release GitHub avec ses chiffres :
voir l'onglet [Releases](https://github.com/valentinratigniet-byte/projet-baptiste-valentin/releases).
