"""Génère les données de contrôle de gestion (dimensions + Réel/Budget/Forecast)
et les distribue vers leurs sources simulées :
  - MySQL (CRM)   : DIM_CLIENT, DIM_PRODUIT, FACT_VENTES_REEL
  - CSV (Finance) : DIM_CENTRE_COUT, DIM_COMPTE, DIM_VERSION_BUDGET,
                     FACT_BUDGET, FACT_FORECAST
    (simule un export ERP/Finance -> ira en Bronze via les data contracts, Sprint 2)

Usage : .venv/Scripts/python.exe data-generation/generate_cg_data.py
"""
import os
import random
from datetime import date, timedelta

import mysql.connector
import pandas as pd
from dotenv import load_dotenv
from faker import Faker

load_dotenv()
random.seed(42)
fake = Faker("fr_FR")
Faker.seed(42)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

N_CENTRES = 15
N_COMPTES = 40
N_PRODUITS = 200
N_CLIENTS = 500
MOIS_BUDGET = pd.date_range("2025-01-01", "2026-12-01", freq="MS")  # 2 ans
DATE_DEBUT_VENTES = date(2025, 1, 1)
DATE_FIN_VENTES = date(2026, 8, 20)  # "aujourd'hui" dans ce portfolio


def gen_dim_centre_cout():
    services = ["Ventes", "Marketing", "Production", "Logistique", "R&D", "SI",
                "RH", "Finance", "Support client", "Achats", "Qualité",
                "Direction régionale Nord", "Direction régionale Sud",
                "Usine A", "Usine B"]
    rows = []
    for i, libelle in enumerate(services[:N_CENTRES], start=1):
        rows.append({
            "centre_cout_id": i,
            "code": f"CC{i:03d}",
            "libelle": libelle,
            "responsable": fake.name(),
            "centre_parent_id": None,
        })
    return pd.DataFrame(rows)


def gen_dim_compte():
    charges = ["Salaires", "Loyers", "Achats matières", "Sous-traitance",
               "Marketing digital", "Déplacements", "Énergie", "Maintenance",
               "Logiciels/licences", "Formation", "Assurances", "Transport",
               "Fournitures", "Honoraires", "Communication"]
    produits = ["Ventes produits", "Ventes services", "Prestations annexes"]
    rows = []
    cid = 1
    for lib in charges + produits:
        nature = "produit" if lib in produits else "charge"
        rows.append({"compte_id": cid, "code_compte": f"6{cid:03d}" if nature == "charge" else f"7{cid:03d}",
                     "libelle": lib, "nature": nature})
        cid += 1
    while cid <= N_COMPTES:
        rows.append({"compte_id": cid, "code_compte": f"6{cid:03d}",
                     "libelle": f"Charge diverse {cid}", "nature": "charge"})
        cid += 1
    return pd.DataFrame(rows)


def gen_dim_produit():
    familles = ["Électronique", "Mobilier", "Textile", "Alimentaire", "Cosmétique"]
    rows = [{"produit_id": i, "code": f"PRD{i:04d}",
             "libelle": fake.word().capitalize() + " " + fake.word(),
             "famille": random.choice(familles)} for i in range(1, N_PRODUITS + 1)]
    return pd.DataFrame(rows)


def gen_dim_client():
    segments = ["Grand compte", "PME", "Particulier", "Revendeur"]
    rows = [{"client_id": i, "code": f"CLI{i:05d}", "libelle": fake.company(),
             "segment": random.choice(segments)} for i in range(1, N_CLIENTS + 1)]
    return pd.DataFrame(rows)


def gen_dim_version_budget():
    return pd.DataFrame([
        {"version_id": 1, "libelle": "Budget initial 2025", "date_validation": "2024-12-15"},
        {"version_id": 2, "libelle": "Budget initial 2026", "date_validation": "2025-12-15"},
    ])


VENTES_CENTRES_LIBELLES = ["Ventes", "Direction régionale Nord", "Direction régionale Sud"]


def gen_fact_ventes_reel(dim_produit, dim_client, dim_centre_cout, dim_compte):
    ventes_centres = dim_centre_cout[dim_centre_cout["libelle"].isin(
        VENTES_CENTRES_LIBELLES)]["centre_cout_id"].tolist()
    compte_ventes_id = int(dim_compte[dim_compte["libelle"] == "Ventes produits"]["compte_id"].iloc[0])
    rows = []
    vid = 1
    d = DATE_DEBUT_VENTES
    while d <= DATE_FIN_VENTES:
        for _ in range(random.randint(3, 12)):  # volume de ventes/jour
            rows.append({
                "vente_id": vid,
                "date": d.isoformat(),
                "centre_cout_id": random.choice(ventes_centres),
                "compte_id": compte_ventes_id,
                "produit_id": random.randint(1, N_PRODUITS),
                "client_id": random.randint(1, N_CLIENTS),
                "montant_reel": round(random.uniform(50, 5000), 2),
                "quantite": random.randint(1, 20),
            })
            vid += 1
        d += timedelta(days=1)
    return pd.DataFrame(rows)


