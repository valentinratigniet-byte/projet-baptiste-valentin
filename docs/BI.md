# BI — tableaux de bord interactifs (Sprint 9)

Le cahier des charges d'origine (`docs/ARCHITECTURE.md`) prévoyait Power
BI / Looker Studio pour cette brique. Contrainte technique actée avec
Valentin : il n'existe pas d'outil permettant de piloter par API l'éditeur
graphique de Power BI Desktop ou de Looker Studio (glisser-déposer des
visuels) — seule la couche modèle sémantique de Power BI est automatisable
(MCP `powerbi-modeling` installé, TOM/XMLA). Décision : 4 tableaux de bord
HTML/JS maison (mêmes conventions que `traceability/`, Sprint 8), Power BI
laissé à Valentin en autonomie dans un second temps.

## Ce qui existe (`dashboards/index.html`)

Une page unique, 4 onglets, alimentée par `scripts/export_dashboard_data.py`
qui interroge les sources réelles à chaque régénération — aucun chiffre
inventé :

- **Exécutif / PDG** : CA réel total, écart Réel/Budget agrégé, clients
  actifs, centres de coûts, évolution mensuelle du CA (ligne, 41 points
  réels), top centres de coûts par CA.
- **Contrôle de gestion** : Réel vs Budget par nature de compte (illustre en
  direct la dette technique #2 — aucun réel sur les comptes de charge, voir
  ci-dessous), top 10 écarts Réel/Budget en valeur absolue, allocation du CA
  « Non affecté » (`fct_allocation_couts`).
- **RH & Opérationnel** : CA par responsable de centre de coût (le seul angle
  « personne » du modèle, voir ci-dessous), carte de la donnée personnelle
  RGPD, volumétrie du pipeline (CRM/ERP/logs/budget/forecast), statut réel du
  dernier `dbt build`.
- **FinOps / Audit** : preuve RLS + masking par requête réelle (rejoue le
  mécanisme de `governance/test_acces_par_profil.py`), stockage et
  partitionnement réels du dataset BigQuery `marts`.

Chaque KPI sensible porte une puce **ⓘ** qui ouvre `traceability/index.html`
directement sur le nœud dbt correspondant (lien profond par hash, ajouté à
`traceability/index.html` ce sprint : `index.html#<id_noeud>` bascule sur le
jeu "Projet réel" et y navigue) — c'est la brique "infobulles alimentées par
la traçabilité" prévue par `docs/ROADMAP.md`.

## Pourquoi pas de vraie entité RH

`docs/MCD.md` ne modélise aucun effectif, masse salariale ou donnée
employé — ce projet est un Contrôle de Gestion, pas un SIRH. L'onglet
« RH & Opérationnel » a donc été construit autour de ce qui existe
réellement : `dim_centre_cout.responsable` (pilotage par responsable) et la
santé opérationnelle du pipeline, plutôt que d'inventer des KPIs RH
(effectifs, turnover) sans source. Assumé et documenté plutôt que masqué,
même principe que la dette #2 (`fct_allocation_couts`).

## Chiffres réels (extraction du 21/08/2026)

| Indicateur | Valeur |
|---|---|
| CA réel total | 19 128 502,08 € |
| Budget total (CA + charges) | 56 012 612,16 € |
| Forecast total | 41 860 249,99 € |
| Écart Réel/Budget (comptes avec les deux) | +1 028 173,99 € |
| Clients actifs | 500 |
| Centres de coûts | 16 |
| Ventes CRM / ERP legacy valides | 4 442 / 2 327 |
| Tests dbt (dernier `dbt build`) | 47/47 OK (21 modèles, 68 nœuds au total) |

**Réel vs Budget par nature** : `produit` (CA) — 156 lignes, 19,13 M€ réel
contre 12,36 M€ budgété (dépassement favorable) ; `charge` — 2 160 lignes,
43,66 M€ budgétés, **0 € réel** (`fct_ventes_reel` ne porte que du CA, pas de
charges réelles — dette #2, illustrée en direct par le graphique plutôt que
seulement documentée en texte).

