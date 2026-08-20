"""Migration Sprint 2 : ERP legacy -> cible.

Lit l'export legacy brut (erp-legacy/exports/), le nettoie, réconcilie les
clients dupliqués/mal orthographiés par fuzzy matching contre le CRM (comme
le Projet 12 du portfolio solo : rapidfuzz + évaluation précision/rappel
contre une vérité terrain), mappe les centres de coût via une table de
correspondance explicite, et charge le résultat dans Postgres
(`erp_migre`, cible dbt-dev) avec un flag qualité par ligne — préfigure les
data contracts du Sprint 3.

Usage : .venv/Scripts/python.exe erp-legacy/migrate_erp_to_target.py
"""
import csv
import os
import unicodedata
from datetime import datetime

import mysql.connector
import psycopg2
from dotenv import load_dotenv
from rapidfuzz import fuzz, process

load_dotenv()

EXPORT_DIR = os.path.join(os.path.dirname(__file__), "exports")
SEUIL_MATCH = 85  # score rapidfuzz minimum pour accepter un rapprochement

# Table de correspondance centre de coût : construite à la main en lisant
# l'export (dette #du diagnostic) -> exactement le genre de livrable qu'une
# vraie mission de refonte ERP produit.
MAPPING_CDCC = {
    "CC01": "Ventes", "CC1": "Ventes", "01": "Ventes",
    "CC02": "Marketing", "CC2": "Marketing",
    "CC03": "Production", "CC3": "Production", "03": "Production",
    "": "Non affecté",
}


def normalize(nom):
    n = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    n = n.upper().replace(".", "")
    for suffixe in [" SARL", " SAS", " SA", " ET FILS", " EURL"]:
        n = n.replace(suffixe, "")
    return " ".join(n.split())  # collapse whitespace


def get_clients_crm():
    conn = mysql.connector.connect(
        host="127.0.0.1", port=3306,
        user=os.getenv("MYSQL_USER", "crm_user"),
        password=os.getenv("MYSQL_PASSWORD", "changeme"),
        database="crm",
    )
    cur = conn.cursor()
    cur.execute("SELECT client_id, libelle FROM dim_client")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def reconcile_clients(clients_crm):
    """Fuzzy-match chaque client legacy contre le référentiel CRM.
    Retourne un dict cdcli -> (client_crm_id_propose, score) et la liste
    brute pour l'éval précision/rappel."""
    choices = {client_id: normalize(libelle) for client_id, libelle in clients_crm}
    choices_inv = {v: k for k, v in choices.items()}  # collisions improbables sur ce volume

    resultats = {}
    verite_terrain = []
    with open(os.path.join(EXPORT_DIR, "REF_CLIENT_LEGACY.csv"), encoding="latin-1") as f:
        for row in csv.DictReader(f, delimiter=";"):
            nom_norm = normalize(row["rscli"])
            match = process.extractOne(nom_norm, choices_inv.keys(), scorer=fuzz.WRatio)
            propose_id, score = None, 0
            if match:
                matched_name, score, _ = match
                if score >= SEUIL_MATCH:
                    propose_id = choices_inv[matched_name]
            resultats[row["cdcli"]] = (propose_id, score)
            verite_terrain.append((
                row["cdcli"],
                int(row["client_crm_id"]) if row["client_crm_id"] else None,
                propose_id,
            ))
    return resultats, verite_terrain


def evaluer_matching(verite_terrain):
    vp = sum(1 for _, vrai, propose in verite_terrain if vrai is not None and vrai == propose)
    fp = sum(1 for _, vrai, propose in verite_terrain
             if propose is not None and vrai != propose)
    fn = sum(1 for _, vrai, propose in verite_terrain if vrai is not None and propose is None)
    precision = vp / (vp + fp) if (vp + fp) else 0
    rappel = vp / (vp + fn) if (vp + fn) else 0
    f1 = 2 * precision * rappel / (precision + rappel) if (precision + rappel) else 0
    print(f"  Réconciliation client : précision={precision:.1%} rappel={rappel:.1%} F1={f1:.1%} "
          f"(VP={vp} FP={fp} FN={fn})")
    return precision, rappel, f1


