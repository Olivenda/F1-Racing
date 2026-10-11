# Copyright Olivenda (Oliver Petz) 2026
"""Formation lap: the field leaves the grid in order, follows the pole sitter round at a gentle pace and lines up
on its grid slots again - then the start lights."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .race_control import hold_speed
from .settings import TOP_SPEED

if TYPE_CHECKING:
    from .car import Car
    from .sessions import RaceSession

GO_AT = 3.0             # seconds after the session start the field pulls away
PACE = 0.50             # share of top speed the formation lap is driven at
CATCH_UP = 1.25         # a car with a gap to the one ahead may go this much faster to close it
FOLLOW_GAP = 70.0       # px to the car ahead
FOLLOW_GAIN = 1.6
APPROACH = 700.0        # px before its grid slot a car starts to think about stopping there
STOP_DECEL = 90.0       # px/s² the approach speed profile brakes with (gentle: the cars brake harder than that)
STOP_GAIN = 2.5         # 1/s: the last metres the speed falls with the distance left (a glide onto the slot)
STEER_ZONE = 500.0      # px before the slot the driven cars steer onto the slot's line
PARK_DIST = 12.0        # closer than this to the slot (and slow): parked
PARK_SPEED = 20.0
PARK_NOW = 4.0          # this close to the slot a car is parked whatever its speed
STALLED = 3.0           # s a car stands still for no reason (nobody close ahead) before the others pass it
STALL_CLEAR = 250.0     # px: with no car closer ahead than this, standing still has no reason
HUMAN_IDLE = 12.0       # s after the field pulls away: a human still on the grid skips the lap
HUMAN_PARK_DIST = 60.0  # a human driver who has (nearly) stopped this close to the slot is parked too
HUMAN_PARK_SPEED = 15.0
OVERSHOOT = 40.0        # a car that rolls this far past its slot is put back on it


class FormationLap:

    def __init__(self, session: "RaceSession") -> None:
        self.s = session
        t = session.track
        self.slots: dict = {}
        for car in session.cars:
            pos, heading = t.grid_pose(car.grid_slot - 1)
            _, ss, lat = t.project(pos)
            self.slots[car] = (pos, heading, ss, lat)
        self.started = False
        self.done = False
        self.parked: set = set()
        self._start_dist: dict = {}
        self._fuel = {c: c.fuel for c in session.cars}
        self._t0 = 0.0
        self._still: dict = {}      # car -> seconds it has stood still for no reason
        # nobody needs longer than this (a car stuck somewhere is put on its slot)
        self._timeout = max(60.0, t.length / (TOP_SPEED * 0.85) / PACE * 2.2)

    @property
    def running(self) -> bool:
        return self.started and not self.done

    def step(self, h: float) -> None:
        s = self.s
        if not self.started:
            if s.time >= GO_AT:
                self.started = True
                self._t0 = s.time
                for car in s.cars:
                    if not car.dnf:
                        car.frozen = False
                        self._start_dist[car] = car.distance
                s.message("EINFÜHRUNGSRUNDE - nicht überholen, zurück auf deinen Startplatz"
                          if s.player is not None else "EINFÜHRUNGSRUNDE", (60, 220, 90), 4.0)
            return
        if self.done:
            return
        late = s.time - self._t0 > self._timeout
        for car in s.cars:
            if car in self.parked or car.dnf:
                continue
            self._track_stall(car, h)
            rem = self._remaining(car)
            if late or rem is not None and (rem < PARK_DIST and car.speed_fwd < PARK_SPEED or rem < PARK_NOW or
                                            self._human(car) and rem < HUMAN_PARK_DIST and
                                            car.speed_fwd < HUMAN_PARK_SPEED or
                                            rem > s.track.length - OVERSHOOT):
                self._park(car)
            elif self._human(car) and s.time - self._t0 > HUMAN_IDLE and \
                    car.distance - self._start_dist.get(car, car.distance) < 40.0:
                # never pulled away: the lap goes on without them, they wait on their slot
                self._park(car)
                if car is s.player or car is s.player2:
                    s.message("Einführungsrunde ausgelassen - warte auf die Ampel", (255, 210, 40), 3.0)
        if all(c in self.parked or c.dnf for c in s.cars):
            self.done = True

    def _track_stall(self, car: "Car", h: float) -> None:
        """How long the car has been standing with nobody close ahead to wait for (stalled, spun, a human who
        doesn't drive) - the cars behind pass it after STALLED seconds instead of waiting for it."""
        if car.speed_fwd > 3.0:
            self._still[car] = 0.0
            return
        L = self.s.track.length
        for o in self.s.cars:
            if o is car or o.dnf or o in self.parked:
                continue
            if 5.0 < (o.s - car.s) % L < STALL_CLEAR:
                self._still[car] = 0.0          # queueing behind someone: a reason to stand
                return
        self._still[car] = self._still.get(car, 0.0) + h

    def stalled(self, car: "Car") -> bool:
        return self._still.get(car, 0.0) > STALLED

    @staticmethod
    def _human(car: "Car") -> bool:
        return car.is_player and getattr(car, "autopilot", None) is None

    def _remaining(self, car: "Car") -> float | None:
        """px to the car's grid slot - None until it has done most of the lap."""
        L = self.s.track.length
        if car.distance - self._start_dist.get(car, car.distance) < L * 0.5:
            return None
        return (self.slots[car][2] - car.s) % L

    def _park(self, car: "Car") -> None:
        """On the slot, standing, and everything the lap counted reset: the race starts from here."""
        pos, heading, _, _ = self.slots[car]
        car.place(pos, heading)
        car.frozen = True
        car.throttle = car.brake = car.steer_input = 0.0
        car.timing_started = False
        car.marker_times = {}
        car.last_marker = -10 ** 9
        car.current_splits = {}
        car.sectors = []
        car.lap_invalid = False
        car.vmax = car.lap_vmax = 0.0
        car.fuel = self._fuel.get(car, car.fuel)
        car.out_of_fuel = False
        car.auto_gear()
        self.parked.add(car)
        if car is self.s.player or car is self.s.player2:
            self.s.message(f"STARTPLATZ P{car.grid_slot} - warte auf die Ampel!", (255, 255, 255), 2.5)

    def control(self, car: "Car") -> None:
        """After the driver's own inputs: hold the formation pace, keep the gap, brake onto the grid slot."""
        s = self.s
        if not self.started or car in self.parked:
            return
        L = s.track.length
        top = car.top_speed
        rem = self._remaining(car)
        approaching = rem is not None and rem < APPROACH
        best_gap, best_v = None, 0.0
        for o in s.cars:
            # parked cars stand on their own slots (off the line), stalled ones get passed
            if o is car or o.dnf or o in self.parked or self.stalled(o):
                continue
            gap = (o.s - car.s + L / 2) % L - L / 2
            if 5.0 < gap < 700.0 and (best_gap is None or gap < best_gap):
                best_gap, best_v = gap, o.speed_fwd
        target = top * PACE
        if best_gap is not None:
            target = min(top * PACE * CATCH_UP, max(0.0, best_v + FOLLOW_GAIN * (best_gap - FOLLOW_GAP)))
        if approaching:
            # down to a standstill on the slot itself (a crawl is left only to cover the last few px)
            target = min(target, max(6.0, min(math.sqrt(2.0 * STOP_DECEL * max(0.0, rem - 2.0)), STOP_GAIN * rem)))
            v = car.speed_fwd
            if not self._human(car):
                # the last few hundred px are driven for the AI: onto the slot's line and down the speed profile
                # (its own driver would brake for the cars already standing in the next column)
                self._steer_to(car, self.slots[car][3], rem)
                if v > target + 3.0:
                    car.throttle = 0.0
                    car.brake = min(1.0, 0.25 + (v - target) / 30.0) if v > 8.0 else 0.0
                else:
                    car.throttle, car.brake = max(0.0, min(0.6, (target - v) / 40.0)), 0.0
                car.straight_mode = False
                return
            if v > target + 3.0:
                car.throttle = 0.0
                car.brake = max(car.brake, min(1.0, 0.25 + (v - target) / 30.0)) if v > 8.0 else 0.0
                car.straight_mode = False
                return
        if target < 2.0:
            # waiting for the car ahead to pull away (no brake at a standstill: that would be reverse)
            car.throttle, car.brake = 0.0, (1.0 if car.speed_fwd > 8.0 else 0.0)
            car.straight_mode = False
            return
        hold_speed(car, target)

    def _steer_to(self, car: "Car", lat: float, rem: float) -> None:
        if rem > STEER_ZONE:
            return
        t = self.s.track
        lat_rate = car.vel.dot(t.normals[car.idx])
        steer = 0.016 * (lat - car.lateral) - 0.02 * lat_rate
        car.steer_input = max(-0.6, min(0.6, steer))
