# Copyright Olivenda (Oliver Petz) 2026
"""In-race pit stop menu (B). Plans tyres, fuel, a front-wing adjustment and repairs for the next stop.

Keyboard: 1-4 change the rows (Shift = backwards) so the arrow keys stay free for driving, ENTER confirms,
5 cancels an ordered stop, B closes. Controller: D-pad up/down/left/right, A on the last row or the pit
button confirms.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .car import PLANK_LIMIT_MM
from .settings import GREEN, GREY, ORANGE, PANEL_LIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .tyres import ALL_COMPOUNDS, COMPOUNDS
from .utils import draw_panel, draw_text

if TYPE_CHECKING:
    from .player_car import Player_Car
    from .sessions import Session

TYRE_OPTIONS = ["keep"] + ALL_COMPOUNDS
ROWS = ["Reifen", "Tanken", "Frontflügel", "Reparatur", "BOX"]


class PitMenu:

    def __init__(self) -> None:
        self.open = False
        self.sel = 0
        self.tyre = 2
        self.fuel = 0.0
        self.front_wing = 0
        self.repair = True

    def toggle(self, car: "Player_Car") -> None:
        if self.open:
            self.open = False
            return
        self.open = True
        self.sel = 0
        if car.pit_request is not None and car.pit_plan is not None:
            # reopening shows what is already ordered
            self.tyre = TYRE_OPTIONS.index(car.pit_request) if car.pit_request in TYRE_OPTIONS else 0
            self.fuel = car.pit_plan.get("fuel", 0.0)
            self.front_wing = car.pit_plan.get("front_wing", 0)
            self.repair = car.pit_plan.get("repair", True)
        else:
            # a fresh plan: a new set of the current compound, nothing else
            current = car.tyres.compound.key if car.tyres is not None else "medium"
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

    def draw(self, screen: pygame.Surface, fonts, car: "Player_Car", session: "Session") -> None:
        if not self.open:
            return
        f = fonts
        w, h = 400, 262
        x, y = SCREEN_WIDTH // 2 - w // 2, 150
        draw_panel(screen, (x, y, w, h), (16, 18, 24), 235, border=ORANGE)
        draw_text(screen, "BOXENSTOPP PLANEN", f.medium, ORANGE, (x + 18, y + 12))
        ordered = car.pit_request is not None
        if ordered:
            draw_text(screen, "angefordert", f.tiny, GREEN, (x + w - 18, y + 18), anchor="topright", shadow=False)
        t = TYRE_OPTIONS[self.tyre]
        need = getattr(session, "total_laps", 0) - car.laps_done
        fuel_txt = f"+{self.fuel:.1f} Rd. ({self.fuel * car.fuel_per_lap:.0f} kg)" if car.fuel_per_lap > 0 else "-"
        if car.fuel_per_lap > 0 and need > 0:
            fuel_txt += f"  ->  Reserve {car.fuel_laps + self.fuel - need:+.1f}"
        fw_now = car.setup.front_wing if car.setup is not None else 0
        values = [
            COMPOUNDS[t].name if t in COMPOUNDS else "nicht wechseln",
            fuel_txt,
            f"{self.front_wing:+d}  (jetzt {fw_now:+d} -> {fw_now + self.front_wing:+d})" if self.front_wing
            else f"unverändert ({fw_now:+d})",
            ("Ja" if self.repair else "Nein") + (f"  ({car.damage.repair_time():.0f}s)" if car.damage.total > 0.05
                                                 else "  (keine Schäden)"),
            "BOXENSTOPP ABSAGEN" if ordered else "BOX ANFORDERN",
        ]
        for k, (row, val) in enumerate(zip(ROWS, values)):
            ry = y + 50 + k * 36
            if k == self.sel:
                pygame.draw.rect(screen, PANEL_LIGHT, (x + 10, ry - 4, w - 20, 32), border_radius=6)
                pygame.draw.rect(screen, ORANGE, (x + 10, ry - 4, 4, 32), border_radius=2)
            if row == "BOX":
                draw_text(screen, f"[5/ENTER]  {val}", f.small_bold, ORANGE if not ordered else (255, 120, 100),
                          (x + w // 2, ry + 12), anchor="center", shadow=False)
                continue
            draw_text(screen, f"[{k + 1}] {row.upper()}", f.tiny, GREY, (x + 22, ry + 12), anchor="midleft",
                      shadow=False)
            col = COMPOUNDS[t].color if k == 0 and t in COMPOUNDS else WHITE
            draw_text(screen, val, f.small_bold, col, (x + 150, ry + 12), anchor="midleft", shadow=False)
        note = f"Planke {car.plank_wear:.2f}/{PLANK_LIMIT_MM:.1f} mm - wird nicht getauscht"
        draw_text(screen, note, f.tiny, YELLOW if car.plank_wear > 0.8 * PLANK_LIMIT_MM else GREY,
                  (x + 18, y + h - 22), shadow=False)
