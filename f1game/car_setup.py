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
    plank: float = 1.0


NEUTRAL = SetupFactors()


@dataclass
class CarSetup:
    front_wing: int = 0
    rear_wing: int = 0
    gearing: int = 0
    ride_height: int = 0
    suspension: int = 0
    tyre_pressure: int = 0
    fuel: int = 1   # race fuel margin in half laps (not a slider: set in the garage's fuel row)

    LABELS = {
        "front_wing": ("Frontflügel-Winkel", "flach", "steil"),
        "rear_wing": ("Heckflügel-Winkel", "flach", "steil"),
        "gearing": ("Getriebe-Übersetzung", "kurz", "lang"),
        "ride_height": ("Bodenfreiheit", "tief", "hoch"),
        "suspension": ("Federung", "weich", "hart"),
        "tyre_pressure": ("Reifendruck", "niedrig", "hoch"),
    }
    HELP = {
        "front_wing": "Mehr Frontflügel = mehr Grip an der Vorderachse: das Auto lenkt schärfer ein, das Heck "
                      "wird nervöser. Kostet wenig Topspeed. Kann beim Boxenstopp verstellt werden.",
        "rear_wing": "Mehr Heckflügel = mehr Grip und ein stabiles Heck, aber deutlich mehr Luftwiderstand. "
                     "Monza/Spa: flach. Monaco: steil. Front steiler als Heck = Übersteuern, umgekehrt Untersteuern.",
        "gearing": "Kurze Gänge beschleunigen besser, laufen aber im Windschatten/Gerade-Modus in den "
                   "Drehzahlbegrenzer. Lange Gänge: höchster Endspeed, träger aus Kurven.",
        "ride_height": "Tiefer = mehr Abtrieb (Bodeneffekt) und etwas weniger Luftwiderstand, aber die Bodenplatte "
                       "(Planke) schleift stärker. Mehr als 1,0 mm Abrieb nach dem Rennen = Disqualifikation! Die "
                       "Planke wird beim Boxenstopp NICHT getauscht.",
        "suspension": "Hart = etwas mehr Grip auf glattem Asphalt, aber mehr Reifenverschleiß und "
                      "schlechter neben der Strecke. Weich = reifenschonend, setzt aber öfter auf (Planke).",
        "tyre_pressure": "Niedriger Druck = mehr Grip, aber mehr Verschleiß und minimal weniger Topspeed. "
                         "Hoher Druck schont die Reifen.",
    }

    @classmethod
    def keys(cls) -> list[str]:
        return [f.name for f in fields(cls) if f.name != "fuel"]

    @property
    def balance(self) -> float:
        """Aero balance from the wing angles: + = more front wing (oversteer), - = more rear (understeer)."""
        return max(-5.0, min(5.0, (self.front_wing - self.rear_wing) / 2.0))

    def factors(self) -> SetupFactors:
        fw, rw, g, h, s, p = (self.front_wing, self.rear_wing, self.gearing, self.ride_height, self.suspension,
                              self.tyre_pressure)
        b = self.balance
        return SetupFactors(
            grip=(1 + 0.0045 * fw + 0.0045 * rw) * (1 - 0.005 * h) * (1 + 0.004 * s) * (1 - 0.006 * p),
            drag=(1 + 0.007 * fw + 0.015 * rw) * (1 + 0.002 * h) * (1 - 0.003 * p),
            engine=1 - 0.011 * g,
            rev_limit=1.10 + 0.02 * g,
            steer_rate=1 + 0.03 * b,
            turn=1 + 0.012 * b,
            slip=1 - 0.045 * b,
            grass_grip=(1 - 0.03 * s) * (1 + 0.02 * h),
            wear=(1 + 0.025 * s) * (1 - 0.04 * p),
            plank=(1 - 0.16 * h + 0.012 * h * h) * (1 - 0.04 * s),
        )

    def clamp(self) -> "CarSetup":
        for k in self.keys():
            setattr(self, k, max(-5, min(5, int(getattr(self, k)))))
        self.fuel = max(-6, min(6, int(self.fuel)))
        return self

    @classmethod
    def from_dict(cls, values: dict) -> "CarSetup":
        values = dict(values)
        if "wing" in values and "front_wing" not in values:
            # old single wing + aero balance -> separate front/rear wing angles
            w, b = int(values.pop("wing")), int(values.pop("balance", 0))
            values["front_wing"], values["rear_wing"] = w + b, w - b
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in values.items() if k in known}).clamp()


def recommended(track: "Track") -> CarSetup:
    track.ensure_geometry()
    total = sum(1.0 / v for v in track.max_speed)
    slow = sum(1.0 / v for v in track.max_speed if v < TOP_SPEED * 0.8) / total
    wing = round((slow - 0.35) * 45)
    longest = max((((b - a) % track.n) for a, b in track.aero_zones), default=0) * track.WAYPOINT_SPACING
    gearing = 2 if longest > 2000 else 1 if longest > 1200 else 0
    return CarSetup(front_wing=wing, rear_wing=wing, gearing=gearing, ride_height=0, suspension=0,
                    tyre_pressure=0, fuel=1).clamp()


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
        "plank": f.plank,
    }


def load_setups() -> dict[str, CarSetup]:
    try:
        raw = json.loads(SETUPS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {track: CarSetup.from_dict(values) for track, values in raw.items() if isinstance(values, dict)}


def save_setups(setups: dict[str, CarSetup]) -> None:
    SETUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETUPS_FILE.write_text(json.dumps({k: asdict(v) for k, v in setups.items()}, indent=1), encoding="utf-8")
