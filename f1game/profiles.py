# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .neural import NeuralNetwork
from .settings import Color

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BRAIN_DIR = DATA_DIR / "brains"
RECORDING_DIR = DATA_DIR / "recordings"
LEGACY_DRIVERS_FILE = DATA_DIR / "drivers.json"
TEAMS_FILE = DATA_DIR / "teams.json"
POOL_FILE = DATA_DIR / "driver_pool.json"


def rating_to_pace(rating: int) -> float:
    return 0.966 + 0.034 * max(0.0, min(1.0, (rating - 60) / 32))


DEFAULT_RATING = {"final": 90, "mid": 84, "early": 78}
TEAM_SPREAD = 2.0
SKILL_GRIP_SHARE = 0.6


def driver_grip(pace: float) -> float:
    return 1.0 - (1.0 - pace) * SKILL_GRIP_SHARE


def amplified(team: "Team") -> "Team":
    def amp(v: float) -> float:
        return 1.0 + (v - 1.0) * TEAM_SPREAD
    return replace(team, engine=amp(team.engine), aero=amp(team.aero), top_speed=amp(team.top_speed),
                   brakes=amp(team.brakes), tyre_wear=amp(team.tyre_wear))


def rating_to_checkpoint(rating: int) -> str:
    return "final" if rating >= 84 else "mid" if rating >= 72 else "early"


@dataclass(frozen=True)
class Team:
    name: str
    color: Color = (200, 200, 200)
    engine: float = 1.0
    aero: float = 1.0
    top_speed: float = 1.0
    brakes: float = 1.0
    tyre_wear: float = 1.0

    @property
    def rating(self) -> float:
        return (self.engine + self.aero + self.top_speed + self.brakes + (2.0 - self.tyre_wear)) / 5.0


REFERENCE_TEAM = Team("Referenz")


def load_teams() -> list[Team]:
    raw: list[dict[str, Any]] = json.loads(TEAMS_FILE.read_text(encoding="utf-8")) if TEAMS_FILE.exists() else []
    return [Team(d["name"], tuple(d.get("color", (200, 200, 200))),
                 float(d.get("engine", 1.0)), float(d.get("aero", 1.0)), float(d.get("top_speed", 1.0)),
                 float(d.get("brakes", 1.0)), float(d.get("tyre_wear", 1.0))) for d in raw]


@dataclass(frozen=True)
class DriverProfile:
    name: str
    short: str
    team: str
    color: Color
    helmet: Color
    brain: str = "balanced"
    checkpoint: str = "final"
    car: Team = field(default=REFERENCE_TEAM)
    pace: float = 1.0
    tyre_mgmt: float = 1.0
    rating: int = 0
    pool: bool = False


PLAYER_PROFILE = DriverProfile("Du (Spieler)", "YOU", "Player Racing", (0, 215, 255), (0, 230, 255))
AUTOPILOT_BRAIN = "balanced"


def player_profile(team: Team | None, name: str | None = None) -> DriverProfile:
    prof = PLAYER_PROFILE if not name else replace(PLAYER_PROFILE, name=name)
    if team is None:
        return prof
    return replace(prof, team=team.name, color=team.color, car=team)


POOL_KEYS = ["name", "short", "team", "fixed", "nationality", "age", "rating", "potential", "style", "checkpoint",
             "tyre_mgmt", "salary", "color", "helmet"]


def save_pool(pool: list[dict[str, Any]]) -> None:
    lines = []
    for d in pool:
        entry = {k: d[k] for k in POOL_KEYS if k in d and d[k] is not None}
        entry.update({k: v for k, v in d.items() if k not in POOL_KEYS})
        lines.append("  " + json.dumps(entry, ensure_ascii=False))
    POOL_FILE.write_text("[\n" + ",\n".join(lines) + "\n]\n", encoding="utf-8")


