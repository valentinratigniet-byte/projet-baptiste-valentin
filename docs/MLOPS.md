# MLOps (Sprint 7)

Trois briques indépendantes, toutes lues/écrites depuis les mêmes marts
gouvernés du Sprint 6 : forecasting, détection de drift, chatbot BI
Text-to-SQL — chacune avec son propre `docs/DETTE-TECHNIQUE.md` si un
raccourci a été pris.

## Forecasting (`mlops/forecast.py`)

Lissage exponentiel de Holt (tendance additive, sans saisonnalité,
`statsmodels`) sur `marts.fct_ecarts_reel_budget` (BigQuery), 3 mois devant,
par `(centre_cout_id, compte_id)`. Pas de modèle saisonnier : les séries
sont simulées sans saisonnalité réelle documentée (`docs/MCD.md`), un
SARIMA n'apporterait que des paramètres en plus, rien de vérifiable.

Séries < 6 mois d'historique de Réel non nul : ignorées plutôt que forcées
à produire un chiffre non fiable — limite assumée, pas un bug. Sur les
données actuelles : **6 séries au total, 3 prévues, 3 ignorées** (le Réel
ne couvre qu'une poignée de combinaisons centre/compte — la CA se
concentre sur peu de comptes, contrairement au Budget qui en couvre
beaucoup plus ; cohérent avec le modèle métier documenté ailleurs, pas une
anomalie).

