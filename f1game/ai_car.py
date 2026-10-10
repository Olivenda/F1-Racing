# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Sequence

from .car import Car
from .neural import NeuralNetwork
from .sensors import compute_inputs
from .settings import AI_CONTROL_INTERVAL, BRAKE_DECEL, CAR_LENGTH, CAR_WIDTH
from .utils import wrap_angle

if TYPE_CHECKING:
    from .profiles import DriverProfile
    from .sessions import Session
    from .track import Track


class NeuralDriver:

    def __init__(self, car: Car, network: NeuralNetwork, marshal: bool = True) -> None:
        self.car = car
        self.net = network
        self.marshal = marshal
        self.inputs: list[float] = []
        self.outputs: list[float] = [0.0, 0.0]
        self.timer = random.uniform(0.0, AI_CONTROL_INTERVAL)
        self.start_delay = random.uniform(0.15, 0.35)
        self.stuck_timer = 0.0
        self.wrong_way_timer = 0.0

    def update(self, dt: float, others: Sequence[Car], track: "Track", race_start: bool = False
               ) -> tuple[float, float, float]:
        car = self.car
        if race_start and self.start_delay > 0:
            self.start_delay -= dt
            return 0.0, 1.0, 0.0
        if self.marshal and self._marshal_check(dt, track):
            return 0.0, 0.0, 0.0

        self.timer -= dt
        if self.timer <= 0.0:
            self.timer += AI_CONTROL_INTERVAL
            self.inputs = compute_inputs(car, others, track)
            if car.tyres is not None and track.wetness > 0.02:
                # the nets were trained in the dry: on a wet track they "feel" faster than they are, so they
                # brake earlier and carry the speed the lower grip allows (corner speed ~ sqrt(grip))
                g = car.tyres.compound.wet_factor(track.wetness)
                if g < 0.99:
                    self.inputs[0] /= math.sqrt(max(0.3, g))
            self.outputs = self.net.forward(self.inputs)
        steer, pedal = self.outputs
        return max(0.0, pedal), max(0.0, -pedal), steer

    def _marshal_check(self, dt: float, track: "Track") -> bool:
        car = self.car
        tan = track.tangents[car.idx]
        backwards = abs(wrap_angle(car.heading - math.atan2(tan.y, tan.x))) > math.radians(110)
        self.stuck_timer = self.stuck_timer + dt if car.vel.length() < 15.0 else 0.0
        self.wrong_way_timer = self.wrong_way_timer + dt if backwards else 0.0
        if self.stuck_timer > 2.5 or self.wrong_way_timer > 2.0:
            car.respawn()
            self.stuck_timer = self.wrong_way_timer = 0.0
            return True
        return False


