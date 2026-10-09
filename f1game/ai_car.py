# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Sequence

from .car import Car
from .neural import NeuralNetwork
from .sensors import compute_inputs
from .settings import AI_CONTROL_INTERVAL
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
