# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields
from typing import TYPE_CHECKING

from .profiles import DATA_DIR
from .settings import TOP_SPEED

if TYPE_CHECKING:
    from .track import Track

SETUPS_FILE = DATA_DIR / "setups.json"


@dataclass
class SetupFactors:
    grip: float = 1.0
    drag: float = 1.0
    engine: float = 1.0
    rev_limit: float = 9.9
    brake: float = 1.0
    steer_rate: float = 1.0
    turn: float = 1.0
    slip: float = 1.0
    brake_slip: float = 1.0
    brake_turn: float = 1.0
    grass_grip: float = 1.0
    wear: float = 1.0


NEUTRAL = SetupFactors()


@dataclass
class CarSetup:
    wing: int = 0
    balance: int = 0
    gearing: int = 0
    brake_bias: int = 0
    suspension: int = 0
    tyre_pressure: int = 0

    LABELS = {
        "wing": ("Flügel / Abtrieb", "wenig", "viel"),
        "balance": ("Aero-Balance", "Heck", "Front"),
        "gearing": ("Getriebe-Übersetzung", "kurz", "lang"),
        "brake_bias": ("Bremsbalance", "hinten", "vorne"),
        "suspension": ("Federung", "weich", "hart"),
        "tyre_pressure": ("Reifendruck", "niedrig", "hoch"),
    }
    HELP = {
        "wing": "Mehr Flügel = mehr Grip in Kurven, aber mehr Luftwiderstand und weniger Topspeed. "
                "Monza/Silverstone: wenig. Monaco/Marina Bay: viel.",
        "balance": "Richtung Front lenkt das Auto schärfer ein, das Heck wird aber nervöser. "
                   "Richtung Heck: stabil, aber Untersteuern.",
        "gearing": "Kurze Gänge beschleunigen besser, laufen aber im Windschatten/Gerade-Modus in den "
                   "Drehzahlbegrenzer. Lange Gänge: höchster Endspeed, träger aus Kurven.",
        "brake_bias": "Optimal leicht vorne (+1). Zu weit vorne: Untersteuern beim Anbremsen. "
                      "Zu weit hinten: das Heck bricht beim Bremsen aus.",
        "suspension": "Hart = etwas mehr Grip auf glattem Asphalt, aber mehr Reifenverschleiß und "
                      "schlechter neben der Strecke. Weich = reifenschonend.",
        "tyre_pressure": "Niedriger Druck = mehr Grip, aber mehr Verschleiß und minimal weniger Topspeed. "
                         "Hoher Druck schont die Reifen.",
    }

    @classmethod
    def keys(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    def factors(self) -> SetupFactors:
        w, b, g, bb, s, p = self.wing, self.balance, self.gearing, self.brake_bias, self.suspension, self.tyre_pressure
        return SetupFactors(
            grip=(1 + 0.009 * w) * (1 + 0.004 * s) * (1 - 0.006 * p),
            drag=(1 + 0.022 * w) * (1 - 0.003 * p),
            engine=1 - 0.011 * g,
            rev_limit=1.10 + 0.02 * g,
            brake=1 - 0.008 * abs(bb - 1),
            steer_rate=1 + 0.03 * b,
            turn=1 + 0.012 * b,
            slip=1 - 0.045 * b,
            brake_slip=1 + 0.05 * min(0, bb),
            brake_turn=1 - 0.02 * max(0, bb - 1),
            grass_grip=1 - 0.03 * s,
            wear=(1 + 0.025 * s) * (1 - 0.04 * p),
        )

    def clamp(self) -> "CarSetup":
        for k in self.keys():
            setattr(self, k, max(-5, min(5, int(getattr(self, k)))))
        return self


def recommended(track: "Track") -> CarSetup:
    track.ensure_geometry()
    total = sum(1.0 / v for v in track.max_speed)
    slow = sum(1.0 / v for v in track.max_speed if v < TOP_SPEED * 0.8) / total
    wing = round((slow - 0.35) * 45)
    longest = max((((b - a) % track.n) for a, b in track.aero_zones), default=0) * track.WAYPOINT_SPACING
    gearing = 2 if longest > 2000 else 1 if longest > 1200 else 0
    return CarSetup(wing=wing, balance=0, gearing=gearing, brake_bias=1, suspension=0, tyre_pressure=0).clamp()


def predicted(setup: CarSetup, top_speed_kmh: float) -> dict[str, float]:
    f = setup.factors()
    top = min(1.0 / math.sqrt(f.drag), f.rev_limit)
    return {
        "top": top_speed_kmh * top,
        "max": top_speed_kmh * min(1.0 / math.sqrt(f.drag * (1 - 0.23)), f.rev_limit),
        "grip": f.grip,
        "accel": f.engine,
        "brake": f.brake,
        "turn": f.turn * f.steer_rate ** 0.3,
        "stability": f.slip * min(1.0, f.brake_slip),
        "wear": f.wear,
    }


def load_setups() -> dict[str, CarSetup]:
    try:
        raw = json.loads(SETUPS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    known = set(CarSetup.keys())
    for track, values in raw.items():
        out[track] = CarSetup(**{k: v for k, v in values.items() if k in known}).clamp()
    return out


def save_setups(setups: dict[str, CarSetup]) -> None:
    SETUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETUPS_FILE.write_text(json.dumps({k: asdict(v) for k, v in setups.items()}, indent=1), encoding="utf-8")
