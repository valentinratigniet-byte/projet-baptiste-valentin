# Gouvernance BigQuery & FinOps (Sprint 6)

Projet GCP dédié : **`bv-dataplatform`** (facturation liée au compte free
tier, distinct du portfolio solo `portfolio-data-vr`). BigQuery + Data
Catalog activés. 3 datasets : `raw`, `staging`, `marts`.

## Périmètre volontairement restreint

La gouvernance (RLS + masking) est appliquée **en profondeur sur une seule
table** — `marts.fct_ecarts_reel_budget`, la plus sensible du modèle CG —
plutôt que superficiellement sur tout l'entrepôt. Raison : prouver que le
mécanisme fonctionne *réellement* (requêtes exécutées, accès refusé/accordé
en vrai) vaut plus qu'une liste de policies jamais testées sur 11 tables.
Généraliser à d'autres marts est mécanique une fois le patron validé ici.

## Setup (scripts, dans l'ordre)

```bash
./.venv/Scripts/python.exe governance/sync_marts_to_bigquery.py
./.venv/Scripts/python.exe governance/apply_rls_and_masking.py
./.venv/Scripts/python.exe governance/test_acces_par_profil.py
```

Nécessite `BQ_KEYFILE`, `BQ_PROJECT`, `BQ_DATASET` dans `.env` (clé du
compte de service `dbt-loader`, hors repo).

## Row-Level Security

`CREATE ROW ACCESS POLICY` sur `fct_ecarts_reel_budget` : seuls
`finance-viewer`, `direction-viewer`, `pdg-viewer` sont nommés. BigQuery
refuse par défaut tout principal non couvert par une policy — `rh-viewer`
n'a donc besoin d'aucune policy de blocage explicite, l'absence suffit.

## Column-Level Security (Policy Tags)

Taxonomie `CG` → tag `Confidentiel`, appliqué à `montant_reel`,
`montant_budget`, `ecart`. Seuls Finance/Direction/PDG ont le rôle
`roles/datacatalog.categoryFineGrainedReader` sur ce tag — défense en
profondeur, indépendante de la RLS (si jamais une RLS mal configurée
laissait passer une ligne, les colonnes sensibles restent bloquées).

## Preuve réelle (pas une simulation)

4 comptes de service (RH/Finance/Direction/PDG), une clé chacun, interrogent
réellement `fct_ecarts_reel_budget` (`governance/test_acces_par_profil.py`).
Résultat d'une exécution réelle :

```
profil               lignes (RLS)    SUM montant_reel (masking)
rh-viewer            0               REFUSE (policy tag)
finance-viewer       2240            11847943.82
direction-viewer     2240            11847943.82
pdg-viewer           2240            11847943.82
```

RH est bloqué par **deux mécanismes indépendants** : 0 ligne visible (RLS)
et refus explicite sur la colonne sensible (Policy Tag) — testé avec une
requête qui ne touche même pas les colonnes protégées, prouvant que les deux
contrôles agissent séparément.

## Partitionnement & rétention (FinOps)

`fct_ecarts_reel_budget` est partitionnée par mois (`periode`), expiration
de partition à 730 jours (2 ans) — les vieilles partitions sont supprimées
automatiquement, pas de coût de stockage qui s'accumule indéfiniment.

## Root causes trouvées en cours de route

**Collision `GOOGLE_APPLICATION_CREDENTIALS`** : cette variable
d'environnement était déjà positionnée de façon *persistante* (niveau
utilisateur Windows) pour le projet GCP du portfolio solo
(`portfolio-data-vr`). `.env` avec le même nom aurait été silencieusement
ignoré par tout script utilisant les credentials par défaut (ADC). Fixé en
renommant systématiquement en **`BQ_KEYFILE`** dans ce projet — jamais le
nom standard — et en construisant les credentials explicitement dans le
code (`service_account.Credentials.from_service_account_file(...)`) plutôt
que de laisser la librairie deviner.

**Troisième piège SSL (gRPC)** : `scripts/fix-local-ssl.ps1` corrige les
clients OpenSSL (`update-ca-certificates`) et `NODE_EXTRA_CA_CERTS` corrige
Node.js — ni l'un ni l'autre ne suffit pour le client Python
`google-cloud-datacatalog`, qui utilise gRPC en interne avec sa **propre**
pile réseau native, indépendante du module `ssl` de Python (donc de
`pip-system-certs`). Fixé via la variable `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH`
pointée vers le bundle CA combiné déjà utilisé par `gcloud` CLI
(`~/.gcp/combined_ca_certs.pem`).

**Data Catalog veut la région en minuscules** (`eu`), contrairement à la
multi-région BigQuery (`EU`) utilisée pour les datasets — deux conventions
différentes pour la même région, trouvé en testant plutôt qu'en devinant.

## IAM du projet `bv-dataplatform`

| Compte de service | Rôles | Usage |
|---|---|---|
| `dbt-loader` | `bigquery.dataEditor`, `bigquery.jobUser`, `bigquery.dataOwner`, `bigquery.securityAdmin`, `datacatalog.categoryAdmin` | dbt (cible prod), scripts `governance/` |
| `rh-viewer` | `bigquery.dataViewer`, `bigquery.jobUser` | Test d'accès profil RH (bloqué par RLS + masking) |
| `finance-viewer`, `direction-viewer`, `pdg-viewer` | idem + `datacatalog.categoryFineGrainedReader` sur le tag `Confidentiel` | Test d'accès profils avec visibilité complète |

Clés des 4 comptes "viewer" dans `~/.gcp/bv-viewers/` (hors repo).
