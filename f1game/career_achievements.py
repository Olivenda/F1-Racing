# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .career import Career

# key -> (career kind: "driver" | "team" | "both", title, description)
ACHIEVEMENTS: dict[str, tuple[str, str, str]] = {
    "first_points": ("both", "Erste Punkte", "Hol die ersten WM-Punkte"),
    "first_podium": ("both", "Aufs Treppchen", "Fahre zum ersten Mal aufs Podium"),
    "first_win": ("both", "Erster Sieg", "Gewinne einen Grand Prix"),
    "pole": ("driver", "Pole Position", "Starte ein Rennen von Platz 1"),
    "wins_5": ("both", "Seriensieger", "Gewinne 5 Rennen"),
    "wins_20": ("both", "Legende", "Gewinne 20 Rennen"),
    "races_50": ("both", "Dauerbrenner", "Bestreite 50 Rennen"),
    "rival_5": ("both", "Erzrivale", "Schlage deinen Rivalen 5-mal in einer Saison"),
    "mate_sweep": ("driver", "Klare Nummer 1", "Sei in jedem Rennen einer Saison vor deinem Teamkollegen"),
    "goals_all": ("driver", "Musterschüler", "Erfülle alle Wochenendziele einer Saison"),
    "top_team": ("driver", "Im Topteam", "Unterschreibe bei einem Team mit Top-3-Auto"),
    "rich_driver": ("driver", "Gut verdient", "Spare 25 Mio auf deinem Konto an"),
    "title": ("driver", "Weltmeister", "Gewinne die Fahrer-WM"),
    "titles_3": ("driver", "Dynastie", "Gewinne 3 Fahrer-Titel"),
    "constructors": ("team", "Konstrukteurs-Champion", "Gewinne die Konstrukteurs-WM"),
    "max_dev": ("team", "Ingenieurskunst", "Bringe einen Entwicklungsbereich auf die Maximalstufe"),
    "campus": ("team", "Hightech-Campus", "Baue alle Einrichtungen voll aus"),
    "pit_crew": ("team", "Boxen-Weltrekord", "Trainiere die Boxencrew auf die Maximalstufe"),
    "star_signing": ("team", "Königstransfer", "Verpflichte einen Fahrer mit Wertung 88+"),
    "rich_team": ("team", "Finanzimperium", "Erreiche 100 Mio Budget"),
    "veteran": ("both", "Veteran", "Schließe 5 Saisons ab"),
}


def _wins(c: "Career") -> int:
    return sum(1 for e in c.race_log if e.get("pos") == 1 and not e.get("dnf"))


def _season_sweep(c: "Career") -> bool:
    log = c.season_log
    return bool(log.get("closed")) and log.get("mate_behind", 0) == 0 and \
        log.get("mate_ahead", 0) >= len(c.championship.rounds)


def _goals_all(c: "Career") -> bool:
    log = c.season_log
    return bool(log.get("closed")) and log.get("goals", 0) >= len(c.championship.rounds) and \
        log.get("goals_met", 0) >= log.get("goals", 0)


CHECKS: dict[str, Callable[["Career"], bool]] = {
    "first_points": lambda c: any(e.get("pts", 0) > 0 for e in c.race_log) or c.stats.get("points", 0) > 0,
    "first_podium": lambda c: any(e.get("pos", 99) <= 3 and not e.get("dnf") for e in c.race_log)
    or c.stats.get("podiums", 0) > 0,
    "first_win": lambda c: _wins(c) > 0 or c.stats.get("wins", 0) > 0,
    "pole": lambda c: any(e.get("q") == 1 for e in c.race_log),
    "wins_5": lambda c: max(_wins(c), c.stats.get("wins", 0)) >= 5,
    "wins_20": lambda c: max(_wins(c), c.stats.get("wins", 0)) >= 20,
    "races_50": lambda c: max(len(c.race_log), c.stats.get("races", 0)) >= 50,
    "rival_5": lambda c: c.season_log.get("rival_ahead", 0) >= 5,
    "mate_sweep": _season_sweep,
    "goals_all": _goals_all,
    "top_team": lambda c: bool(c.team) and c.team_ranking().index(c.team) < 3,
    "rich_driver": lambda c: c.bank >= 25.0,
    "title": lambda c: c.stats.get("titles", 0) >= 1,
    "titles_3": lambda c: c.stats.get("titles", 0) >= 3,
    "constructors": lambda c: any(h.get("team_champion") == c.team for h in c.history),
    "max_dev": lambda c: any(v >= 10 for v in c.upgrades.values()),
    "campus": lambda c: bool(c.facilities) and all(v >= 3 for v in c.facilities.values()),
    "pit_crew": lambda c: c.crew >= 5,
    "star_signing": lambda c: any(c.drivers[n]["rating"] >= 88 for n in c.own_drivers()),
    "rich_team": lambda c: c.budget >= 100.0,
    "veteran": lambda c: len(c.history) >= 5,
}


