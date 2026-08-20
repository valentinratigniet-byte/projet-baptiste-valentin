"""Synchronise le mart le plus sensible du modèle CG (`fct_ecarts_reel_budget`
+ `dim_centre_cout` pour la lisibilité) depuis Postgres vers BigQuery, table
partitionnée par mois avec rétention (FinOps).

Portée volontairement limitée à une table plutôt que tout l'entrepôt : la
gouvernance (RLS + masking, ce script + les scripts `governance/`) est
prouvée de bout en bout sur un cas réel plutôt que déployée superficiellement
partout. Voir docs/GOUVERNANCE.md.

Usage : .venv/Scripts/python.exe governance/sync_marts_to_bigquery.py
"""
import os

import psycopg2
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

load_dotenv()

BQ_PROJECT = os.getenv("BQ_PROJECT", "bv-dataplatform")
RETENTION_JOURS = 730  # 2 ans (FinOps) - au-dela, les partitions expirent automatiquement


def get_bq_client():
    """Credentials explicites depuis BQ_KEYFILE, jamais l'ADC ambiant :
    GOOGLE_APPLICATION_CREDENTIALS est deja positionnee de facon persistante
    sur cette machine pour un autre projet GCP (portfolio-data-vr) - s'y fier
    aurait silencieusement charge le mauvais compte de service."""
    creds = service_account.Credentials.from_service_account_file(os.environ["BQ_KEYFILE"])
    return bigquery.Client(project=BQ_PROJECT, credentials=creds)


def read_postgres(query, colnames):
    conn = psycopg2.connect(
        host="127.0.0.1", port=5434,
        dbname=os.getenv("POSTGRES_DB", "dbt_dev"),
        user=os.getenv("POSTGRES_USER", "dbt_user"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )
    cur = conn.cursor()
    cur.execute(query)
    rows = [dict(zip(colnames, r)) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def load_dim_centre_cout(client):
    rows = read_postgres(
        "SELECT centre_cout_id, code, libelle, responsable, centre_parent_id "
        "FROM public_marts.dim_centre_cout",
        ["centre_cout_id", "code", "libelle", "responsable", "centre_parent_id"])
    for r in rows:
        r["centre_cout_id"] = str(r["centre_cout_id"])  # JSON-safe

    table_id = f"{BQ_PROJECT}.marts.dim_centre_cout"
    schema = [
        bigquery.SchemaField("centre_cout_id", "INT64"),
        bigquery.SchemaField("code", "STRING"),
        bigquery.SchemaField("libelle", "STRING"),
        bigquery.SchemaField("responsable", "STRING"),
        bigquery.SchemaField("centre_parent_id", "INT64"),
    ]
    client.delete_table(table_id, not_found_ok=True)
    table = bigquery.Table(table_id, schema=schema)
    client.create_table(table)
    job = client.load_table_from_json(rows, table_id)
    job.result()
    print(f"  {table_id} <- {len(rows)} lignes")


def load_fct_ecarts(client):
    rows = read_postgres(
        "SELECT periode, centre_cout_id, compte_id, montant_reel, montant_budget, "
        "ecart, ecart_pct FROM public_marts.fct_ecarts_reel_budget",
        ["periode", "centre_cout_id", "compte_id", "montant_reel", "montant_budget",
         "ecart", "ecart_pct"])
    for r in rows:
        r["periode"] = r["periode"].isoformat()
        for champ in ("montant_reel", "montant_budget", "ecart", "ecart_pct"):
            r[champ] = float(r[champ]) if r[champ] is not None else None

    table_id = f"{BQ_PROJECT}.marts.fct_ecarts_reel_budget"
    schema = [
        bigquery.SchemaField("periode", "DATE"),
        bigquery.SchemaField("centre_cout_id", "INT64"),
        bigquery.SchemaField("compte_id", "INT64"),
        bigquery.SchemaField("montant_reel", "NUMERIC"),
        bigquery.SchemaField("montant_budget", "NUMERIC"),
        bigquery.SchemaField("ecart", "NUMERIC"),
        bigquery.SchemaField("ecart_pct", "NUMERIC"),
    ]
    client.delete_table(table_id, not_found_ok=True)
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.MONTH,
        field="periode",
        expiration_ms=RETENTION_JOURS * 24 * 60 * 60 * 1000,
    )
    client.create_table(table)
    job = client.load_table_from_json(rows, table_id)
    job.result()
    print(f"  {table_id} <- {len(rows)} lignes, partitionnee par mois, "
          f"retention {RETENTION_JOURS}j")


def main():
    client = get_bq_client()
    print("Synchronisation vers BigQuery...")
    load_dim_centre_cout(client)
    load_fct_ecarts(client)
    print("Termine. Prochaine etape : governance/apply_rls_and_masking.py")


if __name__ == "__main__":
    main()
