# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import os
import subprocess
from typing import TYPE_CHECKING

import pygame

from .settings import (CYAN, F1_RED, GREEN, GREY, ORANGE, PANEL, PANEL_LIGHT, PURPLE, PX_PER_S_TO_KMH,
                       SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, YELLOW)
from .car import PLANK_LIMIT_MM
from .flags import FLAG_COLORS, FLAG_NAMES, car_flag, hazard_ahead, led_board
from .tyres import COMPOUNDS
from .i18n import tr
from .user_settings import speed_in
from .utils import draw_panel, draw_text, format_gap, format_time

if TYPE_CHECKING:
    from .ai_car import AI_Car
    from .neural import NeuralNetwork
    from .car import Car
    from .sessions import RaceSession, Session


class Fonts:
    def __init__(self) -> None:
        sans = "helveticaneue,helvetica,arial,dejavusans"
        mono = "menlo,consolas,dejavusansmono,couriernew"
        self.huge = pygame.font.SysFont(sans, 76, bold=True)
        self.big = pygame.font.SysFont(sans, 44, bold=True)
        self.large = pygame.font.SysFont(sans, 30, bold=True)
        self.medium = pygame.font.SysFont(sans, 21, bold=True)
        self.small = pygame.font.SysFont(sans, 17)
        self.small_bold = pygame.font.SysFont(sans, 17, bold=True)
        self.tiny = pygame.font.SysFont(sans, 13, bold=True)
        self.mono = pygame.font.SysFont(mono, 15, bold=True)
        self.mono_big = pygame.font.SysFont(mono, 24, bold=True)


