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


COMPOUNDS: dict[str, Compound] = {
    "soft": Compound("soft", "Soft", "S", (235, 40, 45), 1.12, 150.0),
    "medium": Compound("medium", "Medium", "M", (250, 205, 40), 1.00, 290.0),
    "hard": Compound("hard", "Hard", "H", (235, 235, 235), 0.90, 520.0),
}
COMPOUND_ORDER = ["soft", "medium", "hard"]


class TyreSet:

    def __init__(self, compound: str, wear_factor: float = 1.0) -> None:
        self.compound = COMPOUNDS[compound]
        self.wear_factor = wear_factor
        self.wear = 0.0
        self.front_bias = 0.0
        self.laps = 0

    def update(self, dt: float, lateral_use: float, brake: float, throttle: float, slide_speed: float,
               moving: bool) -> None:
        if not moving:
            return
        load = 0.40 + 0.80 * lateral_use + 0.35 * brake + 1.5 * min(1.0, slide_speed / 150.0)
        self.wear = min(1.0, self.wear + load / self.compound.life * self.wear_factor * dt)
        self.front_bias = clamp(self.front_bias + (lateral_use - throttle * 0.5) * dt * 0.02, -0.08, 0.08)

    @property
    def grip(self) -> float:
        w = self.wear
        cliff = max(0.0, w - 0.70) / 0.30
        return self.compound.grip * (1.0 - 0.12 * w - 0.25 * cliff * cliff)

    @property
    def traction(self) -> float:
        return 1.0 - 0.8 * (1.0 - self.grip)

    @property
    def braking(self) -> float:
        return 1.0 - 0.8 * (1.0 - self.grip)

    @property
    def top_speed(self) -> float:
        compound_bonus = (self.compound.grip - 1.0) * 0.15
        return 1.0 + compound_bonus - 0.05 * self.wear ** 1.5

    def corner_wear(self) -> tuple[float, float, float, float]:
        f = clamp(self.wear * (1 + self.front_bias), 0.0, 1.0)
        r = clamp(self.wear * (1 - self.front_bias), 0.0, 1.0)
        return f, clamp(f * 0.97, 0, 1), r, clamp(r * 0.98, 0, 1)
