# Entrepôt & transformation dbt (Sprint 4)

Projet dbt : `dbt_cg/`. Cible dev = Postgres local (`bv-postgres-dbtdev`,
port 5434) ; cible prod = BigQuery (`dbt_cg/profiles.yml`, structurellement
prête mais non fonctionnelle tant qu'il n'y a pas de projet GCP — voir
note dans le fichier).

## Chaîne complète (dans l'ordre)

```bash
./.venv/Scripts/python.exe data-generation/generate_cg_data.py
./.venv/Scripts/python.exe data-generation/generate_logs_mongo.py
./.venv/Scripts/python.exe erp-legacy/generate_erp_legacy_export.py
./.venv/Scripts/python.exe data-contracts/ingest_to_bronze.py      # Bronze/DLQ (Sprint 3)
./.venv/Scripts/python.exe erp-legacy/migrate_erp_to_target.py     # lit Bronze, écrit erp_migre (Sprint 2, branché sur Bronze depuis Sprint 4)
./.venv/Scripts/python.exe data-contracts/load_bronze_to_raw.py    # Bronze -> Postgres schéma raw (nouveau, Sprint 4)
cd dbt_cg && DBT_PROFILES_DIR=. ../.venv/Scripts/dbt.exe build
```

## Architecture des couches

- **`raw`** (schema-on-read, `data-contracts/load_bronze_to_raw.py`) : une
  table par flux Bronze, colonne `data JSONB` — c'est dbt qui type et
  nomme, pas ce loader.
- **`erp_migre`** : chargé directement en Postgres par le script de
  migration Sprint 2 (déjà typé, pas besoin de repasser par `raw`).
- **`staging`** (vues) : un modèle par source, cast + renommage, un
  changement mécanique par ligne. `stg_erp__fact_ventes_migre` filtre les
  lignes déjà invalides (écartées par le contrat Sprint 3) et celles sans
  client CRM réconcilié.
- **`marts`** (tables) : `dim_date`, `dim_client` (golden record MDM),
  `dim_produit`, `dim_centre_cout`, `dim_compte`, `dim_version_budget`,
  `fct_ventes_reel` (union CRM+ERP), `fct_budget`, `fct_forecast`,
  `fct_ecarts_reel_budget`, `fct_allocation_couts`.

## MDM : golden record client

`marts/dim_client.sql` fusionne le CRM (source de vérité) avec les clients
ERP legacy jamais réconciliés (`client_crm_id_propose IS NULL`) : **505**
clients au total (500 CRM + **5** legacy-only avec un nouvel ID généré).

Le générateur avait créé 25 clients "legacy-only" ; seuls 5 ressortent
comme tels après matching. Ce n'est pas un bug : c'est la même limite de
précision (54%) documentée dans `docs/REFONTE-ERP.md` — un legacy-only peut
être rapproché *à tort* d'un CRM homonyme par l'algorithme. Le golden
record reflète fidèlement la décision de l'algorithme, imparfaite comme
documenté, pas une vérité cachée.

## Écarts Réel/Budget

`fct_ecarts_reel_budget` agrège le Réel (transactionnel) au grain du Budget
(mensuel, par centre × compte) avant de les rapprocher — le point clé du
MCD. Exemple réel (premier `dbt build`) :

```
2025-01 | centre 13 | Ventes produits | réel 247 658€ | budget 152 759€ | écart +62,1%
```

**Root cause corrigée en amont** (pas contournée en SQL) : le générateur
Sprint 1 ne budgétait que les charges, jamais le chiffre d'affaires — Réel
(100% ventes) et Budget (100% charges à l'origine) ne partageaient donc
*aucun* compte commun, rendant tout écart vide par construction.
`generate_cg_data.py::gen_fact_budget` budgète désormais aussi les 3
centres commerciaux sur le compte "Ventes produits". Un test de
non-régression (`demo()`) vérifie qu'au moins un compte est commun aux deux
flux.

## Allocations analytiques

`fct_allocation_couts` répartit le CA du centre "Non affecté" (CDCC vide
dans l'ERP legacy) vers les 5 centres commerciaux réels, au prorata de leur
part de CA. **Écart avec le cahier des charges d'origine** : il visait des
charges indirectes, mais le seul fait "Réel" du modèle est un fait de
ventes (aucune charge réelle n'existe, seul le Budget en a) — le mécanisme
de répartition est identique, l'objet réparti (CA non affecté, pas des
charges) diffère. Assumé et documenté plutôt que masqué.

## Tests

68/68 tests dbt PASS (not_null, unique, relationships, accepted_values) sur
les 21 modèles staging + marts.