def gen_fact_budget(dim_centre_cout, dim_compte):
    """Budgète les charges (comme avant) ET le chiffre d'affaires des
    centres commerciaux (compte "Ventes produits") — sans ça, fct_ventes_reel
    (100% revenu) et fact_budget (100% charges à l'origine) ne partageaient
    jamais le même compte, rendant tout calcul d'écart Réel/Budget vide par
    construction. Root cause corrigée ici plutôt que contournée en aval."""
    charge_comptes = dim_compte[dim_compte["nature"] == "charge"]["compte_id"].tolist()
    compte_ventes_id = int(dim_compte[dim_compte["libelle"] == "Ventes produits"]["compte_id"].iloc[0])
    ventes_centres_ids = set(dim_centre_cout[dim_centre_cout["libelle"].isin(
        VENTES_CENTRES_LIBELLES)]["centre_cout_id"].tolist())

    rows = []
    bid = 1
    for _, centre in dim_centre_cout.iterrows():
        comptes_du_centre = random.sample(charge_comptes, k=min(6, len(charge_comptes)))
        bases = {compte_id: round(random.uniform(2000, 40000), 2) for compte_id in comptes_du_centre}
        if centre["centre_cout_id"] in ventes_centres_ids:
            bases[compte_ventes_id] = round(random.uniform(120000, 220000), 2)
        for compte_id, base in bases.items():
            for periode in MOIS_BUDGET:
                version_id = 1 if periode.year == 2025 else 2
                saisonnalite = 1 + 0.1 * (periode.month % 4 - 1.5) / 1.5
                rows.append({
                    "budget_id": bid,
                    "periode": periode.date().isoformat(),
                    "centre_cout_id": centre["centre_cout_id"],
                    "compte_id": compte_id,
                    "version_id": version_id,
                    "montant_budget": round(base * saisonnalite, 2),
                })
                bid += 1
    return pd.DataFrame(rows)


def gen_fact_forecast(fact_budget):
    """Prévisions glissantes : pour chaque (centre, compte), 3 révisions récentes
    qui projettent les 6 prochains mois autour du budget avec un bruit +/-15%."""
    rows = []
    fid = 1
    combos = fact_budget[["centre_cout_id", "compte_id"]].drop_duplicates()
    revisions = ["2026-06-01", "2026-07-01", "2026-08-01"]
    for _, combo in combos.iterrows():
        base_budget = fact_budget[
            (fact_budget["centre_cout_id"] == combo["centre_cout_id"])
            & (fact_budget["compte_id"] == combo["compte_id"])
        ]["montant_budget"].mean()
        for rev in revisions:
            rev_date = date.fromisoformat(rev)
            for m in range(1, 7):
                cible = (rev_date.replace(day=1) + pd.DateOffset(months=m)).date()
                rows.append({
                    "forecast_id": fid,
                    "periode_cible": cible.isoformat(),
                    "date_revision": rev,
                    "centre_cout_id": combo["centre_cout_id"],
                    "compte_id": combo["compte_id"],
                    "montant_forecast": round(base_budget * random.uniform(0.85, 1.15), 2),
                })
                fid += 1
    return pd.DataFrame(rows)


