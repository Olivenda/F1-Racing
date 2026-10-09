# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import random
from typing import Any

DRIVER_PRESS: dict[str, list[tuple[str, list[tuple[str, dict[str, float]]]]]] = {
    "win": [("Sieg! Was war heute der Schlüssel?", [
        ("Das Team hat mir ein fantastisches Auto hingestellt.", {"trust": 5, "rep": 1}),
        ("Ich habe heute den Unterschied gemacht.", {"rep": 4, "trust": -3}),
        ("Wir bleiben auf dem Boden, die Saison ist lang.", {"rep": 1, "trust": 2})])],
    "podium": [("Podium! Bist du zufrieden?", [
        ("Absolut, ein starkes Ergebnis fürs ganze Team.", {"trust": 4, "rep": 1}),
        ("Nein. Ich will gewinnen, nicht Dritter werden.", {"rep": 3, "trust": -1}),
        ("Das Auto hat heute noch nicht für mehr gereicht.", {"rep": 1, "trust": -3})])],
    "dnf": [("Ausfall. Was ist passiert?", [
        ("Das passiert im Motorsport. Wir kommen stärker zurück.", {"trust": 3, "rep": 0}),
        ("Das Team muss die Zuverlässigkeit in den Griff kriegen!", {"rep": 1, "trust": -6}),
        ("Kein Kommentar.", {"rep": -2})])],
    "bad": [("Ein schwieriges Rennen. Woran lag es?", [
        ("Mein Fehler, ich muss mich steigern.", {"trust": 4, "rep": -1}),
        ("Das Auto war einfach nicht schnell genug.", {"rep": 1, "trust": -5}),
        ("Wir analysieren die Daten und lernen daraus.", {"trust": 1})])],
    "rival_won": [("{rival} hat dich heute geschlagen. Deine Antwort?", [
        ("Er hatte heute das bessere Paket. Respekt.", {"rep": 1, "trust": 1}),
        ("Das wird nicht wieder passieren.", {"rep": 2}),
        ("Er hatte Glück mit der Strategie.", {"rep": -1, "trust": -1})])],
    "rival_lost": [("Du hast {rival} geschlagen. Eine Botschaft an ihn?", [
        ("Er ist ein starker Gegner, das war harte Arbeit.", {"rep": 2}),
        ("Er sollte sich warm anziehen.", {"rep": 3, "trust": -1}),
        ("Ich konzentriere mich nur auf mich.", {"rep": 1, "trust": 1})])],
    "mate": [("Wie läuft das Duell mit deinem Teamkollegen?", [
        ("Wir pushen uns gegenseitig - gut fürs Team.", {"trust": 3}),
        ("Ich will die klare Nummer 1 sein.", {"rep": 2, "trust": -2}),
        ("Die Ergebnisse sprechen für sich.", {"rep": 1})])],
}

TEAM_PRESS: dict[str, list[tuple[str, list[tuple[str, dict[str, float]]]]]] = {
    "good": [("Starkes Wochenende. Woher kommt der Aufschwung?", [
        ("Unsere Partner machen diese Entwicklung möglich.", {"mood": 8, "team": 1}),
        ("Die Fahrer haben überragend gearbeitet.", {"team": 2}),
        ("Wir sind noch lange nicht am Ziel.", {"team": 1, "mood": 2})])],
    "bad": [("Wieder keine Punkte. Wie geht es weiter?", [
        ("Wir investieren massiv in die Entwicklung.", {"mood": 3, "team": -1}),
        ("Die Fahrer müssen mehr liefern.", {"team": -2, "mood": 2}),
        ("Geduld - Rom wurde nicht an einem Tag erbaut.", {"mood": -4, "team": 1})])],
    "dnf": [("Ein technischer Defekt. Ist die Zuverlässigkeit ein Problem?", [
        ("Wir haben das im Griff, ein Einzelfall.", {"mood": 2, "team": -1}),
        ("Ja, und wir investieren jetzt gezielt dort.", {"team": 1, "mood": -2}),
        ("Kein Kommentar.", {"mood": -5})])],
    "rival": [("Was sagen Sie zum Duell mit {rival}?", [
        ("Wir wollen sie diese Saison schlagen.", {"team": 2, "mood": 3}),
        ("Wir schauen nur auf uns.", {"team": 1}),
        ("Sie haben mehr Budget - das ist unfair.", {"mood": -4, "team": -1})])],
}


