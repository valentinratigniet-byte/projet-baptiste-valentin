"""Forecasting métier : prévision du Réel (montant_reel) des 3 prochains mois,
par (centre_cout_id, compte_id), à partir de `marts.fct_ecarts_reel_budget`
(BigQuery, alimentée par governance/sync_marts_to_bigquery.py).

Méthode : lissage exponentiel de Holt (tendance additive, sans saisonnalité).
Les séries sont mensuelles et courtes (jusqu'à 45 points, souvent ~24), et
aucune saisonnalité réelle n'est documentée dans les données simulées
(cf. docs/MCD.md) : un modèle saisonnier (ex. SARIMA) n'apporterait rien de
vérifiable ici, juste plus de paramètres à tort. Séries trop courtes
(< MIN_POINTS mois de Réel non nul) sont ignorées plutôt que forcées à
produire un chiffre non fiable — limite assumée, pas un bug caché.

Lecture non masquée de montant_reel (confidentiel) : nécessaire pour
prévoir la donnée elle-même. Le compte de chargement (BQ_KEYFILE) n'a pas
lui-même le rôle de lecteur fin sur le policy tag (il crée les tables, il
n'a pas vocation à en lire le contenu sensible - moindre privilège) : la
lecture se fait donc avec `direction-viewer` (gouvernance Sprint 6, voit les
lignes et les colonnes confidentielles sans masquage), l'écriture du
résultat avec BQ_KEYFILE (seul compte habilité à créer/charger des tables).
Voir docs/GOUVERNANCE.md.

Usage : .venv/Scripts/python.exe mlops/forecast.py
"""
import os
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account
from statsmodels.tsa.holtwinters import ExponentialSmoothing

load_dotenv()

BQ_PROJECT = os.getenv("BQ_PROJECT", "bv-dataplatform")
KEYS_DIR = os.path.join(os.path.expanduser("~"), ".gcp", "bv-viewers")
HORIZON_MOIS = 3
MIN_POINTS = 6  # en dessous, pas assez d'historique pour une tendance fiable


def get_bq_client():
    """Compte de chargement : crée/écrit les tables, moindre privilège en lecture."""
    creds = service_account.Credentials.from_service_account_file(os.environ["BQ_KEYFILE"])
    return bigquery.Client(project=BQ_PROJECT, credentials=creds)


def get_bq_client_lecture():
    """direction-viewer : lit montant_reel sans masquage (dette #6, gouvernance Sprint 6)."""
    keyfile = os.path.join(KEYS_DIR, "direction-viewer.json")
    creds = service_account.Credentials.from_service_account_file(keyfile)
    return bigquery.Client(project=BQ_PROJECT, credentials=creds)


def lire_series(client):
    """Regroupe le Réel par (centre_cout_id, compte_id), trié par période."""
    rows = client.query(
        "SELECT periode, centre_cout_id, compte_id, montant_reel "
        "FROM `marts.fct_ecarts_reel_budget` "
        "WHERE montant_reel IS NOT NULL "
        "ORDER BY centre_cout_id, compte_id, periode"
    ).result()
    series = {}
    for r in rows:
        cle = (r.centre_cout_id, r.compte_id)
        series.setdefault(cle, []).append((r.periode, float(r.montant_reel)))
    return series


def prevoir_serie(points, horizon=HORIZON_MOIS):
    """Holt (tendance additive) sur une série [(periode, valeur), ...] triée.
    Renvoie [(periode_future, valeur_prevue), ...] ou None si trop courte."""
    if len(points) < MIN_POINTS:
        return None
    derniere_periode = points[-1][0]
    valeurs = [v for _, v in points]
    modele = ExponentialSmoothing(
        valeurs, trend="add", seasonal=None, initialization_method="estimated"
    ).fit()
    previsions = modele.forecast(horizon)
    return [
        (derniere_periode + relativedelta(months=i + 1), round(float(p), 2))
        for i, p in enumerate(previsions)
    ]


def ecrire_previsions(client, lignes):
    table_id = f"{BQ_PROJECT}.marts.ml_forecast_reel"
    schema = [
        bigquery.SchemaField("periode", "DATE"),
        bigquery.SchemaField("centre_cout_id", "INT64"),
        bigquery.SchemaField("compte_id", "INT64"),
        bigquery.SchemaField("montant_reel_prevu", "NUMERIC"),
        bigquery.SchemaField("methode", "STRING"),
        bigquery.SchemaField("genere_le", "TIMESTAMP"),
    ]
    client.delete_table(table_id, not_found_ok=True)
    table = bigquery.Table(table_id, schema=schema)
    client.create_table(table)
    job = client.load_table_from_json(lignes, table_id)
    job.result()
    print(f"  {table_id} <- {len(lignes)} lignes")


def main():
    series = lire_series(get_bq_client_lecture())
    genere_le = datetime.now(timezone.utc).isoformat()

    lignes = []
    ignorees = 0
    for (centre_cout_id, compte_id), points in series.items():
        previsions = prevoir_serie(points)
        if previsions is None:
            ignorees += 1
            continue
        for periode, valeur in previsions:
            lignes.append({
                "periode": periode.isoformat(),
                "centre_cout_id": centre_cout_id,
                "compte_id": compte_id,
                "montant_reel_prevu": valeur,
                "methode": "holt_tendance_additive",
                "genere_le": genere_le,
            })

    print(f"{len(series)} séries, {len(series) - ignorees} prévues "
          f"({ignorees} ignorées, < {MIN_POINTS} mois d'historique)")
    ecrire_previsions(get_bq_client(), lignes)


def demo():
    """Self-check : une série synthétique à tendance connue (+10/mois) doit
    produire une prévision qui continue cette tendance ; une série trop
    courte doit être ignorée, pas plantée."""
    from datetime import date

    tendance = [(date(2025, m, 1), 100.0 + 10 * (m - 1)) for m in range(1, 13)]
    previsions = prevoir_serie(tendance, horizon=3)
    assert previsions is not None and len(previsions) == 3
    valeurs = [v for _, v in previsions]
    assert valeurs[0] > 200, f"prévision incohérente avec la tendance : {valeurs}"
    assert valeurs[2] > valeurs[0], "la tendance croissante devrait se poursuivre"

    courte = [(date(2025, 1, 1), 100.0), (date(2025, 2, 1), 110.0)]
    assert prevoir_serie(courte) is None, "série < MIN_POINTS doit être ignorée, pas forcée"

    print("demo(): OK - tendance connue extrapolée correctement, série courte ignorée")


if __name__ == "__main__":
    demo()
    main()
