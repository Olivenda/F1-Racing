# Copyright Olivenda (Oliver Petz) 2026
"""Replay for the race director: the last REPLAY_SECONDS of the race are recorded (every car's pose, ~30 per
second) and can be watched again - the race stands still meanwhile and continues exactly where it was. Incidents
are marked on the timeline and can be jumped to."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from .settings import CYAN, GREY, ORANGE, PANEL, SCREEN_WIDTH, WHITE, YELLOW
from .utils import draw_panel, draw_text, wrap_angle

if TYPE_CHECKING:
    from .car import Car
    from .sessions import RaceSession

REPLAY_SECONDS = 120.0
FRAME_INTERVAL = 1.0 / 30.0
SPEEDS = [0.25, 0.5, 1.0, 2.0]
SEEK_STEP = 5.0
LEAD_IN = 4.0               # jumping to an incident starts this long before it
# the car state a frame holds (and that is put back when the replay ends)
FIELDS = ("pos", "vel", "heading", "steer_angle", "speed_fwd", "spin", "s", "idx", "lateral", "throttle", "brake",
          "on_grass")
SC_FIELDS = ("pos", "heading", "s", "speed")
MARK_COLORS = {"col": (255, 150, 90), "cut": YELLOW, "pen": ORANGE, "warn": YELLOW, "bw": (235, 235, 235),
               "crash": (255, 80, 70), "flag": CYAN}


def _grab(obj, fields: tuple[str, ...]) -> tuple:
    return tuple(Vector2(v) if isinstance(v := getattr(obj, f), Vector2) else v for f in fields)


def _put(obj, fields: tuple[str, ...], values: tuple) -> None:
    for f, v in zip(fields, values):
        setattr(obj, f, Vector2(v) if isinstance(v, Vector2) else v)


class Replay:

    def __init__(self, session: "RaceSession") -> None:
        self.s = session
        self.frames: deque[tuple[float, list[tuple], tuple | None]] = deque()
        self.markers: deque[tuple[float, "Car | None", str, str]] = deque()
        self._last = -1e9
        self.active = False
        self.cursor = 0.0
        self.playing = True
        self.speed_i = 2
        self._live: tuple[list[tuple], tuple | None, int] | None = None
        self._line: pygame.Rect | None = None      # the timeline as last drawn (for dragging the dot)
        self.dragging = False

    # ------------------------------------------------------------------ recording
    def record(self) -> None:
        s = self.s
        if self.active or s.time - self._last < FRAME_INTERVAL:
            return
        self._last = s.time
        sc = s.rc.sc
        self.frames.append((s.time, [_grab(c, FIELDS) for c in s.cars],
                            _grab(sc, SC_FIELDS) if sc is not None else None))
        while self.frames and self.frames[0][0] < s.time - REPLAY_SECONDS:
            self.frames.popleft()
        while self.markers and self.markers[0][0] < s.time - REPLAY_SECONDS:
            self.markers.popleft()

    def mark(self, car: "Car | None", kind: str, text: str) -> None:
        if not self.active:
            self.markers.append((self.s.time, car, kind, text))

    # ------------------------------------------------------------------ watching
    def start(self, at: float | None = None, car: "Car | None" = None) -> bool:
        """Into the replay at race time `at` (default: a few seconds back)."""
        if len(self.frames) < 2:
            self.s.message("Noch keine Aufnahme für ein Replay", ORANGE, 2.0)
            return False
        s = self.s
        sc = s.rc.sc
        self._live = ([_grab(c, FIELDS) for c in s.cars], _grab(sc, SC_FIELDS) if sc is not None else None,
                      s.cam_index)
        self.active = True
        self.playing = True
        first, last = self.frames[0][0], self.frames[-1][0]
        self.cursor = max(first, min(last, (s.time - 10.0) if at is None else at))
        if car is not None and car in s.cars:
            s.focus_car(car)
        self._apply()
        return True

    def stop(self) -> None:
        """Back to the live race, exactly as it was."""
        if not self.active or self._live is None:
            self.active = False
            return
        s = self.s
        cars, sc_state, cam = self._live
        for car, values in zip(s.cars, cars):
            _put(car, FIELDS, values)
        if sc_state is not None and s.rc.sc is not None:
            _put(s.rc.sc, SC_FIELDS, sc_state)
        self.active = False
        self._live = None
        self.dragging = False
        s.free_cam = False
        s.camera.snap(s.cars[s.cam_index].pos)
        s.r3d._initialized = False

    def update(self, frame_dt: float) -> None:
        if not self.active:
            return
        if self.playing and not self.dragging:
            self.cursor += frame_dt * SPEEDS[self.speed_i]
            if self.cursor >= self.frames[-1][0]:
                self.cursor = self.frames[-1][0]
                self.playing = False        # caught up with the live race
        self._apply()                       # (the camera is the session's: it follows or looks around)

    def _frame_pair(self) -> tuple[int, float]:
        frames = self.frames
        lo, hi = 0, len(frames) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if frames[mid][0] <= self.cursor:
                lo = mid
            else:
                hi = mid
        t0, t1 = frames[lo][0], frames[hi][0]
        return lo, 0.0 if t1 <= t0 else max(0.0, min(1.0, (self.cursor - t0) / (t1 - t0)))

    def _apply(self) -> None:
        """Put every car where it was at the cursor (between two frames: interpolated)."""
        s = self.s
        k, a = self._frame_pair()
        _, cars0, sc0 = self.frames[k]
        _, cars1, sc1 = self.frames[min(k + 1, len(self.frames) - 1)]
        for car, v0, v1 in zip(s.cars, cars0, cars1):
            _put(car, FIELDS, v0 if a < 0.5 else v1)
            car.pos = v0[0].lerp(v1[0], a)
            car.heading = v0[2] + wrap_angle(v1[2] - v0[2]) * a
            car.speed_fwd = v0[4] + (v1[4] - v0[4]) * a
        sc = s.rc.sc
        if sc is not None:
            state = sc0 if a < 0.5 else sc1
            if state is not None:
                _put(sc, SC_FIELDS, state)

    def seek(self, dt: float) -> None:
        self.cursor = max(self.frames[0][0], min(self.frames[-1][0], self.cursor + dt))
        self._apply()

    def jump(self, d: int) -> None:
        """To the previous (d < 0) or next incident marker."""
        if d < 0:
            marks = [m for m in self.markers if m[0] - LEAD_IN < self.cursor - 0.5]
            m = marks[-1] if marks else None
        else:
            marks = [m for m in self.markers if m[0] - LEAD_IN > self.cursor + 0.5]
            m = marks[0] if marks else None
        if m is None:
            return
        self.cursor = max(self.frames[0][0], m[0] - LEAD_IN)
        self.playing = True
        if m[1] is not None and m[1] in self.s.cars:
            self.s.focus_car(m[1])
        self._apply()

    def last_incident(self, car: "Car") -> float | None:
        times = [t for t, c, kind, _ in self.markers if c is car and kind != "flag"]
        return times[-1] - LEAD_IN if times else None

    def handle_mouse(self, event: pygame.event.Event) -> bool:
        """Grab the dot (or click anywhere on the timeline) and drag it through the recording."""
        line = self._line
        if line is None:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and line.inflate(16, 26).collidepoint(event.pos):
            self.dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self.dragging = False
            return True
        elif not (event.type == pygame.MOUSEMOTION and self.dragging):
            return False
        first, last = self.frames[0][0], self.frames[-1][0]
        k = max(0.0, min(1.0, (event.pos[0] - line.x) / max(1, line.w)))
        self.cursor = first + (last - first) * k
        self._apply()
        return True

    def handle_key(self, key: int) -> bool:
        """Replay keys (True = handled). Camera and driver keys go on to the session."""
        if key in (pygame.K_r, pygame.K_ESCAPE):
            self.stop()
        elif key == pygame.K_SPACE:
            if not self.playing and self.cursor >= self.frames[-1][0] - 1e-3:
                self.cursor = self.frames[0][0]         # at the end: from the start again
            self.playing = not self.playing
        elif key in (pygame.K_LEFT, pygame.K_a):
            self.seek(-SEEK_STEP)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.seek(SEEK_STEP)
        elif key in (pygame.K_COMMA, pygame.K_MINUS, pygame.K_KP_MINUS):
            self.speed_i = max(0, self.speed_i - 1)
        elif key in (pygame.K_PERIOD, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
            self.speed_i = min(len(SPEEDS) - 1, self.speed_i + 1)
        elif key == pygame.K_q:
            self.jump(-1)
        elif key == pygame.K_e:
            self.jump(1)
        else:
            return False
        return True

    # ------------------------------------------------------------------ drawing
    def draw(self, screen: pygame.Surface) -> None:
        if not self.active:
            return
        f = self.s.game.fonts
        first, last = self.frames[0][0], self.frames[-1][0]
        live = self.s.time
        # banner
        rect = pygame.Rect(SCREEN_WIDTH // 2 - 190, 84, 380, 34)
        pygame.draw.rect(screen, (30, 30, 36), rect, border_radius=6)
        pygame.draw.rect(screen, (220, 40, 40), rect, 2, border_radius=6)
        state = ">" if self.playing else "II"
        speed = SPEEDS[self.speed_i]
        draw_text(screen, f"REPLAY  {state}  {self.cursor - live:+.1f} s  ·  x{speed:g}", f.small_bold, WHITE,
                  rect.center, anchor="center", shadow=False)
        # timeline with the incident markers, right under the banner (the bottom belongs to the chat and gaps)
        bar = pygame.Rect(SCREEN_WIDTH // 2 - 300, rect.bottom + 6, 600, 64)
        draw_panel(screen, bar, PANEL, 230)
        line = self._line = pygame.Rect(bar.x + 16, bar.y + 14, bar.w - 32, 8)
        pygame.draw.rect(screen, (55, 55, 64), line, border_radius=4)
        span = max(1e-6, last - first)

        def x_of(t: float) -> int:
            return int(line.x + line.w * (t - first) / span)

        pygame.draw.rect(screen, (220, 40, 40), (line.x, line.y, x_of(self.cursor) - line.x, line.h),
                         border_radius=4)
        for t, car, kind, _ in self.markers:
            if t >= first:
                pygame.draw.rect(screen, MARK_COLORS.get(kind, WHITE), (x_of(t) - 1, line.y - 5, 3, line.h + 10))
        pygame.draw.circle(screen, WHITE, (x_of(self.cursor), line.centery), 9 if self.dragging else 7)
        near = [m for m in self.markers if abs(m[0] - self.cursor) < 3.0]
        if near:
            t, car, kind, text = min(near, key=lambda m: abs(m[0] - self.cursor))
            who = f"{car.short}: " if car is not None else ""
            draw_text(screen, f"{who}{text}", f.tiny, MARK_COLORS.get(kind, WHITE), (bar.centerx, bar.y + 28),
                      anchor="midtop", shadow=False)
        draw_text(screen, f"{first - live:.0f} s", f.tiny, GREY, (line.x, bar.y + 28), shadow=False)
        draw_text(screen, "LIVE", f.tiny, GREY, (line.right, bar.y + 28), anchor="topright", shadow=False)
        draw_text(screen, "LEER Play/Pause · Punkt ziehen · <-/-> 5 s · ,/. Tempo · Q/E Vorfall · R/ESC zurück",
                  f.tiny, (180, 180, 190), (bar.centerx, bar.bottom - 18), anchor="midtop", shadow=False)

