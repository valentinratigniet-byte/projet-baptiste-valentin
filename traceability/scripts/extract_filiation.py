"""Régénère le jeu de données "Projet réel" de la page de traçabilité KPI
(index.html) à partir d'un target/ dbt compilé (manifest.json + catalog.json
+ run_results.json), et tient un historique d'extractions pour la détection
de dérive.

Adapté du même outil sur le projet solo (portfolio-data/projet-14-filiation),
repointé sur dbt_cg de ce projet binôme.

Usage :
    python scripts/extract_filiation.py [--target DBT_TARGET_DIR] [--html INDEX_HTML]

Par défaut, lit dbt_cg/ (ce projet) et met à jour index.html à côté de ce
script. Relancer après un `dbt run && dbt docs generate` : le schéma courant
est mis à jour, ET un instantané horodaté est ajouté dans snapshots/
(dédupliqué sur le generated_at du manifest) — la vue "Dérive" de l'outil
compare deux instantanés au choix.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlglot.lineage import lineage

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DEFAULT_TARGET = HERE.parent.parent / "dbt_cg" / "target"
DEFAULT_HTML = HERE.parent / "index.html"
SNAPSHOTS_DIR = HERE.parent / "snapshots"

# Nœud brut issu de la migration ERP (Sprint 2) : chaque table de ce système
# reçoit un lien vers la maquette de fiche native (erp-fiche.html), en plus
# de la requête de lecture seule standard.
ERP_SOURCE_NAME = "erp_migre"

TEST_LABEL = {
    "unique": "Unicité",
    "not_null": "Valeurs non nulles",
    "relationships": "Intégrité référentielle",
    "accepted_values": "Valeurs autorisées",
}
STATUS_MAP = {"success": "ok", "pass": "ok", "warn": "warn", "fail": "fail", "error": "fail"}
# dbt_cg n'a pas de macro generate_schema_name custom : le schéma généré est
# "<schema du profil>_<custom schema>", donc "public_staging"/"public_marts"
# (profiles.yml -> schema: public), pas juste "staging"/"marts".
LAYER = {"public_staging": "Staging", "public_marts": "Dimensions & faits"}


def build_tests_index(manifest: dict, run_results: dict) -> dict[tuple[str, str | None], list[dict]]:
    status_by_test = {r["unique_id"]: r["status"] for r in run_results["results"]}
    tests_by_target: dict[tuple[str, str | None], list[dict]] = {}
    for k, v in manifest["nodes"].items():
        if v["resource_type"] != "test":
            continue
        dep_nodes = v.get("depends_on", {}).get("nodes", [])
        col = v.get("column_name")
        tname = v.get("test_metadata", {}).get("name", "other")
        status = STATUS_MAP.get(status_by_test.get(k, ""), "ok")
        label = TEST_LABEL.get(tname, tname)
        if tname == "accepted_values":
            vals = v.get("test_metadata", {}).get("kwargs", {}).get("values", [])
            label = "Valeurs autorisées : " + ", ".join(str(x) for x in vals)
        for target in dep_nodes:
            tests_by_target.setdefault((target, col), []).append({"label": label, "status": status})
    return tests_by_target


def columns_data(columns: dict, tests_by_target: dict, uid: str, upstream_by_col: dict | None = None) -> list[dict]:
    upstream_by_col = upstream_by_col or {}
    result = []
    for cname, cv in sorted(columns.items(), key=lambda kv: kv[1]["index"]):
        entry = {"name": cname, "type": cv["type"], "tests": tests_by_target.get((uid, cname), [])}
        if cname in upstream_by_col:
            entry["upstream"] = upstream_by_col[cname]
        result.append(entry)
    return result


def build_schema_and_table_map(manifest: dict, catalog: dict) -> tuple[dict, dict[str, str]]:
    """Schéma (database -> schema -> table -> {colonne: type}) pour sqlglot,
    et une table de correspondance nom de table réelle -> id de nœud interne."""
    schema: dict[str, Any] = {}
    table_to_id: dict[str, str] = {}

    def add(db: str, sch: str, table: str, cols: dict, node_id: str) -> None:
        schema.setdefault(db, {}).setdefault(sch, {})[table] = {c: (v["type"] or "text") for c, v in cols.items()}
        table_to_id[table] = node_id

    for uid, v in manifest["sources"].items():
        cols = catalog["sources"].get(uid, {}).get("columns", {})
        add(v["database"], v["schema"], v["identifier"], cols, "src_" + v["name"])

    for uid, v in manifest["nodes"].items():
        if v["resource_type"] != "model":
            continue
        cols = catalog["nodes"].get(uid, {}).get("columns", {})
        add(v["database"], v["schema"], v.get("alias") or v["name"], cols, v["name"])

    return schema, table_to_id


def compute_upstream(compiled_sql: str | None, colnames: list[str], schema: dict, table_to_id: dict[str, str]) -> dict[str, list[dict]]:
    """Lignage colonne-à-colonne réel (sqlglot) : pour chaque colonne de sortie,
    remonte jusqu'aux colonnes sources dont elle dérive. Best-effort : une colonne
    dont le lignage ne peut pas être résolu (fonction non supportée, etc.) est
    simplement omise plutôt que de faire échouer toute l'extraction."""
    if not compiled_sql:
        return {}
    result: dict[str, list[dict]] = {}
    for col in colnames:
        try:
            root = lineage(col, compiled_sql, schema=schema, dialect="postgres")
        except Exception:
            continue
        pairs, seen = [], set()
        for leaf in root.walk():
            if leaf.downstream or leaf.expression.__class__.__name__ != "Table":
                continue
            node_id = table_to_id.get(leaf.expression.name)
            col_name = leaf.name.split(".")[-1]
            if not node_id or (node_id, col_name) in seen:
                continue
            seen.add((node_id, col_name))
            pairs.append({"node": node_id, "column": col_name})
        if pairs:
            result[col] = pairs
    return result


