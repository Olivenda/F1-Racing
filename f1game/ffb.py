# Copyright Olivenda (Oliver Petz) 2026
"""Force feedback for wheelbases through SDL's haptic API.

pygame has no force-feedback functions, but it ships SDL2, which does. We load pygame's own SDL2 library with
ctypes (the same instance pygame already initialised), find the haptic device behind a pygame joystick and run
four effects on it:

constant  the steering force, updated every frame (self-aligning torque, kerbs, impacts)
spring    a centring spring - only noticeable when the car is slow or stationary
damper    a little weight so the wheel doesn't oscillate
sine      road texture / kerb / gravel vibration (magnitude updated every frame)

Everything fails soft: without SDL haptic support (gamepads, macOS without drivers, ...) available is False and
the game falls back to SDL rumble.
"""

from __future__ import annotations

import ctypes
import os
import sys

import pygame

SDL_INIT_HAPTIC = 0x00001000
SDL_HAPTIC_CONSTANT = 1 << 0
SDL_HAPTIC_SINE = 1 << 1
SDL_HAPTIC_SPRING = 1 << 7
SDL_HAPTIC_DAMPER = 1 << 8
SDL_HAPTIC_GAIN = 1 << 12
SDL_HAPTIC_AUTOCENTER = 1 << 13
SDL_HAPTIC_CARTESIAN = 1
SDL_HAPTIC_INFINITY = 0xFFFFFFFF

Uint8, Uint16, Sint16, Uint32, Sint32 = ctypes.c_uint8, ctypes.c_uint16, ctypes.c_int16, ctypes.c_uint32, \
    ctypes.c_int32


class _Direction(ctypes.Structure):
    _fields_ = [("type", Uint8), ("dir", Sint32 * 3)]


class _Constant(ctypes.Structure):
    _fields_ = [("type", Uint16), ("direction", _Direction), ("length", Uint32), ("delay", Uint16),
                ("button", Uint16), ("interval", Uint16), ("level", Sint16), ("attack_length", Uint16),
                ("attack_level", Uint16), ("fade_length", Uint16), ("fade_level", Uint16)]


class _Periodic(ctypes.Structure):
    _fields_ = [("type", Uint16), ("direction", _Direction), ("length", Uint32), ("delay", Uint16),
                ("button", Uint16), ("interval", Uint16), ("period", Uint16), ("magnitude", Sint16),
                ("offset", Sint16), ("phase", Uint16), ("attack_length", Uint16), ("attack_level", Uint16),
                ("fade_length", Uint16), ("fade_level", Uint16)]


class _Condition(ctypes.Structure):
    _fields_ = [("type", Uint16), ("direction", _Direction), ("length", Uint32), ("delay", Uint16),
                ("button", Uint16), ("interval", Uint16), ("right_sat", Uint16 * 3), ("left_sat", Uint16 * 3),
                ("right_coeff", Sint16 * 3), ("left_coeff", Sint16 * 3), ("deadband", Uint16 * 3),
                ("center", Sint16 * 3)]


class _Effect(ctypes.Union):
    # padding covers the larger members (ramp, custom) we never use
    _fields_ = [("type", Uint16), ("constant", _Constant), ("periodic", _Periodic), ("condition", _Condition),
                ("_pad", ctypes.c_uint8 * 128)]


def _load_sdl() -> ctypes.CDLL | None:
    """pygame's own SDL2 - the very library (and joystick state) pygame is using."""
    base = os.path.dirname(pygame.__file__)
    names = {"win32": ["SDL2.dll"], "darwin": ["libSDL2-2.0.0.dylib", "libSDL2.dylib"]}.get(
        sys.platform, ["libSDL2-2.0.so.0", "libSDL2.so"])
    candidates = [os.path.join(base, n) for n in names]
    libs = os.path.join(os.path.dirname(base), "pygame_ce.libs")
    if os.path.isdir(libs):
        candidates += [os.path.join(libs, f) for f in os.listdir(libs) if f.lower().startswith("libsdl2-")]
    candidates += names
    for path in candidates:
        try:
            return ctypes.CDLL(path)
        except OSError:
            continue
    return None


