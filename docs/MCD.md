# MCD — Contrôle de Gestion (Réel / Budget / Forecast)

## Le point clé

Réel, Budget et Forecast ne vivent pas au même grain :

- **Réel** est transactionnel : une ligne par vente/dépense, au jour le jour,
  liée à un client/produit précis.
- **Budget** est saisi une fois par période (mois/année), par centre de coût
  et par compte analytique — pas de détail client/produit.
- **Forecast** est glissant : révisé chaque mois, même grain que le Budget,
  avec une colonne "date de révision".

Ils se rejoignent uniquement sur une **clé analytique commune** :
`(centre_coût, compte, période)`. dbt agrège le Réel (transactionnel → mensuel)
pour le comparer au Budget/Forecast (déjà mensuel) et calculer les écarts.

## Entités

```
DIM_DATE(date_id PK, date, mois, trimestre, annee, ...)
DIM_CENTRE_COUT(centre_cout_id PK, code, libelle, responsable, centre_parent_id FK)
DIM_COMPTE(compte_id PK, code_compte, libelle, nature)         -- nature = charge/produit
DIM_PRODUIT(produit_id PK, code, libelle, famille)
DIM_CLIENT(client_id PK, code, libelle, segment, siret)
DIM_VERSION_BUDGET(version_id PK, libelle, date_validation)     -- ex: "Budget initial 2026", "Forecast T2"

FACT_VENTES_REEL(
  vente_id PK,
  date_id       FK -> DIM_DATE,
  centre_cout_id FK -> DIM_CENTRE_COUT,
  compte_id     FK -> DIM_COMPTE,
  produit_id    FK -> DIM_PRODUIT,
  client_id     FK -> DIM_CLIENT,
  montant_reel  NUMERIC,
  quantite      NUMERIC
)                                                -- grain : transaction / jour

FACT_BUDGET(
  budget_id PK,
  periode_id     FK -> DIM_DATE (1er du mois),
  centre_cout_id FK -> DIM_CENTRE_COUT,
  compte_id      FK -> DIM_COMPTE,
  version_id     FK -> DIM_VERSION_BUDGET,
  montant_budget NUMERIC
)                                                -- grain : mois x centre_coût x compte

FACT_FORECAST(
  forecast_id PK,
  periode_cible_id  FK -> DIM_DATE,
  date_revision_id  FK -> DIM_DATE,               -- quand le forecast a été fait
  centre_cout_id    FK -> DIM_CENTRE_COUT,
  compte_id         FK -> DIM_COMPTE,
  montant_forecast  NUMERIC
)                                                -- grain : mois cible x mois de révision x centre_coût x compte
```

## Relations

- `DIM_CENTRE_COUT` est auto-référencée (`centre_parent_id`) pour la
  hiérarchie (ex: Direction → Département → Service).
- `FACT_VENTES_REEL` porte le détail (client/produit) ; `FACT_BUDGET` et
  `FACT_FORECAST` ne le portent pas — c'est voulu, on ne budgète pas au
  client près.
- Le modèle dbt `fct_ecarts_reel_budget` agrège `FACT_VENTES_REEL` par
  `(centre_cout_id, compte_id, mois)` puis fait un `FULL OUTER JOIN` avec
  `FACT_BUDGET` sur cette même clé pour calculer l'écart et le %.
