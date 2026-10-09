# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import random

from .settings import CAR_LENGTH, CAR_WIDTH

IMPACT_THRESHOLD: float = 230.0
HARDNESS: float = 900.0
CRASH_COOLDOWN: float = 0.6
DNF_LIMIT: float = 1.0
PUNCTURE_IMPULSE: float = 420.0


class Damage:
    """Where the car was hit decides what breaks:

    nose / front corners  -> front wing (one side first), front suspension, front tyre
    flanks / sidepods     -> suspension on that side, floor, radiator (cooling)
    rear / rear corners   -> rear wing + diffuser + gearbox ("rear"), rear suspension, rear tyre

    Suspension is tracked per side: a bent left corner pulls the car to the left. The floor is part of the
    chassis and can't be changed in a pit stop (like the plank); everything else is repaired.
    """

    def __init__(self) -> None:
        self.front_wing = 0.0
        self.wing_side = random.choice((-1.0, 1.0))    # which endplate went first (-1 left, +1 right)
        self.rear = 0.0
        self.susp_l = 0.0
        self.susp_r = 0.0
        self.floor = 0.0
        self.cooling = 0.0
        self.multiplier = 1.0
        self.cooldown = 0.0
        self.pending_puncture = False
        self.last_hit = 0.0

    @property
    def suspension(self) -> float:
        return max(self.susp_l, self.susp_r)

    @suspension.setter
    def suspension(self, value: float) -> None:
        self.susp_l = self.susp_r = value

    def apply_impact(self, local_x: float, impulse: float, local_y: float = 0.0) -> float:
        if impulse <= IMPACT_THRESHOLD or self.multiplier <= 0 or self.cooldown > 0:
            return 0.0
        self.cooldown = CRASH_COOLDOWN
        amount = (impulse - IMPACT_THRESHOLD) / HARDNESS * self.multiplier
        self.last_hit = amount
        side = -1.0 if local_y < 0 else 1.0
        corner = abs(local_y) > CAR_WIDTH * 0.22       # hit near a wheel rather than dead centre

        def bend(k: float) -> None:
            if side < 0:
                self.susp_l = min(1.0, self.susp_l + amount * k)
            else:
                self.susp_r = min(1.0, self.susp_r + amount * k)

        if local_x > CAR_LENGTH * 0.2:
            if self.front_wing < 0.05 and corner:
                self.wing_side = side
            self.front_wing = min(1.0, self.front_wing + amount)
            if corner:
                bend(0.35)
        elif local_x < -CAR_LENGTH * 0.2:
            self.rear = min(1.0, self.rear + amount * 0.8)
            if corner:
                bend(0.3)
        else:
            bend(0.7)
            self.floor = min(1.0, self.floor + amount * 0.35)
            self.cooling = min(1.0, self.cooling + amount * 0.4)
            self.front_wing = min(1.0, self.front_wing + amount * 0.15)
        # a hard knock on a wheel can cut the tyre
        if corner and abs(local_x) > CAR_LENGTH * 0.12 and impulse > PUNCTURE_IMPULSE and \
                random.random() < min(0.6, (impulse - PUNCTURE_IMPULSE) / 900.0 + 0.1):
            self.pending_puncture = True
        return amount

    def scrape(self, amount: float) -> None:
        """Floor damage from bottoming out hard (kerbs, gravel) at speed."""
        if self.multiplier > 0:
            self.floor = min(1.0, self.floor + amount * self.multiplier)

    def tick(self, dt: float) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)

    @property
    def grip_factor(self) -> float:
        return (1.0 - 0.30 * self.front_wing) * (1.0 - 0.12 * self.rear) * (1.0 - 0.15 * self.suspension) * \
            (1.0 - 0.14 * self.floor)

    @property
    def top_speed_factor(self) -> float:
        return (1.0 - 0.12 * self.rear) * (1.0 - 0.04 * self.front_wing) * (1.0 - 0.03 * self.floor)

    @property
    def engine_factor(self) -> float:
        # a holed radiator makes the engine run hot: the team turns the power down
        return (1.0 - 0.22 * self.rear) * (1.0 - 0.15 * self.cooling)

    @property
    def brake_factor(self) -> float:
        return 1.0 - 0.15 * self.suspension

    @property
    def steer_bias(self) -> float:
        # a bent corner drags: the car pulls towards the damaged side
        return 0.18 * (self.susp_r - self.susp_l)

    @property
    def pull(self) -> float:
        return 1.0 if self.susp_r >= self.susp_l else -1.0

    @property
    def total(self) -> float:
        return max(self.front_wing, self.rear, self.suspension, self.floor, self.cooling)

    @property
    def is_terminal(self) -> bool:
        return self.suspension >= DNF_LIMIT or self.cooling >= DNF_LIMIT

    def parts(self) -> list[tuple[str, float]]:
        """Damaged parts for the HUD, worst first."""
        out = [("Flügel", self.front_wing), ("Heck", self.rear), ("Aufh. L", self.susp_l),
               ("Aufh. R", self.susp_r), ("Boden", self.floor), ("Kühler", self.cooling)]
        return sorted(((n, v) for n, v in out if v >= 0.05), key=lambda p: -p[1])

    def repair_time(self) -> float:
        t = 0.0
        if self.front_wing > 0.12:
            t += 3.0
        if self.rear > 0.12:
            t += 4.0
        if self.suspension > 0.12:
            t += 6.0 * self.suspension + 2.0 * min(self.susp_l, self.susp_r)
        if self.cooling > 0.12:
            t += 3.0 * self.cooling
        return t

    def repair(self) -> None:
        self.front_wing = self.rear = 0.0
        self.susp_l = self.susp_r = 0.0
        self.cooling = 0.0
        # the floor is part of the chassis: only patched up a little
        self.floor *= 0.7
