"""Exporte l'export ERP legacy brut (erp-legacy/exports/*.csv, Sprint 2) dans
erp-fiche.html, pour la maquette de fiche native en lecture seule liée depuis
la page de traçabilité (Sprint 8).

Lit directement les CSV bruts plutôt que la base Postgres erp_migre : c'est
la donnée la plus brute possible (avant toute réconciliation/nettoyage), et
ça évite une dépendance à Docker pour régénérer cette page.

Usage :
    python scripts/export_erp_fiches.py
"""

import csv
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
EXPORTS_DIR = HERE.parent.parent / "erp-legacy" / "exports"
VENTES_CSV = EXPORTS_DIR / "ERP_EXPORT_VTE_2023_2024.csv"
HTML_PATH = HERE.parent / "erp-fiche.html"


def load_rows(csv_path: Path) -> list[dict]:
    # Export ERP legacy en cp1252 (Windows), pas UTF-8 -- fidèle à un vrai
    # export ERP d'époque plutôt que reconverti pour l'occasion.
    with csv_path.open(encoding="cp1252", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def splice(html_path: Path, marker: str, block: str) -> None:
    html = html_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(// {marker}:BEGIN.*?\n)(.*?)(\n\s*// {marker}:END)", re.S)
    if not pattern.search(html):
        raise SystemExit(f"Marqueurs {marker} introuvables dans {html_path}")
    html_path.write_text(pattern.sub(lambda m: m.group(1) + block + m.group(3), html), encoding="utf-8")


def main() -> None:
    rows = load_rows(VENTES_CSV)
    block = f"  const ERP_ROWS = {json.dumps(rows, ensure_ascii=False, indent=2)};"
    splice(HTML_PATH, "ERP-ROWS", block)
    print(f"OK — {len(rows)} lignes exportées depuis {VENTES_CSV} vers {HTML_PATH}")


def demo() -> None:
    rows = load_rows(VENTES_CSV)
    assert rows, "l'export ERP ne doit pas être vide"
    assert {"NUMPCE", "CDCLI", "MTHT"} <= rows[0].keys(), "colonnes attendues absentes"
    print("demo() OK —", len(rows), "lignes lues")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        main()
