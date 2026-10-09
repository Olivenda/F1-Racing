# Copyright Olivenda (Oliver Petz) 2026
"""In-race pit stop menu (B). Plans tyres, fuel, a front-wing adjustment and repairs for the next stop, and shows
what the stop will cost: time standing, time lost in the lane, the expected position on rejoin, how long the new
tyres will last and what the race strategy from practice says.

Keyboard: 1-4 change the rows (Shift = backwards) so the arrow keys stay free for driving, ENTER or 5 confirms
(or cancels an ordered stop), B closes. Controller: D-pad up/down/left/right, A on the last row or the pit
button confirms.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .car import PLANK_LIMIT_MM
from .pitlane import SPEED_LIMIT
from .settings import CYAN, GREEN, GREY, ORANGE, PANEL_LIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .tyres import ALL_COMPOUNDS, COMPOUNDS
from .utils import draw_panel, draw_text

if TYPE_CHECKING:
    from .player_car import Player_Car
    from .sessions import Session

TYRE_OPTIONS = ["keep"] + ALL_COMPOUNDS
ROWS = ["Reifen", "Tanken", "Frontflügel", "Reparatur", "BOX"]
RED = (255, 90, 90)


def lane_loss(car) -> float:
    """Seconds lost driving through the pit lane at the limiter instead of racing past it."""
    pit = car.track.pit
    if pit is None:
        return 20.0
    race_speed = max(100.0, car.top_speed * 0.75)
    return pit.length / SPEED_LIMIT - pit.length / race_speed + 2.0


class PitMenu:

    def __init__(self) -> None:
        self.open = False
        self.sel = 0
        self.tyre = 2
        self.fuel = 0.0
        self.front_wing = 0
        self.repair = True
        self._rejoin: tuple[float, int, str] | None = None

    def toggle(self, car: "Player_Car") -> None:
        if self.open:
            self.open = False
            return
        self.open = True
        self.sel = 0
        self._rejoin = None
        if car.pit_request is not None and car.pit_plan is not None:
            # reopening shows what is already ordered
            self.tyre = TYRE_OPTIONS.index(car.pit_request) if car.pit_request in TYRE_OPTIONS else 0
            self.fuel = car.pit_plan.get("fuel", 0.0)
            self.front_wing = car.pit_plan.get("front_wing", 0)
            self.repair = car.pit_plan.get("repair", True)
        else:
            # a fresh plan: the next tyre of the race strategy, else a new set of the current compound
            plan = car.next_planned_stop()
            current = plan[1] if plan else car.tyres.compound.key if car.tyres is not None else "medium"
            self.tyre = TYRE_OPTIONS.index(current) if current in TYRE_OPTIONS else 0
            self.fuel, self.front_wing, self.repair = 0.0, 0, True

    def _change(self, row: int, delta: int, car: "Player_Car", session: "Session") -> None:
        if row == 0:
            self.tyre = (self.tyre + delta) % len(TYRE_OPTIONS)
        elif row == 1 and car.fuel_per_lap > 0:
            self.fuel = max(0.0, min(self._max_fuel(car, session), self.fuel + 0.5 * delta))
        elif row == 2 and car.setup is not None:
            fw = car.setup.front_wing
            self.front_wing = max(-5 - fw, min(5 - fw, self.front_wing + delta))
        elif row == 3:
            self.repair = not self.repair
        self._rejoin = None

    @staticmethod
    def _max_fuel(car: "Player_Car", session: "Session") -> float:
        total = getattr(session, "total_laps", session.config.race_laps)
        return max(0.0, round((total + 3 - car.fuel_laps) * 2) / 2)

    def _confirm(self, car: "Player_Car", session: "Session") -> None:
        nothing = TYRE_OPTIONS[self.tyre] == "keep" and self.fuel <= 0 and not self.front_wing and \
            not (self.repair and car.damage.total > 0.05)
        if self.sel == 4 and car.pit_request is not None:
            car.pit_request = None
            car.pit_plan = None
            session.message("Boxenstopp abgesagt", WHITE, 2.0)
        elif nothing and car.pit_request is None:
            session.message("Nichts zu tun - Boxenstopp nicht angefordert", GREY, 2.0)
        else:
            car.pit_request = TYRE_OPTIONS[self.tyre]
            car.pit_plan = {"fuel": self.fuel, "front_wing": self.front_wing, "repair": self.repair}
            comp = COMPOUNDS.get(car.pit_request)
            session.message(f"BOX in dieser Runde: {self._summary(car)}", comp.color if comp else ORANGE, 2.5)
        self.open = False

    def _summary(self, car: "Player_Car") -> str:
        parts = []
        t = TYRE_OPTIONS[self.tyre]
        parts.append(f"{COMPOUNDS[t].name}-Reifen" if t in COMPOUNDS else "ohne Reifenwechsel")
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
        if pygame.K_1 <= key <= pygame.K_4:
            self.sel = key - pygame.K_1
            self._change(self.sel, back, car, session)
        elif joy and key in (pygame.K_UP, pygame.K_DOWN):
            self.sel = (self.sel + (-1 if key == pygame.K_UP else 1)) % len(ROWS)
        elif joy and key in (pygame.K_LEFT, pygame.K_RIGHT):
            self._change(self.sel, -1 if key == pygame.K_LEFT else 1, car, session)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) or (key == pygame.K_5):
            if self.sel == 4 or not joy or key == pygame.K_5:
                self.sel = 4 if key == pygame.K_5 else self.sel
                self._confirm(car, session)
            else:
                self._change(self.sel, 1, car, session)
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
        tyres = TYRE_OPTIONS[self.tyre] in COMPOUNDS
        base = session.stop_time(car) if tyres else 0.0
        fuel_time = self.fuel * car.fuel_per_lap / REFUEL_KG_PER_S
        wing_time = 0.8 if self.front_wing else 0.0
        repair = car.damage.repair_time() if self.repair else 0.0
        return max(base, fuel_time, wing_time, 0.8) + repair + car.penalty_unserved

    def tyre_life(self, car: "Player_Car") -> float | None:
        """Laps the chosen new set should last (to 75% wear), from the wear rate measured on the current set."""
        t = car.tyres
        choice = TYRE_OPTIONS[self.tyre]
        if t is None:
            return None
        L = car.track.length
        laps_on_set = t.laps + (car.distance % L) / L if car.timing_started else t.laps
        if laps_on_set < 0.4 or t.wear < 0.01:
            return None
        rate = t.wear / laps_on_set
        if choice in COMPOUNDS:
            rate *= t.compound.life / COMPOUNDS[choice].life
            return 0.75 / rate
        return max(0.0, (0.75 - t.wear) / rate)

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
        narrow = center_x != SCREEN_WIDTH // 2       # split screen: half the width
        w, h = (420, 430) if narrow else (720, 300)
        x, y = center_x - w // 2, 130
        draw_panel(screen, (x, y, w, h), (16, 18, 24), 238, border=ORANGE)
        draw_text(screen, "BOXENSTOPP PLANEN", f.medium, ORANGE, (x + 18, y + 12))
        ordered = car.pit_request is not None
        if ordered:
            draw_text(screen, "angefordert", f.small_bold, GREEN, (x + w - 18, y + 16), anchor="topright",
                      shadow=False)
        t = TYRE_OPTIONS[self.tyre]
        need = getattr(session, "total_laps", 0) - car.laps_done
        fuel_txt = f"+{self.fuel:.1f} Rd. ({self.fuel * car.fuel_per_lap:.0f} kg)" if car.fuel_per_lap > 0 else "-"
        if car.fuel_per_lap > 0 and need > 0:
            fuel_txt += f" · Res. {car.fuel_laps + self.fuel - need:+.1f}"
        fw_now = car.setup.front_wing if car.setup is not None else 0
        values = [
            "",
            fuel_txt,
            f"{self.front_wing:+d}  ({fw_now:+d} -> {fw_now + self.front_wing:+d})" if self.front_wing
            else f"unverändert ({fw_now:+d})",
            ("Ja" if self.repair else "Nein") + (f"  ({car.damage.repair_time():.0f}s)" if car.damage.total > 0.05
                                                 else "  (keine Schäden)"),
            "BOXENSTOPP ABSAGEN" if ordered else "BOX ANFORDERN",
        ]
        col_w = w - 28 if narrow else 360
        for k, (row, val) in enumerate(zip(ROWS, values)):
            ry = y + 50 + k * 38
            if k == self.sel:
                pygame.draw.rect(screen, PANEL_LIGHT, (x + 10, ry - 4, col_w, 34), border_radius=6)
                pygame.draw.rect(screen, ORANGE, (x + 10, ry - 4, 4, 34), border_radius=2)
            if row == "BOX":
                draw_text(screen, f"[5/ENTER]  {val}", f.small_bold, ORANGE if not ordered else (255, 120, 100),
                          (x + 10 + col_w // 2, ry + 13), anchor="center", shadow=False)
                continue
            draw_text(screen, f"[{k + 1}] {row.upper()}", f.tiny, GREY, (x + 22, ry + 13), anchor="midleft",
                      shadow=False)
            if k == 0:
                self._draw_tyre_chips(screen, f, car, x + 140, ry + 13)
            else:
                draw_text(screen, val, f.small_bold, WHITE, (x + 140, ry + 13), anchor="midleft", shadow=False)

        # ---- what the stop means
        ix, iy = (x + 18, y + 50 + 5 * 38 + 6) if narrow else (x + 390, y + 50)
        stand = self.stand_time(car, session)
        loss = lane_loss(car) + stand
        info: list[tuple[str, str, tuple[int, int, int]]] = []
        if car.tyres is not None:
            cur = car.tyres
            info.append(("Jetzt", f"{cur.compound.name} · {cur.wear * 100:.0f}% · {cur.laps} Rd.",
                         GREEN if cur.wear < 0.5 else YELLOW if cur.wear < 0.75 else RED))
        life = self.tyre_life(car)
        if t in COMPOUNDS:
            if life is None:
                info.append(("Neue Reifen", "Prognose nach der ersten Runde", GREY))
            else:
                ok = need <= 0 or life >= need - 0.5
                txt = f"halten ~{life:.0f} Rd." + (" · bis ins Ziel" if ok and need > 0 else
                                                   f" · Ziel in {need}" if need > 0 else "")
                info.append(("Neue Reifen", txt, GREEN if ok else YELLOW))
        info.append(("Stopp", f"~{stand:.1f}s stehen · ~{loss:.0f}s Verlust", WHITE))
        back = self.rejoin(car, session, loss)
        if back is not None:
            pos, ahead = back
            info.append(("Rückkehr", f"P{pos}" + (f" hinter {ahead}" if ahead else " - in Führung"),
                         GREEN if pos <= session.standings().index(car) + 1 else YELLOW))
        plan = car.next_planned_stop() if session.kind == "race" else None
        if plan is not None:
            lap, comp = plan
            to_go = lap - (car.laps_done + 1)
            when = "diese Runde" if to_go <= 0 else f"in {to_go} Rd. (Rd. {lap})"
            info.append(("Strategie", f"Stopp {car.pit_stops + 1}: {when} -> {COMPOUNDS[comp].name}",
                         ORANGE if to_go <= 0 else CYAN))
        elif car.strategy and session.kind == "race":
            info.append(("Strategie", "Keine weiteren Stopps geplant", CYAN))
        for k, (label, text, col) in enumerate(info):
            ly = iy + k * 38
            draw_text(screen, label.upper(), f.tiny, GREY, (ix, ly), shadow=False)
            draw_text(screen, text, f.small_bold, col, (ix, ly + 15), shadow=False)
        note = f"Planke {car.plank_wear:.2f}/{PLANK_LIMIT_MM:.1f} mm - wird nicht getauscht"
        draw_text(screen, note, f.tiny, YELLOW if car.plank_wear > 0.8 * PLANK_LIMIT_MM else GREY,
                  (x + 18, y + h - 22), shadow=False)
        if not narrow:
            draw_text(screen, "1-4 ändern (Shift zurück) · 5/ENTER bestätigen · B schließen", f.tiny, GREY,
                      (x + w - 18, y + h - 22), anchor="topright", shadow=False)

    def _draw_tyre_chips(self, screen: pygame.Surface, f, car: "Player_Car", x: int, cy: int) -> None:
        """All tyre choices side by side; the chosen one is ringed and named."""
        for k, opt in enumerate(TYRE_OPTIONS):
            cx = x + 13 + k * 31
            chosen = k == self.tyre
            if opt == "keep":
                pygame.draw.circle(screen, (60, 62, 70) if chosen else (34, 36, 42), (cx, cy), 12)
                draw_text(screen, "-", f.small_bold, WHITE if chosen else GREY, (cx, cy - 1), anchor="center",
                          shadow=False)
            else:
                c = COMPOUNDS[opt]
                pygame.draw.circle(screen, (15, 15, 18), (cx, cy), 12)
                pygame.draw.circle(screen, c.color if chosen else tuple(v // 2 for v in c.color), (cx, cy), 12,
                                   3 if chosen else 2)
                draw_text(screen, c.letter, f.tiny, c.color if chosen else GREY, (cx, cy), anchor="center",
                          shadow=False)
            if chosen:
                pygame.draw.circle(screen, WHITE, (cx, cy), 15, 1)
        t = TYRE_OPTIONS[self.tyre]
        name = COMPOUNDS[t].name if t in COMPOUNDS else "nicht wechseln"
        draw_text(screen, name, f.tiny, COMPOUNDS[t].color if t in COMPOUNDS else WHITE,
                  (x + len(TYRE_OPTIONS) * 31 + 4, cy), anchor="midleft", shadow=False)
