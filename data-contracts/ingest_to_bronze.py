"""Pipeline d'ingestion Sprint 3 : lit chaque flux source, applique le data
contract JSON Schema correspondant, anonymise RGPD les champs personnels
identifiés, puis écrit les enregistrements acceptés dans MinIO
(bucket `bronze`) et les rejetés dans `rejects` (Dead-Letter-Queue) avec le
motif du rejet.

Classification RGPD (voir docs/DATA-CONTRACTS.md) : les raisons sociales
d'entreprises (`dim_client.libelle`, `RSCLI` de l'ERP) ne sont PAS anonymisées
— une personne morale n'est pas une personne physique au sens RGPD. Le seul
champ identifié comme donnée personnelle est `dim_centre_cout.responsable`
(nom d'un salarié) : anonymisé par hash irréversible avant toute écriture.

Usage : .venv/Scripts/python.exe data-contracts/ingest_to_bronze.py
"""
import csv
import hashlib
import io
import json
import os
from datetime import date, datetime, timezone

import jsonschema
import mysql.connector
from dotenv import load_dotenv
from minio import Minio
from pymongo import MongoClient

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
SCHEMAS_DIR = os.path.join(BASE_DIR, "schemas")
FINANCE_DIR = os.path.join(BASE_DIR, "..", "data-generation", "output")
ERP_DIR = os.path.join(BASE_DIR, "..", "erp-legacy", "exports")
RUN_TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
SALT = os.getenv("ANONYMIZATION_SALT", "changeme-salt")


def anonymize_person(nom):
    """Hash irréversible (pas de mapping conservé) -> vraie anonymisation,
    pas une pseudonymisation réversible."""
    h = hashlib.sha256((SALT + nom).encode()).hexdigest()[:10]
    return f"Salarie_{h}"


def to_jsonable(record):
    out = {}
    for k, v in record.items():
        if isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        elif hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
            out[k] = float(v)  # Decimal (MySQL)
        else:
            out[k] = v
    return out


# --- Lecteurs par source -----------------------------------------------

