# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from .settings import CAR_LENGTH, CAR_WIDTH, SCREEN_HEIGHT, SCREEN_WIDTH

if TYPE_CHECKING:
    from .sessions import Session
    from .track import Track

SMOKE = (205, 205, 210)
SPRAY = (200, 208, 218)
SPARK_COLORS = [(255, 240, 160), (255, 200, 60), (255, 140, 30)]


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "grow", "color", "kind", "z", "vz")

    def __init__(self, x: float, y: float, vx: float, vy: float, life: float, size: float, grow: float,
                 color: tuple[int, int, int], kind: str, z: float = 2.0, vz: float = 0.0) -> None:
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.grow, self.color, self.kind = size, grow, color, kind
        self.z, self.vz = z, vz       # height above the road (3D view)


class Effects:
    """Eye candy for both views: tyre smoke, grass/gravel dust, rain spray, sparks (impacts and the plank
    scraping the road at top speed) and skid marks burnt into the track surface (2D)."""

    def __init__(self, track: "Track", level: str = "high") -> None:
        self.track = track
        self.level = level
        self.parts: list[Particle] = []
        self.cap = 420 if level == "high" else 160
        self._impulse: dict[int, float] = {}
        self._wheels: dict[int, tuple[Vector2, Vector2]] = {}
        self._blobs: dict[tuple, pygame.Surface] = {}
        darker = tuple(int(c * 0.55) for c in track.definition.asphalt)
        self.skid_color = darker

    @property
    def enabled(self) -> bool:
        return self.level != "off"

    def _emit(self, *args) -> None:
        if len(self.parts) < self.cap:
            self.parts.append(Particle(*args))

    def update(self, session: "Session", dt: float) -> None:
        if not self.enabled or dt <= 0:
            return
        dense = 1.0 if self.level == "high" else 0.45
        fast = session.time_scale > 1.0
        for car in session.cars:
            cid = id(car)
            impulse = car.wall_impulse + car.car_impulse
            hit = impulse - self._impulse.get(cid, impulse)
            self._impulse[cid] = impulse
            if car.is_ghost or (car.dnf and car.vel.length_squared() < 25):
                self._wheels.pop(cid, None)
                continue
            fwd, right = car.forward, car.right
            speed = car.vel.length()
            lat = abs(car.vel.dot(right))
            rear = car.pos - fwd * (CAR_LENGTH * 0.33)
            wl, wr = rear - right * (CAR_WIDTH * 0.40), rear + right * (CAR_WIDTH * 0.40)
            lock = (car.brake > 0.85 and car.sliding or getattr(car, "locking", False)) and speed > 80
            spin = car.throttle > 0.9 and 3 < car.speed_fwd < 70 and getattr(session, "race_started", True) or \
                getattr(car, "wheelspin", 0.0) > 0.3
            slide = lat > 75 and speed > 50
            if hit > 25 and not fast:
                n = int(min(18, 4 + hit / 25) * dense)
                for _ in range(n):
                    a = random.uniform(0, math.tau)
                    v = random.uniform(80, 320)
                    self._emit(car.pos.x + random.uniform(-8, 8), car.pos.y + random.uniform(-8, 8),
                               car.vel.x * 0.4 + math.cos(a) * v, car.vel.y * 0.4 + math.sin(a) * v,
                               random.uniform(0.15, 0.45), 2.0, 0.0, random.choice(SPARK_COLORS), "spark",
                               random.uniform(1.0, 5.0), random.uniform(20, 140))
            if car.on_grass and speed > 40 and not car.in_pit:
                if random.random() < min(1.0, speed / 260) * dense * dt * 40:
                    col = self.track.definition.runoff_color
                    col = tuple(min(255, int(c * 1.1 + 25)) for c in col)
                    for w in (wl, wr):
                        self._emit(w.x, w.y, -car.vel.x * 0.15 + random.uniform(-30, 30),
                                   -car.vel.y * 0.15 + random.uniform(-30, 30), random.uniform(0.5, 1.0),
                                   random.uniform(3, 5), 14.0, col, "dust", 1.0, random.uniform(8, 26))
            elif (car.damage.cooling > 0.45 or car.damage.rear > 0.6) and speed > 30 and not car.in_pit:
                # a holed radiator or broken gearbox trails smoke
                heavy = max(car.damage.cooling, car.damage.rear)
                if random.random() < heavy * dense * dt * 30:
                    back = car.pos - fwd * (CAR_LENGTH * 0.5)
                    self._emit(back.x, back.y, car.vel.x * 0.3 + random.uniform(-15, 15),
                               car.vel.y * 0.3 + random.uniform(-15, 15), random.uniform(0.8, 1.5),
                               random.uniform(3, 5), 18.0, (70, 70, 74), "smoke", 4.0, 10.0)
            elif self.track.wetness > 0.15 and speed > 120 and not car.in_pit:
                # spray off the rear tyres - the wetter and faster, the bigger the cloud
                if random.random() < min(1.0, speed / 400) * self.track.wetness * dense * dt * 60:
                    for w in (wl, wr):
                        self._emit(w.x, w.y, car.vel.x * 0.55 + random.uniform(-25, 25),
                                   car.vel.y * 0.55 + random.uniform(-25, 25), random.uniform(0.35, 0.7),
                                   random.uniform(3, 5), 26.0, SPRAY, "smoke", 2.0, random.uniform(6, 16))
            elif (slide or lock or spin) and not car.in_pit:
                if random.random() < dense * dt * 45:
                    for w in (wl, wr):
                        self._emit(w.x + random.uniform(-2, 2), w.y + random.uniform(-2, 2),
                                   car.vel.x * 0.25 + random.uniform(-20, 20), car.vel.y * 0.25 + random.uniform(-20, 20),
                                   random.uniform(0.6, 1.3), random.uniform(3, 5), 20.0, SMOKE, "smoke", 1.5,
                                   random.uniform(4, 12))
            if speed > car.top_speed * 0.86 and not car.on_grass and not car.in_pit and not fast                     and random.random() < dense * dt * 7:
                # the plank and skid blocks scrape the asphalt at top speed: a shower of sparks behind the car
                under = car.pos - fwd * (CAR_LENGTH * 0.38)
                for _ in range(random.randint(3, 7)):
                    off = random.uniform(-CAR_WIDTH * 0.3, CAR_WIDTH * 0.3)
                    self._emit(under.x + right.x * off, under.y + right.y * off,
                               car.vel.x * 0.6 + random.uniform(-40, 40), car.vel.y * 0.6 + random.uniform(-40, 40),
                               random.uniform(0.12, 0.35), 2.0, 0.0, random.choice(SPARK_COLORS), "spark",
                               0.4, random.uniform(10, 70))
            marking = (slide or lock or spin) and not car.on_grass and not car.in_pit
            prev = self._wheels.get(cid)
            if marking and prev is not None and self.track.surface is not None:
                for a, b in ((prev[0], wl), (prev[1], wr)):
                    if a.distance_squared_to(b) < 900:
                        pygame.draw.line(self.track.surface, self.skid_color, a, b, 3)
            if marking:
                self._wheels[cid] = (Vector2(wl), Vector2(wr))
            else:
                self._wheels.pop(cid, None)
        keep = []
        for p in self.parts:
            p.life -= dt
            if p.life <= 0:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            drag = 3.5 if p.kind == "spark" else 1.8
            p.vx -= p.vx * min(1.0, drag * dt)
            p.vy -= p.vy * min(1.0, drag * dt)
            p.size += p.grow * dt
            p.z += p.vz * dt
            if p.kind == "spark":
                p.vz -= 320.0 * dt
                if p.z < 0:
                    p.z, p.vz = 0.0, -p.vz * 0.35
            else:
                p.vz -= p.vz * min(1.0, 1.2 * dt)
            keep.append(p)
        self.parts = keep

    def _blob(self, radius: int, color: tuple[int, int, int], alpha: int) -> pygame.Surface:
        key = (radius, color, alpha)
        img = self._blobs.get(key)
        if img is None:
            img = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(img, (*color, alpha), (radius + 1, radius + 1), radius)
            if radius > 3:
                pygame.draw.circle(img, (*color, min(255, alpha + alpha // 2)), (radius + 1, radius + 1), radius * 2 // 3)
            if len(self._blobs) > 600:
                self._blobs.clear()
            self._blobs[key] = img
        return img

    def draw(self, screen: pygame.Surface, off: Vector2) -> None:
        if not self.enabled:
            return
        ox, oy = off.x, off.y
        for p in self.parts:
            sx, sy = p.x - ox, p.y - oy
            if not (-40 < sx < SCREEN_WIDTH + 40 and -40 < sy < SCREEN_HEIGHT + 40):
                continue
            t = p.life / p.max_life
            if p.kind == "spark":
                tail = (sx - p.vx * 0.025, sy - p.vy * 0.025)
                pygame.draw.line(screen, p.color, (sx, sy), tail, 2)
                continue
            base = 70 if p.kind == "smoke" else 110
            alpha = max(8, int(base * t) // 8 * 8)
            r = max(2, int(p.size))
            img = self._blob(r, p.color, alpha)
            screen.blit(img, (sx - r - 1, sy - r - 1))
