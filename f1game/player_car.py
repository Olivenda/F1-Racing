# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
import time
from array import array
from typing import TYPE_CHECKING

import pygame

from .ai_car import NeuralDriver
from .car import Car
from .neural import NeuralNetwork
from .profiles import RECORDING_DIR
from .sensors import compute_inputs
from .settings import AI_CONTROL_INTERVAL, BRAKE_DECEL
from .utils import approach

if TYPE_CHECKING:
    from .profiles import DriverProfile
    from .sessions import Session
    from .track import Track


class Player_Car(Car):

    STEER_IN_RATE: float = 6.0
    STEER_OUT_RATE: float = 10.0
    ASSIST_NAMES = ["Aus", "Mittel", "Voll"]
    MIN_SAMPLES_TO_SAVE: int = 300

    def __init__(self, profile: "DriverProfile", track: "Track") -> None:
        super().__init__(profile, track)
        self.is_player = True
        self.autopilot: NeuralDriver | None = None
        self.samples: list[array] = []
        self._rec_timer = 0.0
        self.assist_level = 1
        self.brake_assist_active = False
        self.aero_request = False
        self._fb_impulse = 0.0
        self.slot = 0               # split-screen player number (0 = player 1)
        self.keyset = "all"         # "all", "wasd" or "arrows"

    def set_assists(self, level: int) -> None:
        self.assist_level = level
        self.grip_bonus = (1.0, 1.04, 1.07)[level]

    def enable_autopilot(self, network: NeuralNetwork) -> None:
        if self.autopilot is None:
            self.autopilot = NeuralDriver(self, network)
            self.autopilot.start_delay = 0.0

    def control(self, dt: float, session: "Session") -> None:
        if self.autopilot is not None:
            self.throttle, self.brake, self.steer_input = self.autopilot.update(dt, session.cars, self.track)
            return
        up, down, left, right = self.held_keys()
        self.throttle = 1.0 if up else 0.0
        self.brake = 1.0 if down else 0.0
        target = (-1.0 if left else 0.0) + (1.0 if right else 0.0)
        controls = session.game.controls
        slot = self.slot
        pad_throttle, pad_brake = controls.pedal("throttle", slot), controls.pedal("brake", slot)
        if pad_throttle is not None:
            self.throttle = max(self.throttle, pad_throttle)
        if pad_brake is not None:
            self.brake = max(self.brake, pad_brake)
        analog = controls.steering(slot) if target == 0.0 else None
        speed_ratio = min(1.0, max(0.0, self.speed_fwd) / self.top_speed)
        wheel = controls.kind(slot) == "wheel"
        if analog is not None and (analog != 0.0 or wheel):
            if wheel:
                # a wheel is the steering: no filtering, the driver's hands are the rate limiter
                self.steer_input = analog
            else:
                # sticks get a little speed-sensitive softening so flicks at 300 km/h don't spin the car
                target = analog * (1.0 - 0.25 * speed_ratio)
                self.steer_input = approach(self.steer_input, target, self.STEER_OUT_RATE * 1.6 * dt)
        else:
            if abs(target) > abs(self.steer_input) or target * self.steer_input < 0:
                rate = self.STEER_IN_RATE * (1.0 - 0.45 * speed_ratio)
            else:
                rate = self.STEER_OUT_RATE
            self.steer_input = approach(self.steer_input, target, rate * dt)
        self._record(dt, session)
        self._apply_assists()
        self._feedback(controls)

    def held_keys(self) -> tuple[bool, bool, bool, bool]:
        """(throttle, brake, left, right) from this player's half of the keyboard."""
        keys = pygame.key.get_pressed()
        wasd = (keys[pygame.K_w], keys[pygame.K_s], keys[pygame.K_a], keys[pygame.K_d])
        arrows = (keys[pygame.K_UP], keys[pygame.K_DOWN], keys[pygame.K_LEFT], keys[pygame.K_RIGHT])
        if self.keyset == "wasd":
            return wasd
        if self.keyset == "arrows":
            return arrows
        return wasd[0] or arrows[0], wasd[1] or arrows[1], wasd[2] or arrows[2], wasd[3] or arrows[3]

    def throttle_held(self, controls) -> bool:
        return self.held_keys()[0] or controls.throttle_held(self.slot)

    def _feedback(self, controls) -> None:
        """Vibration / force jolts: impacts, gravel, kerb-like slides and wheelspin."""
        if not controls.has_device(self.slot):
            return
        hit = self.wall_impulse + self.car_impulse - self._fb_impulse
        self._fb_impulse = self.wall_impulse + self.car_impulse
        if hit > 20:
            k = min(1.0, hit / 250.0)
            controls.rumble(k, k, 120 + int(200 * k), self.slot)
        elif self.on_grass and self.speed_fwd > 30:
            controls.rumble(0.35, 0.15, 90, self.slot)
        elif self.sliding and self.speed_fwd > 60:
            controls.rumble(0.0, 0.3, 70, self.slot)
        elif self.launch_spin > 0.0 and self.throttle > 0.5:
            controls.rumble(0.25, 0.0, 70, self.slot)

    def _apply_assists(self) -> None:
        self.brake_assist_active = False
        if self.assist_level >= 1:
            self.steer_input = max(-1.0, min(1.0, self.steer_input - self.spin * 0.35))
        track = self.track
        if self.assist_level >= 2 and track.max_speed and not self.on_grass:
            grip_scale = (self.performance()["grip"] * self.grip_bonus) ** 0.5
            decel = BRAKE_DECEL * self.performance()["brake"] * 0.85
            n, step = track.n, track.WAYPOINT_SPACING
            allowed = 1e9
            for k in range(0, 70, 2):
                v_corner = track.max_speed[(self.idx + k) % n] * grip_scale
                allowed = min(allowed, (v_corner * v_corner + 2.0 * decel * k * step) ** 0.5)
            if self.speed_fwd > allowed + 4.0:
                self.brake = max(self.brake, min(1.0, max(0.35, (self.speed_fwd - allowed) / 50.0)))
                self.throttle = 0.0
                self.brake_assist_active = True

    def _record(self, dt: float, session: "Session") -> None:
        self._rec_timer -= dt
        if self._rec_timer > 0 or self.speed_fwd < 5.0 or self.is_ghost:
            return
        self._rec_timer += AI_CONTROL_INTERVAL
        x = compute_inputs(self, session.cars, self.track)
        self.samples.append(array("f", x + [self.steer_input, self.throttle - self.brake]))

    def save_recording(self, session_kind: str) -> None:
        if len(self.samples) < self.MIN_SAMPLES_TO_SAVE:
            return
        RECORDING_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        data = {"track": self.track.definition.key, "session": session_kind, "best_lap": self.best_lap,
                "samples": [[round(v, 4) for v in row] for row in self.samples]}
        (RECORDING_DIR / f"{stamp}-{self.track.definition.key}.json").write_text(
            json.dumps(data, separators=(",", ":")), encoding="utf-8")
        self.samples = []
