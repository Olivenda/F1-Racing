# Copyright Olivenda (Oliver Petz) 2026
"""Online multiplayer over TCP.

The host runs the whole simulation (AI, physics, race control) exactly like an offline session; the guest's car is
the host's second player and is driven by the inputs the guest sends. The guest builds the same session locally,
but never simulates it: it mirrors the host's state from snapshots and only renders, plays sound and drives its
force feedback.

Everything on the wire is JSON (zlib-compressed, length-prefixed). No pickle: a forwarded port is reachable from
the whole internet, so nothing received may be able to create arbitrary objects.
"""

from __future__ import annotations

import json
import socket
import struct
import threading
import time
import zlib
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Any

import pygame
from pygame.math import Vector2

from .car_setup import CarSetup
from .profiles import DriverProfile, Team
from .tyres import COMPOUNDS, Compound

if TYPE_CHECKING:
    from .car import Car
    from .game import Game
    from .sessions import Session

DEFAULT_PORT = 56543
PROTOCOL = 1
SNAPSHOT_HZ = 30.0
INPUT_HZ = 60.0
MAX_FRAME = 8 << 20
CONNECT_TIMEOUT = 8.0

# keys the guest's game sends to the host instead of handling them itself (always / only while the pit menu is open)
FORWARD_KEYS = {pygame.K_SPACE, pygame.K_b, pygame.K_r, pygame.K_e, pygame.K_q}
FORWARD_MENU_KEYS = {pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_RETURN,
                     pygame.K_KP_ENTER, pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT}

# state that belongs to each screen (camera, HUD toggles, caches) or that is not data
SESSION_SKIP = {"game", "track", "config", "camera", "cameras", "r3d", "r3ds", "fx", "stewards", "pit_menu",
                "pit_menus", "cam_index", "paused", "view3d", "show_ai_info", "show_line", "show_fps", "hide_hud",
                "overview", "director_timer", "_label_cache", "_frame_dt", "messages", "player", "player2", "rc",
                "weather", "team_orders", "_split_buf", "finished", "end_timer", "cars", "time_scale",
                "_weather_timer", "_order_timer", "_player_pos", "_await_reaction", "online", "net_role"}
CAR_SKIP = {"track", "profile", "perf", "sf", "setup", "tyres", "damage", "_rot_cache", "_sprite", "_shadow",
            "samples", "_rec_timer", "keyset", "slot", "autopilot", "_fb_impulse", "_ffb_jolt", "color", "remote",
            "_tel", "_lap_log_start", "brain", "net", "driver", "is_player"}
WEATHER_SKIP = {"_drops", "_tint"}
RC_SKIP = {"s", "sc"}
SC_KEYS = ("s", "speed", "pos", "heading")


# --------------------------------------------------------------------------------------------------- codec
class _Skip:
    pass


SKIP = _Skip()
_DATACLASSES = {"WeekendConfig": None, "DriverProfile": DriverProfile, "Team": Team}