class AI_Car(Car):

    def __init__(self, profile: "DriverProfile", track: "Track", network: NeuralNetwork,
                 engine_factor: float = 1.0, marshal: bool = True) -> None:
        super().__init__(profile, track)
        self.engine_factor = engine_factor
        self.driver = NeuralDriver(self, network, marshal)
        self.sees_others = True

    def control(self, dt: float, session: "Session") -> None:
        others = session.cars if self.sees_others else ()
        self.throttle, self.brake, self.steer_input = self.driver.update(
            dt, others, self.track, race_start=session.is_race_start_phase)
        if others and self.collide_cars:
            # the first lap is the crowded one: more caution until the field has spread out
            caution = 1.5 if session.kind == "race" and self.laps_done == 0 else 1.0
            self._racecraft(dt, others, caution)

    # ------------------------------------------------------------------ racecraft
    # The nets only learned to be fast; this layer makes them fair: they lift (and only then brake) instead of
    # running into the car ahead, leave a car's width when side by side, never turn in on a car alongside and give
    # human drivers extra room.
    LOOK_TIME: float = 0.8          # look ahead this many seconds of travel for cars in the way
    TTC_AI: float = 0.55            # react when contact with the car ahead is closer than this (s)
    TTC_HUMAN: float = 1.2          # ...and earlier when it is a human driver
    ROOM_AI: float = 6.0            # extra lateral clearance (px) on top of a car's width
    ROOM_HUMAN: float = 18.0

    _rc_timer = 0.0
    _rc_lift = 0.0
    _rc_brake = 0.0
    _rc_steer = 0.0
    _rc_side = 0.0                  # +1/-1: a car alongside on that side (don't turn into it), 0: none

    def _racecraft(self, dt: float, others: Sequence[Car], caution: float) -> None:
        self._rc_timer -= dt
        if self._rc_timer <= 0.0:
            self._rc_timer = AI_CONTROL_INTERVAL
            self._rc_lift, self._rc_brake, self._rc_steer, self._rc_side = self._assess(others, caution)
        if self._rc_lift > 0.0:
            self.throttle = min(self.throttle, max(0.0, 1.0 - self._rc_lift))
        if self._rc_brake > 0.0:
            self.brake = max(self.brake, self._rc_brake)
        if self._rc_side and self.steer_input * self._rc_side > 0:
            self.steer_input *= 0.35            # a car alongside on that side: don't turn in on it
        if self._rc_steer:
            hw = self.track.half_width - 14.0
            lat = self.lateral
            # never steer itself off the road to make room
            if not ((self._rc_steer > 0 and lat > hw) or (self._rc_steer < 0 and lat < -hw)):
                self.steer_input = max(-1.0, min(1.0, self.steer_input + self._rc_steer))

    def _assess(self, others: Sequence[Car], caution: float) -> tuple[float, float, float, float]:
        L = self.track.length
        v = max(0.0, self.speed_fwd)
        look = CAR_LENGTH + v * self.LOOK_TIME * caution
        lift, brake, steer, side = 0.0, 0.0, 0.0, 0.0
        for o in others:
            if o is self or o.is_ghost or not o.collide_cars or o.pit_state is not None or o.dnf:
                continue
            ds = (o.s - self.s + L / 2) % L - L / 2
            if ds < -CAR_LENGTH * 1.5 or ds > look:
                continue
            dlat = o.lateral - self.lateral
            human = o.is_player
            room = CAR_WIDTH + (self.ROOM_HUMAN if human else self.ROOM_AI) * caution
            away = -1.0 if dlat > 0 else 1.0           # steer away from the other car's side
            if ds > CAR_LENGTH * 0.6:
                # in front: only matters when it is in our lane
                if abs(dlat) >= room:
                    continue
                gap = ds - CAR_LENGTH
                closing = v - max(0.0, o.speed_fwd)
                limit = (self.TTC_HUMAN if human else self.TTC_AI) * caution
                if gap < 5.0:
                    lift, brake = 1.0, max(brake, 0.6)
                elif closing > 0.0 and gap / closing < limit:
                    need = 1.0 - (gap / closing) / limit          # 0 = just noticed .. 1 = about to hit
                    lift = max(lift, min(1.0, 0.4 + need))
                    # brake as hard as the remaining gap really needs (with a margin for humans)
                    margin = 8.0 + (10.0 if human else 0.0) * caution
                    required = closing * closing / (2.0 * max(1.0, gap - margin))
                    brake = max(brake, min(1.0, required / (BRAKE_DECEL * 0.55)))
                    if o.brake > 0.2 and gap < closing * limit + 25.0:
                        brake = max(brake, min(1.0, o.brake))       # the car ahead brakes: so do we
                # line up the pass on the free side instead of pushing from behind; closing fast (slipstream)
                # means pulling out properly
                pull = 0.32 if closing > 30.0 else 0.15
                steer += pull * away * (1.0 - abs(dlat) / room)
            elif abs(dlat) < room + 8.0:
                # alongside (or just behind and overlapping): leave a car's width, don't squeeze
                squeeze = 1.0 - abs(dlat) / (room + 8.0)
                steer += (0.45 if human else 0.3) * away * squeeze
                side = 1.0 if dlat > 0 else -1.0
                if human and ds > 0.0 and squeeze > 0.35:
                    lift = max(lift, 0.5)                     # a human slightly ahead: concede the corner
        return lift, brake, max(-0.6, min(0.6, steer)), side
