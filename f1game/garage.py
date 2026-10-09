# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable

import pygame

from .car import build_car_sprite
from .car_setup import CarSetup, predicted, recommended
from .profiles import Team
from .settings import CYAN, GREEN, GREY, PANEL, PANEL_LIGHT, PX_PER_S_TO_KMH, TOP_SPEED, WHITE, YELLOW
from .i18n import tr
from .user_settings import speed_in
from .utils import draw_panel, draw_text

if TYPE_CHECKING:
    from .game import Game
    from .track import Track

ACCENT = (70, 170, 255)


def _wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    text = tr(text)
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


class GarageScreen:
    BUTTONS = ["EMPFOHLEN", "NEUTRAL", "FERTIG"]

    def __init__(self, game: "Game", track: "Track", team: Team | None, on_done: Callable[[], None]) -> None:
        from .screens import _Background
        self.game = game
        self.track = track
        self.team = team
        self.on_done = on_done
        self.setup = CarSetup(**vars(game.setup_for(track)))
        self.keys = CarSetup.keys()
        self.sel = 0
        self.bg = _Background()
        self.t = 0.0
        color = team.color if team is not None else (0, 215, 255)
        self.sprite = pygame.transform.rotozoom(build_car_sprite(color, (255, 255, 255), 4.0), 90, 1.0)

    ROW_H = 58

    @property
    def rows(self) -> list[str]:
        return self.keys + ["fuel"] + self.BUTTONS

    def _done(self) -> None:
        self.game.setups[self.track.definition.key] = self.setup
        self.game.save_setups()
        self.on_done()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        row = self.rows[self.sel]
        if event.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(self.rows)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(self.rows)
        elif event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d) and row in self.keys:
            delta = -1 if event.key in (pygame.K_LEFT, pygame.K_a) else 1
            setattr(self.setup, row, max(-5, min(5, getattr(self.setup, row) + delta)))
        elif event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d) and row == "fuel":
            delta = -1 if event.key in (pygame.K_LEFT, pygame.K_a) else 1
            self.setup.fuel = max(-6, min(6, self.setup.fuel + delta))
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            if row == "EMPFOHLEN":
                self.setup = recommended(self.track)
            elif row == "NEUTRAL":
                self.setup = CarSetup()
            elif row == "fuel":
                return
            else:
                self._done()
        elif event.key == pygame.K_ESCAPE:
            self._done()

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, ACCENT, (60, 40, 8, 60))
        draw_text(screen, "GARAGE · FAHRZEUG-SETUP", f.big, WHITE, (84, 36))
        team = self.team.name if self.team is not None else "Referenzauto"
        draw_text(screen, f"{self.track.name} · {team} · gespeichert pro Strecke (data/setups.json)", f.small,
                  GREY, (86, 86))
        self._draw_sliders(screen)
        self._draw_prediction(screen)

    def _draw_sliders(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        px, py, pw = 60, 128, 620
        draw_panel(screen, (px, py, pw, 540), PANEL, 215)
        rec = recommended(self.track)
        rh = self.ROW_H
        for i, key in enumerate(self.keys):
            y = py + 12 + i * rh
            selected = i == self.sel
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 10, y - 4, pw - 20, rh - 4), border_radius=6)
                pygame.draw.rect(screen, ACCENT, (px + 10, y - 4, 5, rh - 4), border_radius=2)
            label, lo, hi = CarSetup.LABELS[key]
            val = getattr(self.setup, key)
            draw_text(screen, label.upper(), f.tiny, WHITE if selected else GREY, (px + 28, y), shadow=False)
            draw_text(screen, f"{val:+d}" if val else "0", f.medium, YELLOW if selected else WHITE,
                      (px + pw - 30, y + 18), anchor="topright", shadow=False)
            sx, sw, sy = px + 110, 380, y + 32
            draw_text(screen, lo, f.tiny, GREY, (sx - 12, sy - 7), anchor="topright", shadow=False)
            draw_text(screen, hi, f.tiny, GREY, (sx + sw + 12, sy - 7), shadow=False)
            pygame.draw.line(screen, (70, 72, 82), (sx, sy), (sx + sw, sy), 4)
            for k in range(11):
                tx = sx + sw * k / 10
                pygame.draw.line(screen, (90, 92, 104), (tx, sy - 5 if k != 5 else sy - 9), (tx, sy + 5), 2)
            rx = sx + sw * (getattr(rec, key) + 5) / 10
            pygame.draw.polygon(screen, GREEN, [(rx, sy + 8), (rx - 5, sy + 15), (rx + 5, sy + 15)])
            vx = sx + sw * (val + 5) / 10
            pygame.draw.circle(screen, ACCENT if selected else WHITE, (vx, sy), 9)
            pygame.draw.circle(screen, (15, 15, 20), (vx, sy), 9, 2)
        fy = py + 12 + len(self.keys) * rh
        selected = self.rows[self.sel] == "fuel"
        if selected:
            pygame.draw.rect(screen, PANEL_LIGHT, (px + 10, fy - 4, pw - 20, 44), border_radius=6)
            pygame.draw.rect(screen, ACCENT, (px + 10, fy - 4, 5, 44), border_radius=2)
        draw_text(screen, "SPRIT BEIM RENNSTART", f.tiny, WHITE if selected else GREY, (px + 28, fy), shadow=False)
        margin = self.setup.fuel / 2
        fuel_txt = "genau Renndistanz" if margin == 0 else f"Renndistanz {margin:+.1f} Runden"
        col = (255, 110, 90) if margin < 0 else YELLOW if selected else WHITE
        draw_text(screen, fuel_txt, f.small_bold, col, (px + 28, fy + 16), shadow=False)
        if selected:
            draw_text(screen, "<  >", f.medium, YELLOW, (px + pw - 30, fy + 8), anchor="topright")
        by = fy + 50
        bw = (pw - 60) // 3
        for k, name in enumerate(self.BUTTONS):
            selected = self.rows[self.sel] == name
            rect = pygame.Rect(px + 20 + k * (bw + 10), by, bw, 40)
            base = ACCENT if name == "FERTIG" else (100, 100, 115)
            pulse = 0.5 + 0.5 * math.sin(self.t * 4) if selected else 0.0
            col = tuple(int(c * (0.75 + 0.25 * pulse)) for c in base) if selected else tuple(c // 3 for c in base)
            pygame.draw.rect(screen, col, rect, border_radius=8)
            draw_text(screen, name, f.small_bold, WHITE, rect.center, anchor="center", shadow=False)
        draw_text(screen, "Grünes Dreieck = empfohlener Wert für diese Strecke", f.tiny, GREEN,
                  (px + 20, by + 48), shadow=False)
        draw_text(screen, "Pfeile wählen/ändern · ENTER/ESC übernehmen", f.tiny, GREY,
                  (px + 20, by + 66), shadow=False)

    def _draw_prediction(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        box = pygame.Rect(700, 128, 540, 540)
        draw_panel(screen, box, PANEL, 215)
        team_top = (self.team.top_speed if self.team is not None else 1.0) * TOP_SPEED * PX_PER_S_TO_KMH
        pred = predicted(self.setup, team_top)
        base = predicted(CarSetup(), team_top)
        screen.blit(self.sprite, self.sprite.get_rect(center=(box.right - 70, box.y + 112)))
        draw_text(screen, "PROGNOSE", f.tiny, GREY, (box.x + 18, box.y + 14), shadow=False)
        units = self.game.settings.units
        top, unit = speed_in(pred["top"], units)
        draw_text(screen, f"{top:.0f} {unit}", f.large, WHITE, (box.x + 18, box.y + 34))
        draw_text(screen, "Topspeed (Kurven-Modus)", f.tiny, GREY, (box.x + 18, box.y + 70), shadow=False)
        draw_text(screen, f"{speed_in(pred['max'], units)[0]:.0f} {unit}", f.medium, CYAN, (box.x + 18, box.y + 92))
        draw_text(screen, "mit Gerade-Modus + Windschatten" + ("  (Begrenzer!)" if pred["max"] < base["max"] - 2
                                                                and self.setup.gearing < 0 else ""),
                  f.tiny, GREY, (box.x + 18, box.y + 118), shadow=False)
        stats = [("Kurvengrip", "grip", False), ("Beschleunigung", "accel", False), ("Bremsleistung", "brake", False),
                 ("Einlenken", "turn", False), ("Heck-Stabilität", "stability", False),
                 ("Reifenverschleiß", "wear", True), ("Planken-Abrieb", "plank", True)]
        for k, (label, key, lower_better) in enumerate(stats):
            y = box.y + 150 + k * 36
            diff = (pred[key] - 1.0) * 100
            good = (diff < 0) if lower_better else (diff > 0)
            col = GREEN if good and abs(diff) > 0.05 else (255, 110, 90) if abs(diff) > 0.05 else WHITE
            draw_text(screen, label, f.small, WHITE, (box.x + 18, y), shadow=False)
            draw_text(screen, f"{diff:+.1f} %", f.mono, col, (box.x + 290, y + 1), anchor="topright", shadow=False)
            cx, w = box.x + 300, 210
            pygame.draw.rect(screen, (45, 45, 52), (cx, y + 6, w, 8), border_radius=3)
            pygame.draw.line(screen, (120, 120, 130), (cx + w // 2, y + 2), (cx + w // 2, y + 18), 2)
            bar = max(-w // 2, min(w // 2, int(diff * (1 if key == "plank" else 10))))
            pygame.draw.rect(screen, col, (cx + w // 2 + min(0, bar), y + 6, abs(bar), 8), border_radius=3)
        key = self.rows[self.sel]
        help_text = CarSetup.HELP.get(key, "Empfohlen: Basis-Setup für diese Strecke (Flügel nach Vollgas-Anteil). "
                                           "Die KI-Teams fahren dieses Setup.")
        if key == "fuel":
            help_text = ("Mehr Sprit = Reserve für Safety-Car-Phasen, aber jedes kg kostet Beschleunigung, Grip "
                         "und Bremsweg. Weniger als die Renndistanz = leichter und schneller, dann muss aber "
                         "getankt werden (Boxenstopp-Menü mit B) oder Sprit gespart werden (früher vom Gas).")
        hy = box.y + 420
        pygame.draw.line(screen, (60, 62, 72), (box.x + 18, hy - 10), (box.right - 18, hy - 10), 1)
        for k, line in enumerate(_wrap(help_text, f.small, box.w - 36)):
            draw_text(screen, line, f.small, (205, 205, 210), (box.x + 18, hy + k * 22), shadow=False)