def pick_press(pool: dict[str, list], key: str, **fmt: str) -> dict[str, Any]:
    question, answers = random.choice(pool[key])
    return {"question": question.format(**fmt),
            "answers": [{"text": a.format(**fmt), "effects": e} for a, e in answers]}


def make_weekend_goal(car_rank: int, n_teams: int, fmt: str, has_mate: bool) -> dict[str, Any]:
    expected = 2 * car_rank
    options = [{"kind": "race_top", "n": min(22, expected + 1), "text": f"Rennen: Top {min(22, expected + 1)}"}]
    if fmt != "race":
        n = min(22, expected + 2)
        options.append({"kind": "quali_top", "n": n, "text": f"Qualifying: Top {n}"})
    if has_mate:
        options.append({"kind": "beat_mate", "n": 0, "text": "Vor dem Teamkollegen ins Ziel"})
    if car_rank <= n_teams // 2 + 1:
        options.append({"kind": "points", "n": 10, "text": "Punkte holen (Top 10)"})
    return random.choice(options)


def goal_met(goal: dict[str, Any], finish: int | None, quali: int | None, mate_finish: int | None,
             dnf: bool) -> bool:
    kind = goal.get("kind")
    if kind == "quali_top":
        return quali is not None and quali <= goal["n"]
    if dnf or finish is None:
        return False
    if kind in ("race_top", "points"):
        return finish <= goal["n"]
    if kind == "beat_mate":
        return mate_finish is None or finish < mate_finish
    return False


SPONSOR_NAMES = ["Volta Energy", "Nordlicht Bank", "Krakatoa Cola", "Helix Telecom", "Aurum Watches",
                 "Pixelstream", "Gecko Logistics", "Solaris Fuel", "Polar Air", "Titan Tools"]


def sponsor_offers(team_rep: float) -> list[dict[str, Any]]:
    names = random.sample(SPONSOR_NAMES, 3)
    r = team_rep
    return [
        {"name": names[0], "kind": "fixed", "base": round(2.0 + r / 30, 2), "bonus": 0.0,
         "text": "Feste Zahlung pro Rennen - kein Risiko"},
        {"name": names[1], "kind": "points", "base": round(1.0 + r / 50, 2), "bonus": 0.3,
         "text": "Weniger Grundgehalt, +0.3 Mio je WM-Punkt"},
        {"name": names[2], "kind": "podium", "base": round(1.3 + r / 45, 2), "bonus": 3.0,
         "text": "+3 Mio je Podium, +5 Mio für einen Sieg"},
    ]


def sponsor_payout(sponsor: dict[str, Any], mood: float, points: int, podiums: int, wins: int) -> float:
    if not sponsor:
        return 0.0
    base = sponsor["base"] * (0.8 + mood / 250.0)
    if sponsor["kind"] == "points":
        return base + sponsor["bonus"] * points
    if sponsor["kind"] == "podium":
        return base + sponsor["bonus"] * podiums + 5.0 * wins
    return base


FAILURES = ["Motorschaden", "Getriebeschaden", "Hydraulikproblem", "Elektrikdefekt", "Bremsdefekt",
            "Überhitzung"]


def base_reliability(rating: float) -> float:
    return max(0.955, min(0.99, 0.975 + (rating - 1.0) * 0.6))


def failure_chance(reliability: float) -> float:
    return max(0.0, (1.0 - reliability) * 2.0)
