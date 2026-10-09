# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from .ai_car import AI_Car
from .car import PLANK_LIMIT_MM, PLANK_RACE_MM, RACE_FUEL_KG, Car
from .physics import handle_collisions
from .player_car import Player_Car
from .profiles import AUTOPILOT_BRAIN, PLAYER_PROFILE, DriverProfile, driver_grip
from .effects import Effects
from .render3d import Renderer3D
from .pit_menu import PitMenu
from .pitlane import PIT_ACCEL, PIT_DECEL, SPEED_LIMIT
from .car_setup import CarSetup, recommended
from .career_events import FAILURES, failure_chance
from .tyres import ALL_COMPOUNDS, COMPOUNDS, COMPOUND_ORDER, TyreSet
from .weather import Weather
from .utils import approach
from .sensors import RADAR_RANGE, lookahead_points
from .race_control import PUNCTURE_WEAR, RaceControl
from .i18n import tr
from .stewards import Stewards
from .settings import (TOP_SPEED, DIFFICULTY_LEVELS, PHYSICS_STEP, PURPLE, SCREEN_HEIGHT,
                       SCREEN_WIDTH, SLIPSTREAM_RANGE, WHITE, YELLOW, GREEN, Color)
from .utils import format_time

if TYPE_CHECKING:
    from .championship import Championship
    from .game import Game
    from .track import Track


@dataclass
class WeekendConfig:
    track_key: str
    mode: str
    race_laps: int
    difficulty_name: str
    ai_profiles: list[DriverProfile]
    grid: list[str] | None = None
    results: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    player: DriverProfile | None = PLAYER_PROFILE
    player2: DriverProfile | None = None        # local split-screen opponent
    start_compound: str = "medium"
    assists: int = 1
    view3d: bool = False
    damage: str = "on"
    tyre_wear_factor: float = 1.0
    auto_camera: bool = True
    championship: "Championship | None" = None
    pit_stop_times: dict[str, float] = field(default_factory=dict)
    instant: bool = False
    rival: str | None = None
    career: bool = False
    focus_team: str | None = None
    reliability: dict[str, float] = field(default_factory=dict)
    objective: str | None = None
    safety_car: bool = True
    gearbox: str = "auto"
    weather: str = "dry"
    weather_seed: int = field(default_factory=lambda: random.randrange(1 << 30))

    @property
    def spectator(self) -> bool:
        return self.player is None

    @property
    def field(self) -> list[DriverProfile]:
        humans = [p for p in (self.player, self.player2) if p is not None]
        return humans + self.ai_profiles

    @property
    def difficulty(self) -> float:
        return DIFFICULTY_LEVELS[self.difficulty_name]


def time_gap(front: Car, back: Car) -> float | None:
    key = back.last_marker
    t_back = back.marker_times.get(key)
    t_front = front.marker_times.get(key)
    if t_back is None or t_front is None:
        return None
    return t_back - t_front


class Camera:

    def __init__(self) -> None:
        self.pos = Vector2()

    def snap(self, pos: Vector2) -> None:
        self.pos = Vector2(pos)

    def update(self, target: Car, dt: float) -> None:
        desired = target.pos + target.vel * 0.50
        self.pos += (desired - self.pos) * min(1.0, dt * 4.0)

    def offset(self, track: "Track") -> Vector2:
        w, h = track.world_size
        return Vector2(min(max(self.pos.x - SCREEN_WIDTH / 2, 0), max(0, w - SCREEN_WIDTH)),
                       min(max(self.pos.y - SCREEN_HEIGHT / 2, 0), max(0, h - SCREEN_HEIGHT)))


REFUEL_KG_PER_S: float = 11.0


