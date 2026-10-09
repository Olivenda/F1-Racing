# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Sequence

from pygame.math import Vector2

from .settings import (CAR_FRICTION_COEFF, CAR_INERTIA, CAR_LENGTH, CAR_MASS, CAR_WIDTH, RESTITUTION_CAR,
                       RESTITUTION_WALL, SPIN_TRANSFER)
from .utils import clamp, cross2

if TYPE_CHECKING:
    from .car import Car
    from .track import Track

_HALF_L = CAR_LENGTH / 2
_HALF_W = CAR_WIDTH / 2
_BROAD_PHASE_SQ = (CAR_LENGTH * 1.15) ** 2


def _point_velocity(car: "Car", r: Vector2) -> Vector2:
    return car.vel + Vector2(-car.spin * r.y, car.spin * r.x)


def _project(corners: list[Vector2], axis: Vector2) -> tuple[float, float]:
    values = [c.dot(axis) for c in corners]
    return min(values), max(values)


def _inside_obb(p: Vector2, car: "Car") -> bool:
    d = p - car.pos
    return abs(d.dot(car.forward)) <= _HALF_L + 0.5 and abs(d.dot(car.right)) <= _HALF_W + 0.5


def sat_test(a: "Car", b: "Car") -> tuple[Vector2, float] | None:
    ca, cb = a.corners(), b.corners()
    best_axis: Vector2 | None = None
    best_depth = 1e9
    for axis in (a.forward, a.right, b.forward, b.right):
        min_a, max_a = _project(ca, axis)
        min_b, max_b = _project(cb, axis)
        overlap = min(max_a, max_b) - max(min_a, min_b)
        if overlap <= 0:
            return None
        if overlap < best_depth:
            best_depth, best_axis = overlap, axis
    assert best_axis is not None
    if (b.pos - a.pos).dot(best_axis) < 0:
        best_axis = -best_axis
    return best_axis, best_depth


def resolve_car_collision(a: "Car", b: "Car", normal: Vector2, depth: float) -> tuple[float, Vector2] | None:
    if a.frozen and b.frozen:
        return None
    push = normal * (depth + 0.05)
    if a.frozen:
        b.pos += push
    elif b.frozen:
        a.pos -= push
    else:
        a.pos -= push * 0.5
        b.pos += push * 0.5

    pts = [c for c in a.corners() if _inside_obb(c, b)] + [c for c in b.corners() if _inside_obb(c, a)]
    contact = sum(pts, Vector2()) / len(pts) if pts else (a.pos + b.pos) * 0.5

    ra, rb = contact - a.pos, contact - b.pos
    v_rel = _point_velocity(b, rb) - _point_velocity(a, ra)
    vn = v_rel.dot(normal)
    if vn >= 0:
        return None

    inv_ma = 0.0 if a.frozen else 1.0 / CAR_MASS
    inv_mb = 0.0 if b.frozen else 1.0 / CAR_MASS
    inv_ia = 0.0 if a.frozen else 1.0 / CAR_INERTIA
    inv_ib = 0.0 if b.frozen else 1.0 / CAR_INERTIA
    ra_n, rb_n = cross2(ra, normal), cross2(rb, normal)
    denom = inv_ma + inv_mb + ra_n * ra_n * inv_ia + rb_n * rb_n * inv_ib
    j = -(1.0 + RESTITUTION_CAR) * vn / denom

    a.vel -= normal * (j * inv_ma)
    b.vel += normal * (j * inv_mb)
    a.spin -= ra_n * j * inv_ia * SPIN_TRANSFER
    b.spin += rb_n * j * inv_ib * SPIN_TRANSFER

    tangent = Vector2(-normal.y, normal.x)
    vt = v_rel.dot(tangent)
    jt = clamp(-vt / (inv_ma + inv_mb + 1e-9), -CAR_FRICTION_COEFF * j, CAR_FRICTION_COEFF * j)
    a.vel -= tangent * (jt * inv_ma)
    b.vel += tangent * (jt * inv_mb)

    a.notify_collision(j, "car", contact)
    b.notify_collision(j, "car", contact)
    return j, contact


def resolve_wall_collision(car: "Car", track: "Track") -> None:
    if car.retired_ghost or car.pit_state is not None:
        return
    deepest: tuple[float, Vector2, Vector2] | None = None
    for corner in car.corners():
        d, nrm = track.lateral_at(corner, car.idx)
        pen = abs(d) - track.wall_limit
        if pen > 0 and (deepest is None or pen > deepest[0]):
            wall_normal = nrm * (-1.0 if d > 0 else 1.0)
            deepest = (pen, corner, wall_normal)
    if deepest is None:
        return
    pen, corner, n = deepest
    car.pos += n * (pen + 0.1)

    r = corner - car.pos
    v_c = _point_velocity(car, r)
    vn = v_c.dot(n)
    if vn >= 0:
        return
    r_n = cross2(r, n)
    j = -(1.0 + RESTITUTION_WALL) * vn / (1.0 / CAR_MASS + r_n * r_n / CAR_INERTIA)
    car.vel += n * (j / CAR_MASS)
    car.spin += r_n * j / CAR_INERTIA * SPIN_TRANSFER * 0.4
    tangent = Vector2(-n.y, n.x)
    vt = car.vel.dot(tangent)
    car.vel -= tangent * (vt * min(0.25, j / 1300.0))
    car.notify_collision(j, "wall", corner)


def handle_collisions(cars: Sequence["Car"], track: "Track",
                      on_contact: Callable[["Car", "Car", float, Vector2], None] | None = None) -> None:
    active = [c for c in cars if not c.is_ghost and c.collide_cars]
    for i in range(len(active)):
        a = active[i]
        for k in range(i + 1, len(active)):
            b = active[k]
            if (a.pos - b.pos).length_squared() > _BROAD_PHASE_SQ:
                continue
            hit = sat_test(a, b)
            if hit is not None:
                result = resolve_car_collision(a, b, hit[0], hit[1])
                if result is not None and on_contact is not None:
                    on_contact(a, b, result[0], result[1])
    for car in cars:
        resolve_wall_collision(car, track)
