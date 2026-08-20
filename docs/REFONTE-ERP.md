# Refonte ERP — diagnostic, mapping, migration (Sprint 2)

Cas d'usage : un ERP legacy (export brut simulé dans
`erp-legacy/exports/`) existait avant le CRM/data platform construits au
Sprint 1. Ce document est le livrable d'une mission de refonte : diagnostic
du schéma existant, mapping vers le modèle cible, plan de migration, et
résultats réels de la migration exécutée (pas une simulation — les chiffres
ci-dessous viennent d'une exécution de `erp-legacy/migrate_erp_to_target.py`).

## 1. Diagnostic du schéma legacy

Source : `erp-legacy/exports/ERP_EXPORT_VTE_2023_2024.csv` (2 500 lignes,
2023-2024), `REF_CLIENT_LEGACY.csv` (131 codes client).

| Symptôme | Exemple observé | Risque |
|---|---|---|
| Table plate, aucune normalisation | Client, article, compte, centre de coût tous répétés sur chaque ligne de vente | Volumétrie gonflée, aucune source de vérité unique |
| Codes tronqués/incohérents | Centre de coût "Ventes" codé `CC01`, `CC1` et `01` selon la ligne | Impossible d'agréger sans table de correspondance manuelle |
| Format client hétérogène | `CDCLI` tantôt numérique (`00024`), tantôt alphanumérique (`CLI35`) | Pas de clé stable, dédoublonnage obligatoire |
| Doublons de saisie | Même client legacy saisi 2 fois avec des variantes d'orthographe ("Ruiz S.A.S." / "Ruiz") | Double comptage si non réconcilié |
| Centre de coût vide | ~15% des lignes | Coûts non affectés, reporting CG faussé |
| Dates cassées | `00/00/0000` sur ~2% des lignes | Lignes inexploitables telles quelles |
| Montants en texte, virgule décimale | `"3265,50"` | Erreur de type si chargé sans parsing explicite |
| Colonne non documentée | `FLGANO` (0/1/vide, jamais expliqué dans l'ERP d'origine) | Dette de connaissance : personne ne sait ce que ça veut dire |
| Compte "poubelle" | `758000` utilisé pour ~50% des lignes, quel que soit le motif réel | Analytique comptable peu fiable en l'état |

**Volumétrie** : 2 500 lignes de vente, 131 codes client (dont 25 jamais
repris dans le CRM), 2 ans d'historique (2023-2024, avant le CRM du
Sprint 1).

## 2. Mapping legacy → cible

| Champ legacy | Type/format | Champ cible (MCD, `docs/MCD.md`) | Transformation |
|---|---|---|---|
| `CDCLI` / `RSCLI` | code + texte libre | `FACT_VENTES_REEL.client_id` | Réconciliation fuzzy-match contre `DIM_CLIENT` (voir §4) |
| `CDCC` | code incohérent, parfois vide | `FACT_VENTES_REEL.centre_cout_id` | Table de correspondance manuelle (`MAPPING_CDCC` dans le script) ; vide → "Non affecté" |
| `CDCPT` | code PCG | `FACT_VENTES_REEL.compte_id` | Repris tel quel (déjà un vrai code comptable), à relier à `DIM_COMPTE` au Sprint 4 |
| `DTPCE` | `DD/MM/YYYY` string, `00/00/0000` = invalide | `FACT_VENTES_REEL.date_id` | Parsing strict ; date invalide → ligne flaggée, pas de valeur par défaut inventée |
| `QTE` | string | `FACT_VENTES_REEL.quantite` | Cast entier |
| `MTHT` | string, virgule décimale | `FACT_VENTES_REEL.montant_reel` | Remplacement `,` → `.`, cast numérique |
| `MTTVA`, `MTTTC` | string, virgule décimale | *(hors MCD actuel — conservés pour audit)* | Idem |
| `FLGANO` | code non documenté | *(non mappé)* | Conservé tel quel dans la table de migration, à investiguer avant tout usage |
| `NUMPCE` | identifiant pièce | `fact_ventes_erp_migre.numpce` (clé technique) | Repris tel quel |

