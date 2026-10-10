# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any

from .career_events import (DRIVER_PRESS, TEAM_PRESS, base_reliability, goal_met, make_weekend_goal,
                            pick_press, sponsor_offers, sponsor_payout)
from .career_achievements import ACHIEVEMENTS, make_rookie, newly_unlocked
from .career_plus import (ACADEMY_FEE, ACADEMY_SLOTS, ACADEMY_UPKEEP, BOARD_START, JUNIOR_MAX_AGE, MAX_SKILL,
                          NEXT_YEAR_FACTOR, SKILL_COST, SKILLS, STAFF_ROLES, board_label, race_xp, staff_candidates,
                          staff_rep_needed)
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
PERSONAL: dict[str, tuple[str, str]] = {
    "manager": ("Manager", "Bessere Vertragsangebote: +6 % Gehalt und mehr Verhandlungsspielraum je Stufe"),
    "pr": ("PR-Berater", "+0.4 Ruf nach jedem Rennen je Stufe"),
    "coach": ("Mentaltrainer", "+0.5 Vertrauen pro Rennen, verfehlte Wochenendziele kosten weniger Vertrauen"),
}
PERSONAL_COST = [1.5, 3.0, 5.0]
REBRAND_COST = 2.0
NATIONALITIES = ["", "DE", "AT", "CH", "GB", "IE", "FR", "BE", "NL", "IT", "ES", "PT", "MC", "DK", "SE", "NO", "FI",
                 "PL", "CZ", "US", "CA", "MX", "BR", "AR", "AU", "NZ", "JP", "CN", "AE", "ZA"]
HELMET_COLORS: list[tuple[int, int, int]] = [(0, 230, 255), (255, 255, 255), (255, 210, 0), (255, 60, 60),
                                             (60, 220, 90), (255, 120, 200), (150, 90, 255), (255, 140, 30),
                                             (30, 30, 34), (120, 200, 255)]
