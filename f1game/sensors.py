# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Sequence

from pygame.math import Vector2

from .settings import CAR_LENGTH, CAR_WIDTH, TOP_SPEED
from .utils import clamp, wrap_angle

if TYPE_CHECKING:
    from .car import Car
    from .track import Track

LOOKAHEAD: tuple[float, ...] = (50.0, 110.0, 190.0, 290.0, 420.0, 580.0)
RADAR_RANGE: float = 280.0
INPUT_NAMES: list[str] = (["Tempo", "Rutschen", "Querpos.", "Winkel"]
                          + [f"Voraus {int(d)}" for d in LOOKAHEAD]
                          + ["Radar VL", "Radar VM", "Radar VR", "Seite L", "Seite R", "Annäherung"])
N_INPUTS: int = len(INPUT_NAMES)
OUTPUT_NAMES: list[str] = ["Lenkung", "Gas/Bremse"]
N_OUTPUTS: int = len(OUTPUT_NAMES)


def lookahead_points(car: "Car", track: "Track") -> list[Vector2]:
    n = track.n
    return [track.center[(car.idx + int(d / track.WAYPOINT_SPACING)) % n] for d in LOOKAHEAD]


def compute_inputs(car: "Car", others: Sequence["Car"], track: "Track") -> list[float]:
    fwd, right = car.forward, car.right
    tan = track.tangents[car.idx]
    hw = track.half_width
    heading_err = wrap_angle(car.heading - math.atan2(tan.y, tan.x))
    inputs = [
        car.speed_fwd / TOP_SPEED,
        clamp(car.vel.dot(right) / 200.0, -2.0, 2.0),
        clamp(car.lateral / hw, -2.0, 2.0),
        heading_err / (math.pi / 2),
    ]
    for p in lookahead_points(car, track):
        rel = p - car.pos
        inputs.append(math.atan2(rel.dot(right), rel.dot(fwd)) / math.pi)

    front_l = front_c = front_r = side_l = side_r = closing = 0.0
    if not car.is_ghost:
        L = track.length
        for o in others:
            if o is car or o.is_ghost:
                continue
            ds = o.s - car.s
            if ds > L / 2:
                ds -= L
            elif ds < -L / 2:
                ds += L
            dl = o.lateral - car.lateral
            if abs(dl) > CAR_WIDTH * 3.0:
                continue
            if abs(ds) < CAR_LENGTH * 1.2:
                prox = clamp(1.0 - (abs(dl) - CAR_WIDTH) / (CAR_WIDTH * 2.0), 0.0, 1.0)
                if dl < 0:
                    side_l = max(side_l, prox)
                else:
                    side_r = max(side_r, prox)
            elif 0.0 < ds < RADAR_RANGE:
                prox = 1.0 - ds / RADAR_RANGE
                if dl < -CAR_WIDTH * 0.8:
                    front_l = max(front_l, prox)
                elif dl > CAR_WIDTH * 0.8:
                    front_r = max(front_r, prox)
                elif prox > front_c:
                    front_c = prox
                    closing = clamp((car.speed_fwd - o.speed_fwd) / 200.0, -1.0, 1.0)
    inputs += [front_l, front_c, front_r, side_l, side_r, closing]
    return inputs
