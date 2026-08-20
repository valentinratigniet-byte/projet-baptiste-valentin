# Roadmap — 10 sprints (2 semaines chacun, ~20 semaines)

Roadmap détaillée pour développer le projet à fond. Conçue à l'origine pour
un binôme (répartition Valentin = Data Engineering/dbt/BigQuery, Baptiste =
Automatisation/BI/Gouvernance) — actuellement exécutée en solo, sprints 2+
sans split de rôle. Dette technique trackée dans
[`DETTE-TECHNIQUE.md`](DETTE-TECHNIQUE.md), mise à jour à chaque fin de
sprint.

## Sprint 1 — Fondations ✅ terminé
- `docker-compose.yml` (MySQL, MongoDB, MinIO, Postgres dbt-dev, n8n, Ollama), structure repo, README, `.env.example`
- Venv Python isolé (3.12, `pip-system-certs`)
- Générateurs Python (Réel/Budget/Forecast/Centres de coûts), chargement MySQL + Mongo
- n8n : compte owner, premier workflow de test (webhook → log), activé et validé
- Ollama : modèle `llama3.2:1b` opérationnel
- Root cause SSL trouvée et corrigée (Avast Web/Mail Shield, pas juste contournée)

## Sprint 2 — Refonte ERP (legacy → cible) ✅ terminé
Nouveau chantier : démontrer une vraie compétence de refonte ERP, pas
seulement de la génération de données propres.
- Simuler un ERP legacy réaliste : schéma plat dénormalisé, codes obscurs
  (`M001`, `TY3`...), doublons, pas de clés étrangères déclarées, NULL non
  gérés, export en CSV/Excel bruts (typique d'un vieux progiciel mal
  exploité, style AS/400 ou SAP mal paramétré)
- Diagnostic écrit : dette du schéma legacy, incohérences relevées, volumétrie,
  risques identifiés
- Mapping legacy → modèle cible : correspondance champ par champ vers les
  dimensions/faits du MCD (`docs/MCD.md`)
- Plan de migration par lots (phases, stratégie de non-régression, rollback)
- Migration effective d'un sous-ensemble (contrôle de gestion) vers le
  pipeline construit aux sprints suivants
