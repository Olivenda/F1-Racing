# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

from dataclasses import dataclass

from .settings import Color
from .utils import clamp


@dataclass(frozen=True)
class Compound:
    key: str
    name: str
    letter: str
    color: Color
    grip: float
    life: float
    kind: str = "slick"

    def wet_factor(self, wetness: float) -> float:
        """Grip multiplier for the water on the track. Slicks aquaplane, inters like a damp track, wets need water."""
        w = clamp(wetness, 0.0, 1.0)
        if self.kind == "inter":
            return 0.87 + 0.20 * w if w <= 0.45 else 0.96 - 0.42 * (w - 0.45)
        if self.kind == "wet":
            return 0.70 + 0.24 * w
        return 1.0 - 0.75 * w ** 1.3

    def wear_factor(self, wetness: float) -> float:
        """Rain tyres on a drying track overheat and chew themselves up; water cools slicks."""
        dry = clamp((0.15 - wetness) / 0.15, 0.0, 1.0)
        if self.kind == "inter":
            return 1.0 + 3.0 * dry
        if self.kind == "wet":
            return 1.0 + 5.0 * dry + 1.5 * clamp((0.5 - wetness) / 0.5, 0.0, 1.0)
        return 1.0 - 0.5 * clamp(wetness, 0.0, 1.0)


COMPOUNDS: dict[str, Compound] = {
    "soft": Compound("soft", "Soft", "S", (235, 40, 45), 1.12, 150.0),
    "medium": Compound("medium", "Medium", "M", (250, 205, 40), 1.00, 290.0),
    "hard": Compound("hard", "Hard", "H", (235, 235, 235), 0.90, 520.0),
    "inter": Compound("inter", "Intermediate", "I", (40, 190, 70), 1.00, 260.0, "inter"),
    "wet": Compound("wet", "Wet", "W", (40, 120, 240), 1.00, 300.0, "wet"),
}
COMPOUND_ORDER = ["soft", "medium", "hard"]          # dry strategy
ALL_COMPOUNDS = COMPOUND_ORDER + ["inter", "wet"]    # anything the crew can fit


OPTIMAL_TEMP = {"slick": 100.0, "inter": 75.0, "wet": 62.0}   # centre of the working window (deg C)
TRACK_TEMP = 32.0
BLANKET_DROP = 22.0      # tyres come off the blankets this far below their window: the out-lap is slippery


class TyreSet:

    def __init__(self, compound: str, wear_factor: float = 1.0) -> None:
        self.compound = COMPOUNDS[compound]
        self.wear_factor = wear_factor
        self.wear = 0.0
        self.front_bias = 0.0
        self.laps = 0
        self.wetness = 0.0
        start = OPTIMAL_TEMP[self.compound.kind] - BLANKET_DROP
        self.temps = [start, start, start, start]      # front left, front right, rear left, rear right
        self.temp_factor = self._temp_grip()

    @property
    def optimal(self) -> float:
        return OPTIMAL_TEMP[self.compound.kind]

    def _temp_grip(self) -> float:
        """Grip multiplier for the tyre temperatures: cold tyres slide, overheated ones go greasy."""
        opt = self.optimal
        total = 0.0
        for t in self.temps:
            dev = t - opt
            if dev < -6:
                total += 1.0 - 0.11 * min(1.0, (-dev - 6) / 40) ** 1.2
            elif dev > 12:
                total += 1.0 - 0.07 * min(1.0, (dev - 12) / 35)
            else:
                total += 1.0
        return total / 4

    def update(self, dt: float, lateral_use: float, brake: float, throttle: float, slide_speed: float,
               moving: bool, speed_ratio: float = 0.0, turn: float = 0.0) -> None:
        """turn: signed lateral load (+ right-hand corner) - the outside tyres work harder."""
        # thermal model: friction work heats the rubber, the airstream (and water) cools it
        slide = min(1.0, slide_speed / 150.0)
        rolling = 2.0 * speed_ratio if moving else 0.0
        heat_f = 6.0 * lateral_use + 7.0 * brake * speed_ratio + 10.0 * slide + rolling
        heat_r = 5.0 * lateral_use + 1.5 * throttle * (1.0 - 0.5 * speed_ratio) + 12.0 * slide + rolling
        cool = 0.045 + 0.035 * speed_ratio + 0.06 * self.wetness
        bias = clamp(turn, -1.0, 1.0) * 0.18
        for k, heat in enumerate((heat_f, heat_f, heat_r, heat_r)):
            side = 1.0 + (bias if k % 2 == 0 else -bias)   # right-hand corner loads the left tyres
            t = self.temps[k]
            self.temps[k] = t + (heat * side - (t - TRACK_TEMP) * cool) * dt
        self.temp_factor = self._temp_grip()
        if not moving:
            return
        hot = max(0.0, max(self.temps) - self.optimal - 12.0) / 35.0
        load = 0.40 + 0.80 * lateral_use + 0.35 * brake + 1.5 * slide
        self.wear = min(1.0, self.wear + load / self.compound.life * self.wear_factor *
                        self.compound.wear_factor(self.wetness) * (1.0 + 1.5 * hot) * dt)
        self.front_bias = clamp(self.front_bias + (lateral_use - throttle * 0.5) * dt * 0.02, -0.08, 0.08)

    @property
    def grip(self) -> float:
        w = self.wear
        cliff = max(0.0, w - 0.70) / 0.30
        return self.compound.grip * (1.0 - 0.12 * w - 0.25 * cliff * cliff) * \
            self.compound.wet_factor(self.wetness) * getattr(self, "temp_factor", 1.0)

    @property
    def traction(self) -> float:
        return 1.0 - 0.8 * (1.0 - self.grip)

    @property
    def braking(self) -> float:
        return 1.0 - 0.8 * (1.0 - self.grip)

    @property
    def top_speed(self) -> float:
        compound_bonus = (self.compound.grip - 1.0) * 0.15
        rain_tyre = {"inter": 0.985, "wet": 0.965}.get(self.compound.kind, 1.0)
        return (1.0 + compound_bonus - 0.05 * self.wear ** 1.5) * rain_tyre

    def corner_wear(self) -> tuple[float, float, float, float]:
        f = clamp(self.wear * (1 + self.front_bias), 0.0, 1.0)
        r = clamp(self.wear * (1 - self.front_bias), 0.0, 1.0)
        return f, clamp(f * 0.97, 0, 1), r, clamp(r * 0.98, 0, 1)
