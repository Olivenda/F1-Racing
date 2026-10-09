# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import random

from .settings import CAR_LENGTH

IMPACT_THRESHOLD: float = 230.0
HARDNESS: float = 900.0
CRASH_COOLDOWN: float = 0.6
DNF_LIMIT: float = 1.0


class Damage:
    def __init__(self) -> None:
        self.front_wing = 0.0
        self.rear = 0.0
        self.suspension = 0.0
        self.pull = random.choice((-1.0, 1.0))
        self.multiplier = 1.0
        self.cooldown = 0.0

    def apply_impact(self, local_x: float, impulse: float) -> float:
        if impulse <= IMPACT_THRESHOLD or self.multiplier <= 0 or self.cooldown > 0:
            return 0.0
        self.cooldown = CRASH_COOLDOWN
        amount = (impulse - IMPACT_THRESHOLD) / HARDNESS * self.multiplier
        if local_x > CAR_LENGTH * 0.2:
            self.front_wing = min(1.0, self.front_wing + amount)
        elif local_x < -CAR_LENGTH * 0.2:
            self.rear = min(1.0, self.rear + amount * 0.8)
        else:
            self.suspension = min(1.0, self.suspension + amount * 0.7)
            self.front_wing = min(1.0, self.front_wing + amount * 0.3)
        return amount

    def tick(self, dt: float) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)

    @property
    def grip_factor(self) -> float:
        return (1.0 - 0.30 * self.front_wing) * (1.0 - 0.12 * self.rear) * (1.0 - 0.15 * self.suspension)

    @property
    def top_speed_factor(self) -> float:
        return (1.0 - 0.12 * self.rear) * (1.0 - 0.04 * self.front_wing)

    @property
    def engine_factor(self) -> float:
        return 1.0 - 0.22 * self.rear

    @property
    def brake_factor(self) -> float:
        return 1.0 - 0.15 * self.suspension

    @property
    def steer_bias(self) -> float:
        return self.pull * 0.18 * self.suspension

    @property
    def total(self) -> float:
        return max(self.front_wing, self.rear, self.suspension)

    @property
    def is_terminal(self) -> bool:
        return self.suspension >= DNF_LIMIT

    def repair_time(self) -> float:
        t = 0.0
        if self.front_wing > 0.12:
            t += 3.0
        if self.rear > 0.12:
            t += 4.0
        if self.suspension > 0.12:
            t += 6.0 * self.suspension
        return t

    def repair(self) -> None:
        self.front_wing = self.rear = 0.0
        self.suspension = 0.0
