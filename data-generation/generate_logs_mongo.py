"""Génère des logs applicatifs (événements utilisateur) dans MongoDB, en
cohérence avec les clients/produits déjà chargés en MySQL par
generate_cg_data.py (mêmes plages d'ID, seed identique).

Usage : .venv/Scripts/python.exe data-generation/generate_logs_mongo.py
"""
import os
import random
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from faker import Faker
from pymongo import MongoClient

load_dotenv()
random.seed(42)
fake = Faker("fr_FR")
Faker.seed(42)

N_CLIENTS = 500
N_PRODUITS = 200
DATE_DEBUT = date(2025, 1, 1)
DATE_FIN = date(2026, 8, 20)

EVENT_TYPES = ["login", "view_product", "add_to_cart", "purchase_attempt",
               "purchase_success", "error"]
EVENT_WEIGHTS = [20, 35, 15, 10, 8, 12]
NIVEAUX = {"error": "error", "purchase_attempt": "warning"}


def gen_logs():
    rows = []
    d = DATE_DEBUT
    while d <= DATE_FIN:
        for _ in range(random.randint(20, 60)):  # volume de logs/jour
            event = random.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0]
            ts = datetime.combine(d, datetime.min.time()) + timedelta(
                seconds=random.randint(0, 86399))
            doc = {
                "timestamp": ts,
                "event_type": event,
                "niveau": NIVEAUX.get(event, "info"),
                "client_id": random.randint(1, N_CLIENTS),
                "session_id": fake.uuid4(),
                "user_agent": fake.user_agent(),
            }
            if event in ("view_product", "add_to_cart", "purchase_attempt", "purchase_success"):
                doc["produit_id"] = random.randint(1, N_PRODUITS)
            if event == "error":
                doc["message"] = random.choice([
                    "Timeout API paiement", "Stock insuffisant",
                    "Session expirée", "Erreur validation formulaire",
                ])
            rows.append(doc)
        d += timedelta(days=1)
    return rows


def load_to_mongo(docs):
    uri = (f"mongodb://{os.getenv('MONGO_USER', 'mongo_admin')}:"
           f"{os.getenv('MONGO_PASSWORD', 'changeme')}@127.0.0.1:27017/?authSource=admin")
    client = MongoClient(uri)
    coll = client["logs"]["app_events"]
    coll.delete_many({})
    coll.insert_many(docs)
    coll.create_index("timestamp")
    coll.create_index("event_type")
    print(f"  Mongo <- logs.app_events: {coll.count_documents({})} documents")
    client.close()


def main():
    random.seed(42)
    Faker.seed(42)
    print("Génération des logs applicatifs...")
    docs = gen_logs()
    print(f"  {len(docs)} événements générés")
    print("Chargement MongoDB...")
    load_to_mongo(docs)
    print("Terminé.")


def demo():
    """Self-check minimal (dette technique #2). Re-seed : voir le commentaire
    équivalent dans generate_cg_data.py (demo() ne doit pas décaler la
    séquence aléatoire de main())."""
    random.seed(42)
    Faker.seed(42)
    docs = gen_logs()
    assert len(docs) > 0
    assert all(1 <= d["client_id"] <= N_CLIENTS for d in docs)
    assert all(d["event_type"] in EVENT_TYPES for d in docs)
    assert all("produit_id" not in d or 1 <= d["produit_id"] <= N_PRODUITS for d in docs)
    assert all(("message" in d) == (d["event_type"] == "error") for d in docs)
    print(f"demo(): OK - {len(docs)} événements, tous invariants respectés")


if __name__ == "__main__":
    demo()
    main()