class Session:

    ghost_field: bool = False       # practice/qualifying: no car-to-car contact, every car drives alone
    kind: str = "session"
    title: str = "Session"
    fast_forward_scale: float = 4.0

    def __init__(self, game: "Game", track: "Track", config: WeekendConfig) -> None:
        self.game = game
        self.track = track
        self.config = config
        track.ensure_built()
        self.time = 0.0
        self.cars: list[Car] = []
        self.player: Player_Car | None = None
        self.player2: Player_Car | None = None
        self.cameras: dict[Car, Camera] = {}
        self.r3ds: dict[Car, Renderer3D] = {}
        self.pit_menus: dict[Car, PitMenu] = {}
        self.camera = Camera()
        self.cam_index = 0
        self.paused = False
        self.finished = False
        self.end_timer: float | None = None
        self.time_scale = 1.0
        self.is_race_start_phase = False
        self.show_ai_info = False
        self.show_line = False
        self.messages: list[list] = []
        self.feed: list[list] = []
        self.fastest_lap: tuple[float, str] | None = None
        self._label_cache: dict[str, pygame.Surface] = {}
        self.view3d = config.view3d
        self.r3d = Renderer3D()
        self.fx = Effects(track, game.settings.effects)
        self.stewards = Stewards(self)
        self.overview = False
        self.director_timer = 0.0
        self.show_fps = getattr(game.settings, "show_fps", False)
        self.best_sectors: list[float | None] = [None, None, None]
        self.hide_hud = False
        self.blue_flag = 0.0
        self._blue_ignored = 0.0
        self._blue_warned = False
        self.team_orders: dict[Car, dict] = {}
        self.failures: dict[str, str] = {}
        self.pit_menu = PitMenu()
        self.weather = Weather(config.weather, config.weather_seed + {"practice": 0, "qualifying": 1}.get(self.kind, 2), self.expected_duration())
        track.wetness = self.weather.wetness
        self._frame_dt = 0.0
        self._weather_note = ""
        net = getattr(game, "net", None)
        # online: "host" simulates and the guest drives player2, "client" only mirrors the host
        self.net_role = net.role if net is not None and net.connected and config.player2 is not None else None
        self.online = self.net_role is not None
        self.host_paused = False
        self.host_finished = False
        if config.objective and config.player is not None:
            self.message(f"TEAMZIEL: {config.objective}", (255, 200, 40), 5.0)

    def expected_duration(self) -> float:
        """Rough session length in seconds, so the rain forecast spans the session."""
        lap = self.track.length / (TOP_SPEED * 0.85)
        laps = {"practice": 10, "qualifying": 4}.get(self.kind, self.config.race_laps + 1)
        return lap * laps

    def _create_cars(self, order: list[DriverProfile]) -> None:
        ai_setup = recommended(self.track)
        for prof in order:
            if self.config.player is not None and prof is self.config.player:
                car: Car = Player_Car(prof, self.track)
                car.set_assists(self.config.assists)
                car.apply_setup(self.game.setup_for(self.track))
                car.manual_gearbox = self.config.gearbox == "manual"
                self.player = car
            elif self.config.player2 is not None and prof is self.config.player2:
                car = Player_Car(prof, self.track)
                car.set_assists(self.config.assists)
                car.apply_setup(self.game.setup_for(self.track))
                car.slot = 1
                car.manual_gearbox = self.config.gearbox == "manual"
                if self.net_role is not None:
                    # online guest: their own assists, gearbox and garage setup
                    net = self.game.net
                    if self.net_role == "host":
                        car.remote = net.remote_input
                        car.set_assists(net.remote_assists)
                        car.manual_gearbox = net.remote_gearbox == "manual"
                        setup = net.remote_setup(self.track.definition.key)
                    else:
                        car.set_assists(self.game.settings.assists)
                        car.manual_gearbox = self.game.settings.gearbox == "manual"
                        setup = None
                    car.apply_setup(setup or (self.game.setup_for(self.track) if self.net_role == "client"
                                              else recommended(self.track)))
                self.player2 = car
            else:
                net = self.game.brains.network(prof.brain, prof.checkpoint)
                car = AI_Car(prof, self.track, net, engine_factor=self.config.difficulty * prof.pace)
                car.grip_bonus = driver_grip(prof.pace)
                car.apply_setup(ai_setup)
            if self.ghost_field:
                car.collide_cars = False
                car.ghost_visual = not car.is_player
                if isinstance(car, AI_Car):
                    car.sees_others = False
            car.tyres = TyreSet(self.compound_for(car), self._wear_factor(car))
            car.damage.multiplier = 0.0 if self.config.damage == "off" else 1.0
            laps = max(1, self.config.race_laps)
            car.fill_fuel(self.start_fuel_laps(car), RACE_FUEL_KG / laps)
            car.plank_per_lap = PLANK_RACE_MM / laps * (1.0 if car.is_player else random.uniform(0.85, 1.1))
            self.cars.append(car)
        self.cam_index = self.cars.index(self.player) if self.player is not None else 0
        self.pit_menus = {p: (self.pit_menu if p is self.player else PitMenu()) for p in self.players}
        if self.net_role == "client":
            # the guest's own car is "the player" here; the host's car is just another (human) car
            self.player, self.player2 = self.player2, None
            self.cam_index = self.cars.index(self.player)
            self.pit_menus = {self.player: self.pit_menu}
            self.game.controls.assign_players(1)
        elif self.online:
            self.game.controls.assign_players(1)
        elif self.player2 is not None:
            # split screen: each player drives on their half of the keyboard, plus a controller if there is one
            self.game.controls.assign_players(2)
            assert self.player is not None
            self.player.keyset, self.player2.keyset = "wasd", "arrows"
            for p in self.players:
                self.cameras[p] = Camera()
                self.r3ds[p] = Renderer3D()
        else:
            self.game.controls.assign_players(1)
        own = [k for k, c in enumerate(self.cars) if c.profile.team == self.config.focus_team]
        if self.player is None and own:
            self.cam_index = own[0]
            self.config.auto_camera = False

    def fuel_margin(self, car: Car) -> float:
        """Extra laps of fuel on top of the race distance: the player's garage choice, AI a safe margin."""
        if isinstance(car, Player_Car) and car.setup is not None:
            return car.setup.fuel / 2.0
        return 1.0

    def start_fuel_laps(self, car: Car) -> float:
        return self.config.race_laps + self.fuel_margin(car)

    def _wear_factor(self, car: Car) -> float:
        return car.perf.tyre_wear * car.profile.tyre_mgmt * car.sf.wear * self.config.tyre_wear_factor

    def stop_time(self, car: Car) -> float:
        return self.config.pit_stop_times.get(car.profile.team, self.STOP_TIME)

    @property
    def focus(self) -> Car:
        return self.cars[self.cam_index]

    def compound_for(self, car: Car) -> str:
        if car.profile is self.config.player or car.profile is self.config.player2:
            return self.config.start_compound
        return Weather.best_compound(self.weather.wetness) or "medium"

    def _weather_calls(self) -> None:
        """AI crews react to the weather mid-lap: the next pit entry is used, not the next lap."""
        if self.track.wetness < 0.12 and self.weather.rain < 0.05 and                 all(c.tyres is None or c.tyres.compound.kind == "slick" for c in self.cars):
            return
        for car in self.cars:
            if car.is_player or car.session_done or car.dnf or car.in_pit or car.pit_request is not None:
                continue
            if self.is_manager_car(car) and self.team_orders.get(car):
                continue
            call = self.weather_tyre_call(car)
            if call:
                car.pit_request = call
                self.add_feed(f"{car.short}: Box für {COMPOUNDS[call].name}")

    def weather_tyre_call(self, car: Car) -> str | None:
        """Tyre the conditions ask for when the car is on the wrong kind (None = current tyres are fine)."""
        if car.tyres is None:
            return None
        want = Weather.best_compound(self.track.wetness)
        kind = car.tyres.compound.kind
        # a little hysteresis so cars don't swap back and forth around the threshold
        w = self.track.wetness
        if want is None and kind != "slick" and w < 0.16 and self.weather.rain < 0.1:
            return self.repair_compound(car) if self.repair_compound(car) in COMPOUND_ORDER else "medium"
        if want == "inter" and (kind == "slick" and w > 0.26 or kind == "wet" and w < 0.6):
            return "inter"
        if want == "wet" and kind != "wet" and w > 0.74:
            return "wet"
        return None

    def _staggered_start(self) -> None:
        for k, car in enumerate(self.cars):
            s = -(260.0 + k * 170.0)
            i = int((s % self.track.length) / self.track.WAYPOINT_SPACING) % self.track.n
            pos, heading = self.track.pose_at(s, self.track.line_offset[i])
            car.place(pos, heading)
            car.vel = car.forward * 120.0
        self.camera.snap(self.focus.pos)

    def message(self, text: str, color: Color = WHITE, duration: float = 2.5) -> None:
        self.messages = [m for m in self.messages if m[0] != text]
        self.messages.append([text, color, duration])
        self.messages = self.messages[-3:]

    def add_feed(self, text: str) -> None:
        self.feed.append([text, 6.0])
        self.feed = self.feed[-5:]

    def focus_car(self, car: Car, manual: bool = True) -> None:
        self.cam_index = self.cars.index(car)
        self.r3d._initialized = False
        if manual and self.spectator and self.config.auto_camera:
            self.config.auto_camera = False
            self.message("TV-Regie aus (A schaltet sie wieder ein)", WHITE, 1.5)

    def _focus_by_position(self, pos: int) -> None:
        order = self.standings()
        if 0 <= pos < len(order):
            self.focus_car(order[pos])

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = event.pos
            row = (y - 182) // self.game.hud.tower_row_h(len(self.cars))
            if 16 <= x <= 226 and y >= 182 and row < len(self.cars):
                self._focus_by_position(int(row))
            return
        if event.type != pygame.KEYDOWN:
            return
        actor, event = self._route(event)
        key = event.key
        if actor is not None and self.pit_menus[actor].handle_key(event, actor, self):
            return
        if self.player2 is not None and actor is self.player2 and key not in (pygame.K_ESCAPE, pygame.K_p):
            # player 2's keys only drive their own car
            if key not in (pygame.K_SPACE, pygame.K_b, pygame.K_r, pygame.K_e, pygame.K_q):
                return
        if self.player2 is not None and not self.online and \
                (pygame.K_0 <= key <= pygame.K_9 or key in (pygame.K_c, pygame.K_m)):
            return  # split screen: the cameras stay on the two players
        if self.spectator and key in (pygame.K_UP, pygame.K_DOWN):
            order = self.standings()
            pos = order.index(self.focus) + (-1 if key == pygame.K_UP else 1)
            self._focus_by_position(pos % len(order))
            return
        if pygame.K_0 <= key <= pygame.K_9:
            self._focus_by_position((key - pygame.K_1) % 10)
            return
        if key == pygame.K_k:
            self.message(f"Kamera: {self.r3d.next_mode()}" + ("" if self.view3d else " (3D mit V)"), WHITE, 1.2)
            return
        if key == pygame.K_m:
            self.overview = not self.overview
            return
        if key == pygame.K_ESCAPE and self.config.instant:
            self.game.go_to_menu()
            return
        if key == pygame.K_ESCAPE:
            if self.paused:
                self.game.go_to_menu()
            else:
                self.paused = True
        elif key == pygame.K_r and self.paused:
            self.game.sound.stop()
            self.game.start_session(self.kind)
            return
        elif key == pygame.K_p and event.mod & pygame.KMOD_SHIFT:
            rc = getattr(self, "rc", None)
            if rc is not None and self.race_started and not rc.active and rc._leader() is not None:
                rc.deploy("SC", "Entscheidung der Rennleitung")
        elif key == pygame.K_p:
            self.paused = not self.paused
        elif key in (pygame.K_F1, pygame.K_i):
            self.show_ai_info = not self.show_ai_info
        elif key in (pygame.K_F2, pygame.K_l):
            self.show_line = not self.show_line
        elif key == pygame.K_c:
            self.focus_car(self.cars[(self.cam_index + 1) % len(self.cars)])
            self.message(f"Kamera: {self.focus.name}", WHITE, 1.2)
        elif key == pygame.K_r and actor is not None and not actor.frozen \
                and actor.autopilot is None and not actor.in_pit:
            actor.respawn()
        elif key == pygame.K_v:
            self.view3d = not self.view3d
            self.message("3D-Verfolgerkamera" if self.view3d else "2D-Draufsicht", WHITE, 1.2)
        elif key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS, pygame.K_RIGHTBRACKET) and self.spectator:
            self.time_scale = min(8.0, self.time_scale * 2)
            self.message(f"Zeitraffer x{self.time_scale:.0f}", WHITE, 1.0)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_SLASH) and self.spectator:
            self.time_scale = max(1.0, self.time_scale / 2)
            self.message(f"Zeitraffer x{self.time_scale:.0f}", WHITE, 1.0)
        elif key == pygame.K_a and self.spectator:
            self.config.auto_camera = not self.config.auto_camera
            self.message("TV-Regie " + ("an" if self.config.auto_camera else "aus"), WHITE, 1.2)
        elif key == pygame.K_F3:
            self.show_fps = not self.show_fps
        elif key == pygame.K_h:
            self.hide_hud = not self.hide_hud
        elif key == pygame.K_SPACE and actor is not None and actor.assist_level == 0:
            if actor.straight_mode:
                actor.straight_mode = False
            else:
                actor.aero_request = True
        elif key in (pygame.K_e, pygame.K_q) and actor is not None and actor.manual_gearbox:
            if actor.autopilot is None:
                actor.shift(1 if key == pygame.K_e else -1)
        elif key == pygame.K_b and actor is not None and actor.autopilot is None:
            self.pit_menus[actor].toggle(actor)
        elif key == pygame.K_b and self.is_manager_car(self.focus):
            self._draft_team_order(self.focus)
        elif key == pygame.K_TAB and self.config.focus_team:
            own = [c for c in self.cars if c.profile.team == self.config.focus_team]
            if own:
                nxt = own[(own.index(self.focus) + 1) % len(own)] if self.focus in own else own[0]
                self.focus_car(nxt, manual=False)
                self.config.auto_camera = False
        else:
            self.on_key(key)

    def on_key(self, key: int) -> None:
        pass

    # player 2's keys next to the arrow keys, translated to the actions player 1 has on the left
    P2_KEYS = {pygame.K_RCTRL: pygame.K_SPACE, pygame.K_RSHIFT: pygame.K_b, pygame.K_DELETE: pygame.K_r,
               pygame.K_PAGEUP: pygame.K_e, pygame.K_PAGEDOWN: pygame.K_q,
               pygame.K_KP1: pygame.K_1, pygame.K_KP2: pygame.K_2, pygame.K_KP3: pygame.K_3,
               pygame.K_KP4: pygame.K_4, pygame.K_KP5: pygame.K_5, pygame.K_KP_ENTER: pygame.K_RETURN}

    @property
    def players(self) -> list[Player_Car]:
        return [p for p in (self.player, self.player2) if p is not None]

    def _route(self, event: pygame.event.Event) -> tuple[Player_Car | None, pygame.event.Event]:
        """Which player a key press belongs to (split screen), and the key in player 1's terms."""
        if getattr(event, "net_remote", False):
            return self.player2, event
        if self.player2 is None or self.online:
            return self.player, event
        if getattr(event, "from_joystick", False):
            slot = getattr(event, "player_slot", 0)
            return (self.players[slot] if 0 <= slot < len(self.players) else None), event
        if event.key in self.P2_KEYS:
            mapped = pygame.event.Event(pygame.KEYDOWN, key=self.P2_KEYS[event.key], mod=event.mod, unicode="",
                                        scancode=0)
            return self.player2, mapped
        if event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            return self.player2, event
        return self.player, event

    @property
    def spectator(self) -> bool:
        return self.player is None

    def enable_player_autopilot(self, car: Player_Car | None = None) -> None:
        for p in ([car] if car is not None else self.players):
            p.enable_autopilot(self.game.brains.network(AUTOPILOT_BRAIN))

    def save_recording(self) -> None:
        if self.player is not None:
            self.player.save_recording(self.kind)

    def update(self, frame_dt: float) -> None:
        self.game.sound.update(self)
        self._frame_dt = 0.0 if self.paused else frame_dt
        if self.paused:
            return
        sim_dt = frame_dt * self.time_scale
        steps = max(1, math.ceil(sim_dt / PHYSICS_STEP - 1e-6))
        h = sim_dt / steps
        for _ in range(steps):
            self._step(h)
        self.fx.update(self, frame_dt)
        if self.spectator and self.config.auto_camera:
            self._director(frame_dt)
        self.camera.update(self.cars[self.cam_index], frame_dt)
        if self.view3d:
            self.r3d.update_camera(self.cars[self.cam_index], frame_dt)
        for p, cam in self.cameras.items():
            cam.update(p, frame_dt)
            if self.view3d:
                self.r3ds[p].update_camera(p, frame_dt)
        for m in self.messages:
            m[2] -= frame_dt
        self.messages = [m for m in self.messages if m[2] > 0]
        for f in self.feed:
            f[1] -= frame_dt
        self.feed = [f for f in self.feed if f[1] > 0]
        self.stewards.tick(frame_dt)
        self._weather_timer = getattr(self, "_weather_timer", 0.0) - frame_dt * self.time_scale
        if self._weather_timer <= 0:
            self._weather_timer = 2.0
            self._weather_calls()
        if self.team_orders:
            self._update_team_orders()
        if self.end_timer is not None:
            self.end_timer -= frame_dt
            if self.end_timer <= 0 and not self.finished:
                self.finished = True
                self.game.session_finished(self)

    def _step(self, h: float) -> None:
        self.pre_step(h)
        self.weather.update(h, self.track, len(self.cars))
        for car in self.cars:
            if car.pit_state is not None:
                self._lane_tick(car, h)
            elif not car.frozen:
                car.control(h, self)
                self.neutralize(car)
        for car in self.cars:
            car.physics_step(h)
        handle_collisions(self.cars, self.track, self.stewards.on_contact)
        for car in self.cars:
            if car.damage.pending_puncture:
                car.damage.pending_puncture = False
                if not car.puncture and not car.dnf:
                    self.on_puncture(car)
        self.post_collisions()
        for car in self.cars:
            car.update_track_state(self)
            self._check_damage(car)
            self._check_pit_entry(car)
            self._active_aero(car, h)
        if self.aero_active:
            self._step_count = getattr(self, "_step_count", 0) + 1
            if self._step_count % 4 == 0:
                self._update_slipstream()
            for car in self.cars:
                car.slipstream = approach(car.slipstream, car.slip_target, h * 2.5)
        self.stewards.update()
        self.time += h

    def pre_step(self, h: float) -> None:
        pass

    def neutralize(self, car: Car) -> None:
        pass

    def post_collisions(self) -> None:
        pass

    def extra_objects(self) -> list:
        return []

    @property
    def aero_active(self) -> bool:
        return False

    def _update_slipstream(self) -> None:
        rng = SLIPSTREAM_RANGE
        active = [c for c in self.cars if not c.is_ghost and not c.frozen]
        for car in self.cars:
            target = 0.0
            if car in active and car.speed_fwd > 250.0:
                fx, fy = math.cos(car.heading), math.sin(car.heading)
                px, py = car.pos.x, car.pos.y
                for other in active:
                    if other is car:
                        continue
                    dx, dy = other.pos.x - px, other.pos.y - py
                    along = dx * fx + dy * fy
                    if 30.0 < along < rng:
                        lat = abs(-dx * fy + dy * fx)
                        if lat < 28.0:
                            target = max(target, (1.0 - along / rng) * (1.0 - 0.5 * lat / 28.0))
            car.slip_target = target

    def _active_aero(self, car: Car, h: float) -> None:
        if isinstance(car, Player_Car) and car.autopilot is None and car.assist_level == 0:
            zone = self.track.aero_zone_at[car.idx] if self.track.aero_zone_at else -1
            wants = car.aero_request
            car.aero_request = car.aero_request and zone < 0 and not car.straight_mode
            car.update_aero(h, wants)
        else:
            car.update_aero(h)

    ORDER_SEND_DELAY = 1.2
    ORDER_REPLY_DELAY = 1.8

    def is_manager_car(self, car: Car) -> bool:
        return (self.spectator and self.config.focus_team is not None and car.profile.team == self.config.focus_team
                and not car.session_done and not car.dnf)

    def _draft_team_order(self, car: Car) -> None:
        if car.in_pit:
            self.message(f"{car.short} ist schon in der Boxengasse", WHITE, 1.5)
            return
        options: list[str | None] = [*ALL_COMPOUNDS, None]
        cur = self.team_orders.get(car, {}).get("compound", "none")
        nxt = options[(options.index(cur) + 1) % len(options)] if cur in options else options[0]
        order = self.team_orders.setdefault(car, {"asked": 0})
        order.update(compound=nxt, send_at=self.time + self.ORDER_SEND_DELAY, reply_at=None)
        label = f"Box für {car.short}: {COMPOUNDS[nxt].name}" if nxt else f"{car.short}: Stopp absagen"
        self.message(f"ANWEISUNG  {label}  (B = ändern)", COMPOUNDS[nxt].color if nxt else WHITE, 1.4)

    def _update_team_orders(self) -> None:
        for car, order in list(self.team_orders.items()):
            if car.session_done or car.dnf:
                del self.team_orders[car]
                continue
            if order.get("send_at") is not None and self.time >= order["send_at"]:
                order["send_at"] = None
                order["reply_at"] = self.time + self.ORDER_REPLY_DELAY
                order["asked"] += 1
                comp = order["compound"]
                car.radio_msg = ((f"Teamchef: Box, Box - {COMPOUNDS[comp].name}!" if comp else
                                  "Teamchef: Bleib draußen, kein Stopp."), (120, 200, 255), self.time + 3.0)
            elif order.get("reply_at") is not None and self.time >= order["reply_at"]:
                order["reply_at"] = None
                self._driver_reply(car, order)

    def _driver_reply(self, car: Car, order: dict) -> None:
        comp = order["compound"]
        name = car.short
        if comp is None:
            if car.pit_request is not None:
                car.pit_request = None
            car.radio_msg = ("Copy, ich bleibe draußen.", GREEN, self.time + 4.0)
            self.add_feed(f"{name}: bleibt draußen (Teamorder)")
            return
        t, d = car.tyres, car.damage
        remaining = getattr(self, "total_laps", 99) - car.laps_done
        wear = t.wear if t else 0.0
        reason = "Reifen sind noch gut!"
        p = 0.25 + 1.3 * wear
        if d.total > 0.25:
            p = 1.0
        if remaining <= 1:
            p, reason = 0.05, "Nur noch eine Runde - auf keinen Fall!"
        elif t is not None and comp == t.compound.key and wear < 0.25:
            p, reason = min(p, 0.15), "Ich habe gerade frische Reifen drauf!"
        ahead = self._gap_to_neighbour(car)
        if ahead is not None and ahead < 0.8 and wear < 0.6:
            p -= 0.2
            reason = "Bin im Zweikampf - noch eine Runde!"
        p += {"aggressive": -0.15, "cautious": 0.15}.get(car.profile.brain, 0.0)
        p += 0.35 * (order["asked"] - 1)
        if random.random() < max(0.0, min(1.0, p)):
            car.pit_request = comp
            text = "Okay, du bist der Chef. Komme rein." if order["asked"] > 1 else \
                f"Verstanden, Box diese Runde - {COMPOUNDS[comp].name}."
            car.radio_msg = (text, GREEN, self.time + 5.0)
            self.add_feed(f"{name} folgt der Anweisung: Box -> {COMPOUNDS[comp].name}")
            del self.team_orders[car]
        else:
            car.radio_msg = (f"Negativ! {reason}", (255, 110, 90), self.time + 5.0)
            self.add_feed(f"{name} lehnt den Boxenstopp ab")
            order["compound"] = "none"

    def _gap_to_neighbour(self, car: Car) -> float | None:
        order = self.standings()
        i = order.index(car)
        gaps = []
        if i > 0:
            g = time_gap(order[i - 1], car)
            if g is not None:
                gaps.append(g)
        if i < len(order) - 1:
            g = time_gap(car, order[i + 1])
            if g is not None:
                gaps.append(g)
        return min(gaps) if gaps else None

    STOP_TIME: float = 2.4

    def _box_of(self, car: Car) -> float:
        if not hasattr(self, "_boxes"):
            teams: list[str] = []
            for c in self.cars:
                if c.profile.team not in teams:
                    teams.append(c.profile.team)
            assert self.track.pit is not None
            self._boxes = dict(zip(teams, self.track.pit.box_positions(len(teams))))
        return self._boxes[car.profile.team]

    def garages(self) -> list[tuple[Vector2, float, Color, str]]:
        pit = self.track.pit
        if pit is None:
            return []
        out = []
        colors = {c.profile.team: (c.perf.color if c.perf.name == c.profile.team else c.color) for c in self.cars}
        for car in self.cars:
            self._box_of(car)
        for team, u in self._boxes.items():
            p, heading = pit.pose(u)
            side = Vector2(-math.sin(heading), math.cos(heading)) * (pit.side * (pit.HALF_WIDTH + 30))
            out.append((p + side, heading, colors.get(team, (200, 200, 200)), team))
        return out

    def plan_pit(self, car: Car, neutralised: bool = False) -> str | None:
        return None

    def damage_pit_allowed(self, car: Car) -> bool:
        return True

    def repair_compound(self, car: Car) -> str:
        return car.tyres.compound.key if car.tyres else "medium"

    def _check_damage(self, car: Car) -> None:
        if car.out_of_fuel and not car.dnf and not car.session_done and not car.in_pit and car.speed_fwd < 8.0:
            self.retire(car, "Kein Benzin mehr")
            return
        if car.dnf or car.session_done or car.damage.multiplier <= 0:
            return
        d = car.damage
        if self.config.damage == "dnf" and d.is_terminal:
            self.retire(car, "Motor überhitzt" if d.cooling >= 1.0 else "Aufhängung gebrochen")
            return
        if car.is_player or car.pit_request is not None or car.pit_state is not None:
            return
        if (d.front_wing > 0.5 or d.rear > 0.55 or d.suspension > 0.4 or d.cooling > 0.5) and                 self.damage_pit_allowed(car):
            car.pit_request = self.repair_compound(car)
            self.add_feed(f"{car.short}: Schaden - Box für Reparatur")

    def retire(self, car: Car, reason: str) -> None:
        car.dnf = True
        car.session_done = True
        car.retired_ghost = True
        car.frozen = True
        self.add_feed(f"AUSFALL: {car.name} ({reason})")
        self.on_retire(car)
        if car is self.player:
            self.message(f"AUSFALL - {reason}", (255, 80, 80), 5.0)
            self.time_scale = self.fast_forward_scale
        if all(c.session_done for c in self.cars) and self.end_timer is None:
            self.end_timer = 3.0

    def on_retire(self, car: Car) -> None:
        pass

    def on_puncture(self, car: Car) -> None:
        car.puncture = True
        self.add_feed(f"REIFENSCHADEN: {car.short} (Kontakt)")
        if car is self.player:
            self.message("REIFENSCHADEN! Sofort an die Box (B)", (255, 80, 80), 4.0)
        elif car.pit_request is None:
            car.pit_request = car.tyres.compound.key if car.tyres else "medium"

    def _director(self, frame_dt: float) -> None:
        self.director_timer -= frame_dt
        if self.director_timer > 0:
            return
        self.director_timer = 7.0
        order = [c for c in self.standings() if not c.session_done]
        best, best_score = None, 1e9
        for pos in range(1, len(order)):
            gap = time_gap(order[pos - 1], order[pos])
            if gap is not None and 0 < gap < 1.5:
                score = gap + pos * 0.15
                if score < best_score:
                    best, best_score = order[pos], score
        target = best or (order[0] if order else self.cars[0])
        new_index = self.cars.index(target)
        if new_index != self.cam_index:
            self.cam_index = new_index
            self.r3d._initialized = False

    def _check_pit_entry(self, car: Car) -> None:
        pit = self.track.pit
        if pit is None or car.pit_state is not None or car.pit_request is None or car.frozen:
            return
        ds = (car.s - pit.entry_abs()) % self.track.length
        if ds < 40.0 and car.speed_fwd > 0:
            car.pit_state = "lane"
            car.pit_u = ds
            car.pit_entry_lat = car.lateral
            car.pit_box_u = self._box_of(car)
            car.pit_compound = car.pit_request
            car.pit_request = None
            car.pit_stopped = False
            car.pit_stop_timer = 0.0
            if car is self.player:
                self.message("BOXENGASSE - Limiter an", (255, 210, 40), 2.5)

    def _lane_tick(self, car: Car, h: float) -> None:
        pit = self.track.pit
        assert pit is not None
        v = max(0.0, car.speed_fwd)
        if car.pit_stop_timer > 0:
            car.pit_stop_timer -= h
            if car.pit_stop_timer <= 0:
                plan = car.pit_plan or {}
                if car.pit_compound not in COMPOUNDS and car.puncture and car.tyres is not None:
                    car.pit_compound = car.tyres.compound.key   # a punctured tyre gets replaced regardless
                if car.pit_compound in COMPOUNDS:
                    car.tyres = TyreSet(car.pit_compound, self._wear_factor(car))
                if plan.get("repair", True):
                    car.damage.repair()
                car.puncture = False
                if plan.get("fuel", 0.0) > 0 and car.fuel_per_lap > 0:
                    car.fuel += plan["fuel"] * car.fuel_per_lap
                    car.out_of_fuel = False
                if plan.get("front_wing", 0) and car.setup is not None:
                    new = CarSetup(**vars(car.setup))
                    new.front_wing = max(-5, min(5, new.front_wing + plan["front_wing"]))
                    car.apply_setup(new)
                car.pit_plan = None
                car.pit_stops += 1
                car.pit_laps.append(car.laps_done + 1)
                if car is not self.player:
                    self.add_feed(f"{car.short} Boxenstopp -> {COMPOUNDS[car.pit_compound].name}")
            v = 0.0
        else:
            if not car.pit_stopped:
                target = min(SPEED_LIMIT, math.sqrt(2.0 * PIT_DECEL * max(0.0, car.pit_box_u - car.pit_u)))
            elif car.pit_u < pit.length - pit.RAMP:
                target = SPEED_LIMIT
            else:
                target = SPEED_LIMIT * 1.8
            v = approach(v, target, (PIT_DECEL if v > target else PIT_ACCEL) * h)
            if not car.pit_stopped and car.pit_u >= car.pit_box_u - 1.0:
                car.pit_stopped = True
                plan = car.pit_plan or {}
                repair = car.damage.repair_time() if plan.get("repair", True) else 0.0
                served = car.penalty_unserved
                car.penalty_unserved = 0.0
                if served > 0:
                    self.stewards.announce(f"{car.short} sitzt {served:.0f}s Strafe in der Box ab", "info")
                fuel_time = plan.get("fuel", 0.0) * car.fuel_per_lap / REFUEL_KG_PER_S
                wing_time = 0.8 if plan.get("front_wing", 0) else 0.0
                tyres = car.pit_compound in COMPOUNDS
                base = self.stop_time(car) if tyres else 0.0
                # tyres, fuel and the wing adjustment happen in parallel; repairs come on top
                car.pit_stop_timer = max(base, fuel_time, wing_time, 0.8) + repair + served + \
                    (0.0 if car is self.player else random.uniform(0.0, 0.8))
                v = 0.0
                if car is self.player:
                    parts = [f"Reifen: {COMPOUNDS[car.pit_compound].name}" if tyres else "Reifen bleiben drauf"]
                    if fuel_time > 0:
                        parts.append(f"Tanken +{plan['fuel']:.1f} Rd.")
                    if wing_time:
                        parts.append(f"Frontflügel {plan['front_wing']:+d}")
                    if repair > 0:
                        parts.append(f"Reparatur ({repair:.0f}s)")
                    self.message("  ·  ".join(parts),
                                 COMPOUNDS[car.pit_compound].color if tyres else WHITE, 3.0)
        car.pit_u += v * h
        pos, heading = pit.pose(min(car.pit_u, pit.length), car.pit_entry_lat)
        car.pos, car.heading = pos, heading
        car.vel = car.forward * v
        car.speed_fwd = v
        car.throttle, car.brake, car.steer_input = (0.3 if v > 0 else 0.0), 0.0, 0.0
        if car.pit_u >= pit.length:
            car.pit_state = None
            car.auto_gear()
            car.ghost_timer = 1.2
            car.spin = 0.0

    def note_sector(self, car: Car, k: int, t: float) -> None:
        if self.best_sectors[k] is None or t < self.best_sectors[k]:
            self.best_sectors[k] = t

    def on_lap_completed(self, car: Car, lap_time: float) -> None:
        valid = (len(car.lap_times) - 1) not in car.invalid_laps
        if valid and not car.session_done:
            rec = self.game.records.check(self.track.definition.key, lap_time, car.name, car.profile.team,
                                          car is self.player)
            if rec == "track":
                self.add_feed(f"STRECKENREKORD: {car.short} {format_time(lap_time)}")
                if car is self.player:
                    self.message(f"NEUER STRECKENREKORD  {format_time(lap_time)}", PURPLE, 4.0)
            elif rec == "personal":
                self.message(f"Persönlicher Streckenrekord  {format_time(lap_time)}", GREEN, 3.0)
        if self.fastest_lap is None or lap_time < self.fastest_lap[0]:
            self.fastest_lap = (lap_time, car.short)
            self.add_feed(f"Schnellste Runde: {car.short} {format_time(lap_time)}")
        # the box is past the line: a car crossing it in the pit lane is still on the old set - don't
        # order a second stop for it
        if not car.session_done and car.pit_request is None and car.pit_state is None and not car.is_player:
            call = self.weather_tyre_call(car)
            car.pit_request = call or self.plan_pit(car)
            if call:
                self.add_feed(f"{car.short}: Box für {COMPOUNDS[call].name}")
        if car is self.player:
            if lap_time == car.best_lap and self.fastest_lap[1] == car.short:
                self.message(f"SCHNELLSTE RUNDE  {format_time(lap_time)}", PURPLE)
            elif lap_time == car.best_lap:
                self.message(f"Persönliche Bestzeit  {format_time(lap_time)}", GREEN)
            else:
                self.message(f"Runde  {format_time(lap_time)}", YELLOW)

    def standings(self) -> list[Car]:
        def key(c: Car) -> tuple[int, float, float]:
            if c.best_lap is not None:
                return (0, c.best_lap, 0.0)
            if c.lap_times:
                return (1, min(c.lap_times), 0.0)
            return (2, 0.0, -c.distance)
        return sorted(self.cars, key=key)

    def results_rows(self) -> list[tuple[str, ...]]:
        raise NotImplementedError

    def _label(self, text: str, color: Color) -> pygame.Surface:
        key = f"{text}|{color}"
        img = self._label_cache.get(key)
        if img is None:
            img = self.game.fonts.tiny.render(tr(text), True, color)
            self._label_cache[key] = img
        return img

    @property
    def show_brake_line(self) -> bool:
        p = self.cars[self.cam_index]
        return self.show_line or (isinstance(p, Player_Car) and p.assist_level >= 1 and p.autopilot is None)

    def _draw_overview(self, screen: pygame.Surface) -> None:
        area = pygame.Rect(240, 40, SCREEN_WIDTH - 520, SCREEN_HEIGHT - 120)
        if getattr(self, "_overview_cache", None) is None:
            surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            surf.fill((16, 18, 24))
            track = self.track
            scale, off = track.minimap_transform(area, pad=10)
            w = max(4, int(track.half_width * 2 * scale))
            pts = [(p.x * scale + off.x, p.y * scale + off.y) for p in track.center]
            for p in pts:
                pygame.draw.circle(surf, (90, 92, 104), p, w / 2 + 2)
            for p in pts:
                pygame.draw.circle(surf, (52, 54, 62), p, w / 2)
            if track.pit is not None:
                lane = [((l + r) * 0.5) * scale + off for l, r in track.pit.outline(24.0)]
                pygame.draw.lines(surf, (200, 170, 40), False, lane, 2)
            s0 = track.center[0] * scale + off
            pygame.draw.line(surf, WHITE, s0 - track.normals[0] * w, s0 + track.normals[0] * w, 3)
            self._overview_cache = (surf, scale, off)
        surf, scale, off = self._overview_cache
        screen.blit(surf, (0, 0))
        order = self.standings()
        for car in sorted(self.cars, key=lambda c: c is self.focus):
            p = car.pos * scale + off
            f = car.forward
            r = Vector2(-f.y, f.x)
            col = car.color if not car.dnf else (90, 90, 90)
            pygame.draw.polygon(screen, (0, 0, 0), [p + f * 10, p - f * 7 + r * 7, p - f * 7 - r * 7])
            pygame.draw.polygon(screen, col, [p + f * 8, p - f * 6 + r * 5, p - f * 6 - r * 5])
            label = f"{order.index(car) + 1} {car.short}"
            img = self._label(label, (0, 230, 255) if car is self.focus else WHITE)
            screen.blit(img, img.get_rect(midbottom=(p.x, p.y - 9)))
            if car is self.focus:
                pygame.draw.circle(screen, YELLOW, p, 14, 2)

    def draw(self, screen: pygame.Surface) -> None:
        if self.overview:
            self._draw_overview(screen)
            self._draw_overlays(screen)
            return
        if self.player2 is not None and not self.online:
            self._draw_split(screen)
            return
        self._draw_view(screen)
        self._draw_overlays(screen)

    def _draw_split(self, screen: pygame.Surface) -> None:
        """Two views side by side: each player's world view is rendered full size and its middle half is shown."""
        buf = getattr(self, "_split_buf", None)
        if buf is None:
            buf = self._split_buf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        half = SCREEN_WIDTH // 2
        keep = self.camera, self.r3d, self.cam_index
        for k, p in enumerate(self.players):
            self.camera, self.r3d, self.cam_index = self.cameras[p], self.r3ds[p], self.cars.index(p)
            self._draw_view(buf, rain=False)
            screen.blit(buf, (k * half, 0), pygame.Rect(half // 2, 0, half, SCREEN_HEIGHT))
        self.camera, self.r3d, self.cam_index = keep
        self.weather.draw(screen, self._frame_dt, view3d=self.view3d)
        pygame.draw.line(screen, (10, 10, 12), (half, 0), (half, SCREEN_HEIGHT), 4)
        if not self.hide_hud or self.paused:
            self.game.hud.draw_split(screen, self)
            for k, p in enumerate(self.players):
                self.pit_menus[p].draw(screen, self.game.fonts, p, self, center_x=half // 2 + k * half)
        if self.paused:
            self.game.hud.draw_pause(screen, self)

    def _draw_view(self, screen: pygame.Surface, rain: bool = True) -> None:
        if self.view3d:
            self.r3d.antialias = self.game.settings.antialias
            self.r3d.draw(screen, self.track, self.cars + self.extra_objects(), self.cars[self.cam_index],
                          self.show_brake_line,
                          self.game.fonts.tiny, self.garages(), rain=self.weather.rain)
            if rain:
                self.weather.draw(screen, self._frame_dt, view3d=True)
            return
        track = self.track
        off = self.camera.offset(track)
        screen.fill(track.definition.grass)
        assert track.surface is not None
        screen.blit(track.surface, (-round(off.x), -round(off.y)))

        if self.show_line:
            pts = [p - off for p in track.racing_line]
            visible = [p for p in pts if -50 < p.x < SCREEN_WIDTH + 50 and -50 < p.y < SCREEN_HEIGHT + 50]
            for p in visible[::2]:
                pygame.draw.circle(screen, (255, 220, 0), p, 2)
        if self.show_brake_line:
            self._draw_brake_line(screen, off)
        self._draw_garages_2d(screen, off)

        for car in sorted(self.cars, key=lambda c: not c.is_ghost):
            car.draw(screen, off)
        for obj in self.extra_objects():
            obj.draw(screen, off, self.time)
        self.fx.draw(screen, off)
        focus = self.cars[self.cam_index]
        if rain:
            self.weather.draw(screen, self._frame_dt, (focus.vel.x, focus.vel.y))

        for car in self.cars:
            sp = car.pos - off
            if not (0 < sp.x < SCREEN_WIDTH and 0 < sp.y < SCREEN_HEIGHT):
                continue
            col = (0, 230, 255) if car.is_player else WHITE
            img = self._label(("DU" if car is self.player and (self.player2 is None or self.online) else car.short)
                              if car.is_player else car.short, col)
            screen.blit(img, img.get_rect(midbottom=(sp.x, sp.y - 20)))
            if self.show_ai_info and isinstance(car, AI_Car):
                self._draw_ai_debug(screen, car, off)

    def _draw_brake_line(self, screen: pygame.Surface, off: Vector2) -> None:
        track, car = self.track, self.focus
        n = track.n
        for k in range(0, 130, 2):
            i = (car.idx + k) % n
            j = (i + 2) % n
            col = (235, 45, 45) if track.brake_zone[i] else (245, 210, 40) \
                if track.max_speed[i] < car.top_speed * 0.9 else (40, 220, 90)
            pygame.draw.line(screen, col, track.racing_line[i] - off, track.racing_line[j] - off, 4)

    def _draw_garages_2d(self, screen: pygame.Surface, off: Vector2) -> None:
        pit = self.track.pit
        if pit is None:
            return
        for pos, heading, color, team in self.garages():
            sp = pos - off
            if not (-80 < sp.x < SCREEN_WIDTH + 80 and -80 < sp.y < SCREEN_HEIGHT + 80):
                continue
            f = Vector2(math.cos(heading), math.sin(heading))
            r = Vector2(-f.y, f.x)
            pts = [sp + f * 24 + r * 16, sp + f * 24 - r * 16, sp - f * 24 - r * 16, sp - f * 24 + r * 16]
            pygame.draw.polygon(screen, (70, 72, 80), pts)
            pygame.draw.polygon(screen, color, pts, 3)
            img = self._label(team[:12], WHITE)
            screen.blit(img, img.get_rect(center=sp))
            lane = sp - r * (pit.side * (pit.HALF_WIDTH + 30))
            pygame.draw.line(screen, color, lane + f * 18 - r * 14, lane + f * 18 + r * 14, 3)
            pygame.draw.line(screen, color, lane - f * 18 - r * 14, lane - f * 18 + r * 14, 3)

    def _draw_overlays(self, screen: pygame.Surface) -> None:
        if self.hide_hud and not self.paused:
            return
        self.game.hud.draw_session(screen, self)
        if self.player is not None:
            self.pit_menu.draw(screen, self.game.fonts, self.player, self)
        cam_car = self.cars[self.cam_index]
        if self.show_ai_info and isinstance(cam_car, AI_Car):
            self.game.hud.draw_network(screen, cam_car)
        if self.paused:
            self.game.hud.draw_pause(screen, self)

    def _draw_ai_debug(self, screen: pygame.Surface, car: AI_Car, off: Vector2) -> None:
        sp = car.pos - off
        for p in lookahead_points(car, self.track):
            pygame.draw.line(screen, (90, 200, 255), sp, p - off, 1)
            pygame.draw.circle(screen, (90, 200, 255), p - off, 3)
        inputs = car.driver.inputs
        if inputs:
            fl, fc, fr, sl, sr = inputs[10:15]
            fwd, right = car.forward, car.right
            for val, side in ((fl, -1), (fc, 0), (fr, 1)):
                tip = car.pos + fwd * RADAR_RANGE * 0.5 + right * side * 30
                col = (255, int(255 * (1 - val)), 60) if val > 0 else (80, 80, 80)
                pygame.draw.line(screen, col, sp, tip - off, 2 if val > 0 else 1)
            for val, side in ((sl, -1), (sr, 1)):
                if val > 0:
                    pygame.draw.circle(screen, (255, 80, 60), car.pos + right * side * 22 - off, 5)
        steer, pedal = car.driver.outputs
        img = self._label(f"{car.profile.brain}  L{steer:+.1f} P{pedal:+.1f}", (255, 220, 120))
        screen.blit(img, img.get_rect(midtop=(sp.x, sp.y + 18)))


class PracticeSession(Session):
    ghost_field = True
    kind = "practice"
    title = "Freies Training"

    def __init__(self, game: "Game", track: "Track", config: WeekendConfig) -> None:
        super().__init__(game, track, config)
        self._create_cars(config.field)
        self._staggered_start()
        self.message("FREIES TRAINING - lerne die Strecke kennen", WHITE, 3.5)
        self.message("ENTER beendet die Session  ·  G Garage (Setup)", (180, 180, 180), 3.5)

    INSTANT_DURATION: float = 100.0

    def update(self, frame_dt: float) -> None:
        super().update(frame_dt)
        if self.config.instant and self.time > self.INSTANT_DURATION and not self.finished:
            self.finished = True
            self.game.session_finished(self)

    def on_key(self, key: int) -> None:
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not self.finished:
            self.finished = True
            self.game.session_finished(self)
        elif key == pygame.K_g and self.player is not None:
            game, player = self.game, self.player
            self.game.sound.stop()

            def back() -> None:
                player.apply_setup(game.setup_for(self.track))
                game.state = self
                self.message("Neues Setup montiert", (70, 170, 255), 2.0)
            game.open_garage(self.track.definition.key, player.perf if player.perf.name else None, back)

    def results_rows(self) -> list[tuple[str, ...]]:
        rows = []
        order = self.standings()
        best = order[0].best_lap if order and order[0].best_lap else None
        for pos, car in enumerate(order, 1):
            gap = "" if pos == 1 or car.best_lap is None or best is None else f"+{car.best_lap - best:.3f}"
            rows.append((str(pos), car.name, car.profile.team, format_time(car.best_lap), gap, str(car.laps_done)))
        return rows


class QualifyingSession(Session):
    ghost_field = True
    kind = "qualifying"
    title = "Qualifying"
    TIMED_LAPS: int = 3

    def __init__(self, game: "Game", track: "Track", config: WeekendConfig) -> None:
        super().__init__(game, track, config)
        self._create_cars(config.field)
        self._staggered_start()
        self.message(f"QUALIFYING - {self.TIMED_LAPS} gezeitete Runden", WHITE, 3.5)
        self.message("Die Bestzeit bestimmt deinen Startplatz", (180, 180, 180), 3.5)

    def compound_for(self, car: Car) -> str:
        if car.profile is self.config.player or car.profile is self.config.player2:
            return self.config.start_compound
        return Weather.best_compound(self.weather.wetness) or "soft"

    def on_lap_completed(self, car: Car, lap_time: float) -> None:
        super().on_lap_completed(car, lap_time)
        if car.laps_done >= self.TIMED_LAPS and not car.session_done:
            car.session_done = True
            car.retired_ghost = True
            if isinstance(car, Player_Car):
                self.enable_player_autopilot(car)
                if all(p.session_done for p in self.players):
                    self.time_scale = self.fast_forward_scale
                    self.message("Qualifying beendet - die übrigen Fahrer werden simuliert", WHITE, 4.0)
            if all(c.session_done for c in self.cars):
                self.end_timer = 2.5

    def results_rows(self) -> list[tuple[str, ...]]:
        rows = []
        order = self.standings()
        best = order[0].best_lap
        for pos, car in enumerate(order, 1):
            gap = "" if pos == 1 or car.best_lap is None or best is None else f"+{car.best_lap - best:.3f}"
            rows.append((str(pos), car.name, car.profile.team, format_time(car.best_lap), gap,
                         " ".join(format_time(t)[2:] + ("x" if k in car.invalid_laps else "")
                                  for k, t in enumerate(car.lap_times))))
        return rows


class RaceSession(Session):
    kind = "race"
    title = "Rennen"
    LIGHT_INTERVAL: float = 0.9
    LIGHTS_START: float = 1.2
    AFTER_WINNER_TIMEOUT: float = 45.0

    def __init__(self, game: "Game", track: "Track", config: WeekendConfig) -> None:
        super().__init__(game, track, config)
        self.total_laps = config.race_laps
        profiles = config.field
        if config.grid:
            by_name = {p.name: p for p in profiles}
            order = [by_name[n] for n in config.grid if n in by_name]
            order += [p for p in profiles if p not in order]
        else:
            order = profiles[:]
            random.shuffle(order)
        self._create_cars(order)
        for slot, car in enumerate(self.cars):
            pos, heading = track.grid_pose(slot)
            car.place(pos, heading)
            car.frozen = True
            car.grid_slot = slot + 1
        self.camera.snap(self.focus.pos)
        self.lights_on = 0
        self.lights_out_at = self.LIGHTS_START + 5 * self.LIGHT_INTERVAL + random.uniform(0.6, 2.2)
        self.race_started = False
        self.race_start_time = 0.0
        self.finish_order: list[Car] = []
        self.winner_time: float | None = None
        self.go_timer = 0.0
        self._last_order: list[Car] = list(self.cars)
        self._order_timer = 0.0
        self._player_pos = self.cars.index(self.player) + 1 if self.player is not None else 0
        self.rc = RaceControl(self, config.safety_car)
        self.pos_history: dict[Car, list[int]] = {c: [c.grid_slot] for c in self.cars}
        if self.player is not None:
            self.message(f"Startplatz P{self._player_pos} - warte auf die Ampel!", WHITE, 4.0)
        else:
            self.message("ZUSCHAUER-RENNEN  ·  C Kamera  ·  A TV-Regie  ·  +/- Zeitraffer", WHITE, 5.0)

    def pre_step(self, h: float) -> None:
        if self.race_started:
            self.go_timer = max(0.0, self.go_timer - h)
            self.rc.step(h)
            return
        if self.time >= self.LIGHTS_START:
            self.lights_on = min(5, 1 + int((self.time - self.LIGHTS_START) / self.LIGHT_INTERVAL))
        if self.time >= self.lights_out_at:
            self._judge_launch()
            self._plan_failures()
            self.race_started = True
            self.is_race_start_phase = True
            self.lights_on = 0
            self.go_timer = 1.5
            self.race_start_time = self.time
            for car in self.cars:
                car.frozen = False
                car.start_timing(self.time)

    @property
    def aero_active(self) -> bool:
        return self.race_started

    def _judge_launch(self) -> None:
        for p in self.players:
            if p.autopilot is not None:
                continue
            if p.throttle_held(self.game.controls):
                p.launch_spin = 1.2
                who = "" if self.player2 is None or (self.online and p is self.player) else f"{p.short}: "
                self.message(f"{who}ZU FRÜH GAS - Räder drehen durch!", (255, 140, 30), 2.5)
            elif p is self.player:
                self._await_reaction = True

    def neutralize(self, car: Car) -> None:
        self.rc.governor(car)
        self._yield_to_blue(car, PHYSICS_STEP)

    def extra_objects(self) -> list:
        return [self.rc.sc] if self.rc.sc is not None else []

    def on_retire(self, car: Car) -> None:
        if not car.in_pit:
            self.rc.incident(car, "dnf")

    def on_puncture(self, car: Car) -> None:
        if self.race_started:
            self.rc.puncture(car, "Kontakt")

    def post_collisions(self) -> None:
        if not self.race_started:
            return
        for car in self.cars:
            if car.crashes > car.seen_crashes:
                car.seen_crashes = car.crashes
                if not car.dnf:
                    self.rc.incident(car, "crash")

    def _plan_failures(self) -> None:
        self.failures: dict[str, str] = {}
        self._failure_at: dict[Car, float] = {}
        if not self.config.reliability:
            return
        L = self.track.length
        for car in self.cars:
            rel = self.config.reliability.get(car.profile.team)
            if rel is not None and random.random() < failure_chance(rel):
                self._failure_at[car] = random.uniform(0.1, 0.95) * self.total_laps * L

    def _check_failures(self) -> None:
        for car, at in list(self._failure_at.items()):
            if car.dnf or car.session_done:
                del self._failure_at[car]
            elif car.distance >= at:
                del self._failure_at[car]
                why = random.choice(FAILURES)
                self.failures[car.name] = why
                self.retire(car, why)

    def _check_reaction(self) -> None:
        p = self.player
        if p is None or not getattr(self, "_await_reaction", False):
            return
        if p.throttle > 0.0:
            self._await_reaction = False
            reaction = self.time - self.race_start_time
            col = GREEN if reaction < 0.25 else YELLOW if reaction < 0.45 else (255, 140, 30)
            self.message(f"Reaktionszeit {reaction:.3f} s", col, 2.5)
        elif self.time - self.race_start_time > 3.0:
            self._await_reaction = False

    BLUE_RANGE = 320.0

    def _check_blue_flag(self) -> None:
        """Blue flags for every car: a car a lap (or more) up within BLUE_RANGE behind means let it through."""
        L = self.track.length
        racing = [c for c in self.cars if not (c.dnf or c.session_done or c.in_pit or c.frozen)]
        for x in racing:
            chaser, gap = None, self.BLUE_RANGE
            for y in racing:
                lead = y.distance - x.distance
                if y is x or lead < L * 0.5:
                    continue
                behind = L - lead % L
                if 5.0 < behind < gap:
                    chaser, gap = y, behind
            x.blue_for, x.blue_gap = chaser, gap
        p = self.player
        if p is None or p.session_done:
            return
        if p.blue_for is not None:
            if self.blue_flag <= 0:
                self.message(f"BLAUE FLAGGE - lass {p.blue_for.short} überrunden", (60, 140, 255), 2.0)
            self.blue_flag = 1.0
            if p.blue_gap < 160:
                self._blue_ignored += 0.5
            if self._blue_ignored >= 12.0:
                self.stewards.penalty(p, 5.0, f"blaue Flaggen ignoriert ({p.blue_for.short})")
                self._blue_ignored = 0.0
            elif self._blue_ignored >= 6.0 and not self._blue_warned:
                self._blue_warned = True
                self.message("Blaue Flagge ignoriert - Verwarnung! Lass ihn vorbei", (255, 140, 30), 3.0)
        else:
            self._blue_ignored = max(0.0, self._blue_ignored - 0.5)
            if self._blue_ignored <= 0:
                self._blue_warned = False

    def _yield_to_blue(self, car: Car, h: float) -> None:
        """AI backmarker under a blue flag: lift a little and, once the lapping car is right behind, let it
        through - the backmarker turns 'ghost' (see-through, no contact, ignored by the chaser's sensors)."""
        chaser = car.blue_for
        if chaser is None or car is self.player or self.rc.active or car.blue_gap > 140.0:
            return
        car.throttle = min(car.throttle, 0.85)
        car.straight_mode = False
        car.ghost_timer = max(car.ghost_timer, 0.5)

    def standings(self) -> list[Car]:
        def key(c: Car) -> tuple[float, int, float]:
            if c.finish_time is not None:
                return (-c.laps_done, 0, c.finish_time)
            return (-(c.laps_done + 1), 1, -c.distance)
        classified = sorted((c for c in self.cars if not c.dnf), key=key)
        dnf = sorted((c for c in self.cars if c.dnf), key=lambda c: -c.distance)
        return classified + dnf

    def damage_pit_allowed(self, car: Car) -> bool:
        return self.race_started and self.total_laps - car.laps_done >= 2

    def repair_compound(self, car: Car) -> str:
        return self._compound_for_laps(max(1, self.total_laps - car.laps_done - 1))

    @staticmethod
    def _compound_for_laps(laps: int) -> str:
        return "soft" if laps <= 4 else "medium" if laps <= 9 else "hard"

    def compound_for(self, car: Car) -> str:
        if car.profile is self.config.player:
            return self.config.start_compound
        wet = Weather.best_compound(self.weather.wetness)
        if wet:
            return wet
        plan = self._compound_for_laps(self.total_laps)
        if plan != "soft" and random.random() < 0.3:
            plan = COMPOUND_ORDER[COMPOUND_ORDER.index(plan) - 1]
        return plan

    def pit_loss(self, car: Car, neutralised: bool = False) -> float:
        """Seconds a stop costs compared with staying on track (pit lane at the limiter + standing still)."""
        pit = self.track.pit
        if pit is None:
            return 25.0
        race_speed = max(100.0, car.top_speed * 0.75)
        loss = pit.length / SPEED_LIMIT - pit.length / race_speed + self.stop_time(car) + 2.0
        if not neutralised:
            return loss
        return loss * (0.5 if self.rc.mode == "SC" else 0.65)

    def _cumulative_cost(self, car: Car, compound: str, wear: float, rate: float, laps: int) -> list[float]:
        """cost[k] = time lost over the next k laps on this set against brand-new softs, puncture risk included."""
        lap = self._lap_estimate(car)
        grip = COMPOUNDS[compound].grip / COMPOUNDS["soft"].grip
        out = [0.0]
        for _ in range(laps):
            wear = min(1.0, wear + rate)
            cliff = max(0.0, wear - 0.70) / 0.30
            rel = grip * (1.0 - 0.12 * wear - 0.25 * cliff * cliff)
            cost = lap * 0.35 * (1.0 - math.sqrt(max(0.0, rel)))
            if wear > PUNCTURE_WEAR:
                cost += 30.0 * (wear - PUNCTURE_WEAR) / (1.0 - PUNCTURE_WEAR)
            out.append(out[-1] + cost)
        return out

    def _lap_estimate(self, car: Car) -> float:
        return car.best_lap or self.track.length / max(100.0, car.top_speed * 0.6)

    def _wear_rate(self, car: Car) -> float:
        """Wear per lap: measured once the set has a couple of laps on it, a physical estimate before that."""
        tyres = car.tyres
        expected = 0.85 * self._lap_estimate(car) * tyres.wear_factor / tyres.compound.life
        if tyres.laps >= 2 and tyres.wear > 0.04:
            measured = tyres.wear / tyres.laps
            return 0.5 * (expected + measured) if tyres.laps < 4 else measured
        return expected

    def plan_pit(self, car: Car, neutralised: bool = False) -> str | None:
        """Strategy: the cheapest way to the flag (any number of stops, any compounds) is found with a small
        dynamic programme. The car pits now only if the best plan that stops now beats the best plan that
        stays out. A request at the line means one more lap on the old set; under SC/VSC the next pit entry
        is used straight away and that stop is cheaper."""
        tyres = car.tyres
        remaining = self.total_laps - car.laps_done
        if tyres is None or tyres.laps < 2 or remaining < 2 or tyres.wear_factor <= 0:
            return None
        if tyres.compound.kind != "slick" or self.track.wetness > 0.15:
            return None     # wet running: the weather call decides
        rate = self._wear_rate(car)
        cur = tyres.compound
        full = self.pit_loss(car)
        first = self.pit_loss(car, neutralised)
        fresh = {key: self._cumulative_cost(car, key, 0.0, rate * cur.life / COMPOUNDS[key].life, remaining)
                 for key in COMPOUND_ORDER}
        best = [0.0] * (remaining + 1)
        opener = [""] * (remaining + 1)
        for n in range(1, remaining + 1):
            value, pick = float("inf"), ""
            for key, cum in fresh.items():
                for k in range(1, n + 1):
                    c = cum[k] + (0.0 if k == n else full + best[n - k])
                    if c < value:
                        value, pick = c, key
            best[n], opener[n] = value, pick
        old = self._cumulative_cost(car, cur.key, tyres.wear, rate, remaining)
        if neutralised and old[remaining] < full:
            return None   # would make it to the flag fine - a "cheap" stop would only be a pace gamble
        old_laps = 0 if neutralised else 1
        now = old[old_laps] + first + best[remaining - old_laps]
        later = min([old[remaining]] + [old[k] + full + best[remaining - k]
                                        for k in range(old_laps + 1, remaining)])
        margin = 0.5 + (sum(map(ord, car.name)) % 7) * 0.25
        if now + margin < later:
            return opener[remaining - old_laps]
        return None

    def on_lap_completed(self, car: Car, lap_time: float) -> None:
        if car.session_done:
            super().on_lap_completed(car, lap_time)
            return
        if car.laps_done >= self.total_laps or self.winner_time is not None:
            car.session_done = True
            car.finish_time = self.time - self.race_start_time + car.penalty_unserved
            car.penalty_unserved = 0.0
            car.retired_ghost = True
            self.finish_order.append(car)
            place = self.standings().index(car) + 1
            if self.winner_time is None:
                self.winner_time = self.time
                self.add_feed(f"Zielflagge! Erster im Ziel: {car.name}")
            if isinstance(car, Player_Car):
                self.enable_player_autopilot(car)
                if all(p.session_done for p in self.players):
                    self.time_scale = self.fast_forward_scale
                who = "Du bist" if self.player2 is None else f"{car.name}:"
                self.message(f"ZIEL! {who} P{place}", YELLOW if place > 3 else (255, 215, 0), 5.0)
            if all(c.session_done for c in self.cars):
                self.end_timer = 3.0
        elif car is self.player and car.laps_done == self.total_laps - 1:
            self.message("LETZTE RUNDE!", (255, 255, 255), 3.0)
        if car in self.pos_history and len(self.pos_history[car]) <= car.laps_done:
            self.pos_history[car].append(self.standings().index(car) + 1)
        super().on_lap_completed(car, lap_time)

    def update(self, frame_dt: float) -> None:
        super().update(frame_dt)
        if self.paused or not self.race_started:
            return
        self._check_reaction()
        if getattr(self, "_failure_at", None):
            self._check_failures()
        self.blue_flag = max(0.0, self.blue_flag - frame_dt)
        if self.winner_time is not None and self.end_timer is None and \
                self.time - self.winner_time > self.AFTER_WINNER_TIMEOUT:
            for car in self.standings():
                if car.finish_time is None and not car.dnf:
                    car.session_done = True
                    car.finish_time = 1e6 - car.distance
            self.end_timer = 1.0
        self._order_timer -= frame_dt
        if self._order_timer <= 0:
            self._order_timer = 0.4
            order = self.standings()
            if self.time - self.race_start_time > 4.0:
                for new_pos, car in enumerate(order):
                    old_pos = self._last_order.index(car)
                    if new_pos < old_pos and car.finish_time is None:
                        passed = self._last_order[new_pos]
                        if passed.finish_time is None:
                            self.add_feed(f"{car.short} überholt {passed.short}  ->  P{new_pos + 1}")
                            if car is self.player and passed.name == self.config.rival:
                                self.message(f"RIVALE {passed.short} ÜBERHOLT!", GREEN, 2.5)
                            elif passed is self.player and car.name == self.config.rival:
                                self.message(f"Rivale {car.short} ist vorbei!", (255, 90, 80), 2.5)
            self._check_blue_flag()
            p = order.index(self.player) + 1 if self.player is not None else 0
            if self.player is not None and p != self._player_pos and self.player.finish_time is None:
                who = "" if self.player2 is None or self.online else f"{self.player.short}: "
                self.message(f"{who}P{p}", GREEN if p < self._player_pos else (255, 90, 90), 1.5)
            self._player_pos = p
            self._last_order = order

    def scrutineering(self) -> list[Car]:
        """Post-race technical check: a skid block worn past the limit means disqualification."""
        out = []
        for car in self.cars:
            if car.dnf or car.plank_per_lap <= 0 or car.plank_wear <= PLANK_LIMIT_MM:
                continue
            car.dnf = car.dsq = True
            car.dsq_reason = f"Planke {car.plank_wear:.2f} mm abgenutzt (max. {PLANK_LIMIT_MM:.1f} mm)"
            out.append(car)
        return out

    def leader_gap(self, car: Car, leader: Car) -> str:
        if not self.race_started:
            return ""
        if car.dsq:
            return "DSQ"
        if car.dnf:
            return "DNF"
        if car is leader:
            return "Leader" if car.finish_time is None else format_time(car.finish_time)
        if car.finish_time is not None and leader.finish_time is not None and car.finish_time < 1e5:
            laps_down = leader.laps_done - car.laps_done
            if laps_down > 0:
                return f"+{laps_down} Rd."
            return f"+{car.finish_time - leader.finish_time:.3f}"
        laps_down = int((leader.distance - car.distance) // self.track.length)
        if laps_down >= 1:
            return f"+{laps_down} Rd."
        gap = time_gap(leader, car)
        return f"+{gap:.3f}" if gap is not None else "--"

    def results_rows(self) -> list[tuple[str, ...]]:
        order = self.standings()
        leader = order[0]
        rows = []
        for pos, car in enumerate(order, 1):
            gap = self.leader_gap(car, leader) if pos > 1 else format_time(car.finish_time)
            if car.penalty_total > 0:
                gap += f" +{car.penalty_total:.0f}s"
            rows.append((str(pos), car.name, car.profile.team, gap, format_time(car.best_lap), str(car.laps_done)))
        return rows
