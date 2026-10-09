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
SPARK_COLORS = [(255, 240, 160), (255, 200, 60), (255, 140, 30)]


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "grow", "color", "kind")

    def __init__(self, x: float, y: float, vx: float, vy: float, life: float, size: float, grow: float,
                 color: tuple[int, int, int], kind: str) -> None:
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.grow, self.color, self.kind = size, grow, color, kind


class Effects:
    """2D-view eye candy: tyre smoke, grass/gravel dust, sparks and skid marks burnt into the track surface."""

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
            lock = car.brake > 0.85 and car.sliding and speed > 80
            spin = car.throttle > 0.9 and 3 < car.speed_fwd < 70 and getattr(session, "race_started", True)
            slide = lat > 75 and speed > 50
            if hit > 25 and not fast:
                n = int(min(18, 4 + hit / 25) * dense)
                for _ in range(n):
                    a = random.uniform(0, math.tau)
                    v = random.uniform(80, 320)
                    self._emit(car.pos.x + random.uniform(-8, 8), car.pos.y + random.uniform(-8, 8),
                               car.vel.x * 0.4 + math.cos(a) * v, car.vel.y * 0.4 + math.sin(a) * v,
                               random.uniform(0.15, 0.45), 2.0, 0.0, random.choice(SPARK_COLORS), "spark")
            if car.on_grass and speed > 40 and not car.in_pit:
                if random.random() < min(1.0, speed / 260) * dense * dt * 40:
                    col = self.track.definition.runoff_color
                    col = tuple(min(255, int(c * 1.1 + 25)) for c in col)
                    for w in (wl, wr):
                        self._emit(w.x, w.y, -car.vel.x * 0.15 + random.uniform(-30, 30),
                                   -car.vel.y * 0.15 + random.uniform(-30, 30), random.uniform(0.5, 1.0),
                                   random.uniform(3, 5), 14.0, col, "dust")
            elif (slide or lock or spin) and not car.in_pit:
                if random.random() < dense * dt * 45:
                    for w in (wl, wr):
                        self._emit(w.x + random.uniform(-2, 2), w.y + random.uniform(-2, 2),
                                   car.vel.x * 0.25 + random.uniform(-20, 20), car.vel.y * 0.25 + random.uniform(-20, 20),
                                   random.uniform(0.6, 1.3), random.uniform(3, 5), 20.0, SMOKE, "smoke")
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
