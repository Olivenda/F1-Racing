# Copyright Olivenda (Oliver Petz) 2026
"""More career depth: driver skills bought with XP, staff for the team boss, a junior academy, board confidence
and next-year development. Data and small helpers; the Career class owns the state."""

from __future__ import annotations

import random
from typing import Any

# ---------------------------------------------------------------------------------------------- driver skills
# key: (name, effect per level). Every skill acts in the race on the player's own car.
SKILLS: dict[str, tuple[str, str]] = {
    "quali": ("Qualifying-Ass", "+0,5 % Grip im Qualifying"),
    "tyres": ("Reifenflüsterer", "-5 % Reifenverschleiß"),
    "wet": ("Regenkönig", "+1,5 % Grip auf nasser Strecke"),
    "slip": ("Windschattenjäger", "+15 % Windschatten-Effekt"),
    "start": ("Raketenstart", "+6 % Beschleunigung in den ersten 6 s nach dem Start"),
    "fuel": ("Spritsparer", "-3 % Spritverbrauch"),
}
SKILL_COST = [50, 100, 160]            # XP for level 1, 2, 3 (midfield earns ~180 XP a season, a front-runner ~380)
MAX_SKILL = len(SKILL_COST)
START_BOOST_TIME = 6.0


def race_xp(pos: int, dnf: bool, points: int, beat_mate: bool, beat_rival: bool, goal: bool) -> int:
    """XP for one race weekend."""
    xp = 5 + points
    if not dnf:
        xp += 5
    if beat_mate:
        xp += 8
    if beat_rival:
        xp += 5
    if goal:
        xp += 10
    if not dnf and pos == 1:
        xp += 5
    return xp


# ---------------------------------------------------------------------------------------------- team staff
STAFF_ROLES: dict[str, tuple[str, str]] = {
    "td": ("Technischer Direktor", "Entwicklung: +2,5 % Erfolgschance und +6 % Wirkung je Stern"),
    "mech": ("Chefmechaniker", "Boxenstopps: -0,05 s je Stern und seltener ein verpatzter Stopp"),
    "eng": ("Renningenieur", "Deine Fahrer und Junioren entwickeln sich schneller"),
}
FIRST = ["Adrian", "Bea", "Carlo", "Dana", "Elif", "Finn", "Greta", "Hugo", "Ines", "Jonas", "Kai", "Lena", "Marco",
         "Nora", "Oskar", "Paula", "Rafael", "Sofia", "Tomas", "Vera", "Yuki", "Zoe"]
LAST = ["Albers", "Bianchi", "Costa", "Dufour", "Eriksen", "Fischer", "García", "Hoffmann", "Ivanov", "Jansen",
        "Kowalski", "Laurent", "Moretti", "Nakamura", "Olsen", "Peters", "Rossi", "Schmidt", "Tanaka", "Vogel",
        "Weber", "Young"]


def staff_salary(stars: int) -> float:
    return round(0.4 + 0.35 * stars ** 1.5, 1)


def staff_rep_needed(stars: int) -> float:
    return max(0.0, (stars - 2) * 18.0)


def staff_candidates(team_rep: float, taken: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Three candidates per role; the better the team's reputation, the better the people on offer."""
    out: dict[str, list[dict[str, Any]]] = {}
    for role in STAFF_ROLES:
        cands = []
        for _ in range(3):
            top = 3 + (team_rep >= 40) + (team_rep >= 70)
            stars = random.randint(1, top)
            for _ in range(20):
                name = f"{random.choice(FIRST)} {random.choice(LAST)}"
                if name not in taken:
                    break
            taken.add(name)
            cands.append({"name": name, "stars": stars, "salary": staff_salary(stars)})
        cands.sort(key=lambda s: -s["stars"])
        out[role] = cands
    return out


# ---------------------------------------------------------------------------------------------- junior academy
ACADEMY_SLOTS = 2
ACADEMY_FEE = 0.5              # Mio to sign a junior
ACADEMY_UPKEEP = 0.6           # Mio per season and junior
JUNIOR_MAX_AGE = 22


# ---------------------------------------------------------------------------------------------- board
BOARD_START = 60.0


def board_label(value: float) -> str:
    if value >= 75:
        return "begeistert"
    if value >= 50:
        return "zufrieden"
    if value >= 30:
        return "besorgt"
    return "Ultimatum"


# ---------------------------------------------------------------------------------------------- next-year car
NEXT_YEAR_FACTOR = 1.6         # a part developed for next season's car is worth this much more
