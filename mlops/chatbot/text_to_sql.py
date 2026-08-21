"""Chatbot BI Text-to-SQL : question en français -> SQL BigQuery -> réponse.

Génération : Ollama local (`llama3.2:1b`, déjà utilisé pour la veille
stratégique du Sprint 5 - modèle volontairement petit, cf. `docs/N8N.md`).
Aucune confiance accordée à la sortie du modèle : toute requête générée
passe par `valider_sql` (liste blanche de commandes/tables, une seule
instruction) puis un `dry_run` BigQuery (détecte les erreurs de syntaxe
sans consommer de quota) avant toute exécution réelle - même principe de
défense en profondeur que la RLS + policy tags du Sprint 6
(`docs/GOUVERNANCE.md`) : plusieurs mécanismes indépendants, pas un seul
filtre. Exécution avec `direction-viewer` (lecture seule, non masqué) et un
plafond `maximum_bytes_billed` (FinOps, même réflexe que le Sprint 6).

Usage : .venv/Scripts/python.exe mlops/chatbot/text_to_sql.py "question"
"""
import re
import sys

from google.cloud import bigquery

from schema import client_lecture, decrire_pour_prompt, lire_schema

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELE = "llama3.2:1b"
LIMITE_LIGNES = 100
OCTETS_MAX_FACTURES = 100 * 1024 * 1024  # 100 Mo - le dataset entier tient largement dedans

MOTS_INTERDITS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|MERGE|TRUNCATE|GRANT|REVOKE|CALL|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

PROMPT_TEMPLATE = """Tu es un generateur de requetes SQL BigQuery en lecture seule.
Schema disponible :
{schema}

Regle stricte : reponds UNIQUEMENT avec la requete SQL (SELECT uniquement), sans explication, sans balises markdown, une seule instruction, prefixe les tables par "marts.". N'utilise QUE les colonnes listees ci-dessus pour chaque table - montant_reel, montant_budget, ecart et ecart_pct n'existent QUE dans marts.fct_ecarts_reel_budget, jamais dans marts.dim_centre_cout.

Exemple :
Question : Quel est le libelle du centre de cout ayant le plus gros ecart total ?
SQL : SELECT dc.libelle FROM marts.fct_ecarts_reel_budget fe JOIN marts.dim_centre_cout dc ON fe.centre_cout_id = dc.centre_cout_id GROUP BY dc.libelle ORDER BY SUM(fe.ecart) DESC LIMIT 1

Question : {question}
SQL :"""


def generer_sql(question, schema_desc, modele=MODELE):
    import requests
    prompt = PROMPT_TEMPLATE.format(schema=schema_desc, question=question)
    r = requests.post(OLLAMA_URL, json={"model": modele, "stream": False, "prompt": prompt}, timeout=60)
    r.raise_for_status()
    reponse = r.json()["response"].strip()
    # le modele ajoute parfois des balises markdown malgre la consigne
    reponse = re.sub(r"^```sql\s*|```$", "", reponse, flags=re.IGNORECASE | re.MULTILINE).strip()
    return reponse


def valider_sql(sql, tables_autorisees):
    """Garde-fou avant toute exécution : la sortie d'un LLM n'est jamais
    fiable par construction, on ne l'exécute jamais telle quelle.
    Renvoie (True, sql_nettoyé) ou (False, raison_du_rejet)."""
    nettoye = sql.strip().rstrip(";").strip()
    if not nettoye:
        return False, "SQL vide"
    if ";" in nettoye:
        return False, "plusieurs instructions détectées (';' au milieu de la requête)"
    if not re.match(r"^(SELECT|WITH)\b", nettoye, re.IGNORECASE):
        return False, "ne commence pas par SELECT/WITH"
    if MOTS_INTERDITS.search(nettoye):
        return False, "contient un mot-clé DDL/DML interdit"
    tables_referencees = re.findall(r"(?:FROM|JOIN)\s+`?(?:marts\.)?(\w+)`?", nettoye, re.IGNORECASE)
    inconnues = [t for t in tables_referencees if t.lower() not in tables_autorisees]
    if inconnues:
        return False, f"table(s) non autorisée(s) : {inconnues}"
    return True, nettoye