def parse_montant(s):
    return float(s.replace(",", ".")) if s else None


def parse_date(s):
    if not s or s == "00/00/0000":
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def clean_lignes(reconciliation):
    lignes = []
    with open(os.path.join(EXPORT_DIR, "ERP_EXPORT_VTE_2023_2024.csv"), encoding="latin-1") as f:
        for row in csv.DictReader(f, delimiter=";"):
            client_crm_id, score = reconciliation.get(row["CDCLI"], (None, 0))
            date_piece = parse_date(row["DTPCE"])
            centre = MAPPING_CDCC.get(row["CDCC"].strip())
            motifs = []
            if date_piece is None:
                motifs.append("date_invalide")
            if centre is None:
                motifs.append("centre_cout_inconnu")
            lignes.append({
                "numpce": row["NUMPCE"],
                "cdcli": row["CDCLI"],
                "client_crm_id_propose": client_crm_id,
                "score_matching": round(score, 1),
                "centre_cout_libelle": centre,
                "compte_code": row["CDCPT"],
                "date_piece": date_piece,
                "montant_ht": parse_montant(row["MTHT"]),
                "montant_tva": parse_montant(row["MTTVA"]),
                "montant_ttc": parse_montant(row["MTTTC"]),
                "ligne_valide": len(motifs) == 0,
                "motif_rejet": ",".join(motifs) or None,
            })
    return lignes


def load_to_postgres(lignes, verite_terrain):
    conn = psycopg2.connect(
        host="127.0.0.1", port=5434,
        dbname=os.getenv("POSTGRES_DB", "dbt_dev"),
        user=os.getenv("POSTGRES_USER", "dbt_user"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS erp_migre")
    cur.execute("""CREATE TABLE IF NOT EXISTS erp_migre.client_reconciliation (
        cdcli VARCHAR(20) PRIMARY KEY, client_crm_id_verite INT,
        client_crm_id_propose INT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS erp_migre.fact_ventes_erp_migre (
        numpce VARCHAR(20) PRIMARY KEY, cdcli VARCHAR(20),
        client_crm_id_propose INT, score_matching NUMERIC,
        centre_cout_libelle VARCHAR(50), compte_code VARCHAR(10),
        date_piece DATE, montant_ht NUMERIC, montant_tva NUMERIC,
        montant_ttc NUMERIC, ligne_valide BOOLEAN, motif_rejet VARCHAR(100))""")

    cur.execute("TRUNCATE erp_migre.client_reconciliation, erp_migre.fact_ventes_erp_migre")
    cur.executemany(
        "INSERT INTO erp_migre.client_reconciliation VALUES (%s, %s, %s)",
        verite_terrain)
    cur.executemany(
        """INSERT INTO erp_migre.fact_ventes_erp_migre VALUES
        (%(numpce)s, %(cdcli)s, %(client_crm_id_propose)s, %(score_matching)s,
         %(centre_cout_libelle)s, %(compte_code)s, %(date_piece)s,
         %(montant_ht)s, %(montant_tva)s, %(montant_ttc)s,
         %(ligne_valide)s, %(motif_rejet)s)""",
        lignes)
    conn.commit()

    cur.execute("SELECT ligne_valide, count(*) FROM erp_migre.fact_ventes_erp_migre GROUP BY 1")
    for valide, n in cur.fetchall():
        print(f"  Postgres <- fact_ventes_erp_migre: {n} lignes ({'valides' if valide else 'à corriger'})")
    cur.close()
    conn.close()


def main():
    print("Réconciliation clients (fuzzy match legacy -> CRM)...")
    clients_crm = get_clients_crm()
    reconciliation, verite_terrain = reconcile_clients(clients_crm)
    evaluer_matching(verite_terrain)

    print("Nettoyage des lignes de vente...")
    lignes = clean_lignes(reconciliation)
    n_invalides = sum(1 for l in lignes if not l["ligne_valide"])
    print(f"  {len(lignes)} lignes ({n_invalides} à corriger, "
          f"{n_invalides / len(lignes):.1%})")

    print("Chargement Postgres (schéma erp_migre)...")
    load_to_postgres(lignes, verite_terrain)
    print("Terminé.")


if __name__ == "__main__":
    main()
