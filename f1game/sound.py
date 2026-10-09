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
CHANNELS = 2
CHUNK_SECONDS = 0.045
MAX_CHUNK_SECONDS = 0.16
TABLE_SIZE = 2048
NOISE_SIZE = 8192
SINE_SIZE = 1024
HARMONICS = 44
CYLINDERS = 6
IDLE_RPM = 4000.0
MAX_RPM = 15000.0
VOLUMES: dict[str, tuple[str, float]] = {"off": ("Aus", 0.0), "low": ("Leise", 0.35), "normal": ("Normal", 0.7),
                                         "high": ("Laut", 1.0)}


def _cycle_table(seed: int, ring: float, decay: float, drive: float, jitter: float, harmonics: int,
                 tilt: float) -> list[float]:
    """One full 4-stroke cycle (two crank turns) of a V6: six exhaust pulses, band-limited so it
    never aliases when played back at high revs."""
    rng = random.Random(seed)
    starts = [(j + rng.uniform(-0.015, 0.015)) / CYLINDERS for j in range(CYLINDERS)]
    amps = [1.0 + rng.uniform(-jitter, jitter) for _ in range(CYLINDERS)]
    n = TABLE_SIZE
    raw = []
    for k in range(n):
        x = k / n
        v = 0.0
        for s, a in zip(starts, amps):
            u = ((x - s) % 1.0) * CYLINDERS
            v += a * math.exp(-u * decay) * (math.sin(math.tau * ring * u) + 0.6 * math.sin(math.pi * min(u, 1.0)))
        raw.append(math.tanh(v * drive))
    cos_t = [math.cos(math.tau * k / n) for k in range(n)]
    sin_t = [math.sin(math.tau * k / n) for k in range(n)]
    coeffs = []
    for h in range(1, harmonics + 1):
        re = im = 0.0
        for k in range(n):
            idx = (h * k) % n
            re += raw[k] * cos_t[idx]
            im -= raw[k] * sin_t[idx]
        fade = 0.5 + 0.5 * math.cos(math.pi * h / (harmonics + 1))
        weight = fade / (1.0 + tilt * h / CYLINDERS)
        coeffs.append((h, re * weight, im * weight))
    table = []
    for k in range(n):
        v = 0.0
        for h, re, im in coeffs:
            idx = (h * k) % n
            v += re * cos_t[idx] - im * sin_t[idx]
        table.append(v)
    peak = max(abs(v) for v in table) or 1.0
    return [v / peak for v in table]


def _pulse_envelope() -> list[float]:
    starts = [j / CYLINDERS for j in range(CYLINDERS)]
    env = []
    for k in range(TABLE_SIZE):
        x = k / TABLE_SIZE
        env.append(sum(math.exp(-((x - s) % 1.0) * CYLINDERS * 4.5) for s in starts))
    peak = max(env)
    return [v / peak for v in env]


