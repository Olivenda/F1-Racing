# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from .car import build_car_sprite
from .settings import TOP_SPEED, YELLOW

if TYPE_CHECKING:
    from .car import Car
    from .sessions import RaceSession

SC_SPEED = 0.42
SC_LAPS = 2
GAP_TARGET = 95.0
CATCH_UP = 0.80
FOLLOW_GAIN = 1.6
VSC_SPEED = 0.58
COOLDOWN = 60.0
YELLOW_TIME = 12.0
PUNCTURE_WEAR = 0.88
GIVE_BACK_TIME = 15.0
GRACE = 1.5


class SafetyCar:

    def __init__(self, session: "RaceSession", s: float) -> None:
        self.track = session.track
        self.s = s % self.track.length
        self.speed = 0.0
        self.pos = Vector2()
        self.heading = 0.0
        self.color = (225, 228, 235)
        self.profile = SimpleNamespace(helmet=(255, 150, 0), name="Safety Car", team="FIA")
        self.short = "SC"
        self.name = "Safety Car"
        self.is_player = False
        self.is_ghost = False
        self._sprite = build_car_sprite(self.color, (255, 150, 0))
        self._place()

    def _place(self) -> None:
        t = self.track
        i = int(self.s / t.WAYPOINT_SPACING) % t.n
        self.pos, self.heading = t.pose_at(self.s, t.line_offset[i] if t.line_offset else 0.0)

    def update(self, h: float, target_speed: float) -> None:
        self.speed += max(-400.0 * h, min(250.0 * h, target_speed - self.speed))
        self.s = (self.s + self.speed * h) % self.track.length
        self._place()

    def draw(self, surface: pygame.Surface, cam: Vector2, t: float) -> None:
        sp = self.pos - cam
        if not (-60 < sp.x < surface.get_width() + 60 and -60 < sp.y < surface.get_height() + 60):
            return
        img = pygame.transform.rotate(self._sprite, -math.degrees(self.heading))
        surface.blit(img, img.get_rect(center=(round(sp.x), round(sp.y))))
        if int(t * 6) % 2 == 0:
            r = Vector2(-math.sin(self.heading), math.cos(self.heading))
            for side in (-1, 1):
                pygame.draw.circle(surface, (255, 160, 0), sp + r * side * 4, 3)