class ForceFeedback:

    def __init__(self) -> None:
        self.sdl = None
        self.haptic = None
        self.instance_id: int | None = None
        self.features = 0
        self.effects: dict[str, int] = {}
        self.data: dict[str, _Effect] = {}
        self.ok = False
        try:
            sdl = _load_sdl()
            if sdl is None or sdl.SDL_InitSubSystem(SDL_INIT_HAPTIC) != 0:
                return
            sdl.SDL_JoystickFromInstanceID.restype = ctypes.c_void_p
            sdl.SDL_JoystickFromInstanceID.argtypes = [ctypes.c_int32]
            sdl.SDL_JoystickIsHaptic.argtypes = [ctypes.c_void_p]
            sdl.SDL_HapticOpenFromJoystick.restype = ctypes.c_void_p
            sdl.SDL_HapticOpenFromJoystick.argtypes = [ctypes.c_void_p]
            sdl.SDL_HapticClose.argtypes = [ctypes.c_void_p]
            sdl.SDL_HapticQuery.restype = ctypes.c_uint
            sdl.SDL_HapticQuery.argtypes = [ctypes.c_void_p]
            sdl.SDL_HapticNewEffect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Effect)]
            sdl.SDL_HapticUpdateEffect.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(_Effect)]
            sdl.SDL_HapticRunEffect.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32]
            sdl.SDL_HapticStopAll.argtypes = [ctypes.c_void_p]
            sdl.SDL_HapticSetGain.argtypes = [ctypes.c_void_p, ctypes.c_int]
            sdl.SDL_HapticSetAutocenter.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.sdl = sdl
        except (OSError, AttributeError):
            self.sdl = None

    @property
    def available(self) -> bool:
        return self.ok

    # ------------------------------------------------------------------ device
    def attach(self, joystick: "pygame.joystick.JoystickType | None") -> bool:
        """Open the haptic side of this joystick (no-op if it is already open)."""
        if self.sdl is None or joystick is None:
            self.detach()
            return False
        iid = joystick.get_instance_id()
        if iid == self.instance_id and self.haptic:
            return self.ok
        self.detach()
        self.instance_id = iid
        try:
            joy = self.sdl.SDL_JoystickFromInstanceID(iid)
            if not joy or self.sdl.SDL_JoystickIsHaptic(joy) != 1:
                return False
            self.haptic = self.sdl.SDL_HapticOpenFromJoystick(joy)
            if not self.haptic:
                return False
            self.features = self.sdl.SDL_HapticQuery(self.haptic)
            if self.features & SDL_HAPTIC_AUTOCENTER:
                self.sdl.SDL_HapticSetAutocenter(self.haptic, 0)   # we do the centring ourselves
            if self.features & SDL_HAPTIC_GAIN:
                self.sdl.SDL_HapticSetGain(self.haptic, 100)
            if self.features & SDL_HAPTIC_CONSTANT:
                self._create("constant", self._constant(0))
            if self.features & SDL_HAPTIC_SPRING:
                self._create("spring", self._condition(SDL_HAPTIC_SPRING, 0))
            if self.features & SDL_HAPTIC_DAMPER:
                self._create("damper", self._condition(SDL_HAPTIC_DAMPER, 0))
            if self.features & SDL_HAPTIC_SINE:
                self._create("sine", self._sine(0, 60))
            self.ok = "constant" in self.effects
        except (OSError, AttributeError, ValueError):
            self.ok = False
        return self.ok

    def detach(self) -> None:
        if self.sdl is not None and self.haptic:
            try:
                self.sdl.SDL_HapticStopAll(self.haptic)
                self.sdl.SDL_HapticClose(self.haptic)
            except OSError:
                pass
        self.haptic = None
        self.instance_id = None
        self.effects.clear()
        self.data.clear()
        self.ok = False

    # ------------------------------------------------------------------ effects
    @staticmethod
    def _direction() -> _Direction:
        d = _Direction()
        d.type = SDL_HAPTIC_CARTESIAN
        d.dir[0] = 1            # along the steering axis: positive level turns the wheel to the right
        return d

    def _constant(self, level: int) -> _Effect:
        e = _Effect()
        e.constant.type = SDL_HAPTIC_CONSTANT
        e.constant.direction = self._direction()
        e.constant.length = SDL_HAPTIC_INFINITY
        e.constant.level = level
        return e

    def _condition(self, kind: int, coeff: int) -> _Effect:
        e = _Effect()
        c = e.condition
        c.type = kind
        c.direction = self._direction()
        c.length = SDL_HAPTIC_INFINITY
        for k in range(3):
            c.right_sat[k] = c.left_sat[k] = 0xFFFF
            c.right_coeff[k] = c.left_coeff[k] = coeff
        return e

    def _sine(self, magnitude: int, period_ms: int) -> _Effect:
        e = _Effect()
        p = e.periodic
        p.type = SDL_HAPTIC_SINE
        p.direction = self._direction()
        p.length = SDL_HAPTIC_INFINITY
        p.period = max(10, period_ms)
        p.magnitude = magnitude
        return e

    def _create(self, name: str, effect: _Effect) -> None:
        eid = self.sdl.SDL_HapticNewEffect(self.haptic, ctypes.byref(effect))
        if eid >= 0:
            self.sdl.SDL_HapticRunEffect(self.haptic, eid, 1)
            self.effects[name] = eid
            self.data[name] = effect

    def _update(self, name: str) -> None:
        eid = self.effects.get(name)
        if eid is not None:
            self.sdl.SDL_HapticUpdateEffect(self.haptic, eid, ctypes.byref(self.data[name]))

    def set_forces(self, torque: float, spring: float, damper: float, vibration: float, period_ms: int) -> None:
        """torque -1..1 (positive = pulls the wheel right), spring/damper/vibration 0..1."""
        if not self.ok:
            return
        try:
            level = int(max(-1.0, min(1.0, torque)) * 32767)
            c = self.data["constant"].constant
            if abs(c.level - level) > 120:
                c.level = level
                self._update("constant")
            for name, amount in (("spring", spring), ("damper", damper)):
                if name in self.data:
                    coeff = int(max(0.0, min(1.0, amount)) * 32767)
                    cond = self.data[name].condition
                    if abs(cond.right_coeff[0] - coeff) > 300:
                        for k in range(3):
                            cond.right_coeff[k] = cond.left_coeff[k] = coeff
                        self._update(name)
            if "sine" in self.data:
                p = self.data["sine"].periodic
                mag = int(max(0.0, min(1.0, vibration)) * 32767)
                period = max(10, int(period_ms))
                if abs(p.magnitude - mag) > 300 or abs(p.period - period) > 4:
                    p.magnitude, p.period = mag, period
                    self._update("sine")
        except (OSError, KeyError):
            self.ok = False

    def neutral(self) -> None:
        """Menus / pause: a gentle centring spring, no driving forces."""
        self.set_forces(0.0, 0.25, 0.1, 0.0, 60)
