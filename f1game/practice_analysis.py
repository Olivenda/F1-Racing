# Copyright Olivenda (Oliver Petz) 2026
"""Everything the car recorded in free practice, in five tabs:

Übersicht      lap table, lap-time/tyre chart, the race engineer's summary
Sektoren       sector times per lap, ideal lap, gaps to the fastest car in every sector, speed trap, time sheet
Fahrstil       throttle/brake/coasting share, slides, under-/oversteer, lock-ups, kerbs, off-track, smoothness
Setup & Auto   the setup that was run, what the data says about it, damage, plank, fuel
Rennstrategie  0/1/2-stop plans simulated over the race distance with the measured pace, wear and fuel
"""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, Callable

import pygame

from .car import PLANK_LIMIT_MM
from .car_setup import CarSetup
from .i18n import tr
from .pitlane import SPEED_LIMIT
from .race_control import PUNCTURE_WEAR
from .settings import (CYAN, GREEN, GREY, PANEL, PANEL_LIGHT, PURPLE, PX_PER_S_TO_KMH, SCREEN_HEIGHT, SCREEN_WIDTH,
                       WHITE, YELLOW)
from .tyres import COMPOUND_ORDER, COMPOUNDS
from .user_settings import speed_in
from .utils import draw_panel, draw_text, format_time

if TYPE_CHECKING:
    from .game import Game
    from .player_car import Player_Car
    from .sessions import Session

RED = (255, 90, 90)
TABS = ["Übersicht", "Sektoren", "Fahrstil", "Setup & Auto", "Rennstrategie"]
FUEL_LAP_FACTOR = 0.0004     # lap time grows ~0.04% per kg of fuel on board


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _pct(part: float, total: float) -> float:
    return 100.0 * part / total if total > 0 else 0.0


