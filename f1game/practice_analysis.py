# Copyright Olivenda (Oliver Petz) 2026
"""Telemetry review after free practice: per-lap tyre wear, fuel use and plank wear, projected onto the race."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pygame

from .car import PLANK_LIMIT_MM
from .settings import CYAN, GREEN, GREY, PANEL, PANEL_LIGHT, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .tyres import COMPOUNDS
from .user_settings import speed_in
from .utils import draw_panel, draw_text, format_time

if TYPE_CHECKING:
    from .game import Game
    from .player_car import Player_Car

RED = (255, 90, 90)


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


class PracticeAnalysisScreen:

    VISIBLE_ROWS = 14

    def __init__(self, game: "Game", car: "Player_Car", race_laps: int, on_continue: Callable[[], None],
                 continue_label: str) -> None:
        from .screens import _Background
        self.game = game
        self.car = car
        self.log = car.lap_log
        self.race_laps = max(1, race_laps)
        self.on_continue = on_continue
        self.continue_label = continue_label
        self.bg = _Background()
        self.t = 0.0
        self.scroll = 0
        self.findings = self._analyse()

    # ------------------------------------------------------------------ analysis
    def _clean(self) -> list[dict]:
        """Laps that say something about race pace: no pit stop, valid, not an out-lap."""
        return [e for e in self.log if not e["pit"] and e["wear_delta"] is not None and e["lap"] > 1] or \
            [e for e in self.log if not e["pit"] and e["wear_delta"] is not None]

    def _analyse(self) -> list[tuple[str, str, tuple[int, int, int]]]:
        out: list[tuple[str, str, tuple[int, int, int]]] = []
        laps = self._clean()
        n = self.race_laps
        if not laps:
            return [("Zu wenig Daten", "Fahre mindestens 2 volle Runden ohne Boxenstopp.", GREY)]
        valid = [e["time"] for e in laps if e["valid"]]
        if valid:
            out.append(("Pace", f"Ø {format_time(_avg(valid))} · Bestzeit {format_time(min(valid))} "
                                f"· Streuung {max(valid) - min(valid):.2f}s", WHITE))
        by_comp: dict[str, list[float]] = {}
        for e in laps:
            by_comp.setdefault(e["compound"], []).append(e["wear_delta"])
        for comp, deltas in by_comp.items():
            per_lap = _avg(deltas) or 0.0
            if per_lap <= 0:
                continue
            life = 0.75 / per_lap   # tyres fall off the cliff at ~75% wear
            name = COMPOUNDS[comp].name if comp in COMPOUNDS else comp
            col = GREEN if life >= n else YELLOW if life >= n / 2 else RED
            stops = 0 if life >= n else int(n / life)
            out.append((f"Reifen {name}", f"{per_lap * 100:.1f}% pro Runde -> hält ~{life:.0f} Rd. "
                                          f"({'kein Stopp nötig' if stops == 0 else f'{stops} Stopp(s) im Rennen'})",
                        col))
        fuel = [e["fuel_used"] for e in laps if e["fuel_used"] is not None and e["fuel_used"] > 0]
        if fuel:
            per_lap = _avg(fuel) or 0.0
            nominal = self.car.fuel_per_lap
            need_laps = per_lap * n / nominal if nominal > 0 else n
            margin = round((need_laps - n) * 2 + 1) / 2   # +0.5 lap safety
            out.append(("Sprit", f"{per_lap:.2f} kg pro Runde -> Rennen braucht {per_lap * n:.0f} kg · "
                                 f"Empfehlung: Renndistanz {margin:+.1f} Rd.", CYAN))
        plank = [e["plank_delta"] for e in laps]
        if plank:
            per_lap = _avg(plank) or 0.0
            race = per_lap * n
            col = RED if race > PLANK_LIMIT_MM else YELLOW if race > 0.8 * PLANK_LIMIT_MM else GREEN
            verdict = "DISQUALIFIKATION droht - Bodenfreiheit erhöhen!" if race > PLANK_LIMIT_MM else \
                "knapp - Randsteine meiden oder höher fahren" if race > 0.8 * PLANK_LIMIT_MM else \
                "sicher - Bodenfreiheit könnte tiefer" if race < 0.55 * PLANK_LIMIT_MM else "im grünen Bereich"
            out.append(("Planke", f"{per_lap:.3f} mm pro Runde -> {race:.2f} mm im Rennen ({verdict})", col))
        vmax = max((e["vmax"] for e in laps), default=0.0)
        if vmax > 0:
            v, unit = speed_in(vmax, self.game.settings.units)
            out.append(("Topspeed", f"{v:.0f} {unit}", WHITE))
        return out

    # ------------------------------------------------------------------ input / loop
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.scroll = max(0, self.scroll - 1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.scroll = max(0, min(len(self.log) - self.VISIBLE_ROWS, self.scroll + 1))
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.on_continue()
        elif event.key == pygame.K_g:
            game = self.game
            team = self.car.perf if self.car.perf.name else None
            game.open_garage(self.car.track.definition.key, team, lambda: setattr(game, "state", self))
        elif event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, CYAN, (60, 30, 8, 60))
        draw_text(screen, "DATENANALYSE · FREIES TRAINING", f.big, WHITE, (84, 26))
        draw_text(screen, f"{self.car.track.name} · {len(self.log)} Runden · Hochrechnung auf {self.race_laps} "
                          f"Rennrunden", f.small, GREY, (86, 76))
        self._draw_table(screen)
        self._draw_chart(screen)
        self._draw_findings(screen)
        draw_text(screen, f"ENTER {self.continue_label} · G Garage (Setup anpassen) · Pfeile blättern · ESC Menü",
                  f.small, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 24), anchor="center")

    def _draw_table(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        box = pygame.Rect(40, 110, 640, 330)
        draw_panel(screen, box, PANEL, 215)
        cols = [("RD.", 14), ("ZEIT", 50), ("REIFEN", 150), ("VERSCHL.", 262), ("SPRIT", 352), ("PLANKE", 446),
                ("VMAX", 580)]
        for name, x in cols:
            draw_text(screen, name, f.tiny, GREY, (box.x + x, box.y + 12), shadow=False)
        if not self.log:
            draw_text(screen, "Keine gezeitete Runde gefahren.", f.small, GREY, (box.x + 14, box.y + 46),
                      shadow=False)
            return
        best = min((e["time"] for e in self.log if e["valid"]), default=None)
        rows = self.log[self.scroll:self.scroll + self.VISIBLE_ROWS]
        for k, e in enumerate(rows):
            y = box.y + 34 + k * 21
            if k % 2:
                pygame.draw.rect(screen, PANEL_LIGHT, (box.x + 6, y - 2, box.w - 12, 20), border_radius=3)
            tcol = (175, 80, 255) if e["time"] == best else WHITE if e["valid"] else (150, 150, 150)
            comp = COMPOUNDS.get(e["compound"])
            cells = [
                (str(e["lap"]) + (" P" if e["pit"] else ""), WHITE),
                (format_time(e["time"]) + ("" if e["valid"] else " x"), tcol),
                (f"{comp.name if comp else '-'} {e['wear'] * 100:.0f}%", comp.color if comp else WHITE),
                ("-" if e["wear_delta"] is None else f"+{e['wear_delta'] * 100:.1f}%", WHITE),
                ("-" if e["fuel_used"] is None else f"{e['fuel_used']:.2f} kg", WHITE),
                (f"{e['plank']:.2f} (+{e['plank_delta']:.3f})",
                 RED if e["plank"] > PLANK_LIMIT_MM else YELLOW if e["plank"] > 0.8 * PLANK_LIMIT_MM else WHITE),
                (f"{speed_in(e['vmax'], self.game.settings.units)[0]:.0f}", WHITE),
            ]
            for (text, col), (_, x) in zip(cells, cols):
                draw_text(screen, text, f.mono if x in (50, 262, 352) else f.small, col, (box.x + x, y),
                          shadow=False)

    def _draw_chart(self, screen: pygame.Surface) -> None:
        """Lap time (bars) and tyre wear (line) per lap."""
        f = self.game.fonts
        box = pygame.Rect(700, 110, 540, 330)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "RUNDENZEIT & REIFENVERSCHLEISS", f.tiny, GREY, (box.x + 14, box.y + 12), shadow=False)
        log = self.log[-24:]
        if len(log) < 2:
            draw_text(screen, "Mindestens 2 Runden für den Verlauf.", f.small, GREY, (box.x + 14, box.y + 46),
                      shadow=False)
            return
        plot = pygame.Rect(box.x + 50, box.y + 40, box.w - 70, box.h - 80)
        times = [e["time"] for e in log]
        lo, hi = min(times), max(times)
        if hi - lo < 0.5:
            hi = lo + 0.5
        step = plot.w / len(log)
        for k, e in enumerate(log):
            h = 12 + (plot.h - 12) * (1.0 - (e["time"] - lo) / (hi - lo))
            col = (90, 140, 220) if e["valid"] else (80, 80, 90)
            if e["pit"]:
                col = (160, 110, 40)
            pygame.draw.rect(screen, col, (plot.x + k * step + 2, plot.bottom - h, max(2, step - 4), h),
                             border_radius=2)
        pts = [(plot.x + (k + 0.5) * step, plot.bottom - plot.h * e["wear"]) for k, e in enumerate(log)]
        pygame.draw.lines(screen, YELLOW, False, pts, 2)
        for p in pts:
            pygame.draw.circle(screen, YELLOW, p, 3)
        draw_text(screen, format_time(lo)[2:], f.tiny, GREY, (plot.x - 6, plot.y), anchor="topright", shadow=False)
        draw_text(screen, format_time(hi)[2:], f.tiny, GREY, (plot.x - 6, plot.bottom - 12), anchor="topright",
                  shadow=False)
        draw_text(screen, "Balken = Rundenzeit (höher = schneller) · gelb = Reifenverschleiß · braun = Boxenrunde",
                  f.tiny, GREY, (box.x + 14, box.bottom - 24), shadow=False)

    def _draw_findings(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        box = pygame.Rect(40, 456, 1200, 220)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "RENNINGENIEUR · AUSWERTUNG", f.tiny, GREY, (box.x + 14, box.y + 12), shadow=False)
        for k, (title, text, col) in enumerate(self.findings[:7]):
            y = box.y + 36 + k * 26
            draw_text(screen, title, f.small_bold, col, (box.x + 14, y), shadow=False)
            draw_text(screen, text, f.small, WHITE, (box.x + 150, y), shadow=False)
