"""Applique la gouvernance BigQuery sur `marts.fct_ecarts_reel_budget` :
- Row-Level Security : seuls Finance/Direction/PDG voient des lignes (RH
  n'a pas vocation à voir le détail des marges par centre de coût — s'il
  n'existe aucune ROW ACCESS POLICY qui le nomme, BigQuery refuse par
  défaut, pas besoin de policy de blocage explicite pour RH).
- Column-Level Security (Policy Tags) : les colonnes montant_reel/
  montant_budget/ecart sont masquées pour qui n'a pas le rôle
  datacatalog.categoryFineGrainedReader sur le tag "CG_Confidentiel" -
  défense en profondeur, indépendante de la RLS.

Prérequis : governance/sync_marts_to_bigquery.py déjà exécuté.
Usage : .venv/Scripts/python.exe governance/apply_rls_and_masking.py
"""
import os

from dotenv import load_dotenv
from google.cloud import bigquery, datacatalog_v1
from google.oauth2 import service_account

load_dotenv()
if os.getenv("GRPC_CA_BUNDLE"):
    # gRPC (client Data Catalog) a sa propre pile SSL, indépendante de
    # pip-system-certs - doit être positionné avant toute création de canal.
    os.environ.setdefault("GRPC_DEFAULT_SSL_ROOTS_FILE_PATH", os.environ["GRPC_CA_BUNDLE"])

BQ_PROJECT = os.getenv("BQ_PROJECT", "bv-dataplatform")
# Data Catalog veut la region en minuscules ("eu"), contrairement a la
# multi-region BigQuery ("EU") utilisee pour les datasets - deux conventions
# differentes pour la meme region, trouve en testant.
LOCATION = "eu"
PROFILS_AUTORISES = ["finance-viewer", "direction-viewer", "pdg-viewer"]  # pas rh-viewer


def get_credentials():
    return service_account.Credentials.from_service_account_file(os.environ["BQ_KEYFILE"])


def apply_row_access_policy(client):
    membres = ", ".join(f"'serviceAccount:{p}@{BQ_PROJECT}.iam.gserviceaccount.com'"
                         for p in PROFILS_AUTORISES)
    sql = f"""
    CREATE OR REPLACE ROW ACCESS POLICY finance_direction_pdg_acces_complet
    ON `{BQ_PROJECT}.marts.fct_ecarts_reel_budget`
    GRANT TO ({membres})
    FILTER USING (true)
    """
    client.query(sql).result()
    print("  Row access policy creee : Finance/Direction/PDG voient toutes les lignes, "
          "RH n'en voit aucune (aucune policy ne le nomme).")


def get_or_create_taxonomy(dc_client):
    parent = f"projects/{BQ_PROJECT}/locations/{LOCATION}"
    for t in dc_client.list_taxonomies(parent=parent):
        if t.display_name == "CG":
            return t
    return dc_client.create_taxonomy(
        parent=parent,
        taxonomy=datacatalog_v1.Taxonomy(
            display_name="CG",
            description="Classification donnees Controle de Gestion",
            activated_policy_types=[
                datacatalog_v1.Taxonomy.PolicyType.FINE_GRAINED_ACCESS_CONTROL],
        ),
    )


def get_or_create_policy_tag(dc_client, taxonomy):
    for t in dc_client.list_policy_tags(parent=taxonomy.name):
        if t.display_name == "Confidentiel":
            return t
    return dc_client.create_policy_tag(
        parent=taxonomy.name,
        policy_tag=datacatalog_v1.PolicyTag(
            display_name="Confidentiel",
            description="Montants Reel/Budget/Ecart - Finance/Direction/PDG uniquement",
        ),
    )


def apply_policy_tags(bq_client, dc_client):
    """Crée la taxonomie + le tag si absents (idempotent), l'applique aux 3
    colonnes sensibles, autorise Finance/Direction/PDG à les lire en clair."""
    taxonomy = get_or_create_taxonomy(dc_client)
    print(f"  Taxonomie : {taxonomy.name}")
    tag = get_or_create_policy_tag(dc_client, taxonomy)
    print(f"  Policy tag : {tag.name}")

    table_ref = bq_client.dataset("marts").table("fct_ecarts_reel_budget")
    table = bq_client.get_table(table_ref)
    sensibles = {"montant_reel", "montant_budget", "ecart"}
    nouveau_schema = []
    for field in table.schema:
        if field.name in sensibles:
            field = field.to_api_repr()
            field["policyTags"] = {"names": [tag.name]}
            field = bigquery.SchemaField.from_api_repr(field)
        nouveau_schema.append(field)
    table.schema = nouveau_schema
    bq_client.update_table(table, ["schema"])
    print("  Policy tag applique a montant_reel, montant_budget, ecart")

    for profil in PROFILS_AUTORISES:
        policy = dc_client.get_iam_policy(request={"resource": tag.name})
        policy.bindings.add(
            role="roles/datacatalog.categoryFineGrainedReader",
            members=[f"serviceAccount:{profil}@{BQ_PROJECT}.iam.gserviceaccount.com"],
        )
        dc_client.set_iam_policy(request={"resource": tag.name, "policy": policy})
    print(f"  Lecture fine accordee a : {', '.join(PROFILS_AUTORISES)} (pas rh-viewer)")


def main():
    creds = get_credentials()
    bq_client = bigquery.Client(project=BQ_PROJECT, credentials=creds)
    dc_client = datacatalog_v1.PolicyTagManagerClient(credentials=creds)

    print("Row-Level Security...")
    apply_row_access_policy(bq_client)
    print("Column-Level Security (Policy Tags)...")
    apply_policy_tags(bq_client, dc_client)
    print("Termine. Verifier avec governance/test_acces_par_profil.py")


if __name__ == "__main__":
    main()
