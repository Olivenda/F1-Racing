# Copyright Olivenda (Oliver Petz) 2026
"""In-race pit stop menu (B). The crew prepares the tyres - from the race strategy, the weather or the race
engineer's call - and the menu shows exactly what the stop will bring: the tyres, the time standing and lost, the
position on rejoin and how long the new set lasts. The driver adjusts fuel, the front wing and repairs, and
orders or cancels the stop. Entering the pit lane is up to the driver: follow the guide line to the pit entry.

Keys: the pit-menu keybinds (default I/K up/down, J/L less/more, U confirm; rebindable in the controls menu),
or 1-3 change a row directly (Shift = backwards) and 4/5/ENTER confirm. Controller: D-pad, or the bound buttons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .car import PLANK_LIMIT_MM
from .pitlane import SPEED_LIMIT
from .settings import CYAN, GREEN, GREY, ORANGE, PANEL_LIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .tyres import COMPOUND_ORDER, COMPOUNDS
from .utils import draw_panel, draw_text

if TYPE_CHECKING:
    from .player_car import Player_Car
    from .sessions import Session

ROWS = ["Tanken", "Frontflügel", "Reparatur", "BOX"]
RED = (255, 90, 90)
NAV_UP, NAV_DOWN, NAV_LESS, NAV_MORE, NAV_OK = pygame.K_F5, pygame.K_F6, pygame.K_F7, pygame.K_F8, pygame.K_F9


def lane_loss(car) -> float:
    """Seconds lost driving through the pit lane at the limiter instead of racing past it."""
    pit = car.track.pit
    if pit is None:
        return 20.0
    race_speed = max(100.0, car.top_speed * 0.75)
    return pit.length / SPEED_LIMIT - pit.length / race_speed + 2.0


def wear_rate(car) -> float | None:
    """Tyre wear per lap measured on the current set (None before there is enough of it)."""
    t = car.tyres
    if t is None:
        return None
    L = car.track.length
    laps_on_set = t.laps + (car.distance % L) / L if car.timing_started else t.laps
    if laps_on_set < 0.4 or t.wear < 0.01:
        return None
    return t.wear / laps_on_set


def crew_choice(car, session: "Session") -> tuple[str, str]:
    """(compound, why) the crew has ready for the next stop: weather first, then the race strategy, then the
    engineer's pick - the fastest dry compound that still reaches the finish."""
    call = session.weather_tyre_call(car) if hasattr(session, "weather_tyre_call") else None
    if call in COMPOUNDS:
        return call, "Wetter"
    wet = session.track.wetness
    current = car.tyres.compound.key if car.tyres is not None else "medium"
    if car.tyres is not None and car.tyres.compound.kind != "slick" and wet > 0.16:
        return current, "Wetter"
    plan = car.next_planned_stop() if session.kind == "race" else None
    if plan is not None:
        return plan[1], "Strategie"
    remaining = getattr(session, "total_laps", 0) - car.laps_done - 1
    rate = wear_rate(car)
    if session.kind != "race" or remaining <= 0 or rate is None or car.tyres is None:
        return (current if current in COMPOUND_ORDER else "medium"), "Renningenieur"
    for comp in COMPOUND_ORDER:                     # soft first: the fastest one that lasts
        life = 0.75 / (rate * car.tyres.compound.life / COMPOUNDS[comp].life)
        if life >= remaining:
            return comp, "Renningenieur"
    return COMPOUND_ORDER[-1], "Renningenieur"