def enc(v: Any, cars: dict[int, int] | None = None) -> Any:
    """Python value -> JSON-able value. Car references become indices; unknown objects are SKIP."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, Vector2):
        return {"v": [round(v.x, 3), round(v.y, 3)]}
    if cars is not None and id(v) in cars:
        return {"c": cars[id(v)]}
    if isinstance(v, Compound):
        return {"k": v.key}
    if isinstance(v, (list, tuple, set, frozenset)):
        items = [enc(x, cars) for x in v]
        if any(x is SKIP for x in items):
            return SKIP
        if isinstance(v, list):
            return items
        return {"t": items} if isinstance(v, tuple) else {"s": items}
    if isinstance(v, dict):
        pairs = [[enc(k, cars), enc(x, cars)] for k, x in v.items()]
        if any(a is SKIP or b is SKIP for a, b in pairs):
            return SKIP
        return {"d": pairs}
    if is_dataclass(v) and type(v).__name__ in _DATACLASSES:
        out = {f.name: enc(getattr(v, f.name), cars) for f in fields(v)}
        return {"dc": type(v).__name__, "f": {k: x for k, x in out.items() if x is not SKIP}}
    return SKIP


def _hashable(v: Any) -> Any:
    return tuple(_hashable(x) for x in v) if isinstance(v, list) else v


def dec(v: Any, cars: list | None = None) -> Any:
    if isinstance(v, list):
        return [dec(x, cars) for x in v]
    if not isinstance(v, dict):
        return v
    if "v" in v:
        return Vector2(float(v["v"][0]), float(v["v"][1]))
    if "c" in v:
        i = int(v["c"])
        return cars[i] if cars is not None and 0 <= i < len(cars) else None
    if "k" in v:
        return COMPOUNDS.get(str(v["k"]), next(iter(COMPOUNDS.values())))
    if "t" in v:
        return tuple(dec(x, cars) for x in v["t"])
    if "s" in v:
        return {_hashable(dec(x, cars)) for x in v["s"]}
    if "d" in v:
        return {_hashable(dec(k, cars)): dec(x, cars) for k, x in v["d"]}
    if "dc" in v:
        cls = _DATACLASSES.get(str(v["dc"]))
        if cls is None:
            from .sessions import WeekendConfig
            cls = WeekendConfig if v["dc"] == "WeekendConfig" else None
        if cls is None:
            raise ValueError("unknown type")
        known = {f.name for f in fields(cls)}
        return cls(**{k: dec(x, cars) for k, x in v["f"].items() if k in known})
    raise ValueError("bad value")


# --------------------------------------------------------------------------------------------------- transport
class Connection:
    """Length-prefixed, zlib-compressed JSON messages over a non-blocking TCP socket."""

    def __init__(self, sock: socket.socket) -> None:
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = sock
        self._in = bytearray()
        self._out = bytearray()
        self.closed = False
        self.sent_bytes = 0
        self.recv_bytes = 0

    def send(self, msg: dict) -> None:
        if self.closed:
            return
        data = zlib.compress(json.dumps(msg, separators=(",", ":")).encode("utf-8"), 1)
        self._out += struct.pack(">I", len(data)) + data
        self.flush()

    def flush(self) -> None:
        while self._out and not self.closed:
            try:
                n = self.sock.send(self._out)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                self.close()
                return
            self.sent_bytes += n
            del self._out[:n]
        if len(self._out) > 4 * MAX_FRAME:
            self.close()        # the other side stopped reading

    def poll(self) -> list[dict]:
        if self.closed:
            return []
        self.flush()
        while True:
            try:
                chunk = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self.close()
                break
            if not chunk:
                self.close()
                break
            self.recv_bytes += len(chunk)
            self._in += chunk
        out = []
        while len(self._in) >= 4:
            size = struct.unpack(">I", self._in[:4])[0]
            if size > MAX_FRAME:
                self.close()
                return out
            if len(self._in) < 4 + size:
                break
            raw = bytes(self._in[4:4 + size])
            del self._in[:4 + size]
            try:
                msg = json.loads(zlib.decompress(raw).decode("utf-8"))
            except (ValueError, zlib.error):
                self.close()
                return out
            if isinstance(msg, dict):
                out.append(msg)
        return out

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                self.sock.close()
            except OSError:
                pass


# --------------------------------------------------------------------------------------------------- inputs
class RemoteInput:
    """Stands in for Controls on the host for the guest's car: the guest's raw keys, pedals and wheel."""

    def __init__(self) -> None:
        self.keys: tuple[bool, bool, bool, bool] = (False, False, False, False)
        self.throttle: float | None = None
        self.brake: float | None = None
        self.steer: float | None = None
        self.device_kind = "keyboard"

    def update(self, msg: dict) -> None:
        keys = msg.get("k", [])
        if isinstance(keys, list) and len(keys) == 4:
            self.keys = tuple(bool(k) for k in keys)

        def unit(name: str, low: float) -> float | None:
            v = msg.get(name)
            return None if not isinstance(v, (int, float)) else max(low, min(1.0, float(v)))
        self.throttle, self.brake, self.steer = unit("th", 0.0), unit("br", 0.0), unit("st", -1.0)
        self.device_kind = "wheel" if msg.get("kind") == "wheel" else "pad" if msg.get("kind") == "pad" else "keyboard"

    def pedal(self, which: str, slot: int = 0) -> float | None:
        return self.throttle if which == "throttle" else self.brake

    def steering(self, slot: int = 0) -> float | None:
        return self.steer

    def kind(self, slot: int = 0) -> str:
        return self.device_kind

    def has_device(self, slot: int = 0) -> bool:
        return False

    def throttle_held(self, slot: int = 0) -> bool:
        return (self.throttle or 0.0) > 0.5


def local_input(car, controls) -> dict:
    """What the guest sends every frame: the same raw inputs Player_Car.control reads on the host."""
    keys = car.held_keys(controls)
    kind = controls.kind(0) if controls.has_device(0) else "keyboard"
    return {"t": "in", "k": [bool(k) for k in keys], "th": controls.pedal("throttle", 0),
            "br": controls.pedal("brake", 0), "st": controls.steering(0), "kind": kind}


# --------------------------------------------------------------------------------------------------- snapshots
def _state(obj: Any, skip: set[str], cars: dict[int, int], cache: dict, ch: str,
           only: set[str] | None = None) -> dict:
    out = {}
    for k, v in vars(obj).items():
        if k in skip or (only is not None and k not in only):
            continue
        if isinstance(v, list) and len(v) > 12:
            # long lists only grow (lap logs, lap times): re-encode them only when their length changes
            key = (ch, k)
            hit = cache.get(key)
            if hit is not None and hit[0] == id(v) and hit[1] == len(v):
                out[k] = hit[2]
                continue
            e = enc(v, cars)
            cache[key] = (id(v), len(v), e)
        else:
            e = enc(v, cars)
        if e is not SKIP:
            out[k] = e
    return out


class SnapshotWriter:
    """Host side: per-channel deltas of the session, every car, its tyres and damage, weather and race control."""

    def __init__(self, session: "Session", guest: "Car | None") -> None:
        self.session = session
        self.guest = guest
        self.cars = {id(c): i for i, c in enumerate(session.cars)}
        self.last: dict[str, dict] = {}
        self.cache: dict = {}
        player = session.player or session.cars[0]
        self.car_keys = set(vars(player)) - CAR_SKIP

    def _delta(self, ch: str, state: dict) -> dict:
        last = self.last.setdefault(ch, {})
        out = {k: v for k, v in state.items() if k not in last or last[k] != v}
        last.update(out)
        return out

    def build(self) -> dict:
        s, cars, cache = self.session, self.cars, self.cache
        msg: dict[str, Any] = {"t": "snap", "time": round(s.time, 4)}
        msg["s"] = self._delta("s", _state(s, SESSION_SKIP, cars, cache, "s"))
        msg["c"] = [self._delta(f"c{i}", _state(c, CAR_SKIP, cars, cache, f"c{i}", self.car_keys))
                    for i, c in enumerate(s.cars)]
        msg["ty"] = [self._delta(f"t{i}", _state(c.tyres, set(), cars, cache, f"t{i}")) if c.tyres else {}
                     for i, c in enumerate(s.cars)]
        msg["dm"] = [self._delta(f"d{i}", _state(c.damage, set(), cars, cache, f"d{i}"))
                     for i, c in enumerate(s.cars)]
        msg["w"] = self._delta("w", _state(s.weather, WEATHER_SKIP, cars, cache, "w"))
        msg["wet"] = round(s.track.wetness, 4)
        rc = getattr(s, "rc", None)
        if rc is not None:
            msg["rc"] = self._delta("rc", _state(rc, RC_SKIP, cars, cache, "rc"))
            msg["sc"] = None if rc.sc is None else {k: enc(getattr(rc.sc, k)) for k in SC_KEYS}
        if self.guest is not None and self.guest in s.pit_menus:
            msg["pm"] = _state(s.pit_menus[self.guest], set(), cars, cache, "pm")
        msg["feed"] = enc(s.feed)
        msg["fin"] = bool(s.finished)
        msg["hp"] = bool(s.paused)
        return msg


def _apply(obj: Any, state: dict, cars: list) -> None:
    have = vars(obj)
    for k, v in state.items():
        if k.startswith("__") or k not in have:
            continue
        try:
            setattr(obj, k, dec(v, cars))
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            pass


def apply_snapshot(session: "Session", msg: dict) -> None:
    """Guest side: write a host snapshot into the local (never simulated) session."""
    cars = session.cars
    _apply(session, msg.get("s", {}), cars)
    for group, attr in (("c", None), ("ty", "tyres"), ("dm", "damage")):
        for car, state in zip(cars, msg.get(group, [])):
            target = car if attr is None else getattr(car, attr, None)
            if target is not None and state:
                _apply(target, state, cars)
    _apply(session.weather, msg.get("w", {}), cars)
    if isinstance(msg.get("wet"), (int, float)):
        session.track.wetness = float(msg["wet"])
    rc = getattr(session, "rc", None)
    if rc is not None and "rc" in msg:
        _apply(rc, msg["rc"], cars)
        sc_state = msg.get("sc")
        if sc_state is None:
            rc.sc = None
        else:
            if rc.sc is None:
                from .race_control import SafetyCar
                rc.sc = SafetyCar(session, 0.0)
            for k in SC_KEYS:
                if k in sc_state:
                    setattr(rc.sc, k, dec(sc_state[k]))
    if "pm" in msg and session.player is not None:
        _apply(session.pit_menu, msg["pm"], cars)
    if isinstance(msg.get("feed"), list):
        try:
            session.feed = dec(msg["feed"], cars)
        except (ValueError, TypeError):
            pass
    session.host_paused = bool(msg.get("hp"))
    session.host_finished = bool(msg.get("fin"))


# --------------------------------------------------------------------------------------------------- lobby / link
def local_addresses() -> list[str]:
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))       # no packet is sent: only picks the outgoing interface
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips


class NetPlay:
    """One online link: host (listens on a port) or guest (connects to an address)."""

    def __init__(self, game: "Game", role: str, port: int, address: str = "") -> None:
        self.game = game
        self.role = role
        self.port = port
        self.address = address
        self.conn: Connection | None = None
        self.listener: socket.socket | None = None
        self.status = ""
        self.error = ""
        self.remote_name = ""
        self.remote_setups: dict[str, dict] = {}
        self.remote_assists = 1
        self.remote_gearbox = "auto"
        self.remote_input = RemoteInput()
        self.session: "Session | None" = None
        self.writer: SnapshotWriter | None = None
        self._snap_timer = 0.0
        self._input_timer = 0.0
        self._last_input: dict | None = None
        self.snapshots: list[dict] = []
        self.waiting_session: dict | None = None
        self.ping_ms = 0.0
        self._ping_timer = 0.0
        self._connect_thread: threading.Thread | None = None
        self._pending_sock: socket.socket | None = None
        self.was_connected = False
        self.lobby: dict[str, str] = {}
        self._lobby_sent: tuple | None = None
        if role == "host":
            self._listen()
        else:
            self._connect()

    # ---- setup
    def _listen(self) -> None:
        try:
            ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            ls.bind(("0.0.0.0", self.port))
            ls.listen(1)
            ls.setblocking(False)
            self.listener = ls
            self.status = "listening"
        except OSError as e:
            self.status, self.error = "error", f"Port {self.port} nicht verfügbar ({e.strerror or e})"

    def _connect(self) -> None:
        self.status = "connecting"

        def run() -> None:
            try:
                sock = socket.create_connection((self.address, self.port), timeout=CONNECT_TIMEOUT)
                self._pending_sock = sock
            except OSError as e:
                self.error = f"Keine Verbindung zu {self.address}:{self.port} ({e.strerror or e})"
                self.status = "error"
        self._connect_thread = threading.Thread(target=run, daemon=True)
        self._connect_thread.start()

    @property
    def connected(self) -> bool:
        return self.status == "connected" and self.conn is not None and not self.conn.closed

    def close(self) -> None:
        if self.conn is not None and not self.conn.closed:
            self.conn.send({"t": "bye"})
            self.conn.close()
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass
            self.listener = None
        self.status = "closed"

    def send(self, msg: dict) -> None:
        if self.conn is not None:
            self.conn.send(msg)

    def _hello(self) -> dict:
        st = self.game.settings
        return {"t": "hello", "v": PROTOCOL, "name": st.player_name, "assists": st.assists, "gearbox": st.gearbox,
                "setups": {k: vars(s) for k, s in self.game.setups.items()}}

    # ---- per frame
    def poll(self, dt: float) -> None:
        if self.status == "listening" and self.listener is not None:
            try:
                sock, addr = self.listener.accept()
            except (BlockingIOError, InterruptedError):
                sock = None
            except OSError:
                sock = None
            if sock is not None:
                self.conn = Connection(sock)
                self.status = "handshake"
                self.address = addr[0]
                self.listener.close()
                self.listener = None
        if self.status == "connecting" and self._pending_sock is not None:
            self.conn = Connection(self._pending_sock)
            self._pending_sock = None
            self.status = "handshake"
            self.conn.send(self._hello())
        if self.conn is None:
            return
        for msg in self.conn.poll():
            try:
                self._handle(msg)
            except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                self.error = "Ungültige Daten empfangen - Verbindung getrennt"
                self.conn.close()
                break
        if self.conn.closed and self.status != "closed":
            self.status = "closed"
            if not self.error:
                self.error = "Verbindung getrennt"
            self.game.on_net_lost(self)
            return
        self._ping_timer -= dt
        if self.connected and self._ping_timer <= 0:
            self._ping_timer = 1.0
            self.send({"t": "ping", "at": time.perf_counter()})

    def _handle(self, msg: dict) -> None:
        kind = msg.get("t")
        if kind == "ping":
            self.send({"t": "pong", "at": msg.get("at")})
        elif kind == "pong" and isinstance(msg.get("at"), (int, float)):
            self.ping_ms = (time.perf_counter() - float(msg["at"])) * 1000.0
        elif kind == "bye":
            self.error = "Der Mitspieler hat das Spiel verlassen"
            self.conn.close()
        elif kind == "hello" and self.role == "host":
            if msg.get("v") != PROTOCOL:
                self.conn.send({"t": "reject", "why": "Andere Spielversion"})
                self.conn.close()
                return
            self._read_profile(msg)
            self.status = "connected"
            self.was_connected = True
            self.send({"t": "welcome", "v": PROTOCOL, "name": self.game.settings.player_name})
        elif kind == "welcome" and self.role == "client":
            self.remote_name = str(msg.get("name", "Host"))[:24]
            self.status = "connected"
            self.was_connected = True
        elif kind == "reject":
            self.error = str(msg.get("why", "Abgelehnt"))[:80]
            self.conn.close()
        elif kind == "setups" and self.role == "host":
            self._read_setups(msg.get("setups"))
        elif kind == "in" and self.role == "host":
            self.remote_input.update(msg)
        elif kind == "key" and self.role == "host":
            self._remote_key(msg)
        elif kind == "session" and self.role == "client":
            self.waiting_session = msg
        elif kind == "snap" and self.role == "client":
            self.snapshots.append(msg)
        elif kind == "lobby" and self.role == "client":
            self.lobby = {"track": str(msg.get("track", ""))[:40], "text": str(msg.get("text", ""))[:120]}

    def _read_profile(self, msg: dict) -> None:
        self.remote_name = str(msg.get("name") or "Gast")[:24]
        self.remote_assists = max(0, min(2, int(msg.get("assists", 1))))
        self.remote_gearbox = "manual" if msg.get("gearbox") == "manual" else "auto"
        self._read_setups(msg.get("setups"))

    def _read_setups(self, setups: Any) -> None:
        if not isinstance(setups, dict):
            return
        for key, values in list(setups.items())[:64]:
            if isinstance(values, dict):
                try:
                    CarSetup.from_dict(values)
                    self.remote_setups[str(key)] = values
                except (TypeError, ValueError):
                    pass

    def remote_setup(self, track_key: str) -> CarSetup | None:
        values = self.remote_setups.get(track_key)
        return CarSetup.from_dict(values) if values else None

    def _remote_key(self, msg: dict) -> None:
        key = msg.get("key")
        if not isinstance(key, int) or key not in FORWARD_KEYS | FORWARD_MENU_KEYS:
            return
        from .sessions import Session
        state = self.game.state
        if isinstance(state, Session) and state is self.session and state.player2 is not None:
            event = pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0,
                                       net_remote=True, from_joystick=bool(msg.get("joy")))
            state.handle_event(event)

    # ---- host
    def host_started(self, session: "Session", kind: str) -> None:
        """A new session runs on the host: tell the guest to build the same one."""
        self.session = session
        self.writer = SnapshotWriter(session, session.player2)
        self._snap_timer = 0.0
        cfg = enc(session.config)
        self.send({"t": "session", "kind": kind, "cfg": cfg, "order": [c.name for c in session.cars]})

    def host_tick(self, dt: float) -> None:
        if not self.connected or self.writer is None or self.session is None:
            return
        self._snap_timer -= dt
        finished = self.session.finished
        if self._snap_timer > 0 and not finished:
            return
        self._snap_timer = 1.0 / SNAPSHOT_HZ
        self.send(self.writer.build())
        if finished:
            self.writer = None          # the last snapshot carried the result

    def host_lobby(self, game: "Game") -> None:
        """While the host picks track and mode, the guest sees the choice (and can set up for that track)."""
        from .screens import SetupScreen
        from .track import TRACK_DEFS
        if not self.connected or not isinstance(game.state, SetupScreen):
            return
        c = game.menu_choice
        td = TRACK_DEFS[c["track"]]
        screen = game.state
        info = (td.key, td.name, screen.modes[c["mode"]][1], c["laps"])
        if info != self._lobby_sent:
            self._lobby_sent = info
            self.send({"t": "lobby", "track": td.key, "text": f"{td.name} · {info[2]} · {c['laps']} Runden"})

    # ---- guest
    def client_frame(self, session: "Session", dt: float) -> None:
        """Replaces Session.update on the guest: mirror, extrapolate between snapshots, render-side updates."""
        game = self.game
        game.sound.update(session)
        session._frame_dt = dt
        got = bool(self.snapshots)
        for msg in self.snapshots:
            apply_snapshot(session, msg)
        self.snapshots.clear()
        if not got and not getattr(session, "host_paused", False):
            for car in session.cars:
                if not car.frozen:
                    car.pos += car.vel * dt     # dead reckoning until the next snapshot
        session.fx.update(session, dt)
        session.camera.update(session.cars[session.cam_index], dt)
        if session.view3d:
            session.r3d.update_camera(session.cars[session.cam_index], dt)
        for m in session.messages:
            m[2] -= dt
        session.messages = [m for m in session.messages if m[2] > 0]
        player = session.player
        if player is not None:
            self._input_timer += dt
            msg = local_input(player, game.controls)
            if (msg != self._last_input and self._input_timer >= 1.0 / INPUT_HZ) or self._input_timer >= 0.25:
                self._input_timer = 0.0
                self._last_input = msg
                self.send(msg)
            if not session.paused:
                player._feedback(game.controls, dt)
        if getattr(session, "host_finished", False) and not session.finished:
            session.finished = True
            game.session_finished(session)

    def forward_key(self, session: "Session", event: pygame.event.Event) -> bool:
        """Guest: driving keys go to the host's simulation. True when the key was sent (and is not used locally)."""
        key = event.key
        menu_open = session.pit_menu.open
        if key in FORWARD_KEYS and not (session.paused and key == pygame.K_r) or (menu_open and key in FORWARD_MENU_KEYS):
            self.send({"t": "key", "key": key, "joy": bool(getattr(event, "from_joystick", False))})
            return True
        return False
