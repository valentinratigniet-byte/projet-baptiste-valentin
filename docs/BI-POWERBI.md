# BI — modèle Power BI (conception visuelle par Valentin)

Complément à `docs/BI.md` (dashboards HTML/JS) : ce document couvre le
modèle sémantique Power BI construit via le MCP `powerbi-modeling`
(couche modèle uniquement — les visuels sont conçus par Valentin dans
Power BI Desktop, voir décision dans `docs/BI.md`).

Fichier : `dashboards/powerbi/dbt_cg.pbix`. Nom du rapport : **Pilotage
CG**. Captures des 4 pages finales : `dashboards/powerbi/outputs/`
(`page1-pdg.png`, `page2-cg.png`, `page3-rh.png`, `page4-finops.png`).

## Modèle

Connexion : PostgreSQL `127.0.0.1:5434` / `dbt_dev`, schéma `public_marts`
(import). Étoile classique : 6 dimensions (`Dim Client`, `Dim Date`,
`Dim Produit`, `Dim Centre de coût`, `Dim Compte`, `Dim Version budget`) +
5 faits (`Fct Ventes Réel`, `Fct Budget`, `Fct Forecast`,
`Fct Écarts Réel-Budget`, `Fct Allocation coûts`), plus `Fct Logs
Applicatifs` (voir ci-dessous). Toutes les tables et colonnes sont
documentées (description visible dans le volet Modèle de Power BI Desktop).

- **`Dim Date`** marquée comme vraie table de dates (Mark as Date Table).
  Les 8 tables de dates automatiques que Power BI crée par défaut à
  l'import ont été supprimées — sans ce nettoyage, chaque colonne de date
  aurait sa propre mini-table cachée et le calendrier ne serait pas
  partagé entre les faits. Une 9ᵉ (`DateTableTemplate_8fe82ddb…`, 0
  relation, orpheline) avait survécu au nettoyage initial — trouvée et
  supprimée en cours de session.
- **Colonnes finales de `Dim Date`** (9 colonnes) : `date` (clé),
  `annee`, `annee_mois` (AAAA-MM, axe recommandé pour les courbes),
  `premier_jour_mois` (alignement Réel/Budget/Forecast au grain mensuel),
  `date_key` (surrogate AAAAMMJJ, masquée) — et `trimestre`/`mois`
  (numériques, **masqués**) qui n'existent que pour trier
  `trimestre_nom` (Trim 1…Trim 4) et `mois_nom` (Janvier…Décembre), les
  colonnes réellement affichées. Hiérarchie **Calendrier** : Année →
  Trimestre → Mois, construite sur `trimestre_nom`/`mois_nom` (pas les
  numéros bruts) pour un rendu identique aux autres rapports du
  portfolio (`projet-09-dashboard-powerbi`, `dashboard-olist`).
- Relations R→D construites explicitement sur `Dim Date[date]`. Un cas
  d'ambiguïté trouvé et résolu : `Fct Budget` a deux chemins possibles vers
  `Dim Date` (direct via `periode`, et indirect via `Dim Version
  budget.date_validation`) — la seconde a été mise **inactive** (activable
  via `USERELATIONSHIP` en DAX si un jour utile).
- `centre_parent_id` (hiérarchie de centres de coûts prévue par
  `docs/MCD.md`) n'est peuplé pour **aucun** centre sur ce jeu de données —
  vérifié en base avant de construire quoi que ce soit. Aucune hiérarchie
  parent-enfant construite : n'aurait montré qu'un seul niveau à plat.
  Analysis Services refuse par ailleurs les relations d'une table sur
  elle-même dans ce contexte (erreur serveur explicite, testé).
- 4 colonnes techniques (clés, parties de date) corrigées de `Sum` à
  `None` comme agrégation par défaut — sommer un `budget_id` ou une
  `année` n'a pas de sens.

## Mesures DAX (17)

Toutes documentées, organisées par dossier d'affichage : `CA Réel`, `Nb
clients actifs`, `CA Réel (Année précédente)` + `CA Réel vs N-1 %` (time
intelligence via `Dim Date`), `Budget Total`, `Forecast Total`, `Réel
(comptes rapprochés)` / `Budget (comptes rapprochés)` / `Écart
Réel-Budget` / `Écart Réel-Budget %` / `Nb lignes` (ces 5 sur `Fct Écarts
Réel-Budget`, au grain du rapprochement plutôt que recalculées depuis les
tables sources — évite tout double-comptage), `Montant alloué`, `Nb
centres de coût`, `Nb événements` / `Nb erreurs` / `Taux d'erreur %` (sur
`Fct Logs Applicatifs`), `Lignes` (sur `Volumétrie Pipeline`, voir plus
bas). `Écart Réel-Budget %` est un `DIVIDE(SUM(écart), SUM(budget))`,
jamais une moyenne des `ecart_pct` ligne à ligne (qui sur-pondérerait les
petites lignes). Les mesures monétaires/%  affichent le signe `+`
explicitement (`+#,##0 €;-#,##0 €;0 €`), demandé pour les cartes KPI
Exécutif/CG.

