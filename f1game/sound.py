# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from array import array
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from .sessions import Session

RATE = 22050
CHUNK_SECONDS = 0.04
TABLE_SIZE = 1024
VOLUMES: dict[str, tuple[str, float]] = {"off": ("Aus", 0.0), "low": ("Leise", 0.35), "normal": ("Normal", 0.75)}


def _engine_table() -> list[float]:
    table = []
    for k in range(TABLE_SIZE):
        x = k / TABLE_SIZE * math.tau
        v = (0.35 * math.sin(x) + 1.0 * math.sin(2 * x) + 0.55 * math.sin(4 * x + 0.4)
             + 0.35 * math.sin(6 * x + 1.1) + 0.22 * math.sin(8 * x + 0.3) + 0.12 * math.sin(12 * x))
        table.append(math.tanh(v * 0.9))
    peak = max(abs(v) for v in table)
    return [v / peak for v in table]


class EngineVoice:

    def __init__(self, system: "SoundSystem", channel: int) -> None:
        self.sys = system
        self.ch = pygame.mixer.Channel(channel)
        self.phase = 0.0
        self.freq = 70.0
        self.amp = 0.0

    def feed(self, target_freq: float, amp: float) -> None:
        if amp <= 0.001:
            if self.ch.get_busy():
                self.ch.stop()
            self.amp = 0.0
            return
        if not self.ch.get_busy():
            self.ch.play(self._chunk(target_freq, amp))
        if self.ch.get_queue() is None:
            self.ch.queue(self._chunk(target_freq, amp))

    def _chunk(self, target_freq: float, amp: float) -> pygame.mixer.Sound:
        s = self.sys
        n = int(s.rate * CHUNK_SECONDS)
        table, mask = s.table, TABLE_SIZE - 1
        inc0 = self.freq * 0.5 * TABLE_SIZE / s.rate
        inc1 = target_freq * 0.5 * TABLE_SIZE / s.rate
        d_inc = (inc1 - inc0) / n
        a0, a1 = self.amp * 30000, amp * 30000
        d_amp = (a1 - a0) / n
        phase, inc, scale = self.phase, inc0, a0
        ch = s.channels
        data = array("h", bytes(2 * n * ch))
        for k in range(n):
            i = int(phase)
            a = table[i & mask]
            v = int((a + (table[(i + 1) & mask] - a) * (phase - i)) * scale)
            if ch == 1:
                data[k] = v
            else:
                base = k * ch
                for c in range(ch):
                    data[base + c] = v
            phase += inc
            inc += d_inc
            scale += d_amp
        self.phase = phase % TABLE_SIZE
        self.freq = target_freq
        self.amp = amp
        return pygame.mixer.Sound(buffer=data.tobytes())

    def stop(self) -> None:
        self.ch.stop()
        self.amp = 0.0


def engine_pitch(car) -> float:
    rpm = car.rpm_fraction if car.speed_fwd > 3 else 0.25 + 0.5 * car.throttle
    return 70.0 + 300.0 * rpm


