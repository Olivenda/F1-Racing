# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from .pitlane import SPEED_LIMIT
from .settings import CAR_LENGTH, CAR_WIDTH, TOP_SPEED, YELLOW

if TYPE_CHECKING:
    from .car import Car
    from .sessions import RaceSession

SC_SPEED = 0.42
SC_LAPS = 2
GAP_TARGET = 95.0
CATCH_UP = 0.80
FOLLOW_GAIN = 1.6
VSC_SPEED = 0.58
COOLDOWN = 60.0
YELLOW_TIME = 12.0
PUNCTURE_WEAR = 0.88
GIVE_BACK_TIME = 15.0
GRACE = 3.0               # a pass already under way when the neutralisation is called may still be completed
RESTART_LINE_TIME = 25.0  # after the restart: no overtaking until a car has crossed the control line itself
RED_SPEED = 0.30          # red flag: the field slows to this share of top speed and stops in order
RED_STOP_TIME = 6.0       # ...the leader is down to a standstill after this many seconds


def follow_speed(gap: float, ahead_speed: float, top: float) -> float:
    """Under the safety car: the speed that settles a car GAP_TARGET behind the one ahead."""
    target = ahead_speed + FOLLOW_GAIN * (gap - GAP_TARGET)
    return max(top * 0.20, min(top * CATCH_UP, target))


def hold_speed(car: "Car", target: float) -> None:
    """Lift and brake so the car doesn't go faster than target (race control's limit under SC/VSC)."""
    v = car.speed_fwd
    if v > target + 4.0:
        car.throttle = 0.0
        car.brake = max(car.brake, min(1.0, (v - target) / 90.0))
    elif v > target - 15.0:
        car.throttle = min(car.throttle, 0.25)
    car.straight_mode = False


class SafetyCar:

    def __init__(self, session: "RaceSession", s: float) -> None:
        self.track = session.track
        self.s = s % self.track.length
        self.speed = 0.0
        self.pos = Vector2()
        self.heading = 0.0
        self.color = (225, 228, 235)
        self.profile = SimpleNamespace(helmet=(255, 150, 0), name="Safety Car", team="FIA")
        self.short = "SC"
        self.name = "Safety Car"
        self.is_player = False
        self.is_ghost = False
        self.lights_on = True               # light bar: off once it is "in this lap"
        self.pit_u: float | None = None     # driving down the pit lane (after the period)
        self.done = False                   # parked in the pit lane: gone
        self.steer_angle = 0.0
        self.lateral = 0.0
        self._sprite = _road_car_sprite(self.color)
        self._place()

    @property
    def speed_fwd(self) -> float:
        """(the AI's sensors see the safety car like a car)"""
        return self.speed

    def _place(self) -> None:
        t = self.track
        i = int(self.s / t.WAYPOINT_SPACING) % t.n
        self.lateral = t.line_offset[i] if t.line_offset else 0.0
        self.pos, self.heading = t.pose_at(self.s, self.lateral)

    def update(self, h: float, target_speed: float) -> None:
        if self.pit_u is not None:
            self._pit_step(h)
            return
        self.speed += max(-400.0 * h, min(250.0 * h, target_speed - self.speed))
        self.s = (self.s + self.speed * h) % self.track.length
        self._place()

    @property
    def on_track(self) -> bool:
        return self.pit_u is None

    def enter_pit(self) -> None:
        self.pit_u = 0.0
        self.lights_on = False

    def _pit_step(self, h: float) -> None:
        """Down the pit lane at the speed limit, then it stops and leaves the picture."""
        pit = self.track.pit
        if pit is None:
            self.done = True
            return
        stop = pit.length * 0.45
        left = stop - self.pit_u
        target = min(SPEED_LIMIT, max(0.0, left) * 1.2)
        self.speed += max(-450.0 * h, min(250.0 * h, target - self.speed))
        self.pit_u += self.speed * h
        self.pos, self.heading = pit.pose(self.pit_u)
        if left < 4.0 and self.speed < 5.0:
            self.done = True

    def draw(self, surface: pygame.Surface, cam: Vector2, t: float) -> None:
        sp = self.pos - cam
        if not (-60 < sp.x < surface.get_width() + 60 and -60 < sp.y < surface.get_height() + 60):
            return
        img = pygame.transform.rotozoom(self._sprite, -math.degrees(self.heading), 1.0)
        surface.blit(img, img.get_rect(center=(round(sp.x), round(sp.y))))
        if self.lights_on and int(t * 6) % 2 == 0:
            r = Vector2(-math.sin(self.heading), math.cos(self.heading))
            for side in (-1, 1):
                pygame.draw.circle(surface, (255, 160, 0), sp + r * side * 4, 3)