def read_mysql(query):
    conn = mysql.connector.connect(
        host="127.0.0.1", port=3306,
        user=os.getenv("MYSQL_USER", "crm_user"),
        password=os.getenv("MYSQL_PASSWORD", "changeme"),
        database="crm",
    )
    cur = conn.cursor(dictionary=True)
    cur.execute(query)
    rows = [to_jsonable(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def read_mongo():
    uri = (f"mongodb://{os.getenv('MONGO_USER', 'mongo_admin')}:"
           f"{os.getenv('MONGO_PASSWORD', 'changeme')}@127.0.0.1:27017/?authSource=admin")
    client = MongoClient(uri)
    docs = list(client["logs"]["app_events"].find({}, {"_id": 0}))
    client.close()
    return [to_jsonable(d) for d in docs]


def read_finance_csv(filename, int_fields, float_fields):
    path = os.path.join(FINANCE_DIR, filename)
    rows = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for k in int_fields:
                row[k] = int(row[k]) if row[k] not in (None, "") else None
            for k in float_fields:
                row[k] = float(row[k]) if row[k] not in (None, "") else None
            rows.append(row)
    return rows


def read_erp_legacy_raw():
    path = os.path.join(ERP_DIR, "ERP_EXPORT_VTE_2023_2024.csv")
    with open(path, encoding="latin-1") as f:
        return list(csv.DictReader(f, delimiter=";"))


# --- Anonymisation par flux ----------------------------------------------

def anonymize_centre_cout(records):
    for r in records:
        r["responsable"] = anonymize_person(r["responsable"])
    return records


# --- Contrat + DLQ ---------------------------------------------------------

def validate_records(records, schema_file):
    with open(os.path.join(SCHEMAS_DIR, schema_file), encoding="utf-8") as f:
        schema = json.load(f)
    validator = jsonschema.Draft7Validator(schema)
    accepted, rejected = [], []
    for r in records:
        errors = sorted(validator.iter_errors(r), key=str)
        if errors:
            rejected.append({"record": r, "erreur": errors[0].message})
        else:
            accepted.append(r)
    return accepted, rejected


def to_jsonl_bytes(records):
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in records).encode("utf-8")


def write_minio(client, bucket, flow_name, records):
    if not records:
        return
    for b in (bucket,):
        if not client.bucket_exists(b):
            client.make_bucket(b)
    data = to_jsonl_bytes(records)
    object_name = f"{flow_name}/{RUN_TS}.jsonl"
    client.put_object(bucket, object_name, io.BytesIO(data), length=len(data),
                       content_type="application/x-ndjson")


FLOWS = [
    ("crm/dim_client", lambda: read_mysql("SELECT * FROM dim_client"), "dim_client.schema.json", None),
    ("crm/dim_produit", lambda: read_mysql("SELECT * FROM dim_produit"), "dim_produit.schema.json", None),
    ("crm/fact_ventes_reel", lambda: read_mysql("SELECT * FROM fact_ventes_reel"), "fact_ventes_reel.schema.json", None),
    ("logs/app_events", read_mongo, "app_events.schema.json", None),
    ("finance/dim_centre_cout",
     lambda: read_finance_csv("dim_centre_cout.csv", ["centre_cout_id", "centre_parent_id"], []),
     "dim_centre_cout.schema.json", anonymize_centre_cout),
    ("finance/dim_compte", lambda: read_finance_csv("dim_compte.csv", ["compte_id"], []),
     "dim_compte.schema.json", None),
    ("finance/dim_version_budget", lambda: read_finance_csv("dim_version_budget.csv", ["version_id"], []),
     "dim_version_budget.schema.json", None),
    ("finance/fact_budget",
     lambda: read_finance_csv("fact_budget.csv", ["budget_id", "centre_cout_id", "compte_id", "version_id"], ["montant_budget"]),
     "fact_budget.schema.json", None),
    ("finance/fact_forecast",
     lambda: read_finance_csv("fact_forecast.csv", ["forecast_id", "centre_cout_id", "compte_id"], ["montant_forecast"]),
     "fact_forecast.schema.json", None),
    ("erp_legacy/vente_ligne_brute", read_erp_legacy_raw, "erp_vente_ligne.schema.json", None),
]


def main():
    client = Minio("localhost:9000",
                    access_key=os.getenv("MINIO_ROOT_USER", "minio_admin"),
                    secret_key=os.getenv("MINIO_ROOT_PASSWORD", "changeme123"),
                    secure=False)

    total_ok, total_ko = 0, 0
    for flow_name, reader, schema_file, anonymize in FLOWS:
        records = reader()
        if anonymize:
            records = anonymize(records)
        accepted, rejected = validate_records(records, schema_file)
        write_minio(client, "bronze", flow_name, accepted)
        write_minio(client, "rejects", flow_name, [
            {**r["record"], "_motif_rejet": r["erreur"]} for r in rejected])
        total_ok += len(accepted)
        total_ko += len(rejected)
        print(f"  {flow_name}: {len(accepted)} acceptés, {len(rejected)} rejetés"
              + (f" (ex: {rejected[0]['erreur']})" if rejected else ""))

    print(f"Total : {total_ok} acceptés -> bronze/, {total_ko} rejetés -> rejects/")


def demo():
    """Self-check minimal (dette technique #7) : vérifie qu'un flux propre
    (dim_client) a 0 rejet et que le flux ERP a bien ~2% de rejets attendus
    (dates invalides connues, cf. docs/REFONTE-ERP.md) — pas de dérive
    silencieuse d'un contrat."""
    for flow_name, reader, schema_file, anonymize in FLOWS:
        if flow_name not in ("crm/dim_client", "erp_legacy/vente_ligne_brute"):
            continue
        records = reader()
        if anonymize:
            records = anonymize(records)
        accepted, rejected = validate_records(records, schema_file)
        if flow_name == "crm/dim_client":
            assert len(rejected) == 0, f"dim_client devrait être 100% conforme, {len(rejected)} rejets"
        if flow_name == "erp_legacy/vente_ligne_brute":
            taux = len(rejected) / len(records)
            assert 0.01 < taux < 0.03, f"taux de rejet ERP inattendu : {taux:.1%} (attendu ~2%)"
    print("demo(): OK - dim_client 0 rejet, ERP legacy ~2% de rejets (dates invalides), invariants respectés")


if __name__ == "__main__":
    demo()
    main()