class RaceControl:
    def __init__(self, session: "RaceSession", enabled: bool) -> None:
        self.s = session
        self.enabled = enabled
        self.mode: str | None = None
        self.phase = ""
        self.sc: SafetyCar | None = None
        self.until = 0.0
        self.sc_end_lap = 0
        self.cooldown_until = 0.0
        self.yellow: dict[int, float] = {}
        self.periods: list[str] = []
        self._period_start = 0
        self._restart_lap = 0
        self._puncture_timer = 0.0
        self.give_back: dict[tuple, float] = {}
        self._pending: dict[tuple, float] = {}
        self._order: dict = {}
        self._order_timer = 0.0
        self._since = 0.0

    @property
    def active(self) -> bool:
        return self.mode is not None

    def sector_of(self, car: "Car") -> int:
        return min(2, int((car.s % self.s.track.length) / self.s.track.length * 3))

    def _leader(self) -> "Car | None":
        order = [c for c in self.s.standings() if not c.session_done and not c.dnf]
        return order[0] if order else None

    def _can_start(self) -> bool:
        s = self.s
        leader = self._leader()
        return (self.enabled and s.race_started and not self.active and s.time >= self.cooldown_until
                and leader is not None and leader.laps_done >= 1 and s.total_laps - leader.laps_done > 2
                and s.winner_time is None)

    def incident(self, car: "Car", severity: str) -> None:
        s = self.s
        sector = self.sector_of(car)
        self.yellow[sector] = s.time + YELLOW_TIME
        if not self._can_start():
            return
        if severity == "dnf":
            self.deploy("SC" if random.random() < 0.65 else "VSC", f"{car.short} steht auf der Strecke")
        elif car.damage.total > 0.5 and random.random() < 0.5:
            self.deploy("SC", f"schwerer Unfall von {car.short}")
        elif random.random() < 0.25:
            self.deploy("VSC", f"Trümmer nach Unfall von {car.short}")

    def deploy(self, mode: str, reason: str) -> None:
        s = self.s
        leader = self._leader()
        if leader is None:
            return
        self.mode = mode
        self._period_start = leader.laps_done + 1
        if mode == "SC":
            self.sc = SafetyCar(s, leader.s + 380.0)
            self.sc.speed = leader.speed_fwd
            self.phase = "out"
            self.sc_end_lap = leader.laps_done + SC_LAPS
            s.stewards.announce(f"SAFETY CAR - {reason}", "investigation", 8.0)
            s.message("SAFETY CAR - nicht überholen!", YELLOW, 3.5)
        else:
            self.until = s.time + random.uniform(25.0, 40.0)
            s.stewards.announce(f"VIRTUAL SAFETY CAR - {reason}", "investigation", 8.0)
            s.message("VIRTUAL SAFETY CAR - Tempo reduzieren", YELLOW, 3.5)
        s.add_feed(f"{'SAFETY CAR' if mode == 'SC' else 'VSC'}: {reason}")
        self._since = s.time
        self._order = {}
        self._pending = {}
        self._cheap_stops()

    def _cheap_stops(self) -> None:
        s = self.s
        for car in s.cars:
            if car.dnf or car.session_done or car.in_pit or car.pit_request is not None or car.tyres is None:
                continue
            remaining = s.total_laps - car.laps_done
            if car is s.player:
                if remaining > 2:
                    s.message("Günstiger Stopp unter Neutralisation möglich (B)", (255, 200, 40), 3.0)
                continue
            if car.tyres.wear > 0.3 and remaining > 3:
                car.pit_request = s._compound_for_laps(remaining - 1)

    def _end(self) -> None:
        s = self.s
        leader = self._leader()
        lap = leader.laps_done if leader else self._period_start
        self.periods.append(f"{self.mode} Runde {self._period_start}-{max(self._period_start, lap)}")
        s.stewards.announce("GRÜNE FLAGGE - Rennen freigegeben", "info", 6.0)
        s.message("GRÜN! RESTART!" if self.mode == "SC" else "VSC ENDE - GRÜN!", (60, 220, 90), 2.5)
        self.mode = None
        self.phase = ""
        self.sc = None
        self.cooldown_until = s.time + COOLDOWN

    def step(self, h: float) -> None:
        s = self.s
        now = s.time
        self.yellow = {k: v for k, v in self.yellow.items() if v > now}
        self._punctures(h)
        self._order_timer -= h
        if self._order_timer <= 0 and (self.active or self.give_back):
            self._order_timer = 0.25
            self._check_overtakes()
        if self.mode == "VSC" and now >= self.until:
            self._end()
        elif self.mode == "SC":
            self._sc_step(h)

    def _sc_step(self, h: float) -> None:
        s, sc = self.s, self.sc
        leader = self._leader()
        top = TOP_SPEED
        if self.phase in ("out", "in") and sc is None:
            self.phase = "restart"
            self._restart_lap = leader.laps_done if leader else 0
        if self.phase == "out" and sc is not None:
            sc.update(h, top * SC_SPEED)
            if leader is not None and leader.laps_done >= self.sc_end_lap:
                self.phase = "in"
                s.message("SAFETY CAR IN THIS LAP", YELLOW, 3.0)
                s.add_feed("Safety Car kommt in dieser Runde rein")
        elif self.phase == "in" and sc is not None:
            sc.update(h, top * SC_SPEED)
            pit = s.track.pit
            entry = pit.entry_abs() if pit is not None else 0.0
            if (sc.s - entry) % s.track.length < 30.0:
                self.phase = "restart"
                self.sc = None
                self._restart_lap = leader.laps_done if leader else 0
        elif self.phase == "restart":
            if leader is None or leader.laps_done > self._restart_lap:
                self._end()

    def governor(self, car: "Car") -> None:
        if not self.active or car.in_pit or car.session_done or car.frozen:
            return
        top = car.top_speed
        if self.mode == "VSC":
            target = top * VSC_SPEED
        else:
            target = self._follow_target(car, top)
        if self.must_yield(car) and car is not self.s.player:
            target *= 0.5
        v = car.speed_fwd
        if v > target + 4.0:
            car.throttle = 0.0
            car.brake = max(car.brake, min(1.0, (v - target) / 90.0))
        elif v > target - 15.0:
            car.throttle = min(car.throttle, 0.25)
        car.straight_mode = False

    def _follow_target(self, car: "Car", top: float) -> float:
        s = self.s
        L = s.track.length
        best_gap, best_speed = None, 0.0
        yielding = {a for a, b in self.give_back if b is car}
        objects = [(o.s, o.speed_fwd) for o in s.cars if o is not car and not o.in_pit and not o.dnf
                   and not o.session_done and o not in yielding]
        if self.sc is not None:
            objects.append((self.sc.s, self.sc.speed))
        for os_, ov in objects:
            gap = (os_ - car.s) % L
            if 5.0 < gap < 900.0 and (best_gap is None or gap < best_gap):
                best_gap, best_speed = gap, ov
        if best_gap is None:
            limit = top * SC_SPEED if self.phase == "restart" else top * CATCH_UP
            return limit
        target = best_speed + FOLLOW_GAIN * (best_gap - GAP_TARGET)
        return max(top * 0.20, min(top * CATCH_UP, target))

    @staticmethod
    def _racing(car: "Car") -> bool:
        return not (car.in_pit or car.dnf or car.session_done or car.puncture or car.frozen or car.is_ghost)

    def _fair_victim(self, b: "Car") -> bool:
        return self._racing(b) and not self.must_yield(b) and b.pit_request is None and b.speed_fwd > 60.0

    PASS_MARGIN = 26.0
    PASS_HOLD = 1.0

    def _check_overtakes(self) -> None:
        s = self.s
        now = s.time
        order = {c: k for k, c in enumerate(s.standings())}
        for (a, b), deadline in list(self.give_back.items()):
            if order[a] > order[b]:
                del self.give_back[(a, b)]
                s.stewards.announce(f"{a.short} hat die Position an {b.short} zurückgegeben", "info", 5.0)
                if a is s.player:
                    s.message("Position zurückgegeben - keine Strafe", (60, 220, 90), 2.5)
            elif not self._racing(b) or a.dnf or a.session_done:
                del self.give_back[(a, b)]
            elif now >= deadline:
                del self.give_back[(a, b)]
                s.stewards.penalty(a, 5.0, f"unter {self.mode or 'Safety Car'} {b.short} überholt")
        if self.active and now - self._since > GRACE and self._order:
            for a, ka in order.items():
                kb_prev = self._order.get(a)
                if kb_prev is None or ka >= kb_prev or not self._racing(a):
                    continue
                for b, kb in order.items():
                    if b is a or (a, b) in self.give_back or not self._fair_victim(b):
                        continue
                    prev_a, prev_b = self._order.get(a), self._order.get(b)
                    if prev_b is not None and prev_a > prev_b and ka < kb and a.laps_done >= b.laps_done:
                        self._pending.setdefault((a, b), now)
            for (a, b), since in list(self._pending.items()):
                if order.get(a, 0) > order.get(b, 0) or not self._racing(a) or not self._fair_victim(b):
                    del self._pending[(a, b)]
                elif a.distance - b.distance > self.PASS_MARGIN and now - since >= self.PASS_HOLD:
                    del self._pending[(a, b)]
                    self.give_back[(a, b)] = now + GIVE_BACK_TIME
                    s.stewards.announce(f"Überholen unter {self.mode}: {a.short} muss Platz an {b.short} "
                                        "zurückgeben", "investigation", 6.0)
                    if a is s.player:
                        s.message(f"Unter {self.mode} überholt! Lass {b.short} vorbei ({GIVE_BACK_TIME:.0f} s)",
                                  (255, 140, 30), 4.0)
                    elif b is s.player:
                        s.message(f"{a.short} hat dich unter {self.mode} überholt - er muss zurückgeben",
                                  YELLOW, 3.0)
        self._order = {c: k for c, k in order.items() if self._racing(c)}

    def must_yield(self, car: "Car") -> bool:
        return any(a is car for a, _ in self.give_back)

    def _punctures(self, h: float) -> None:
        self._puncture_timer -= h
        if self._puncture_timer > 0:
            return
        self._puncture_timer = 0.5
        s = self.s
        for car in s.cars:
            t = car.tyres
            if t is None or car.puncture or car.in_pit or car.session_done or car.dnf:
                continue
            if t.wear > PUNCTURE_WEAR and random.random() < 0.5 * 0.08 * (t.wear - PUNCTURE_WEAR) / (1 - PUNCTURE_WEAR):
                self.puncture(car, "abgefahrener Reifen")

    def puncture(self, car: "Car", why: str) -> None:
        s = self.s
        car.puncture = True
        s.add_feed(f"REIFENSCHADEN: {car.short} ({why})")
        self.yellow[self.sector_of(car)] = s.time + YELLOW_TIME * 0.5
        if car is s.player:
            s.message("REIFENSCHADEN! Sofort an die Box (B)", (255, 80, 80), 4.0)
            if car.pit_request is None:
                car.pit_request = car.tyres.compound.key if car.tyres else "medium"
        elif car.pit_request is None:
            remaining = s.total_laps - car.laps_done
            car.pit_request = s._compound_for_laps(max(1, remaining - 1))