def merge_legacy_drivers() -> None:
    if not LEGACY_DRIVERS_FILE.exists():
        return
    try:
        legacy = json.loads(LEGACY_DRIVERS_FILE.read_text(encoding="utf-8"))
        pool = json.loads(POOL_FILE.read_text(encoding="utf-8")) if POOL_FILE.exists() else []
    except (OSError, ValueError):
        return
    known = {d["name"] for d in pool}
    merged = []
    for d in legacy:
        if d["name"] in known:
            continue
        cp = str(d.get("checkpoint", "final"))
        rating = int(d.get("rating", DEFAULT_RATING.get(cp, 84)))
        merged.append({"name": d["name"], "short": d["short"], "team": d.get("team", ""), "fixed": True,
                       "nationality": d.get("nationality", ""), "age": int(d.get("age", 28)), "rating": rating,
                       "potential": rating, "style": d.get("brain", "balanced"), "checkpoint": cp,
                       "tyre_mgmt": 1.0, "salary": round(0.3 + ((rating - 60) / 32) ** 2 * 14, 1),
                       "color": d.get("color"), "helmet": d.get("helmet", [255, 255, 255])})
    for d in pool:
        d.setdefault("fixed", False)
    save_pool(merged + pool)
    LEGACY_DRIVERS_FILE.unlink()


def load_pool() -> list[dict[str, Any]]:
    merge_legacy_drivers()
    try:
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def load_drivers(library: "BrainLibrary", teams: list[Team] | None = None) -> list[DriverProfile]:
    by_name = {t.name: t for t in (teams if teams is not None else load_teams())}
    pool = [d for d in load_pool() if d.get("team") in by_name]
    pool.sort(key=lambda d: not d.get("fixed", False))
    drivers = []
    for d in pool:
        team = by_name[d["team"]]
        r = int(d.get("rating", 75))
        color = tuple(d["color"]) if d.get("color") else team.color
        drivers.append(DriverProfile(d["name"], d["short"], team.name, color,
                                     tuple(d.get("helmet", (255, 255, 255))),
                                     d.get("style", "balanced"), str(d.get("checkpoint") or rating_to_checkpoint(r)),
                                     team, rating_to_pace(r), float(d.get("tyre_mgmt", 1.0)), r,
                                     not d.get("fixed", False)))
    drivers = [d for d in drivers if library.has(d.brain)]
    if library.has("clone") and not any(d.brain == "clone" for d in drivers):
        drivers.insert(0, DriverProfile("Dein KI-Klon", "CLN", "Trained on You", (255, 0, 200), (0, 230, 255),
                                        "clone", "final"))
    return drivers


class BrainLibrary:

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def reload(self) -> None:
        self._cache.clear()

    def has(self, style: str) -> bool:
        return (BRAIN_DIR / f"{style}.json").exists()

    def data(self, style: str) -> dict[str, Any] | None:
        if style not in self._cache:
            path = BRAIN_DIR / f"{style}.json"
            if not path.exists():
                return None
            self._cache[style] = json.loads(path.read_text(encoding="utf-8"))
        return self._cache[style]

    def checkpoint(self, style: str, label: str = "final") -> dict[str, Any] | None:
        data = self.data(style)
        if not data or not data.get("checkpoints"):
            return None
        for cp in data["checkpoints"]:
            if cp["label"] == label:
                return cp
        return data["checkpoints"][-1]

    def network(self, style: str, label: str = "final") -> NeuralNetwork:
        cp = self.checkpoint(style, label) or self.checkpoint("base", label)
        if cp is None:
            raise FileNotFoundError("Keine trainierten KI-Gehirne gefunden - bitte zuerst 'python train.py all' "
                                    "ausführen oder im Menü 'KI-Training' starten.")
        return NeuralNetwork.from_dict(cp["network"])

    def save(self, style: str, data: dict[str, Any]) -> Path:
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        path = BRAIN_DIR / f"{style}.json"
        if path.exists():
            path.replace(BRAIN_DIR / f"{style}.backup.json")
        path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        self._cache[style] = data
        return path


def recording_stats() -> tuple[int, int]:
    if not RECORDING_DIR.exists():
        return 0, 0
    files = list(RECORDING_DIR.glob("*.json"))
    samples = 0
    for f in files:
        try:
            samples += len(json.loads(f.read_text(encoding="utf-8")).get("samples", []))
        except (OSError, ValueError):
            pass
    return len(files), samples
