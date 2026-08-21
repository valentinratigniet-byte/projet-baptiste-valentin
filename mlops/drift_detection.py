"""Détection de data drift (Evidently AI) sur le flux Réel CRM
(`public_staging.stg_crm__fact_ventes_reel`, Postgres dev).

Limite assumée : ce pipeline n'a encore qu'une seule exécution réelle
(pas d'historique de runs Bronze successifs à comparer). La "dérive" est
donc mesurée entre les deux moitiés chronologiques du même jeu de données
(ancien vs récent) plutôt qu'entre deux ingestions réelles distinctes -
ça prouve le mécanisme de détection, pas une vraie dérive de production.
Mise à niveau : comparer Bronze du jour à Bronze de la veille une fois le
pipeline exécuté plusieurs fois dans le temps (n8n, Sprint 5, pourrait le
déclencher quotidiennement).

Colonnes suivies : montant_reel/quantite (numériques),
centre_cout_id/produit_id/source (catégorielles) - les mêmes qui alimentent
l'entrepôt dbt en aval.

Usage : .venv/Scripts/python.exe mlops/drift_detection.py
"""
import os

import pandas as pd
import psycopg2
from evidently import Dataset, DataDefinition, Report
from evidently.presets import DataDriftPreset

REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "drift_report.html")
SEUIL_PART_COLONNES_DERIVEES = 0.5  # >= la moitié des colonnes suivies en dérive -> alerte

NUMERIQUES = ["montant_reel", "quantite"]
CATEGORIELLES = ["centre_cout_id", "produit_id", "source"]
DATA_DEF = DataDefinition(numerical_columns=NUMERIQUES, categorical_columns=CATEGORIELLES)


def lire_ventes():
    colonnes = ["date_vente", "montant_reel", "quantite", "centre_cout_id", "produit_id", "source"]
    conn = psycopg2.connect(
        host="127.0.0.1", port=5434,
        dbname=os.getenv("POSTGRES_DB", "dbt_dev"),
        user=os.getenv("POSTGRES_USER", "dbt_user"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )
    cur = conn.cursor()
    cur.execute(
        f"SELECT {', '.join(colonnes)} FROM public_staging.stg_crm__fact_ventes_reel "
        "ORDER BY date_vente"
    )
    df = pd.DataFrame(cur.fetchall(), columns=colonnes)
    cur.close()
    conn.close()
    df["montant_reel"] = df["montant_reel"].astype(float)  # psycopg2 renvoie du Decimal (NUMERIC)
    return df


def scinder_reference_courant(df):
    """Moitié chronologique la plus ancienne = référence, la plus récente = courant."""
    milieu = len(df) // 2
    return df.iloc[:milieu], df.iloc[milieu:]


def executer_rapport(reference_df, courant_df):
    ref_ds = Dataset.from_pandas(reference_df, data_definition=DATA_DEF)
    cur_ds = Dataset.from_pandas(courant_df, data_definition=DATA_DEF)
    report = Report(metrics=[DataDriftPreset()])
    return report.run(current_data=cur_ds, reference_data=ref_ds)


def resumer(snapshot):
    """P-value par colonne (métrique `ValueDrift`, un test par type de colonne :
    K-S pour le numérique, Z-test/chi2 pour le catégoriel) + part de colonnes
    en dérive (p < 0.05), calculée à partir de ces mêmes p-values plutôt que
    de la métrique agrégée `DriftedColumnsCount` du preset : cette dernière
    utilise en interne un test par défaut différent par colonne (Wasserstein
    au lieu de K-S, notamment) et donnerait un chiffre incohérent avec le
    détail affiché colonne par colonne - une seule source de vérité plutôt
    que deux tests qui se contredisent silencieusement dans l'output."""
    resultats = snapshot.dict()["metrics"]
    par_colonne = {
        m["config"]["column"]: m["value"]
        for m in resultats if m["metric_name"].startswith("ValueDrift")
    }
    part_derivees = sum(p < 0.05 for p in par_colonne.values()) / len(par_colonne)
    return part_derivees, par_colonne


def main():
    df = lire_ventes()
    reference_df, courant_df = scinder_reference_courant(df)
    print(f"Référence : {len(reference_df)} lignes ({reference_df['date_vente'].min()} -> "
          f"{reference_df['date_vente'].max()})")
    print(f"Courant   : {len(courant_df)} lignes ({courant_df['date_vente'].min()} -> "
          f"{courant_df['date_vente'].max()})")

    snapshot = executer_rapport(reference_df, courant_df)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    snapshot.save_html(REPORT_PATH)

    part_derivees, par_colonne = resumer(snapshot)
    print(f"\nColonnes en dérive : {part_derivees:.0%}")
    for colonne, p_value in par_colonne.items():
        print(f"  {colonne}: p-value={p_value:.4f}" + (" [DÉRIVE]" if p_value < 0.05 else ""))

    verdict = "DÉRIVE DÉTECTÉE" if part_derivees >= SEUIL_PART_COLONNES_DERIVEES else "PAS DE DÉRIVE SIGNIFICATIVE"
    print(f"\nVerdict : {verdict} (seuil : {SEUIL_PART_COLONNES_DERIVEES:.0%} des colonnes)")
    print(f"Rapport détaillé : {REPORT_PATH}")


def demo():
    """Self-check synthétique (pas de dépendance Postgres) : vérifie le
    signal sur `montant_reel` (colonne numérique, test K-S) - déterministe.
    Les colonnes catégorielles à faible cardinalité (produit_id, centre_cout_id)
    sont volontairement exclues de cette assertion : sur un petit échantillon
    (n=100/bucket), leur test (chi2/JS selon la cardinalité) peut remonter un
    faux positif isolé - limite connue de la détection catégorielle à faible
    volume, pas un défaut du script. Le rapport HTML réel (`main()`, ~4 400
    lignes) reste le juge de référence, cette assertion ne fait que garantir
    que le mécanisme réagit dans le bon sens."""
    import numpy as np
    rng = np.random.default_rng(42)

    stable = pd.DataFrame({
        "montant_reel": rng.normal(100, 10, 200),
        "quantite": rng.integers(1, 5, 200),
        "centre_cout_id": rng.integers(1, 5, 200),
        "produit_id": rng.integers(1, 10, 200),
        "source": rng.choice(["crm", "erp"], 200),
    })
    derive = stable.copy()
    derive["montant_reel"] = rng.normal(1000, 10, 200)  # dérive nette et volontaire

    _, colonnes_stable = resumer(executer_rapport(stable.iloc[:100], stable.iloc[100:]))
    _, colonnes_derive = resumer(executer_rapport(stable, derive))

    assert colonnes_stable["montant_reel"] > 0.05, (
        f"deux échantillons de la même distribution ne devraient pas déclencher "
        f"de fausse alerte sur montant_reel (p={colonnes_stable['montant_reel']:.4f})"
    )
    assert colonnes_derive["montant_reel"] < 0.01, (
        f"une dérive nette (moyenne x10) devrait être détectée sur montant_reel "
        f"(p={colonnes_derive['montant_reel']:.4f})"
    )
    print("demo(): OK - dérive volontaire détectée sur montant_reel "
          f"(p={colonnes_derive['montant_reel']:.2e}), pas de fausse alerte sur données stables "
          f"(p={colonnes_stable['montant_reel']:.2f})")


if __name__ == "__main__":
    demo()
    main()