def available(kind: str) -> list[str]:
    return [k for k, (who, _, _) in ACHIEVEMENTS.items() if who in (kind, "both")]


def newly_unlocked(c: "Career") -> list[str]:
    out = []
    for key in available(c.kind):
        if key in c.achievements:
            continue
        try:
            if CHECKS[key](c):
                out.append(key)
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    return out


# ---------------------------------------------------------------------------------- rookies

ROOKIE_NAMES: dict[str, tuple[list[str], list[str]]] = {
    "DE": (["Jonas", "Felix", "Moritz", "Paul", "Niklas"], ["Krämer", "Hoffmann", "Brandt", "Seidel", "Winter"]),
    "GB": (["Oliver", "Harry", "Jack", "George", "Alfie"], ["Whitmore", "Ashby", "Fletcher", "Hale", "Pryce"]),
    "IT": (["Matteo", "Luca", "Andrea", "Marco", "Pietro"], ["Ferri", "Galli", "Moretti", "Conti", "Rinaldi"]),
    "FR": (["Hugo", "Théo", "Louis", "Mathis", "Jules"], ["Lefèvre", "Girard", "Moreau", "Roux", "Fournier"]),
    "ES": (["Pablo", "Álvaro", "Hugo", "Mario", "Iker"], ["Navarro", "Ortega", "Molina", "Castro", "Vidal"]),
    "NL": (["Daan", "Sem", "Lars", "Milan", "Bram"], ["de Vries", "Bakker", "Visser", "Smit", "Mulder"]),
    "BR": (["Gabriel", "Rafael", "Enzo", "Bruno", "Caio"], ["Souza", "Barbosa", "Ribeiro", "Teixeira", "Lima"]),
    "JP": (["Haruto", "Ren", "Sota", "Yuto", "Kaito"], ["Takeda", "Moriyama", "Fujiwara", "Kondo", "Ishida"]),
    "US": (["Logan", "Mason", "Carter", "Wyatt", "Hunter"], ["Brooks", "Hayes", "Turner", "Bennett", "Reed"]),
    "AU": (["Lachlan", "Cooper", "Riley", "Hamish", "Archer"], ["Dawson", "McKenzie", "Walsh", "Harding", "Crowe"]),
    "FI": (["Eetu", "Aleksi", "Joona", "Onni", "Valtteri"], ["Mäkelä", "Heikkinen", "Laine", "Koskinen", "Salo"]),
    "MX": (["Santiago", "Emiliano", "Diego", "Mateo", "Iker"], ["Ramírez", "Herrera", "Vargas", "Mendoza", "Cruz"]),
}
STYLES = ["balanced", "aggressive", "cautious", "base"]


def make_rookie(taken_names: set[str], taken_shorts: set[str], rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    for _ in range(40):
        nat = rng.choice(list(ROOKIE_NAMES))
        first, last = ROOKIE_NAMES[nat]
        name = f"{rng.choice(first)} {rng.choice(last)}"
        if name not in taken_names:
            break
    letters = "".join(ch for ch in name.split()[-1].upper() if ch.isalpha())
    short = (letters + "XXX")[:3]
    k = 3
    while short in taken_shorts and k < len(letters):
        short = letters[:2] + letters[k]
        k += 1
    rating = rng.randint(66, 76)
    potential = min(95, rating + rng.randint(8, 20))
    return {"short": short, "team": "", "default": False, "color": None, "checkpoint": "early",
            "helmet": [rng.randint(40, 255) for _ in range(3)], "style": rng.choice(STYLES), "rating": rating,
            "age": rng.randint(18, 21), "nationality": nat, "tyre_mgmt": round(rng.uniform(0.96, 1.06), 2),
            "salary": round(0.3 + ((rating - 60) / 32) ** 2 * 14, 1), "potential": potential, "years": 0,
            "name": name}