## 3. Plan de migration

**Phase 1 — Extraction & constat** (fait) : export brut versionné,
diagnostic ci-dessus.

**Phase 2 — Réconciliation client** (fait) : fuzzy matching `RSCLI` contre
`DIM_CLIENT`, évalué contre une vérité terrain (voir §4).

**Phase 3 — Nettoyage & mapping centre de coût/compte** (fait) : table de
correspondance `CDCC` explicite, parsing dates/montants, flag qualité par
ligne (`ligne_valide`, `motif_rejet`) — préfigure les data contracts du
Sprint 3.

**Phase 4 — Chargement cible** (fait, périmètre réduit) : chargement dans
Postgres (`erp_migre`, cible dbt-dev) plutôt que directement dans le modèle
CG définitif — le pipeline dbt qui consommera ce schéma n'existe qu'à
partir du Sprint 4. Stratégie de non-régression : le CRM (MySQL) n'est pas
touché par cette migration, `erp_migre` est un schéma additif.

**Phase 5 — Intégration dbt** (à faire, Sprint 4) : modèle staging sur
`erp_migre.fact_ventes_erp_migre`, union avec `fact_ventes_reel` (CRM) dans
le modèle Gold, avec la colonne `source` conservée pour traçabilité.

**Rollback** : `erp_migre` est un schéma isolé, `DROP SCHEMA erp_migre
CASCADE` annule la migration sans toucher au reste de la plateforme.

## 4. Résultats de la migration exécutée

```
Réconciliation client : précision=54.0% rappel=100.0% F1=70.1% (VP=68 FP=58 FN=0)
2500 lignes migrées (51 à corriger, 2.0%)
```

**Le rappel à 100% et la précision à 54% ne sont pas un bug du matching —
c'est un vrai plafond de données, vérifié :**

```sql
SELECT libelle, COUNT(*) FROM dim_client GROUP BY libelle HAVING COUNT(*) > 1;
-- Bonnin (4), Legros (4), Roussel (3), Potier (3), Leroy (3), ...
```

Le CRM lui-même contient des clients différents (ID différents) portant le
même nom (les données du Sprint 1 sont générées avec des patronymes
français courants, sans deuxième attribut différenciant). Un matching par
nom seul ne peut structurellement pas distinguer deux clients homonymes —
aucun algorithme de fuzzy matching ne résout ça sans un second attribut
(SIRET, adresse, contact). Le rappel à 100% confirme que l'algorithme
retrouve bien un candidat à chaque fois qu'il existe un vrai match ; la
précision plafonne à cause de l'ambiguïté des données sources, pas d'une
erreur de seuil ou de scorer.

**2% de lignes à corriger** (`ligne_valide=false` dans
`erp_migre.fact_ventes_erp_migre`) : dates `00/00/0000` ou centre de coût
non mappé. Chargées quand même avec leur `motif_rejet`, pas silencieusement
écartées — c'est le comportement que les data contracts du Sprint 3
généraliseront à tous les flux (Dead-Letter-Queue).

## 5. Limites connues et recommandations

- **Identifiant client non fiable** : ni le CRM ni l'export legacy ne
  portent de SIRET ou d'identifiant métier stable. Recommandation : ajouter
  un champ SIRET aux générateurs (CRM et legacy) si une vraie déduplication
  MDM est visée au Sprint 4 — sans ça, ~46% des rapprochements client
  resteront invérifiables par construction.
- **`FLGANO` non documenté** : conservé tel quel dans `erp_migre`, aucune
  règle métier n'a pu être établie faute de documentation d'origine (fidèle
  à la réalité d'un vrai ERP mal documenté).
- **Compte comptable `758000` sur-utilisé** : signalé mais non retraité ici
  — la vraie ventilation analytique relève du Sprint 4 (allocations).