## `Fct Logs Applicatifs` — import des volumétries pipeline

`raw.logs_app_events` stocke chaque événement en `jsonb` (flux
MongoDB → Bronze → raw, schema-on-read) — illisible tel quel par le
connecteur Postgres de Power BI. Une vue SQL a été créée pour l'aplatir :

```sql
create or replace view raw.v_logs_app_events as
select id, loaded_at,
       (data->>'timestamp')::timestamp as evenement_survenu_le,
       data->>'event_type' as type_evenement,
       data->>'niveau' as niveau,
       (data->>'client_id')::int as client_id,
       data->>'message' as message
from raw.logs_app_events;
```

Importée dans le modèle comme n'importe quelle autre table Postgres.
**Piège rencontré** : le connecteur Power BI Desktop avait mis en cache la
liste des tables/vues au moment du premier "Obtenir les données" — la
syntaxe standard `Source{[Schema="raw",Item="v_logs_app_events"]}` ne
trouvait pas la vue nouvellement créée (`La clé ne correspondait à aucune
ligne dans la table`), alors même que la vue existait bien côté Postgres.
Contournement : `Value.NativeQuery` (requête SQL passée telle quelle, pas
de dépendance à la liste de navigation mise en cache) — nécessite une
autorisation manuelle dans Power BI Desktop la première fois ("Exécuter la
requête native ?").

**Deuxième piège** : `evenement_survenu_le` porte une heure
(`2025-01-01T10:00:48`), `Dim Date[date]` est un pur jour (minuit) — une
relation directe entre les deux ne matchait donc jamais aucune ligne
(0 résultat silencieux, pas d'erreur). Corrigé par une colonne calculée
`date_evenement = DATE(YEAR(...), MONTH(...), DAY(...))`, reliée à
`Dim Date` à la place. Vérifié par requête DAX directe (60 événements le
2025-01-01, cohérent) avant de considérer le point réglé.

Reliée à `Dim Client` (`client_id`) et `Dim Date` (`date_evenement`) : les
mêmes segments (année, centre de coût si un jour élargi, client) filtrent
donc aussi cette table — c'est la partie "dynamique" de l'import, pas un
chiffre figé.

Mesures : `Nb événements`, `Nb erreurs` (niveau = error), `Taux d'erreur
%`. Sur les données actuelles : 23 841 événements, répartition par type
(view_product 8 202, login 4 830, add_to_cart 3 605, error 2 910,
purchase_attempt 2 333, purchase_success 1 961).

**Note** : les autres volumétries pipeline (lignes CRM, ERP, budget,
forecast) n'ont **pas** été réimportées séparément — elles sont déjà
disponibles nativement via `COUNTROWS` filtré sur `source`/table
existante (`Fct Ventes Réel[source]`, `Fct Budget`, `Fct Forecast`), pas
besoin d'une nouvelle table pour un chiffre déjà présent dans le modèle.

## Table calculée `Volumétrie Pipeline` — visuel « Volumétrie pipeline » (page RH)

Table déconnectée à 3 lignes (`DATATABLE`), juste les libellés `CRM
(raw)`, `ERP legacy valides`, `Logs applicatifs` — aucune donnée
dupliquée. La mesure `Lignes` fait un `SWITCH(SELECTEDVALUE(...), ...)`
qui va chercher le vrai compte par branche : `COUNTROWS` filtré sur
`Fct Ventes Réel[source]` pour CRM/ERP, `COUNTROWS('Fct Logs
Applicatifs')` pour les logs. Vérifié : 4 442 / 2 327 / 23 841, cohérent
avec `Fct Ventes Réel[source]="CRM"` / `="ERP_LEGACY"` et le total `Fct
Logs Applicatifs`. Table statique : ne bouge pas avec les filtres de
page (normal, indicateur technique).

## RLS (Row-Level Security) — page FinOps/Audit

4 rôles créés, reproduisant le comportement des comptes de service
BigQuery (`governance/test_acces_par_profil.py`, Sprint 6) :

| Rôle | Filtre sur `Fct Écarts Réel-Budget` | Équivalent BigQuery |
|---|---|---|
| RH | `FALSE()` (0 ligne) | `rh-viewer` : 0 ligne + colonne refusée |
| Finance | aucun (accès complet) | `finance-viewer` |
| Direction | aucun (accès complet) | `direction-viewer` |
| PDG | aucun (accès complet) | `pdg-viewer` |

Le filtre est **volontairement scopé à cette seule table**, comme sur
BigQuery (dette #5 : RLS appliquée à 1 mart sur 11, profondeur plutôt que
largeur) — les autres tables restent visibles à tous les rôles, pas de
sur-extension du périmètre par rapport à ce qui est documenté.

**Vérifié par requête DAX réelle** (simulation du filtre `FALSE()` du
rôle RH, l'impersonation de rôle via connexion séparée n'étant pas
supportée sur une instance Power BI Desktop locale) :

```
Sans filtre          : COUNTROWS('Fct Écarts Réel-Budget') = 2316
Filtre RH (FALSE())  : COUNTROWS('Fct Écarts Réel-Budget') = (vide)
```

**Piège DAX trouvé** : `COUNTROWS` sous un filtre `FALSE()` (donc sur
0 ligne) renvoie `BLANK`, pas `0` — comportement contre-intuitif mais
documenté (`FILTER(table, FALSE())` court-circuite tout le calcul à
blanc plutôt que de compter une table vide). Une carte affichant
`(Vide)` ressemble à une erreur pour la démo RLS. Corrigé en forçant la
coercition blanc → 0 : mesure `Nb lignes = COUNTROWS('Fct Écarts
Réel-Budget') + 0`. Revérifié : filtre RH → `0`, sans filtre → `2316`.

## Table de référence `Rôles RLS` — visuel « 4 rôles ↔ comptes de service » (page FinOps)

Table calculée statique (`DATATABLE`, 4 lignes, 3 colonnes texte) : pas
de champ "Rôle" natif dans Power BI (les rôles RLS sont de la config,
pas des données) — cette table sert uniquement à afficher la
correspondance rôle Power BI ↔ compte de service BigQuery dans un
visuel Table, sans rien taper à la main dans le canvas.

**Limite assumée** : Power BI Desktop natif ne fait que du filtrage de
lignes (RLS), pas de sécurité au niveau colonne (OLS — masquer uniquement
`montant_reel` tout en laissant les autres colonnes visibles). Ça
demanderait Tabular Editor ou un espace Fabric/Premium avec XMLA en
écriture, hors périmètre ici. Comme RH voit de toute façon 0 ligne sur
cette table, l'effet pratique est équivalent (rien à voir), mais ce n'est
pas formellement les deux mécanismes indépendants de BigQuery (RLS +
Policy Tag) — documenté plutôt que présenté comme identique.

**Pour tester dans Power BI Desktop** : ruban Modélisation → Afficher en
tant que → cocher un rôle → OK. Tous les visuels de toutes les pages se
recalculent en direct pour ce rôle — c'est un vrai test, pas une maquette.

## Pages (construites par Valentin, 4/4 terminées)

Captures dans `dashboards/powerbi/outputs/`.

- **Vue direction** (`page1-pdg.png`) : 4 cartes (CA Réel, Écart
  Réel-Budget, Clients actifs, Nb centres de coût), courbe Évolution
  mensuelle du CA (`Dim Date[annee_mois]`), barres Top centres de coût,
  carte CA Réel vs N-1 %.
- **Contrôle de gestion** (`page2-cg.png`) : barres groupées Réel vs
  Budget par nature de compte, matrice Top 10 écarts Réel/Budget,
  barres Allocation « Non affecté », cartes Budget/Forecast/Écart %.
- **RH & Opérationnel** (`page3-rh.png`) : barres CA par responsable
  (donnée pseudonymisée RGPD), barres Événements applicatifs par type
  (`Fct Logs Applicatifs[type_evenement]` seul en axe — **pas** de
  `Dim Date` dans ce visuel, qui sert uniquement au cross-filtre via les
  slicers de la page), carte Taux d'erreur %, table Volumétrie pipeline.
- **FinOps / Audit** (`page4-finops.png`) : explication + démo bascule
  de rôle (carte `Nb lignes` sur `Fct Écarts Réel-Budget`, à tester via
  Modélisation → Afficher en tant que), table `Rôles RLS`, bandeau sur
  la limite OLS.

Slicers communs à toutes les pages : Année/Trimestre/Mois via la
hiérarchie **Calendrier** de `Dim Date`, filtrés dynamiquement — vérifié
qu'ils propagent correctement jusqu'à `Fct Logs Applicatifs` via la
relation `date_evenement` → `Dim Date[date]` (23 841 événements au
total, 14 541 sur le seul filtre année 2025, cohérent).