- Livrable : `docs/REFONTE-ERP.md` (diagnostic + mapping + plan)

  → tout réalisé : export legacy simulé (2 500 lignes, `erp-legacy/exports/`),
  réconciliation client par fuzzy matching évaluée (précision 54%/rappel
  100%/F1 70,1% — plafond de données réel et documenté, pas un bug),
  mapping centre de coût, chargement dans Postgres (`erp_migre`), 2% de
  lignes flaggées à corriger plutôt que rejetées silencieusement. Dette
  ajoutée : absence de SIRET dans les deux générateurs (`DETTE-TECHNIQUE.md`
  #7/#8, ciblée Sprint 4).

## Sprint 3 — Data Contracts, Qualité & Bronze ✅ terminé
- Schémas JSON Schema pour chaque flux (CRM, logs, Finance CSV, exports ERP legacy du Sprint 2)
- Validation à l'ingestion + Dead-Letter-Queue pour les rejets
- Anonymisation RGPD (pseudonymisation des identifiants clients/personnes)
- Écriture vers MinIO (bronze/, rejects/)
- Ajout des self-checks `demo()` sur les générateurs Sprint 1 (dette #2)
- Généralisation du script SSL (dette #1)

  → tout réalisé : 10 schémas JSON Schema (`data-contracts/schemas/`),
  pipeline unique `ingest_to_bronze.py` couvrant les 10 flux (MySQL, Mongo,
  CSV Finance, CSV ERP legacy), 35 269 enregistrements acceptés → `bronze/`,
  51 rejetés → `rejects/` (exactement les 51 dates invalides déjà repérées
  au Sprint 2 — cohérence vérifiée). RGPD : un seul champ réellement
  personnel identifié (`responsable`, nom de salarié) et anonymisé par hash
  irréversible ; raisons sociales clients délibérément non anonymisées
  (personnes morales, hors RGPD) — voir `docs/DATA-CONTRACTS.md` pour la
  justification. Dette #1 et #2 (SSL, self-checks) soldées ; 2 nouvelles
  dettes ouvertes (#7 pipeline sans self-check, #8 migration ERP non
  branchée sur Bronze), ciblées Sprint 4.

## Sprint 4 — Entrepôt & Transformation ✅ terminé
- dbt multi-target opérationnel (Postgres dev / BigQuery prod)
- Modèles Silver : staging propre sur toutes les sources (CRM, ERP migré, Finance)
- `fct_ecarts_reel_budget` : agrégation Réel au grain Budget, calcul écart et %
- Allocations analytiques (répartition de charges indirectes entre centres de coûts)
- Master Data Management : dédoublonnage/golden record sur les entités issues de la fusion CRM + ERP legacy
- Tests dbt (not_null, unique, relationships, accepted_values) sur tous les modèles

  → tout réalisé, détail complet dans `docs/DBT.md` : projet `dbt_cg/`
  (cible dev Postgres fonctionnelle, cible prod BigQuery prête mais non
  connectée — dette #8), nouveau loader `data-contracts/load_bronze_to_raw.py`
  (Bronze → schéma `raw`), 21 modèles (10 staging + 11 marts), **68/68 tests
  dbt PASS**. `fct_ecarts_reel_budget` fonctionne avec des écarts réels
  (ex. +62% sur un centre en janvier) après correction d'une root cause
  découverte en le construisant (Réel et Budget ne partageaient aucun
  compte). `dim_client` golden record : 505 clients (500 CRM + 5 legacy-only
  résolus). `fct_allocation_couts` livré avec un écart de périmètre assumé
  et documenté (ventile du CA, pas des charges — dette #7). Un deuxième bug
  de reproductibilité trouvé et corrigé au passage (`demo()` décalait l'état
  aléatoire de `main()`). Dette #1/#2 (Sprint 3) définitivement soldées ;
  #5/#6 (SIRET) reportées à Sprint 5, faute de temps ce sprint-ci.

## Sprint 5 — Hub n8n
- Reverse ETL : génération de la liasse de clôture mensuelle (Excel) → dépôt Drive
- Alerting dépassement budgétaire (Discord/Slack/Email) déclenché depuis Gold, jamais depuis la source
- Veille stratégique : collecte APIs (Finance/Bourse/IA/Pilotage d'entreprise) → résumé Ollama → distribution
- Workflows exportés en JSON versionné dans `n8n/workflows/` + script d'import (dette #3)
- Notification n8n des changements de schéma dbt (webhook déclenché en CI)

## Sprint 6 — Gouvernance avancée & FinOps
- Row-Level Security (RLS) sur BigQuery, par profil (RH/Finance/Direction/PDG)
- Column-Level Security / Dynamic Masking via Policy Tags (données sensibles : salaires, marges)
- Partitionnement et règles de rétention (FinOps, contrôle des coûts BigQuery)
- CI/CD GitHub Actions : `dbt docs` → GitHub Pages à chaque merge
- Pipeline CI complet (lint + self-checks générateurs + `dbt build` dev) — solde la dette #4
- Checklist rotation des secrets avant toute exposition réseau (dette #5)

## Sprint 7 — MLOps
- Forecasting métier (Python, séries temporelles sur `fct_ecarts_reel_budget`)
- Détection de data drift (Evidently AI) sur les flux Bronze/Silver
- Chatbot BI Text-to-SQL : Ollama local interrogeant BigQuery en lecture seule
- Évaluation du chatbot sur un jeu de questions/réponses métier avec vérité terrain

## Sprint 8 — KPI Traçabilité interactive
Nouvelle fonctionnalité : reprise et adaptation du pattern du projet
Filiation (portfolio solo, `projet-14-filiation`) à ce projet binôme.
- Page interactive (HTML/CSS/JS vanilla, sans dépendance) : clic sur
  n'importe quel indicateur/colonne/table → remonte sa formule/SQL jusqu'à
  la donnée brute et sa source
- Script d'extraction automatique depuis le manifest/catalog/run_results dbt
  de **ce** projet (rien d'inventé, statut réel du dernier `dbt run`)
- Lien "fiche ERP" en lecture seule sur chaque donnée brute issue de la
  migration du Sprint 2 : deep link vers une maquette de fiche native,
  **jamais d'édition directe** (gouvernance lecture-seule déjà actée sur le
  reste du portfolio)
- Couverture : au minimum les KPIs des 4 dashboards du Sprint 9

## Sprint 9 — BI (tableaux de bord)
- TdB Exécutif/PDG : macro-vision, KPIs globaux
- TdB Contrôle de Gestion : P&L, suivi centres de coûts, écarts Réel vs Budget vs Forecast
- TdB RH & Opérationnel
- TdB FinOps/Audit : coûts BigQuery, audit de sécurité (RLS/masking appliqués)
- Infobulles de documentation vivante, alimentées par l'outil de traçabilité du Sprint 8
- Connexion RLS testée par profil (un compte "RH" ne voit pas les marges, etc.)

## Sprint 10 — Finition
- Dette technique : toutes les lignes de `DETTE-TECHNIQUE.md` soldées ou explicitement actées comme limite assumée
- Tests end-to-end du pipeline complet (source → Bronze → Gold → BI → reverse ETL)
- README final, `docs/REFONTE-ERP.md` et outil de traçabilité liés depuis l'index
- `git init` + publication GitHub (à valider avant tout push)

## Definition of Done par sprint
- Mise à jour de `DETTE-TECHNIQUE.md` (ajout des nouveaux raccourcis, retrait de ceux réellement soldés)
- Pas de secret en dur (voir `.env.example`)
- `docker compose up` fonctionne de zéro
- Code review croisée si le binôme redevient actif
