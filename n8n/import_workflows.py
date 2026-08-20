"""Importe les workflows versionnés (n8n/workflows/*.json) dans une instance
n8n fraîche : recrée les credentials (Postgres dbt-dev, MinIO Bronze) à
partir de .env, réécrit les références de credentials dans chaque workflow
avec les nouveaux IDs (propres à chaque instance n8n), puis crée et active
chaque workflow.

Résout la dette technique #1 (workflows créés à la main, jamais versionnés).

Prérequis : le compte owner n8n doit déjà exister (voir docs/ARCHITECTURE.md
/rest/owner/setup) et la stack Docker doit tourner.

Usage : .venv/Scripts/python.exe n8n/import_workflows.py
"""
import http.cookiejar
import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:5678"
WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), "workflows")

CREDENTIALS = [
    {
        "name": "Postgres dbt-dev",
        "type": "postgres",
        "data": {
            "host": "postgres",
            "port": 5432,
            "database": os.getenv("POSTGRES_DB", "dbt_dev"),
            "user": os.getenv("POSTGRES_USER", "dbt_user"),
            "password": os.getenv("POSTGRES_PASSWORD", "changeme"),
            "maxConnections": 100,
            "ssl": "disable",
        },
    },
    {
        "name": "MinIO Bronze",
        "type": "s3",
        "data": {
            "endpoint": "http://minio:9000",
            "region": "us-east-1",
            "accessKeyId": os.getenv("MINIO_ROOT_USER", "minio_admin"),
            "secretAccessKey": os.getenv("MINIO_ROOT_PASSWORD", "changeme123"),
            "forcePathStyle": True,
            "ignoreSSLIssues": True,
        },
    },
]


def make_session():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def call(opener, method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    with opener.open(req) as resp:
        return json.loads(resp.read())


def login(opener):
    call(opener, "POST", "/rest/login", {
        "emailOrLdapLoginId": os.getenv("N8N_ADMIN_EMAIL", "admin@bv-dataplatform.local"),
        "password": os.getenv("N8N_ADMIN_PASSWORD"),
    })


def ensure_credentials(opener):
    """Retourne {(type, name): id}. Recrée seulement si absent (idempotent)."""
    existing = call(opener, "GET", "/rest/credentials")["data"]
    by_key = {(c["type"], c["name"]): c["id"] for c in existing}
    ids = {}
    for cred in CREDENTIALS:
        key = (cred["type"], cred["name"])
        if key in by_key:
            ids[key] = by_key[key]
            print(f"  credential deja presente : {cred['name']}")
            continue
        created = call(opener, "POST", "/rest/credentials", cred)["data"]
        ids[key] = created["id"]
        print(f"  credential creee : {cred['name']} -> {created['id']}")
    return ids


def remap_credentials(nodes, cred_ids):
    for node in nodes:
        for cred_type, ref in node.get("credentials", {}).items():
            key = (cred_type, ref["name"])
            if key in cred_ids:
                ref["id"] = cred_ids[key]


def import_workflow(opener, filepath, cred_ids):
    with open(filepath, encoding="utf-8") as f:
        wf = json.load(f)
    remap_credentials(wf["nodes"], cred_ids)
    wf["active"] = False

    created = call(opener, "POST", "/rest/workflows", wf)["data"]
    wf_id, version_id = created["id"], created["versionId"]

    has_webhook = any(n["type"] == "n8n-nodes-base.webhook" for n in wf["nodes"])
    if has_webhook:
        call(opener, "POST", f"/rest/workflows/{wf_id}/activate", {"versionId": version_id})
        status = "importe + active"
    else:
        status = "importe (pas de webhook a activer)"
    print(f"  {wf['name']} -> {wf_id} ({status})")


def main():
    opener = make_session()
    print("Connexion a n8n...")
    login(opener)

    print("Credentials...")
    cred_ids = ensure_credentials(opener)

    print("Workflows...")
    for filename in sorted(os.listdir(WORKFLOWS_DIR)):
        if filename.endswith(".json"):
            import_workflow(opener, os.path.join(WORKFLOWS_DIR, filename), cred_ids)

    print("Termine.")


if __name__ == "__main__":
    main()
