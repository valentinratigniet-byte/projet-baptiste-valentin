"""Schéma du dataset `marts` (BigQuery), introspecté en direct via
INFORMATION_SCHEMA plutôt qu'écrit à la main : reste synchrone avec le
dataset réel sans étape de régénération séparée (rien d'inventé). Sert de
contexte au générateur SQL (`text_to_sql.py`) et de source de vérité pour la
liste des tables autorisées (garde-fou de sécurité).

Usage : import direct, ou `python mlops/chatbot/schema.py` pour un aperçu.
"""
import os

from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

load_dotenv()

BQ_PROJECT = os.getenv("BQ_PROJECT", "bv-dataplatform")
KEYS_DIR = os.path.join(os.path.expanduser("~"), ".gcp", "bv-viewers")
PROFIL_LECTURE = "direction-viewer"  # voir mlops/forecast.py : lecture non masquée nécessaire pour le BI


def client_lecture():
    keyfile = os.path.join(KEYS_DIR, f"{PROFIL_LECTURE}.json")
    creds = service_account.Credentials.from_service_account_file(keyfile)
    return bigquery.Client(project=BQ_PROJECT, credentials=creds)


def lire_schema(client):
    """{nom_table: [(colonne, type), ...]} pour tout le dataset `marts`."""
    rows = client.query(
        "SELECT table_name, column_name, data_type "
        "FROM `marts.INFORMATION_SCHEMA.COLUMNS` "
        "ORDER BY table_name, ordinal_position"
    ).result()
    tables = {}
    for r in rows:
        tables.setdefault(r.table_name, []).append((r.column_name, r.data_type))
    return tables


def decrire_pour_prompt(tables):
    """Format compact injecté dans le prompt du LLM."""
    lignes = []
    for table, colonnes in tables.items():
        cols = ", ".join(f"{c} {t}" for c, t in colonnes)
        lignes.append(f"Table marts.{table} (colonnes: {cols})")
    return "\n".join(lignes)


if __name__ == "__main__":
    tables = lire_schema(client_lecture())
    print(decrire_pour_prompt(tables))
