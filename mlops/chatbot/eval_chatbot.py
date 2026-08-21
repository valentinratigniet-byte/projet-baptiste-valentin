"""Évaluation du chatbot Text-to-SQL sur un jeu de questions/réponses métier
avec vérité terrain (`questions_verite_terrain.json`).

Méthode : "execution accuracy" - on ne compare pas le texte SQL généré (un
même résultat peut s'écrire de plusieurs façons syntaxiquement valides), on
compare le résultat de son exécution à celui d'une requête de référence
écrite à la main, exécutée en direct sur les mêmes données au moment du
test - pas de valeurs figées en dur, le jeu de données peut être régénéré
entre deux exécutions.

Usage : .venv/Scripts/python.exe mlops/chatbot/eval_chatbot.py
"""
import json
import os
from decimal import Decimal

from schema import client_lecture
from text_to_sql import repondre

QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), "questions_verite_terrain.json")


def normaliser(lignes):
    """Rend deux résultats comparables indépendamment de l'ordre des lignes,
    de la précision flottante (NUMERIC BigQuery vs float Python) et du nom
    des colonnes - volontairement ignoré : `COUNT(*)` sans alias devient
    `f0_` côté BigQuery quand la référence écrit `AS n`, un nom différent
    ne veut pas dire une requête fausse. Limite assumée : deux colonnes
    différentes avec les mêmes valeurs par coïncidence compareraient égal -
    acceptable sur les requêtes à 1-2 colonnes de ce jeu de test."""
    def normaliser_valeur(v):
        if isinstance(v, (int, float, Decimal)):
            return round(float(v), 2)
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return v

    lignes_normalisees = [
        tuple(sorted((normaliser_valeur(v) for v in ligne.values()), key=str))
        for ligne in lignes
    ]
    return sorted(lignes_normalisees, key=str)


def executer_reference(client, sql):
    return [dict(r) for r in client.query(sql).result()]


def evaluer():
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        cas = json.load(f)

    client = client_lecture()
    reussites = 0
    for c in cas:
        resultat = repondre(c["question"], client=client)
        attendu = executer_reference(client, c["sql_reference"])
        ok = resultat["ok"] and normaliser(resultat["lignes"]) == normaliser(attendu)
        reussites += ok

        print(f"[{'OK' if ok else 'ECHEC'}] {c['question']}")
        if not ok:
            print(f"    SQL générée : {resultat['sql']!r}")
            if resultat["erreur"]:
                print(f"    erreur      : {resultat['erreur']}")
            print(f"    obtenu      : {resultat['lignes']}")
            print(f"    attendu     : {attendu}")

    precision = reussites / len(cas)
    print(f"\nPrécision (execution accuracy) : {reussites}/{len(cas)} ({precision:.0%})")
    return precision


def demo():
    """Self-check de `normaliser` seul (pas de dépendance Ollama/BigQuery) :
    ordre des lignes/colonnes, nom des colonnes et arrondi flottant ne
    doivent pas casser la comparaison ; une vraie différence de valeur, un
    résultat vide côté généré, ou une ligne en trop doivent rester détectés."""
    a = [{"total": Decimal("100.001"), "id": 2}, {"total": 50, "id": 1}]
    b = [{"n": 1, "montant": 50.0}, {"n": 2, "montant": 100.0}]  # noms de colonnes différents
    assert normaliser(a) == normaliser(b), "ordre, type numérique et nom de colonne ne devraient pas compter"

    c = [{"id": 1, "total": 51}, {"id": 2, "total": 100}]
    assert normaliser(a) != normaliser(c), "une vraie différence de valeur doit rester détectée"

    assert normaliser([]) != normaliser(a), "un résultat vide ne doit jamais matcher un résultat non vide"
    assert normaliser(a[:1]) != normaliser(a), "une ligne manquante doit rester détectée"

    print("demo(): OK - comparaison robuste à l'ordre/au nom des colonnes et à l'arrondi, "
          "sensible à une vraie différence")


if __name__ == "__main__":
    demo()
    evaluer()