class PitMenu:

    def __init__(self) -> None:
        self.open = False
        self.sel = 0
        self.fuel = 0.0
        self.front_wing = 0
        self.repair = True
        self._rejoin: tuple[float, int, str] | None = None

    def toggle(self, car: "Player_Car") -> None:
        if self.open:
            self.open = False
            return
        self.open = True
        self.sel = len(ROWS) - 1
        self._rejoin = None
        if car.pit_plan is not None:
            # reopening shows what is already ordered
            self.fuel = car.pit_plan.get("fuel", 0.0)
            self.front_wing = car.pit_plan.get("front_wing", 0)
            self.repair = car.pit_plan.get("repair", True)
        else:
            self.fuel, self.front_wing, self.repair = 0.0, 0, True

    def tyre(self, car: "Player_Car", session: "Session") -> tuple[str, str]:
        """The tyres this stop brings: what is ordered, else what the crew has ready."""
        if car.pit_request in COMPOUNDS:
            return car.pit_request, getattr(car, "pit_reason", "") or "Crew"
        return crew_choice(car, session)

    def _change(self, row: int, delta: int, car: "Player_Car", session: "Session") -> None:
        if row == 0 and car.fuel_per_lap > 0:
            self.fuel = max(0.0, min(self._max_fuel(car, session), self.fuel + 0.5 * delta))
        elif row == 1 and car.setup is not None:
            fw = car.setup.front_wing
            self.front_wing = max(-5 - fw, min(5 - fw, self.front_wing + delta))
        elif row == 2:
            self.repair = not self.repair
        self._rejoin = None
        if car.pit_request is not None:
            car.pit_plan = self._plan()             # an ordered stop follows the changes right away

    def _plan(self) -> dict:
        return {"fuel": self.fuel, "front_wing": self.front_wing, "repair": self.repair}

    @staticmethod
    def _max_fuel(car: "Player_Car", session: "Session") -> float:
        total = getattr(session, "total_laps", session.config.race_laps)
        return max(0.0, round((total + 3 - car.fuel_laps) * 2) / 2)

    def _confirm(self, car: "Player_Car", session: "Session") -> None:
        if car.pit_request is not None:
            car.pit_request = None
            car.pit_plan = None
            car.stop_declined_lap = car.laps_done
            session.message("Boxenstopp abgesagt", WHITE, 2.0)
        else:
            comp, why = self.tyre(car, session)
            car.pit_request = comp
            car.pit_reason = why
            car.pit_plan = self._plan()
            session.message(f"BOX angefordert: {self._summary(comp)} - Linie zur Boxeneinfahrt folgen",
                            COMPOUNDS[comp].color, 3.0)
        self.open = False

    def _summary(self, comp: str) -> str:
        parts = [f"{COMPOUNDS[comp].name}-Reifen"]
        if self.fuel > 0:
            parts.append(f"+{self.fuel:.1f} Rd. Sprit")
        if self.front_wing:
            parts.append(f"Frontflügel {self.front_wing:+d}")
        return " · ".join(parts)

    def handle_key(self, event: pygame.event.Event, car: "Player_Car", session: "Session") -> bool:
        """Returns True when the menu used the key."""
        if not self.open:
            return False
        key = event.key
        joy = getattr(event, "from_joystick", False)
        back = -1 if event.mod & pygame.KMOD_SHIFT else 1
        last = len(ROWS) - 1
        if pygame.K_1 <= key <= pygame.K_3:
            self.sel = key - pygame.K_1
            self._change(self.sel, back, car, session)
        elif key == NAV_UP or (joy and key == pygame.K_UP):
            self.sel = (self.sel - 1) % len(ROWS)
        elif key == NAV_DOWN or (joy and key == pygame.K_DOWN):
            self.sel = (self.sel + 1) % len(ROWS)
        elif key in (NAV_LESS, NAV_MORE) or (joy and key in (pygame.K_LEFT, pygame.K_RIGHT)):
            self._change(self.sel, -1 if key in (NAV_LESS, pygame.K_LEFT) else 1, car, session)
        elif key in (NAV_OK, pygame.K_4, pygame.K_5, pygame.K_RETURN, pygame.K_KP_ENTER):
            if joy and key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.sel != last:
                self._change(self.sel, 1, car, session)
            else:
                self._confirm(car, session)
        elif key == pygame.K_b:
            if joy:
                self._confirm(car, session)
            else:
                self.toggle(car)
        elif key == pygame.K_ESCAPE:
            self.open = False
        else:
            return False
        return True

    # ------------------------------------------------------------------ estimates
    def stand_time(self, car: "Player_Car", session: "Session") -> float:
        """Seconds standing in the box with this plan (same rules as the pit service in sessions.py)."""
        from .sessions import REFUEL_KG_PER_S
        fuel_time = self.fuel * car.fuel_per_lap / REFUEL_KG_PER_S
        wing_time = 0.8 if self.front_wing else 0.0
        repair = car.damage.repair_time() if self.repair else 0.0
        return max(session.stop_time(car), fuel_time, wing_time, 0.8) + repair + car.penalty_unserved

    @staticmethod
    def tyre_life(car: "Player_Car", comp: str) -> float | None:
        """Laps the new set should last (to 75% wear), from the wear rate measured on the current set."""
        rate = wear_rate(car)
        if rate is None or car.tyres is None:
            return None
        return 0.75 / (rate * car.tyres.compound.life / COMPOUNDS[comp].life)

    def rejoin(self, car: "Player_Car", session: "Session", loss: float) -> tuple[int, str] | None:
        """(position, car just ahead) after the stop: every car behind closer than the time lost gets past."""
        from .sessions import time_gap
        if session.kind != "race" or not getattr(session, "race_started", False):
            return None
        if self._rejoin is not None and session.time - self._rejoin[0] < 0.5:
            return self._rejoin[1], self._rejoin[2]
        order = session.standings()
        if car not in order:
            return None
        i = order.index(car)
        passed = []
        for other in order[i + 1:]:
            if other.dnf or other.finish_time is not None:
                continue
            gap = time_gap(car, other)
            if gap is not None and gap < loss:
                passed.append(other)
        ahead = passed[-1].short if passed else (order[i - 1].short if i > 0 else "")
        self._rejoin = (session.time, i + 1 + len(passed), ahead)
        return self._rejoin[1], self._rejoin[2]

    # ------------------------------------------------------------------ drawing
    def draw(self, screen: pygame.Surface, fonts, car: "Player_Car", session: "Session",
             center_x: int = SCREEN_WIDTH // 2) -> None:
        if not self.open:
            return
        f = fonts
        w = 430
        x, y = center_x - w // 2, 112
        ordered = car.pit_request is not None
        comp, why = self.tyre(car, session)
        c = COMPOUNDS[comp]
        need = getattr(session, "total_laps", 0) - car.laps_done

        # ---- estimates, condensed into a few lines
        stand = self.stand_time(car, session)
        loss = lane_loss(car) + stand
        lines: list[tuple[str, tuple[int, int, int]]] = []
        life = self.tyre_life(car, comp)
        if life is not None:
            ok = need <= 0 or life >= need - 0.5
            lines.append((f"Neue Reifen ~{life:.0f} Rd." + (" · bis ins Ziel" if ok and need > 0 else
                                                           f" · Ziel in {need}" if need > 0 else ""),
                          GREEN if ok else YELLOW))
        back = self.rejoin(car, session, loss)
        stop = f"Stopp ~{stand:.1f}s · Verlust ~{loss:.0f}s"
        if back is not None:
            pos, ahead = back
            stop += f" · P{pos}" + (f" hinter {ahead}" if ahead else "")
        lines.append((stop, WHITE))
        plan = car.next_planned_stop() if session.kind == "race" else None
        if plan is not None:
            lap, pcomp = plan
            to_go = lap - (car.laps_done + 1)
            when = "diese Runde" if to_go <= 0 else f"in {to_go} Rd."
            lines.append((f"Strategie: Stopp {car.pit_stops + 1} {when} -> {COMPOUNDS[pcomp].name}",
                          ORANGE if to_go <= 0 else CYAN))

        rh = 26
        h = 72 + len(ROWS) * rh + 8 + len(lines) * 19 + 26
        draw_panel(screen, (x, y, w, h), (16, 18, 24), 235, border=ORANGE)
        draw_text(screen, "BOXENSTOPP", f.small_bold, ORANGE, (x + 12, y + 8), shadow=False)
        draw_text(screen, "angefordert" if ordered else "nicht angefordert", f.tiny, GREEN if ordered else GREY,
                  (x + w - 12, y + 10), anchor="topright", shadow=False)

        # the tyres the crew has ready
        ty = y + 32
        pygame.draw.circle(screen, (15, 15, 18), (x + 26, ty + 16), 13)
        pygame.draw.circle(screen, c.color, (x + 26, ty + 16), 13, 3)
        draw_text(screen, c.letter, f.small_bold, c.color, (x + 26, ty + 16), anchor="center", shadow=False)
        draw_text(screen, f"{c.name}-Reifen", f.small_bold, c.color, (x + 46, ty + 2), shadow=False)
        cur = car.tyres
        sub = f"Reifenwahl: {why}" + (f" · jetzt {cur.compound.letter} {cur.wear * 100:.0f}%" if cur else "")
        draw_text(screen, sub, f.tiny, GREY, (x + 46, ty + 20), shadow=False)

        fuel_txt = f"+{self.fuel:.1f} Rd. ({self.fuel * car.fuel_per_lap:.0f} kg)" if car.fuel_per_lap > 0 else "-"
        if car.fuel_per_lap > 0 and need > 0:
            fuel_txt += f" · Res. {car.fuel_laps + self.fuel - need:+.1f}"
        fw_now = car.setup.front_wing if car.setup is not None else 0
        values = [
            fuel_txt,
            f"{fw_now:+d} -> {fw_now + self.front_wing:+d}" if self.front_wing else f"unverändert ({fw_now:+d})",
            ("Ja" if self.repair else "Nein") + (f"  ({car.damage.repair_time():.0f}s)" if car.damage.total > 0.05
                                                 else "  (keine Schäden)"),
            "BOXENSTOPP ABSAGEN" if ordered else "BOX ANFORDERN",
        ]
        for k, (row, val) in enumerate(zip(ROWS, values)):
            ry = y + 72 + k * rh
            if k == self.sel:
                pygame.draw.rect(screen, PANEL_LIGHT, (x + 6, ry - 2, w - 12, rh - 2), border_radius=5)
                pygame.draw.rect(screen, ORANGE, (x + 6, ry - 2, 3, rh - 2), border_radius=2)
            mid = ry + rh // 2 - 2
            if row == "BOX":
                draw_text(screen, val, f.small_bold, ORANGE if not ordered else (255, 120, 100),
                          (x + w // 2, mid), anchor="center", shadow=False)
                continue
            draw_text(screen, str(k + 1), f.tiny, ORANGE, (x + 16, mid), anchor="midleft", shadow=False)
            draw_text(screen, row.upper(), f.tiny, GREY, (x + 30, mid), anchor="midleft", shadow=False)
            draw_text(screen, val, f.tiny, WHITE, (x + 132, mid), anchor="midleft", shadow=False)

        ly = y + 72 + len(ROWS) * rh + 6
        for text, col in lines:
            draw_text(screen, text, f.tiny, col, (x + 12, ly), shadow=False)
            ly += 19
        note = f"Planke {car.plank_wear:.2f}/{PLANK_LIMIT_MM:.1f} mm · 1-3 ändern · 4/ENTER · B zu"
        draw_text(screen, note, f.tiny, YELLOW if car.plank_wear > 0.8 * PLANK_LIMIT_MM else (120, 120, 130),
                  (x + 12, y + h - 20), shadow=False)
