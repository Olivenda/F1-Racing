# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

from typing import TYPE_CHECKING

from .settings import CAR_LENGTH, CAR_WIDTH, ORANGE, YELLOW

if TYPE_CHECKING:
    from pygame.math import Vector2

    from .car import Car
    from .sessions import Session

WARNINGS = 5
TL_MARGIN = CAR_WIDTH * 1.0
TL_MIN_TIME = 0.45
ADVANTAGE_RATIO = 0.97
TL_PENALTY_EVERY = 5
CONTACT_THRESHOLD = 200.0
HARD_CONTACT = 340.0
DECISION_DELAY = 4.0


class Stewards:
    def __init__(self, session: "Session") -> None:
        self.session = session
        self.log: list[list] = []
        self.pending: list[tuple[float, "Car", "Car", float]] = []
        self._pair_cooldown: dict[tuple[int, int], float] = {}
        self.penalties_issued = 0

    def announce(self, text: str, kind: str = "info", duration: float = 9.0) -> None:
        self.log.append([text, duration, kind])
        self.log = self.log[-4:]

    def tick(self, frame_dt: float) -> None:
        for entry in self.log:
            entry[1] -= frame_dt
        self.log = [e for e in self.log if e[1] > 0]

    @property
    def racing(self) -> bool:
        s = self.session
        return s.kind == "race" and getattr(s, "race_started", False)

    def update(self) -> None:
        now = self.session.time
        for car in self.session.cars:
            self._track_limits(car, now)
        due = [p for p in self.pending if p[0] <= now]
        self.pending = [p for p in self.pending if p[0] > now]
        for _, culprit, victim, impulse in due:
            seconds = 10.0 if impulse >= HARD_CONTACT else 5.0
            self.penalty(culprit, seconds, f"Kollision mit {victim.short} verursacht")

    def _track_limits(self, car: "Car", now: float) -> None:
        if car.in_pit or car.is_ghost or car.frozen or car.session_done:
            car.tl_off = False
            return
        hw = self.session.track.half_width
        lat = abs(car.lateral)
        if not car.tl_off:
            if lat > hw + TL_MARGIN and car.speed_fwd > 60:
                car.tl_off = True
                car.tl_since = now
                car.tl_forced = now - car.last_contact_time < 2.0
                car.tl_distance = car.distance
                car.tl_speed = car.speed_fwd
        elif lat < hw:
            car.tl_off = False
            duration = now - car.tl_since
            if not car.tl_forced and duration >= TL_MIN_TIME:
                progress_rate = (car.distance - car.tl_distance) / duration
                if progress_rate > car.tl_speed * ADVANTAGE_RATIO:
                    self._violation(car)

    def _violation(self, car: "Car") -> None:
        s = self.session
        car.lap_invalid = True
        if s.kind != "race":
            if car is s.player:
                s.message("TRACK LIMITS - Runde gestrichen", ORANGE, 2.5)
            return
        if not self.racing:
            return
        car.tl_count += 1
        n = car.tl_count
        if n < WARNINGS:
            if car is s.player:
                s.message(f"Track Limits - Verwarnung {n}/{WARNINGS}", YELLOW, 2.0)
        elif n == WARNINGS:
            self.announce(f"Schwarz-weiße Flagge: {car.short} (Track Limits)", "investigation")
            if car is s.player:
                s.message("SCHWARZ-WEISSE FLAGGE - nächster Verstoß wird bestraft", (240, 240, 240), 3.0)
        elif (n - WARNINGS) % TL_PENALTY_EVERY == 1:
            self.penalty(car, 5.0, "wiederholte Track-Limits-Verstöße")

    def on_contact(self, a: "Car", b: "Car", impulse: float, contact: "Vector2") -> None:
        now = self.session.time
        a.last_contact_time = b.last_contact_time = now
        if not self.racing or impulse < CONTACT_THRESHOLD:
            return
        key = (min(id(a), id(b)), max(id(a), id(b)))
        if now - self._pair_cooldown.get(key, -1e9) < 6.0:
            return
        la = (contact - a.pos).dot(a.forward)
        lb = (contact - b.pos).dot(b.forward)
        front, rear = CAR_LENGTH * 0.25, CAR_LENGTH * 0.05
        if la > front and lb < rear:
            culprit, victim = a, b
        elif lb > front and la < rear:
            culprit, victim = b, a
        else:
            return
        self._pair_cooldown[key] = now
        self.pending.append((now + DECISION_DELAY, culprit, victim, impulse))
        self.announce(f"Untersuchung: Kollision {culprit.short} / {victim.short}", "investigation")

    def penalty(self, car: "Car", seconds: float, reason: str) -> None:
        s = self.session
        car.penalty_total += seconds
        if car.finish_time is not None and car.finish_time < 1e5:
            car.finish_time += seconds
        else:
            car.penalty_unserved += seconds
        self.penalties_issued += 1
        self.announce(f"{seconds:.0f}s Zeitstrafe: {car.short} - {reason}", "penalty")
        if car is s.player:
            s.message(f"{seconds:.0f} SEKUNDEN STRAFE - {reason}", ORANGE, 4.0)
