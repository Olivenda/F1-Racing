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
# a contact is judged by the impulse it adds up to (physics splits a hit over several steps): a light touch
# stays below the threshold, a real hit (~150 px/s faster into the car ahead) is well over the hard limit
CONTACT_THRESHOLD = 90.0
HARD_CONTACT = 180.0
CONTACT_WINDOW = 0.5        # s: impulses of a pair this close together are one contact
DECISION_DELAY = 4.0
SERVE_LAPS = 3              # a drive-through / stop & go has to be served within this many laps
STOP_GO_TIME = 10.0
# not served before the flag: the time added instead (as in F1)
DRIVE_PENALTY_TIME = {"DT": 20.0, "SG": 30.0}
DRIVE_PENALTY_NAME = {"DT": "Drive-Through", "SG": "Stop & Go"}
WARNINGS_PER_PENALTY = 3    # every third official warning brings a 5 s penalty
INCIDENT_LOG = 30           # incidents kept per car
ANNOUNCE_COLORS = {"info": (220, 220, 225), "investigation": YELLOW, "penalty": ORANGE}


class Stewards:
    def __init__(self, session: "Session") -> None:
        self.session = session
        self.log: list[list] = []
        self.pending: list[tuple[float, "Car", "Car", float]] = []
        self._pair_cooldown: dict[tuple[int, int], float] = {}
        self._contact: dict[tuple[int, int], list[float]] = {}     # pair -> [impulse so far, last touch]
        self.penalties_issued = 0
        self.director = None            # race director (spectator): may take over the decisions

    def announce(self, text: str, kind: str = "info", duration: float = 9.0) -> None:
        self.log.append([text, duration, kind])
        self.log = self.log[-4:]
        log_chat = getattr(self.session, "log_chat", None)
        if log_chat is not None:
            log_chat(text, ANNOUNCE_COLORS.get(kind, (220, 220, 225)))

    def log_incident(self, car: "Car", kind: str, text: str) -> None:
        """Keep a car's history for the race director: kind "cut", "col", "warn", "bw", "pen" or "info"."""
        car.incidents.append((car.laps_done + 1, kind, text))
        del car.incidents[:-INCIDENT_LOG]
        replay = getattr(self.session, "replay", None)
        if replay is not None and kind != "info":
            replay.mark(car, kind, text)

    def warn(self, car: "Car", reason: str) -> None:
        """An official warning; every WARNINGS_PER_PENALTY-th one brings a 5 s penalty (which a race director's
        assistant may hold as a suggestion like any other)."""
        s = self.session
        car.warnings += 1
        n = car.warnings
        self.log_incident(car, "warn", f"Verwarnung {n} - {reason}")
        self.announce(f"Verwarnung {n}: {car.short} - {reason}", "investigation")
        if car is s.player or car is getattr(s, "player2", None):
            s.message(f"VERWARNUNG ({n}) - {reason}", YELLOW, 3.0)
        if n % WARNINGS_PER_PENALTY == 0:
            self.penalty(car, 5.0, f"{n} Verwarnungen")

    def black_white(self, car: "Car", reason: str) -> None:
        s = self.session
        car.bw_until = s.time + 10.0
        car.bw_count += 1
        self.log_incident(car, "bw", f"Schwarz-weiße Flagge - {reason}")
        self.announce(f"Schwarz-weiße Flagge: {car.short} ({reason})", "investigation")

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
            if self.racing:
                car.tl_wide += 1
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
        self.log_incident(car, "cut", f"Track Limits mit Vorteil ({n})")
        if n < WARNINGS:
            if car is s.player:
                s.message(f"Track Limits - Verwarnung {n}/{WARNINGS}", YELLOW, 2.0)
        elif n == WARNINGS:
            self.black_white(car, "Track Limits")
            if car is s.player:
                s.message("SCHWARZ-WEISSE FLAGGE - nächster Verstoß wird bestraft", (240, 240, 240), 3.0)
        elif (n - WARNINGS) % TL_PENALTY_EVERY == 1:
            self.penalty(car, 5.0, "wiederholte Track-Limits-Verstöße")

    def on_contact(self, a: "Car", b: "Car", impulse: float, contact: "Vector2") -> None:
        now = self.session.time
        a.last_contact_time = b.last_contact_time = now
        if not self.racing:
            return
        key = (min(id(a), id(b)), max(id(a), id(b)))
        acc = self._contact.get(key)
        if acc is None or now - acc[1] > CONTACT_WINDOW:
            acc = self._contact[key] = [0.0, now]
        acc[0] += impulse
        acc[1] = now
        impulse = acc[0]
        if impulse < CONTACT_THRESHOLD:
            return
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
        culprit.contacts_caused += 1
        self.log_incident(culprit, "col", f"Kollision mit {victim.short} verursacht")
        self.pending.append((now + DECISION_DELAY, culprit, victim, impulse))
        self.announce(f"Untersuchung: Kollision {culprit.short} / {victim.short}", "investigation")

    def penalty(self, car: "Car", seconds: float, reason: str, auto: bool = True) -> None:
        """auto: the stewards' own decision - a race director may hold it as a suggestion or overrule it."""
        if auto and self.director is not None and self.director.intercept_penalty(car, seconds, reason):
            return
        s = self.session
        car.penalty_total += seconds
        if car.finish_time is not None and car.finish_time < 1e5:
            car.finish_time += seconds
        else:
            car.penalty_unserved += seconds
        self.penalties_issued += 1
        self.log_incident(car, "pen", f"{seconds:.0f}s Zeitstrafe - {reason}")
        self.announce(f"{seconds:.0f}s Zeitstrafe: {car.short} - {reason}", "penalty")
        if car is s.player:
            s.message(f"{seconds:.0f} SEKUNDEN STRAFE - {reason}", ORANGE, 4.0)

    def drive_penalty(self, car: "Car", kind: str, reason: str, auto: bool = True) -> None:
        """A drive-through ("DT") or 10 s stop & go ("SG"): into the pit lane within SERVE_LAPS laps (not under
        SC/VSC), black flag otherwise. A car that has finished gets the time instead."""
        if auto and self.director is not None and self.director.intercept_penalty(car, kind, reason):
            return
        s = self.session
        name = DRIVE_PENALTY_NAME[kind]
        if car.finish_time is not None:
            self.penalty(car, DRIVE_PENALTY_TIME[kind], f"{name} (nach dem Ziel) - {reason}", auto=False)
            return
        if car.drive_penalty is not None:
            # a second one on top: the stewards make it a stop & go
            kind, name = "SG", DRIVE_PENALTY_NAME["SG"]
        car.drive_penalty = kind
        car.drive_penalty_due = car.laps_done + SERVE_LAPS
        self.penalties_issued += 1
        self.log_incident(car, "pen", f"{name} - {reason}")
        self.announce(f"{name}: {car.short} - {reason}", "penalty")
        if car is s.player or car is getattr(s, "player2", None):
            s.message(f"{name.upper()} - in {SERVE_LAPS} Runden in die Box!", ORANGE, 4.0)

    def drive_penalty_served(self, car: "Car") -> None:
        name = DRIVE_PENALTY_NAME.get(car.drive_penalty or "", "Strafe")
        car.drive_penalty = None
        self.log_incident(car, "info", f"{name} abgesessen")
        self.announce(f"{car.short} hat die {name}-Strafe abgesessen", "info")
