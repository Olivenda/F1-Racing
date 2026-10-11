# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Sequence

from . import ai_pace
from .car import Car
from .neural import NeuralNetwork
from .sensors import INPUT_NAMES, compute_inputs
from .settings import AI_CONTROL_INTERVAL, BRAKE_DECEL, CAR_LENGTH, CAR_WIDTH, brake_decel
from .utils import wrap_angle

RADAR_FRONT = INPUT_NAMES.index("Radar VL")      # Radar VL, VM, VR

if TYPE_CHECKING:
    from .profiles import DriverProfile
    from .sessions import Session
    from .track import Track


class NeuralDriver:

    def __init__(self, car: Car, network: NeuralNetwork, marshal: bool = True) -> None:
        self.car = car
        self.net = network
        self.sc_net: NeuralNetwork | None = None    # trained to follow in line behind the safety car
        self.marshal = marshal
        self.inputs: list[float] = []
        self.outputs: list[float] = [0.0, 0.0]
        self.timer = random.uniform(0.0, AI_CONTROL_INTERVAL)
        self.start_delay = random.uniform(0.15, 0.35)
        self.stuck_timer = 0.0
        self.wrong_way_timer = 0.0

    def update(self, dt: float, others: Sequence[Car], track: "Track", race_start: bool = False,
               neutral: bool = False, hold: bool = False) -> tuple[float, float, float]:
        car = self.car
        if race_start and self.start_delay > 0:
            self.start_delay -= dt
            return 0.0, 1.0, 0.0
        if self.marshal and not hold and self._marshal_check(dt, track):
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
            net = self.net
            if neutral and self.sc_net is not None and max(self.inputs[RADAR_FRONT:RADAR_FRONT + 3]) > 0.0:
                net = self.sc_net       # someone (or the safety car) ahead: follow in line, don't race
            self.outputs = net.forward(self.inputs)
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
        self.corner_factor = 1.0        # < 1: a weaker driver is held to a share of the full-strength AI's speed
        self._corner_timer = 0.0
        self._corner_cap = 1e9
        self._pace_ref: list[float] | None = None
        self.skill = 1.0                # AI strength 0.3 .. 1.0, see set_skill
        self._brake_skill = 0.8
        self._lap_seen = -1
        self._lap_factor = 1.0
        self._hesitate = 0.0
        self._err_kind = ""             # the driving mistake under way ("late", "lock", "wide", "snap")
        self._err_time = 0.0
        self._was_braking = False

    def mistake_chance(self, wet: float = 0.0) -> float:
        """Chance of a driving mistake per corner: a beginner gets roughly one in eight wrong, the full-strength
        AI one in a few hundred. A wet track makes everyone a bit more error-prone."""
        k = (self.skill - 0.3) / 0.7
        return (0.004 + 0.12 * (1.0 - k) ** 2) * (1.6 if wet > 0.22 else 1.0)

    def set_skill(self, strength: float) -> None:
        """How well this AI drives. Never touches the car: a weaker driver is slower through the corners, brakes
        earlier and more gently, feeds the throttle in carefully, varies from lap to lap and now and then
        hesitates. 0.3 is a beginner, 1.0 the full-strength trained net."""
        self.skill = max(0.3, min(1.0, strength))
        k = (self.skill - 0.3) / 0.7                    # 0 beginner .. 1 full strength
        # relative to the median full-strength driver: near 100% the cap sits above even the fastest ones
        self.corner_factor = 1.0 if k >= 0.999 else 0.62 + 0.44 * k ** 0.35
        self._brake_skill = 0.45 + 0.55 * k            # share of the car's real braking a driver dares to use

    def control(self, dt: float, session: "Session") -> None:
        others = session.cars if self.sees_others else ()
        rc = getattr(session, "rc", None)
        neutral = rc.active if rc is not None else getattr(session, "neutralised", False)
        seen = others
        if others:
            # the safety car is no car of the field, but the nets have to see it
            extra = [o for o in session.extra_objects() if getattr(o, "on_track", True)]
            seen = list(others) + extra if extra else others
        self.throttle, self.brake, self.steer_input = self.driver.update(
            dt, seen, self.track, race_start=session.is_race_start_phase, neutral=neutral,
            hold=rc is not None and rc.mode == "RED")      # stopped for a red flag: not stuck
        # the pace reference only learns from racing laps: a formation lap or a neutralised field would pull it
        # down to their slow speeds - and every weaker AI driver with it
        self._corner_limit(dt, learn=not neutral and getattr(session, "race_started", True) and not self.session_done)
        if self.skill < 1.0 and not self.in_pit and not session.is_race_start_phase:
            self._driver_skill(dt)
        if not self.in_pit and not session.is_race_start_phase and not neutral:
            self._mistakes(dt)
        if others and self.collide_cars:
            # the first lap is the crowded one: more caution until the field has spread out; behind the safety
            # car the field is bunched up and nobody may pass
            caution = 1.8 if neutral else 1.5 if session.kind == "race" and self.laps_done == 0 else 1.0
            self._racecraft(dt, others, caution, neutral)

    def _driver_skill(self, dt: float) -> None:
        """The human side of a weaker driver: careful on the throttle with the wheels turned, a different pace each
        lap and a moment of hesitation now and then."""
        k = (self.skill - 0.3) / 0.7
        if self.laps_done != self._lap_seen:
            self._lap_seen = self.laps_done
            spread = 0.05 * (1.0 - k)
            self._lap_factor = 1.0 - random.uniform(0.0, spread)
        # only out of the corners: on a straight a weaker driver is flat out like everyone else
        exiting = self.speed_fwd < self.top_speed * 0.75
        if self._hesitate > 0.0:
            self._hesitate -= dt
            self.throttle = min(self.throttle, 0.25)
        elif exiting and self.speed_fwd > 120.0 and random.random() < (1.0 - k) * 0.08 * dt:
            self._hesitate = random.uniform(0.25, 0.6)      # a beginner: now and then late on the throttle
        steer = abs(self.steer_input)
        if self.brake <= 0.0 and exiting and steer > 0.2:
            careful = (1.0 - k) * 0.7 * min(1.0, (steer - 0.2) * 2.0)
            self.throttle = min(self.throttle, 1.0 - careful)

    def _mistakes(self, dt: float) -> None:
        """Now and then a driver gets a corner wrong: brakes too late or locks up and runs wide, misses the apex
        on the way out or (weaker drivers) is too greedy on the throttle. Rarer the stronger the AI."""
        braking = self.brake > 0.4
        if self._err_time > 0.0:
            self._err_time -= dt
            kind = self._err_kind
            if kind == "late":
                self.brake *= 0.3                               # braked too late: carries too much speed
            elif kind == "lock":
                self.brake, self.throttle = 1.0, 0.0            # locked the fronts: goes straight on
                self.steer_input *= 0.4
            elif kind == "wide":
                self.steer_input *= 0.45                        # missed the apex: runs out to the kerb / grass
            elif kind == "snap":
                self.throttle = 1.0                             # too much throttle with the wheels turned
            if self._err_time <= 0.0:
                self._err_kind = ""
        else:
            fast = self.speed_fwd > self.top_speed * 0.45
            p = self.mistake_chance(self.track.wetness)
            if braking and not self._was_braking and fast and random.random() < p:
                self._err_kind = "late" if random.random() < 0.6 else "lock"
                self._err_time = random.uniform(0.2, 0.45)
            elif not braking and self._was_braking and abs(self.steer_input) > 0.3 and random.random() < p * 0.6:
                greedy = self.skill < 0.6 and random.random() < 0.4
                self._err_kind = "snap" if greedy else "wide"
                self._err_time = random.uniform(0.25, 0.4) if greedy else random.uniform(0.4, 0.7)
        self._was_braking = braking

    def _corner_limit(self, dt: float, learn: bool = True) -> None:
        """Weaker drivers: through the corners never faster than corner_factor x the typical speed of a
        full-strength AI there (see ai_pace), braking for it early; on the straights they are just as fast. Cars
        not held back keep the reference up to date."""
        track = self.track
        if self.in_pit or self.frozen:
            return
        ref = self._pace_ref
        if ref is None or len(ref) != track.n:
            ref = self._pace_ref = ai_pace.profile(track.definition.key, track.n)
        f = self.corner_factor * self._lap_factor
        if self.skill < 1.0:
            self._corner_timer -= dt
            if self._corner_timer <= 0.0:
                self._corner_timer = AI_CONTROL_INTERVAL
                n, step = track.n, track.WAYPOINT_SPACING
                brake_k = self.performance()["brake"] * self._brake_skill
                top = self.top_speed
                allowed = 1e9
                for k in range(0, 40, 2):
                    r = ref[(self.idx + k) % n]
                    t = (r / top - 0.55) / 0.3
                    if r <= 0.0 or t >= 1.0:
                        continue                # unknown, or flat out: the weaker driver is just as fast there
                    # all of the reduction in slow corners, fading out towards the fast ones - out to well above
                    # the median driver there, so the quick ones aren't held back either
                    t = max(0.0, t)
                    v = r * (f + (1.12 - f) * t * t * (3.0 - 2.0 * t))
                    allowed = min(allowed, (v * v + 2.0 * brake_decel(v) * brake_k * k * step) ** 0.5)
                self._corner_cap = allowed
            excess = self.speed_fwd - self._corner_cap
            if excess > 3.0:
                self.throttle = 0.0
                self.brake = max(self.brake, min(1.0, max(0.3, excess / 50.0)))
                return
            if excess > -5.0:
                self.throttle = min(self.throttle, 0.7)
                return
        if learn and not self.on_grass and not self.is_ghost and self.speed_fwd > 20.0 and ref[self.idx] > 0.0:
            # a typical speed, not the fastest ever seen: a slipstream or a lucky moment must not raise the
            # reference for everyone (that made the old one useless in the corners)
            ref[self.idx] += (self.speed_fwd - ref[self.idx]) * 0.01

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

    def _racecraft(self, dt: float, others: Sequence[Car], caution: float, neutral: bool = False) -> None:
        self._rc_timer -= dt
        if self._rc_timer <= 0.0:
            self._rc_timer = AI_CONTROL_INTERVAL
            self._rc_lift, self._rc_brake, self._rc_steer, self._rc_side = self._assess(others, caution, neutral)
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

    def _assess(self, others: Sequence[Car], caution: float, neutral: bool = False
                ) -> tuple[float, float, float, float]:
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
                if neutral:
                    continue            # no passing under SC/VSC: stay in line behind it
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
