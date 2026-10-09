# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from .settings import (BRAKE_DECEL, CAR_LENGTH, CAR_WIDTH, DRAG_SHARE, ENGINE_ACCEL, ENGINE_FADE,
                       GEAR_THRESHOLDS, GRASS_DRAG, GRASS_ENGINE_FACTOR, GRASS_GRIP_FACTOR, LATERAL_GRIP,
                       MAX_STEER_ANGLE, PX_PER_S_TO_KMH, REVERSE_ACCEL, REVERSE_MAX_SPEED, ROLLING_FRICTION,
                       SLIP_RECOVERY, SLIPSTREAM_DRAG, SPIN_DAMPING, STRAIGHT_MODE_DRAG, STRAIGHT_MODE_GRIP, STEER_RATE, TOP_SPEED, WHEELBASE, Color)
from .utils import approach, clamp, wrap_angle

from .car_setup import NEUTRAL, CarSetup, SetupFactors
from .profiles import amplified
from .damage import IMPACT_THRESHOLD, Damage
from .tyres import TyreSet

if TYPE_CHECKING:
    from .profiles import DriverProfile
    from .sessions import Session
    from .track import Track

MARKERS_PER_LAP: int = 40
# fuel and plank wear are scaled to the race distance so a 5-lap and a 50-lap race both behave like a full GP
RACE_FUEL_KG: float = 100.0
FUEL_ACCEL_LOSS: float = 0.0012     # per kg
FUEL_GRIP_LOSS: float = 0.0003
FUEL_BRAKE_LOSS: float = 0.0009
PLANK_LIMIT_MM: float = 1.0
PLANK_RACE_MM: float = 0.55         # neutral setup, clean driving, full race distance
SECTOR_MARKERS: tuple[int, int] = (13, 26)


def _mix(a: Color, b: Color, t: float) -> Color:
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


_SPRITE_CACHE: dict[tuple, pygame.Surface] = {}


