# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from .profiles import DATA_DIR

SETTINGS_FILE = DATA_DIR / "settings.json"

DAMAGE_MODES = {"off": "Aus", "on": "An", "dnf": "An + Ausfälle"}
TYRE_WEAR_MODES = {"off": ("Aus", 0.0), "normal": ("Normal", 1.0), "double": ("Doppelt", 2.0)}
ASSIST_NAMES = ["Aus", "Mittel (Stabilität + Bremslinie)", "Voll (+ automatische Bremshilfe)"]
UNITS = {"kmh": ("km/h", 1.0), "mph": ("mph", 0.621371)}
FPS_OPTIONS = [30, 60, 120, 144]
EFFECT_LEVELS = {"off": "Aus", "low": "Niedrig", "high": "Hoch"}


def speed_in(kmh: float, units: str) -> tuple[float, str]:
    label, factor = UNITS.get(units, UNITS["kmh"])
    return kmh * factor, label


@dataclass
class UserSettings:
    player_name: str = "Du (Spieler)"
    assists: int = 1
    view3d: bool = False
    damage: str = "on"
    tyre_wear: str = "normal"
    auto_camera: bool = True
    show_fps: bool = False
    fullscreen: bool = False
    sound: str = "normal"
    safety_car: bool = True
    language: str = "en"
    units: str = "kmh"
    fps: int = 60
    effects: str = "high"

    @property
    def tyre_wear_factor(self) -> float:
        return TYRE_WEAR_MODES[self.tyre_wear][1]

    @classmethod
    def load(cls) -> "UserSettings":
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        settings = cls(**{k: v for k, v in raw.items() if k in known})
        if settings.damage not in DAMAGE_MODES:
            settings.damage = "on"
        if settings.tyre_wear not in TYRE_WEAR_MODES:
            settings.tyre_wear = "normal"
        if settings.sound not in ("off", "low", "normal", "high"):
            settings.sound = "normal"
        if settings.language not in ("en", "de"):
            settings.language = "en"
        if settings.units not in UNITS:
            settings.units = "kmh"
        if settings.effects not in EFFECT_LEVELS:
            settings.effects = "high"
        if settings.fps not in FPS_OPTIONS:
            settings.fps = 60
        settings.assists = max(0, min(2, int(settings.assists)))
        return settings

    def save(self) -> None:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
