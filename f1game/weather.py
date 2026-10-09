# Copyright Olivenda (Oliver Petz) 2026
"""Weather: a rain forecast per session, a track that gets wet and dries again, and the rain on screen.

rain     0..1  how hard it is raining right now
wetness  0..1  standing water on the track (lags behind the rain, dries with time and traffic)
Slicks lose grip quickly on a wet track; intermediates are best on a damp/wet track, full wets in heavy rain.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame

from .settings import SCREEN_HEIGHT, SCREEN_WIDTH

if TYPE_CHECKING:
    from .track import Track

WEATHER_MODES = {"dry": "Trocken", "dynamic": "Wechselhaft", "wet": "Regen"}
WET_THRESHOLD = 0.22      # above this slicks are slower than intermediates
FULL_WET_THRESHOLD = 0.68  # above this full wets beat intermediates


class Weather:

    def __init__(self, mode: str, seed: int, duration: float) -> None:
        """duration: rough length of the session in seconds, the forecast covers it."""
        rng = random.Random(seed)
        self.mode = mode
        self.points: list[tuple[float, float]] = []   # (time, rain) keyframes
        if mode == "wet":
            base = rng.uniform(0.45, 0.85)
            t = 0.0
            while t < duration + 120:
                self.points.append((t, max(0.15, min(1.0, base + rng.uniform(-0.3, 0.25)))))
                t += rng.uniform(40, 90)
        elif mode == "dynamic":
            # dry start, one or two showers of different strength somewhere in the session
            self.points.append((0.0, 0.0 if rng.random() < 0.75 else rng.uniform(0.3, 0.6)))
            t = rng.uniform(0.15, 0.45) * duration
            for _ in range(rng.choice((1, 1, 2))):
                peak = rng.uniform(0.35, 1.0)
                build, hold, clear = rng.uniform(20, 50), rng.uniform(30, 0.35 * duration), rng.uniform(20, 60)
                self.points += [(t, 0.0), (t + build, peak), (t + build + hold, peak * rng.uniform(0.6, 1.0)),
                                (t + build + hold + clear, 0.0)]
                t += build + hold + clear + rng.uniform(0.15, 0.4) * duration
            self.points.append((max(t, duration + 120), 0.0))
        else:
            self.points = [(0.0, 0.0), (duration + 120, 0.0)]
        self.points.sort()
        self.rain = self.forecast(0.0)
        self.wetness = self.rain * 0.9 if mode == "wet" else self.rain * 0.6
        self.time = 0.0
        self._drops: list[list[float]] = [[rng.uniform(0, SCREEN_WIDTH), rng.uniform(0, SCREEN_HEIGHT),
                                           rng.uniform(0.6, 1.0)] for _ in range(260)]
        self._tint: pygame.Surface | None = None

    def forecast(self, t: float) -> float:
        pts = self.points
        if t <= pts[0][0]:
            return pts[0][1]
        for (t0, r0), (t1, r1) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                return r0 + (r1 - r0) * (0.5 - 0.5 * math.cos(math.pi * k))
        return pts[-1][1]

    def update(self, dt: float, track: "Track", cars_on_track: int) -> None:
        self.time += dt
        self.rain = self.forecast(self.time)
        if self.rain > 0.02:
            target = min(1.0, self.rain * 1.08)
            # water builds up over ~25-50 s of steady rain and runs off slowly when the rain eases
            rate = 0.03 * (0.4 + self.rain) if self.wetness < target else 0.006
            self.wetness += (target - self.wetness) * min(1.0, rate * dt)
        else:
            # drying: wind/sun plus a dry line cut by the cars
            self.wetness = max(0.0, self.wetness - dt * (0.0025 + 0.00025 * cars_on_track))
        track.wetness = self.wetness

    def eta_rain(self, horizon: float = 120.0) -> float | None:
        """Seconds until it starts raining (None if dry for the next `horizon` seconds or raining already)."""
        if self.rain > 0.05:
            return None
        t = self.time
        while t < self.time + horizon:
            t += 5.0
            if self.forecast(t) > 0.1:
                return t - self.time
        return None

    def eta_dry(self, horizon: float = 120.0) -> float | None:
        if self.rain <= 0.05:
            return None
        t = self.time
        while t < self.time + horizon:
            t += 5.0
            if self.forecast(t) <= 0.05:
                return t - self.time
        return None

    @staticmethod
    def best_compound(wetness: float) -> str | None:
        """The tyre that suits the track (None = slicks)."""
        if wetness >= FULL_WET_THRESHOLD:
            return "wet"
        if wetness >= WET_THRESHOLD:
            return "inter"
        return None

    def label(self) -> str:
        if self.rain > 0.65:
            return "Starkregen"
        if self.rain > 0.3:
            return "Regen"
        if self.rain > 0.05:
            return "Nieselregen"
        if self.wetness > WET_THRESHOLD:
            return "Nass, trocknet ab"
        if self.wetness > 0.05:
            return "Feucht"
        return "Trocken"

    # ------------------------------------------------------------------ drawing
    def draw(self, screen: pygame.Surface, dt: float, cam_vel: tuple[float, float] = (0.0, 0.0),
             view3d: bool = False) -> None:
        if self.wetness > 0.03 or self.rain > 0.03:
            dark = int(70 * min(1.0, 0.35 * self.wetness + 0.75 * self.rain))
            if self._tint is None:
                self._tint = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            self._tint.fill((20, 30, 48, dark))
            screen.blit(self._tint, (0, 0))
        if self.rain <= 0.03:
            return
        n = int(len(self._drops) * min(1.0, self.rain * 1.2))
        # 3D: rain falls towards the camera (longer, steeper streaks); 2D: seen from above, short slanted ticks
        length = 26.0 if view3d else 9.0
        speed = 900.0 if view3d else 420.0
        vx, vy = cam_vel
        col = (190, 205, 225)
        for d in self._drops[:n]:
            d[1] += speed * d[2] * dt - vy * dt * 0.15
            d[0] += (-120 * d[2] - vx * 0.15) * dt
            if d[1] > SCREEN_HEIGHT or d[0] < -20 or d[0] > SCREEN_WIDTH + 20 or d[1] < -40:
                d[0] = random.uniform(0, SCREEN_WIDTH + 60)
                d[1] = random.uniform(-40, 0) if d[1] > SCREEN_HEIGHT else random.uniform(0, SCREEN_HEIGHT)
            ln = length * d[2]
            pygame.draw.line(screen, col, (d[0], d[1]), (d[0] - ln * 0.28, d[1] - ln), 1)
