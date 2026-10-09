# Copyright Olivenda (Oliver Petz) 2026
"""Wheelbase / pedal / gamepad input.

Every device gets a binding profile (stored per device name in data/controls.json). An axis binding remembers
its rest and full-travel raw values, so inverted pedals, combined pedal axes and triggers that rest at -1 all
normalise to 0..1 (pedals) or -1..1 (steering) the same way.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import pygame

from .profiles import DATA_DIR

CONTROLS_FILE = DATA_DIR / "controls.json"

# in-race actions that can sit on a button; each one is delivered as the keyboard key the session already knows
ACTIONS: dict[str, tuple[str, int]] = {
    "drs": ("Gerade-Modus / DRS", pygame.K_SPACE),
    "pit": ("Boxenstopp anfordern", pygame.K_b),
    "pause": ("Pause", pygame.K_p),
    "menu": ("Menü / Verlassen (ESC)", pygame.K_ESCAPE),
    "camera": ("Kamera wechseln", pygame.K_k),
    "view": ("2D / 3D", pygame.K_v),
    "reset": ("Auto zurücksetzen", pygame.K_r),
    "map": ("Streckenübersicht", pygame.K_m),
    "continue": ("Weiter / Training beenden", pygame.K_RETURN),
}
AXES: dict[str, str] = {"steer": "Lenkung", "throttle": "Gaspedal", "brake": "Bremspedal"}
DEVICE_KINDS = {"wheel": "Lenkrad + Pedale", "gamepad": "Gamepad"}

# XInput layout as SDL reports it on Windows (Xbox pads and most PC gamepads)
_PAD_BUTTONS = {"drs": 2, "pit": 3, "pause": 7, "menu": 1, "camera": 4, "view": 5, "reset": 6, "map": 9,
                "continue": 0}
_WHEEL_HINTS = ("wheel", "g29", "g920", "g923", "g27", "g25", "t300", "t150", "tmx", "t248", "t-gt", "fanatec",
                "csl", "clubsport", "podium", "moza", "simucube", "thrustmaster", "lenkrad", "racing", "dd1", "dd2",
                "r5", "r9", "r12", "r16", "r21", "sim")
_PAD_HINTS = ("xbox", "xinput", "controller", "gamepad", "dualsense", "dualshock", "ps4", "ps5", "wireless",
              "8bitdo", "switch pro")


@dataclass
class AxisBinding:
    axis: int = -1
    rest: float = 0.0
    full: float = 1.0

    def read(self, joy: "pygame.joystick.JoystickType") -> float | None:
        if self.axis < 0 or self.axis >= joy.get_numaxes():
            return None
        span = self.full - self.rest
        if abs(span) < 1e-3:
            return None
        return (joy.get_axis(self.axis) - self.rest) / span


@dataclass
class DeviceProfile:
    kind: str = "gamepad"
    steer: AxisBinding = field(default_factory=lambda: AxisBinding(0, 0.0, 1.0))
    throttle: AxisBinding = field(default_factory=lambda: AxisBinding(5, -1.0, 1.0))
    brake: AxisBinding = field(default_factory=lambda: AxisBinding(4, -1.0, 1.0))
    buttons: dict[str, int] = field(default_factory=lambda: dict(_PAD_BUTTONS))
    # steering feel
    deadzone: float = 0.06          # fraction of the axis ignored around centre (gamepad sticks drift)
    linearity: float = 1.4          # >1 = finer control around centre
    saturation: float = 1.0         # fraction of the axis that already gives full lock (wheel: 0.5 = half turn)
    pedal_deadzone: float = 0.04
    rumble: float = 0.7             # vibration / force strength 0..1

    @classmethod
    def for_device(cls, name: str, axes: int) -> "DeviceProfile":
        low = name.lower()
        if any(h in low for h in _WHEEL_HINTS) and not any(h in low for h in _PAD_HINTS):
            # wheel bases: steering on axis 0, pedals are usually separate axes resting at +1 (released)
            return cls(kind="wheel", steer=AxisBinding(0, 0.0, 1.0),
                       throttle=AxisBinding(min(1, axes - 1), 1.0, -1.0) if axes > 1 else AxisBinding(-1),
                       brake=AxisBinding(min(2, axes - 1), 1.0, -1.0) if axes > 2 else AxisBinding(-1),
                       buttons={"drs": 0, "pit": 1, "pause": 9, "camera": 2, "view": 3, "reset": 8,
                                "map": -1, "continue": 6, "menu": 7},
                       deadzone=0.0, linearity=1.0, saturation=0.5, pedal_deadzone=0.02, rumble=0.8)
        prof = cls()
        if axes < 6:  # simple pads without analog triggers: right stick Y as combined throttle/brake
            prof.throttle = AxisBinding(min(3, axes - 1), 0.0, -1.0)
            prof.brake = AxisBinding(min(3, axes - 1), 0.0, 1.0)
        return prof

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict) -> "DeviceProfile":
        prof = cls()
        for key in ("kind", "deadzone", "linearity", "saturation", "pedal_deadzone", "rumble"):
            if key in raw:
                setattr(prof, key, type(getattr(prof, key))(raw[key]))
        for key in AXES:
            if isinstance(raw.get(key), dict):
                b = raw[key]
                setattr(prof, key, AxisBinding(int(b.get("axis", -1)), float(b.get("rest", 0.0)),
                                               float(b.get("full", 1.0))))
        if isinstance(raw.get("buttons"), dict):
            prof.buttons = {k: int(v) for k, v in raw["buttons"].items() if k in ACTIONS}
        if prof.kind not in DEVICE_KINDS:
            prof.kind = "gamepad"
        return prof


class Controls:
    """Owns all connected joysticks. One device is 'active' (the one last touched)."""

    NAV_REPEAT_DELAY = 0.35
    NAV_REPEAT_RATE = 0.12

    def __init__(self) -> None:
        pygame.joystick.init()
        self.joys: dict[int, pygame.joystick.JoystickType] = {}
        self.profiles: dict[str, DeviceProfile] = {}
        self.active: int | None = None
        self.enabled = True
        self._nav_dir: tuple[int, int] = (0, 0)
        self._nav_timer = 0.0
        self._rumble_until = 0
        self._load()
        for k in range(pygame.joystick.get_count()):
            self._add(k)

    # ------------------------------------------------------------------ persistence
    def _load(self) -> None:
        try:
            raw = json.loads(CONTROLS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for name, data in raw.get("devices", {}).items():
            if isinstance(data, dict):
                self.profiles[name] = DeviceProfile.from_json(data)
        self.enabled = bool(raw.get("enabled", True))

    def save(self) -> None:
        CONTROLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"enabled": self.enabled, "devices": {n: p.to_json() for n, p in self.profiles.items()}}
        CONTROLS_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")

    # ------------------------------------------------------------------ devices
    def _add(self, device_index: int) -> None:
        try:
            joy = pygame.joystick.Joystick(device_index)
            joy.init()
        except pygame.error:
            return
        self.joys[joy.get_instance_id()] = joy
        name = joy.get_name()
        if name not in self.profiles:
            self.profiles[name] = DeviceProfile.for_device(name, joy.get_numaxes())
        # a wheel always wins over a pad that happens to be plugged in as well
        if self.active not in self.joys or (self.profiles[name].kind == "wheel"
                                            and self.profile_of(self.active).kind != "wheel"):
            self.active = joy.get_instance_id()

    @property
    def joystick(self) -> "pygame.joystick.JoystickType | None":
        return self.joys.get(self.active) if self.active is not None else None

    @property
    def profile(self) -> DeviceProfile | None:
        joy = self.joystick
        return self.profiles.get(joy.get_name()) if joy is not None else None

    def profile_of(self, instance_id: int) -> DeviceProfile:
        return self.profiles[self.joys[instance_id].get_name()]

    @property
    def connected(self) -> bool:
        return self.enabled and self.joystick is not None

    def device_name(self) -> str:
        joy = self.joystick
        return joy.get_name() if joy is not None else "kein Gerät"

    def cycle_device(self) -> None:
        ids = list(self.joys)
        if not ids:
            return
        k = ids.index(self.active) if self.active in ids else -1
        self.active = ids[(k + 1) % len(ids)]

    # ------------------------------------------------------------------ driving input
    def steering(self) -> float | None:
        joy, prof = self.joystick, self.profile
        if not self.enabled or joy is None or prof is None:
            return None
        v = prof.steer.read(joy)
        if v is None:
            return None
        sign = 1.0 if v >= 0 else -1.0
        mag = abs(v)
        if mag <= prof.deadzone:
            return 0.0
        mag = (mag - prof.deadzone) / max(1e-3, 1.0 - prof.deadzone)
        mag = min(1.0, mag / max(0.05, prof.saturation))
        return sign * mag ** max(0.3, prof.linearity)

    def pedal(self, which: str) -> float | None:
        joy, prof = self.joystick, self.profile
        if not self.enabled or joy is None or prof is None:
            return None
        binding = getattr(prof, which)
        if abs(binding.rest) > 0.9 and binding.axis < joy.get_numaxes() and joy.get_axis(binding.axis) == 0.0:
            # SDL reports 0.0 for triggers/pedals until their first motion event - that is "released", not half
            return 0.0
        v = binding.read(joy)
        if v is None:
            return None
        v = max(0.0, min(1.0, v))
        dz = prof.pedal_deadzone
        return 0.0 if v <= dz else min(1.0, (v - dz) / max(1e-3, 1.0 - 2 * dz))

    def throttle_held(self) -> bool:
        v = self.pedal("throttle")
        return v is not None and v > 0.2

    def rumble(self, low: float, high: float, ms: int) -> None:
        """Short vibration on pads / force jolt on wheels that expose SDL rumble."""
        joy, prof = self.joystick, self.profile
        if not self.connected or joy is None or prof is None or prof.rumble <= 0:
            return
        now = pygame.time.get_ticks()
        if now < self._rumble_until - ms // 2:
            return
        self._rumble_until = now + ms
        try:
            joy.rumble(min(1.0, low * prof.rumble), min(1.0, high * prof.rumble), ms)
        except (pygame.error, AttributeError):
            pass

    def stop_rumble(self) -> None:
        joy = self.joystick
        if joy is not None:
            try:
                joy.stop_rumble()
            except (pygame.error, AttributeError):
                pass

    # ------------------------------------------------------------------ events -> keys
    def translate(self, event: pygame.event.Event, in_session: bool) -> list[pygame.event.Event]:
        """Turn joystick events into the keyboard events the screens already understand."""
        if event.type == pygame.JOYDEVICEADDED:
            self._add(event.device_index)
            return []
        if event.type == pygame.JOYDEVICEREMOVED:
            self.joys.pop(event.instance_id, None)
            if self.active == event.instance_id:
                self.active = next(iter(self.joys), None)
            return []
        if not self.enabled:
            return []
        if event.type == pygame.JOYBUTTONDOWN:
            if event.instance_id in self.joys and event.instance_id != self.active:
                self.active = event.instance_id
            prof = self.profiles.get(self.joys[event.instance_id].get_name()) if event.instance_id in self.joys \
                else None
            if prof is None:
                return []
            if in_session:
                return [_key(ACTIONS[a][1]) for a, b in prof.buttons.items() if b == event.button and a in ACTIONS]
            menu = {0: pygame.K_RETURN, 1: pygame.K_ESCAPE, 7: pygame.K_RETURN, 6: pygame.K_ESCAPE}
            if prof.kind == "wheel":
                menu = {prof.buttons.get("drs", 0): pygame.K_RETURN, prof.buttons.get("pit", 1): pygame.K_ESCAPE}
            key = menu.get(event.button)
            return [_key(key)] if key is not None else []
        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            out = []
            if y:
                out.append(_key(pygame.K_UP if y > 0 else pygame.K_DOWN))
            if x:
                out.append(_key(pygame.K_RIGHT if x > 0 else pygame.K_LEFT))
            return out
        return []

    def menu_stick(self, dt: float, in_session: bool) -> list[pygame.event.Event]:
        """Left stick / wheel acts as arrow keys in menus, with key-repeat."""
        joy, prof = self.joystick, self.profile
        if in_session or not self.enabled or joy is None or prof is None or prof.kind == "wheel":
            self._nav_dir = (0, 0)
            return []
        x = joy.get_axis(0) if joy.get_numaxes() > 0 else 0.0
        y = joy.get_axis(1) if joy.get_numaxes() > 1 else 0.0
        d = (0, 0)
        if abs(y) > 0.6 and abs(y) >= abs(x):
            d = (0, 1 if y > 0 else -1)
        elif abs(x) > 0.6:
            d = (1 if x > 0 else -1, 0)
        if d == (0, 0):
            self._nav_dir = d
            return []
        if d != self._nav_dir:
            self._nav_dir = d
            self._nav_timer = self.NAV_REPEAT_DELAY
        else:
            self._nav_timer -= dt
            if self._nav_timer > 0:
                return []
            self._nav_timer = self.NAV_REPEAT_RATE
        key = {(0, -1): pygame.K_UP, (0, 1): pygame.K_DOWN, (-1, 0): pygame.K_LEFT, (1, 0): pygame.K_RIGHT}[d]
        return [_key(key)]


def _key(key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0, from_joystick=True)
