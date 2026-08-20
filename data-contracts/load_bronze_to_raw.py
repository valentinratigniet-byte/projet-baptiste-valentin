"""Charge les objets Bronze (MinIO, validés au Sprint 3) dans Postgres,
schéma `raw`, une table par flux, colonne `data JSONB` (schema-on-read —
c'est dbt (models/staging/) qui type et nomme les colonnes, pas ce loader).

Prend le dernier run (objet le plus récent) de chaque flux.

Usage : .venv/Scripts/python.exe data-contracts/load_bronze_to_raw.py
"""
import io
import json
import os

import psycopg2
from dotenv import load_dotenv
from minio import Minio

load_dotenv()

FLOWS = [
    "crm/dim_client", "crm/dim_produit", "crm/fact_ventes_reel",
    "logs/app_events",
    "finance/dim_centre_cout", "finance/dim_compte", "finance/dim_version_budget",
    "finance/fact_budget", "finance/fact_forecast",
    "erp_legacy/vente_ligne_brute",
]


def table_name(flow):
    return flow.replace("/", "_")


def latest_object(client, bucket, prefix):
    objects = list(client.list_objects(bucket, prefix=f"{prefix}/", recursive=True))
    if not objects:
        return None
    return max(objects, key=lambda o: o.last_modified).object_name


def read_jsonl(client, bucket, object_name):
    resp = client.get_object(bucket, object_name)
    try:
        text = resp.read().decode("utf-8")
    finally:
        resp.close()
        resp.release_conn()
    return [json.loads(line) for line in text.splitlines() if line]


def main():
    minio_client = Minio("localhost:9000",
                          access_key=os.getenv("MINIO_ROOT_USER", "minio_admin"),
                          secret_key=os.getenv("MINIO_ROOT_PASSWORD", "changeme123"),
                          secure=False)
    conn = psycopg2.connect(
        host="127.0.0.1", port=5434,
        dbname=os.getenv("POSTGRES_DB", "dbt_dev"),
        user=os.getenv("POSTGRES_USER", "dbt_user"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS raw")

    total = 0
    for flow in FLOWS:
        table = table_name(flow)
        obj = latest_object(minio_client, "bronze", flow)
        if not obj:
            print(f"  {flow}: aucun objet Bronze trouvé (lancer data-contracts/ingest_to_bronze.py d'abord)")
            continue
        records = read_jsonl(minio_client, "bronze", obj)

        cur.execute(f"CREATE TABLE IF NOT EXISTS raw.{table} "
                    f"(id SERIAL PRIMARY KEY, loaded_at TIMESTAMPTZ DEFAULT now(), data JSONB)")
        cur.execute(f"TRUNCATE raw.{table}")
        cur.executemany(f"INSERT INTO raw.{table} (data) VALUES (%s)",
                         [(json.dumps(r),) for r in records])
        conn.commit()
        total += len(records)
        print(f"  raw.{table} <- {len(records)} lignes (depuis {obj})")

    print(f"Total : {total} lignes chargées dans le schéma raw.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