class EngineVoice:
    """Streams a synthesised engine in short chunks. Two wavetables (on-load and overrun) are
    cross-faded by throttle, combustion noise is gated by the firing pulses, a low-pass opens up
    with load, and a turbo whistle plus straight-cut gear whine sit on top."""

    def __init__(self, system: "SoundSystem", channel: int, lite: bool = False) -> None:
        self.sys = system
        self.ch = pygame.mixer.Channel(channel)
        self.lite = lite
        self.phase = 0.0
        self.freq = IDLE_RPM / 120.0
        self.amp = 0.0
        self.load = 0.0
        self.lp = 0.0
        self.turbo_phase = 0.0
        self.whine_phase = 0.0
        self.noise_pos = random.randrange(NOISE_SIZE)
        self.chunk_s = CHUNK_SECONDS
        self.pan = 0.0

    def feed(self, rpm: float, load: float, amp: float, bright: float = 1.0, turbo: float = 0.0,
             whine: float = 0.0, pan: float = 0.0, frame_dt: float = 0.016) -> None:
        if amp <= 0.001 and self.amp <= 0.001:
            if self.ch.get_busy():
                self.ch.stop()
            self.amp = 0.0
            return
        # chunks last at least ~2 frames, so a slow frame (3D, loading, GC) doesn't leave a gap (crackle)
        self.chunk_s = max(CHUNK_SECONDS, min(MAX_CHUNK_SECONDS, frame_dt * 2.2))
        params = (rpm, load, min(0.9, max(0.0, amp)), bright, turbo, whine)
        if not self.ch.get_busy():
            self.ch.play(self._chunk(*params))
        if self.ch.get_queue() is None:
            self.ch.queue(self._chunk(*params))
        self.pan += (pan - self.pan) * 0.3        # no hard jumps between left and right
        self.ch.set_volume(min(1.0, 1.0 - self.pan), min(1.0, 1.0 + self.pan))

    def _chunk(self, rpm: float, load: float, amp: float, bright: float, turbo: float,
               whine: float) -> pygame.mixer.Sound:
        s = self.sys
        rate = s.rate
        n = int(rate * self.chunk_s)
        tl, to, env, noise, sine = s.table_load, s.table_off, s.envelope, s.noise, s.sine
        mask, nmask, smask = TABLE_SIZE - 1, NOISE_SIZE - 1, SINE_SIZE - 1
        freq = rpm / 120.0
        inc0 = self.freq * TABLE_SIZE / rate
        inc1 = freq * TABLE_SIZE / rate
        d_inc = (inc1 - inc0) / n
        sc0, sc1 = self.amp * 21000.0, amp * 21000.0
        d_sc = (sc1 - sc0) / n
        ld = self.load
        d_ld = (load - ld) / n
        rpm_frac = max(0.0, min(1.0, (rpm - IDLE_RPM) / (MAX_RPM - IDLE_RPM)))
        grit = (0.06 + 0.22 * load * (0.3 + 0.7 * rpm_frac)) * bright
        fc = (900.0 + 5200.0 * (0.25 + 0.75 * load) * (0.45 + 0.55 * rpm_frac)) * bright
        cut = 1.0 - math.exp(-math.tau * fc / rate)
        phase, inc, sc, lp = self.phase, inc0, sc0, self.lp
        npos = self.noise_pos
        mono = array("h", bytes(2 * n))
        if self.lite:
            for k in range(n):
                i = int(phase)
                fr = phase - i
                i &= mask
                j = (i + 1) & mask
                a = to[i]
                x = a + (to[j] - a) * fr
                b = tl[i]
                x += (b + (tl[j] - b) * fr - x) * ld
                x += noise[(npos + k) & nmask] * env[i] * grit
                lp += (x - lp) * cut
                mono[k] = int(lp * sc)
                phase += inc
                inc += d_inc
                sc += d_sc
                ld += d_ld
        else:
            tp, wp = self.turbo_phase, self.whine_phase
            t_inc = (2300.0 + 3900.0 * turbo) * SINE_SIZE / rate
            t_amp = 0.06 * turbo * turbo
            w_amp = whine
            w_ratio = 14.0 * SINE_SIZE / TABLE_SIZE
            for k in range(n):
                i = int(phase)
                fr = phase - i
                i &= mask
                j = (i + 1) & mask
                a = to[i]
                x = a + (to[j] - a) * fr
                b = tl[i]
                x += (b + (tl[j] - b) * fr - x) * ld
                x += noise[(npos + k) & nmask] * env[i] * grit
                lp += (x - lp) * cut
                tp += t_inc
                wp += inc * w_ratio
                v = lp + sine[int(tp) & smask] * t_amp + sine[int(wp) & smask] * w_amp
                mono[k] = int(v * sc)
                phase += inc
                inc += d_inc
                sc += d_sc
                ld += d_ld
            self.turbo_phase = tp % SINE_SIZE
            self.whine_phase = wp % SINE_SIZE
        self.phase = phase % TABLE_SIZE
        self.lp = lp
        self.noise_pos = (npos + n) & nmask
        self.freq = freq
        self.amp = amp
        self.load = load
        return s.make_sound(mono)

    def stop(self) -> None:
        self.ch.stop()
        self.amp = 0.0


def engine_rpm(car) -> float:
    if car.speed_fwd > 3:
        frac = car.rpm_fraction
    else:
        frac = 0.08 + 0.6 * car.throttle
    return IDLE_RPM + (MAX_RPM - IDLE_RPM) * frac


def engine_pitch(car) -> float:
    return engine_rpm(car) / 40.0


