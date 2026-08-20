"""Preuve par la requête, pas par la doc : interroge `fct_ecarts_reel_budget`
avec les 4 comptes de service (RH/Finance/Direction/PDG) et compare les
résultats réels — deux requêtes séparées pour prouver les deux mécanismes
indépendamment :
1. Colonnes non sensibles (periode, centre_cout_id, compte_id, ecart_pct)
   -> teste la Row-Level Security seule
2. Colonnes sensibles (montant_reel) -> teste le masking de colonne
   (Policy Tag) en plus de la RLS

Usage : .venv/Scripts/python.exe governance/test_acces_par_profil.py
"""
import os

from dotenv import load_dotenv
from google.api_core.exceptions import Forbidden
from google.cloud import bigquery, datacatalog_v1
from google.oauth2 import service_account

load_dotenv()
if os.getenv("GRPC_CA_BUNDLE"):
    os.environ.setdefault("GRPC_DEFAULT_SSL_ROOTS_FILE_PATH", os.environ["GRPC_CA_BUNDLE"])

BQ_PROJECT = os.getenv("BQ_PROJECT", "bv-dataplatform")
KEYS_DIR = os.path.join(os.path.expanduser("~"), ".gcp", "bv-viewers")
PROFILS = ["rh-viewer", "finance-viewer", "direction-viewer", "pdg-viewer"]


def client_for(profil):
    keyfile = os.path.join(KEYS_DIR, f"{profil}.json")
    creds = service_account.Credentials.from_service_account_file(keyfile)
    return bigquery.Client(project=BQ_PROJECT, credentials=creds)


def compter_lignes_visibles(client):
    """Colonnes non sensibles uniquement -> teste la RLS seule."""
    try:
        r = list(client.query(
            "SELECT COUNT(*) AS n FROM `marts.fct_ecarts_reel_budget`"
        ).result())[0]
        return r.n
    except Forbidden:
        return "REFUSE (RLS)"


def lire_montant_total(client):
    """Colonne sensible -> teste le masking en plus de la RLS."""
    try:
        r = list(client.query(
            "SELECT SUM(montant_reel) AS total FROM `marts.fct_ecarts_reel_budget`"
        ).result())[0]
        return r.total
    except Forbidden:
        return "REFUSE (policy tag)"


def check_policy_tag_bindings():
    creds = service_account.Credentials.from_service_account_file(
        os.environ["BQ_KEYFILE"])
    dc_client = datacatalog_v1.PolicyTagManagerClient(credentials=creds)
    for taxo in dc_client.list_taxonomies(
            parent=f"projects/{BQ_PROJECT}/locations/eu"):
        if taxo.display_name != "CG":
            continue
        for tag in dc_client.list_policy_tags(parent=taxo.name):
            if tag.display_name != "Confidentiel":
                continue
            policy = dc_client.get_iam_policy(request={"resource": tag.name})
            return sorted(m for b in policy.bindings for m in b.members)
    return []


def main():
    print(f"{'profil':20s} {'lignes (RLS)':15s} {'SUM montant_reel (masking)'}")
    for profil in PROFILS:
        client = client_for(profil)
        n = compter_lignes_visibles(client)
        total = lire_montant_total(client)
        print(f"{profil:20s} {str(n):15s} {total}")

    print()
    print("IAM bindings du policy tag (defense en profondeur) :")
    membres = check_policy_tag_bindings()
    for m in membres:
        print(f"  - {m}")
    assert not any("rh-viewer" in m for m in membres), \
        "rh-viewer ne doit JAMAIS avoir accès aux colonnes sensibles"
    print("OK : rh-viewer absent des lecteurs autorisés du policy tag")


if __name__ == "__main__":
    main()
