"""Test end-to-end du pipeline complet : source -> Bronze -> Gold -> BI -> reverse ETL
(Sprint 10, docs/ROADMAP.md). Enchaine les scripts existants (chacun a déjà son propre
demo()) plutôt que de les réécrire, et vérifie le résultat réel à chaque étape - pas
juste que les commandes rendent la main sans erreur.

Prérequis : `docker compose up -d` (tous les services healthy), venv activé.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import psycopg2
import requests
from dotenv import load_dotenv
from minio import Minio

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
ROOT = os.path.join(BASE_DIR, "..")
PYTHON = sys.executable


def run(relative_script):
    """Lance un script du pipeline avec le même interpréteur que ce test, échoue fort."""
    path = os.path.join(ROOT, relative_script)
    result = subprocess.run([PYTHON, path], cwd=os.path.dirname(path))
    assert result.returncode == 0, f"{relative_script} a échoué (code {result.returncode})"
    print(f"  OK  {relative_script}")


def pg_connect():
    return psycopg2.connect(
        host="127.0.0.1", port=5434,
        dbname=os.getenv("POSTGRES_DB", "dbt_dev"),
        user=os.getenv("POSTGRES_USER", "dbt_user"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )


def stage_source_to_bronze():
    print("1) Source -> Bronze")
    run("data-generation/generate_cg_data.py")
    run("data-generation/generate_logs_mongo.py")
    run("erp-legacy/generate_erp_legacy_export.py")
    run("data-contracts/ingest_to_bronze.py")


def stage_bronze_to_raw():
    print("2) Bronze -> raw Postgres")
    run("erp-legacy/migrate_erp_to_target.py")
    run("data-contracts/load_bronze_to_raw.py")


def stage_raw_to_gold():
    print("3) raw -> Gold (dbt build)")
    dbt_dir = os.path.join(ROOT, "dbt_cg")
    dbt_bin = os.path.join(ROOT, ".venv", "Scripts", "dbt.exe")
    result = subprocess.run(
        [dbt_bin, "build", "--profiles-dir", "."],
        cwd=dbt_dir, capture_output=True, text=True,
    )
    print(result.stdout[-2000:])
    assert result.returncode == 0, f"dbt build a échoué :\n{result.stderr}"

    with open(os.path.join(dbt_dir, "target", "run_results.json"), encoding="utf-8") as f:
        run_results = json.load(f)
    failures = [r for r in run_results["results"] if r["status"] not in ("success", "pass")]
    assert not failures, f"{len(failures)} nœud(s) dbt en échec : {[r['unique_id'] for r in failures]}"
    n_tests = sum(1 for r in run_results["results"] if r["status"] == "pass")
    n_models = sum(1 for r in run_results["results"] if r["status"] == "success")
    print(f"  OK  dbt build : {n_models} modèles, {n_tests} tests, 0 échec")


def stage_gold_to_bi():
    print("4) Gold -> BI (les marts lus par les dashboards/Power BI ont des données)")
    conn = pg_connect()
    cur = conn.cursor()
    checks = [
        ("public_marts.dim_date", 1000),
        ("public_marts.fct_ventes_reel", 1000),
        ("public_marts.fct_ecarts_reel_budget", 1000),
        ("public_marts.fct_budget", 100),
    ]
    for table, minimum in checks:
        cur.execute(f"select count(*) from {table}")
        n = cur.fetchone()[0]
        assert n >= minimum, f"{table} : {n} lignes, attendu >= {minimum}"
        print(f"  OK  {table} : {n} lignes")
    conn.close()


def stage_reverse_etl():
    print("5) Reverse ETL (webhook n8n -> clôture mensuelle -> dépôt MinIO)")
    resp = requests.post(
        "http://localhost:5678/webhook/trigger-cloture-mensuelle", timeout=15
    )
    assert resp.status_code == 200, f"webhook n8n : HTTP {resp.status_code} — {resp.text[:200]}"

    time.sleep(3)  # exécution asynchrone côté n8n (responseMode=onReceived)

    client = Minio(
        "localhost:9000",
        access_key=os.getenv("MINIO_ROOT_USER", "minio_admin"),
        secret_key=os.getenv("MINIO_ROOT_PASSWORD", "changeme123"),
        secure=False,
    )
    key = f"cloture/liasse_ecarts_{datetime.now(timezone.utc).strftime('%Y-%m')}.xlsx"
    stat = client.stat_object("gold-exports", key)
    age_seconds = (datetime.now(timezone.utc) - stat.last_modified).total_seconds()
    assert age_seconds < 60, (
        f"{key} existe mais date de {age_seconds:.0f}s — probablement un ancien "
        "dépôt, pas la preuve que ce run a déclenché le workflow"
    )
    print(f"  OK  gold-exports/{key} déposé il y a {age_seconds:.0f}s ({stat.size} octets)")


def main():
    for stage in (
        stage_source_to_bronze,
        stage_bronze_to_raw,
        stage_raw_to_gold,
        stage_gold_to_bi,
        stage_reverse_etl,
    ):
        stage()
    print("\ne2e OK : source -> Bronze -> Gold -> BI -> reverse ETL, bout en bout, données réelles vérifiées.")


if __name__ == "__main__":
    main()