class SoundSystem:

    HEAR_RANGE: float = 650.0
    SOUND_SPEED: float = 1800.0

    def __init__(self, volume_key: str = "normal") -> None:
        self.enabled = False
        self.volume = VOLUMES.get(volume_key, VOLUMES["normal"])[1]
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, CHANNELS, 1024)
            freq, _, channels = pygame.mixer.get_init()
        except (pygame.error, TypeError):
            return
        self.rate = freq
        self.channels = channels
        pygame.mixer.set_num_channels(14)
        self.skid_ch = pygame.mixer.Channel(1)
        self.fx_ch = pygame.mixer.Channel(2)
        self.beep_ch = pygame.mixer.Channel(3)
        self.ui_ch = pygame.mixer.Channel(5)
        self.pop_ch = pygame.mixer.Channel(7)
        self.wind_ch = pygame.mixer.Channel(8)
        self.gravel_ch = pygame.mixer.Channel(9)
        self.shift_ch = pygame.mixer.Channel(10)
        self.fx2_ch = pygame.mixer.Channel(11)

        self.table_load = _cycle_table(7, ring=2.7, decay=2.3, drive=2.2, jitter=0.10, harmonics=HARMONICS, tilt=0.18)
        self.table_off = _cycle_table(11, ring=1.5, decay=3.4, drive=1.1, jitter=0.38, harmonics=26, tilt=0.55)
        self.envelope = _pulse_envelope()
        rng = random.Random(3)
        self.noise = [rng.uniform(-1.0, 1.0) for _ in range(NOISE_SIZE)]
        self.sine = [math.sin(math.tau * k / SINE_SIZE) for k in range(SINE_SIZE)]

        self.engine = EngineVoice(self, 0)
        self.others = [EngineVoice(self, 4, lite=True), EngineVoice(self, 6, lite=True)]

        self.skid = self._sound(self._squeal(0.7), loop_fade=True)
        self.wind = self._sound(self._noise(0.8, smooth=0.82, gain=2.6), loop_fade=True)
        self.gravel = self._sound(self._gravel(0.7), loop_fade=True)
        self.crash_heavy = [self._sound(self._crash(seed, heavy=True)) for seed in range(3)]
        self.crash_light = [self._sound(self._crash(seed + 10, heavy=False)) for seed in range(3)]
        self.pops = [self._sound(self._pop(seed)) for seed in range(5)]
        self.shift = self._sound(self._shift_clack())
        self.beep = self._sound(self._tone(660.0, 0.2, attack=0.004))
        self.go = self._sound(self._sweep(520.0, 1040.0, 0.35))
        self.click = self._sound(self._blip(1500.0, 0.03))
        self.confirm = self._sound(self._blip(880.0, 0.045) + self._blip(1320.0, 0.07))
        self.back = self._sound(self._blip(990.0, 0.04) + self._blip(660.0, 0.06))
        self.fanfare = self._sound(self._blip(784.0, 0.11) + self._blip(988.0, 0.11) + self._blip(1175.0, 0.11)
                                   + self._blip(1568.0, 0.32))

        self._last_gear = "N"
        self._cut_until = 0
        self._last_impulse = 0.0
        self._last_lights = 0
        self._focus_id = 0
        self._load = 0.0
        self._boost = 0.0
        self._last_throttle = 0.0
        self._last_ticks = pygame.time.get_ticks()
        self._pop_cooldown = 0.0
        self._voice_cars: list[int | None] = [None] * len(self.others)
        self._levels: dict[int, float] = {}
        self._frame_dt = 0.016
        self.enabled = True

    # ------------------------------------------------------------------ synthesis helpers

    def make_sound(self, mono: array) -> pygame.mixer.Sound:
        if self.channels == 1:
            return pygame.mixer.Sound(buffer=mono.tobytes())
        data = array("h", bytes(2 * len(mono) * self.channels))
        for c in range(self.channels):
            data[c::self.channels] = mono
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _sound(self, samples: list[float], loop_fade: bool = False) -> pygame.mixer.Sound:
        if loop_fade:
            n = len(samples) // 8
            for k in range(n):
                w = k / n
                samples[k] = samples[k] * w + samples[-n + k] * (1 - w)
            samples = samples[:-n]
        return self.make_sound(array("h", (int(max(-1.0, min(1.0, v)) * 30000) for v in samples)))

    def _noise(self, seconds: float, smooth: float, gain: float = 1.8) -> list[float]:
        out, y = [], 0.0
        for _ in range(int(self.rate * seconds)):
            y += (random.uniform(-1.0, 1.0) - y) * (1.0 - smooth)
            out.append(y * gain)
        return out

    def _squeal(self, seconds: float) -> list[float]:
        out = []
        noise = self._noise(seconds, 0.35, 1.0)
        partials = [(1.0, 1.0), (1.51, 0.45), (2.03, 0.3), (2.98, 0.12)]
        for k, nv in enumerate(noise):
            t = k / self.rate
            base = 1050.0 + 60.0 * math.sin(math.tau * 5.3 * t) + 25.0 * math.sin(math.tau * 13.1 * t)
            tone = sum(a * math.sin(math.tau * base * m * t) for m, a in partials)
            wobble = 0.75 + 0.25 * math.sin(math.tau * 7.7 * t)
            out.append(0.32 * tone * wobble + 0.35 * nv)
        return out

    def _gravel(self, seconds: float) -> list[float]:
        rumble = self._noise(seconds, 0.93, 6.0)
        hiss = self._noise(seconds, 0.2, 0.5)
        out = []
        crack = 0.0
        for k in range(len(rumble)):
            if random.random() < 0.004:
                crack = random.uniform(0.4, 0.9)
            crack *= 0.93
            out.append(rumble[k] * 0.8 + hiss[k] * (0.15 + crack))
        return out

    def _crash(self, seed: int, heavy: bool) -> list[float]:
        rng = random.Random(seed)
        seconds = 0.9 if heavy else 0.28
        noise = self._noise(seconds, 0.25 if heavy else 0.1, 1.0)
        metal = [(rng.uniform(420, 560), 0.35, 7.0), (rng.uniform(1100, 1300), 0.25, 11.0),
                 (rng.uniform(1750, 1950), 0.18, 15.0), (rng.uniform(2500, 2800), 0.12, 22.0)]
        out = []
        for k, nv in enumerate(noise):
            t = k / self.rate
            thump = math.sin(math.tau * (75.0 - 35.0 * t) * t) * math.exp(-t * (9.0 if heavy else 30.0))
            crunch = nv * math.exp(-t * (7.0 if heavy else 26.0))
            ring = sum(a * math.sin(math.tau * f * t) * math.exp(-t * d) for f, a, d in metal)
            scrape = nv * 0.25 * math.exp(-t * 3.0) if heavy else 0.0
            v = (0.9 * thump + 0.75 * crunch + (0.6 if heavy else 0.35) * ring + scrape)
            out.append(math.tanh(v * 1.4))
        return out

    def _pop(self, seed: int) -> list[float]:
        rng = random.Random(seed + 100)
        seconds = rng.uniform(0.05, 0.09)
        noise = self._noise(seconds, rng.uniform(0.3, 0.6), 1.0)
        body = rng.uniform(90.0, 160.0)
        out = []
        for k, nv in enumerate(noise):
            t = k / self.rate
            env = math.exp(-t * rng.uniform(45.0, 70.0))
            out.append(math.tanh((1.3 * nv + 0.9 * math.sin(math.tau * body * t)) * env * 2.0))
        return out

    def _shift_clack(self) -> list[float]:
        noise = self._noise(0.06, 0.15, 1.0)
        out = []
        for k, nv in enumerate(noise):
            t = k / self.rate
            out.append((0.6 * nv + 0.5 * math.sin(math.tau * 180.0 * t)) * math.exp(-t * 60.0))
        return out

    def _tone(self, freq: float, seconds: float, attack: float = 0.002) -> list[float]:
        n = int(self.rate * seconds)
        out = []
        for k in range(n):
            t = k / self.rate
            env = min(1.0, t / attack) * min(1.0, (n - k) / (self.rate * 0.03))
            out.append(env * (0.45 * math.sin(math.tau * freq * t) + 0.12 * math.sin(math.tau * 2 * freq * t)))
        return out

    def _sweep(self, f0: float, f1: float, seconds: float) -> list[float]:
        n = int(self.rate * seconds)
        out, ph = [], 0.0
        for k in range(n):
            f = f0 + (f1 - f0) * k / n
            ph += math.tau * f / self.rate
            env = min(1.0, k / (self.rate * 0.005)) * (1.0 - k / n) ** 1.5
            out.append(0.5 * env * math.sin(ph))
        return out

    def _blip(self, freq: float, seconds: float) -> list[float]:
        n = int(self.rate * seconds)
        out = []
        for k in range(n):
            t = k / self.rate
            env = min(1.0, t / 0.002) * math.exp(-t * 4.0 / seconds)
            out.append(0.42 * env * (math.sin(math.tau * freq * t) + 0.25 * math.sin(math.tau * 3 * freq * t)))
        return out

    # ------------------------------------------------------------------ control

    def set_volume(self, volume_key: str) -> None:
        self.volume = VOLUMES.get(volume_key, VOLUMES["normal"])[1]
        if self.volume <= 0:
            self.stop()

    def stop(self) -> None:
        if self.enabled:
            self.engine.stop()
            for v in self.others:
                v.stop()
            for ch in (self.skid_ch, self.fx_ch, self.fx2_ch, self.beep_ch, self.pop_ch, self.wind_ch,
                       self.gravel_ch, self.shift_ch):
                ch.stop()

    def ui(self, kind: str = "click") -> None:
        if self.enabled and self.volume > 0:
            snd = {"confirm": self.confirm, "back": self.back, "fanfare": self.fanfare}.get(kind, self.click)
            self.ui_ch.play(snd)
            self.ui_ch.set_volume((0.5 if kind == "fanfare" else 0.3) * self.volume)

    def _loop(self, ch: pygame.mixer.Channel, snd: pygame.mixer.Sound, level: float, attack: float = 12.0,
              release: float = 6.0) -> None:
        """Looping noise (skid, gravel, wind) that fades in and out instead of switching on and off (clicks)."""
        key = id(ch)
        cur = self._levels.get(key, 0.0)
        rate = attack if level > cur else release
        cur += (level - cur) * min(1.0, rate * self._frame_dt)
        self._levels[key] = cur
        if cur > 0.008:
            if not ch.get_busy():
                ch.play(snd, loops=-1)
            ch.set_volume(min(1.0, cur))
        elif ch.get_busy():
            ch.stop()
            self._levels[key] = 0.0

    def _other_cars(self, session: "Session", focus, vol: float) -> None:
        near = []
        for c in session.cars:
            if c is focus or c.dnf or c.in_pit:
                continue
            d = c.pos.distance_to(focus.pos)
            if d < self.HEAR_RANGE:
                near.append((d, id(c), c))
        near.sort()
        # each voice keeps its car while it stays in range: re-sorting by distance every frame made the
        # voices jump between cars (sudden pitch changes)
        wanted = [c for _, _, c in near[:len(self.others)]]
        by_id = {id(c): (d, c) for d, _, c in near}
        for k in range(len(self.others)):
            cid = self._voice_cars[k]
            if cid is not None and (cid not in by_id or by_id[cid][1] not in wanted):
                self._voice_cars[k] = None
        for c in wanted:
            if id(c) not in self._voice_cars and None in self._voice_cars:
                self._voice_cars[self._voice_cars.index(None)] = id(c)
        for k, voice in enumerate(self.others):
            cid = self._voice_cars[k]
            if cid is None:
                voice.feed(0.0, 0.0, 0.0, frame_dt=self._frame_dt)
                continue
            d, car = by_id[cid]
            rel = car.pos - focus.pos
            direction = rel / max(d, 1.0)
            v_away = (car.vel - focus.vel).dot(direction)
            doppler = self.SOUND_SPEED / max(300.0, self.SOUND_SPEED + v_away)
            loud = (1.0 - d / self.HEAR_RANGE) ** 2
            pan = max(-0.85, min(0.85, direction.dot(focus.right)))
            bright = 0.35 + 0.65 * (1.0 - d / self.HEAR_RANGE)
            voice.feed(engine_rpm(car) * doppler, car.throttle, (0.14 + 0.16 * car.throttle) * loud * vol,
                       bright=bright, pan=pan, frame_dt=self._frame_dt)

    def update(self, session: "Session") -> None:
        if not self.enabled:
            return
        if self.volume <= 0 or session.paused or session.overview or session.finished:
            self.stop()
            return
        now = pygame.time.get_ticks()
        dt = max(0.001, min(0.1, (now - self._last_ticks) / 1000.0))
        self._last_ticks = now
        self._frame_dt = dt
        car = session.focus
        if id(car) != self._focus_id:
            self._focus_id = id(car)
            self._voice_cars = [None] * len(self.others)
            self._last_impulse = car.wall_impulse + car.car_impulse
            self._last_gear = car.gear
        fast_forward = session.time_scale > 1.0
        mute = 0.0 if fast_forward else 1.0
        vol = self.volume
        speed_frac = max(0.0, min(1.0, car.speed_fwd / max(1.0, car.top_speed)))

        if car.dnf:
            self.engine.feed(0.0, 0.0, 0.0)
        else:
            rpm = engine_rpm(car)
            rpm_frac = (rpm - IDLE_RPM) / (MAX_RPM - IDLE_RPM)
            target_load = car.throttle * (0.0 if car.brake > 0.3 else 1.0)
            rate = 14.0 if target_load > self._load else 7.0
            self._load += (target_load - self._load) * min(1.0, rate * dt)
            spool = car.throttle * max(0.0, (rpm_frac - 0.25) / 0.75)
            self._boost += (spool - self._boost) * min(1.0, (2.2 if spool > self._boost else 3.5) * dt)
            amp = (0.34 + 0.30 * self._load) * (0.6 if car.in_pit else 1.0)
            gear = car.gear
            if gear.isdigit() and self._last_gear.isdigit() and gear != self._last_gear:
                up = int(gear) > int(self._last_gear)
                if up:
                    self._cut_until = now + 55
                if not fast_forward and (car.throttle > 0.3 or not up):
                    self.shift_ch.play(self.shift)
                    self.shift_ch.set_volume((0.35 if up else 0.22) * vol)
            if now < self._cut_until:
                amp *= 0.35
            self._last_gear = gear
            top = car.top_speed * car.sf.rev_limit
            if car.throttle > 0.5 and car.speed_fwd > top - 3:
                amp *= 0.55 + 0.45 * (int(session.time * 28) % 2)
                rpm *= 0.985 + 0.015 * (int(session.time * 28) % 2)
            if car.in_pit:
                amp *= 0.75 + 0.25 * (int(session.time * 14) % 2)
            whine = 0.02 + 0.04 * speed_frac * (1.0 - 0.6 * self._load)
            self.engine.feed(rpm, self._load, amp * vol * mute, bright=1.0, turbo=self._boost,
                             whine=whine * speed_frac, frame_dt=dt)
            self._pop_cooldown -= dt
            lifted = self._last_throttle > 0.6 and car.throttle < 0.2
            overrun = car.throttle < 0.15 and rpm_frac > 0.5 and car.speed_fwd > 60
            if not fast_forward and self._pop_cooldown <= 0 and overrun and \
                    (lifted or random.random() < 1.5 * dt * rpm_frac):
                self.pop_ch.play(random.choice(self.pops))
                self.pop_ch.set_volume(random.uniform(0.25, 0.55) * vol * (0.6 + 0.4 * rpm_frac))
                self._pop_cooldown = random.uniform(0.18, 0.6)
            self._last_throttle = car.throttle

        self._other_cars(session, car, vol * mute)

        self._loop(self.wind_ch, self.wind, 0.0 if fast_forward else 0.32 * speed_frac ** 2 * vol)
        on_grass = car.on_grass and car.speed_fwd > 20 and not car.in_pit
        self._loop(self.gravel_ch, self.gravel, 0.0 if fast_forward or not on_grass
                   else (0.25 + 0.55 * speed_frac) * vol)

        slip = abs(car.vel.dot(car.right)) if not car.in_pit else 0.0
        lock = car.brake > 0.85 and car.speed_fwd > 120 and car.sliding
        skid = 0.0 if fast_forward or car.on_grass else max(0.0, min(1.0, (slip - 35.0) / 140.0))
        skid = max(skid, 0.45 if lock and not fast_forward else 0.0)
        self._loop(self.skid_ch, self.skid, skid * 0.45 * vol)

        impulse = car.wall_impulse + car.car_impulse
        hit = impulse - self._last_impulse
        self._last_impulse = impulse
        if hit > 25.0 and not fast_forward:
            heavy = hit > 140.0
            ch = self.fx_ch if heavy or not self.fx_ch.get_busy() else self.fx2_ch
            ch.play(random.choice(self.crash_heavy if heavy else self.crash_light))
            ch.set_volume(min(1.0, 0.25 + hit / 450.0) * vol)

        lights = getattr(session, "lights_on", 0)
        if lights > self._last_lights:
            self.beep_ch.play(self.beep)
            self.beep_ch.set_volume(0.55 * vol)
        elif lights == 0 and self._last_lights == 5:
            self.beep_ch.play(self.go)
            self.beep_ch.set_volume(0.5 * vol)
        self._last_lights = lights
