"""Régénère les données des 4 tableaux de bord (index.html, Sprint 9) depuis
les sources réelles du projet : Postgres dev (marts CG) pour PDG/Contrôle de
gestion/RH, BigQuery (4 comptes de service `*-viewer`) pour la preuve RLS +
masking et les métadonnées de stockage du dataset `marts` FinOps.

Rien n'est simulé : chaque nombre vient d'une requête réelle exécutée au
moment du run. Best-effort sur la partie BigQuery (comme le reste du
portfolio) : si les clés de service ne sont pas disponibles, la section
finops.rls_profils est simplement absente plutôt que de faire échouer tout
l'export.

Usage :
    python dashboards/scripts/export_dashboard_data.py
"""
import json
import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

HERE = Path(__file__).resolve().parent
HTML_PATH = HERE.parent / "index.html"
KEYS_DIR = Path.home() / ".gcp" / "bv-viewers"
PROFILS = ["rh-viewer", "finance-viewer", "direction-viewer", "pdg-viewer"]


def pg_connect():
    return psycopg2.connect(
        host="127.0.0.1", port=5434,
        dbname=os.getenv("POSTGRES_DB", "dbt_dev"),
        user=os.getenv("POSTGRES_USER", "dbt_user"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )


def rows(cur, query, params=None):
    cur.execute(query, params or ())
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def build_pdg(cur):
    kpis = rows(cur, """
        SELECT
          (SELECT sum(montant_reel) FROM public_marts.fct_ventes_reel) AS ca_total,
          (SELECT count(DISTINCT client_id) FROM public_marts.fct_ventes_reel) AS clients_actifs,
          (SELECT count(*) FROM public_marts.dim_centre_cout) AS nb_centres,
          (SELECT sum(montant_budget) FROM public_marts.fct_budget) AS budget_total,
          (SELECT sum(montant_forecast) FROM public_marts.fct_forecast) AS forecast_total,
          (SELECT sum(ecart) FROM public_marts.fct_ecarts_reel_budget) AS ecart_total
    """)[0]

    top_centres = rows(cur, """
        SELECT dc.libelle, dc.responsable, sum(f.montant_reel) AS ca
        FROM public_marts.fct_ventes_reel f
        JOIN public_marts.dim_centre_cout dc ON dc.centre_cout_id = f.centre_cout_id
        GROUP BY 1, 2 ORDER BY ca DESC
    """)

    evolution = rows(cur, """
        SELECT to_char(date_trunc('month', date_vente), 'YYYY-MM') AS mois,
               sum(montant_reel) AS ca
        FROM public_marts.fct_ventes_reel
        GROUP BY 1 ORDER BY 1
    """)

    return {**kpis, "top_centres": top_centres, "evolution_mensuelle": evolution}


def build_cg(cur):
    top_ecarts = rows(cur, """
        SELECT dc.libelle AS centre, dcp.libelle AS compte,
               to_char(e.periode, 'YYYY-MM') AS periode,
               e.montant_reel AS reel, e.montant_budget AS budget,
               e.ecart, e.ecart_pct
        FROM public_marts.fct_ecarts_reel_budget e
        JOIN public_marts.dim_centre_cout dc ON dc.centre_cout_id = e.centre_cout_id
        JOIN public_marts.dim_compte dcp ON dcp.compte_id = e.compte_id
        WHERE e.ecart IS NOT NULL
        ORDER BY abs(e.ecart) DESC LIMIT 10
    """)

    nature = rows(cur, """
        SELECT dcp.nature, count(*) AS nb_lignes,
               sum(e.montant_reel) AS reel, sum(e.montant_budget) AS budget
        FROM public_marts.fct_ecarts_reel_budget e
        JOIN public_marts.dim_compte dcp ON dcp.compte_id = e.compte_id
        GROUP BY 1
    """)

    allocation = rows(cur, """
        SELECT dc.libelle AS centre, a.ca_propre, a.cle_repartition, a.montant_alloue
        FROM public_marts.fct_allocation_couts a
        JOIN public_marts.dim_centre_cout dc ON dc.centre_cout_id = a.centre_cout_id
        ORDER BY a.montant_alloue DESC
    """)

    return {"top_ecarts": top_ecarts, "nature": nature, "allocation": allocation}


def build_rh(cur):
    responsables = rows(cur, """
        SELECT dc.libelle AS centre, dc.responsable, sum(f.montant_reel) AS ca
        FROM public_marts.fct_ventes_reel f
        JOIN public_marts.dim_centre_cout dc ON dc.centre_cout_id = f.centre_cout_id
        WHERE dc.responsable IS NOT NULL
        GROUP BY 1, 2 ORDER BY ca DESC
    """)

    pipeline = rows(cur, """
        SELECT
          (SELECT count(*) FROM raw.crm_fact_ventes_reel) AS crm_lignes,
          (SELECT count(*) FROM public_staging.stg_erp__fact_ventes_migre) AS erp_valides,
          (SELECT count(*) FROM raw.logs_app_events) AS logs_events,
          (SELECT count(*) FROM raw.finance_fact_budget) AS budget_lignes,
          (SELECT count(*) FROM raw.finance_fact_forecast) AS forecast_lignes
    """)[0]

    return {"responsables": responsables, "pipeline": pipeline}


def build_dbt_test_stats():
    """Statut réel du dernier `dbt build` (target/run_results.json), pas une
    estimation. 'tests' = nœuds de type test uniquement (les modèles sont
    comptés à part) : voir le nombre total de nœuds exécutés séparément."""
    target = HERE.parent.parent / "dbt_cg" / "target" / "run_results.json"
    if not target.exists():
        return None
    rr = json.loads(target.read_text(encoding="utf-8"))
    tests = [r for r in rr["results"] if r["unique_id"].startswith("test.")]
    models = [r for r in rr["results"] if r["unique_id"].startswith("model.")]
    return {
        "tests_total": len(tests),
        "tests_ok": sum(1 for r in tests if r["status"] == "success"),
        "models_total": len(models),
        "generated_at": rr["metadata"]["generated_at"],
    }


def build_finops():
    """Best-effort : dégrade silencieusement si les clés de service (BigQuery)
    ne sont pas disponibles sur cette machine, comme le reste du portfolio."""
    if not KEYS_DIR.exists() or not os.getenv("BQ_KEYFILE"):
        return {}
    try:
        from google.api_core.exceptions import Forbidden
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError:
        return {}

    bq_project = os.getenv("BQ_PROJECT", "bv-dataplatform")

    def client_for(profil):
        creds = service_account.Credentials.from_service_account_file(str(KEYS_DIR / f"{profil}.json"))
        return bigquery.Client(project=bq_project, credentials=creds)

    rls_profils = []
    for profil in PROFILS:
        try:
            client = client_for(profil)
            try:
                n = list(client.query("SELECT COUNT(*) AS n FROM `marts.fct_ecarts_reel_budget`").result())[0].n
            except Forbidden:
                n = None
            try:
                total = list(client.query("SELECT SUM(montant_reel) AS total FROM `marts.fct_ecarts_reel_budget`").result())[0].total
            except Forbidden:
                total = None
            rls_profils.append({
                "profil": profil,
                "lignes_visibles": n,
                "montant_visible": float(total) if total is not None else None,
            })
        except Exception as e:
            rls_profils.append({"profil": profil, "erreur": str(e)})

    tables = []
    try:
        loader_creds = service_account.Credentials.from_service_account_file(os.environ["BQ_KEYFILE"])
        loader = bigquery.Client(project=bq_project, credentials=loader_creds)
        for t in loader.list_tables("marts"):
            tbl = loader.get_table(t.reference)
            part = tbl.time_partitioning
            tables.append({
                "table": tbl.table_id,
                "rows": tbl.num_rows,
                "mb": round((tbl.num_bytes or 0) / 1024 / 1024, 4),
                "partitioned_by": part.field if part else None,
                "retention_jours": round(part.expiration_ms / 86_400_000) if part and part.expiration_ms else None,
            })
    except Exception:
        pass

    return {"rls_profils": rls_profils, "tables_bigquery": tables}


def to_js_const(var_name, data):
    return f"  const {var_name} = {json.dumps(data, ensure_ascii=False, indent=2, default=str)};"


def splice(html_path, marker, block):
    html = html_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(// {marker}:BEGIN.*?\n)(.*?)(\n\s*// {marker}:END)", re.S)
    if not pattern.search(html):
        raise SystemExit(f"Marqueurs {marker} introuvables dans {html_path}")
    html_path.write_text(pattern.sub(lambda m: m.group(1) + block + m.group(3), html), encoding="utf-8")


def main():
    conn = pg_connect()
    cur = conn.cursor()
    data = {
        "pdg": build_pdg(cur),
        "cg": build_cg(cur),
        "rh": build_rh(cur),
        "dbt": build_dbt_test_stats(),
        "finops": build_finops(),
    }
    cur.close()
    conn.close()

    splice(HTML_PATH, "DASHBOARD-DATA", to_js_const("DASHBOARD_DATA", data))
    n_finops = len(data["finops"].get("rls_profils", []))
    print(f"OK — {HTML_PATH} régénéré. FinOps : {n_finops}/4 profils BigQuery interrogés.")


def demo():
    """Self-check sans dépendance externe : vérifie que le pipeline JSON->HTML
    (splice) fonctionne sur un jeu de données minimal, sans toucher Postgres/BigQuery."""
    import tempfile
    fake_html = "<script>\n  // DASHBOARD-DATA:BEGIN\n  const DASHBOARD_DATA = {};\n  // DASHBOARD-DATA:END\n</script>"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fake.html"
        path.write_text(fake_html, encoding="utf-8")
        splice(path, "DASHBOARD-DATA", to_js_const("DASHBOARD_DATA", {"pdg": {"ca_total": 1.0}}))
        assert "1.0" in path.read_text(encoding="utf-8")
    print("demo() OK — splice JSON->HTML fonctionne")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        main()