def _road_car_sprite(body: tuple[int, int, int]) -> pygame.Surface:
    """Top-down GT safety car (nose to +x), same footprint as an F1 car sprite."""
    S = 8
    L, W = CAR_LENGTH, CAR_WIDTH
    big = pygame.Surface((int(L * S), int(W * S)), pygame.SRCALPHA)
    w, h = big.get_size()
    pygame.draw.rect(big, (14, 14, 16), (int(w * 0.18), 0, int(w * 0.16), h), border_radius=S * 2)       # tyres
    pygame.draw.rect(big, (14, 14, 16), (int(w * 0.68), 0, int(w * 0.16), h), border_radius=S * 2)
    pygame.draw.rect(big, body, (int(w * 0.04), int(h * 0.08), int(w * 0.92), int(h * 0.84)), border_radius=S * 4)
    pygame.draw.rect(big, (34, 42, 56), (int(w * 0.30), int(h * 0.16), int(w * 0.36), int(h * 0.68)),
                     border_radius=S * 3)                                                                     # glass
    pygame.draw.rect(big, body, (int(w * 0.36), int(h * 0.22), int(w * 0.22), int(h * 0.56)), border_radius=S * 2)
    pygame.draw.rect(big, (255, 150, 0), (int(w * 0.42), int(h * 0.20), int(w * 0.06), int(h * 0.60)))    # light bar
    pygame.draw.rect(big, (255, 140, 0), (int(w * 0.08), int(h * 0.46), int(w * 0.84), int(h * 0.08)))    # stripe
    for y in (0.16, 0.70):
        pygame.draw.rect(big, (240, 240, 226), (int(w * 0.90), int(h * y), int(w * 0.05), int(h * 0.14)))
    return pygame.transform.smoothscale(big, (max(1, int(L)), max(1, int(W))))