MAX_POOL = 70


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
    player_short: str = ""
    player_number: int = 0
    player_nationality: str = ""
    helmet: list[int] = field(default_factory=lambda: [0, 230, 255])
    personal: dict[str, int] = field(default_factory=lambda: {k: 0 for k in PERSONAL})
    achievements: dict[str, int] = field(default_factory=dict)
    new_achievements: list[str] = field(default_factory=list)
    race_log: list[dict[str, Any]] = field(default_factory=list)
    xp: int = 0
    skills: dict[str, int] = field(default_factory=lambda: {k: 0 for k in SKILLS})
    interest: list[str] = field(default_factory=list)       # teams that want you (driver career, from mid-season)
    staff: dict[str, dict[str, Any]] = field(default_factory=dict)
    staff_offers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    board: float = BOARD_START
    dev_focus: str = "now"                                   # "now" or "next" (next season's car)
    next_year: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, slot: str, kind: str, player_name: str, difficulty: str, laps: int, fmt: str, teams: list[Team],
               team_name: str = "", team_color: tuple[int, int, int] = (255, 0, 140),
               player_drives: bool = True, short: str = "", number: int = 0, nationality: str = "",
               helmet: tuple[int, int, int] = (0, 230, 255)) -> "Career":
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
                     slot=slot, player_short=short.strip().upper()[:3], player_number=number,
                     player_nationality=nationality, helmet=list(helmet))
        if kind == "team":
            name = team_name.strip() or f"{player_name} Racing"
            career.teams[name] = {"color": list(team_color), **NEW_TEAM_BASE, "own": True}
            career.team = name
            career.staff_offers = staff_candidates(career.team_rep, set())
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
                           "points": 0, "goals_met": 0, "goals": 0, "failures": 0, "mate_q_ahead": 0,
                           "mate_q_behind": 0, "xp": 0}
        self.interest = []
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
        prof = player_profile(self.team_obj(self.team), self.player_name)
        return replace(prof, rating=0, short=self.player_short or prof.short, helmet=tuple(self.helmet),
                       number=self.player_number, tyre_mgmt=1.0 - 0.05 * self.skills.get("tyres", 0))

    def player_skills(self) -> dict[str, int]:
        return {k: v for k, v in self.skills.items() if v} if self.player_drives else {}

    def skill_cost(self, key: str) -> int | None:
        lvl = self.skills.get(key, 0)
        return SKILL_COST[lvl] if lvl < MAX_SKILL else None

    def buy_skill(self, key: str) -> str:
        cost = self.skill_cost(key)
        if cost is None:
            return f"{SKILLS[key][0]} bereits auf Maximalstufe"
        if self.xp < cost:
            return f"Zu wenig XP ({cost} nötig, du hast {self.xp})"
        self.xp -= cost
        self.skills[key] = self.skills.get(key, 0) + 1
        self.news.insert(0, f"Neue Fähigkeit: {SKILLS[key][0]} Stufe {self.skills[key]}")
        self.save()
        return f"{SKILLS[key][0]} Stufe {self.skills[key]}"

    # ------------------------------------------------------------------ staff (team career)
    def staff_stars(self, role: str) -> int:
        return int(self.staff.get(role, {}).get("stars", 0)) if self.kind == "team" else 0

    def hire_staff(self, role: str, index: int) -> str:
        offers = self.staff_offers.get(role, [])
        if not 0 <= index < len(offers):
            return ""
        cand = offers[index]
        need = staff_rep_needed(cand["stars"])
        if self.team_rep < need:
            return f"{cand['name']} will nicht: Teamruf {need:.0f} nötig (hast {self.team_rep:.0f})"
        fee = cand["salary"] * 0.5
        if self.budget < fee:
            return f"Zu wenig Budget für die Ablöse ({fee:.1f} Mio)"
        self.budget -= fee
        self.season_log["expenses"] = self.season_log.get("expenses", 0.0) + fee
        old = self.staff.get(role)
        self.staff[role] = dict(cand)
        offers.pop(index)
        if old:
            offers.append(old)
        title = STAFF_ROLES[role][0]
        self.news.insert(0, f"Neuer {title}: {cand['name']} ({cand['stars']} Sterne, {cand['salary']:.1f} Mio/Saison)")
        self.save()
        return f"{cand['name']} ist dein {title}"

    def staff_salaries(self) -> float:
        return sum(p.get("salary", 0.0) for p in self.staff.values()) if self.kind == "team" else 0.0

    # ------------------------------------------------------------------ junior academy (team career)
    def juniors(self) -> list[str]:
        return [n for n, d in self.drivers.items() if d.get("junior") == self.team and not d["team"]]

    def academy_candidates(self) -> list[str]:
        free = [n for n, d in self.drivers.items() if not d["team"] and not d.get("default") and not d.get("junior")
                and d.get("age", 30) <= JUNIOR_MAX_AGE]
        return sorted(free, key=lambda n: -(self.drivers[n].get("potential", 0) * 2 + self.drivers[n]["rating"]))[:6]

    def sign_junior(self, name: str) -> str:
        if len(self.juniors()) >= ACADEMY_SLOTS:
            return f"Die Akademie ist voll ({ACADEMY_SLOTS} Plätze)"
        if self.budget < ACADEMY_FEE:
            return f"Zu wenig Budget ({ACADEMY_FEE:.1f} Mio)"
        self.budget -= ACADEMY_FEE
        self.season_log["expenses"] = self.season_log.get("expenses", 0.0) + ACADEMY_FEE
        self.drivers[name]["junior"] = self.team
        self.news.insert(0, f"Akademie: {name} ({self.drivers[name]['age']} J., Potenzial "
                            f"{self.drivers[name].get('potential', 0)}) gehört jetzt zu deinem Nachwuchs")
        self.save()
        return f"{name} in der Akademie"

    def release_junior(self, name: str) -> str:
        self.drivers[name].pop("junior", None)
        self.news.insert(0, f"Akademie: {name} verlässt den Nachwuchs")
        self.save()
        return f"{name} entlassen"

    def _academy_after_race(self) -> list[str]:
        notes = []
        eng = self.staff_stars("eng")
        for name in self.juniors():
            d = self.drivers[name]
            if d["rating"] < max(d.get("potential", 0), d["rating"]) and random.random() < 0.22 + 0.05 * eng:
                d["rating"] += 1
                notes.append(f"Akademie: {name} macht Fortschritte (Wertung {d['rating']}).")
        return notes

    @property
    def short_code(self) -> str:
        return self.player_short or "".join(ch for ch in self.player_name.upper() if ch.isalpha())[:3] or "YOU"

    def pit_stop_times(self) -> dict[str, float]:
        if self.kind != "team":
            return {}
        return {self.team: crew_stop_time(self.crew) - 0.05 * self.staff_stars("mech")}

    def slow_stop_chances(self) -> dict[str, float]:
        """A better chief mechanic botches fewer stops (base 6 %)."""
        return {self.team: 0.06 * (1.0 - 0.15 * self.staff_stars("mech"))} if self.kind == "team" else {}

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
            me = self.quali_pos - 1
            log = self.season_log
            for mate in (self.lineup(self.team) if self.team else []):
                if mate in order:
                    key = "mate_q_ahead" if me < order.index(mate) else "mate_q_behind"
                    log[key] = log.get(key, 0) + 1

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
        goals_before = log.get("goals_met", 0)
        if self.kind == "driver":
            notes += self._driver_after_race(rows, names)
            notes += self._transfer_rumours()
        else:
            notes += self._team_after_race(rows)
        if self.player_drives and self.player_name in names:
            k = names.index(self.player_name)
            mates = [j for j, r in enumerate(rows) if r["team"] == self.team and j != k]
            rival_k = names.index(self.rival) if self.rival in names else None
            gained = race_xp(k + 1, rows[k]["dnf"], rows[k]["points"], bool(mates) and all(k < j for j in mates),
                             rival_k is not None and k < rival_k, log.get("goals_met", 0) > goals_before)
            self.xp += gained
            log["xp"] = log.get("xp", 0) + gained
            notes.append(f"+{gained} XP für deine Fähigkeiten (jetzt {self.xp} XP).")
        notes += self._ai_development()
        self._log_race(rows, names, track)
        self._make_press(rows, names)
        self.news = (notes + self.news)[:16]
        log["races"] = log.get("races", 0) + 1
        if self.kind == "driver":
            self._new_weekend_goal()
        self._champ_saved()
        return notes

    def _log_race(self, rows: list[dict[str, Any]], names: list[str], track: str) -> None:
        if self.player_drives and self.player_name in names:
            k = names.index(self.player_name)
            pos, dnf, pts = k + 1, rows[k]["dnf"], rows[k]["points"]
        else:
            ours = [k for k, r in enumerate(rows) if r["team"] == self.team]
            if not ours:
                return
            finished = [k for k in ours if not rows[k]["dnf"]]
            best = min(finished) if finished else min(ours)
            pos, dnf, pts = best + 1, not finished, sum(rows[k]["points"] for k in ours)
        self.race_log.append({"s": self.season, "r": len(self.championship.results), "track": track, "pos": pos,
                              "dnf": bool(dnf), "pts": pts, "q": self.quali_pos, "team": self.team})
        self.race_log = self.race_log[-400:]
        self.quali_pos = 0

    def form(self, n: int = 5) -> list[dict[str, Any]]:
        return self.race_log[-n:]

    def _transfer_rumours(self) -> list[str]:
        """From mid-season, stronger teams take notice when your reputation is good enough."""
        champ = self.championship
        if not self.team or len(champ.results) < max(1, len(champ.rounds) // 2):
            return []
        ranking = self.team_ranking()
        n = len(ranking)
        mine = ranking.index(self.team)
        notes = []
        for k, team in enumerate(ranking[:mine]):
            if team in self.interest:
                continue
            if self.reputation + random.uniform(-4, 8) >= 85 - 70 * k / max(1, n - 1) and random.random() < 0.35:
                self.interest.append(team)
                notes.append(f"Gerücht: {team} ist an dir interessiert - ein Angebot zum Saisonende ist sicher.")
                break
        return notes

    def _driver_after_race(self, rows: list[dict[str, Any]], names: list[str]) -> list[str]:
        notes = []
        log = self.season_log
        me = names.index(self.player_name) if self.player_name in names else None
        if me is None:
            return notes
        row = rows[me]
        rep = row["points"] / 4.0 - 0.4 - (2.0 if row["dnf"] else 0.0) + 0.4 * self.personal.get("pr", 0)
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
        coach = self.personal.get("coach", 0)
        trust = (1.0 if any(me < k for k in mates) else 0.0) - (1.5 if row["dnf"] and not row.get("failure") else 0.0) \
            + 0.5 * coach
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
                trust -= max(1.0, 4.0 - coach)
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
        rounds = len(self.championship.rounds)
        staff = self.staff_salaries() / rounds + ACADEMY_UPKEEP * len(self.juniors()) / rounds
        costs = salaries + OPERATIONS_PER_RACE + upkeep + staff
        notes += self._progress_projects()
        notes += self._academy_after_race()
        sim = self.facilities.get("simulator", 0)
        grow = 0.15 * sim + 0.06 * self.staff_stars("eng")
        for name in self.own_drivers():
            d = self.drivers[name]
            if grow and random.random() < grow and d["rating"] < max(d.get("potential", 0), d["rating"]) + 2:
                d["rating"] += 1
                notes.append(f"Simulator-Arbeit zahlt sich aus: {name} jetzt Wertung {d['rating']}.")
        self.budget += sponsor + prize - costs
        log["income"] += sponsor + prize
        log["expenses"] += costs
        self.team_rep = max(0.0, min(100.0, self.team_rep + points / 6.0 - 0.3))
        # the board judges every weekend against the season goal
        pos, goal = self.team_pos(), self.team_goal()
        mood = (2.0 if pos is not None and pos <= goal else -2.0) + 2.5 * podiums + (1.0 if points else -0.5) \
            - 1.5 * sum(1 for k in ours if rows[k].get("failure"))
        old = board_label(self.board)
        self.board = max(0.0, min(100.0, self.board + mood))
        if board_label(self.board) != old:
            notes.append(f"Vorstand jetzt {board_label(self.board)} ({self.board:.0f}/100).")
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
        return min(0.98, 0.8 + 0.06 * self.facilities.get("windtunnel", 0) + 0.025 * self.staff_stars("td"))

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
        nxt = self.dev_focus == "next"
        self.projects.append({"area": area, "races_left": races, "cost": cost, "next": nxt})
        name = AREAS[area][0] if area in AREAS else "Zuverlässigkeit"
        self.news.insert(0, f"Projekt gestartet: {name} Stufe {self.area_level(area) + 1} (fertig in {races} Rd.)"
                         + (" - für das Auto der nächsten Saison" if nxt else ""))
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
            share = (1.0 if ok else 0.5) * (1.0 + 0.06 * self.staff_stars("td"))
            if p.get("next"):
                # goes into next season's car: worth more, but only from the first race of the new season
                self.next_year.append({"area": area, "share": share * NEXT_YEAR_FACTOR})
                self.upgrades[area] = self.area_level(area) + 1
                name = AREAS[area][0] if area in AREAS else "Zuverlässigkeit"
                notes.append(f"Fertig fürs nächste Jahr: {name} Stufe {self.upgrades[area]}" +
                             ("" if ok else " - enttäuschend, weniger Wirkung."))
                continue
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

    def _apply_part(self, area: str, share: float) -> None:
        if area == "reliability":
            t = self.teams[self.team]
            t["reliability"] = round(min(0.995, t.get("reliability", 0.965) + RELIABILITY_STEP * share), 4)
        else:
            _name, key, step = AREAS[area]
            self.teams[self.team][key] = round(self.teams[self.team][key] + step * share, 4)

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
        junior = d.get("junior") == self.team
        if not junior and self.team_rep < self.required_rep(name):
            return f"{name} will nicht: dein Team braucht Ruf {self.required_rep(name):.0f} (hat {self.team_rep:.0f})"
        fee = 0.0 if junior else d["salary"] * 0.5
        if self.budget < fee:
            return f"Zu wenig Budget für die Ablöse ({fee:.1f} Mio)"
        self.budget -= fee
        self.season_log["expenses"] = self.season_log.get("expenses", 0.0) + fee
        d["team"] = self.team
        d["years"] = years
        d.pop("junior", None)
        if junior:
            self.news.insert(0, f"Aus der eigenen Akademie befördert: {name} ({years} J., {d['salary']:.1f} Mio/Saison)")
        else:
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
            candidates += [t for t in self.interest if t in ranking and t not in candidates]
            if not candidates:
                candidates = ranking[-1:]
        for team in candidates:
            rank = ranking.index(team) + 1
            manager = self.personal.get("manager", 0)
            salary = round((0.6 + (n - rank) * 0.9 + self.reputation / 25) * (1.0 + 0.06 * manager), 1)
            goal = max(2, min(20, round(rank * 1.6) + 2))
            limit = 1.0 + self.reputation / 250 + (self.trust / 400 if team == self.team else 0.0) + \
                random.uniform(0.0, 0.15) + 0.04 * manager
            keen = team in self.interest
            offers.append({"team": team, "salary": round(salary * (1.1 if keen else 1.0), 1),
                           "years": random.choice([1, 2, 2, 3]), "goal": goal, "rank": rank,
                           "limit": round(limit + (0.05 if keen else 0.0), 3), "keen": keen})
        offers.sort(key=lambda o: (not o.get("keen"), o["rank"]))
        offers = offers[:5]
        offers.sort(key=lambda o: o["rank"])
        return offers

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
            self.board = max(0.0, min(100.0, self.board + (15 if review["goal_met"] else -20)))
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
        notes += self._retirements_and_rookies()
        for team, t in self.teams.items():
            if t.get("own"):
                continue
            for key in ("engine", "aero", "top_speed", "brakes"):
                t[key] = round(max(0.95, min(1.06, t[key] + random.gauss(0.002, 0.006))), 4)
        if self.kind == "team":
            notes += self._team_new_season()
        best = max(self.teams, key=lambda t: self.team_obj(t).rating if not self.teams[t].get("own") else 0)
        notes.append(f"Wintertests: {best} gilt als Favorit für Saison {self.season + 1}.")
        self.season += 1
        self._new_championship()
        self.news = (notes + [f"Saison {self.season} beginnt!"] + self.news)[:14]
        self.save()
        return notes

    def _team_new_season(self) -> list[str]:
        notes = []
        if self.next_year:
            for part in self.next_year:
                self._apply_part(part["area"], part["share"])
            notes.append(f"Neues Auto: {len(self.next_year)} Teile aus der Vorjahresentwicklung sind eingebaut.")
            self.next_year = []
        if self.board >= 70:
            bonus = round((self.board - 50) * 0.2, 1)
            self.budget += bonus
            notes.append(f"Der Vorstand ist {board_label(self.board)}: +{bonus:.1f} Mio Zusatzbudget.")
        elif self.board < 30:
            cut = round((30 - self.board) * 0.3, 1)
            self.budget -= cut
            notes.append(f"Der Vorstand kürzt das Budget um {cut:.1f} Mio - Ergebnisse müssen her!")
            if self.board < 12 and self.staff:
                role = max(self.staff, key=lambda r: self.staff[r].get("salary", 0))
                gone = self.staff.pop(role)
                notes.append(f"Der Vorstand entlässt {gone['name']} ({STAFF_ROLES[role][0]}).")
            self.board = max(self.board, 25.0)
        taken = {p["name"] for p in self.staff.values()}
        self.staff_offers = staff_candidates(self.team_rep, taken)
        for name in self.juniors():
            if self.drivers[name].get("age", 0) > JUNIOR_MAX_AGE + 2:
                self.drivers[name].pop("junior", None)
                notes.append(f"Akademie: {name} ist zu alt für den Nachwuchs und sucht sich ein Cockpit.")
        return notes

    def _retirements_and_rookies(self) -> list[str]:
        notes = []
        mine = set(self.own_drivers()) if self.kind == "team" else set()
        retired = []
        for name, d in list(self.drivers.items()):
            if d.get("default") or name in mine or d["age"] < 37:
                continue
            if random.random() < 0.15 * (d["age"] - 36):
                retired.append(name)
                del self.drivers[name]
        if retired:
            notes.append("Karriereende: " + ", ".join(retired[:4]) + (" ..." if len(retired) > 4 else "")
                         + " treten zurück." if len(retired) > 1 else f"Karriereende: {retired[0]} tritt zurück.")
        free_pool = sum(1 for d in self.drivers.values() if not d.get("default"))
        count = max(2, min(4, len(retired) + 1)) if free_pool < MAX_POOL else 0
        names = set(self.drivers) | {self.player_name}
        shorts = {d["short"] for d in self.drivers.values()} | {self.short_code}
        rookies = []
        for _ in range(count):
            r = make_rookie(names, shorts)
            name = r.pop("name")
            names.add(name)
            shorts.add(r["short"])
            self.drivers[name] = r
            rookies.append(f"{name} ({r['nationality']}, {r['age']} J., Potenzial {r['potential']})")
        if rookies:
            notes.append("Neue Talente im Fahrermarkt: " + ", ".join(rookies))
        self._fill_seats(announce=False)
        return notes

    def buy_personal(self, key: str) -> str:
        level = self.personal.get(key, 0)
        if level >= len(PERSONAL_COST):
            return f"{PERSONAL[key][0]} bereits auf Maximalstufe"
        cost = PERSONAL_COST[level]
        if self.bank < cost:
            return f"Zu wenig Geld auf dem Konto ({cost:.1f} Mio nötig)"
        self.bank -= cost
        self.personal[key] = level + 1
        self.news.insert(0, f"Investition: {PERSONAL[key][0]} Stufe {level + 1} (-{cost:.1f} Mio)")
        self.save()
        return f"{PERSONAL[key][0]} Stufe {level + 1}"

    def check_achievements(self) -> list[str]:
        new = newly_unlocked(self)
        for key in new:
            self.achievements[key] = self.season
            self.new_achievements.append(key)
            self.news.insert(0, f"ERFOLG FREIGESCHALTET: {ACHIEVEMENTS[key][1]} - {ACHIEVEMENTS[key][2]}")
        return new

    def set_options(self, laps: int, difficulty: str, fmt: str) -> None:
        self.laps, self.difficulty, self.format = laps, difficulty, fmt
        champ = self.championship
        champ.laps, champ.difficulty, champ.format = laps, difficulty, fmt
        if self.kind == "driver":
            self._new_weekend_goal()
        self._champ_saved()

    def set_identity(self, short: str, number: int, nationality: str, helmet: tuple[int, int, int]) -> None:
        self.player_short = short.strip().upper()[:3]
        self.player_number = max(0, min(99, number))
        self.player_nationality = nationality
        self.helmet = [int(v) for v in helmet]

    def _rewrite(self, key: str, old: str, new: str) -> None:
        for res in self.championship.results:
            for row in res["rows"]:
                if row.get(key) == old:
                    row[key] = new
        title_key = "champion" if key == "name" else "team_champion"
        for h in self.history:
            for table in ("driver_table", "team_table"):
                for e in h.get(table, []):
                    if e.get(key) == old:
                        e[key] = new
            if h.get(title_key) == old:
                h[title_key] = new
            if key == "team" and h.get("team") == old:
                h["team"] = new

    def rename_player(self, name: str) -> str:
        name = name.strip()
        if not name or name == self.player_name:
            return ""
        if name in self.drivers or name in self.teams:
            return "Dieser Name ist schon vergeben"
        old = self.player_name
        self._rewrite("name", old, name)
        self.player_name = name
        self.championship.player_name = name
        self.news.insert(0, f"{old} tritt ab sofort als {name} an.")
        self._champ_saved()
        return f"Name geändert: {name}"

    def rename_team(self, name: str) -> str:
        name = name.strip()
        if self.kind != "team" or not name or name == self.team:
            return ""
        if name in self.teams or name in self.drivers:
            return "Diesen Namen gibt es schon"
        if self.budget < REBRAND_COST:
            return f"Rebranding kostet {REBRAND_COST:.0f} Mio - zu wenig Budget"
        old = self.team
        self.budget -= REBRAND_COST
        self.season_log["expenses"] = self.season_log.get("expenses", 0.0) + REBRAND_COST
        self.teams = {(name if k == old else k): v for k, v in self.teams.items()}
        for d in self.drivers.values():
            if d["team"] == old:
                d["team"] = name
        for e in self.race_log:
            if e.get("team") == old:
                e["team"] = name
        self._rewrite("team", old, name)
        self.team = name
        self.championship.team = name
        self.news.insert(0, f"Rebranding: {old} heißt jetzt {name} (-{REBRAND_COST:.0f} Mio)")
        self._champ_saved()
        return f"Team heißt jetzt {name}"

    def save(self) -> None:
        self.check_achievements()
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
        for d in career.drivers.values():
            d["short"] = d["short"].strip(" :")
        career._fill_seats()
        career._ensure_reliability()
        if career.kind == "team" and not career.sponsor and not career.sponsor_offers:
            career.sponsor_offers = sponsor_offers(career.team_rep)
        if career.kind == "driver" and not career.weekend_goal:
            career._new_weekend_goal()
        if career.kind == "team" and not career.staff_offers:
            career.staff_offers = staff_candidates(career.team_rep, {p["name"] for p in career.staff.values()})
        for k in SKILLS:
            career.skills.setdefault(k, 0)
        return career

    def _fill_seats(self, announce: bool = True) -> None:
        changed = False
        wanted = {d["name"]: d.get("team", "") for d in load_pool()}
        for team, t in self.teams.items():
            if t.get("own"):
                continue
            seats = 1 if (self.kind == "driver" and team == self.team) else 2
            while len(self.lineup(team)) < seats:
                free = [n for n, d in self.drivers.items() if not d.get("default") and not d["team"]
                        and not d.get("junior")]
                if not free:
                    return
                pick = next((n for n in free if wanted.get(n) == team), None) or \
                    max(free, key=lambda n: self.drivers[n]["rating"])
                self.drivers[pick]["team"] = team
                self.drivers[pick]["years"] = 2
                changed = True
        if changed and announce:
            self.news.insert(0, "Neu: Jedes Team startet jetzt mit zwei Autos - volles Starterfeld wie in der echten F1.")
            self.save()

    @staticmethod
    def delete(slot: str) -> None:
        try:
            slot_path(slot).unlink()
        except OSError:
            pass


__all__ = ["Career", "AREAS", "PERSONAL", "PERSONAL_COST", "NATIONALITIES", "HELMET_COLORS", "REBRAND_COST", "MAX_LEVEL", "MAX_CREW", "POINTS", "TEAM_COLORS", "crew_stop_time", "upgrade_cost",
           "crew_cost", "load_pool", "team_rank"]