def fetch_row_counts(profile_path: Path, tables: list[tuple[str, str]]) -> dict[str, int]:
    """Compte les lignes réelles via une connexion Postgres directe. Best-effort :
    si la base n'est pas joignable, renvoie {} sans faire échouer l'extraction.

    profiles.yml de ce projet utilise des `{{ env_var(...) }}` Jinja (secrets
    via variables d'environnement, pas en clair comme sur le projet solo) —
    un yaml.safe_load naïf laisserait le texte Jinja tel quel. On lit donc les
    mêmes variables d'environnement, avec les mêmes valeurs par défaut que
    `erp-legacy/migrate_erp_to_target.py` et `dbt_cg/profiles.yml` (port 5434,
    base de démo locale, non secrets)."""
    if not profile_path.exists() or not tables:
        return {}
    try:
        import psycopg2
    except ImportError:
        return {}
    try:
        conn = psycopg2.connect(
            host="127.0.0.1", port=5434,
            dbname=os.getenv("POSTGRES_DB", "dbt_dev"),
            user=os.getenv("POSTGRES_USER", "dbt_user"),
            password=os.getenv("POSTGRES_PASSWORD", "changeme"),
            connect_timeout=3,
        )
    except Exception:
        return {}

    counts: dict[str, int] = {}
    with conn:
        with conn.cursor() as cur:
            for sch, tbl in tables:
                try:
                    cur.execute(f'select count(*) from "{sch}"."{tbl}"')
                    counts[f"{sch}.{tbl}"] = cur.fetchone()[0]
                except Exception:
                    conn.rollback()
    conn.close()
    return counts


def infer_fk_guesses(nodes: dict[str, Any]) -> None:
    """Relations inférées par convention de nommage (colonne `xxx_id` -> table
    `xxx`/`xxxs` du même système) entre tables brutes. PAS des contraintes
    réelles : ce projet n'en déclare aucune en base (landing zone non
    contrainte) — vérifié via information_schema avant d'écrire cette
    heuristique. Utilisé uniquement pour le mini schéma relationnel par
    système ; le lignage colonne-à-colonne (sqlglot) reste la source de
    vérité pour tout le reste."""
    raw_by_system: dict[str, list[str]] = {}
    for nid, n in nodes.items():
        if n["type"] == "raw" and n.get("source"):
            raw_by_system.setdefault(n["source"]["system"], []).append(nid)

    for ids in raw_by_system.values():
        short_to_id = {nodes[i]["short"].lower(): i for i in ids}
        for nid in ids:
            node = nodes[nid]
            guesses = []
            for col in node.get("columns", []):
                cname = col["name"]
                if not cname.endswith("_id") or cname == "id":
                    continue
                prefix = cname[:-3].lower()
                target_id = short_to_id.get(prefix) or short_to_id.get(prefix + "s")
                if not target_id or target_id == nid:
                    continue
                if "id" not in {c["name"] for c in nodes[target_id]["columns"]}:
                    continue
                guesses.append({"column": cname, "refNode": target_id, "refColumn": "id"})
            if guesses:
                node["fkGuesses"] = guesses


