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

## Sprint 5 — Hub n8n ✅ terminé
- Reverse ETL : génération de la liasse de clôture mensuelle (Excel) → dépôt Drive
- Alerting dépassement budgétaire (Discord/Slack/Email) déclenché depuis Gold, jamais depuis la source
- Veille stratégique : collecte APIs (Finance/Bourse/IA/Pilotage d'entreprise) → résumé Ollama → distribution
- Workflows exportés en JSON versionné dans `n8n/workflows/` + script d'import (dette #3)
- Notification n8n des changements de schéma dbt (webhook déclenché en CI)

  → tout réalisé, détail complet dans `docs/N8N.md` : 5 workflows testés
  (y compris après réimport complet sur instance vierge). `cloture-mensuelle`
  dépose un vrai XLSX (Postgres → Spreadsheet File → MinIO) ;
  `alerting-depassement-budgetaire` détecte 20 lignes à >20% d'écart et les
  formate ; `veille-strategique` collecte Hacker News + taux de change,
  résume via Ollama (`llama3.2:1b`) et dépose le résultat — qualité de
  résumé limitée par la taille du modèle, assumé. Discord/Slack/Drive
  laissés en placeholder explicite (pas de compte externe disponible,
  dettes #6/#7). Dette #5/#6 (SIRET, reportée du Sprint 4) réglée : ajout
  du champ SIRET, précision de réconciliation 54% → **80,2%** (F1 89,0%).
  Root cause SSL round 2 trouvée : Node.js (n8n) ignore le magasin de
  certificats OS, fixé via `NODE_EXTRA_CA_CERTS`.

## Sprint 6 — Gouvernance avancée & FinOps ✅ terminé
- Row-Level Security (RLS) sur BigQuery, par profil (RH/Finance/Direction/PDG)
- Column-Level Security / Dynamic Masking via Policy Tags (données sensibles : salaires, marges)
- Partitionnement et règles de rétention (FinOps, contrôle des coûts BigQuery)
- CI/CD GitHub Actions : `dbt docs` → GitHub Pages à chaque merge
- Pipeline CI complet (lint + self-checks générateurs + `dbt build` dev) — solde la dette #4
- Checklist rotation des secrets avant toute exposition réseau (dette #5)

  → tout réalisé, détail complet dans `docs/GOUVERNANCE.md`. **Vrai projet
  GCP dédié** `bv-dataplatform` (facturation liée, distinct du portfolio
  solo), pas une simulation. RLS + Policy Tags appliqués sur
  `fct_ecarts_reel_budget` (partitionnée par mois, rétention 730j) et
  **prouvés par requête réelle** avec 4 comptes de service : RH voit 0
  ligne et se fait refuser la colonne `montant_reel` (deux mécanismes
  indépendants), Finance/Direction/PDG voient les 2 240 lignes et
  11 847 943,82€. CI GitHub Actions vert du premier coup sur le pipeline
  complet ; `dbt docs` publié sur GitHub Pages
  (https://valentinratigniet-byte.github.io/projet-baptiste-valentin/).
  Trois root causes trouvées et corrigées en cours de route : collision
  `GOOGLE_APPLICATION_CREDENTIALS` avec le portfolio solo (renommé
  `BQ_KEYFILE`), troisième piège SSL (gRPC, indépendant de Python/Node —
  `GRPC_CA_BUNDLE`), convention de région Data Catalog (`eu` minuscule vs
  `EU` BigQuery).

## Sprint 7 — MLOps ✅ terminé
- Forecasting métier (Python, séries temporelles sur `fct_ecarts_reel_budget`)
- Détection de data drift (Evidently AI) sur les flux Bronze/Silver
- Chatbot BI Text-to-SQL : Ollama local interrogeant BigQuery en lecture seule
- Évaluation du chatbot sur un jeu de questions/réponses métier avec vérité terrain

  → tout réalisé, détail complet dans `docs/MLOPS.md` : `mlops/forecast.py`
  (lissage de Holt, `statsmodels`) prévoit 3 mois sur les séries avec assez
  d'historique (3 prévues / 6, le reste ignoré plutôt que forcé) et écrit
  `marts.ml_forecast_reel` ; `mlops/drift_detection.py` (Evidently AI) mesure
  **60% des colonnes suivies en dérive** entre les deux moitiés
  chronologiques du flux CRM (pas encore deux runs réels distincts à
  comparer — limite assumée) et publie un rapport HTML ; `mlops/chatbot/`
  génère du SQL via Ollama local, le valide (liste blanche de
  tables/commandes, dry_run BigQuery avant toute exécution) puis l'exécute
  en lecture seule (`direction-viewer`, plafond FinOps). Évalué à **60%
  d'execution accuracy** (10 questions, vérité terrain, comparaison par
  résultat exécuté plutôt que par texte SQL) après ajout d'un exemple
  few-shot au prompt (30% en zero-shot). `llama3.2:3b` testé pour remplacer
  le 1B (piste annoncée au Sprint 5) : plus juste mais 169s par question sur
  ce matériel CPU-only contre 1-3s pour le 1B, jugé inutilisable en
  interactif — le 1B est resté le modèle du chatbot, choix documenté plutôt
  que silencieusement abandonné. Dette ajoutée : chatbot sans routage RLS
  par profil, détection de drift sur un seul run (`docs/DETTE-TECHNIQUE.md`
  #9/#10).

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