class SoundSystem:

    def __init__(self, volume_key: str = "normal") -> None:
        self.enabled = False
        self.volume = VOLUMES.get(volume_key, VOLUMES["normal"])[1]
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            freq, _, channels = pygame.mixer.get_init()
        except (pygame.error, TypeError):
            return
        self.rate = freq
        self.channels = channels
        pygame.mixer.set_num_channels(8)
        self.skid_ch = pygame.mixer.Channel(1)
        self.fx_ch = pygame.mixer.Channel(2)
        self.beep_ch = pygame.mixer.Channel(3)
        self.ui_ch = pygame.mixer.Channel(5)
        self.table = _engine_table()
        self.engine = EngineVoice(self, 0)
        self.other = EngineVoice(self, 4)
        self.skid = self._sound(self._noise(0.6, smooth=0.55), loop_fade=True)
        self.crash = self._sound(self._crash())
        self.beep = self._sound(self._tone(660.0, 0.18))
        self.click = self._sound(self._tone(1250.0, 0.025))
        self.confirm = self._sound(self._tone(880.0, 0.05) + self._tone(1320.0, 0.07))
        self._last_gear = "N"
        self._cut_until = 0
        self._last_impulse = 0.0
        self._last_lights = 0
        self._focus_id = 0
        self.enabled = True

    HEAR_RANGE: float = 600.0
    SOUND_SPEED: float = 1800.0

    def _other_car(self, session: "Session", focus, vol: float) -> None:
        best, best_d = None, self.HEAR_RANGE
        for c in session.cars:
            if c is focus or c.dnf or c.in_pit:
                continue
            d = c.pos.distance_to(focus.pos)
            if d < best_d:
                best, best_d = c, d
        if best is None:
            self.other.feed(0.0, 0.0)
            return
        rel = best.pos - focus.pos
        direction = rel / max(best_d, 1.0)
        v_away = (best.vel - focus.vel).dot(direction)
        doppler = self.SOUND_SPEED / max(300.0, self.SOUND_SPEED + v_away)
        loud = (1.0 - best_d / self.HEAR_RANGE) ** 2
        self.other.feed(engine_pitch(best) * doppler * 1.04, (0.12 + 0.12 * best.throttle) * loud * vol)

    def _sound(self, samples: list[float], loop_fade: bool = False) -> pygame.mixer.Sound:
        if loop_fade:
            n = len(samples) // 8
            for k in range(n):
                w = k / n
                samples[k] = samples[k] * w + samples[-n + k] * (1 - w)
            samples = samples[:-n]
        data = array("h", (int(max(-1.0, min(1.0, v)) * 30000) for v in samples))
        if self.channels > 1:
            data = array("h", (v for v in data for _ in range(self.channels)))
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _noise(self, seconds: float, smooth: float) -> list[float]:
        out, y = [], 0.0
        for _ in range(int(self.rate * seconds)):
            y += (random.uniform(-1.0, 1.0) - y) * (1.0 - smooth)
            out.append(y * 1.8)
        return out

    def _crash(self) -> list[float]:
        out = []
        noise = self._noise(0.45, 0.3)
        for k, nv in enumerate(noise):
            t = k / self.rate
            env = math.exp(-t * 11.0)
            out.append(env * (0.8 * nv + 0.7 * math.sin(math.tau * 70 * t)))
        return out

    def _tone(self, freq: float, seconds: float) -> list[float]:
        n = int(self.rate * seconds)
        return [0.5 * math.sin(math.tau * freq * k / self.rate) * min(1.0, (n - k) / (self.rate * 0.02))
                for k in range(n)]

    def set_volume(self, volume_key: str) -> None:
        self.volume = VOLUMES.get(volume_key, VOLUMES["normal"])[1]
        if self.volume <= 0:
            self.stop()

    def stop(self) -> None:
        if self.enabled:
            self.engine.stop()
            self.other.stop()
            for ch in (self.skid_ch, self.fx_ch, self.beep_ch):
                ch.stop()

    def ui(self, kind: str = "click") -> None:
        if self.enabled and self.volume > 0:
            self.ui_ch.play(self.confirm if kind == "confirm" else self.click)
            self.ui_ch.set_volume(0.35 * self.volume)

    def update(self, session: "Session") -> None:
        if not self.enabled:
            return
        if self.volume <= 0 or session.paused or session.overview or session.finished:
            self.stop()
            return
        car = session.focus
        if id(car) != self._focus_id:
            self._focus_id = id(car)
            self._last_impulse = car.wall_impulse + car.car_impulse
        fast_forward = session.time_scale > 1.0
        vol = self.volume

        if car.dnf:
            target, amp = 0.0, 0.0
        else:
            target = engine_pitch(car)
            amp = (0.20 + 0.22 * car.throttle) * (0.6 if car.in_pit else 1.0)
            gear = car.gear
            now = pygame.time.get_ticks()
            if gear.isdigit() and self._last_gear.isdigit() and int(gear) > int(self._last_gear):
                self._cut_until = now + 70
            if now < self._cut_until:
                amp *= 0.3
            self._last_gear = gear
            top = car.top_speed * car.sf.rev_limit
            if car.throttle > 0.5 and car.speed_fwd > top - 3:
                amp *= 0.55 + 0.45 * (int(session.time * 25) % 2)
        self.engine.feed(target, amp * vol * (0.0 if fast_forward else 1.0))

        self._other_car(session, car, vol * (0.0 if fast_forward else 1.0))

        slip = abs(car.vel.dot(car.right)) if not car.in_pit else 0.0
        skid = 0.0 if fast_forward or car.on_grass else max(0.0, min(1.0, (slip - 35.0) / 140.0))
        if skid > 0.02:
            if not self.skid_ch.get_busy():
                self.skid_ch.play(self.skid, loops=-1)
            self.skid_ch.set_volume(skid * 0.5 * vol)
        elif self.skid_ch.get_busy():
            self.skid_ch.stop()

        impulse = car.wall_impulse + car.car_impulse
        hit = impulse - self._last_impulse
        self._last_impulse = impulse
        if hit > 60.0 and not fast_forward:
            self.fx_ch.play(self.crash)
            self.fx_ch.set_volume(min(1.0, hit / 450.0) * vol)

        lights = getattr(session, "lights_on", 0)
        if lights > self._last_lights:
            self.beep_ch.play(self.beep)
            self.beep_ch.set_volume(0.6 * vol)
        self._last_lights = lights