class PracticeAnalysisScreen:

    VISIBLE_ROWS = 13

    def __init__(self, game: "Game", car: "Player_Car", race_laps: int, on_continue: Callable[[], None],
                 continue_label: str, session: "Session | None" = None) -> None:
        from .screens import _Background
        self.game = game
        self.car = car
        self.session = session
        self.log = car.lap_log
        self.race_laps = max(1, race_laps)
        self.on_continue = on_continue
        self.continue_label = continue_label
        self.bg = _Background()
        self.t = 0.0
        self.tab = 0
        self.scroll = 0
        self.findings = self._analyse()
        self.style = self._style()
        self.setup_notes = self._setup_notes()
        self.strategies = self._strategies()

    # ================================================================== data
    def _clean(self) -> list[dict]:
        """Laps that say something about race pace: no pit stop, not an out-lap."""
        return [e for e in self.log if not e["pit"] and e["wear_delta"] is not None and e["lap"] > 1] or \
            [e for e in self.log if not e["pit"] and e["wear_delta"] is not None]

    def _wear_rates(self) -> dict[str, float]:
        out: dict[str, list[float]] = {}
        for e in self._clean():
            if e["wear_delta"] and e["wear_delta"] > 0:
                out.setdefault(e["compound"], []).append(e["wear_delta"])
        return {k: sum(v) / len(v) for k, v in out.items()}

    def _field_sector_best(self) -> list[tuple[float, str] | None]:
        best: list[tuple[float, str] | None] = [None, None, None]
        if self.session is None:
            return best
        for c in self.session.cars:
            for k, t in enumerate(c.best_sectors):
                if t is not None and (best[k] is None or t < best[k][0]):
                    best[k] = (t, c.short)
        return best

    def _fuel_margin(self) -> float:
        fuel = [e["fuel_used"] for e in self._clean() if e["fuel_used"] is not None and e["fuel_used"] > 0]
        nominal = self.car.fuel_per_lap
        per_lap = _avg(fuel) or nominal
        need_laps = per_lap * self.race_laps / nominal if nominal > 0 else self.race_laps
        return round((need_laps - self.race_laps) * 2 + 1) / 2   # +0.5 lap safety

    def _plank_race(self) -> float | None:
        plank = [e["plank_delta"] for e in self._clean()]
        return (_avg(plank) or 0.0) * self.race_laps if plank else None

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
        if self.session is not None and self.car.best_lap is not None:
            order = sorted((c for c in self.session.cars if c.best_lap is not None), key=lambda c: c.best_lap)
            if self.car in order:
                pos = order.index(self.car) + 1
                gap = self.car.best_lap - order[0].best_lap
                out.append(("Position", f"P{pos} von {len(order)}" + (f" · +{gap:.3f}s auf {order[0].short}"
                                                                       if pos > 1 else " · Tagesbestzeit!"),
                            GREEN if pos <= 3 else WHITE))
        for comp, per_lap in self._wear_rates().items():
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
            out.append(("Sprit", f"{per_lap:.2f} kg pro Runde -> Rennen braucht {per_lap * n:.0f} kg · "
                                 f"Empfehlung: Renndistanz {self._fuel_margin():+.1f} Rd.", CYAN))
        race = self._plank_race()
        if race is not None:
            col = RED if race > PLANK_LIMIT_MM else YELLOW if race > 0.8 * PLANK_LIMIT_MM else GREEN
            verdict = "DISQUALIFIKATION droht - Bodenfreiheit erhöhen!" if race > PLANK_LIMIT_MM else \
                "knapp - Randsteine meiden oder höher fahren" if race > 0.8 * PLANK_LIMIT_MM else \
                "sicher - Bodenfreiheit könnte tiefer" if race < 0.55 * PLANK_LIMIT_MM else "im grünen Bereich"
            out.append(("Planke", f"{race / n:.3f} mm pro Runde -> {race:.2f} mm im Rennen ({verdict})", col))
        vmax = max((e["vmax"] for e in laps), default=0.0)
        if vmax > 0:
            v, unit = speed_in(vmax, self.game.settings.units)
            out.append(("Topspeed", f"{v:.0f} {unit}", WHITE))
        return out

    def _style(self) -> dict[str, float]:
        """Driving style summed over all timed laps."""
        laps = [e for e in self.log if e.get("t")]
        keys = ("t", "full", "part", "brake_t", "coast", "grass_t", "slide_t", "under_t", "over_t", "lock_t",
                "spin_t", "kerb_t", "straight_t", "steer_work", "shifts")
        total: dict[str, float] = {k: float(sum(e.get(k, 0.0) for e in laps)) for k in keys}
        total["laps"] = float(len(laps))
        return total

    def _setup_notes(self) -> list[tuple[str, tuple[int, int, int]]]:
        """What the telemetry says about the setup, with concrete changes."""
        st, setup = self.style, self.car.setup or CarSetup()
        t = st["t"]
        if t <= 0:
            return [("Noch keine Daten - fahre ein paar Runden.", GREY)]
        notes: list[tuple[str, tuple[int, int, int]]] = []
        under, over = _pct(st["under_t"], t), _pct(st["over_t"], t)
        if under > 6.0 and under > over * 1.5:
            notes.append((f"Untersteuern ({under:.1f}% der Zeit): Frontflügel +1/+2 oder Heckflügel -1, Federung "
                          "weicher.", YELLOW))
        elif over > 4.0 and over > under * 1.5:
            notes.append((f"Übersteuern ({over:.1f}% der Zeit): Heckflügel +1 oder Frontflügel -1, früher und "
                          "sanfter ans Gas.", YELLOW))
        else:
            notes.append(("Balance passt: kaum Unter- oder Übersteuern.", GREEN))
        if self.session is not None and self.car.vmax > 0:
            speeds = sorted((c.vmax for c in self.session.cars if c.vmax > 0), reverse=True)
            rank = sum(1 for v in speeds if v > self.car.vmax) + 1
            if rank > len(speeds) * 0.7:
                notes.append((f"Topspeed nur Platz {rank}/{len(speeds)}: weniger Heckflügel oder längere "
                              "Übersetzung.", YELLOW))
            elif rank <= 2 and under + over > 5:
                notes.append(("Sehr schnell auf der Geraden, aber wenig Grip: mehr Flügel kostet kaum Zeit.", YELLOW))
        wear = self._wear_rates()
        if wear and 0.75 / max(wear.values()) < self.race_laps / 2:
            notes.append(("Hoher Reifenverschleiß: Reifendruck +1 oder Federung weicher, weniger rutschen.", YELLOW))
        race = self._plank_race()
        if race is not None:
            if race > PLANK_LIMIT_MM:
                need = 1 + int((race - PLANK_LIMIT_MM) / 0.12)
                notes.append((f"Planke {race:.2f} mm im Rennen: Bodenfreiheit um mind. +{need} erhöhen!", RED))
            elif race < 0.45 and setup.ride_height > -5:
                notes.append(("Planke hat Reserve: Bodenfreiheit -1 bringt mehr Abtrieb.", GREEN))
        if _pct(st["kerb_t"], t) > 6:
            notes.append(("Viel auf den Randsteinen: schadet der Planke und dem Unterboden.", YELLOW))
        if self.car.damage.total > 0.05:
            parts = ", ".join(f"{n} {v * 100:.0f}%" for n, v in self.car.damage.parts())
            notes.append((f"Schäden am Auto: {parts}", RED))
        notes.append((f"Sprit fürs Rennen: Renndistanz {self._fuel_margin():+.1f} Runden.", CYAN))
        return notes

    # ------------------------------------------------------------------ race strategy
    def _pit_loss(self) -> float:
        pit = self.car.track.pit
        if pit is None:
            return 25.0
        race_speed = max(100.0, self.car.top_speed * 0.75)
        return pit.length / SPEED_LIMIT - pit.length / race_speed + 2.4 + 2.0

    @staticmethod
    def _splits(n: int, stints: int) -> list[tuple[int, ...]]:
        """Ways to cut n laps into `stints` parts (each at least one lap), thinned out for long races."""
        if stints == 1:
            return [(n,)]
        out = sorted({tuple(b - a for a, b in zip((0,) + cut, cut + (n,)))
                      for cut in itertools.combinations(range(1, n), stints - 1)})
        return out[::max(1, len(out) // 40)]

    def _strategies(self) -> list[tuple[float, list[tuple[str, int]]]]:
        """Every 0/1/2-stop plan over the race distance with the measured pace, wear rates and fuel weight."""
        laps = self._clean()
        valid = sorted(e["time"] for e in laps if e["valid"]) or sorted(e["time"] for e in laps)
        if not valid:
            return []
        n = self.race_laps
        base = valid[len(valid) // 3]                    # a representative quick lap, not the one-off best
        ref = laps[0]["compound"] if laps[0]["compound"] in COMPOUNDS else "medium"
        rates = self._wear_rates()
        measured = next(iter(rates.items()), None)
        wet = self.car.track.wetness > 0.22
        options = ["inter", "wet"] if wet else COMPOUND_ORDER
        fuel_kg = self.car.fuel_per_lap * n
        pit_loss = self._pit_loss()
        # pace of fresh softs, from the compound the laps were done on (avg fuel load in practice)
        base_soft = base / (1.0 + 0.35 * (1.0 - math.sqrt(COMPOUNDS[ref].grip / COMPOUNDS["soft"].grip)))

        def rate(c: str) -> float:
            if c in rates:
                return rates[c]
            if measured is not None and measured[0] in COMPOUNDS:
                return measured[1] * COMPOUNDS[measured[0]].life / COMPOUNDS[c].life
            return 0.85 * base / COMPOUNDS[c].life

        def stint(c: str, start: int, length: int) -> float | None:
            total, wear = 0.0, 0.0
            for k in range(length):
                wear += rate(c)
                if wear > 0.97:
                    return None
                cliff = max(0.0, wear - 0.70) / 0.30
                rel = COMPOUNDS[c].grip / COMPOUNDS["soft"].grip * (1.0 - 0.12 * wear - 0.25 * cliff * cliff)
                lap = base_soft * (1.0 + 0.35 * (1.0 - math.sqrt(max(0.05, rel))))
                lap *= 1.0 + FUEL_LAP_FACTOR * (fuel_kg * (1.0 - (start + k) / n) - fuel_kg / 2)
                if wear > PUNCTURE_WEAR:
                    lap += 30.0 * (wear - PUNCTURE_WEAR) / (1.0 - PUNCTURE_WEAR)
                total += lap
            return total

        plans: dict[tuple, float] = {}
        for stops in range(0, min(3, n)):
            for combo in itertools.product(options, repeat=stops + 1):
                for split in self._splits(n, stops + 1):
                    total, start = stops * pit_loss, 0
                    for c, length in zip(combo, split):
                        part = stint(c, start, length)
                        if part is None:
                            break
                        total += part
                        start += length
                    else:
                        plans[tuple(zip(combo, split))] = total
        ranked = sorted(plans.items(), key=lambda kv: kv[1])[:8]
        return [(total, list(plan)) for plan, total in ranked]

    # ================================================================== input / loop
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d, pygame.K_TAB):
            self.tab = (self.tab + (-1 if event.key in (pygame.K_LEFT, pygame.K_a) else 1)) % len(TABS)
            self.scroll = 0
        elif event.key in (pygame.K_UP, pygame.K_w):
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
        pygame.draw.rect(screen, CYAN, (60, 22, 8, 54))
        draw_text(screen, "DATENANALYSE · FREIES TRAINING", f.big, WHITE, (84, 18))
        draw_text(screen, f"{self.car.track.name} · {len(self.log)} Runden · Hochrechnung auf {self.race_laps} "
                          f"Rennrunden", f.small, GREY, (86, 66))
        x = 40
        for k, name in enumerate(TABS):
            w = f.small_bold.size(name)[0] + 30
            active = k == self.tab
            pygame.draw.rect(screen, CYAN if active else (40, 42, 52), (x, 94, w, 30), border_radius=6)
            draw_text(screen, name, f.small_bold, (10, 12, 16) if active else WHITE, (x + w // 2, 109),
                      anchor="center", shadow=False)
            x += w + 8
        (self._tab_overview, self._tab_sectors, self._tab_style, self._tab_setup, self._tab_strategy)[self.tab](screen)
        draw_text(screen, f"Links/rechts Tabs · ENTER {self.continue_label} · G Garage · Pfeile blättern · ESC Menü",
                  f.small, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 18), anchor="center")

    def _lines(self, screen: pygame.Surface, box: pygame.Rect, title: str,
               lines: list[tuple[str, str, tuple[int, int, int]]], label_w: int = 150) -> None:
        f = self.game.fonts
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, title, f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
        for k, (label, text, col) in enumerate(lines[:max(1, (box.h - 36) // 25)]):
            y = box.y + 32 + k * 25
            if label:
                draw_text(screen, label, f.small_bold, col, (box.x + 14, y), shadow=False)
            draw_text(screen, text, f.small, WHITE if label else col, (box.x + 14 + label_w, y), shadow=False)

    # ------------------------------------------------------------------ tab: overview
    def _tab_overview(self, screen: pygame.Surface) -> None:
        self._draw_table(screen)
        self._draw_chart(screen)
        self._lines(screen, pygame.Rect(40, 466, 1200, 214), "RENNINGENIEUR · AUSWERTUNG", self.findings)

    def _draw_table(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        box = pygame.Rect(40, 134, 640, 322)
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
        for k, e in enumerate(self.log[self.scroll:self.scroll + self.VISIBLE_ROWS]):
            y = box.y + 34 + k * 21
            if k % 2:
                pygame.draw.rect(screen, PANEL_LIGHT, (box.x + 6, y - 2, box.w - 12, 20), border_radius=3)
            tcol = PURPLE if e["time"] == best else WHITE if e["valid"] else (150, 150, 150)
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
        f = self.game.fonts
        box = pygame.Rect(700, 134, 540, 322)
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
            col = (160, 110, 40) if e["pit"] else (90, 140, 220) if e["valid"] else (80, 80, 90)
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

    # ------------------------------------------------------------------ tab: sectors
    def _tab_sectors(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        units = self.game.settings.units
        box = pygame.Rect(40, 134, 760, 402)
        draw_panel(screen, box, PANEL, 215)
        cols = [("RD.", 14), ("SEKTOR 1", 70), ("SEKTOR 2", 180), ("SEKTOR 3", 290), ("RUNDE", 400),
                ("KURVEN-MIN. S1/S2/S3", 530)]
        for name, x in cols:
            draw_text(screen, name, f.tiny, GREY, (box.x + x, box.y + 12), shadow=False)
        rows = [e for e in self.log if len(e.get("sectors", [])) == 3]
        mine = [min((e["sectors"][k] for e in rows if e["valid"]), default=None) for k in range(3)]
        field = self._field_sector_best()
        for k, e in enumerate(rows[self.scroll:self.scroll + 15]):
            y = box.y + 34 + k * 23
            if k % 2:
                pygame.draw.rect(screen, PANEL_LIGHT, (box.x + 6, y - 2, box.w - 12, 22), border_radius=3)
            draw_text(screen, str(e["lap"]), f.small, WHITE, (box.x + 14, y), shadow=False)
            for s in range(3):
                t = e["sectors"][s]
                col = PURPLE if field[s] and abs(t - field[s][0]) < 1e-6 else \
                    GREEN if mine[s] is not None and abs(t - mine[s]) < 1e-6 else WHITE
                draw_text(screen, f"{t:6.3f}", f.mono, col if e["valid"] else (150, 150, 150),
                          (box.x + 70 + s * 110, y), shadow=False)
            draw_text(screen, format_time(e["time"]), f.mono, WHITE if e["valid"] else (150, 150, 150),
                      (box.x + 400, y), shadow=False)
            mins = e.get("sector_min", [999, 999, 999])
            text = " / ".join("-" if m >= 999 else f"{speed_in(m, units)[0]:.0f}" for m in mins)
            draw_text(screen, text, f.small, WHITE, (box.x + 530, y), shadow=False)
        if not rows:
            draw_text(screen, "Keine vollständige Runde mit Sektorzeiten.", f.small, GREY, (box.x + 14, box.y + 46),
                      shadow=False)
        lines: list[tuple[str, str, tuple[int, int, int]]] = []
        if all(m is not None for m in mine):
            ideal, best = sum(mine), self.car.best_lap
            lines.append(("Ideale Runde", format_time(ideal) + (f"  (Bestzeit {format_time(best)} - "
                                                                 f"{best - ideal:.3f}s liegen noch drin)"
                                                                 if best else ""), CYAN))
        losses = []
        for s in range(3):
            if mine[s] is not None and field[s] is not None:
                gap = mine[s] - field[s][0]
                losses.append((gap, s))
                lines.append((f"Sektor {s + 1}", f"du {mine[s]:.3f} · Bestwert {field[s][0]:.3f} ({field[s][1]}) · "
                                                 f"{gap:+.3f}s",
                              PURPLE if gap <= 0 else GREEN if gap < 0.15 else YELLOW if gap < 0.4 else RED))
        if losses and max(losses)[0] > 0.05:
            gap, s = max(losses)
            lines.append(("Zeitverlust", f"am meisten in Sektor {s + 1} ({gap:.3f}s) - Bremspunkte und Kurvenausgang "
                                         "prüfen", YELLOW))
        self._lines(screen, pygame.Rect(40, 546, 1200, 134), "VERGLEICH MIT DEM FELD", lines, 140)
        rank_box = pygame.Rect(810, 134, 430, 402)
        draw_panel(screen, rank_box, PANEL, 215)
        draw_text(screen, "ZEITENLISTE TRAINING · SPEEDTRAP", f.tiny, GREY, (rank_box.x + 14, rank_box.y + 12),
                  shadow=False)
        if self.session is None:
            return
        order = sorted((c for c in self.session.cars if c.best_lap is not None), key=lambda c: c.best_lap)
        top = order[0].best_lap if order else 0.0
        for k, c in enumerate(order[:15]):
            y = rank_box.y + 34 + k * 23
            col = CYAN if c is self.car else WHITE
            draw_text(screen, f"{k + 1:>2}. {c.short}", f.small_bold, col, (rank_box.x + 14, y), shadow=False)
            draw_text(screen, format_time(c.best_lap), f.mono, col, (rank_box.x + 110, y), shadow=False)
            if k:
                draw_text(screen, f"+{c.best_lap - top:.3f}", f.mono, GREY, (rank_box.x + 220, y), shadow=False)
            v = speed_in(c.vmax * PX_PER_S_TO_KMH, units)[0]
            draw_text(screen, f"{v:.0f}", f.small, col, (rank_box.right - 16, y), anchor="topright", shadow=False)

    # ------------------------------------------------------------------ tab: driving style
    def _tab_style(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        st = self.style
        t = st["t"]
        box = pygame.Rect(40, 134, 600, 402)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "PEDALE & ZEITANTEILE (ALLE RUNDEN)", f.tiny, GREY, (box.x + 14, box.y + 12), shadow=False)
        bars = [("Vollgas", st["full"], GREEN), ("Teilgas", st["part"], (140, 200, 120)),
                ("Bremse", st["brake_t"], RED), ("Rollen", st["coast"], GREY), ("Gerade-Modus", st["straight_t"], CYAN)]
        for k, (label, value, col) in enumerate(bars):
            y = box.y + 40 + k * 34
            p = _pct(value, t)
            draw_text(screen, label, f.small_bold, WHITE, (box.x + 14, y), shadow=False)
            pygame.draw.rect(screen, (45, 45, 52), (box.x + 170, y + 4, 330, 14), border_radius=6)
            pygame.draw.rect(screen, col, (box.x + 170, y + 4, int(330 * min(1.0, p / 100)), 14), border_radius=6)
            draw_text(screen, f"{p:.1f}%", f.mono, WHITE, (box.right - 14, y + 2), anchor="topright", shadow=False)
        laps = max(1.0, st["laps"])
        events = [("Rutschen / Übersteuern", st["over_t"]), ("Untersteuern", st["under_t"]),
                  ("Blockierende Räder", st["lock_t"]), ("Durchdrehende Räder", st["spin_t"]),
                  ("Auf Randsteinen", st["kerb_t"]), ("Neben der Strecke", st["grass_t"])]
        for k, (label, value) in enumerate(events):
            y = box.y + 220 + k * 27
            col = GREEN if value / laps < 0.3 else YELLOW if value / laps < 1.0 else RED
            draw_text(screen, label, f.small, WHITE, (box.x + 14, y), shadow=False)
            draw_text(screen, f"{value:.1f}s gesamt · {value / laps:.2f}s pro Runde", f.small, col, (box.x + 260, y),
                      shadow=False)
        if self.car.manual_gearbox or st["shifts"]:
            draw_text(screen, f"Schaltvorgänge: {st['shifts'] / laps:.0f} pro Runde", f.small, GREY,
                      (box.x + 14, box.bottom - 24), shadow=False)
        tb = pygame.Rect(650, 134, 590, 402)
        draw_panel(screen, tb, PANEL, 215)
        cols = [("RD.", 14), ("VOLLGAS", 60), ("BREMSE", 150), ("ROLLEN", 230), ("RUTSCHEN", 310), ("NEBEN", 400),
                ("LENKUNRUHE", 470)]
        for name, x in cols:
            draw_text(screen, name, f.tiny, GREY, (tb.x + x, tb.y + 12), shadow=False)
        rows = [e for e in self.log if e.get("t")]
        for k, e in enumerate(rows[self.scroll:self.scroll + 15]):
            y = tb.y + 34 + k * 23
            lt = e["t"]
            cells = [str(e["lap"]), f"{_pct(e['full'], lt):.0f}%", f"{_pct(e['brake_t'], lt):.0f}%",
                     f"{_pct(e['coast'], lt):.0f}%", f"{e['slide_t']:.1f}s", f"{e['grass_t']:.1f}s",
                     f"{e['steer_work'] / max(1.0, lt):.2f}"]
            for text, (_, x) in zip(cells, cols):
                draw_text(screen, text, f.small, WHITE, (tb.x + x, y), shadow=False)
        self._lines(screen, pygame.Rect(40, 546, 1200, 134), "TIPPS ZUM FAHRSTIL", self._style_tips(), 0)

    def _style_tips(self) -> list[tuple[str, str, tuple[int, int, int]]]:
        st = self.style
        t = st["t"]
        if t <= 0:
            return [("", "Noch keine Daten.", GREY)]
        laps = max(1.0, st["laps"])
        tips = []
        if _pct(st["coast"], t) > 8:
            tips.append(("", f"{_pct(st['coast'], t):.0f}% Rollen ohne Gas und Bremse - später bremsen, früher wieder "
                             "ans Gas.", YELLOW))
        if st["lock_t"] / laps > 0.4:
            tips.append(("", "Blockierende Räder beim Bremsen: Bremse dosieren und früher bremsen - kostet Reifen "
                             "und Zeit.", YELLOW))
        if st["spin_t"] / laps > 0.4:
            tips.append(("", "Durchdrehende Räder am Kurvenausgang: sanfter ans Gas, Lenkung zuerst öffnen.", YELLOW))
        if st["grass_t"] / laps > 0.5:
            tips.append(("", "Zu oft neben der Strecke: Track Limits, Planke und Unterboden leiden.", RED))
        if st["steer_work"] / t > 1.2:
            tips.append(("", "Unruhige Lenkung: weniger Korrekturen, eine saubere Linie fahren.", YELLOW))
        if not tips:
            tips.append(("", "Sauberer Fahrstil - weiter so!", GREEN))
        return tips

    # ------------------------------------------------------------------ tab: setup & car
    def _tab_setup(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        box = pygame.Rect(40, 134, 420, 546)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "GEFAHRENES SETUP", f.tiny, GREY, (box.x + 14, box.y + 12), shadow=False)
        setup = self.car.setup or CarSetup()
        keys = CarSetup.keys()
        for k, key in enumerate(keys):
            label = CarSetup.LABELS[key][0]
            v = getattr(setup, key)
            y = box.y + 40 + k * 56
            draw_text(screen, label, f.small_bold, WHITE, (box.x + 14, y), shadow=False)
            sx, sw = box.x + 14, box.w - 90
            pygame.draw.line(screen, (70, 72, 82), (sx, y + 32), (sx + sw, y + 32), 4)
            pygame.draw.circle(screen, CYAN, (sx + sw * (v + 5) / 10, y + 32), 8)
            draw_text(screen, f"{v:+d}" if v else "0", f.medium, YELLOW, (box.right - 14, y + 20), anchor="topright")
        y = box.y + 40 + len(keys) * 56
        balance = "Front" if setup.balance > 0 else "Heck" if setup.balance < 0 else "neutral"
        draw_text(screen, f"Sprit beim Start: Renndistanz {setup.fuel / 2:+.1f} Rd.", f.small, WHITE, (box.x + 14, y),
                  shadow=False)
        draw_text(screen, f"Aero-Balance: {balance} ({setup.balance:+.1f})", f.small, WHITE, (box.x + 14, y + 26),
                  shadow=False)
        self._lines(screen, pygame.Rect(470, 134, 770, 330), "WAS DIE DATEN ÜBER DAS SETUP SAGEN",
                    [("", text, col) for text, col in self.setup_notes], 0)
        car = self.car
        tyres = car.tyres
        state = [("Schäden", ", ".join(f"{n} {v * 100:.0f}%" for n, v in car.damage.parts()) or "keine",
                  RED if car.damage.total > 0.05 else GREEN),
                 ("Planke", f"{car.plank_wear:.2f} mm abgenutzt (Limit {PLANK_LIMIT_MM:.1f} mm)",
                  YELLOW if car.plank_wear > 0.5 * PLANK_LIMIT_MM else GREEN),
                 ("Reifen", f"{tyres.compound.name} · {tyres.wear * 100:.0f}% abgefahren · {tyres.laps} Rd."
                  if tyres else "-", WHITE),
                 ("Sprit", f"{car.fuel:.1f} kg übrig · {car.fuel_per_lap:.2f} kg/Rd. nominal", WHITE),
                 ("Strecke", f"{car.track.wetness * 100:.0f}% nass", CYAN if car.track.wetness > 0.2 else WHITE)]
        self._lines(screen, pygame.Rect(470, 474, 770, 206), "ZUSTAND DES AUTOS NACH DEM TRAINING", state, 110)

    # ------------------------------------------------------------------ tab: race strategy
    def _tab_strategy(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        box = pygame.Rect(40, 134, 1200, 382)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, f"RENNSIMULATION · {self.race_laps} RUNDEN · Boxenstopp kostet ~{self._pit_loss():.1f}s",
                  f.tiny, GREY, (box.x + 14, box.y + 12), shadow=False)
        if not self.strategies:
            draw_text(screen, "Zu wenig Daten für eine Rennsimulation - fahre ein paar Runden am Stück.", f.small,
                      GREY, (box.x + 14, box.y + 46), shadow=False)
            return
        best = self.strategies[0][0]
        for k, (total, plan) in enumerate(self.strategies):
            y = box.y + 40 + k * 41
            if k == 0:
                pygame.draw.rect(screen, (30, 60, 40), (box.x + 8, y - 6, box.w - 16, 36), border_radius=6)
            stops = len(plan) - 1
            draw_text(screen, f"{k + 1}.", f.medium, WHITE, (box.x + 18, y), shadow=False)
            draw_text(screen, "kein Stopp" if stops == 0 else f"{stops} Stopp(s)", f.small_bold, GREY,
                      (box.x + 60, y + 4), shadow=False)
            x = box.x + 180
            for comp, length in plan:
                c = COMPOUNDS[comp]
                w = max(44, int(560 * length / self.race_laps))
                pygame.draw.rect(screen, c.color, (x, y + 2, w - 4, 22), border_radius=5)
                draw_text(screen, f"{c.letter} {length}", f.small_bold, (15, 15, 18), (x + 8, y + 3), shadow=False)
                x += w
            draw_text(screen, format_time(total), f.mono, WHITE, (box.x + 800, y + 4), shadow=False)
            draw_text(screen, "schnellste" if k == 0 else f"+{total - best:.1f}s", f.mono,
                      GREEN if k == 0 else GREY, (box.x + 960, y + 4), shadow=False)
        plan = self.strategies[0][1]
        # translated piece by piece: the joined list would not match a translation template as a whole
        stops_txt = ", ".join(tr(f"Runde {sum(length for _, length in plan[:k + 1])} -> {COMPOUNDS[c].name}")
                              for k, (c, _) in enumerate(plan[1:]))
        lines = [("Empfehlung", f"Start auf {COMPOUNDS[plan[0][0]].name}" +
                  (f" · Stopp: {stops_txt}" if stops_txt else " · durchfahren"), GREEN),
                 ("Sprit", f"Renndistanz {self._fuel_margin():+.1f} Runden tanken (Garage)", CYAN)]
        race = self._plank_race()
        if race is not None:
            lines.append(("Planke", f"~{race:.2f} mm im Rennen (Limit {PLANK_LIMIT_MM:.1f} mm)",
                          RED if race > PLANK_LIMIT_MM else GREEN))
        w = getattr(self.session, "weather", None)
        if w is not None and w.mode != "dry":
            lines.append(("Wetter", "Wechselhaft gemeldet - Intermediates bereithalten, die Strategie kann kippen."
                          if w.mode == "dynamic" else "Regenrennen erwartet - Wets/Intermediates.", CYAN))
        self._lines(screen, pygame.Rect(40, 526, 1200, 154), "STRATEGIE", lines, 140)
