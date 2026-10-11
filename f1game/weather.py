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
RAIN_WEEKEND_CHANCE = 0.30  # "dynamic": share of weekends with a shower at all
# ...and which ONE session of such a weekend gets it: never more than one shower per weekend
RAIN_SESSION = (("race", 0.5), ("qualifying", 0.3), ("practice", 0.2))


def rain_session(mode: str, weekend_seed: int) -> str | None:
    """"dynamic" weather: the one session of the weekend that gets a shower (None = a dry weekend)."""
    if mode != "dynamic":
        return None
    rng = random.Random(weekend_seed * 7919 + 17)
    if rng.random() >= RAIN_WEEKEND_CHANCE:
        return None
    r = rng.random()
    for kind, share in RAIN_SESSION:
        if r < share:
            return kind
        r -= share
    return "race"


def plan_fits(compound_kind: str, wetness: float) -> bool:
    """Whether a planned stop onto this kind of tyre still makes sense on the track as it is: rain tyres only
    once it is wet, slicks only once it is dry enough (the forecast can be a lap or two out)."""
    if compound_kind == "slick":
        return wetness < WET_THRESHOLD
    return wetness >= WET_THRESHOLD * 0.8


class Weather:

    def __init__(self, mode: str, seed: int, duration: float, weekend_seed: int | None = None,
                 kind: str = "race") -> None:
        """duration: rough length of the session in seconds, the forecast covers it.
        weekend_seed: shared by all sessions of a weekend, decides which session (if any) gets the shower."""
        rng = random.Random(seed)
        self.mode = mode
        self.duration = duration
        self.points: list[tuple[float, float]] = []   # (time, rain) keyframes
        if mode == "dynamic" and rain_session(mode, seed if weekend_seed is None else weekend_seed) != kind:
            mode = "dry"
        if mode == "wet":
            # steady rain: the intensity drifts slowly instead of changing every minute
            base = rng.uniform(0.5, 0.8)
            t = 0.0
            while t < duration + 120:
                self.points.append((t, max(0.3, min(0.95, base + rng.uniform(-0.12, 0.12)))))
                t += rng.uniform(150, 300)
        elif mode == "dynamic":
            # exactly ONE rain period: it sets in and stays, passes as a single shower, or a wet start clears up
            peak = rng.uniform(0.4, 0.9)
            ramp = rng.uniform(25, 60)
            end = duration + 120
            shape = rng.random()
            if shape < 0.45:
                t = rng.uniform(0.25, 0.65) * duration
                self.points += [(0.0, 0.0), (t, 0.0), (t + ramp, peak), (max(end, t + ramp + 1), peak * 0.9)]
            elif shape < 0.8:
                t = rng.uniform(0.15, 0.5) * duration
                stop = t + ramp + rng.uniform(0.2, 0.4) * duration
                self.points += [(0.0, 0.0), (t, 0.0), (t + ramp, peak), (stop, peak * 0.85),
                                (stop + ramp, 0.0), (max(end, stop + ramp + 1), 0.0)]
            else:
                start = peak * 0.85
                t = rng.uniform(0.2, 0.5) * duration
                self.points += [(0.0, start), (t, start * 0.9), (t + ramp, 0.0), (max(end, t + ramp + 1), 0.0)]
        else:
            self.points = [(0.0, 0.0), (duration + 120, 0.0)]
        self.points.sort()
        self.rain = self.forecast(0.0)
        self.wetness = self.rain * 0.9 if mode == "wet" else self.rain * 0.6
        self.start_wetness = self.wetness
        self.time = 0.0
        self._drops: list[list[float]] = [[rng.uniform(0, SCREEN_WIDTH), rng.uniform(0, SCREEN_HEIGHT),
                                           rng.uniform(0.6, 1.0)] for _ in range(260)]

    def forecast(self, t: float) -> float:
        pts = self.points
        if t <= pts[0][0]:
            return pts[0][1]
        for (t0, r0), (t1, r1) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                return r0 + (r1 - r0) * (0.5 - 0.5 * math.cos(math.pi * k))
        return pts[-1][1]

    @staticmethod
    def wet_step(wetness: float, rain: float, dt: float, cars_on_track: int) -> float:
        """Standing water after dt seconds of this rain."""
        if rain > 0.02:
            target = min(1.0, rain * 1.08)
            # water builds up over ~25-50 s of steady rain and runs off slowly when the rain eases
            rate = 0.03 * (0.4 + rain) if wetness < target else 0.006
            return wetness + (target - wetness) * min(1.0, rate * dt)
        # drying: wind/sun plus a dry line cut by the cars
        return max(0.0, wetness - dt * (0.0025 + 0.00025 * cars_on_track))

    def predict_wetness(self, ahead: float, cars_on_track: int = 20, step: float = 2.0) -> list[float]:
        """Track wetness every `step` seconds over the next `ahead` seconds, from the forecast."""
        w, t, out = self.wetness, self.time, []
        while t < self.time + ahead:
            t += step
            w = self.wet_step(w, self.forecast(t), step, cars_on_track)
            out.append(w)
        return out

    # ------------------------------------------------------------------ the forecast in laps
    def lap_outlook(self, lap_time: float, laps: int, from_time: float | None = None,
                    cars_on_track: int = 20) -> list[tuple[float, float]]:
        """(rain chance, expected track wetness) for each of the next `laps` laps. The chance is the forecast
        made a little uncertain: a lap next to the rain shows some chance too."""
        lap_time = max(10.0, lap_time)
        t0 = self.time if from_time is None else from_time
        rains, wets = [], []
        w, t = self.wetness if from_time is None else self.start_wetness, t0
        for k in range(laps):
            peak, end = 0.0, t0 + (k + 1) * lap_time
            while t < end:
                t += 2.0
                r = self.forecast(t)
                peak = max(peak, r)
                w = self.wet_step(w, r, 2.0, cars_on_track)
            rains.append(peak)
            wets.append(w)
        out = []
        for k in range(laps):
            near = max([rains[k]] + [0.55 * rains[j] for j in (k - 1, k + 1) if 0 <= j < laps])
            chance = 0.0 if near <= 0.05 else min(0.95, 0.45 + 0.6 * near)
            out.append((chance, wets[k]))
        return out

    def summary(self, lap_time: float, laps: int, from_time: float | None = None) -> str:
        """The weather broadcast in one line, counted in laps."""
        outlook = self.lap_outlook(lap_time, laps, from_time)
        wet = [k + 1 for k, (_, w) in enumerate(outlook) if w >= WET_THRESHOLD]
        rain = [k + 1 for k, (c, _) in enumerate(outlook) if c >= 0.6]
        if not rain and not wet:
            return "Trocken - kein Regen erwartet"
        if wet and len(wet) == laps:
            heavy = sum(1 for _, w in outlook if w >= FULL_WET_THRESHOLD) > laps // 2
            return "Starkregen über die ganze Distanz - Full Wets" if heavy else "Regen über die ganze Distanz"
        if not wet:
            return f"Leichter Schauer um Runde {rain[0]} - Strecke bleibt fast trocken"
        if wet[0] == 1:
            return f"Nasser Start, trocknet ab ca. Runde {wet[-1] + 1}"
        if wet[-1] == laps:
            return f"Regen ab ca. Runde {rain[0] if rain else wet[0]}, nass ab Runde {wet[0]}"
        return f"Schauer: nass von Runde {wet[0]} bis {wet[-1]}"

    def update(self, dt: float, track: "Track", cars_on_track: int) -> None:
        self.time += dt
        self.rain = self.forecast(self.time)
        self.wetness = self.wet_step(self.wetness, self.rain, dt, cars_on_track)
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
            # dst * (1 - a) + tint * a as two blend fills: no full-screen alpha blit (that cost several ms)
            a = 70 * min(1.0, 0.35 * self.wetness + 0.75 * self.rain) / 255
            keep = int(255 * (1 - a))
            screen.fill((keep, keep, keep), special_flags=pygame.BLEND_RGB_MULT)
            screen.fill((int(20 * a), int(30 * a), int(48 * a)), special_flags=pygame.BLEND_RGB_ADD)
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
