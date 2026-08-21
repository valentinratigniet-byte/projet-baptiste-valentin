# Traçabilité KPI interactive (Sprint 8)

Reprise du prototype du portfolio solo (`portfolio-data/projet-14-filiation`)
repointé sur ce projet : une page unique (`traceability/index.html`, aucune
dépendance côté navigateur) où on clique sur n'importe quelle source, colonne
ou modèle et on remonte, niveau par niveau, jusqu'à la donnée brute — Fiche
détaillée, Graphe complet zoomable avec analyse d'impact, vue Dérive
(comparaison d'instantanés historisés) et vue Systèmes.

## Ce qui vient de dbt_cg (`scripts/extract_filiation.py`)

Rien n'est inventé : le script lit `dbt_cg/target/manifest.json` +
`catalog.json` + `run_results.json` (statut réel du dernier `dbt run`/`dbt
test`) et régénère les blocs `AUTO-GENERATED`/`SNAPSHOTS` de `index.html` par
marqueurs, comme sur le prototype solo. Adapté à ce projet :

- **Cible** : `dbt_cg/target` (au lieu de `dbt_ecommerce`).
- **Libellés de couche** : ce projet n'a pas de macro `generate_schema_name`
  personnalisée, donc dbt génère `public_staging`/`public_marts` (préfixe du
  schéma du profil + schéma custom), pas juste `staging`/`marts` — `LAYER`
  adapté en conséquence.
- **Comptage de lignes réel** : `profiles.yml` de ce projet utilise des
  `{{ env_var(...) }}` Jinja (secrets via variables d'environnement), pas des
  valeurs en clair comme sur le projet solo — un `yaml.safe_load` naïf
  laisserait le texte Jinja tel quel. `fetch_row_counts` lit donc directement
  les mêmes variables d'environnement que `erp-legacy/migrate_erp_to_target.py`
  (port 5434, mêmes valeurs par défaut), best-effort (dégrade silencieusement
  si Postgres n'est pas démarré).

**Résultat sur l'extraction actuelle** : 32 nœuds (11 sources brutes + 10
modèles staging + 11 marts), 53 tests dbt affichés au niveau colonne (tous
`ok`), 107 colonnes avec lignage colonne-à-colonne résolu par sqlglot. Le
total dbt réel (`dbt test`) est plus élevé (68/68 dans `STATUS.md`) : les
tests sans `column_name` (contraintes au niveau table plutôt que colonne) ne
sont pas rattachés à une colonne dans cet outil — même comportement que sur
le prototype solo, pas une régression de ce sprint.

## Fiche ERP native en lecture seule (nouveau sur ce sprint)

Le prototype solo se limitait à une maquette de bouton désactivé sur le jeu
"Projet réel". Ici, la donnée brute issue de la migration ERP (Sprint 2,
`docs/REFONTE-ERP.md`) a une vraie destination cliquable :
`traceability/erp-fiche.html?numpce=...` — une page à part, look "écran ERP
legacy", recherche par n° de pièce ou code client, lecture seule stricte
(bannière, aucun formulaire d'écriture).

- Alimentée par `scripts/export_erp_fiches.py`, qui lit directement
  `erp-legacy/exports/ERP_EXPORT_VTE_2023_2024.csv` (2 500 lignes, encodage
  `cp1252` — export ERP d'époque, pas reconverti pour l'occasion) et l'embarque
  dans `erp-fiche.html` par le même mécanisme de marqueurs
  (`ERP-ROWS:BEGIN/END`) que `extract_filiation.py`. Choix délibéré de lire
  le CSV brut plutôt que la table `erp_migre.fact_ventes_erp_migre` en base :
  c'est la donnée la plus brute possible, et ça évite de dépendre de Docker
  pour régénérer cette page précise.
- Les deux nœuds sources `erp_migre` (`fact_ventes_erp_migre`,
  `client_reconciliation`) portent le lien dans `extract_filiation.py`
  (`ERP_SOURCE_NAME`, marqué via `source_name` du manifest dbt) — mécanique
  réutilisable si d'autres sources ERP legacy sont ajoutées un jour.
- Cohérent avec la décision de gouvernance actée sur le prototype solo
  (`docs/GOUVERNANCE.md`, [[governance-read-only-preference]] côté mémoire) :
  aucune écriture depuis l'outil, uniquement un lien de sortie vers une
  fiche native — l'ERP applique des règles métier qu'une écriture directe en
  base contournerait.

## Vérification (pas juste `node --check`)

Une régression passée sur le prototype solo (page blanche après l'ajout des
rôles, `ReferenceError` de zone morte temporelle, invisible à `node --check`
car erreur d'exécution et non de syntaxe) a changé la pratique de
vérification : rendu DOM réel via `jsdom` avant de considérer un changement
JS terminé. Fait ici sur les deux pages (`index.html` et `erp-fiche.html`) :
chargement complet, navigation vers le nœud `src_fact_ventes_erp_migre`,
vérification que le nouveau lien "Fiche ERP native" apparaît dans le DOM
rendu, et recherche `?numpce=V000001` sur `erp-fiche.html` — la fiche
correspondante (Aubert SA, 5 822,56 € HT) s'affiche correctement, sans
erreur JS sur les deux pages.

## Limites assumées

- Comptage de lignes et vue Systèmes vides tant que Docker (Postgres) n'est
  pas démarré au moment de l'extraction — dégradation silencieuse déjà
  documentée ci-dessus, pas une régression.
- Un seul instantané réel dans `snapshots/` à ce stade (vue Dérive pas
  encore comparable à un vrai avant/après) — se remplit au fil des
  `dbt run` successifs, comme sur le prototype solo.
- Rôles/RBAC du prototype solo conservés tels quels (simulation client
  uniquement, aucun contrôle d'accès réel — page statique sans backend).