Lecture non masquée (`montant_reel` est confidentiel, la prévision en a
besoin) via `direction-viewer` — le compte de chargement (`BQ_KEYFILE`) n'a
volontairement pas ce droit (moindre privilège : il crée/écrit des tables,
il n'a pas vocation à en lire le contenu sensible). Résultat écrit dans
`marts.ml_forecast_reel` (méthode, date de génération incluses — traçable).

## Détection de drift (`mlops/drift_detection.py`)

Evidently AI (`DataDriftPreset`) sur `stg_crm__fact_ventes_reel` (Postgres
dev, ~4 400 lignes) : `montant_reel`/`quantite` (K-S), `centre_cout_id`/
`produit_id`/`source` (test catégoriel).

**Limite assumée** : le pipeline n'a encore qu'une seule exécution réelle,
donc pas d'historique de runs Bronze successifs à comparer. La "dérive"
est mesurée entre les deux moitiés chronologiques du même jeu de données
(ancien vs récent) — prouve le mécanisme, pas une vraie dérive de
production. Mise à niveau : comparer Bronze du jour à Bronze de la veille
une fois le pipeline exécuté plusieurs fois dans le temps (n8n pourrait le
déclencher quotidiennement, Sprint 5).

Résultat réel mesuré : **3 colonnes sur 5 en dérive (60%)** entre les deux
moitiés — verdict "DÉRIVE DÉTECTÉE" au seuil de 50%. Rapport détaillé
(HTML, Evidently) dans `mlops/reports/drift_report.html` (généré, pas
commité — `.gitignore`).

Part de colonnes en dérive calculée à partir des p-values par colonne
(`ValueDrift`) plutôt que de la métrique agrégée `DriftedColumnsCount` du
preset : cette dernière utilise en interne un test par défaut différent
par colonne (Wasserstein plutôt que K-S, notamment) et donnait un chiffre
incohérent avec le détail affiché colonne par colonne — trouvé en
vérifiant le script, corrigé pour n'avoir qu'une seule source de vérité.

## Chatbot BI Text-to-SQL (`mlops/chatbot/`)

Pipeline : question en français → schéma introspecté en direct
(`schema.py`, `INFORMATION_SCHEMA.COLUMNS`, jamais figé en dur) → SQL
généré par Ollama local (`text_to_sql.py`) → validation stricte
(`valider_sql` : une seule instruction, `SELECT`/`WITH` uniquement, aucun
mot-clé DDL/DML, table référencée dans une liste blanche) → `dry_run`
BigQuery (détecte les hallucinations de schéma avant tout coût/effet) →
exécution plafonnée (`maximum_bytes_billed`, `LIMIT` auto-ajoutée) avec
`direction-viewer` (lecture seule, non masqué).

Défense en profondeur volontairement dupliquée par rapport à la RLS +
policy tags du Sprint 6 (`docs/GOUVERNANCE.md`) : plusieurs mécanismes
indépendants plutôt qu'un seul filtre — la sortie d'un LLM n'est jamais
fiable par construction, elle est traitée comme une entrée utilisateur non
fiable, pas comme du SQL de confiance.

### Modèle : 1B gardé, 3B testé et rejeté pour latence

`llama3.2:1b` (déjà utilisé pour la veille du Sprint 5) a été gardé après
un test comparatif avec `llama3.2:3b`, ce dernier étant la piste annoncée
dans `docs/N8N.md` ("un modèle plus gros donnera un résultat plus
exploitable"). En pratique sur cette machine (Ollama en conteneur Docker,
CPU uniquement, pas de GPU passé au conteneur) :

- `llama3.2:1b` : ~1-3s par question, exploitable en interactif
- `llama3.2:3b` : **169s (2 min 49s) mesurées sur une seule question**
  (704% CPU observé, `docker stats`, pas de GPU passé au conteneur) —
  réponse correcte cette fois-là, mais inutilisable en interactif à ce
  temps de latence

Correction du forward-reference de `docs/N8N.md` : la piste "modèle plus
gros" a été testée, pas ignorée — le compromis latence/précision a
tranché en faveur du 1B, documenté ici plutôt que silencieusement conservé.

### Évaluation (`eval_chatbot.py`, `questions_verite_terrain.json`)

Méthode "execution accuracy" : on ne compare pas le texte SQL généré (un
même résultat s'écrit de plusieurs façons syntaxiquement valides), on
compare le résultat de son exécution à celui d'une requête de référence
écrite à la main, exécutée en direct sur les mêmes données au moment du
test — pas de valeurs figées en dur. Comparaison insensible à l'ordre des
lignes, au nom des colonnes (`COUNT(*)` sans alias devient `f0_` côté
BigQuery) et à l'arrondi flottant.

**Précision mesurée : 3/10 (30%) en zero-shot, 6/10 (60%) après ajout d'un
exemple few-shot au prompt** (JOIN de référence + rappel explicite que les
colonnes montant_reel/montant_budget/ecart/ecart_pct n'existent que dans
`fct_ecarts_reel_budget`, jamais dans `dim_centre_cout` — l'erreur la plus
fréquente du modèle). Échecs restants : confusion de table sur les
questions nécessitant un JOIN, agrégats imbriqués mal formés
(`SUM` sans `GROUP BY`), `LIMIT` mal placée. Plafond connu d'un modèle 1B
sur du texte-vers-SQL avec JOIN — cohérent avec la limite déjà documentée
pour la veille stratégique (`docs/N8N.md`).

Le `dry_run` BigQuery s'est avéré être le vrai filet de sécurité plus que
de qualité : la plupart des échecs sont rejetés *avant* exécution
(hallucination de colonne/table détectée), jamais une réponse fausse
présentée comme correcte silencieusement.

## Dette technique ajoutée ce sprint

Voir `docs/DETTE-TECHNIQUE.md` (lignes #9 et #10) :

- Le chatbot lit toujours en `direction-viewer` (vision complète, non
  masquée) quel que soit qui pose la question — pas de routage RLS par
  profil comme pour les comptes de service du Sprint 6. Il n'existe pas de
  notion d'utilisateur/session dans ce portfolio pour router autrement.
- La détection de drift compare deux moitiés du même run plutôt que deux
  runs réels successifs (cf. section dédiée ci-dessus).

## CI

`.github/workflows/ci.yml` exécute les 4 self-checks (`demo()`, aucune
dépendance BigQuery/Ollama) après `dbt build`, plus `drift_detection.py`
en entier (lit le staging Postgres du run CI lui-même, aucune dépendance
externe). `forecast.py` et le chatbot ne tournent pas en CI : ils
nécessitent BigQuery (compte de service réel) et Ollama (modèle local) —
ni l'un ni l'autre disponibles dans un runner GitHub Actions public, même
principe que `governance/` (Sprint 6), jamais en CI.