def load_to_mysql(dim_produit, dim_client, fact_ventes_reel):
    conn = mysql.connector.connect(
        host="127.0.0.1", port=3306,
        user=os.getenv("MYSQL_USER", "crm_user"),
        password=os.getenv("MYSQL_PASSWORD", "changeme"),
        database="crm",
    )
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS dim_produit (
        produit_id INT PRIMARY KEY, code VARCHAR(20), libelle VARCHAR(200), famille VARCHAR(50))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS dim_client (
        client_id INT PRIMARY KEY, code VARCHAR(20), libelle VARCHAR(200), segment VARCHAR(50))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS fact_ventes_reel (
        vente_id INT PRIMARY KEY, date DATE, centre_cout_id INT, compte_id INT,
        produit_id INT, client_id INT, montant_reel DECIMAL(12,2), quantite INT)""")

    for table, df, cols in [
        ("dim_produit", dim_produit, ["produit_id", "code", "libelle", "famille"]),
        ("dim_client", dim_client, ["client_id", "code", "libelle", "segment"]),
        ("fact_ventes_reel", fact_ventes_reel,
         ["vente_id", "date", "centre_cout_id", "compte_id", "produit_id",
          "client_id", "montant_reel", "quantite"]),
    ]:
        cur.execute(f"TRUNCATE TABLE {table}")
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        cur.executemany(sql, df[cols].values.tolist())
        print(f"  MySQL <- {table}: {len(df)} lignes")

    conn.commit()
    cur.close()
    conn.close()


def main():
    random.seed(42)
    Faker.seed(42)
    print("Génération des dimensions...")
    dim_centre_cout = gen_dim_centre_cout()
    dim_compte = gen_dim_compte()
    dim_produit = gen_dim_produit()
    dim_client = gen_dim_client()
    dim_version_budget = gen_dim_version_budget()

    print("Génération du Réel...")
    fact_ventes_reel = gen_fact_ventes_reel(dim_produit, dim_client, dim_centre_cout, dim_compte)

    print("Génération du Budget...")
    fact_budget = gen_fact_budget(dim_centre_cout, dim_compte)

    print("Génération du Forecast...")
    fact_forecast = gen_fact_forecast(fact_budget)

    print("Écriture des exports Finance (CSV -> futur Bronze)...")
    dim_centre_cout.to_csv(f"{OUTPUT_DIR}/dim_centre_cout.csv", index=False)
    dim_compte.to_csv(f"{OUTPUT_DIR}/dim_compte.csv", index=False)
    dim_version_budget.to_csv(f"{OUTPUT_DIR}/dim_version_budget.csv", index=False)
    fact_budget.to_csv(f"{OUTPUT_DIR}/fact_budget.csv", index=False)
    fact_forecast.to_csv(f"{OUTPUT_DIR}/fact_forecast.csv", index=False)
    print(f"  {len(fact_budget)} lignes budget, {len(fact_forecast)} lignes forecast -> {OUTPUT_DIR}/")

    print("Chargement CRM (MySQL)...")
    load_to_mysql(dim_produit, dim_client, fact_ventes_reel)

    print("Terminé.")


def demo():
    """Self-check minimal (dette technique #2) : rejoue la génération pure
    (pas de DB/IO) et vérifie les invariants de base. `assert` volontaire :
    doit planter bruyamment si un futur refactor casse une borne d'ID ou une
    jointure, comme l'a fait silencieusement le bug d'ID de compte hardcodé.

    Re-seed en entrée : demo() consomme des tirages aléatoires, donc sans
    ça main() ne regénèrerait plus les mêmes données selon qu'il est appelé
    seul ou après demo() (bug réel rencontré en développant ce self-check)."""
    random.seed(42)
    Faker.seed(42)
    dim_centre_cout = gen_dim_centre_cout()
    dim_compte = gen_dim_compte()
    dim_produit = gen_dim_produit()
    dim_client = gen_dim_client()
    fact_ventes_reel = gen_fact_ventes_reel(dim_produit, dim_client, dim_centre_cout, dim_compte)
    fact_budget = gen_fact_budget(dim_centre_cout, dim_compte)
    fact_forecast = gen_fact_forecast(fact_budget)

    assert len(dim_centre_cout) == N_CENTRES
    assert len(dim_compte) == N_COMPTES
    assert len(dim_produit) == N_PRODUITS
    assert len(dim_client) == N_CLIENTS
    assert fact_ventes_reel["montant_reel"].min() > 0
    assert fact_ventes_reel["produit_id"].between(1, N_PRODUITS).all()
    assert fact_ventes_reel["client_id"].between(1, N_CLIENTS).all()
    assert fact_ventes_reel["compte_id"].isin(dim_compte["compte_id"]).all()
    assert fact_budget["montant_budget"].min() > 0
    assert fact_budget["centre_cout_id"].isin(dim_centre_cout["centre_cout_id"]).all()
    assert fact_forecast["montant_forecast"].min() > 0
    assert not fact_ventes_reel.isnull().any().any()
    comptes_communs = set(fact_ventes_reel["compte_id"]) & set(fact_budget["compte_id"])
    assert comptes_communs, "Réel et Budget doivent partager au moins un compte (sinon écart toujours vide)"
    print("demo(): OK -", len(fact_ventes_reel), "ventes,", len(fact_budget),
          "budget,", len(fact_forecast), "forecast, tous invariants respectés")


if __name__ == "__main__":
    demo()
    main()