def ajouter_limite(sql, limite=LIMITE_LIGNES):
    if re.search(r"\bLIMIT\s+\d+\s*$", sql, re.IGNORECASE):
        return sql
    return f"{sql}\nLIMIT {limite}"


def repondre(question, client=None):
    """Pipeline complet : schéma -> génération -> validation -> dry_run -> exécution.
    Renvoie un dict {"ok": bool, "sql": str, "lignes": [...] | None, "erreur": str | None} -
    la requête générée est toujours renvoyée, même en cas de rejet (transparence,
    debug) - jamais de "boîte noire" sur ce qui a été tenté."""
    client = client or client_lecture()
    tables = lire_schema(client)
    schema_desc = decrire_pour_prompt(tables)

    sql_brut = generer_sql(question, schema_desc)
    ok, sql_ou_raison = valider_sql(sql_brut, {t.lower() for t in tables})
    if not ok:
        return {"ok": False, "sql": sql_brut, "lignes": None, "erreur": sql_ou_raison}

    sql = ajouter_limite(sql_ou_raison)
    try:
        client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    except Exception as exc:
        return {"ok": False, "sql": sql, "lignes": None, "erreur": f"dry_run échoué : {exc}"}

    try:
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=OCTETS_MAX_FACTURES)
        lignes = [dict(r) for r in client.query(sql, job_config=job_config).result()]
    except Exception as exc:
        return {"ok": False, "sql": sql, "lignes": None, "erreur": f"exécution échouée : {exc}"}

    return {"ok": True, "sql": sql, "lignes": lignes, "erreur": None}


def demo():
    """Self-check de `valider_sql` seul (pas de dépendance Ollama/BigQuery) :
    les tentatives malveillantes/hallucinées doivent toutes être rejetées,
    une requête légitime doit passer."""
    tables = {"fct_ecarts_reel_budget", "dim_centre_cout"}
    cas_rejetes = [
        "DROP TABLE marts.fct_ecarts_reel_budget",
        "SELECT * FROM marts.fct_ecarts_reel_budget; DROP TABLE marts.dim_centre_cout",
        "DELETE FROM marts.fct_ecarts_reel_budget",
        "SELECT * FROM marts.table_secrete",
        "UPDATE marts.fct_ecarts_reel_budget SET montant_reel = 0",
        "",
    ]
    for sql in cas_rejetes:
        ok, raison = valider_sql(sql, tables)
        assert not ok, f"aurait dû être rejeté : {sql!r} (accepté avec {raison!r})"

    ok, propre = valider_sql(
        "SELECT centre_cout_id, SUM(montant_reel) FROM marts.fct_ecarts_reel_budget GROUP BY 1",
        tables,
    )
    assert ok, "une requête SELECT légitime sur une table autorisée devrait passer"
    assert ajouter_limite("SELECT 1 LIMIT 10").count("LIMIT") == 1, \
        "LIMIT déjà présent ne doit pas être doublé"
    assert ajouter_limite("SELECT 1").count("LIMIT") == 1, \
        "LIMIT absent doit être ajouté"

    print(f"demo(): OK - {len(cas_rejetes)} requêtes malveillantes/invalides rejetées, "
          f"1 requête légitime acceptée")


if __name__ == "__main__":
    demo()
    if len(sys.argv) > 1:
        resultat = repondre(" ".join(sys.argv[1:]))
        print(f"SQL générée :\n{resultat['sql']}\n")
        if resultat["ok"]:
            for ligne in resultat["lignes"]:
                print(ligne)
        else:
            print(f"Rejetée : {resultat['erreur']}")
