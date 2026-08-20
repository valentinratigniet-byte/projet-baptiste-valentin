# État des lieux

Dernière mise à jour : Sprint 5 terminé (20/08/2026).

## Avancement

| Sprint | Sujet | Statut |
|---|---|---|
| 1 | Fondations (Docker, générateurs CG, n8n, Ollama) | ✅ terminé |
| 2 | Refonte ERP legacy → cible | ✅ terminé |
| 3 | Data contracts, qualité & RGPD | ✅ terminé |
| 4 | Entrepôt & transformation dbt | ✅ terminé |
| 5 | Hub n8n (reverse ETL, alerting, veille) | ✅ terminé |
| 6 | Gouvernance avancée & FinOps | ⬜ à venir |
| 7 | MLOps (forecasting, drift, chatbot) | ⬜ à venir |
| 8 | KPI Traçabilité interactive | ⬜ à venir |
| 9 | BI (4 tableaux de bord) | ⬜ à venir |
| 10 | Finition | ⬜ à venir |

Détail sprint par sprint avec les chiffres réels de chaque exécution :
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Ce qui tourne aujourd'hui (vérifié, pas déclaratif)

- **Infra** : `docker compose up -d` → MySQL, MongoDB, MinIO, Postgres, n8n, Ollama, tous healthy
- **Données** : 4 442 ventes réelles (CRM) + 2 457 lignes ERP legacy migrées + 23 841 logs applicatifs + budget/forecast (2 232 / 1 674 lignes)
- **Qualité** : 10 contrats JSON Schema, ~35 400 lignes acceptées en Bronze, ~43 rejetées en DLQ (dates ERP invalides)
- **RGPD** : 1 champ personnel identifié et anonymisé (nom de salarié) ; raisons sociales clients volontairement non anonymisées (justifié dans `docs/DATA-CONTRACTS.md`)
- **Entrepôt** : `dbt_cg/`, 21 modèles, **68/68 tests PASS**, écarts Réel/Budget calculés avec de vrais montants, MDM golden record (507 clients)
- **n8n** : 5 workflows versionnés et importables (`n8n/import_workflows.py`), testés y compris après réimport complet sur instance vierge — clôture mensuelle (XLSX → MinIO), alerting budgétaire, veille stratégique (collecte → Ollama → distribution), notification de schéma dbt
- **MDM** : réconciliation client par SIRET + fuzzy-match — précision 54% → **80,2%** (F1 89,0%) depuis l'ajout du SIRET

## Dette technique ouverte

Voir [`docs/DETTE-TECHNIQUE.md`](docs/DETTE-TECHNIQUE.md) — 7 lignes ouvertes
à ce stade (pas de CI, cible BigQuery non connectée, intégrations
Discord/Slack/Drive en placeholder faute de compte externe, etc.), chacune
avec son plafond connu. Rien n'est caché : plusieurs root causes ont été
trouvées et corrigées en cours de route plutôt que contournées (Réel/Budget
sans compte commun, reproductibilité des générateurs, magasin de
certificats Node.js distinct de l'OS).

## Historique des versions

Chaque sprint terminé est tagué comme release GitHub avec ses chiffres :
voir l'onglet [Releases](https://github.com/valentinratigniet-byte/projet-baptiste-valentin/releases).
