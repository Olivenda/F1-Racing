# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pygame.math import Vector2

from .utils import circumradius, lerp

if TYPE_CHECKING:
    from .track import Track

SPEED_LIMIT: float = 165.0
PIT_DECEL: float = 650.0
PIT_ACCEL: float = 260.0


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class PitLane:
    HALF_WIDTH: float = 22.0
    RAMP: float = 180.0

    def __init__(self, track: "Track") -> None:
        self.track = track
        sp = track.WAYPOINT_SPACING
        n = track.n

        def straight(i: int) -> bool:
            i %= n
            return circumradius(track.center[i - 4], track.center[i], track.center[(i + 4) % n]) > 650

        back = 0
        while back * sp < 950 and straight(-back):
            back += 1
        fwd = 0
        while fwd * sp < 750 and straight(fwd):
            fwd += 1
        self.entry_s = -(back * sp - 30.0)
        self.exit_s = fwd * sp - 30.0
        self.length = self.exit_s - self.entry_s
        self.offset = track.wall_limit + 16.0 + self.HALF_WIDTH
        self.side = self._choose_side()
        self.lane_lat = self.side * self.offset
        self.merge_lat = self.side * track.half_width * 0.45

    def _choose_side(self) -> int:
        track = self.track
        n = track.n
        near = set()
        for u in range(int(self.entry_s) - 400, int(self.exit_s) + 400, 12):
            near.add(int((u % track.length) / track.WAYPOINT_SPACING) % n)
        best_side, best_clear = -1, -1.0
        for side in (-1, 1):
            clear = 1e9
            for u in range(0, int(self.length), 30):
                p, _ = track.pose_at(self.entry_s + u, side * (self.offset + self.HALF_WIDTH + 40))
                for i in range(0, n, 2):
                    if i in near:
                        continue
                    c = track.center[i]
                    clear = min(clear, math.hypot(c.x - p.x, c.y - p.y))
            if clear > best_clear:
                best_side, best_clear = side, clear
        return best_side

    def lateral(self, u: float, entry_lat: float | None = None) -> float:
        start = self.merge_lat if entry_lat is None else entry_lat
        if u < self.RAMP:
            return lerp(start, self.lane_lat, smoothstep(u / self.RAMP))
        if u > self.length - self.RAMP:
            return lerp(self.lane_lat, self.merge_lat, smoothstep((u - (self.length - self.RAMP)) / self.RAMP))
        return self.lane_lat

    def pose(self, u: float, entry_lat: float | None = None) -> tuple[Vector2, float]:
        p, _ = self.track.pose_at(self.entry_s + u, self.lateral(u, entry_lat))
        q, _ = self.track.pose_at(self.entry_s + u + 6.0, self.lateral(u + 6.0, entry_lat))
        d = q - p
        return p, math.atan2(d.y, d.x)

    def box_positions(self, count: int) -> list[float]:
        start, end = self.RAMP + 50.0, self.length - self.RAMP - 50.0
        step = (end - start) / max(1, count)
        return [start + step * (k + 0.5) for k in range(count)]

    def entry_abs(self) -> float:
        return self.entry_s % self.track.length

    def ramp_indices(self) -> set[int]:
        track = self.track
        out = set()
        for a, b in ((self.entry_s, self.entry_s + self.RAMP), (self.exit_s - self.RAMP, self.exit_s)):
            s = a
            while s <= b:
                out.add(int((s % track.length) / track.WAYPOINT_SPACING) % track.n)
                s += track.WAYPOINT_SPACING
        return out

    def outline(self, step: float = 12.0) -> list[tuple[Vector2, Vector2]]:
        out = []
        u = 0.0
        while u <= self.length:
            p, heading = self.pose(u)
            nrm = Vector2(-math.sin(heading), math.cos(heading)) * self.HALF_WIDTH
            out.append((p - nrm, p + nrm))
            u += step
        return out
