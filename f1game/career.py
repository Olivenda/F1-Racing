# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any

from .career_events import (DRIVER_PRESS, TEAM_PRESS, base_reliability, goal_met, make_weekend_goal,
                            pick_press, sponsor_offers, sponsor_payout)
from .championship import POINTS, Championship
from .profiles import (DATA_DIR, DriverProfile, Team, load_pool, player_profile, rating_to_checkpoint,
                       rating_to_pace)

if TYPE_CHECKING:
    from .sessions import RaceSession

CAREER_DIR = DATA_DIR / "careers"
LEGACY_FILE = DATA_DIR / "career.json"
SLOTS: dict[str, list[str]] = {"driver": ["driver_1", "driver_2", "driver_3"], "team": ["team_1", "team_2", "team_3"]}


def slot_path(slot: str):
    return CAREER_DIR / f"{slot}.json"


def slot_summary(slot: str) -> dict[str, Any] | None:
    try:
        raw = json.loads(slot_path(slot).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    champ = raw.get("champ", {})
    stamp = slot_path(slot).stat().st_mtime
    return {"kind": raw.get("kind"), "team": raw.get("team", ""), "season": raw.get("season", 1),
            "round": len(champ.get("results", [])), "rounds": len(champ.get("rounds", [])) or 6,
            "player": raw.get("player_name", ""), "budget": raw.get("budget", 0.0),
            "reputation": raw.get("reputation" if raw.get("kind") == "driver" else "team_rep", 0.0),
            "titles": raw.get("stats", {}).get("titles", 0), "wins": raw.get("stats", {}).get("wins", 0),
            "saved": time.strftime("%d.%m.%Y %H:%M", time.localtime(stamp))}


def migrate_legacy() -> None:
    if not LEGACY_FILE.exists():
        return
    try:
        raw = json.loads(LEGACY_FILE.read_text(encoding="utf-8"))
        kind = raw.get("kind", "driver")
        free = [sl for sl in SLOTS.get(kind, SLOTS["driver"]) if not slot_path(sl).exists()]
        if not free:
            return
        raw["slot"] = free[0]
        CAREER_DIR.mkdir(parents=True, exist_ok=True)
        slot_path(free[0]).write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        LEGACY_FILE.unlink()
    except (OSError, ValueError):
        pass

AREAS: dict[str, tuple[str, str, float]] = {
    "engine": ("Motor (Beschleunigung)", "engine", 0.006),
    "aero": ("Aerodynamik (Kurvengrip)", "aero", 0.006),
    "top_speed": ("Luftwiderstand (Topspeed)", "top_speed", 0.005),
    "brakes": ("Bremsen", "brakes", 0.006),
    "tyre_wear": ("Reifenschonung", "tyre_wear", -0.012),
}
MAX_LEVEL = 10
MAX_CREW = 5
NEW_TEAM_BASE = {"engine": 0.975, "aero": 0.97, "top_speed": 0.98, "brakes": 0.98, "tyre_wear": 1.03}
TEAM_COLORS: list[tuple[int, int, int]] = [(255, 0, 140), (120, 255, 60), (255, 230, 0), (150, 80, 255),
                                           (0, 200, 120), (255, 110, 30), (40, 40, 40), (255, 255, 255)]
START_BUDGET = 45.0
OPERATIONS_PER_RACE = 1.0
COST_CAP = 40.0
MAX_PROJECTS = 2
RELIABILITY_STEP = 0.004
FACILITIES: dict[str, tuple[str, str]] = {
    "windtunnel": ("Windkanal", "Projekte schneller fertig (+Erfolgschance)"),
    "simulator": ("Simulator", "Deine Fahrer verbessern sich während der Saison"),
    "factory": ("Fabrik", "Entwicklungsprojekte 8 % billiger je Stufe"),
}
FACILITY_COST = [8.0, 14.0, 20.0]
FACILITY_UPKEEP = 0.25


def upgrade_cost(level: int) -> float:
    return 3.0 + 1.5 * level


def crew_cost(level: int) -> float:
    return 4.0 + 2.0 * level


def crew_stop_time(level: int) -> float:
    return 3.0 - 0.15 * level


def team_rank(teams: dict[str, dict[str, Any]], name: str) -> int:
    order = sorted(teams, key=lambda t: -team_object(t, teams[t]).rating)
    return order.index(name) + 1


def team_object(name: str, d: dict[str, Any]) -> Team:
    return Team(name, tuple(d.get("color", (200, 200, 200))), d["engine"], d["aero"],
                d["top_speed"], d["brakes"], d["tyre_wear"])


@dataclass
class Career:
    kind: str
    player_name: str
    difficulty: str
    laps: int
    format: str
    teams: dict[str, dict[str, Any]]
    drivers: dict[str, dict[str, Any]]
    season: int = 1
    champ: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    news: list[str] = field(default_factory=list)
    team: str = ""
    stats: dict[str, int] = field(default_factory=lambda: {"races": 0, "wins": 0, "podiums": 0, "points": 0,
                                                           "titles": 0})
    contract: dict[str, Any] = field(default_factory=dict)
    reputation: float = 20.0
    bank: float = 0.0
    rival: str = ""
    offers: list[dict[str, Any]] = field(default_factory=list)
    budget: float = START_BUDGET
    team_rep: float = 25.0
    upgrades: dict[str, int] = field(default_factory=lambda: {k: 0 for k in AREAS})
    crew: int = 0
    player_drives: bool = True
    season_log: dict[str, Any] = field(default_factory=dict)
    slot: str = "driver_1"
    trust: float = 50.0
    weekend_goal: dict[str, Any] = field(default_factory=dict)
    quali_pos: int = 0
    press: dict[str, Any] = field(default_factory=dict)
    projects: list[dict[str, Any]] = field(default_factory=list)
    facilities: dict[str, int] = field(default_factory=lambda: {k: 0 for k in FACILITIES})
    sponsor: dict[str, Any] = field(default_factory=dict)
    sponsor_offers: list[dict[str, Any]] = field(default_factory=list)
    sponsor_mood: float = 60.0

    @classmethod
    def create(cls, slot: str, kind: str, player_name: str, difficulty: str, laps: int, fmt: str, teams: list[Team],
               team_name: str = "", team_color: tuple[int, int, int] = (255, 0, 140),
               player_drives: bool = True) -> "Career":
        team_data = {t.name: {"color": list(t.color), "engine": t.engine, "aero": t.aero, "top_speed": t.top_speed,
                              "brakes": t.brakes, "tyre_wear": t.tyre_wear} for t in teams}
        drivers: dict[str, dict[str, Any]] = {}
        for d in load_pool():
            seat = d.get("team", "") if d.get("team", "") in team_data else ""
            fixed = bool(d.get("fixed")) and bool(seat)
            drivers[d["name"]] = {"short": d["short"], "team": seat, "default": fixed, "color": d.get("color"),
                                  "checkpoint": d.get("checkpoint") or rating_to_checkpoint(int(d["rating"])),
                                  "helmet": d.get("helmet", [255, 255, 255]), "style": d.get("style", "balanced"),
                                  "rating": int(d["rating"]), "age": int(d.get("age", 25)),
                                  "nationality": d.get("nationality", ""), "tyre_mgmt": float(d.get("tyre_mgmt", 1.0)),
                                  "salary": float(d.get("salary", 1.0)), "potential": int(d.get("potential", 0)),
                                  "years": 2 if seat else 0}
        career = cls(kind=kind, player_name=player_name, difficulty=difficulty, laps=laps, format=fmt,
                     teams=team_data, drivers=drivers, player_drives=player_drives if kind == "team" else True,
                     slot=slot)
        if kind == "team":
            name = team_name.strip() or f"{player_name} Racing"
            career.teams[name] = {"color": list(team_color), **NEW_TEAM_BASE, "own": True}
            career.team = name
            career.news.append(f"Willkommen, Teamchef! {name} startet mit {START_BUDGET:.0f} Mio Budget.")
            career.news.append("Hol dir im Fahrermarkt " + ("einen Teamkollegen." if player_drives else "zwei Fahrer."))
        else:
            career.offers = career._make_offers(first=True)
            career.news.append("Willkommen in der Formel 1! Wähle deinen ersten Vertrag.")
        career._new_championship()
        return career

    def _new_championship(self) -> None:
        from .track import TRACK_DEFS
        champ = Championship(rounds=[d.key for d in TRACK_DEFS], format=self.format, laps=self.laps,
                             difficulty=self.difficulty, field_size=0, spectator=not self.player_drives,
                             player_name=self.player_name, team=self.team)
        self.champ = asdict(champ)
        if hasattr(self, "_champ_obj"):
            del self._champ_obj
        self.season_log = {"start_rep": self.reputation if self.kind == "driver" else self.team_rep,
                           "income": 0.0, "expenses": 0.0, "rival_ahead": 0, "rival_behind": 0,
                           "mate_ahead": 0, "mate_behind": 0, "dev_spent": 0.0, "wins": 0, "podiums": 0,
                           "points": 0, "goals_met": 0, "goals": 0, "failures": 0}
        self._ensure_reliability()
        self._pick_rival()
        if self.kind == "team":
            self.sponsor = {}
            self.sponsor_offers = sponsor_offers(self.team_rep)
        else:
            self._new_weekend_goal()

    @property
    def championship(self) -> Championship:
        if not hasattr(self, "_champ_obj"):
            obj = Championship(**self.champ)
            obj._hook = self._champ_saved
            self._champ_obj = obj
        return self._champ_obj

    def _champ_saved(self) -> None:
        self.champ = asdict(self.championship)
        self.save()

    @property
    def needs_contract(self) -> bool:
        return self.kind == "driver" and not self.team

    @property
    def season_over(self) -> bool:
        return self.championship.finished

    def team_obj(self, name: str) -> Team:
        return team_object(name, self.teams[name])

    def lineup(self, team: str) -> list[str]:
        return [n for n, d in self.drivers.items() if d["team"] == team]

    def own_drivers(self) -> list[str]:
        return self.lineup(self.team) if self.team else []

    def seats(self) -> int:
        return (1 if self.player_drives else 2) - len(self.own_drivers())

    def ready_to_race(self) -> tuple[bool, str]:
        if self.needs_contract:
            return False, "Zuerst einen Vertrag unterschreiben"
        if self.kind == "team" and not self.sponsor:
            return False, "Zuerst einen Titelsponsor für diese Saison wählen"
        if self.kind == "team" and self.seats() > 0:
            return False, "Noch ein freies Cockpit - im Fahrermarkt einen Fahrer verpflichten"
        if self.season_over:
            return False, "Saison beendet - Saisonabschluss öffnen"
        return True, ""

    def profile_for(self, name: str) -> DriverProfile:
        d = self.drivers[name]
        team = self.team_obj(d["team"])
        color = tuple(d["color"]) if d.get("color") else team.color
        rating = int(d["rating"])
        if d.get("default"):
            return DriverProfile(name, d["short"], team.name, color, tuple(d["helmet"]),
                                 d["style"], d["checkpoint"], team, rating_to_pace(rating), 1.0, rating)
        return DriverProfile(name, d["short"], team.name, color, tuple(d["helmet"]),
                             d["style"], rating_to_checkpoint(rating), team, rating_to_pace(rating),
                             float(d["tyre_mgmt"]), rating)

    def field_profiles(self) -> list[DriverProfile]:
        out = []
        for team in self.teams:
            for name in self.lineup(team):
                out.append(self.profile_for(name))
        return out

    def player(self) -> DriverProfile | None:
        if not self.player_drives or not self.team:
            return None
        return replace(player_profile(self.team_obj(self.team), self.player_name), rating=0)

    def pit_stop_times(self) -> dict[str, float]:
        return {self.team: crew_stop_time(self.crew)} if self.kind == "team" else {}

    def team_ranking(self) -> list[str]:
        return sorted(self.teams, key=lambda t: -self.team_obj(t).rating)

    def goal_text(self) -> str:
        if self.kind == "driver":
            g = self.contract.get("goal", 10)
            return f"Saisonziel: Fahrer-WM Platz {g} oder besser"
        g = self.team_goal()
        return f"Saisonziel: Konstrukteurs-WM Platz {g} oder besser"

    def team_goal(self) -> int:
        return max(1, min(len(self.teams) - 1, team_rank(self.teams, self.team) + 1))

    def player_driver_pos(self) -> int | None:
        for k, e in enumerate(self.championship.driver_table()):
            if e["player"]:
                return k + 1
        return None

    def team_pos(self, team: str | None = None) -> int | None:
        team = team or self.team
        for k, e in enumerate(self.championship.team_table()):
            if e["team"] == team:
                return k + 1
        return None

    def _ensure_reliability(self) -> None:
        for name, t in self.teams.items():
            if "reliability" not in t:
                t["reliability"] = 0.965 if t.get("own") else round(base_reliability(self.team_obj(name).rating), 4)

    def reliability_map(self) -> dict[str, float]:
        self._ensure_reliability()
        return {name: t["reliability"] for name, t in self.teams.items()}

    @property
    def status(self) -> str:
        if self.trust >= 75:
            return "Nummer-1-Fahrer"
        if self.trust >= 45:
            return "Stammfahrer"
        if self.trust >= 25:
            return "unter Beobachtung"
        return "Cockpit in Gefahr"

    def _new_weekend_goal(self) -> None:
        if self.kind != "driver" or not self.team or self.championship.finished:
            self.weekend_goal = {}
            return
        has_mate = bool(self.lineup(self.team))
        self.weekend_goal = make_weekend_goal(team_rank(self.teams, self.team), len(self.teams), self.format,
                                              has_mate)
        self.quali_pos = 0

    def note_quali(self, order: list[str]) -> None:
        if self.player_name in order:
            self.quali_pos = order.index(self.player_name) + 1

    def answer_press(self, index: int) -> str:
        if not self.press:
            return ""
        ans = self.press["answers"][index]
        e = ans["effects"]
        self.reputation = max(0.0, min(100.0, self.reputation + e.get("rep", 0)))
        self.trust = max(0.0, min(100.0, self.trust + e.get("trust", 0)))
        self.team_rep = max(0.0, min(100.0, self.team_rep + e.get("team", 0)))
        self.sponsor_mood = max(0.0, min(100.0, self.sponsor_mood + e.get("mood", 0)))
        parts = [f"{label} {e[k]:+.0f}" for k, label in (("rep", "Ruf"), ("trust", "Vertrauen"), ("team", "Teamruf"),
                                                           ("mood", "Sponsor")) if e.get(k)]
        self.news.insert(0, f"Presse: \"{ans['text']}\"")
        self.press = {}
        self.save()
        return " · ".join(parts) or "keine Auswirkung"

    def _make_press(self, rows: list[dict[str, Any]], names: list[str]) -> None:
        if self.kind == "driver":
            if self.player_name not in names:
                return
            k = names.index(self.player_name)
            row = rows[k]
            rival_k = names.index(self.rival) if self.rival in names else None
            if row["dnf"]:
                key = "dnf"
            elif k == 0:
                key = "win"
            elif k < 3:
                key = "podium"
            elif rival_k is not None and random.random() < 0.5:
                key = "rival_won" if rival_k < k else "rival_lost"
            elif k >= 2 * team_rank(self.teams, self.team) + 3:
                key = "bad"
            else:
                key = "mate"
            self.press = pick_press(DRIVER_PRESS, key, rival=self.rival or "dein Rivale")
        else:
            ours = [r for r in rows if r["team"] == self.team]
            points = sum(r["points"] for r in ours)
            if any(r.get("failure") for r in ours):
                key = "dnf"
            elif points >= 8:
                key = "good"
            elif points == 0 and random.random() < 0.6:
                key = "bad"
            else:
                key = "rival" if self.rival else "good"
            self.press = pick_press(TEAM_PRESS, key, rival=self.rival or "der Konkurrenz")

    def _ai_development(self) -> list[str]:
        ranking = self.team_ranking()
        brought = []
        labels = {"engine": "Motor", "aero": "Aero", "top_speed": "Speed", "brakes": "Bremsen"}
        for name in ranking:
            t = self.teams[name]
            if t.get("own"):
                continue
            rank = ranking.index(name) + 1
            if random.random() < 0.38 - 0.015 * rank:
                key = random.choice(list(labels))
                t[key] = round(min(1.07, t[key] + random.uniform(0.002, 0.005)), 4)
                brought.append(f"{name} ({labels[key]})")
            if random.random() < 0.15:
                t["reliability"] = round(min(0.995, t.get("reliability", 0.975) + 0.002), 4)
        return [f"Updates: {', '.join(brought[:4])}" + (" ..." if len(brought) > 4 else "")] if brought else []

    def _pick_rival(self) -> None:
        if self.kind == "team":
            last = self.history[-1]["team_table"] if self.history else None
            ranking = [e["team"] for e in last] if last else self.team_ranking()
            if self.team in ranking:
                k = ranking.index(self.team)
                self.rival = ranking[k - 1] if k > 0 else (ranking[1] if len(ranking) > 1 else "")
            return
        if not self.team:
            self.rival = ""
            return
        last = self.history[-1]["driver_table"] if self.history else None
        candidates = [n for n, d in self.drivers.items() if d["team"] and d["team"] != self.team]
        if last:
            names = [e["name"] for e in last]
            if self.player_name in names:
                k = names.index(self.player_name)
                for name in reversed(names[:k]) if k > 0 else names[1:]:
                    if name in candidates:
                        self.rival = name
                        return
        ranking = self.team_ranking()
        k = ranking.index(self.team)
        for team in [ranking[k - 1]] if k > 0 else ranking[1:]:
            mates = [n for n in candidates if self.drivers[n]["team"] == team]
            if mates:
                self.rival = mates[0]
                return
        self.rival = random.choice(candidates) if candidates else ""

    def after_race(self, session: "RaceSession", result: dict[str, Any]) -> list[str]:
        rows = result["rows"]
        names = [r["name"] for r in rows]
        notes: list[str] = []
        track = result["track_name"]
        log = self.season_log
        winner = rows[0]["name"] if rows else "?"
        notes.append(f"{track}: Sieg für {winner}.")
        if self.player_drives and self.player_name in names:
            k = names.index(self.player_name)
            row = rows[k]
            st = self.stats
            st["races"] += 1
            st["points"] += row["points"]
            if not row["dnf"]:
                st["wins"] += k == 0
                st["podiums"] += k < 3
            notes.append(f"Du wurdest {'ausgeschieden (DNF)' if row['dnf'] else f'P{k + 1}'}"
                         + (f" (+{row['points']} Punkte)." if row["points"] else "."))
        failures = getattr(session, "failures", {})
        for r in rows:
            r["failure"] = failures.get(r["name"], "")
        for name, why in failures.items():
            notes.append(f"Technischer Defekt: {name} ({why}).")
        if self.player_drives and self.player_name in names:
            k = names.index(self.player_name)
            log["points"] = log.get("points", 0) + rows[k]["points"]
            if not rows[k]["dnf"]:
                log["wins"] = log.get("wins", 0) + (k == 0)
                log["podiums"] = log.get("podiums", 0) + (k < 3)
        if self.kind == "driver":
            notes += self._driver_after_race(rows, names)
        else:
            notes += self._team_after_race(rows)
        notes += self._ai_development()
        self._make_press(rows, names)
        self.news = (notes + self.news)[:16]
        log["races"] = log.get("races", 0) + 1
        if self.kind == "driver":
            self._new_weekend_goal()
        self._champ_saved()
        return notes

    def _driver_after_race(self, rows: list[dict[str, Any]], names: list[str]) -> list[str]:
        notes = []
        log = self.season_log
        me = names.index(self.player_name) if self.player_name in names else None
        if me is None:
            return notes
        row = rows[me]
        rep = row["points"] / 4.0 - 0.4 - (2.0 if row["dnf"] else 0.0)
        mates = [k for k, r in enumerate(rows) if r["team"] == self.team and k != me]
        for k in mates:
            if me < k:
                rep += 1.0
                log["mate_ahead"] += 1
            else:
                log["mate_behind"] += 1
        if self.rival in names:
            r = names.index(self.rival)
            if me < r:
                rep += 1.5
                log["rival_ahead"] += 1
                notes.append(f"Rivale {self.rival} geschlagen!")
            else:
                log["rival_behind"] += 1
                notes.append(f"Rivale {self.rival} war diesmal vorne.")
        self.reputation = max(0.0, min(100.0, self.reputation + rep))
        trust = (1.0 if any(me < k for k in mates) else 0.0) - (1.5 if row["dnf"] and not row.get("failure") else 0.0)
        bonus = 0.0
        goal = self.weekend_goal
        if goal:
            mate_finish = min((k + 1 for k in mates if not rows[k]["dnf"]), default=None)
            ok = goal_met(goal, me + 1, self.quali_pos or None, mate_finish, row["dnf"])
            log["goals"] = log.get("goals", 0) + 1
            if ok:
                log["goals_met"] = log.get("goals_met", 0) + 1
                trust += 6.0
                bonus = 0.3
                notes.append(f"Wochenendziel erreicht ({goal['text']}): +0.3 Mio Bonus, Team vertraut dir mehr.")
            else:
                trust -= 4.0
                notes.append(f"Wochenendziel verfehlt ({goal['text']}).")
        self.trust = max(0.0, min(100.0, self.trust + trust))
        pay = self.contract.get("salary", 0.0) / len(self.championship.rounds) + 0.05 * row["points"] + bonus
        self.bank += pay
        log["income"] += pay
        return notes

    def _team_after_race(self, rows: list[dict[str, Any]]) -> list[str]:
        notes = []
        log = self.season_log
        ours = [k for k, r in enumerate(rows) if r["team"] == self.team]
        points = sum(rows[k]["points"] for k in ours)
        podiums = sum(1 for k in ours if k < 3 and not rows[k]["dnf"])
        wins = sum(1 for k in ours if k == 0 and not rows[k]["dnf"])
        sponsor = sponsor_payout(self.sponsor, self.sponsor_mood, points, podiums, wins)
        self.sponsor_mood = max(0.0, min(100.0, self.sponsor_mood + (3 if points else -2)
                                         - 4 * sum(1 for k in ours if rows[k].get("failure"))))
        prize = 0.25 * points
        salaries = sum(self.drivers[n]["salary"] for n in self.own_drivers()) / len(self.championship.rounds)
        upkeep = FACILITY_UPKEEP * sum(self.facilities.values())
        costs = salaries + OPERATIONS_PER_RACE + upkeep
        notes += self._progress_projects()
        sim = self.facilities.get("simulator", 0)
        for name in self.own_drivers():
            d = self.drivers[name]
            if sim and random.random() < 0.15 * sim and d["rating"] < max(d.get("potential", 0), d["rating"]) + 2:
                d["rating"] += 1
                notes.append(f"Simulator-Arbeit zahlt sich aus: {name} jetzt Wertung {d['rating']}.")
        self.budget += sponsor + prize - costs
        log["income"] += sponsor + prize
        log["expenses"] += costs
        self.team_rep = max(0.0, min(100.0, self.team_rep + points / 6.0 - 0.3))
        notes.append(f"Finanzen: +{sponsor + prize:.1f} Mio ({self.sponsor.get('name', 'Sponsor')}/Preisgeld), "
                     f"-{costs:.1f} Mio (Gehälter/Betrieb). Budget {self.budget:.1f} Mio.")
        team_names = [r["team"] for r in rows]
        if self.rival and self.rival in team_names and self.team in team_names:
            ours = min(k for k, r in enumerate(rows) if r["team"] == self.team)
            theirs = min(k for k, r in enumerate(rows) if r["team"] == self.rival)
            if ours < theirs:
                log["rival_ahead"] += 1
                notes.append(f"Rivalenteam {self.rival} geschlagen!")
            else:
                log["rival_behind"] += 1
        if self.budget < 0:
            notes.append("ACHTUNG: Budget im Minus - keine Upgrades oder Verpflichtungen möglich!")
        return notes

    def area_level(self, area: str) -> int:
        return self.upgrades.get(area, 0)

    def project_cost(self, area: str) -> float:
        return round(upgrade_cost(self.area_level(area)) * (1.0 - 0.08 * self.facilities.get("factory", 0)), 2)

    def project_duration(self, area: str) -> int:
        base = 2 if self.facilities.get("windtunnel", 0) < 2 else 1
        return base + (1 if self.area_level(area) >= 5 else 0)

    def project_success(self) -> float:
        return min(0.97, 0.8 + 0.06 * self.facilities.get("windtunnel", 0))

    def cap_left(self) -> float:
        return COST_CAP - self.season_log.get("dev_spent", 0.0)

    def start_project(self, area: str) -> str:
        if any(p["area"] == area for p in self.projects):
            return "Für diesen Bereich läuft bereits ein Projekt"
        if len(self.projects) >= MAX_PROJECTS:
            return f"Maximal {MAX_PROJECTS} Projekte gleichzeitig"
        if self.area_level(area) >= MAX_LEVEL:
            return "Maximale Stufe erreicht"
        cost = self.project_cost(area)
        if self.budget < cost:
            return f"Zu wenig Budget ({cost:.1f} Mio nötig)"
        if cost > self.cap_left() + 1e-6:
            return f"Budgetobergrenze erreicht (noch {self.cap_left():.1f} Mio diese Saison)"
        self.budget -= cost
        self.season_log["expenses"] = self.season_log.get("expenses", 0.0) + cost
        self.season_log["dev_spent"] = self.season_log.get("dev_spent", 0.0) + cost
        races = self.project_duration(area)
        self.projects.append({"area": area, "races_left": races, "cost": cost})
        name = AREAS[area][0] if area in AREAS else "Zuverlässigkeit"
        self.news.insert(0, f"Projekt gestartet: {name} Stufe {self.area_level(area) + 1} (fertig in {races} Rd.)")
        self.save()
        return f"{name}: Projekt läuft ({races} Rennen)"

    def _progress_projects(self) -> list[str]:
        notes, keep = [], []
        for p in self.projects:
            p["races_left"] -= 1
            if p["races_left"] > 0:
                keep.append(p)
                continue
            area = p["area"]
            ok = random.random() < self.project_success()
            share = 1.0 if ok else 0.5
            if area == "reliability":
                t = self.teams[self.team]
                t["reliability"] = round(min(0.995, t.get("reliability", 0.965) + RELIABILITY_STEP * share), 4)
                name = "Zuverlässigkeit"
            else:
                name, key, step = AREAS[area]
                self.teams[self.team][key] = round(self.teams[self.team][key] + step * share, 4)
            self.upgrades[area] = self.area_level(area) + 1
            notes.append(f"Neues Teil: {name} Stufe {self.upgrades[area]}" +
                         ("" if ok else " - enttäuschend, nur halbe Wirkung."))
        self.projects = keep
        return notes

    def build_facility(self, key: str) -> str:
        level = self.facilities.get(key, 0)
        if level >= len(FACILITY_COST):
            return "Maximale Ausbaustufe"
        cost = FACILITY_COST[level]
        if self.budget < cost:
            return f"Zu wenig Budget ({cost:.0f} Mio nötig)"
        self.budget -= cost
        self.season_log["expenses"] = self.season_log.get("expenses", 0.0) + cost
        self.facilities[key] = level + 1
        self.news.insert(0, f"Ausbau: {FACILITIES[key][0]} Stufe {level + 1} (-{cost:.0f} Mio)")
        self.save()
        return f"{FACILITIES[key][0]} Stufe {level + 1}"

    def choose_sponsor(self, index: int) -> str:
        offer = self.sponsor_offers[index]
        self.sponsor = offer
        self.sponsor_offers = []
        self.sponsor_mood = 60.0
        self.news.insert(0, f"Titelsponsor {self.season}. Saison: {offer['name']} ({offer['text']})")
        self.save()
        return f"Vertrag mit {offer['name']}"

    def buy_crew(self) -> str:
        if self.crew >= MAX_CREW:
            return "Boxencrew bereits auf Maximalstufe"
        cost = crew_cost(self.crew)
        if self.budget < cost:
            return f"Zu wenig Budget ({cost:.1f} Mio nötig)"
        self.budget -= cost
        self.crew += 1
        self.news.insert(0, f"Boxencrew trainiert: Stopp jetzt {crew_stop_time(self.crew):.2f} s (-{cost:.1f} Mio)")
        self.save()
        return f"Boxencrew Stufe {self.crew}"

    def required_rep(self, name: str) -> float:
        return max(0.0, (self.drivers[name]["rating"] - 68) * 2.6)

    def sign(self, name: str, years: int) -> str:
        d = self.drivers[name]
        if d["team"]:
            return f"{name} fährt bereits für {d['team']}"
        if self.seats() <= 0:
            return "Kein freies Cockpit - zuerst einen Fahrer entlassen"
        if self.team_rep < self.required_rep(name):
            return f"{name} will nicht: dein Team braucht Ruf {self.required_rep(name):.0f} (hat {self.team_rep:.0f})"
        fee = d["salary"] * 0.5
        if self.budget < fee:
            return f"Zu wenig Budget für die Ablöse ({fee:.1f} Mio)"
        self.budget -= fee
        self.season_log["expenses"] = self.season_log.get("expenses", 0.0) + fee
        d["team"] = self.team
        d["years"] = years
        self.news.insert(0, f"Neu im Team: {name} ({years} J., {d['salary']:.1f} Mio/Saison, Ablöse {fee:.1f} Mio)")
        self.save()
        return f"{name} verpflichtet!"

    def release(self, name: str) -> str:
        d = self.drivers[name]
        cost = d["salary"] * 0.5 * max(1, d.get("years", 1))
        if self.budget < cost:
            return f"Abfindung zu teuer ({cost:.1f} Mio)"
        self.budget -= cost
        d["team"] = ""
        d["years"] = 0
        self.news.insert(0, f"{name} entlassen (Abfindung {cost:.1f} Mio)")
        self.save()
        return f"{name} entlassen"

    def _make_offers(self, first: bool = False) -> list[dict[str, Any]]:
        ranking = self.team_ranking()
        n = len(ranking)
        offers = []
        if first:
            candidates = ranking[-3:]
        else:
            candidates = [t for k, t in enumerate(ranking)
                          if self.reputation + random.uniform(-6, 6) >= 85 - 70 * k / max(1, n - 1)]
            if self.team and self.team not in candidates and self._goal_met():
                candidates.append(self.team)
            if not candidates:
                candidates = ranking[-1:]
        for team in candidates:
            rank = ranking.index(team) + 1
            salary = round(0.6 + (n - rank) * 0.9 + self.reputation / 25, 1)
            goal = max(2, min(20, round(rank * 1.6) + 2))
            limit = 1.0 + self.reputation / 250 + (self.trust / 400 if team == self.team else 0.0) + \
                random.uniform(0.0, 0.15)
            offers.append({"team": team, "salary": salary, "years": random.choice([1, 2, 2, 3]), "goal": goal,
                           "rank": rank, "limit": round(limit, 3)})
        offers.sort(key=lambda o: o["rank"])
        return offers[:5]

    def negotiate(self, index: int, demand: float, years: int) -> tuple[bool, str]:
        offer = self.offers[index]
        if demand > offer.get("limit", 1.1) + 1e-9:
            team = offer["team"]
            del self.offers[index]
            if not self.offers:
                worst = self.team_ranking()[-1]
                self.offers.append({"team": worst, "salary": 0.8, "years": 1, "goal": 22, "rank": len(self.teams),
                                    "limit": 1.0})
            self.save()
            return False, f"{team} lehnt ab und zieht das Angebot zurück!"
        offer = dict(offer, salary=round(offer["salary"] * demand, 1), years=years)
        self.accept_offer(offer)
        return True, f"Unterschrieben: {offer['salary']:.1f} Mio/Saison, {years} Saison(s)"

    def accept_offer(self, offer: dict[str, Any]) -> None:
        old = self.team
        if offer["team"] != old:
            for name in self.lineup(offer["team"]):
                d = self.drivers[name]
                if not d.get("default"):
                    d["team"] = old if old else ""
                    if old:
                        self.news.insert(0, f"{name} wechselt im Tausch zu {old}.")
        self.team = offer["team"]
        self.contract = {"salary": offer["salary"], "years": offer["years"], "goal": offer["goal"]}
        self.offers = []
        if old and old != self.team:
            self.news.insert(0, f"Wechsel: {old} -> {self.team}")
        self.news.insert(0, f"Vertrag bei {self.team}: {offer['years']} J., {offer['salary']:.1f} Mio/Saison, "
                            f"Ziel P{offer['goal']}")
        if old != self.team:
            self.trust = 50.0
        self._new_weekend_goal()
        champ = self.championship
        champ.team = self.team
        self._pick_rival()
        self._champ_saved()

    def _goal_met(self) -> bool:
        if self.kind == "driver":
            pos = self.player_driver_pos()
            return pos is not None and pos <= self.contract.get("goal", 10)
        pos = self.team_pos()
        return pos is not None and pos <= self.team_goal()

    def season_review(self) -> dict[str, Any]:
        champ = self.championship
        dt, tt = champ.driver_table(), champ.team_table()
        goal_met = self._goal_met()
        review = {"season": self.season, "champion": dt[0]["name"] if dt else "-",
                  "team_champion": tt[0]["team"] if tt else "-", "driver_pos": self.player_driver_pos(),
                  "team_pos": self.team_pos() if self.team else None, "goal_met": goal_met,
                  "goal": self.goal_text(), "log": dict(self.season_log)}
        if self.kind == "team" and self.team_pos():
            review["prize"] = (len(self.teams) - self.team_pos() + 1) * 2.5
        return review

    def finish_season(self) -> dict[str, Any]:
        review = self.season_review()
        if self.season_log.get("closed"):
            return review
        champ = self.championship
        log = self.season_log
        self.history.append({"season": self.season, "driver_table": champ.driver_table()[:12],
                             "team_table": champ.team_table(), "driver_pos": review["driver_pos"],
                             "team_pos": review["team_pos"], "champion": review["champion"],
                             "team_champion": review["team_champion"], "team": self.team,
                             "wins": log.get("wins", 0), "podiums": log.get("podiums", 0),
                             "points": log.get("points", 0), "goal_met": review["goal_met"],
                             "goals": f"{log.get('goals_met', 0)}/{log.get('goals', 0)}",
                             "budget": round(self.budget, 1), "rep": round(self.reputation if self.kind == "driver"
                                                                           else self.team_rep, 1)})
        if review["champion"] == self.player_name:
            self.stats["titles"] += 1
        if self.kind == "driver":
            self.reputation = max(0.0, min(100.0, self.reputation + (10 if review["goal_met"] else -8)
                                           + (15 if review["driver_pos"] == 1 else 0)))
            self.contract["years"] = self.contract.get("years", 1) - 1
            self.trust = max(0.0, min(100.0, self.trust + (8 if review["goal_met"] else -10)))
            self.offers = self._make_offers()
            if self.trust < 25:
                self.offers = [o for o in self.offers if o["team"] != self.team] or self.offers
                self.contract["years"] = 0
                self.news.insert(0, f"{self.team} löst deinen Vertrag auf - zu wenig Vertrauen.")
            elif self.contract["years"] > 0 and all(o["team"] != self.team for o in self.offers):
                rank = team_rank(self.teams, self.team)
                self.offers.insert(0, {"team": self.team, "salary": self.contract["salary"],
                                       "years": self.contract["years"], "goal": self.contract["goal"], "rank": rank,
                                       "current": True, "limit": 1.0 + self.trust / 300})
            for o in self.offers:
                if o["team"] == self.team and self.trust >= 75 and not o.get("current"):
                    o["salary"] = round(o["salary"] * 1.15, 1)
        else:
            prize = review.get("prize", 0.0)
            self.budget += prize
            self.team_rep = max(0.0, min(100.0, self.team_rep + (8 if review["goal_met"] else -5)))
            for name in self.own_drivers():
                self.drivers[name]["years"] = self.drivers[name].get("years", 1) - 1
        self.season_log["closed"] = True
        self.save()
        return review

    def expiring(self) -> list[str]:
        return [n for n in self.own_drivers() if self.drivers[n].get("years", 0) <= 0]

    def renew(self, name: str, years: int = 2) -> str:
        d = self.drivers[name]
        d["years"] = years
        d["salary"] = round(d["salary"] * 1.1, 1)
        self.save()
        return f"{name} verlängert ({years} J., {d['salary']:.1f} Mio/Saison)"

    def start_next_season(self) -> list[str]:
        notes = []
        if self.kind == "team":
            for name in self.expiring():
                self.drivers[name]["team"] = ""
                notes.append(f"Vertrag ausgelaufen: {name} verlässt das Team.")
        for name, d in self.drivers.items():
            if d.get("default"):
                continue
            d["age"] += 1
            if d["age"] < 26:
                d["rating"] = min(max(d["rating"], d.get("potential", d["rating"])), d["rating"] + random.randint(1, 4))
            elif d["age"] > 32:
                d["rating"] = max(55, d["rating"] - random.randint(0, 3))
            else:
                d["rating"] = max(55, min(95, d["rating"] + random.randint(-1, 1)))
            d["salary"] = round(0.3 + ((d["rating"] - 60) / 32) ** 2 * 14, 1) if d["team"] != self.team \
                else d["salary"]
        for team, t in self.teams.items():
            if t.get("own"):
                continue
            for key in ("engine", "aero", "top_speed", "brakes"):
                t[key] = round(max(0.95, min(1.06, t[key] + random.gauss(0.002, 0.006))), 4)
        best = max(self.teams, key=lambda t: self.team_obj(t).rating if not self.teams[t].get("own") else 0)
        notes.append(f"Wintertests: {best} gilt als Favorit für Saison {self.season + 1}.")
        self.season += 1
        self._new_championship()
        self.news = (notes + [f"Saison {self.season} beginnt!"] + self.news)[:14]
        self.save()
        return notes

    def save(self) -> None:
        if hasattr(self, "_champ_obj"):
            self.champ = asdict(self._champ_obj)
        CAREER_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        slot_path(self.slot).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, slot: str) -> "Career | None":
        try:
            raw = json.loads(slot_path(slot).read_text(encoding="utf-8"))
            raw["slot"] = slot
            career = cls(**raw)
        except (OSError, ValueError, TypeError):
            return None
        career._fill_seats()
        career._ensure_reliability()
        if career.kind == "team" and not career.sponsor and not career.sponsor_offers:
            career.sponsor_offers = sponsor_offers(career.team_rep)
        if career.kind == "driver" and not career.weekend_goal:
            career._new_weekend_goal()
        return career

    def _fill_seats(self) -> None:
        changed = False
        wanted = {d["name"]: d.get("team", "") for d in load_pool()}
        for team, t in self.teams.items():
            if t.get("own"):
                continue
            seats = 1 if (self.kind == "driver" and team == self.team) else 2
            while len(self.lineup(team)) < seats:
                free = [n for n, d in self.drivers.items() if not d.get("default") and not d["team"]]
                if not free:
                    return
                pick = next((n for n in free if wanted.get(n) == team), None) or \
                    max(free, key=lambda n: self.drivers[n]["rating"])
                self.drivers[pick]["team"] = team
                self.drivers[pick]["years"] = 2
                changed = True
        if changed:
            self.news.insert(0, "Neu: Jedes Team startet jetzt mit zwei Autos - volles Starterfeld wie in der echten F1.")
            self.save()

    @staticmethod
    def delete(slot: str) -> None:
        try:
            slot_path(slot).unlink()
        except OSError:
            pass


__all__ = ["Career", "AREAS", "MAX_LEVEL", "MAX_CREW", "POINTS", "TEAM_COLORS", "crew_stop_time", "upgrade_cost",
           "crew_cost", "load_pool", "team_rank"]
