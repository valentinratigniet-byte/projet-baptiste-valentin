"""Simule un export brut d'un ERP legacy (style AS/400 / vieux progiciel
comptable) : table plate, colonnes tronquées 8 caractères, CSV `;` en
latin-1, dates FR string, montants à virgule, codes incohérents, doublons
clients, centres de coût mal renseignés.

Ce fichier EST la dette qu'on va diagnostiquer et migrer (docs/REFONTE-ERP.md).
Ne pas "nettoyer" ce générateur : le désordre est le point.

Usage : .venv/Scripts/python.exe erp-legacy/generate_erp_legacy_export.py
"""
import csv
import os
import random
import unicodedata
from datetime import date, timedelta

import mysql.connector
from dotenv import load_dotenv
from faker import Faker

load_dotenv()
random.seed(7)
fake = Faker("fr_FR")
Faker.seed(7)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "exports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

N_LIGNES = 2500
DATE_DEBUT = date(2023, 1, 1)  # l'ERP existait avant le CRM (Sprint 1)
DATE_FIN = date(2024, 12, 31)

# Plan comptable legacy : mélange de codes PCG réels et d'un "compte poubelle"
# (classique dans un vieil ERP jamais nettoyé)
COMPTES_LEGACY = ["706100", "706200", "707000", "758000", "758000", "758000"]

# Centres de coûts : le même centre physique est codé de 3 façons différentes
# selon qui a saisi la fiche, + 15% de lignes non affectées
CDCC_VARIANTS = {
    "Ventes": ["CC01", "CC1", "01"],
    "Marketing": ["CC02", "CC2"],
    "Production": ["CC03", "CC3", "03"],
}


def deform_name(nom):
    """Produit une variante 'legacy' d'un nom de client réel (CRM)."""
    variantes = [
        lambda s: s.upper(),
        lambda s: s.replace("S.A.R.L.", "SARL").replace("S.A.", "SA"),
        lambda s: s + " " if random.random() < 0.3 else s,
        lambda s: unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode(),
        lambda s: s[:20],  # troncature champ legacy 20 caractères
        lambda s: s.replace(" ", "  "),  # double espace, saisie clavier
    ]
    n = nom
    for v in random.sample(variantes, k=random.randint(1, 2)):
        n = v(n)
    return n.strip()


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


def build_legacy_clients(clients_crm):
    """Construit le référentiel client legacy :
    - ~80 clients CRM avec 1 ou 2 variantes de saisie (le vrai problème MDM)
    - ~25 clients legacy-only (jamais repris dans le CRM)
    Retourne une liste de dicts {cdcli, rscli, client_crm_id (ou None)}."""
    legacy = []
    code = 1
    sample = random.sample(clients_crm, k=min(80, len(clients_crm)))
    for client_id, libelle in sample:
        n_variantes = random.choices([1, 2], weights=[70, 30])[0]
        for _ in range(n_variantes):
            legacy.append({
                "cdcli": f"{code:05d}" if random.random() < 0.6 else f"CLI{code}",
                "rscli": deform_name(libelle),
                "client_crm_id": client_id,
            })
            code += 1
    for _ in range(25):
        legacy.append({
            "cdcli": f"{code:05d}",
            "rscli": fake.company(),
            "client_crm_id": None,  # client legacy jamais migré vers le CRM
        })
        code += 1
    return legacy


def gen_lignes(legacy_clients):
    rows = []
    d = DATE_DEBUT
    pieces = 1
    while d <= DATE_FIN:
        for _ in range(random.randint(2, 6)):
            client = random.choice(legacy_clients)
            centre_libelle = random.choice(list(CDCC_VARIANTS) + [None])
            cdcc = random.choice(CDCC_VARIANTS[centre_libelle]) if centre_libelle else ""
            date_piece = d if random.random() > 0.02 else None  # 2% de dates cassées
            qte = random.randint(1, 15)
            pu = round(random.uniform(30, 800), 2)
            mtht = round(qte * pu, 2)
            mttva = round(mtht * 0.2, 2)
            mtttc = round(mtht + mttva, 2)
            rows.append({
                "CDSOC": "0001",
                "NUMPCE": f"V{pieces:06d}",
                "CDCLI": client["cdcli"],
                "RSCLI": client["rscli"],
                "CDCC": cdcc,
                "CDCPT": random.choice(COMPTES_LEGACY),
                "DTPCE": date_piece.strftime("%d/%m/%Y") if date_piece else "00/00/0000",
                "QTE": str(qte),
                "MTHT": f"{mtht:.2f}".replace(".", ","),
                "MTTVA": f"{mttva:.2f}".replace(".", ","),
                "MTTTC": f"{mtttc:.2f}".replace(".", ","),
                "FLGANO": random.choice(["0", "0", "0", "1", ""]),  # flag non documenté
            })
            pieces += 1
        d += timedelta(days=1)
        if len(rows) >= N_LIGNES:
            break
    return rows[:N_LIGNES]


def main():
    print("Lecture des clients CRM (pour créer les variantes legacy)...")
    clients_crm = get_clients_crm()
    legacy_clients = build_legacy_clients(clients_crm)
    print(f"  {len(legacy_clients)} codes client legacy "
          f"({sum(1 for c in legacy_clients if c['client_crm_id'] is None)} legacy-only)")

    print("Génération des lignes de vente ERP...")
    rows = gen_lignes(legacy_clients)

    out_path = os.path.join(OUTPUT_DIR, "ERP_EXPORT_VTE_2023_2024.csv")
    with open(out_path, "w", newline="", encoding="latin-1") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {len(rows)} lignes -> {out_path} (latin-1, ';', décimales virgule)")

    # Référentiel client legacy, pour la réconciliation (Sprint 2)
    ref_path = os.path.join(OUTPUT_DIR, "REF_CLIENT_LEGACY.csv")
    with open(ref_path, "w", newline="", encoding="latin-1") as f:
        writer = csv.DictWriter(f, fieldnames=["cdcli", "rscli", "client_crm_id"], delimiter=";")
        writer.writeheader()
        writer.writerows(legacy_clients)
    print(f"  référentiel client -> {ref_path}")


if __name__ == "__main__":
    main()