class HUD:
    TOWER_ROW_H = 21

    def __init__(self, fonts: Fonts) -> None:
        self.f = fonts
        self.units = "kmh"
        self._minimap_cache: dict[str, pygame.Surface] = {}
        self._ram_mb = 0.0
        self._ram_checked = 0
        self._sog_label: pygame.Surface | None = None
        self._trend: dict[int, tuple] = {}
        self.style = "modern"

    def clear_caches(self) -> None:
        self._minimap_cache.clear()
        self._sog_label = None

    def ram_mb(self) -> float:
        now = pygame.time.get_ticks()
        if now - self._ram_checked > 2000:
            self._ram_checked = now
            try:
                out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True,
                                     text=True, timeout=1).stdout
                self._ram_mb = int(out.strip()) / 1024
            except (OSError, ValueError, subprocess.SubprocessError):
                self._ram_mb = 0.0
        return self._ram_mb

    def draw_session(self, screen: pygame.Surface, s: "Session") -> None:
        self.units = s.game.settings.units
        self.style = getattr(s.game.settings, "hud_style", "modern")
        assist = getattr(s.game.settings, "hud_assist", "full")
        standings = s.standings()
        cockpit = s.view3d and s.r3d.cockpit
        self._info_panel(screen, s, standings)
        self._timing_tower(screen, s, standings)
        self._minimap(screen, s)
        if not cockpit:     # in the cockpit the steering wheel display shows speed, gear and revs
            if self.style == "modern":
                self._dashboard(screen, s.focus)
            else:
                self._speedo(screen, s.focus)
        if assist == "full" and s.view3d and s.r3d.cam.kind in ("onboard", "chase"):
            self._spotter(screen, s)
        self._engineer(screen, s)
        self._pit_overlay(screen, s.focus)
        if s.kind == "race":
            self._race_gaps(screen, s, standings)
            self._lights(screen, s)
        else:
            self._delta_panel(screen, s)
        self._sectors(screen, s)
        self._weather(screen, s)
        self._neutralization(screen, s)
        if assist != "off":
            self._flag_display(screen, s, assist == "full")
        self._messages(screen, s)
        self._feed(screen, s)
        self._race_control(screen, s)
        self._footer(screen, s)

    def _info_panel(self, screen: pygame.Surface, s: "Session", standings: list["Car"]) -> None:
        f = self.f
        p = s.focus
        draw_panel(screen, (16, 16, 300, 128))
        pygame.draw.rect(screen, F1_RED, (16, 16, 6, 128), border_top_left_radius=8, border_bottom_left_radius=8)
        title = f"{s.title.upper()}  ·  {s.track.name.upper()}"
        if s.spectator:
            title = f"ZUSCHAUER  ·  {p.name.upper()}"
        draw_text(screen, title[:44], f.tiny, GREY, (32, 24))
        pos = standings.index(p) + 1
        draw_text(screen, "POS", f.tiny, GREY, (32, 46))
        draw_text(screen, f"{pos}", f.big, WHITE, (32, 56))
        draw_text(screen, f"/{len(s.cars)}", f.medium, GREY, (32 + f.big.size(str(pos))[0] + 2, 76))

        draw_text(screen, "RUNDE", f.tiny, GREY, (140, 46))
        if s.kind == "race":
            lap_txt = f"{min(p.laps_done + 1, s.total_laps)}/{s.total_laps}"
            if p.session_done:
                lap_txt = "DSQ" if p.dsq else "DNF" if p.dnf else "ZIEL"
        elif s.kind == "qualifying":
            lap_txt = "IN" if p.session_done else ("OUT" if not p.timing_started else
                                                    f"{min(p.laps_done + 1, 3)}/3")
        else:
            lap_txt = str(p.laps_done + 1) if p.timing_started else "OUT"
        draw_text(screen, lap_txt, f.large, WHITE, (140, 60))

        cur = p.current_lap_time(s.time) if not p.session_done else None
        draw_text(screen, "AKTUELL", f.tiny, GREY, (32, 106))
        draw_text(screen, format_time(cur), f.mono, WHITE, (32, 120))
        draw_text(screen, "BESTE", f.tiny, GREY, (140, 106))
        best_col = PURPLE if s.fastest_lap and p.best_lap == s.fastest_lap[0] else GREEN
        draw_text(screen, format_time(p.best_lap), f.mono, best_col if p.best_lap else WHITE, (140, 120))
        draw_text(screen, "LETZTE", f.tiny, GREY, (232, 106))
        draw_text(screen, format_time(p.last_lap)[2:] if p.last_lap else "--", f.mono, WHITE, (232, 120))

    @classmethod
    def tower_row_h(cls, n: int) -> int:
        return cls.TOWER_ROW_H if n <= 14 else 16

    def _timing_tower(self, screen: pygame.Surface, s: "Session", standings: list["Car"]) -> None:
        f = self.f
        rh = self.tower_row_h(len(standings))
        compact = rh < self.TOWER_ROW_H
        name_font = f.tiny if compact else f.small_bold
        val_font = f.tiny if compact else f.mono
        x, y = 16, 156
        h = 28 + rh * len(standings)
        draw_panel(screen, (x, y, 210, h))
        header = "ABSTAND ZUM FÜHRENDEN" if s.kind == "race" else "BESTZEIT"
        draw_text(screen, header, f.tiny, GREY, (x + 10, y + 8), shadow=False)
        leader = standings[0]
        best = leader.best_lap
        ty = 0 if compact else 1
        for i, car in enumerate(standings):
            ry = y + 26 + i * rh
            if car.is_player or (s.spectator and car is s.focus):
                pygame.draw.rect(screen, (0, 90, 120), (x + 3, ry - 1, 204, rh - 1), border_radius=4)
            elif car is s.focus:
                pygame.draw.rect(screen, (60, 60, 75), (x + 3, ry - 1, 204, rh - 1), border_radius=4)
            draw_text(screen, f"{i + 1:>2}", val_font, WHITE, (x + 8, ry + ty), shadow=False)
            pygame.draw.rect(screen, car.color, (x + 38, ry + 2, 4, rh - 5))
            rival = car.name == s.config.rival
            draw_text(screen, car.short, name_font, CYAN if car.is_player else (255, 90, 80) if rival else WHITE,
                      (x + 48, ry + ty), shadow=False)
            if car.tyres is not None:
                comp = car.tyres.compound
                r = 6 if compact else 7
                cy = ry + rh // 2 - 1
                pygame.draw.circle(screen, (20, 20, 22), (x + 98, cy), r)
                pygame.draw.circle(screen, comp.color, (x + 98, cy), r, 2)
                if not compact:
                    lt = f.tiny.render(comp.letter, True, comp.color)
                    screen.blit(lt, lt.get_rect(center=(x + 98, cy)))
            pen = car.penalty_unserved if car.finish_time is None else 0.0
            if pen > 0:
                draw_text(screen, f"+{pen:.0f}", f.tiny, ORANGE, (x + 108, ry + ty + 1), shadow=False)
            if car.dnf:
                draw_text(screen, "DSQ" if car.dsq else "DNF", val_font, (255, 80, 80), (x + 200, ry + ty), anchor="topright", shadow=False)
                continue
            if car.in_pit:
                draw_text(screen, "BOX", val_font, ORANGE, (x + 200, ry + ty), anchor="topright", shadow=False)
                continue
            if s.kind == "race":
                val = s.leader_gap(car, leader)
                col = WHITE
                if car.finish_time is not None:
                    val = ("FIN " + val) if i > 0 else "FIN"
                    col = (255, 215, 0) if i < 3 else (200, 200, 200)
            else:
                if car.best_lap is None:
                    val, col = "--", GREY
                elif i == 0:
                    val, col = format_time(car.best_lap), PURPLE
                else:
                    val, col = f"+{car.best_lap - (best or 0):.3f}", WHITE
                if s.kind == "qualifying" and car.session_done:
                    col = (150, 150, 150) if i > 0 else col
            draw_text(screen, val, val_font, col, (x + 200, ry + ty), anchor="topright", shadow=False)

    def _sectors(self, screen: pygame.Surface, s: "Session") -> None:
        car = s.focus
        if not car.timing_started or car.session_done or (s.kind == "race" and not getattr(s, "race_started", True)):
            return
        if s.kind == "race" and getattr(s, "go_timer", 0) > 0:
            return
        f = self.f
        w, gap = 104, 6
        x0 = SCREEN_WIDTH // 2 - (3 * w + 2 * gap) // 2
        for k in range(3):
            rect = pygame.Rect(x0 + k * (w + gap), 16, w, 26)
            if k < len(car.sectors):
                t = car.sectors[k]
                best = s.best_sectors[k]
                col = PURPLE if best is not None and t <= best + 1e-6 else \
                    GREEN if car.best_sectors[k] is not None and t <= car.best_sectors[k] + 1e-6 else YELLOW
                text_col = WHITE
            elif k < len(car.last_sectors):
                t, col, text_col = car.last_sectors[k], (60, 62, 72), (170, 170, 180)
            else:
                t, col, text_col = None, (45, 47, 55), GREY
            yellow = k in getattr(getattr(s, "rc", None), "yellow", {})
            draw_panel(screen, rect, (90, 75, 0) if yellow else (14, 15, 20), 200, radius=5)
            pygame.draw.rect(screen, col, (rect.x, rect.bottom - 4, rect.w, 4), border_radius=2)
            label = f"S{k + 1}  {t:.3f}" if t is not None else f"S{k + 1}"
            draw_text(screen, label, f.tiny, text_col, (rect.centerx, rect.y + 10), anchor="center", shadow=False)

    def _weather(self, screen: pygame.Surface, s: "Session") -> None:
        w = getattr(s, "weather", None)
        if w is None or (w.mode == "dry" and w.wetness < 0.01):
            return
        f = self.f
        x, y, bw, bh = 812, 14, 200, 50
        draw_panel(screen, (x, y, bw, bh))
        # cloud with rain drops / sun
        cx, cy = x + 24, y + 22
        if w.rain > 0.05 or w.wetness > 0.2:
            for dx, r in ((-7, 7), (0, 9), (8, 7)):
                pygame.draw.circle(screen, (170, 178, 192), (cx + dx, cy - 2), r)
            for k in range(min(4, 1 + int(w.rain * 4))):
                px = cx - 9 + k * 6
                pygame.draw.line(screen, (90, 150, 255), (px, cy + 9), (px - 2, cy + 15), 2)
        else:
            pygame.draw.circle(screen, (255, 200, 40), (cx, cy), 8)
        col = (90, 150, 255) if w.wetness > 0.22 else WHITE
        draw_text(screen, w.label(), f.small_bold, col, (x + 46, y + 6), shadow=False)
        sub = f"Strecke {w.wetness * 100:.0f}% nass"
        eta = w.eta_rain()
        if eta is not None:
            sub = f"Regen in ~{eta:.0f}s"
        else:
            dry = w.eta_dry()
            if dry is not None and dry < 90:
                sub += f" · Ende ~{dry:.0f}s"
        draw_text(screen, sub, f.tiny, (180, 180, 190), (x + 46, y + 28), shadow=False)

    def _neutralization(self, screen: pygame.Surface, s: "Session") -> None:
        rc = getattr(s, "rc", None)
        if rc is None or not rc.active:
            return
        f = self.f
        if rc.mode == "SC":
            text = {"out": "SAFETY CAR", "in": "SAFETY CAR IN THIS LAP", "restart": "RESTART AN DER ZIELLINIE"}[rc.phase]
        else:
            text = f"VIRTUAL SAFETY CAR  {max(0.0, rc.until - s.time):.0f}s"
        rect = pygame.Rect(SCREEN_WIDTH // 2 - 165, 48, 330, 30)
        blink = int(pygame.time.get_ticks() / 400) % 2
        pygame.draw.rect(screen, (255, 200, 30) if blink else (200, 150, 0), rect, border_radius=6)
        draw_text(screen, text, f.small_bold, (20, 15, 0), rect.center, anchor="center", shadow=False)

    def _minimap(self, screen: pygame.Surface, s: "Session") -> None:
        box = pygame.Rect(SCREEN_WIDTH - 256, 16, 240, 170)
        key = s.track.definition.key
        base = self._minimap_cache.get(key)
        if base is None:
            base = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(base, (*PANEL, 205), base.get_rect(), border_radius=8)
            s.track.draw_outline(base, base.get_rect(), (200, 200, 200), 3)
            self._minimap_cache[key] = base
        screen.blit(base, box)
        scale, off = s.track.minimap_transform(pygame.Rect(0, 0, box.w, box.h))
        for car in sorted(s.cars, key=lambda c: c.is_player):
            px = box.x + car.pos.x * scale + off.x
            py = box.y + car.pos.y * scale + off.y
            r = 5 if car.is_player else 4
            pygame.draw.circle(screen, (0, 0, 0), (px, py), r + 1)
            pygame.draw.circle(screen, car.color, (px, py), r)
            if car.is_player:
                pygame.draw.circle(screen, WHITE, (px, py), r + 2, 1)
        for obj in s.extra_objects():
            px, py = box.x + obj.pos.x * scale + off.x, box.y + obj.pos.y * scale + off.y
            pygame.draw.circle(screen, (0, 0, 0), (px, py), 6)
            pygame.draw.circle(screen, (255, 200, 30) if int(pygame.time.get_ticks() / 300) % 2 else WHITE,
                               (px, py), 5)

    def _speedo(self, screen: pygame.Surface, car: "Car") -> None:
        f = self.f
        x, y, w, h = SCREEN_WIDTH - 296, SCREEN_HEIGHT - 142, 280, 126
        draw_panel(screen, (x, y, w, h))
        rpm = car.rpm_fraction
        leds = 15
        for i in range(leds):
            lit = rpm >= (i + 1) / leds * 0.98
            col = (40, 220, 80) if i < 5 else (235, 40, 40) if i < 10 else (80, 120, 255)
            if not lit:
                col = tuple(c // 6 for c in col)
            pygame.draw.circle(screen, col, (x + 24 + i * 16.5, y + 16), 6)
        speed, unit = speed_in(car.speed_kmh, self.units)
        draw_text(screen, f"{int(speed)}", f.big, WHITE, (x + 150, y + 34), anchor="topright")
        draw_text(screen, unit, f.small, GREY, (x + 154, y + 58))
        pygame.draw.rect(screen, PANEL_LIGHT, (x + 206, y + 32, 58, 62), border_radius=8)
        flash = getattr(car, "shift_flash", 0.0)
        gcol = (255, 90, 90) if flash < 0 else WHITE if flash > 0 else YELLOW
        draw_text(screen, car.gear, f.big, gcol, (x + 235, y + 63), anchor="center")
        if car.manual_gearbox:
            draw_text(screen, "SEQ", f.tiny, GREY, (x + 235, y + 28), anchor="center", shadow=False)
        bx = x + 18
        for i, (val, col, label) in enumerate(((car.throttle, GREEN, "GAS"), (car.brake, F1_RED, "BRK"))):
            by = y + 92 + i * 14
            draw_text(screen, label, f.tiny, GREY, (bx, by - 2), shadow=False)
            pygame.draw.rect(screen, (50, 50, 55), (bx + 34, by, 140, 8), border_radius=3)
            pygame.draw.rect(screen, col, (bx + 34, by, 140 * val, 8), border_radius=3)
        mode_rect = pygame.Rect(x + 146, y + 78, 56, 15)
        if car.straight_mode:
            pygame.draw.rect(screen, (70, 170, 255), mode_rect, border_radius=4)
            draw_text(screen, "GERADE", f.tiny, (5, 20, 40), mode_rect.center, anchor="center", shadow=False)
        else:
            zone = car.track.aero_zone_at[car.idx] >= 0 if car.track.aero_zone_at else False
            col = (70, 170, 255) if zone else (110, 110, 120)
            pygame.draw.rect(screen, col, mode_rect, 2, border_radius=4)
            draw_text(screen, "KURVE", f.tiny, col, mode_rect.center, anchor="center", shadow=False)
        if car.slipstream > 0.03:
            bar_h = int(44 * min(1.0, car.slipstream))
            pygame.draw.rect(screen, (50, 50, 55), (x + 18, y + 34, 8, 44), border_radius=3)
            pygame.draw.rect(screen, CYAN, (x + 18, y + 78 - bar_h, 8, bar_h), border_radius=3)
            if self._sog_label is None:
                self._sog_label = pygame.transform.rotate(f.tiny.render(tr("SOG"), True, CYAN), 90)
            screen.blit(self._sog_label, (x + 29, y + 38))
        if car.on_grass:
            draw_text(screen, "RASEN!", f.small_bold, (120, 220, 90), (x + 200, y + 100))
        elif car.sliding:
            draw_text(screen, "SLIDE", f.small_bold, ORANGE, (x + 205, y + 100))

    # ------------------------------------------------------------------ modern dashboard
    def _dashboard(self, screen: pygame.Surface, car: "Car") -> None:
        f = self.f
        w, h = 404, 130
        x, y = SCREEN_WIDTH - w - 16, SCREEN_HEIGHT - h - 16
        draw_panel(screen, (x, y, w, h), alpha=215)
        pygame.draw.rect(screen, car.color, (x, y, w, 3), border_top_left_radius=8, border_top_right_radius=8)
        # shift lights: 15 LEDs, green - red - blue, flashing blue at the limiter
        rpm = car.rpm_fraction
        flash = rpm > 0.97 and pygame.time.get_ticks() // 70 % 2
        for i in range(15):
            col = (40, 220, 80) if i < 5 else (235, 40, 40) if i < 10 else (80, 120, 255)
            if flash:
                col = (80, 120, 255)
            lit = rpm >= (i + 1) / 15 * 0.98
            pygame.draw.circle(screen, col if lit else tuple(c // 6 for c in col), (x + 22 + i * 15, y + 17), 5)
        # gear
        box = pygame.Rect(x + 12, y + 32, 66, 74)
        pygame.draw.rect(screen, PANEL_LIGHT, box, border_radius=8)
        shift = getattr(car, "shift_flash", 0.0)
        gcol = (255, 90, 90) if shift < 0 else WHITE if shift > 0 else YELLOW
        draw_text(screen, car.gear, f.big, gcol, (box.centerx, box.centery - 2), anchor="center", shadow=False)
        img = f.tiny.render("SEQ" if car.manual_gearbox else "AUTO", True, GREY)
        screen.blit(img, img.get_rect(midtop=(box.centerx, box.bottom + 2)))
        # speed and pedals
        speed, unit = speed_in(car.speed_kmh, self.units)
        draw_text(screen, f"{int(speed)}", f.big, WHITE, (x + 236, y + 26), anchor="topright", shadow=False)
        img = f.tiny.render(unit, True, GREY)
        screen.blit(img, img.get_rect(topright=(x + 236, y + 72)))
        for i, (val, col, label) in enumerate(((car.throttle, GREEN, "THR"), (car.brake, F1_RED, "BRK"))):
            by = y + 80 + i * 14
            img = f.tiny.render(label, True, GREY)
            screen.blit(img, (x + 92, by - 3))
            pygame.draw.rect(screen, (46, 48, 56), (x + 122, by, 62, 8), border_radius=3)
            if val > 0.01:
                pygame.draw.rect(screen, col, (x + 122, by, max(3, int(62 * val)), 8), border_radius=3)
        pill = pygame.Rect(x + 92, y + 108, 92, 15)
        if car.straight_mode:
            pygame.draw.rect(screen, (70, 170, 255), pill, border_radius=5)
            draw_text(screen, "GERADE", f.tiny, (5, 20, 40), pill.center, anchor="center", shadow=False)
        else:
            zone = car.track.aero_zone_at[car.idx] >= 0 if car.track.aero_zone_at else False
            col = (70, 170, 255) if zone else (100, 100, 112)
            pygame.draw.rect(screen, col, pill, 2, border_radius=5)
            draw_text(screen, "KURVE", f.tiny, col, pill.center, anchor="center", shadow=False)
        if car.slipstream > 0.03:
            bh = int(40 * min(1.0, car.slipstream))
            pygame.draw.rect(screen, (46, 48, 56), (x + 84, y + 34, 5, 40), border_radius=2)
            pygame.draw.rect(screen, CYAN, (x + 84, y + 74 - bh, 5, bh), border_radius=2)
        if car.on_grass:
            draw_text(screen, "RASEN!", f.tiny, (120, 220, 90), (x + 236, y + 6), anchor="topright", shadow=False)
        elif car.sliding or getattr(car, "wheelspin", 0.0) > 0.3:
            draw_text(screen, "SLIDE", f.tiny, ORANGE, (x + 236, y + 6), anchor="topright", shadow=False)
        elif getattr(car, "locking", False):
            draw_text(screen, "LOCK", f.tiny, (255, 90, 90), (x + 236, y + 6), anchor="topright", shadow=False)
        self._car_status(screen, car, pygame.Rect(x + 248, y + 10, 70, 112))
        # tyre temperatures and fuel
        cx = x + 362
        t = car.tyres
        draw_text(screen, "REIFEN °C", f.tiny, GREY, (cx, y + 8), anchor="midtop", shadow=False)
        if t is not None and hasattr(t, "temps"):
            for k, temp in enumerate(t.temps):
                img = f.small_bold.render(f"{temp:.0f}", True, self._temp_color(temp, t.optimal))
                screen.blit(img, img.get_rect(center=(cx - 15 + (k % 2) * 30, y + 34 + (k // 2) * 20)))
        laps = getattr(car, "fuel_laps", 0.0)
        img = f.tiny.render(f"{getattr(car, 'fuel', 0.0):.0f} kg", True, WHITE)
        screen.blit(img, img.get_rect(midtop=(cx, y + 76)))
        bar = pygame.Rect(cx - 28, y + 94, 56, 6)
        pygame.draw.rect(screen, (46, 48, 56), bar, border_radius=3)
        pygame.draw.rect(screen, YELLOW if laps < 1.5 else (200, 200, 210),
                         (bar.x, bar.y, int(bar.w * min(1.0, laps / 10)), bar.h), border_radius=3)
        draw_text(screen, f"{laps:.1f} Rd.", f.tiny, GREY, (cx, y + 104), anchor="midtop", shadow=False)

    @staticmethod
    def _temp_color(temp: float, optimal: float) -> tuple[int, int, int]:
        """Blue cold, green in the working window, orange warm, red overheating."""
        dev = temp - optimal
        if dev < -25:
            return (70, 130, 255)
        if dev < -10:
            return (110, 190, 255)
        if dev <= 12:
            return (70, 230, 120)
        if dev <= 22:
            return (255, 170, 50)
        return (255, 70, 50)

    def _car_status(self, screen: pygame.Surface, car: "Car", box: pygame.Rect) -> None:
        """Top-down car: tyres coloured by wear (outline = compound), wings/pods/floor by damage."""
        def dmg(v: float) -> tuple[int, int, int]:
            v = max(0.0, min(1.0, v))
            if v < 0.05:
                return (70, 76, 90)
            return (255, int(220 - 180 * v), 40) if v < 0.5 else (240, int(140 - 120 * v), 30)

        def wear_col(v: float) -> tuple[int, int, int]:
            v = max(0.0, min(1.0, v))
            if v < 0.5:
                return (int(60 + 380 * v), 220, 80)
            return (250, int(220 - 300 * (v - 0.5)), 50)
        d = car.damage
        cx = box.centerx
        tyres = car.tyres
        wear = tyres.corner_wear() if tyres is not None else (0.0, 0.0, 0.0, 0.0)
        comp = tyres.compound.color if tyres is not None else GREY
        pygame.draw.rect(screen, dmg(d.front_wing), (cx - 26, box.y, 52, 8), border_radius=3)
        pygame.draw.rect(screen, (70, 76, 90), (cx - 5, box.y + 8, 10, 26))
        pygame.draw.rect(screen, dmg(d.floor), (cx - 13, box.y + 34, 26, 52), border_radius=5)
        pygame.draw.rect(screen, dmg(d.cooling), (cx - 21, box.y + 44, 8, 30), border_radius=3)
        pygame.draw.rect(screen, dmg(d.cooling), (cx + 13, box.y + 44, 8, 30), border_radius=3)
        pygame.draw.rect(screen, dmg(d.rear), (cx - 24, box.bottom - 10, 48, 9), border_radius=3)
        # tyres: front left, front right, rear left, rear right
        spots = ((cx - 34, box.y + 14), (cx + 20, box.y + 14), (cx - 35, box.y + 70), (cx + 20, box.y + 70))
        for k, ((tx, ty), wv) in enumerate(zip(spots, wear)):
            w_, h_ = (14, 24) if k < 2 else (15, 28)
            susp = d.susp_l if k % 2 == 0 else d.susp_r
            rect = pygame.Rect(tx, ty, w_, h_)
            pygame.draw.rect(screen, wear_col(wv), rect, border_radius=4)
            if tyres is not None and hasattr(tyres, "temps"):
                # temperature strip: blue cold, green in the window, red overheating
                dev = tyres.temps[k] - tyres.optimal
                tcol = (60, 140, 255) if dev < -12 else (255, 70, 50) if dev > 14 else (60, 230, 120)
                pygame.draw.rect(screen, tcol, (rect.x + 3, rect.y + 3, rect.w - 6, 5), border_radius=2)
            pygame.draw.rect(screen, comp, rect, 2, border_radius=4)
            if susp > 0.05:
                pygame.draw.line(screen, dmg(susp), (rect.right if k % 2 == 0 else rect.x, rect.centery),
                                 (cx - 13 if k % 2 == 0 else cx + 13, rect.centery), 3)
        if tyres is not None:
            pygame.draw.circle(screen, (12, 12, 16), (cx, box.y + 60), 10)
            pygame.draw.circle(screen, comp, (cx, box.y + 60), 10, 2)
            img = self.f.tiny.render(tyres.compound.letter, True, comp)
            screen.blit(img, img.get_rect(center=(cx, box.y + 60)))

    def _spotter(self, screen: pygame.Surface, s: "Session") -> None:
        """Chevrons at the side of the screen when a car is right alongside (hard to see in 3D)."""
        me = s.focus
        f, r = me.forward, me.right
        sides = {-1: 0.0, 1: 0.0}
        for other in s.cars:
            if other is me or other.is_ghost or getattr(other, "ghost_visual", False) or other.dnf:
                continue
            d = other.pos - me.pos
            along, lat = d.dot(f), d.dot(r)
            if abs(along) < 42 and 10 < abs(lat) < 46:
                side = 1 if lat > 0 else -1
                sides[side] = max(sides[side], 1.0 - abs(along) / 42)
        cy = SCREEN_HEIGHT // 2 + 20
        for side, k in sides.items():
            if k <= 0:
                continue
            x = SCREEN_WIDTH // 2 + side * 330
            col = (255, int(200 - 120 * k), 40)
            for j in range(3):
                off = j * 16 * side
                pts = [(x + off, cy - 22), (x + off + side * 14, cy), (x + off, cy + 22)]
                pygame.draw.lines(screen, col if j < 1 + int(k * 2.5) else (90, 70, 40), False, pts, 6)

    def _flag_detail(self, s: "Session", car: "Car", flag: str) -> str:
        if flag == "blue":
            chaser = getattr(car, "blue_for", None)
            return f"{chaser.short} überrundet dich" if chaser is not None else ""
        if flag in ("yellow", "yellow2"):
            sector = min(2, int((car.s % s.track.length) / s.track.length * 3)) + 1
            return f"Sektor {sector} · nicht überholen" if flag == "yellow" else f"Sektor {sector} · Gefahr, langsam!"
        return {"sc": "Abstand halten · nicht überholen", "vsc": "Delta einhalten · nicht überholen",
                "green": "Strecke frei", "chequered": "Rennen beendet",
                "bw": "Track Limits - letzte Warnung"}.get(flag, "")

    def _flag_display(self, screen: pygame.Surface, s: "Session", full: bool) -> None:
        """Digital flag panel at the left edge (like the LED marshal boards), with full HUD assistance also
        flashing screen edges and a warning for slow cars ahead."""
        car = s.focus
        flag = car_flag(s, car)
        t = pygame.time.get_ticks()
        phase = (t // 280) % 2
        f = self.f
        if flag is not None:
            board = led_board(flag, phase, 28, 16, 4)
            x, y = 238, 156
            w = max(board.get_width(), f.tiny.size(tr(self._flag_detail(s, car, flag)))[0], 150) + 20
            draw_panel(screen, (x, y, w, board.get_height() + 58), (12, 13, 18), 225)
            col = FLAG_COLORS[flag]
            pygame.draw.rect(screen, col, (x, y, w, 3), border_radius=2)
            screen.blit(board, (x + (w - board.get_width()) // 2, y + 10))
            ty = y + board.get_height() + 16
            draw_text(screen, FLAG_NAMES[flag], f.small_bold, col if flag not in ("chequered", "bw") else WHITE,
                      (x + w // 2, ty), anchor="midtop", shadow=False)
            detail = self._flag_detail(s, car, flag)
            if detail:
                draw_text(screen, detail, f.tiny, (200, 200, 208), (x + w // 2, ty + 21), anchor="midtop", shadow=False)
            if full and flag in ("yellow", "yellow2", "blue", "sc", "vsc") and phase == 0:
                for ex in (0, SCREEN_WIDTH - 8):
                    pygame.draw.rect(screen, col, (ex, 200, 8, 320))
        if not full or not getattr(s, "race_started", True) or car.speed_fwd < 90.0:
            return
        rc = getattr(s, "rc", None)
        if rc is not None and rc.active:
            return
        hazard = hazard_ahead(s, car)
        if hazard is None:
            return
        dist, lat = hazard
        side = lat - car.lateral
        where = "LINKS" if side < -12 else "RECHTS" if side > 12 else "MITTE"
        rect = pygame.Rect(SCREEN_WIDTH // 2 - 170, 84, 340, 36)
        draw_panel(screen, rect, (120, 70, 0) if phase else (170, 100, 0), 235)
        pygame.draw.polygon(screen, (255, 210, 40), [(rect.x + 14, rect.bottom - 8), (rect.x + 30, rect.y + 6),
                                                     (rect.x + 46, rect.bottom - 8)])
        draw_text(screen, "!", f.small_bold, (30, 20, 0), (rect.x + 30, rect.bottom - 9), anchor="midbottom",
                  shadow=False)
        draw_text(screen, f"LANGSAMES AUTO VORAUS · {dist * PX_PER_S_TO_KMH / 3.6:.0f} m · {where}", f.small_bold, WHITE,
                  (rect.x + 58, rect.centery), anchor="midleft", shadow=False)

    def _pit_overlay(self, screen: pygame.Surface, car: "Car") -> None:
        f = self.f
        if car.in_pit:
            cx = SCREEN_WIDTH // 2
            py = SCREEN_HEIGHT - 190
            draw_panel(screen, (cx - 150, py, 300, 70), (60, 45, 0), 220)
            limit, unit = speed_in(100.0, self.units)
            draw_text(screen, f"PIT LIMITER  {limit:.0f} {unit}", f.medium, (255, 210, 40), (cx, py + 20), anchor="center")
            service = getattr(car, "pit_service", None)
            if service is not None and car.pit_stopped and (car.pit_stop_timer > 0 or car.pit_hold):
                self._pit_service(screen, car, service, cx, py)
            else:
                sub = f"-> {COMPOUNDS[car.pit_compound].name}" if car.pit_compound in COMPOUNDS else "-> Box"
                if car.pit_stopped and car.pit_last_stop is not None:
                    sub = f"Stopp {car.pit_last_stop:.2f}s  ·  GO GO GO!"
                draw_text(screen, sub, f.small_bold, WHITE, (cx, py + 50), anchor="center")
        if getattr(car, "brake_assist_active", False):
            draw_text(screen, "BREMSHILFE", f.small_bold, (255, 90, 90), (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 110),
                      anchor="center")

    def _pit_service(self, screen: pygame.Surface, car: "Car", service: dict, cx: int, py: int) -> None:
        """Stationary clock counting up (like the TV graphic) and the four wheels: grey waiting, red off, green on."""
        f = self.f
        t = service["t"]
        col = YELLOW if service.get("problem") is not None else WHITE
        img = f.mono_big.render(f"{t:5.2f}s", True, col)
        screen.blit(img, img.get_rect(midleft=(cx - 118, py + 50)))
        wheels = service.get("wheels")
        if wheels:
            for k, (off, on) in enumerate(wheels):
                x = cx + 26 + (k % 2) * 24
                y = py + 38 + (k // 2) * 15
                state = (40, 220, 90) if t >= on else (235, 50, 45) if t >= off else (110, 110, 120)
                if k == service.get("problem") and off <= t < on:
                    state = (255, 200, 40) if pygame.time.get_ticks() // 150 % 2 else (235, 50, 45)
                pygame.draw.rect(screen, state, (x, y, 18, 11), border_radius=3)
        light = (255, 200, 40) if car.pit_hold and car.pit_stop_timer <= 0 else (235, 50, 45)
        pygame.draw.circle(screen, (10, 10, 12), (cx + 118, py + 50), 12)
        pygame.draw.circle(screen, light, (cx + 118, py + 50), 9)
        if car.pit_hold and car.pit_stop_timer <= 0:
            draw_text(screen, "WARTEN", f.tiny, YELLOW, (cx + 96, py + 50), anchor="midright", shadow=False)

    @staticmethod
    def _tyre_forecast(car: "Car") -> float | None:
        t = car.tyres
        if t is None:
            return None
        L = car.track.length
        laps_on_set = t.laps + (car.distance % L) / L if car.timing_started else t.laps
        if laps_on_set < 0.4 or t.wear < 0.01:
            return None
        rate = t.wear / laps_on_set
        return max(0.0, (0.75 - t.wear) / rate)

    def _gap_trend(self, s: "Session", car: "Car", standings: list["Car"]) -> tuple[float | None, float | None]:
        from .sessions import time_gap
        i = standings.index(car)
        if i == 0 or s.kind != "race":
            return None, None
        gap = time_gap(standings[i - 1], car)
        key = (id(car), standings[i - 1].name)
        memo = self._trend.get(id(car))
        trend = None
        if memo is None or memo[0] != key[1]:
            self._trend[id(car)] = (key[1], car.laps_done, gap, None)
        else:
            _, lap, old_gap, trend = memo
            if car.laps_done > lap and gap is not None and old_gap is not None:
                trend = gap - old_gap
                self._trend[id(car)] = (key[1], car.laps_done, gap, trend)
        return gap, trend

    def _radio(self, s: "Session", car: "Car", forecast: float | None, remaining: int | None,
               gap: float | None, trend: float | None) -> tuple[str, tuple[int, int, int]]:
        if car.radio_msg is not None and s.time < car.radio_msg[2]:
            return car.radio_msg[0], car.radio_msg[1]
        d, t = car.damage, car.tyres
        if car.dnf:
            return "Auto abstellen. Das war's für heute.", (255, 90, 90)
        if car.in_pit:
            return "Limiter an, rein in die Box.", ORANGE
        if car.puncture:
            return "Reifenschaden! Langsam zurück an die Box.", (255, 90, 90)
        rc = getattr(s, "rc", None)
        if rc is not None and rc.active:
            if rc.mode == "SC" and rc.phase == "restart":
                return "Restart kommt - Reifen warm halten, bereit machen!", YELLOW
            return ("Safety Car! Abstand halten, nicht überholen." if rc.mode == "SC"
                    else "VSC - Tempo halten, Delta beachten."), YELLOW
        if car.penalty_unserved > 0 and s.kind == "race":
            return f"{car.penalty_unserved:.0f}s Strafe offen - beim Stopp abgesessen.", ORANGE
        if d.cooling > 0.4:
            return "Kühler beschädigt - Motor wird heiß, Leistung reduziert. Box!", (255, 90, 90)
        if d.front_wing > 0.4 or d.suspension > 0.35:
            side = "links" if d.susp_l > d.susp_r else "rechts"
            return (f"Aufhängung {side} beschädigt - das Auto zieht! Box empfohlen." if d.suspension > 0.35
                    else "Frontflügel beschädigt! Box für Reparatur empfohlen."), (255, 90, 90)
        if d.floor > 0.3:
            return "Unterboden beschädigt - weniger Abtrieb. Lässt sich in der Box nicht tauschen.", YELLOW
        if car.pit_request:
            if car.pit_request in COMPOUNDS:
                return f"Box, Box! {COMPOUNDS[car.pit_request].name} bereit - Linie folgen.", ORANGE
            return "Box, Box! Die Crew ist bereit.", ORANGE
        if car.out_of_fuel:
            return "Kein Sprit mehr! Auto ausrollen lassen.", (255, 90, 90)
        call = s.weather_tyre_call(car) if hasattr(s, "weather_tyre_call") else None
        if call == "inter":
            return "Strecke ist nass - Box für Intermediates! (B)", (90, 150, 255)
        if call == "wet":
            return "Starkregen - wir brauchen Full Wets! (B)", (90, 150, 255)
        if call is not None:
            return "Strecke trocknet ab - Slicks sind jetzt schneller! (B)", YELLOW
        w = getattr(s, "weather", None)
        if w is not None:
            eta = w.eta_rain(60.0)
            if eta is not None:
                return f"Regen kommt in ca. {eta:.0f} Sekunden.", (90, 150, 255)
        if car.fuel_per_lap > 0 and remaining is not None and remaining > 0 and                 car.fuel_laps < remaining - (car.distance % s.track.length) / s.track.length - 0.05:
            return "Sprit reicht nicht! Lift and Coast oder zum Tanken an die Box.", (255, 90, 90)
        if car.plank_per_lap > 0 and car.plank_wear > 0.85 * PLANK_LIMIT_MM and s.kind == "race":
            return "Planke fast am Limit! Randsteine meiden, sonst Disqualifikation.", (255, 90, 90)
        plan = car.next_planned_stop() if s.kind == "race" and car.is_player else None
        if plan is not None and not car.in_pit:
            lap, comp = plan
            to_go = lap - (car.laps_done + 1)
            if to_go <= 0:
                return f"Plan: Box diese Runde - {COMPOUNDS[comp].name}! (B, dann 5)", ORANGE
            if to_go <= 2:
                return f"Plan: Stopp in {to_go} Rd. auf {COMPOUNDS[comp].name}.", (90, 200, 255)
        if t is not None and t.wear > 0.8:
            return "Reifen sind am Ende - jetzt reinkommen!", (255, 90, 90)
        if getattr(s, "blue_flag", 0) > 0:
            return "Blaue Flagge - lass ihn vorbei.", (60, 140, 255)
        if remaining is not None and forecast is not None and remaining > 1 and forecast < remaining - 0.5:
            stop_in = max(0, int(forecast))
            return (f"Stopp nötig: Reifen halten noch ~{round(forecast)} Rd." if stop_in > 0
                    else "Reifen halten nicht bis ins Ziel - Box mit B."), YELLOW
        if trend is not None and gap is not None and gap < 2.5 and trend < -0.15:
            return f"Du holst {abs(trend):.1f}s pro Runde auf - dran bleiben!", GREEN
        if gap is not None and gap < 1.0:
            return "Im Windschatten - Gerade-Modus nutzen!", CYAN
        if trend is not None and trend > 0.3:
            return f"Wir verlieren {trend:.1f}s pro Runde nach vorne.", YELLOW
        if car.last_lap and car.best_lap and car.last_lap <= car.best_lap + 1e-6:
            return "Gute Runde! Persönliche Bestzeit.", GREEN
        if remaining is not None and remaining > 1 and forecast is not None:
            return "Reifen schaffen es bis ins Ziel. Tempo halten.", WHITE
        return "Alles im grünen Bereich.", WHITE

    def _engineer(self, screen: pygame.Surface, s: "Session") -> None:
        f = self.f
        car = s.focus
        standings = s.standings()
        x, y, w, h = SCREEN_WIDTH - 256, 314, 240, 258
        draw_panel(screen, (x, y, w, h))
        pygame.draw.rect(screen, car.color, (x, y, w, 4), border_radius=3)
        pos = standings.index(car) + 1
        title = "RENNINGENIEUR" if car is s.player else f"P{pos} {car.name}"
        if car.profile.number:
            title += f" · #{car.profile.number}"
        draw_text(screen, title[:28], f.tiny, GREY if car is s.player else WHITE, (x + 12, y + 9), shadow=False)
        if car is not s.player:
            sub = car.profile.team + (f" · KI {car.profile.brain}/{car.profile.checkpoint}" if not car.is_player else "")
            draw_text(screen, sub[:38], f.tiny, (130, 130, 140), (x + 12, y + 23), shadow=False)
        remaining = max(0, getattr(s, "total_laps", 0) - car.laps_done) if s.kind == "race" else None
        forecast = self._tyre_forecast(car)
        t = car.tyres
        ty = y + 38
        if t is not None:
            # 2x2 tyre grid: temperature on top (colour = working window), wear underneath
            temps = getattr(t, "temps", None)
            for k, wear in enumerate(t.corner_wear()):
                cell = pygame.Rect(x + 10 + (k % 2) * 54, ty + (k // 2) * 41, 50, 38)
                wcol = GREEN if wear < 0.5 else YELLOW if wear < 0.75 else (255, 90, 90)
                pygame.draw.rect(screen, (24, 26, 32), cell, border_radius=6)
                pygame.draw.rect(screen, wcol, (cell.x, cell.bottom - 4, int(cell.w * (1 - wear)), 4),
                                 border_bottom_left_radius=6, border_bottom_right_radius=6)
                if temps is not None:
                    tc = self._temp_color(temps[k], t.optimal)
                    pygame.draw.rect(screen, tc, cell, 2, border_radius=6)
                    img = f.small_bold.render(f"{temps[k]:.0f}°", True, tc)
                    screen.blit(img, img.get_rect(midtop=(cell.centerx, cell.y + 2)))
                img = f.tiny.render(f"{(1 - wear) * 100:.0f}%", True, (170, 170, 180))
                screen.blit(img, img.get_rect(midbottom=(cell.centerx, cell.bottom - 5)))
            comp = t.compound
            rx = x + 122
            pygame.draw.circle(screen, (15, 15, 18), (rx + 13, ty + 13), 13)
            pygame.draw.circle(screen, comp.color, (rx + 13, ty + 13), 13, 3)
            draw_text(screen, comp.letter, f.small_bold, comp.color, (rx + 13, ty + 13), anchor="center", shadow=False)
            draw_text(screen, comp.name, f.small_bold, WHITE, (rx + 32, ty - 2), shadow=False)
            draw_text(screen, f"{t.laps} Rd. alt", f.tiny, GREY, (rx + 32, ty + 15), shadow=False)
            life = 1.0 - t.wear
            col = GREEN if t.wear < 0.5 else YELLOW if t.wear < 0.75 else (255, 90, 90)
            pygame.draw.rect(screen, (45, 45, 52), (rx, ty + 34, 106, 7), border_radius=3)
            pygame.draw.rect(screen, col, (rx, ty + 34, int(106 * life), 7), border_radius=3)
            if forecast is None:
                l1, l2, fcol = "Prognose", "nach 1. Runde", GREY
            elif t.wear >= 0.75:
                l1, l2, fcol = "Reifen am", "Limit!", (255, 90, 90)
            else:
                l1 = f"~{round(forecast)} Rd. übrig"
                ok = remaining is not None and forecast >= remaining - 0.5
                l2 = "bis ins Ziel" if ok else (f"Ziel in {remaining}" if remaining is not None else "")
                fcol = GREEN if ok else YELLOW if remaining is not None else WHITE
            draw_text(screen, l1, f.tiny, fcol, (rx, ty + 48), shadow=False)
            draw_text(screen, l2, f.tiny, fcol, (rx, ty + 63), shadow=False)
        # car condition chips
        d = car.damage
        cy = y + 122
        for k, (label, v) in enumerate((("FLÜGEL", d.front_wing), ("HECK", d.rear), ("AUFH.", d.suspension),
                                        ("BODEN", d.floor), ("KÜHL.", d.cooling))):
            chip = pygame.Rect(x + 10 + k * 44, cy, 42, 16)
            col = (52, 58, 66) if v < 0.05 else YELLOW if v < 0.4 else (255, 80, 70)
            pygame.draw.rect(screen, col, chip, border_radius=4)
            img = f.tiny.render(tr(label), True, (230, 232, 236) if v < 0.05 else (20, 20, 24))
            if img.get_width() > chip.w - 4:
                img = pygame.transform.smoothscale(img, (chip.w - 4, img.get_height()))
            screen.blit(img, img.get_rect(center=chip.center))
        cy += 22
        # fuel
        if car.fuel_per_lap > 0:
            need = (remaining - (car.distance % s.track.length) / s.track.length) if remaining else None
            short = need is not None and car.fuel_laps < need - 0.05
            fcol = (255, 90, 90) if car.out_of_fuel or short else YELLOW if car.fuel_laps < 1.5 else (200, 200, 210)
            draw_text(screen, "SPRIT", f.tiny, GREY, (x + 12, cy), shadow=False)
            pygame.draw.rect(screen, (45, 45, 52), (x + 56, cy + 4, 70, 7), border_radius=3)
            frac = min(1.0, car.fuel_laps / max(1.0, need if need else car.fuel_laps or 1.0))
            pygame.draw.rect(screen, fcol, (x + 56, cy + 4, int(70 * frac), 7), border_radius=3)
            ftxt = f"{car.fuel:.0f} kg " + (f"{car.fuel_laps - need:+.1f}" if need is not None else
                                            f"{car.fuel_laps:.1f} Rd.")
            draw_text(screen, ftxt, f.tiny, fcol, (x + 132, cy), shadow=False)
        cy += 18
        gap, trend = self._gap_trend(s, car, standings)
        if s.is_manager_car(car):
            pending = s.team_orders.get(car, {}).get("compound", "none")
            hint = "B: Box-Anweisung · TAB: 2. Fahrer"
            if pending not in ("none", None):
                hint = f"Anweisung: {COMPOUNDS[pending].name} ..."
            draw_text(screen, hint, f.tiny, (120, 200, 255), (x + 12, cy), shadow=False)
            cy += 17
        elif s.kind == "race" and gap is not None:
            draw_text(screen, "VORDERMANN", f.tiny, GREY, (x + 12, cy), shadow=False)
            draw_text(screen, f"{gap:.2f}s", f.small_bold, WHITE, (x + 120, cy - 3), anchor="topright", shadow=False)
            if trend is not None and abs(trend) >= 0.05:
                closing = trend < 0
                tcol = GREEN if closing else (255, 110, 90)
                ax, ay = x + 132, cy + 7
                tri = [(ax, ay + 5), (ax + 10, ay + 5), (ax + 5, ay - 5)] if closing else \
                    [(ax, ay - 5), (ax + 10, ay - 5), (ax + 5, ay + 5)]
                pygame.draw.polygon(screen, tcol, tri)
                draw_text(screen, f"{abs(trend):.1f}s/Rd.", f.tiny, tcol, (x + 148, cy), shadow=False)
            cy += 17
        info = []
        if car.pit_stops:
            info.append(f"Stopps {car.pit_stops}")
        nxt = car.next_planned_stop() if s.kind == "race" else None
        if nxt is not None:
            info.append(f"Plan Rd. {nxt[0]} {COMPOUNDS[nxt[1]].letter}")
        if s.kind == "race" and car.tl_count:
            info.append(f"Track Limits {car.tl_count}/{5}")
        if car.vmax > 30:
            vmax, unit = speed_in(car.vmax * PX_PER_S_TO_KMH, s.game.settings.units)
            info.append(f"Vmax {vmax:.0f}")
        if car.plank_per_lap > 0:
            info.append(f"Planke {car.plank_wear:.2f}")
        if info:
            plank_hot = car.plank_per_lap > 0 and car.plank_wear > 0.8 * PLANK_LIMIT_MM
            draw_text(screen, " · ".join(tr(i) for i in info)[:44], f.tiny, YELLOW if plank_hot else (170, 170, 180),
                      (x + 12, cy), shadow=False)
        # radio
        msg, col = self._radio(s, car, forecast, remaining, gap, trend)
        ry = y + h - 48
        pygame.draw.rect(screen, (28, 30, 38), (x + 8, ry, w - 16, 40), border_radius=6)
        pygame.draw.rect(screen, col, (x + 8, ry, 3, 40), border_radius=2)
        draw_text(screen, "FUNK", f.tiny, GREY, (x + 18, ry + 4), shadow=False)
        words, line, lines = tr(msg).split(), "", []
        for word in words:
            trial = f"{line} {word}".strip()
            if f.tiny.size(trial)[0] > w - 84 and line:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
        for k, ln in enumerate(lines[:2]):
            draw_text(screen, ln, f.tiny, col, (x + 66, ry + 5 + k * 16), shadow=False)

    def _race_control(self, screen: pygame.Surface, s: "Session") -> None:
        log = s.stewards.log
        if not log:
            return
        f = self.f
        h = 26 + 22 * len(log)
        x, y = 16, SCREEN_HEIGHT - 34 - h
        draw_panel(screen, (x, y, 360, h), (10, 18, 40), 225)
        pygame.draw.rect(screen, (30, 70, 200), (x + 8, y + 6, 34, 14), border_radius=3)
        draw_text(screen, "OIA", f.tiny, (255, 220, 40), (x + 25, y + 13), anchor="center", shadow=False)
        draw_text(screen, "RENNLEITUNG", f.tiny, GREY, (x + 50, y + 6), shadow=False)
        colors = {"info": (220, 220, 225), "investigation": YELLOW, "penalty": ORANGE}
        for k, (text, ttl, kind) in enumerate(log):
            img = f.tiny.render(tr(text)[:52], True, colors.get(kind, WHITE))
            img.set_alpha(int(255 * min(1.0, ttl)))
            screen.blit(img, (x + 10, y + 26 + k * 22))

    def _race_gaps(self, screen: pygame.Surface, s: "RaceSession", standings: list["Car"]) -> None:
        from .sessions import time_gap
        f = self.f
        p = s.focus
        i = standings.index(p)
        cx = SCREEN_WIDTH // 2
        y = 52 if s.view3d and s.r3d.cockpit else SCREEN_HEIGHT - 70
        boxes: list[tuple[str, str, tuple[int, int, int], str]] = []
        if not s.race_started:
            return
        if i > 0:
            ahead = standings[i - 1]
            g = time_gap(ahead, p)
            boxes.append((f"P{i}  {ahead.short}", format_gap(g) if g is not None else "--", (255, 110, 110), "VOR DIR"))
        if i < len(standings) - 1:
            behind = standings[i + 1]
            g = time_gap(p, behind)
            boxes.append((f"P{i + 2}  {behind.short}", format_gap(-g) if g is not None else "--",
                          (110, 230, 140), "HINTER DIR"))
        total_w = len(boxes) * 200 + (len(boxes) - 1) * 12
        x = cx - 40 - total_w // 2
        for name, gap, col, label in boxes:
            draw_panel(screen, (x, y, 200, 54))
            pygame.draw.rect(screen, col, (x, y, 200, 3), border_radius=2)
            draw_text(screen, label, f.tiny, GREY, (x + 10, y + 8), shadow=False)
            draw_text(screen, name, f.small_bold, WHITE, (x + 10, y + 26), shadow=False)
            draw_text(screen, gap, f.mono_big, col, (x + 190, y + 20), anchor="topright", shadow=False)
            x += 212

    def _delta_panel(self, screen: pygame.Surface, s: "Session") -> None:
        f = self.f
        p = s.focus
        x, y = SCREEN_WIDTH // 2 - 110, 52 if s.view3d and s.r3d.cockpit else SCREEN_HEIGHT - 70
        draw_panel(screen, (x, y, 220, 54))
        draw_text(screen, "DELTA ZUR BESTZEIT", f.tiny, GREY, (x + 10, y + 8), shadow=False)
        d = p.live_delta()
        col = GREEN if d is not None and d < 0 else (255, 90, 90) if d is not None else GREY
        draw_text(screen, format_gap(d), f.mono_big, col, (x + 110, y + 36), anchor="center", shadow=False)

    def _lights(self, screen: pygame.Surface, s: "RaceSession") -> None:
        if s.race_started and s.go_timer <= 0:
            return
        cx = SCREEN_WIDTH // 2
        if not s.race_started:
            w = 5 * 52 + 16
            draw_panel(screen, (cx - w // 2, 20, w, 104), (8, 8, 10), 230)
            for i in range(5):
                ux = cx - w // 2 + 12 + i * 52
                pygame.draw.rect(screen, (25, 25, 28), (ux, 28, 44, 88), border_radius=8)
                for k in range(2):
                    center = (ux + 22, 50 + k * 44)
                    if i < s.lights_on:
                        glow = pygame.Surface((60, 60), pygame.SRCALPHA)
                        pygame.draw.circle(glow, (255, 30, 30, 70), (30, 30), 28)
                        screen.blit(glow, (center[0] - 30, center[1] - 30))
                        pygame.draw.circle(screen, (255, 35, 35), center, 15)
                        pygame.draw.circle(screen, (255, 160, 160), (center[0] - 4, center[1] - 4), 4)
                    else:
                        pygame.draw.circle(screen, (55, 15, 15), center, 15)
        else:
            alpha = min(1.0, s.go_timer)
            img = self.f.huge.render("GO!", True, (60, 255, 110))
            img.set_alpha(int(255 * alpha))
            screen.blit(img, img.get_rect(center=(cx, 110)))

    def _messages(self, screen: pygame.Surface, s: "Session") -> None:
        y = 175
        for text, color, ttl in s.messages:
            img = self.f.large.render(tr(text), True, color)
            img.set_alpha(int(255 * min(1.0, ttl * 2)))
            rect = img.get_rect(center=(SCREEN_WIDTH // 2, y))
            draw_panel(screen, rect.inflate(30, 12), alpha=int(170 * min(1.0, ttl * 2)))
            screen.blit(img, rect)
            y += 50

    def _feed(self, screen: pygame.Surface, s: "Session") -> None:
        x, y = SCREEN_WIDTH - 256, 196
        for text, ttl in s.feed:
            img = self.f.tiny.render(tr(text), True, WHITE)
            img.set_alpha(int(255 * min(1.0, ttl)))
            draw_panel(screen, (x, y, 240, 20), alpha=int(170 * min(1.0, ttl)), radius=4)
            screen.blit(img, (x + 8, y + 3))
            y += 23

    def _footer(self, screen: pygame.Surface, s: "Session") -> None:
        f = self.f
        hint = "V 2D/3D · K Kamera · M Karte · B Box · P Pause · C/1-0 Fahrer · H HUD · I KI · L Linie · R Reset"
        if s.player is not None and s.player.assist_level == 0:
            hint = "LEER Gerade-Modus · " + hint
        if s.spectator:
            hint = "Pfeile/1-0/Klick Fahrer · A TV-Regie · +/- Zeitraffer · V 2D/3D · K Kamera · M Karte · H HUD · P Pause"
            if s.config.focus_team:
                hint = "B Box-Anweisung · TAB eigener Fahrer · " + hint
        if s.kind == "practice":
            hint += " · G Garage · ENTER Session beenden"
        if s.show_fps:
            draw_text(screen, f"{s.game.clock.get_fps():3.0f} FPS · RAM {self.ram_mb():.0f} MB", f.tiny, YELLOW,
                      (SCREEN_WIDTH - 16, SCREEN_HEIGHT - 22), anchor="topright")
        draw_text(screen, hint, f.tiny, (200, 200, 200), (16, SCREEN_HEIGHT - 22))
        if s.time_scale > 1.0:
            draw_text(screen, f">> SIMULATION x{int(s.time_scale)}", f.medium, YELLOW,
                      (SCREEN_WIDTH // 2, 140), anchor="center")
        cam_car = s.cars[s.cam_index]
        if cam_car is not s.player and not s.spectator:
            draw_text(screen, f"KAMERA: {cam_car.name}  (Gehirn: {cam_car.profile.brain}/{cam_car.profile.checkpoint})",
                      f.small_bold, CYAN,
                      (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 92), anchor="center")

    def draw_network(self, screen: pygame.Surface, car: "AI_Car") -> None:
        rect = pygame.Rect(SCREEN_WIDTH - 470, SCREEN_HEIGHT - 470, 454, 316)
        draw_panel(screen, rect)
        draw_text(screen, f"NEURONALES NETZ · {car.short} · {car.profile.brain}/{car.profile.checkpoint}",
                  self.f.tiny, GREY, (rect.x + 12, rect.y + 8), shadow=False)
        draw_network(screen, rect.inflate(-20, -36).move(0, 10), car.driver.net, self.f.tiny)

    def draw_split(self, screen: pygame.Surface, s: "Session") -> None:
        """Split screen: a compact HUD per player half, lights/messages/race control across the middle."""
        self.units = s.game.settings.units
        f = self.f
        half = SCREEN_WIDTH // 2
        standings = s.standings()
        for k, car in enumerate(s.players):
            x0 = k * half
            # position / lap / times
            draw_panel(screen, (x0 + 12, 12, 236, 86))
            pygame.draw.rect(screen, car.color, (x0 + 12, 12, 5, 86), border_radius=3)
            draw_text(screen, f"P{k + 1} · {car.name}"[:26], f.tiny, GREY, (x0 + 26, 18), shadow=False)
            pos = standings.index(car) + 1
            draw_text(screen, f"{pos}", f.large, WHITE, (x0 + 26, 34))
            draw_text(screen, f"/{len(s.cars)}", f.small, GREY, (x0 + 30 + f.large.size(str(pos))[0], 46))
            if s.kind == "race":
                lap = "DSQ" if car.dsq else "DNF" if car.dnf else "ZIEL" if car.session_done else \
                    f"{min(car.laps_done + 1, s.total_laps)}/{s.total_laps}"
            else:
                lap = str(car.laps_done + 1) if car.timing_started else "OUT"
            draw_text(screen, "RUNDE", f.tiny, GREY, (x0 + 110, 34), shadow=False)
            draw_text(screen, lap, f.medium, WHITE, (x0 + 110, 48), shadow=False)
            draw_text(screen, format_time(car.current_lap_time(s.time) if not car.session_done else None),
                      f.mono, WHITE, (x0 + 26, 76), shadow=False)
            best_col = PURPLE if s.fastest_lap and car.best_lap == s.fastest_lap[0] else GREEN
            draw_text(screen, format_time(car.best_lap), f.mono, best_col if car.best_lap else GREY,
                      (x0 + 136, 76), shadow=False)
            # speed, gear, tyres, fuel, plank
            bx, by = x0 + half - 248, SCREEN_HEIGHT - 104
            draw_panel(screen, (bx, by, 236, 92))
            speed, unit = speed_in(car.speed_kmh, self.units)
            draw_text(screen, f"{int(speed)}", f.large, WHITE, (bx + 104, by + 6), anchor="topright")
            draw_text(screen, unit, f.tiny, GREY, (bx + 108, by + 22), shadow=False)
            draw_text(screen, car.gear, f.large, YELLOW, (bx + 210, by + 6), anchor="topright")
            if car.straight_mode:
                draw_text(screen, "GERADE", f.tiny, CYAN, (bx + 140, by + 14), shadow=False)
            t = car.tyres
            if t is not None:
                comp = t.compound
                pygame.draw.circle(screen, comp.color, (bx + 20, by + 56), 9, 3)
                draw_text(screen, comp.letter, f.tiny, comp.color, (bx + 20, by + 56), anchor="center", shadow=False)
                life = 1.0 - t.wear
                col = GREEN if t.wear < 0.5 else YELLOW if t.wear < 0.75 else (255, 90, 90)
                draw_text(screen, f"{life * 100:.0f}%", f.small_bold, col, (bx + 36, by + 46), shadow=False)
            if car.fuel_per_lap > 0:
                fcol = (255, 90, 90) if car.out_of_fuel else WHITE
                draw_text(screen, f"Sprit {car.fuel_laps:.1f} Rd.", f.tiny, fcol, (bx + 92, by + 44), shadow=False)
            if car.plank_per_lap > 0:
                pcol = (255, 90, 90) if car.plank_wear > PLANK_LIMIT_MM else WHITE
                draw_text(screen, f"Planke {car.plank_wear:.2f}", f.tiny, pcol, (bx + 92, by + 60), shadow=False)
            parts = car.damage.parts()
            if parts:
                n, v = parts[0]
                draw_text(screen, f"{n} {v * 100:.0f}%", f.tiny, (255, 90, 90) if v > 0.4 else YELLOW,
                          (bx + 12, by + 74), shadow=False)
            if car.pit_request:
                draw_text(screen, "BOX", f.small_bold, ORANGE, (bx + 200, by + 66), anchor="topright", shadow=False)
            if car.in_pit:
                draw_text(screen, "PIT LIMITER", f.small_bold, ORANGE, (x0 + half // 2, SCREEN_HEIGHT - 150),
                          anchor="center")
        if s.kind == "race":
            self._lights(screen, s)
        self._neutralization(screen, s)
        self._messages(screen, s)
        self._race_control(screen, s)
        hint = "P1: WASD · LEER Gerade · B Box · R Reset      P2: Pfeile · STRG-R Gerade · SHIFT-R Box · ENTF Reset"
        if s.time < 12.0 or s.paused:
            rect = draw_text(screen, hint, f.tiny, WHITE, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 132), anchor="center")
            draw_panel(screen, rect.inflate(20, 10), alpha=170)
            draw_text(screen, hint, f.tiny, WHITE, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 132), anchor="center")

    def draw_pause(self, screen: pygame.Surface, s: "Session") -> None:
        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        screen.blit(shade, (0, 0))
        draw_text(screen, "PAUSE", self.f.huge, WHITE, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 40), anchor="center")
        # clickable buttons (keys P / R / ESC still work)
        mouse = pygame.mouse.get_pos()
        self.pause_buttons = []
        for k, (label, key) in enumerate((("WEITER (P)", pygame.K_p), ("NEUSTART (R)", pygame.K_r),
                                          ("HAUPTMENÜ (ESC)", pygame.K_ESCAPE))):
            rect = pygame.Rect(SCREEN_WIDTH // 2 - 330 + k * 225, SCREEN_HEIGHT // 2 + 12, 210, 40)
            hover = rect.collidepoint(mouse)
            pygame.draw.rect(screen, F1_RED if hover else (44, 46, 56), rect, border_radius=8)
            draw_text(screen, label, self.f.small_bold, WHITE, rect.center, anchor="center", shadow=False)
            self.pause_buttons.append((rect, key))
        draw_text(screen, f"{s.title}  ·  {s.track.name}  ·  F12: Screenshot", self.f.small, (150, 150, 160),
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 90), anchor="center", shadow=False)
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 300)
        pygame.draw.rect(screen, F1_RED, (SCREEN_WIDTH // 2 - 60, SCREEN_HEIGHT // 2 + 60, 120 * pulse, 4))


def _activation_color(v: float) -> tuple[int, int, int]:
    v = max(-1.0, min(1.0, v))
    if v >= 0:
        return (int(70 + 185 * v), int(70 + 90 * v), 70)
    return (70, int(70 + 90 * -v), int(70 + 185 * -v))


def draw_network(screen: pygame.Surface, rect: pygame.Rect, net: "NeuralNetwork", font: pygame.font.Font) -> None:
    from .sensors import INPUT_NAMES, OUTPUT_NAMES
    sizes = net.sizes
    acts = net.activations or [[0.0] * n for n in sizes]
    label_w = 78
    inner = pygame.Rect(rect.x + label_w, rect.y, rect.w - label_w - 120, rect.h)
    cols = [inner.x + inner.w * i / (len(sizes) - 1) for i in range(len(sizes))]
    pos = [[(cols[l], inner.y + inner.h * (j + 0.5) / n) for j in range(n)] for l, n in enumerate(sizes)]
    for l, W in enumerate(net.weights):
        for j, row in enumerate(W):
            for i, w in enumerate(row):
                if abs(w) < 0.45:
                    continue
                strength = abs(w * acts[l][i])
                base = (230, 140, 60) if w > 0 else (80, 140, 240)
                col = tuple(int(c * min(1.0, 0.25 + strength)) for c in base)
                pygame.draw.line(screen, col, pos[l][i], pos[l + 1][j], 1)
    for l, layer in enumerate(pos):
        r = 6 if l == 0 else 7
        for j, p in enumerate(layer):
            pygame.draw.circle(screen, _activation_color(acts[l][j]), p, r)
            pygame.draw.circle(screen, (15, 15, 18), p, r, 1)
    for j, name in enumerate(INPUT_NAMES[:sizes[0]]):
        img = font.render(name, True, (190, 190, 195))
        screen.blit(img, img.get_rect(midright=(pos[0][j][0] - 10, pos[0][j][1])))
    for j, name in enumerate(OUTPUT_NAMES):
        img = font.render(f"{name} {acts[-1][j]:+.2f}", True, WHITE)
        screen.blit(img, img.get_rect(midleft=(pos[-1][j][0] + 12, pos[-1][j][1])))