def build_car_sprite(body: Color, helmet: Color, scale: float = 1.0) -> pygame.Surface:
    """Top-down F1 car, drawn 8x oversized and smooth-scaled down so the edges are anti-aliased.
    The nose points to +x. scale=1 gives the in-race size (CAR_LENGTH x CAR_WIDTH)."""
    key = (tuple(body), tuple(helmet), round(scale, 2))
    cached = _SPRITE_CACHE.get(key)
    if cached is not None:
        return cached.copy()
    S = 8
    L, W = CAR_LENGTH, CAR_WIDTH
    surf = pygame.Surface((int(L * S), int(W * S)), pygame.SRCALPHA)
    dark = _mix(body, (0, 0, 0), 0.45)
    light = _mix(body, (255, 255, 255), 0.35)
    carbon, tyre, rim = (28, 28, 32), (16, 16, 18), (70, 70, 76)

    def P(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * S, y * S) for x, y in pts]

    def R(x: float, y: float, w: float, h: float) -> pygame.Rect:
        return pygame.Rect(round(x * S), round(y * S), round(w * S), round(h * S))

    for x, w in ((3.0, 7.0), (23.0, 6.0)):
        for y in (0.0, W - 3.6):
            pygame.draw.rect(surf, tyre, R(x, y, w, 3.6), border_radius=S)
            pygame.draw.rect(surf, rim, R(x + 0.6, y + (0.5 if y else 2.6), w - 1.2, 0.5))
    pygame.draw.polygon(surf, carbon, P([(4, 3.2), (23, 4.2), (25, 6.0), (25, 10.0), (23, 11.8), (4, 12.8)]))
    pygame.draw.polygon(surf, body, P([(8, 3.6), (12, 3.0), (19, 3.4), (22, 5.6), (22, 10.4), (19, 12.6), (12, 13.0),
                                       (8, 12.4)]))
    pygame.draw.polygon(surf, dark, P([(9, 3.9), (12, 3.4), (16, 3.6), (16, 4.4), (9, 4.6)]))
    pygame.draw.polygon(surf, dark, P([(9, 12.1), (12, 12.6), (16, 12.4), (16, 11.6), (9, 11.4)]))
    pygame.draw.polygon(surf, body, P([(3.5, 6.0), (13, 5.4), (24, 6.4), (31.5, 7.3), (33.6, 7.7), (33.6, 8.3),
                                       (31.5, 8.7), (24, 9.6), (13, 10.6), (3.5, 10.0)]))
    pygame.draw.line(surf, light, (5 * S, 8 * S), (32 * S, 8 * S), int(0.7 * S))
    pygame.draw.polygon(surf, dark, P([(30.6, 0.8), (33.6, 1.4), (33.6, W - 1.4), (30.6, W - 0.8)]))
    pygame.draw.rect(surf, light, R(32.6, 1.4, 0.7, W - 2.8))
    for y in (0.6, W - 1.6):
        pygame.draw.rect(surf, carbon, R(30.2, y, 3.6, 1.0))
    pygame.draw.rect(surf, dark, R(0.2, 1.2, 3.6, W - 2.4), border_radius=S // 2)
    pygame.draw.rect(surf, light, R(0.4, 1.6, 1.0, W - 3.2))
    for y in (0.8, W - 1.8):
        pygame.draw.rect(surf, carbon, R(0.0, y, 4.0, 1.0))
    pygame.draw.ellipse(surf, (12, 12, 14), R(14.0, 5.8, 7.5, 4.4))
    pygame.draw.circle(surf, helmet, (17.4 * S, 8 * S), 1.7 * S)
    pygame.draw.circle(surf, _mix(helmet, (0, 0, 0), 0.4), (17.4 * S, 8 * S), 1.7 * S, max(1, S // 3))
    pygame.draw.arc(surf, carbon, R(15.0, 5.6, 7.6, 4.8), -1.4, 1.4, int(0.6 * S))
    pygame.draw.line(surf, carbon, (14.6 * S, 8 * S), (21.6 * S, 8 * S), max(1, S // 3))
    pygame.draw.rect(surf, (255, 40, 40), R(0.0, 7.4, 0.6, 1.2))
    out = pygame.transform.smoothscale(surf, (max(2, round(L * scale)), max(2, round(W * scale))))
    _SPRITE_CACHE[key] = out
    return out.copy()


def shadow_of(sprite: pygame.Surface, alpha: int = 85) -> pygame.Surface:
    shadow = sprite.copy()
    shadow.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGB_MULT)
    shadow.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    return shadow


class Car:

    def __init__(self, profile: "DriverProfile", track: "Track") -> None:
        self.profile = profile
        self.name = profile.name
        self.short = profile.short
        self.color = profile.color
        self.track = track
        self.is_player = False

        self.pos = Vector2()
        self.vel = Vector2()
        self.heading = 0.0
        self.spin = 0.0
        self.steer_angle = 0.0
        self.speed_fwd = 0.0
        self.sliding = False

        self.throttle = 0.0
        self.brake = 0.0
        self.steer_input = 0.0

        self.idx = 0
        self.s = 0.0
        self.lateral = 0.0
        self.distance = 0.0
        self.lap_floor = -1
        self.on_grass = False

        self.timing_started = False
        self.lap_start_time = 0.0
        self.laps_done = 0
        self.lap_times: list[float] = []
        self.last_lap: float | None = None
        self.best_lap: float | None = None
        self.marker_times: dict[int, float] = {}
        self.last_marker = -10 ** 9
        self.current_splits: dict[int, float] = {}
        self.best_splits: dict[int, float] = {}
        self.session_done = False
        self.finish_time: float | None = None
        self.sectors: list[float] = []
        self.last_sectors: list[float] = []
        self.best_sectors: list[float | None] = [None, None, None]
        self.launch_spin = 0.0
        self.puncture = False
        self.pit_laps: list[int] = []
        self.seen_crashes = 0
        self.radio_msg: tuple[str, tuple[int, int, int], float] | None = None
        self.grid_slot = 0

        self.frozen = False
        self.collide_cars = True
        self.blue_for: "Car | None" = None
        self.blue_gap = 0.0
        self.engine_factor = 1.0
        self.perf = amplified(profile.car)
        self.tyres: TyreSet | None = None
        self.grip_bonus = 1.0
        self.setup: CarSetup | None = None
        self.sf: SetupFactors = NEUTRAL
        self.pit_request: str | None = None
        self.pit_state: str | None = None
        self.pit_u = 0.0
        self.pit_entry_lat = 0.0
        self.pit_box_u = 0.0
        self.pit_compound = "medium"
        self.pit_stop_timer = 0.0
        self.pit_stopped = False
        self.pit_stops = 0
        self.damage = Damage()
        self.damage.multiplier = 0.0
        self.dnf = False
        self.crashes = 0
        self.tl_off = False
        self.tl_forced = False
        self.tl_since = 0.0
        self.tl_count = 0
        self.tl_distance = 0.0
        self.tl_speed = 0.0
        self.lap_invalid = False
        self.invalid_laps: set[int] = set()
        self.last_contact_time = -1e9
        self.penalty_unserved = 0.0
        self.penalty_total = 0.0
        self.wall_impulse = 0.0
        self.car_impulse = 0.0
        self.grass_time = 0.0
        self.ghost_timer = 0.0
        self.retired_ghost = False
        self.collision_flash = 0.0
        self.slipstream = 0.0
        self.slip_target = 0.0
        self.straight_mode = False
        self.straight_mode_time = 0.0
        self.fuel = 0.0                 # kg on board
        self.fuel_per_lap = 0.0         # kg per lap at race pace; 0 = fuel not simulated
        self.out_of_fuel = False
        self.plank_wear = 0.0           # mm worn off the skid block
        self.plank_per_lap = 0.0        # mm per lap for a neutral setup; 0 = not simulated
        self.dsq = False
        self.dsq_reason = ""
        self.pit_plan: dict | None = None
        self.lap_log: list[dict] = []
        self._lap_log_start: dict | None = None

        self._sprite = build_car_sprite(self.color, profile.helmet)
        self._shadow = shadow_of(self._sprite)
        self._rot_cache: dict[int, pygame.Surface] = {}
        self.vmax = 0.0
        self.lap_vmax = 0.0

    @property
    def forward(self) -> Vector2:
        return Vector2(math.cos(self.heading), math.sin(self.heading))

    @property
    def right(self) -> Vector2:
        return Vector2(-math.sin(self.heading), math.cos(self.heading))

    @property
    def is_ghost(self) -> bool:
        return self.ghost_timer > 0.0 or self.retired_ghost or self.in_pit

    @property
    def in_pit(self) -> bool:
        return self.pit_state is not None

    @property
    def top_speed(self) -> float:
        return TOP_SPEED * self.perf.top_speed

    @property
    def tyre_grip(self) -> float:
        return self.tyres.grip if self.tyres else 1.0

    def apply_setup(self, setup: CarSetup | None) -> None:
        self.setup = setup
        self.sf = setup.factors() if setup is not None else NEUTRAL

    def fill_fuel(self, laps: float, per_lap: float) -> None:
        self.fuel_per_lap = per_lap
        self.fuel = max(0.0, laps * per_lap)
        self.out_of_fuel = False

    @property
    def fuel_laps(self) -> float:
        return self.fuel / self.fuel_per_lap if self.fuel_per_lap > 0 else 99.0

    @property
    def fuel_factors(self) -> tuple[float, float, float]:
        """(accel, grip, brake) multipliers for the weight of the fuel on board."""
        f = self.fuel
        return 1.0 - FUEL_ACCEL_LOSS * f, 1.0 - FUEL_GRIP_LOSS * f, 1.0 - FUEL_BRAKE_LOSS * f

    def performance(self) -> dict[str, float]:
        t, d, p, sf = self.tyres, self.damage, self.perf, self.sf
        fa, fg, fb = self.fuel_factors
        return {
            "grip": p.aero * sf.grip * (t.grip if t else 1.0) * d.grip_factor * fg,
            "accel": p.engine * sf.engine * (t.traction if t else 1.0) * d.engine_factor * fa,
            "top": p.top_speed * min(sf.drag ** -0.5, sf.rev_limit) * (t.top_speed if t else 1.0) * d.top_speed_factor,
            "brake": p.brakes * sf.brake * (t.braking if t else 1.0) * d.brake_factor * fb,
        }

    @property
    def speed_kmh(self) -> float:
        return abs(self.speed_fwd) * PX_PER_S_TO_KMH

    @property
    def gear(self) -> str:
        if self.speed_fwd < -3:
            return "R"
        if abs(self.speed_fwd) < 3 and self.throttle <= 0:
            return "N"
        return str(1 + sum(1 for t in GEAR_THRESHOLDS if self.speed_fwd >= t))

    @property
    def rpm_fraction(self) -> float:
        v = max(0.0, self.speed_fwd)
        bounds = (0.0,) + GEAR_THRESHOLDS + (TOP_SPEED,)
        for lo, hi in zip(bounds, bounds[1:]):
            if v < hi:
                return clamp(0.35 + 0.65 * (v - lo) / (hi - lo), 0.0, 1.0)
        return 1.0

    def corners(self) -> list[Vector2]:
        f = self.forward * (CAR_LENGTH / 2)
        r = self.right * (CAR_WIDTH / 2)
        return [self.pos + f + r, self.pos + f - r, self.pos - f - r, self.pos - f + r]

    def place(self, pos: Vector2, heading: float) -> None:
        self.pos = Vector2(pos)
        self.heading = heading
        self.vel = Vector2()
        self.spin = 0.0
        self.steer_angle = 0.0
        self.speed_fwd = 0.0
        self.idx, self.s, self.lateral = self.track.project(self.pos)
        L = self.track.length
        self.distance = self.s - L if self.s > L / 2 else self.s
        self.lap_floor = math.floor(self.distance / L)

    def respawn(self) -> None:
        t = self.track
        i = self.idx
        offset = t.line_offset[i] if t.line_offset else 0.0
        self.pos = t.center[i] + t.normals[i] * offset
        self.heading = math.atan2(t.tangents[i].y, t.tangents[i].x)
        self.vel = Vector2()
        self.spin = 0.0
        self.speed_fwd = 0.0
        self.ghost_timer = 2.0

    def control(self, dt: float, session: "Session") -> None:
        raise NotImplementedError

    def notify_collision(self, impulse: float, kind: str, contact: Vector2 | None = None) -> None:
        if impulse > IMPACT_THRESHOLD:
            self.crashes += 1
        if contact is not None:
            rel = contact - self.pos
            self.damage.apply_impact(rel.dot(self.forward), impulse, rel.dot(self.right))
        if kind == "car":
            self.car_impulse += impulse
        else:
            self.wall_impulse += impulse
        if impulse > 20:
            self.collision_flash = 0.25

    STRAIGHT_STEER_LIMIT: float = 0.45

    def update_aero(self, h: float, wants: bool | None = None) -> None:
        zone = self.track.aero_zone_at[self.idx] if self.track.aero_zone_at else -1
        if self.straight_mode:
            self.straight_mode_time += h
            if zone < 0 or self.brake > 0.1 or abs(self.steer_input) > self.STRAIGHT_STEER_LIMIT or \
                    self.on_grass or self.in_pit or self.frozen:
                self.straight_mode = False
            return
        if zone < 0 or self.in_pit or self.frozen or self.on_grass or self.brake > 0.0 or self.speed_fwd < 150:
            return
        if wants is None:
            wants = self.throttle > 0.9 and abs(self.steer_input) < 0.25
        if wants:
            self.straight_mode = True

    def physics_step(self, dt: float) -> None:
        self.ghost_timer = max(0.0, self.ghost_timer - dt)
        self.collision_flash = max(0.0, self.collision_flash - dt)
        self.damage.tick(dt)
        if self.frozen:
            self.vel.update(0, 0)
            self.spin = 0.0
            self.speed_fwd = 0.0
            return
        if self.pit_state is not None:
            return

        if self.tyres is not None:
            self.tyres.wetness = self.track.wetness
        fwd, right = self.forward, self.right
        vf = self.vel.dot(fwd)
        vl = self.vel.dot(right)
        perf = self.perf
        sf = self.sf
        tyre_grip = self.tyre_grip
        top = self.top_speed
        top *= self.damage.top_speed_factor * (self.tyres.top_speed if self.tyres else 1.0)
        grip = LATERAL_GRIP * perf.aero * sf.grip * tyre_grip * self.grip_bonus * self.damage.grip_factor * \
            (GRASS_GRIP_FACTOR * sf.grass_grip if self.on_grass else 1.0) * \
            (STRAIGHT_MODE_GRIP if self.straight_mode else 1.0) * (0.55 if self.puncture else 1.0)
        engine = ENGINE_ACCEL * self.engine_factor * perf.engine * sf.engine * self.damage.engine_factor * \
            (self.tyres.traction if self.tyres else 1.0) * \
            (GRASS_ENGINE_FACTOR if self.on_grass else 1.0)
        if self.launch_spin > 0.0:
            self.launch_spin = max(0.0, self.launch_spin - dt)
            engine *= 0.45
        brake_force = BRAKE_DECEL * perf.brakes * sf.brake * (self.tyres.braking if self.tyres else 1.0) * \
            self.damage.brake_factor
        if self.on_grass:
            self.grass_time += dt

        steer_target = clamp(self.steer_input + self.damage.steer_bias, -1.0, 1.0)
        self.steer_angle = approach(self.steer_angle, steer_target, STEER_RATE * sf.steer_rate * dt)

        acc = 0.0
        if self.throttle > 0.0:
            if vf >= -5.0:
                acc += engine * self.throttle * (1.0 - ENGINE_FADE * clamp(vf / top, 0.0, 1.0))
            else:
                acc += BRAKE_DECEL * 0.6 * self.throttle
        ratio = vf / top
        drag_factor = sf.drag * (1.0 - SLIPSTREAM_DRAG * self.slipstream) * \
            (1.0 - STRAIGHT_MODE_DRAG if self.straight_mode else 1.0)
        acc -= ENGINE_ACCEL * perf.engine * DRAG_SHARE * ratio * abs(ratio) * drag_factor
        braking_forward = False
        if self.brake > 0.0:
            if vf > 8.0:
                acc -= brake_force * self.brake * (0.6 if self.on_grass else 1.0)
                braking_forward = True
            elif vf > -REVERSE_MAX_SPEED:
                acc -= REVERSE_ACCEL * self.brake
        if self.throttle <= 0.0 and self.brake <= 0.0 and abs(vf) > 0.5:
            acc -= math.copysign(ROLLING_FRICTION, vf)
        if self.on_grass:
            acc -= GRASS_DRAG * vf
        new_vf = vf + acc * dt
        if vf > 0.0 > new_vf and (braking_forward or self.brake <= 0.0):
            new_vf = 0.0
        if vf < 0.0 < new_vf and self.throttle <= 0.0:
            new_vf = 0.0
        rev_cap = top * (0.5 if self.puncture else sf.rev_limit)
        if new_vf > rev_cap:
            new_vf = max(rev_cap, vf - 400.0 * dt) if vf > rev_cap else rev_cap

        speed = max(abs(new_vf), 1.0)
        turn = sf.turn * (sf.brake_turn if braking_forward else 1.0)
        k_max = min(math.tan(MAX_STEER_ANGLE) / WHEELBASE, grip * turn / (speed * speed))
        yaw_rate = new_vf * self.steer_angle * k_max
        self.heading = wrap_angle(self.heading + (yaw_rate + self.spin) * dt)
        self.spin *= math.exp(-SPIN_DAMPING * dt)

        world_v = fwd * new_vf + right * vl
        fwd2, right2 = self.forward, self.right
        vf2 = world_v.dot(fwd2)
        slip_hold = sf.slip * (sf.brake_slip if braking_forward else 1.0)
        vl2 = approach(world_v.dot(right2), 0.0, grip * SLIP_RECOVERY * slip_hold * dt)
        self.vel = fwd2 * vf2 + right2 * vl2
        self.speed_fwd = vf2
        self.sliding = abs(vl2) > 60.0
        if vf2 > self.vmax:
            self.vmax = vf2
        if vf2 > self.lap_vmax:
            self.lap_vmax = vf2
        self.pos += self.vel * dt
        if self.tyres is not None:
            lateral_use = min(1.2, abs(vf2 * yaw_rate) / max(grip, 1.0))
            self.tyres.update(dt, lateral_use, self.brake, self.throttle, abs(vl2), abs(vf2) > 5.0)
        if vf2 > 5.0 and not self.session_done:
            self._consume(dt, vf2 / top)

    def _consume(self, dt: float, speed_ratio: float) -> None:
        lap_frac = self.speed_fwd * dt / self.track.length
        if self.fuel_per_lap > 0 and not self.out_of_fuel:
            # mostly distance based; lifting off still saves fuel (~0.8 is a typical lap's average throttle)
            self.fuel = max(0.0, self.fuel - self.fuel_per_lap * lap_frac * (0.6 + 0.4 * self.throttle) / 0.92)
            if self.fuel <= 0.0:
                self.out_of_fuel = True
        if self.plank_per_lap > 0:
            # the skid block touches down when the car is compressed: high speed (downforce), braking dive,
            # kerbs and grass; a heavy fuel load makes the car sit lower
            load = 0.35 + 0.9 * speed_ratio * speed_ratio + 0.5 * self.brake * speed_ratio +                 (1.6 * speed_ratio if self.on_grass else 0.0)
            load *= 1.0 + 0.003 * self.fuel
            self.plank_wear += self.plank_per_lap * lap_frac * load / 1.35 * self.sf.plank
        if self.on_grass and speed_ratio > 0.55:
            # bouncing over kerbs and gravel at speed knocks the floor about, more so on a low car
            self.damage.scrape(0.004 * dt * speed_ratio * self.sf.plank)

    def update_track_state(self, session: "Session") -> None:
        track = self.track
        L = track.length
        # called every physics step (a few px of travel), so a narrow window keeps the projection from
        # snapping onto a neighbouring part of the track at chicanes and hairpins
        idx, s, lat = track.project(self.pos, self.idx, back=4, fwd=6)
        ds = s - self.s
        if ds < -L / 2:
            ds += L
        elif ds > L / 2:
            ds -= L
        self.distance += ds
        self.idx, self.s, self.lateral = idx, s, lat
        self.on_grass = abs(lat) > track.half_width and self.pit_state is None

        floor_now = math.floor(self.distance / L)
        if floor_now > self.lap_floor:
            self.lap_floor = floor_now
            if floor_now == 0:
                if not self.timing_started:
                    self.start_timing(session.time)
            elif self.timing_started:
                self._complete_lap(session)

        marker = math.floor(self.distance / (L / MARKERS_PER_LAP))
        if marker > self.last_marker:
            start = max(marker - 3, self.last_marker + 1)
            for m in range(start, marker + 1):
                self.marker_times.setdefault(m, session.time)
                if self.timing_started:
                    self.current_splits[m % MARKERS_PER_LAP] = session.time - self.lap_start_time
                    if m % MARKERS_PER_LAP in SECTOR_MARKERS and len(self.sectors) < 2:
                        self._close_sector(session, session.time - self.lap_start_time)
            self.last_marker = marker

    def _close_sector(self, session: "Session", lap_time_so_far: float) -> None:
        t = lap_time_so_far - sum(self.sectors)
        k = len(self.sectors)
        self.sectors.append(t)
        if not self.lap_invalid and (self.best_sectors[k] is None or t < self.best_sectors[k]):
            self.best_sectors[k] = t
        note = getattr(session, "note_sector", None)
        if note is not None and not self.lap_invalid:
            note(self, k, t)

    def live_delta(self) -> float | None:
        m = self.last_marker % MARKERS_PER_LAP
        if m == 0 or m not in self.current_splits or m not in self.best_splits:
            return None
        return self.current_splits[m] - self.best_splits[m]

    def start_timing(self, now: float) -> None:
        self._lap_log_start = self._snapshot()
        self.timing_started = True
        self.lap_start_time = now
        self.sectors = []

    def _complete_lap(self, session: "Session") -> None:
        lap = session.time - self.lap_start_time
        self.lap_start_time = session.time
        if self.session_done:
            return
        self.laps_done += 1
        if len(self.sectors) == 2:
            self._close_sector(session, lap)
        self.last_sectors = self.sectors
        self.sectors = []
        if self.tyres is not None:
            self.tyres.laps += 1
        self.lap_times.append(lap)
        self.last_lap = lap
        self._log_lap(lap)
        valid = not self.lap_invalid
        if not valid:
            self.invalid_laps.add(len(self.lap_times) - 1)
        self.lap_invalid = False
        if valid and (self.best_lap is None or lap < self.best_lap):
            self.best_lap = lap
            self.best_splits = self.current_splits
        self.current_splits = {}
        session.on_lap_completed(self, lap)

    def _snapshot(self) -> dict:
        t = self.tyres
        return {"wear": t.wear if t else 0.0, "compound": t.compound.key if t else "", "fuel": self.fuel,
                "plank": self.plank_wear, "pits": self.pit_stops}

    def _log_lap(self, lap: float) -> None:
        """Per-lap telemetry for the post-practice analysis."""
        now = self._snapshot()
        start = self._lap_log_start or now
        pitted = now["pits"] != start["pits"]
        self.lap_log.append({
            "lap": len(self.lap_times), "time": lap, "valid": not self.lap_invalid, "compound": now["compound"],
            "wear": now["wear"], "wear_delta": None if pitted else now["wear"] - start["wear"],
            "fuel": now["fuel"], "fuel_used": None if pitted else start["fuel"] - now["fuel"],
            "plank": now["plank"], "plank_delta": now["plank"] - start["plank"], "pit": pitted,
            "vmax": self.lap_vmax * PX_PER_S_TO_KMH,
        })
        self._lap_log_start = now
        self.lap_vmax = 0.0

    def current_lap_time(self, now: float) -> float | None:
        return now - self.lap_start_time if self.timing_started else None

    def draw(self, surface: pygame.Surface, cam: Vector2) -> None:
        screen_pos = self.pos - cam
        if not (-60 < screen_pos.x < surface.get_width() + 60 and -60 < screen_pos.y < surface.get_height() + 60):
            return
        key = int(round(-math.degrees(self.heading) / 3.0)) * 3 % 360
        img = self._rot_cache.get(key)
        if img is None:
            img = pygame.transform.rotozoom(self._sprite, key, 1.0)
            self._rot_cache[key] = img
            self._rot_cache[key + 2000] = pygame.transform.rotozoom(self._shadow, key, 1.0)
        rect = img.get_rect(center=(round(screen_pos.x), round(screen_pos.y)))
        if not self.is_ghost:
            surface.blit(self._rot_cache[key + 2000], rect.move(3, 4))
        if self.is_ghost:
            ghost = self._rot_cache.get(key + 1000)
            if ghost is None:
                ghost = img.copy()
                ghost.set_alpha(105)
                self._rot_cache[key + 1000] = ghost
            surface.blit(ghost, rect)
        else:
            surface.blit(img, rect)
        if self.brake > 0.2 and self.speed_fwd > 5 and not self.is_ghost:
            rear = screen_pos - self.forward * (CAR_LENGTH / 2 - 1)
            pygame.draw.circle(surface, (255, 40, 40), rear, 2)
        if self.collision_flash > 0:
            pygame.draw.circle(surface, (255, 220, 80), screen_pos, int(CAR_LENGTH * 0.7), 2)