**RLS + masking (BigQuery, requête réelle du 21/08/2026)** :

```
profil               lignes (RLS)    SUM montant_reel (masking)
rh-viewer             0              REFUS (policy tag)
finance-viewer        2 240          11 847 943,82 €
direction-viewer      2 240          11 847 943,82 €
pdg-viewer            2 240          11 847 943,82 €
```

**Stockage BigQuery (dataset `marts`)** : 3 tables, 0,090 MB au total —
`fct_ecarts_reel_budget` partitionnée par mois sur `periode`, rétention 730
jours (confirmé par l'API, pas seulement par `docs/GOUVERNANCE.md`). Très en
dessous du palier gratuit (10 GB stockage / 1 TB requêtes par mois) : le
coût réel actuel est ≈ 0 €, honnête plutôt qu'un chiffre FinOps inventé pour
occuper la case. `ml_forecast_reel` (9 lignes, sortie MLOps du Sprint 7)
découverte au passage — n'était pas encore documentée comme table BigQuery à
part entière.

## Décisions techniques

- **Postgres pour PDG/CG/RH, BigQuery pour FinOps/RLS** : seuls
  `fct_ecarts_reel_budget` et `dim_centre_cout` sont synchronisés vers
  BigQuery (dette #5, profondeur plutôt que largeur) — les 3 premiers
  tableaux de bord lisent donc directement `dbt_cg` (Postgres dev), le
  quatrième réutilise les 4 comptes de service `*-viewer` déjà provisionnés
  au Sprint 6.
- **Best-effort sur la partie BigQuery** : si les clés de service
  (`~/.gcp/bv-viewers/`, `BQ_KEYFILE`) sont absentes, `finops.rls_profils`
  et `finops.tables_bigquery` sont simplement vides plutôt que de faire
  échouer tout l'export — même principe que `traceability/scripts/extract_filiation.py`
  pour les comptages de lignes.
- **CI** : `export_dashboard_data.py --demo` (self-check sans dépendance
  externe) puis une exécution réelle contre le Postgres éphémère du run —
  valide les requêtes SQL à chaque push. La partie BigQuery n'est jamais
  testée en CI (pas de clés de service disponibles), comme `governance/`.
- **Vérifié par rendu DOM réel (`jsdom`)** avant publication, pas seulement
  `node --check` : les 4 onglets, leurs graphiques (ligne + barres + barres
  groupées + barres divergentes) et les liens profonds vers la traçabilité
  ont été exercés — pratique désormais systématique sur ce projet depuis la
  régression du prototype solo (voir `docs/TRACABILITE-KPI.md`).
- **Palette et specs de graphique** : palette de référence validée (voir la
  compétence dataviz du projet), pas de bibliothèque de graphiques —
  SVG/HTML natif, cohérent avec le reste du portfolio ("vanilla, sans
  dépendance").

## Limites assumées

- Pas de vraie couche RBAC serveur sur ces dashboards (page statique) : la
  preuve RLS/masking vient de la requête BigQuery réelle affichée, pas d'un
  filtrage de la page elle-même — cohérent avec l'avertissement déjà présent
  sur `traceability/index.html`.
- Power BI (visuels) non construit — laissé à Valentin, modèle sémantique
  disponible via le MCP `powerbi-modeling` si besoin plus tard.
- Le graphique d'évolution mensuelle du CA n'a pas de vraie échelle
  temporelle continue : les points sont espacés également (un mois = un
  intervalle fixe), pas au prorata du calendrier. **Rencontré sur les
  données actuelles** : le jeu de données généré (Sprint 1) ne contient
  aucune vente sur octobre à décembre 2024 (41 points réels sur 44 mois
  possibles entre janvier 2023 et août 2026) — sur ce graphique, ce trou
  calendaire est invisible, la ligne passe directement de septembre 2024 à
  janvier 2025 comme si les mois se suivaient. Chiffre honnête (aucune
  donnée inventée pour combler le trou), mais représentation trompeuse sur
  ce point précis — à corriger si ce dashboard sert de référence externe
  (échelle X proportionnelle aux mois réels, ou marqueur de rupture
  explicite).