class RaceControl:
    def __init__(self, session: "RaceSession", enabled: bool) -> None:
        self.s = session
        self.enabled = enabled
        self.mode: str | None = None
        self.phase = ""
        self.sc: SafetyCar | None = None
        self.until = 0.0
        self.sc_end_lap = 0
        self.cooldown_until = 0.0
        self.yellow: dict[int, float] = {}
        self.yellow_at: dict[int, float] = {}     # where in the sector the incident is (double yellow before it)
        self.cleared: dict[int, float] = {}       # sector -> until when its panels show green after a yellow
        self.green_until = 0.0
        self.periods: list[str] = []
        self._period_start = 0
        self._restart_lap = 0
        self._puncture_timer = 0.0
        self.give_back: dict[tuple, float] = {}
        self._pending: dict[tuple, float] = {}
        self._ref: list = []                      # the order the field has to keep under SC/VSC
        self._rank: dict = {}
        self._line_due: dict = {}                 # restart: car -> lap count it has to complete before passing
        self._line_until = 0.0
        self._order_timer = 0.0
        self._since = 0.0
        self._lead: "Car | None" = None
        self.director = None                      # race director (spectator): may take over the decisions

    @property
    def active(self) -> bool:
        return self.mode is not None

    def sector_of(self, car: "Car") -> int:
        return min(2, int((car.s % self.s.track.length) / self.s.track.length * 3))

    def _leader(self) -> "Car | None":
        order = [c for c in self.s.standings() if not c.session_done and not c.dnf]
        return order[0] if order else None

    def _can_start(self) -> bool:
        s = self.s
        leader = self._leader()
        return (self.enabled and s.race_started and not self.active and s.time >= self.cooldown_until
                and leader is not None and leader.laps_done >= 1 and s.total_laps - leader.laps_done > 2
                and s.winner_time is None)

    def incident(self, car: "Car", severity: str) -> None:
        s = self.s
        sector = self.sector_of(car)
        self.yellow[sector] = s.time + YELLOW_TIME
        self.yellow_at[sector] = car.s % s.track.length
        if not self._can_start():
            return
        if severity == "dnf":
            self._auto_deploy("SC" if random.random() < 0.65 else "VSC", f"{car.short} steht auf der Strecke")
        elif car.damage.total > 0.5 and random.random() < 0.5:
            self._auto_deploy("SC", f"schwerer Unfall von {car.short}")
        elif car.damage.total > 0.25 and random.random() < 0.3:
            self._auto_deploy("VSC", f"Trümmer nach Unfall von {car.short}")

    def _auto_deploy(self, mode: str, reason: str) -> None:
        """Race control's own call - unless a race director decides (or is asked) instead."""
        if self.director is not None and self.director.intercept_deploy(mode, reason):
            return
        self.deploy(mode, reason)

    def deploy(self, mode: str, reason: str) -> None:
        s = self.s
        leader = self._leader()
        if leader is None:
            return
        if self.mode == "RED":
            self.periods.append(f"Rote Flagge Runde {self._period_start}")
        self.mode = mode
        self._period_start = leader.laps_done + 1
        if mode == "RED":
            if self.sc is not None and self.sc.on_track:
                self.sc = None
            self.phase = ""
            s.stewards.announce(f"ROTE FLAGGE - {reason}", "penalty", 10.0)
            s.message("ROTE FLAGGE - Rennen unterbrochen", (255, 70, 60), 4.0)
            s.add_feed(f"ROTE FLAGGE: {reason}")
            self._since = s.time
            self._ref, self._rank = [], {}
            self._line_due = {}
            self._pending = {}
            return
        if mode == "SC":
            self.sc = SafetyCar(s, leader.s + 380.0)
            self.sc.speed = leader.speed_fwd
            self.phase = "out"
            self.sc_end_lap = leader.laps_done + SC_LAPS
            s.stewards.announce(f"SAFETY CAR - {reason}", "investigation", 8.0)
            s.message("SAFETY CAR - nicht überholen!", YELLOW, 3.5)
        else:
            self.until = s.time + random.uniform(25.0, 40.0)
            s.stewards.announce(f"VIRTUAL SAFETY CAR - {reason}", "investigation", 8.0)
            s.message("VIRTUAL SAFETY CAR - Tempo reduzieren", YELLOW, 3.5)
        s.add_feed(f"{'SAFETY CAR' if mode == 'SC' else 'VSC'}: {reason}")
        self._since = s.time
        self._ref, self._rank = [], {}
        self._line_due = {}
        self._pending = {}
        self._cheap_stops()

    def _cheap_stops(self) -> None:
        s = self.s
        for car in s.cars:
            if car.dnf or car.session_done or car.in_pit or car.pit_request is not None or car.tyres is None:
                continue
            remaining = s.total_laps - car.laps_done
            if car is s.player:
                if remaining > 2:
                    s.message("Günstiger Stopp unter Neutralisation möglich (B)", (255, 200, 40), 3.0)
                continue
            if remaining > 2:
                car.pit_request = s.plan_pit(car, neutralised=True)

    def _end(self) -> None:
        s = self.s
        leader = self._leader()
        lap = leader.laps_done if leader else self._period_start
        name = "Rote Flagge" if self.mode == "RED" else self.mode
        self.periods.append(f"{name} Runde {self._period_start}-{max(self._period_start, lap)}")
        s.stewards.announce("GRÜNE FLAGGE - Rennen freigegeben", "info", 6.0)
        s.message("GRÜN! RESTART!" if self.mode in ("SC", "RED") else "VSC ENDE - GRÜN!", (60, 220, 90), 2.5)
        self.mode = None
        self.phase = ""
        if self.sc is not None and self.sc.on_track:
            self.sc = None          # (a safety car still driving down the pit lane finishes parking)
        self.cooldown_until = s.time + COOLDOWN
        self.green_until = s.time + 6.0
        self.yellow.clear()
        # the field keeps its order until each car has crossed the control line
        self._line_due = {c: c.laps_done for c in self._ref if self._racing(c)}
        self._line_until = s.time + RESTART_LINE_TIME

    def step(self, h: float) -> None:
        s = self.s
        now = s.time
        for k, v in list(self.yellow.items()):
            if v <= now:
                del self.yellow[k]
                self.cleared[k] = now + 6.0
        self._punctures(h)
        self._order_timer -= h
        if self._order_timer <= 0 and (self.active or self.give_back or self._line_due):
            self._order_timer = 0.25
            self._check_overtakes()
        if self.mode == "VSC" and now >= self.until:
            self._end()
        elif self.mode == "SC":
            self._sc_step(h)
        elif self.sc is not None:
            self.sc.update(h, 0.0)
            if self.sc.done:
                self.sc = None

    def _sc_step(self, h: float) -> None:
        s, sc = self.s, self.sc
        leader = self._leader()
        self._lead = leader
        top = TOP_SPEED
        if self.phase in ("out", "in") and (sc is None or not sc.on_track):
            self.phase = "restart"
            self._restart_lap = leader.laps_done if leader else 0
        if self.phase == "out" and sc is not None:
            sc.update(h, top * SC_SPEED)
            if leader is not None and leader.laps_done >= self.sc_end_lap:
                self.phase = "in"
                s.message("SAFETY CAR IN THIS LAP", YELLOW, 3.0)
                s.add_feed("Safety Car kommt in dieser Runde rein")
        elif self.phase == "in" and sc is not None:
            sc.lights_on = False
            sc.update(h, top * SC_SPEED)
            pit = s.track.pit
            entry = pit.entry_abs() if pit is not None else 0.0
            if (sc.s - entry) % s.track.length < 30.0:
                self.phase = "restart"
                self._restart_lap = leader.laps_done if leader else 0
                if pit is not None:
                    sc.enter_pit()          # drives down the pit lane instead of vanishing
                else:
                    self.sc = None
        elif self.phase == "restart":
            if sc is not None:
                sc.update(h, 0.0)
                if sc.done:
                    self.sc = None
            if leader is None or leader.laps_done > self._restart_lap:
                self._end()

    def governor(self, car: "Car") -> None:
        if car.in_pit or car.session_done or car.frozen:
            return
        yielding = self.must_yield(car) and not car.is_player
        if not self.active and not yielding:
            return
        top = car.top_speed
        if self.mode == "RED":
            target = self._red_target(car, top)
            if target < 2.0:
                # stopped in line, waiting for the restart (no brake at a standstill: that would be reverse)
                car.throttle, car.brake = 0.0, (1.0 if car.speed_fwd > 1.0 else 0.0)
                car.straight_mode = False
                return
        elif self.mode == "VSC":
            target = top * VSC_SPEED
        elif self.mode == "SC":
            target = self._follow_target(car, top)
        else:
            target = top
        if yielding:
            # an AI that has to give a place back: lift until the car it passed is by again
            victim = next(b for a, b in self.give_back if a is car)
            target = min(target, max(top * 0.2, victim.speed_fwd * 0.8))
        hold_speed(car, target)

    def _ahead_in_order(self, o: "Car", car: "Car") -> bool:
        """Whether o is ahead of car in the order to be kept (the reference order, race distance otherwise)."""
        ro, rc = self._rank.get(o), self._rank.get(car)
        if ro is not None and rc is not None:
            return ro < rc
        return o.distance > car.distance

    def _follow_target(self, car: "Car", top: float) -> float:
        s = self.s
        L = s.track.length
        best_gap, best_speed = None, 0.0
        yielding = {a for a, b in self.give_back if b is car}
        objects = [(o.s, o.speed_fwd, self._ahead_in_order(o, car)) for o in s.cars if o is not car
                   and not o.in_pit and not o.dnf and not o.session_done and o not in yielding]
        if self.sc is not None and self.sc.on_track:
            objects.append((self.sc.s, self.sc.speed, True))
        for os_, ov, in_front in objects:
            gap = (os_ - car.s + L / 2) % L - L / 2
            # side by side: only the car that is behind in the kept order falls back into line
            lower = -60.0 if in_front else 5.0
            if lower < gap < 900.0 and (best_gap is None or gap < best_gap):
                best_gap, best_speed = gap, ov
        if self.sc is not None and self.sc.on_track and self.phase in ("out", "in"):
            sc_gap = (self.sc.s - car.s + L / 2) % L - L / 2
            if -500.0 < sc_gap < 10.0 and car is self._lead:
                # the leader has got alongside/past the safety car: drop back behind it
                return top * SC_SPEED * 0.55
        if best_gap is None:
            limit = top * SC_SPEED if self.phase == "restart" else top * CATCH_UP
            return limit
        return follow_speed(best_gap, best_speed, top)

    def _red_target(self, car: "Car", top: float) -> float:
        """Red flag: slow down and stop in order, GAP_TARGET behind the car ahead (the leader just stops)."""
        L = self.s.track.length
        best_gap, best_speed = None, 0.0
        for o in self.s.cars:
            if o is car or o.in_pit or o.dnf or o.session_done:
                continue
            gap = (o.s - car.s + L / 2) % L - L / 2
            lower = -60.0 if self._ahead_in_order(o, car) else 5.0
            if lower < gap < 900.0 and (best_gap is None or gap < best_gap):
                best_gap, best_speed = gap, o.speed_fwd
        if best_gap is None:
            left = max(0.0, 1.0 - (self.s.time - self._since) / RED_STOP_TIME)
            return top * RED_SPEED * left
        target = best_speed + FOLLOW_GAIN * (best_gap - GAP_TARGET)
        return max(0.0, min(top * RED_SPEED, target))

    @staticmethod
    def _racing(car: "Car") -> bool:
        return not (car.in_pit or car.dnf or car.session_done or car.puncture or car.frozen or car.is_ghost)

    def _fair_victim(self, b: "Car") -> bool:
        return self._racing(b) and not self.must_yield(b) and b.pit_request is None and b.speed_fwd > 60.0

    PASS_MARGIN = CAR_LENGTH * 1.25     # clearly past: more than a whole car length ahead (not side by side)
    PASS_HOLD = 1.5

    def _sync_reference(self, order: list["Car"]) -> None:
        """Keep the reference order: cars that pit or retire leave it, cars back from the pit lane join it where
        they rejoined. During the grace period it simply follows the track."""
        racing = [c for c in order if self._racing(c)]
        if self.active and self.s.time - self._since <= GRACE:
            self._ref = racing
            self._rank = {c: k for k, c in enumerate(racing)}
            return
        keep = set(racing)
        ref = [c for c in self._ref if c in keep]
        known = set(ref)
        rank = {c: k for k, c in enumerate(order)}
        for c in racing:
            if c in known:
                continue
            at = next((k for k, o in enumerate(ref) if rank[o] > rank[c]), len(ref))
            ref.insert(at, c)
        self._ref = ref
        self._rank = {c: k for k, c in enumerate(ref)}

    def _no_passing(self, a: "Car") -> bool:
        """Whether car a may not overtake right now: SC/VSC, or after the restart before its own line crossing."""
        if self.active:
            return self.s.time - self._since > GRACE
        due = self._line_due.get(a)
        return due is not None and a.laps_done <= due

    def _check_overtakes(self) -> None:
        s = self.s
        now = s.time
        order = s.standings()
        pos = {c: k for k, c in enumerate(order)}
        for (a, b), deadline in list(self.give_back.items()):
            if pos[a] > pos[b]:
                del self.give_back[(a, b)]
                s.stewards.announce(f"{a.short} hat die Position an {b.short} zurückgegeben", "info", 5.0)
                if a is s.player:
                    s.message("Position zurückgegeben - keine Strafe", (60, 220, 90), 2.5)
            elif not self._racing(b) or a.dnf or a.session_done:
                del self.give_back[(a, b)]
            elif now >= deadline:
                del self.give_back[(a, b)]
                s.stewards.penalty(a, 5.0, f"unter {self.mode or 'Safety Car'} {b.short} überholt")
        if self._line_due:
            self._line_due = {c: d for c, d in self._line_due.items()
                              if c.laps_done <= d and self._racing(c) and now < self._line_until}
        if not self.active and not self._line_due:
            self._ref, self._rank = [], {}
            self._pending.clear()
            return
        self._sync_reference(order)
        ref = self._ref
        for i, b in enumerate(ref):
            for a in ref[i + 1:]:
                # a should be behind b - is it ahead on the road?
                if pos[a] > pos[b] or a.laps_done < b.laps_done:
                    self._pending.pop((a, b), None)
                    continue
                if not self._no_passing(a) or not self._fair_victim(b) or self.must_yield(b) or \
                        (a, b) in self.give_back:
                    # a legal place change (b slow with a problem, in the pit entry, giving a place back; or
                    # still in the grace period): the reference follows the road
                    if (a, b) not in self.give_back:
                        self._pending.pop((a, b), None)
                        ref.remove(a)
                        ref.insert(ref.index(b), a)
                        self._rank = {c: k for k, c in enumerate(ref)}
                        return      # indices changed: carry on with the next check
                    continue
                since = self._pending.setdefault((a, b), now)
                if a.distance - b.distance > self.PASS_MARGIN and now - since >= self.PASS_HOLD:
                    del self._pending[(a, b)]
                    self.give_back[(a, b)] = now + GIVE_BACK_TIME
                    what = self.mode or "Restart"
                    s.stewards.announce(f"Überholen unter {what}: {a.short} muss Platz an {b.short} "
                                        "zurückgeben", "investigation", 6.0)
                    if a is s.player:
                        s.message(f"Unter {what} überholt! Lass {b.short} vorbei ({GIVE_BACK_TIME:.0f} s)",
                                  (255, 140, 30), 4.0)
                    elif b is s.player:
                        s.message(f"{a.short} hat dich unter {what} überholt - er muss zurückgeben",
                                  YELLOW, 3.0)
        for key in [k for k in self._pending if k[0] not in ref or k[1] not in ref]:
            del self._pending[key]

    def must_yield(self, car: "Car") -> bool:
        return any(a is car for a, _ in self.give_back)

    def _punctures(self, h: float) -> None:
        self._puncture_timer -= h
        if self._puncture_timer > 0:
            return
        self._puncture_timer = 0.5
        s = self.s
        for car in s.cars:
            t = car.tyres
            if t is None or car.puncture or car.in_pit or car.session_done or car.dnf:
                continue
            if t.wear > PUNCTURE_WEAR and random.random() < 0.5 * 0.08 * (t.wear - PUNCTURE_WEAR) / (1 - PUNCTURE_WEAR):
                self.puncture(car, "abgefahrener Reifen")

    def puncture(self, car: "Car", why: str) -> None:
        s = self.s
        car.puncture = True
        s.add_feed(f"REIFENSCHADEN: {car.short} ({why})")
        sector = self.sector_of(car)
        self.yellow[sector] = s.time + YELLOW_TIME * 0.5
        self.yellow_at[sector] = car.s % s.track.length
        if car is s.player:
            s.message("REIFENSCHADEN! Sofort an die Box (B)", (255, 80, 80), 4.0)
            if car.pit_request is None:
                car.pit_request = car.tyres.compound.key if car.tyres else "medium"
        elif car.pit_request is None:
            remaining = s.total_laps - car.laps_done
            car.pit_request = s._compound_for_laps(max(1, remaining - 1))