def extract_nodes(target_dir: Path) -> tuple[dict[str, Any], str]:
    """Retourne (nœuds, generated_at) à partir d'un target/ dbt compilé."""
    manifest = json.loads((target_dir / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((target_dir / "catalog.json").read_text(encoding="utf-8"))
    run_results = json.loads((target_dir / "run_results.json").read_text(encoding="utf-8"))
    tests_by_target = build_tests_index(manifest, run_results)
    schema, table_to_id = build_schema_and_table_map(manifest, catalog)

    nodes: dict[str, Any] = {}

    for uid, v in manifest["sources"].items():
        cols = catalog["sources"].get(uid, {}).get("columns", {})
        nid = "src_" + v["name"]
        select_cols = ", ".join(sorted(cols, key=lambda x: cols[x]["index"])) if cols else "*"
        nodes[nid] = {
            "domain": "Sources",
            "type": "raw",
            "name": v["identifier"],
            "short": v["identifier"],
            "description": v.get("description") or "Aucune description renseignée dans dbt (source externe).",
            "deps": [],
            "source": {"system": f"Postgres — {v['database']}", "table": f"{v['schema']}.{v['identifier']}"},
            "sql": f"select\n    {select_cols}\nfrom {v['schema']}.{v['identifier']}",
            "queryHint": f'select * from "{v["schema"]}"."{v["identifier"]}" limit 20;',
            "updateTemplate": (
                f'update "{v["schema"]}"."{v["identifier"]}"\n'
                f"set <colonne> = <nouvelle_valeur>\n"
                f"where <condition_precise>;"
            ),
            "columns": columns_data(cols, tests_by_target, uid),
        }
        if v["source_name"] == ERP_SOURCE_NAME:
            nodes[nid]["erpFicheHref"] = "erp-fiche.html?table=" + v["identifier"]

    for uid, v in manifest["nodes"].items():
        if v["resource_type"] != "model":
            continue
        name = v["name"]
        cat_cols = catalog["nodes"].get(uid, {}).get("columns", {})
        deps = [r["name"] for r in v.get("refs", [])] + ["src_" + s[1] for s in v.get("sources", [])]
        upstream_by_col = compute_upstream(v.get("compiled_code"), list(cat_cols.keys()), schema, table_to_id)
        alias = v.get("alias") or name
        nodes[name] = {
            "domain": LAYER.get(v.get("schema"), v.get("schema")),
            "type": "derived",
            "name": name,
            "short": name,
            "description": v.get("description") or "Aucune description renseignée dans dbt.",
            "deps": deps,
            "materialized": v["config"].get("materialized"),
            "relation": v["database"] + "." + v["schema"] + "." + alias,
            "sqlKind": "jinja",
            "sql": v.get("raw_code", ""),
            "queryHint": f'select * from "{v["schema"]}"."{alias}" limit 20;',
            "filePath": (v.get("original_file_path") or "").replace("\\", "/"),
            "columns": columns_data(cat_cols, tests_by_target, uid, upstream_by_col),
        }

    infer_fk_guesses(nodes)

    # Marquage RGPD : toute table portant une colonne "email" (donnée personnelle
    # réelle du projet), pour la démo du rôle RH dans l'outil.
    for n in nodes.values():
        if any(c["name"].lower() == "email" for c in n.get("columns", [])):
            n["tags"] = n.get("tags", []) + ["Donnée personnelle (RGPD)"]

    row_count_targets = [tuple(n["source"]["table"].split(".")) if n["type"] == "raw" else tuple(n["relation"].split(".")[1:]) for n in nodes.values()]
    row_counts = fetch_row_counts(target_dir.parent / "profiles.yml", row_count_targets)
    for n in nodes.values():
        key = n["source"]["table"] if n["type"] == "raw" else ".".join(n["relation"].split(".")[1:])
        if key in row_counts:
            n["rowCount"] = row_counts[key]

    return nodes, manifest["metadata"]["generated_at"]


def to_js_const(var_name: str, data: Any) -> str:
    return f"  const {var_name} = {json.dumps(data, ensure_ascii=False, indent=2)};"


def splice(html_path: Path, marker: str, block: str) -> None:
    html = html_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(// {marker}:BEGIN.*?\n)(.*?)(\n\s*// {marker}:END)",
        re.S,
    )
    if not pattern.search(html):
        raise SystemExit(f"Marqueurs {marker} introuvables dans {html_path}")
    new_html = pattern.sub(lambda m: m.group(1) + block + m.group(3), html)
    html_path.write_text(new_html, encoding="utf-8")


def save_snapshot(nodes: dict, generated_at: str, snapshots_dir: Path, label: str | None = None) -> bool:
    """Écrit un instantané JSON, sauf si un instantané existe déjà pour ce generated_at.
    Retourne True si un nouveau fichier a été écrit."""
    snapshots_dir.mkdir(exist_ok=True)
    safe_name = generated_at.replace(":", "-")
    path = snapshots_dir / f"{safe_name}.json"
    if path.exists():
        return False
    path.write_text(
        json.dumps({"label": label or generated_at, "generated_at": generated_at, "nodes": nodes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def build_snapshots_block(snapshots_dir: Path) -> str:
    snapshots = {}
    if snapshots_dir.exists():
        for f in sorted(snapshots_dir.glob("*.json")):
            snap = json.loads(f.read_text(encoding="utf-8"))
            snapshots[f.stem] = snap
    return to_js_const("SNAPSHOTS", snapshots)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Dossier target/ dbt compilé")
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML, help="index.html à mettre à jour")
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS_DIR, help="Dossier des instantanés historisés")
    parser.add_argument("--label", default=None, help="Nom lisible pour l'instantané de cette extraction")
    args = parser.parse_args()

    nodes, generated_at = extract_nodes(args.target)
    splice(args.html, "AUTO-GENERATED", to_js_const("realNodes", nodes) + "\n" + to_js_const("REAL_GENERATED_AT", generated_at))

    is_new = save_snapshot(nodes, generated_at, args.snapshots, args.label)
    splice(args.html, "SNAPSHOTS", build_snapshots_block(args.snapshots))

    print(f"OK — {args.html} régénéré depuis {args.target}")
    print(f"instantané {'ajouté' if is_new else 'déjà présent'} pour {generated_at}")


if __name__ == "__main__":
    main()
