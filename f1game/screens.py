# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Callable

import pygame

from .car import build_car_sprite
from .championship import FORMATS, Championship
from .profiles import recording_stats
from .sound import VOLUMES
from .tyres import ALL_COMPOUNDS, COMPOUND_ORDER, COMPOUNDS
from .user_settings import ASSIST_NAMES, DAMAGE_MODES, EFFECT_LEVELS, FPS_OPTIONS, TYRE_WEAR_MODES, UNITS, speed_in
from .settings import (CYAN, DIFFICULTY_LEVELS, F1_RED, GREEN, GREY, PANEL, PANEL_LIGHT, PX_PER_S_TO_KMH,
                       SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, YELLOW)
from .track import TRACK_DEFS
from .weather import WEATHER_MODES
from .i18n import LANGUAGES, set_language, tr
from .utils import clear_render_caches, draw_panel, draw_text, format_time, vertical_gradient

if TYPE_CHECKING:
    from .game import Game
    from .sessions import RaceSession

MODES: list[tuple[str, str]] = [
    ("weekend", "Rennwochenende"),
    ("practice", "Freies Training"),
    ("qualifying", "Qualifying + Rennen"),
    ("race", "Nur Rennen"),
]
MODE_HINTS: dict[str, str] = {
    "weekend": "Training -> Qualifying (3 Runden) -> Rennen mit Podium",
    "practice": "Freie Fahrt mit Live-Zeitentabelle",
    "qualifying": "3 gezeitete Runden bestimmen die Startaufstellung",
    "race": "Zufällige Startaufstellung, direkt zur Ampel",
}


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


def session_dnf(car) -> bool:
    return car is not None and getattr(car, "dnf", False)


def _fit(text: str, font: pygame.font.Font, width: int) -> str:
    text = tr(text)
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "...")[0] > width:
        text = text[:-1]
    return text + "..."


class _Background:

    def __init__(self) -> None:
        self.base = vertical_gradient((SCREEN_WIDTH, SCREEN_HEIGHT), (24, 26, 34), (8, 8, 12))
        self.lines = [[random.uniform(0, SCREEN_WIDTH), random.uniform(0, SCREEN_HEIGHT),
                       random.uniform(200, 700), random.uniform(60, 220)] for _ in range(26)]

    def update(self, dt: float) -> None:
        for ln in self.lines:
            ln[0] += ln[2] * dt
            if ln[0] - ln[3] > SCREEN_WIDTH + 100:
                ln[0] = -50
                ln[1] = random.uniform(0, SCREEN_HEIGHT)

    def draw(self, screen: pygame.Surface) -> None:
        screen.blit(self.base, (0, 0))
        for x, y, v, length in self.lines:
            shade = int(30 + v / 700 * 30)
            pygame.draw.line(screen, (shade, shade, shade + 8), (x - length, y + length * 0.25), (x, y), 2)


class MainMenu:

    ITEMS: list[tuple[str, str]] = [
        ("EINZELSPIELER", "Fahre selbst ein Rennwochenende gegen die KI"),
        ("KARRIERE", "Fahrer-Karriere mit Verträgen & Rivalen oder eigenes Team als Teamchef"),
        ("WELTMEISTERSCHAFT", "Saison über alle Strecken mit WM-Punkten, Fahrer- und Teamwertung"),
        ("ZUSCHAUER-RENNEN", "Nur KI-Fahrer - lehn dich zurück, TV-Regie inklusive"),
        ("KI-TRAINING", "Neuronale Netze live trainieren oder deinen Klon erzeugen"),
        ("EINSTELLUNGEN", "Name, Fahrhilfen, Ansicht, Schaden, Reifen, Sound, Vollbild"),
        ("BEENDEN", ""),
    ]

    def __init__(self, game: "Game") -> None:
        self.game = game
        self.sel = 0
        self.bg = _Background()
        self.t = 0.0
        self.showcase_track = 0
        self.rec_files, self.rec_samples = recording_stats()
        self.dots = [(t.color, 0.06 + (t.rating - 0.97) * 0.9 + k * 0.0013, k * 0.035)
                     for k, t in enumerate(game.teams)] or [((200, 200, 200), 0.06, 0.0)]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(self.ITEMS)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(self.ITEMS)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            choice = self.ITEMS[self.sel][0]
            if choice == "EINZELSPIELER":
                self.game.open_setup(spectator=False)
            elif choice == "ZUSCHAUER-RENNEN":
                self.game.open_setup(spectator=True)
            elif choice == "WELTMEISTERSCHAFT":
                self.game.open_championship()
            elif choice == "KARRIERE":
                self.game.open_career_slots()
            elif choice == "KI-TRAINING":
                self.game.open_training()
            elif choice == "EINSTELLUNGEN":
                self.game.open_settings()
            else:
                self.game.running = False
        elif event.key == pygame.K_ESCAPE:
            self.game.running = False

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)
        self.showcase_track = int(self.t / 8.0) % len(TRACK_DEFS)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        for k in range(3):
            pygame.draw.polygon(screen, (min(255, 160 + k * 40), 0, 0),
                                [(40 + k * 18, 60), (70 + k * 18, 60), (40 + k * 18, 150), (10 + k * 18, 150)])
        draw_text(screen, "F1", f.huge, WHITE, (110, 52))
        draw_text(screen, "GRAND PRIX", f.huge, WHITE, (110, 120))
        draw_text(screen, "Neuronale KI · Karriere · WM · Aktive Aero · Setup · Sound · 2D/3D", f.small, GREY,
                  (114, 205))

        for i, (label, sub) in enumerate(self.ITEMS):
            y = 238 + i * 63
            selected = i == self.sel
            slide = 18 if selected else 0
            w = 470 if selected else 430
            col = F1_RED if selected else PANEL_LIGHT
            pygame.draw.polygon(screen, col, [(60 + slide, y), (60 + slide + w, y), (40 + slide + w, y + 55),
                                              (40 + slide, y + 55)])
            draw_text(screen, label, f.large, WHITE, (80 + slide, y + 6))
            if sub:
                draw_text(screen, sub, f.tiny, (235, 235, 235) if selected else GREY, (82 + slide, y + 37),
                          shadow=False)

        self._draw_showcase(screen)
        st = self.game.settings
        info = (f"Fahrer: {st.player_name}  ·  Fahrhilfen: {['Aus', 'Mittel', 'Voll'][st.assists]}  ·  "
                f"Ansicht: {'3D' if st.view3d else '2D'}  ·  Aufnahmen: {self.rec_samples} Samples")
        draw_text(screen, info, f.tiny, (150, 150, 160), (60, SCREEN_HEIGHT - 28), shadow=False)
        draw_text(screen, "Pfeile wählen · ENTER bestätigen · ESC beenden", f.tiny, (150, 150, 160),
                  (SCREEN_WIDTH - 40, SCREEN_HEIGHT - 28), anchor="topright", shadow=False)

    def _draw_showcase(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        td = TRACK_DEFS[self.showcase_track]
        track = self.game.tracks[td.key]
        box = pygame.Rect(640, 60, 600, 330)
        draw_panel(screen, box, PANEL, 200)
        track.draw_outline(screen, box.inflate(-40, -60).move(0, 14), (225, 225, 230), 5)
        scale, off = track.minimap_transform(box.inflate(-40, -60).move(0, 14))
        for color, speed, phase in self.dots:
            i = int(((self.t * speed + phase) % 1.0) * track.n)
            p = track.center[i] * scale + off
            pygame.draw.circle(screen, (10, 10, 12), p, 7)
            pygame.draw.circle(screen, color, p, 5)
        draw_text(screen, f"{td.name.upper()}  ·  {td.country}", f.medium, WHITE, (box.x + 18, box.y + 12))

        tb = pygame.Rect(640, 404, 600, 270)
        draw_panel(screen, tb, PANEL, 200)
        draw_text(screen, "TEAMS  ·  FAHRZEUG-WERTUNG  (data/teams.json)", f.tiny, GREY, (tb.x + 16, tb.y + 10),
                  shadow=False)
        teams = sorted(self.game.teams, key=lambda t: -t.rating)
        cols = 2
        per_col = (len(teams) + cols - 1) // cols
        for k, team in enumerate(teams):
            cx = tb.x + 16 + (k // per_col) * 292
            cy = tb.y + 34 + (k % per_col) * 38
            pygame.draw.rect(screen, team.color, (cx, cy + 2, 6, 28))
            draw_text(screen, f"{k + 1}. {_fit(team.name, f.small_bold, 150)}", f.small_bold, WHITE, (cx + 14, cy),
                      shadow=False)
            bar = max(0.05, min(1.0, (team.rating - 0.96) / 0.08))
            pygame.draw.rect(screen, (45, 45, 52), (cx + 14, cy + 22, 250, 6), border_radius=3)
            pygame.draw.rect(screen, team.color if sum(team.color) > 120 else (90, 100, 200),
                             (cx + 14, cy + 22, 250 * bar, 6), border_radius=3)


class SetupScreen:

    PLAYER_ROWS = ["Strecke", "Modus", "Rennrunden", "KI-Stärke", "Gegner", "Dein Team", "Spieler", "Startreifen",
                   "Fahrzeug-Setup", "START", "ZURÜCK"]
    SPECTATOR_ROWS = ["Strecke", "Modus", "Rennrunden", "Fahrerfeld", "START", "ZURÜCK"]
    SPECTATOR_MODES = [m for m in MODES if m[0] != "practice"]

    def __init__(self, game: "Game", spectator: bool) -> None:
        self.game = game
        self.spectator = spectator
        self.rows = self.SPECTATOR_ROWS if spectator else self.PLAYER_ROWS
        self.sel = self.rows.index("START")
        self.bg = _Background()
        self.t = 0.0
        self.diffs = list(DIFFICULTY_LEVELS.keys())
        self.modes = self.SPECTATOR_MODES if spectator else MODES
        self.c["mode"] = min(self.c["mode"], len(self.modes) - 1)
        self.c["opponents"] = max(1, min(self.max_opponents, self.c["opponents"]))

    @property
    def c(self) -> dict[str, int]:
        return self.game.menu_choice

    @property
    def max_opponents(self) -> int:
        n = len(self.game.drivers)
        return n if self.spectator else max(1, n - 1)

    def _change(self, delta: int) -> None:
        row = self.rows[self.sel]
        if row == "Strecke":
            self.c["track"] = (self.c["track"] + delta) % len(TRACK_DEFS)
        elif row == "Modus":
            self.c["mode"] = (self.c["mode"] + delta) % len(self.modes)
        elif row == "Rennrunden":
            self.c["laps"] = max(1, min(30, self.c["laps"] + delta))
        elif row == "KI-Stärke":
            self.c["diff"] = (self.c["diff"] + delta) % len(self.diffs)
        elif row in ("Gegner", "Fahrerfeld"):
            low = 2 if self.spectator else 1
            self.c["opponents"] = max(low, min(self.max_opponents, self.c["opponents"] + delta))
        elif row == "Dein Team":
            self.c["team"] = (self.c["team"] + delta) % max(1, len(self.game.teams))
        elif row == "Startreifen":
            self.c["tyre"] = (self.c["tyre"] + delta) % len(ALL_COMPOUNDS)
        elif row == "Spieler":
            self.c["players"] = 2 if self.c.get("players", 1) == 1 else 1

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(self.rows)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(self.rows)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._change(-1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._change(1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            row = self.rows[self.sel]
            if row == "START":
                self.game.start_weekend(TRACK_DEFS[self.c["track"]].key, self.modes[self.c["mode"]][0],
                                        self.c["laps"], self.diffs[self.c["diff"]], self.c["opponents"],
                                        spectator=self.spectator)
            elif row == "ZURÜCK":
                self.game.go_to_menu()
            elif row == "Fahrzeug-Setup":
                self._open_garage()
            else:
                self.sel = self.rows.index("START")
        elif event.key == pygame.K_r and not self.spectator:
            self._random_race()
        elif event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()

    def _random_race(self) -> None:
        import random
        c = self.c
        c["track"] = random.randrange(len(TRACK_DEFS))
        c["team"] = random.randrange(max(1, len(self.game.teams)))
        c["tyre"] = random.randrange(len(COMPOUND_ORDER))
        c["mode"] = next((k for k, m in enumerate(self.modes) if m[0] == "race"), c["mode"])
        self.game.start_weekend(TRACK_DEFS[c["track"]].key, self.modes[c["mode"]][0], c["laps"],
                                self.diffs[c["diff"]], c["opponents"])

    def _open_garage(self) -> None:
        game = self.game
        team = game.teams[self.c["team"]] if game.teams else None

        def back() -> None:
            screen = SetupScreen(game, False)
            screen.sel = screen.rows.index("Fahrzeug-Setup")
            game.state = screen
        game.open_garage(TRACK_DEFS[self.c["track"]].key, team, back)

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)

    def _value(self, row: str) -> str:
        if row == "Fahrzeug-Setup":
            track = self.game.tracks[TRACK_DEFS[self.c["track"]].key]
            st = self.game.setup_for(track)
            own = track.definition.key in self.game.setups
            return (f"{'Eigenes' if own else 'Empfohlen'}: Flügel {st.front_wing:+d}/{st.rear_wing:+d} · Höhe {st.ride_height:+d}"
                    "  (ENTER)")
        if row == "Strecke":
            return TRACK_DEFS[self.c["track"]].name
        if row == "Modus":
            return self.modes[self.c["mode"]][1]
        if row == "Rennrunden":
            return f"{self.c['laps']} Runden"
        if row == "KI-Stärke":
            factor = DIFFICULTY_LEVELS[self.diffs[self.c["diff"]]]
            return f"{self.diffs[self.c['diff']]}  ({factor * 100:.0f}% Motorleistung)"
        if row in ("Gegner", "Fahrerfeld"):
            return f"{self.c['opponents']} KI-Fahrer"
        if row == "Dein Team":
            return self.game.teams[self.c["team"]].name if self.game.teams else "Referenzauto"
        if row == "Spieler":
            return "2 Spieler (Splitscreen)" if self.c.get("players", 1) == 2 else "1 Spieler"
        if row == "Startreifen":
            comp = COMPOUNDS[ALL_COMPOUNDS[self.c["tyre"]]]
            return f"{comp.name}  (Grip {comp.grip * 100:.0f}%)"
        return ""

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        accent = (40, 110, 200) if self.spectator else F1_RED
        pygame.draw.rect(screen, accent, (60, 40, 8, 60))
        draw_text(screen, "ZUSCHAUER-RENNEN" if self.spectator else "EINZELSPIELER", f.big, WHITE, (84, 36))
        draw_text(screen, "Nur KI-Fahrer · TV-Regie wählt die spannendsten Zweikämpfe" if self.spectator
                  else "Dein Team, deine Reifen - gegen trainierte neuronale Netze", f.small, GREY, (86, 86))

        px, py, pw = 60, 128, 500
        draw_panel(screen, (px, py, pw, 498), PANEL, 215)
        for i, row in enumerate(self.rows):
            ry = py + 14 + i * 44
            selected = i == self.sel
            if row in ("START", "ZURÜCK"):
                ry += 12 if row == "START" else 26
                pulse = 0.5 + 0.5 * math.sin(self.t * 4) if selected else 0.0
                base = accent if row == "START" else (90, 90, 100)
                col = tuple(int(c * (0.75 + 0.25 * pulse)) for c in base) if selected else \
                    tuple(c // 3 for c in base)
                h = 48 if row == "START" else 34
                pygame.draw.rect(screen, col, (px + 20, ry, pw - 40, h), border_radius=8)
                label = ("ZUSCHAUEN" if self.spectator else "RENNEN STARTEN") if row == "START" else "ZURÜCK"
                draw_text(screen, label, f.large if row == "START" else f.medium, WHITE,
                          (px + pw // 2, ry + h // 2), anchor="center")
                continue
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 12, ry, pw - 24, 38), border_radius=6)
                pygame.draw.rect(screen, accent, (px + 12, ry, 5, 38), border_radius=2)
            draw_text(screen, row.upper(), f.tiny, GREY, (px + 28, ry + 12), shadow=False)
            if row == "Startreifen":
                comp = COMPOUNDS[ALL_COMPOUNDS[self.c["tyre"]]]
                pygame.draw.circle(screen, comp.color, (px + 148, ry + 19), 8, 3)
            draw_text(screen, self._value(row), f.small_bold, WHITE, (px + 165, ry + 10), shadow=False)
            if selected:
                draw_text(screen, "<  >", f.medium, YELLOW, (px + pw - 24, ry + 19), anchor="midright")
        mode_key = self.modes[self.c["mode"]][0]
        draw_text(screen, MODE_HINTS[mode_key], f.small, (190, 190, 190), (px, py + 508))
        st = self.game.settings
        summary = (f"Einstellungen: Fahrhilfen {['Aus', 'Mittel', 'Voll'][st.assists]} · "
                   f"{'3D' if st.view3d else '2D'} · Schaden {DAMAGE_MODES[st.damage]} · "
                   f"Reifenverschleiß {TYRE_WEAR_MODES[st.tyre_wear][0]}")
        draw_text(screen, summary, f.tiny, (120, 200, 255), (px, py + 534), shadow=False)
        if not self.spectator:
            draw_text(screen, "R: Zufallsrennen (Strecke, Team, Reifen)", f.tiny, YELLOW, (px, py + 554),
                      shadow=False)
        self._draw_track_preview(screen)
        self._draw_roster(screen)

    def _draw_track_preview(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        td = TRACK_DEFS[self.c["track"]]
        track = self.game.tracks[td.key]
        box = pygame.Rect(600, 140, 380, 250)
        draw_panel(screen, box, PANEL, 215)
        track.draw_outline(screen, box.inflate(-30, -30), (230, 230, 230), 4)
        scale, off = track.minimap_transform(box.inflate(-30, -30))
        i = int(self.t * 40) % track.n
        p = track.center[i] * scale + off
        pygame.draw.circle(screen, F1_RED, p, 6)
        pygame.draw.circle(screen, WHITE, p, 6, 2)

        ib = pygame.Rect(992, 140, 248, 250)
        draw_panel(screen, ib, PANEL, 215)
        if self.rows[self.sel] in ("Dein Team", "Startreifen") and self.game.teams:
            self._draw_team_card(screen, ib)
            return
        draw_text(screen, td.name.upper(), f.large, WHITE, (ib.x + 16, ib.y + 14))
        draw_text(screen, td.country, f.small, GREY, (ib.x + 16, ib.y + 50))
        draw_text(screen, f"Länge: {track.length * 0.45 / 1000:.2f} km", f.small_bold, YELLOW, (ib.x + 16, ib.y + 80))
        draw_text(screen, f"Breite: {'eng' if td.half_width < 60 else 'breit'}  ·  "
                          f"Auslauf: {'Mauern' if td.runoff < 15 else 'Rasen'}", f.tiny, WHITE, (ib.x + 16, ib.y + 106))
        for k, line in enumerate(_wrap(td.character, f.small, ib.w - 32)):
            draw_text(screen, line, f.small, (200, 200, 205), (ib.x + 16, ib.y + 134 + k * 22), shadow=False)
        rec = self.game.records.tracks.get(td.key)
        mine = self.game.records.player.get(td.key)
        if rec:
            draw_text(screen, _fit(f"Rekord {format_time(rec['time'])} · {rec['driver']}", f.tiny, ib.w - 32), f.tiny,
                      (175, 80, 255), (ib.x + 16, ib.bottom - 40), shadow=False)
        if mine:
            draw_text(screen, f"Deine Bestzeit {format_time(mine['time'])}", f.tiny, (40, 210, 90),
                      (ib.x + 16, ib.bottom - 22), shadow=False)

    def _draw_team_card(self, screen: pygame.Surface, ib: pygame.Rect) -> None:
        f = self.game.fonts
        team = self.game.teams[self.c["team"]]
        pygame.draw.rect(screen, team.color, (ib.x, ib.y, ib.w, 6), border_radius=3)
        draw_text(screen, team.name.upper(), f.medium, WHITE, (ib.x + 16, ib.y + 16))
        rank = sorted(self.game.teams, key=lambda t: -t.rating).index(team) + 1
        draw_text(screen, f"Auto-Ranking: P{rank} von {len(self.game.teams)}", f.tiny, YELLOW, (ib.x + 16, ib.y + 46))
        stats = [("Motor", team.engine), ("Aero / Grip", team.aero), ("Topspeed", team.top_speed),
                 ("Bremsen", team.brakes), ("Reifenschonung", 2.0 - team.tyre_wear)]
        for k, (label, val) in enumerate(stats):
            y = ib.y + 72 + k * 32
            draw_text(screen, label, f.tiny, GREY, (ib.x + 16, y), shadow=False)
            draw_text(screen, f"{(val - 1) * 100:+.0f}%", f.tiny, WHITE, (ib.right - 16, y), anchor="topright",
                      shadow=False)
            bar = (val - 0.94) / 0.12
            pygame.draw.rect(screen, (45, 45, 52), (ib.x + 16, y + 16, ib.w - 32, 7), border_radius=3)
            pygame.draw.rect(screen, team.color if team.color != (7, 11, 54) else (90, 100, 200),
                             (ib.x + 16, y + 16, (ib.w - 32) * max(0.05, min(1.0, bar)), 7), border_radius=3)

    def _draw_roster(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        brains = self.game.brains
        track_key = TRACK_DEFS[self.c["track"]].key
        box = pygame.Rect(600, 402, 640, 298)
        draw_panel(screen, box, PANEL, 215)
        roster = self.game.field_preview(self.spectator, self.c["opponents"])
        draw_text(screen, f"STARTERFELD · {len(roster) + (0 if self.spectator else 1)} AUTOS  "
                          "(data/driver_pool.json)", f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
        per_col = 11
        cols = 1 if len(roster) <= per_col else 2
        col_w = (box.w - 20) // cols
        if cols == 1:
            for x, h in ((300, "GEHIRN / STAND"), (450, "WERTUNG"), (530, "TEST-RUNDE")):
                draw_text(screen, h, f.tiny, GREY, (box.x + x, box.y + 10), shadow=False)
        row_h = min(23, (box.h - 38) // per_col)
        for i, prof in enumerate(roster):
            col, row = divmod(i, per_col)
            x, y = box.x + 10 + col * col_w, box.y + 34 + row * row_h
            cp = brains.checkpoint(prof.brain, prof.checkpoint) or {}
            lap = (cp.get("benchmark") or {}).get(track_key)
            rating = prof.rating or {"final": 90, "mid": 84, "early": 78}.get(prof.checkpoint, 84)
            pygame.draw.rect(screen, prof.color, (x + 4, y + 3, 5, row_h - 6))
            if cols == 1:
                draw_text(screen, _fit(prof.name, f.small_bold, 150), f.small_bold, WHITE, (x + 18, y), shadow=False)
                draw_text(screen, _fit(prof.team, f.tiny, 115), f.tiny, (150, 150, 160), (x + 172, y + 3),
                          shadow=False)
                draw_text(screen, f"{prof.brain} / {prof.checkpoint}", f.tiny, (255, 200, 120), (x + 290, y + 3),
                          shadow=False)
                draw_text(screen, str(rating), f.mono, YELLOW, (x + 450, y + 2), shadow=False)
                draw_text(screen, f"{lap:.2f}s" if lap else "--", f.mono, (120, 230, 140) if lap else GREY,
                          (x + 520, y + 2), shadow=False)
            else:
                draw_text(screen, _fit(prof.name, f.tiny, 130), f.tiny, WHITE, (x + 16, y + 3), shadow=False)
                draw_text(screen, f"{prof.brain[:4]}/{prof.checkpoint}", f.tiny, (255, 200, 120), (x + 152, y + 3),
                          shadow=False)
                draw_text(screen, str(rating), f.mono, YELLOW, (x + 250, y + 2), shadow=False)


class SettingsScreen:

    ROWS = ["Sprache", "Spielername", "Lenkrad & Controller", "Fahrhilfen", "Ansicht", "Schaden", "Reifenverschleiß", "Wetter", "Safety Car",
            "TV-Regie (Zuschauer)", "Sound", "Einheiten", "Partikel & Effekte", "Bildrate", "FPS anzeigen",
            "Vollbild", "ZURÜCK"]
    HELP = {
        "Spielername": "Tippen zum Ändern, Rücktaste löscht. Erscheint in Zeitentabellen und auf dem Podium.",
        "Lenkrad & Controller": "ENTER öffnet die Einrichtung: Wheelbase, Pedale und Gamepads kalibrieren, "
                                "Lenkbereich, Totzone, Vibration und Tastenbelegung.",
        "Fahrhilfen": "Mittel: Stabilitätskontrolle + farbige Bremslinie. Voll: zusätzlich automatische "
                      "Bremshilfe vor Kurven.",
        "Ansicht": "Startansicht im Rennen. Im Rennen jederzeit mit V umschalten.",
        "Schaden": "An: Treffer beschädigen Frontflügel, Heck und Aufhängung (weniger Grip/Tempo, Auto zieht). "
                   "Reparatur beim Boxenstopp. Mit Ausfällen: zerstörte Aufhängung = DNF.",
        "Reifenverschleiß": "Doppelt macht Strategie und Boxenstopps wichtiger, Aus deaktiviert den Verschleiß.",
        "Wetter": "Trocken: nie Regen. Wechselhaft: Schauer können kommen und gehen - Strecke wird nass und "
                  "trocknet wieder ab. Regen: nasses Rennen. Bei Nässe Intermediates (grün) oder Wets (blau) holen.",
        "TV-Regie (Zuschauer)": "Die Kamera springt automatisch zu engen Zweikämpfen (im Rennen mit A umschalten).",
        "Sprache": "Sprache des Spiels / game language. Standard: English.",
        "Safety Car": "Bei Ausfällen und schweren Unfällen: Safety Car (Feld fährt geschlossen hinter dem SC, "
                      "Restart) oder Virtuelles Safety Car (alle langsamer). Gelbe Flaggen, Reifenschäden.",
        "Sound": "V6-Turbo-Motor mit Zündfolge, Turbopfeifen, Getriebesurren, Schaltrucken und Fehlzündungen "
                 "beim Gaswegnehmen, Reifenquietschen, Kies, Fahrtwind, Einschläge und Startampel - Gegner in "
                 "Stereo mit Dopplereffekt. Alles live erzeugt, ohne Audiodateien.",
        "FPS anzeigen": "Bildrate unten rechts einblenden (im Rennen auch mit F3).",
        "Einheiten": "Geschwindigkeit in km/h oder mph - im HUD, in der Garage und in der Analyse.",
        "Partikel & Effekte": "Reifenrauch, Funken bei Einschlägen, Staub neben der Strecke und Bremsspuren auf "
                              "dem Asphalt.",
        "Bildrate": "Höhere Bildrate = flüssiger, braucht mehr Rechenleistung.",
        "Vollbild": "Skaliert das Spiel auf den ganzen Bildschirm.",
        "ZURÜCK": "Einstellungen werden automatisch gespeichert.",
    }

    def __init__(self, game: "Game") -> None:
        self.game = game
        self.sel = 0
        self.bg = _Background()
        self.t = 0.0

    @property
    def st(self):
        return self.game.settings

    def _value(self, row: str) -> str:
        st = self.st
        return {
            "Spielername": st.player_name + ("_" if self.rows_sel == "Spielername" and int(self.t * 2) % 2 else ""),
            "Fahrhilfen": ASSIST_NAMES[st.assists],
            "Lenkrad & Controller": self.game.controls.device_name() if self.game.controls.connected
            else "nur Tastatur",
            "Ansicht": "3D-Verfolgerkamera" if st.view3d else "2D-Draufsicht",
            "Schaden": DAMAGE_MODES[st.damage],
            "Reifenverschleiß": TYRE_WEAR_MODES[st.tyre_wear][0],
            "TV-Regie (Zuschauer)": "An" if st.auto_camera else "Aus",
            "Sound": VOLUMES[st.sound][0],
            "Safety Car": "An" if st.safety_car else "Aus",
            "Wetter": WEATHER_MODES[st.weather],
            "Sprache": LANGUAGES.get(st.language, "English"),
            "FPS anzeigen": "An" if st.show_fps else "Aus",
            "Einheiten": UNITS[st.units][0],
            "Partikel & Effekte": EFFECT_LEVELS[st.effects],
            "Bildrate": f"{st.fps} FPS",
            "Vollbild": "An" if st.fullscreen else "Aus",
        }.get(row, "")

    @property
    def rows_sel(self) -> str:
        return self.ROWS[self.sel]

    def _change(self, delta: int) -> None:
        st, row = self.st, self.rows_sel
        if row == "Fahrhilfen":
            st.assists = (st.assists + delta) % 3
        elif row == "Ansicht":
            st.view3d = not st.view3d
        elif row == "Schaden":
            keys = list(DAMAGE_MODES)
            st.damage = keys[(keys.index(st.damage) + delta) % len(keys)]
        elif row == "Reifenverschleiß":
            keys = list(TYRE_WEAR_MODES)
            st.tyre_wear = keys[(keys.index(st.tyre_wear) + delta) % len(keys)]
        elif row == "TV-Regie (Zuschauer)":
            st.auto_camera = not st.auto_camera
        elif row == "Safety Car":
            st.safety_car = not st.safety_car
        elif row == "Wetter":
            keys = list(WEATHER_MODES)
            st.weather = keys[(keys.index(st.weather) + delta) % len(keys)]
        elif row == "Sprache":
            st.language = "de" if st.language == "en" else "en"
            set_language(st.language)
            clear_render_caches()
            self.game.hud.clear_caches()
        elif row == "Sound":
            keys = list(VOLUMES)
            st.sound = keys[(keys.index(st.sound) + delta) % len(keys)]
            self.game.sound.set_volume(st.sound)
        elif row == "FPS anzeigen":
            st.show_fps = not st.show_fps
        elif row == "Einheiten":
            st.units = "mph" if st.units == "kmh" else "kmh"
        elif row == "Partikel & Effekte":
            keys = list(EFFECT_LEVELS)
            st.effects = keys[(keys.index(st.effects) + delta) % len(keys)]
        elif row == "Bildrate":
            st.fps = FPS_OPTIONS[(FPS_OPTIONS.index(st.fps) + delta) % len(FPS_OPTIONS)]
        elif row == "Vollbild":
            st.fullscreen = not st.fullscreen
            self.game.apply_display()
        else:
            return
        st.save()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        row = self.rows_sel
        if event.key in (pygame.K_UP,):
            self.sel = (self.sel - 1) % len(self.ROWS)
        elif event.key in (pygame.K_DOWN,):
            self.sel = (self.sel + 1) % len(self.ROWS)
        elif row == "Spielername" and event.key == pygame.K_BACKSPACE:
            self.st.player_name = self.st.player_name[:-1]
            self.game.apply_player_name()
        elif row == "Spielername" and event.unicode and event.unicode.isprintable() and \
                event.key not in (pygame.K_RETURN, pygame.K_ESCAPE) and len(self.st.player_name) < 20:
            self.st.player_name += event.unicode
            self.game.apply_player_name()
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._change(-1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._change(1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            if row == "ZURÜCK":
                self._leave()
            elif row == "Lenkrad & Controller":
                from .controls_screen import ControlsScreen
                self.game.state = ControlsScreen(self.game)
            else:
                self._change(1)
        elif event.key == pygame.K_ESCAPE:
            self._leave()

    def _leave(self) -> None:
        if not self.st.player_name.strip():
            self.st.player_name = "Du (Spieler)"
            self.game.apply_player_name()
        self.st.save()
        self.game.go_to_menu()

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, (200, 200, 210), (60, 40, 8, 60))
        draw_text(screen, "EINSTELLUNGEN", f.big, WHITE, (84, 36))
        draw_text(screen, "Gespeichert in data/settings.json", f.small, GREY, (86, 86))
        px, py, pw = 60, 124, 640
        draw_panel(screen, (px, py, pw, 560), PANEL, 215)
        rh = min(41, (560 - 20) // len(self.ROWS))
        for i, row in enumerate(self.ROWS):
            ry = py + 10 + i * rh
            selected = i == self.sel
            if row == "ZURÜCK":
                col = (120, 120, 130) if selected else (50, 50, 58)
                pygame.draw.rect(screen, col, (px + 20, ry + 4, pw - 40, rh - 4), border_radius=8)
                draw_text(screen, "ZURÜCK", f.medium, WHITE, (px + pw // 2, ry + 2 + rh // 2), anchor="center")
                continue
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 12, ry, pw - 24, rh - 2), border_radius=6)
                pygame.draw.rect(screen, (200, 200, 210), (px + 12, ry, 5, rh - 2), border_radius=2)
            mid = ry + (rh - 2) // 2
            draw_text(screen, row.upper(), f.tiny, GREY, (px + 28, mid), anchor="midleft", shadow=False)
            draw_text(screen, self._value(row), f.small_bold, CYAN if row == "Spielername" else WHITE,
                      (px + 250, mid), anchor="midleft", shadow=False)
            if selected and row != "Spielername":
                draw_text(screen, "<  >", f.medium, YELLOW, (px + pw - 24, mid), anchor="midright")
        hb = pygame.Rect(730, 140, 510, 200)
        draw_panel(screen, hb, PANEL, 215)
        draw_text(screen, self.rows_sel.upper(), f.medium, WHITE, (hb.x + 18, hb.y + 16))
        for k, line in enumerate(_wrap(self.HELP.get(self.rows_sel, ""), f.small, hb.w - 36)):
            draw_text(screen, line, f.small, (205, 205, 210), (hb.x + 18, hb.y + 56 + k * 24), shadow=False)
        draw_text(screen, "Pfeile hoch/runter wählen · links/rechts ändern · ESC zurück", f.small, GREY,
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30), anchor="center")


class ResultsScreen:

    def __init__(self, game: "Game", title: str, subtitle: str, headers: list[str], rows: list[tuple[str, ...]],
                 player_name: str, continue_label: str, on_continue: Callable[[], None],
                 col_x: list[int] | None = None) -> None:
        self.game = game
        self.title = title
        self.subtitle = subtitle
        self.headers = headers
        self.rows = rows
        self.player_name = player_name
        self.continue_label = continue_label
        self.on_continue = on_continue
        self.col_x = col_x or [0, 60, 300, 520, 680, 800]
        self.bg = _Background()
        self.t = 0.0

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.on_continue()
            elif event.key == pygame.K_ESCAPE:
                self.game.go_to_menu()

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, F1_RED, (60, 40, 8, 60))
        draw_text(screen, self.title.upper(), f.big, WHITE, (84, 36))
        draw_text(screen, self.subtitle, f.small, GREY, (86, 86))
        x0, y0 = 60, 118
        w = SCREEN_WIDTH - 120
        row_h = min(34, (SCREEN_HEIGHT - y0 - 44 - 56) // max(1, len(self.rows)))
        compact = row_h < 28
        draw_panel(screen, (x0, y0, w, 44 + row_h * len(self.rows)), PANEL, 220)
        for k, h in enumerate(self.headers):
            draw_text(screen, h, f.tiny, GREY, (x0 + 20 + self.col_x[k], y0 + 14), shadow=False)
        for i, row in enumerate(self.rows):
            y = y0 + 40 + i * row_h
            if self.t * 12 < i:
                break
            is_player = row[1] == self.player_name
            if is_player:
                pygame.draw.rect(screen, (0, 80, 110), (x0 + 6, y - 2, w - 12, row_h - 2), border_radius=5)
            elif i % 2 == 0:
                pygame.draw.rect(screen, (30, 32, 40), (x0 + 6, y - 2, w - 12, row_h - 2), border_radius=5)
            for k, val in enumerate(row):
                if compact:
                    font = f.small_bold if k < 3 else f.mono
                else:
                    font = f.medium if k == 0 else f.mono if k >= 3 else f.small_bold
                col = CYAN if is_player and k == 1 else WHITE
                if k == 0 and i < 3:
                    col = [(255, 215, 0), (200, 200, 210), (205, 127, 50)][i]
                draw_text(screen, val, font, col, (x0 + 20 + self.col_x[k], y + (0 if compact else 4)),
                          shadow=False)
        pulse = 0.6 + 0.4 * math.sin(self.t * 4)
        draw_text(screen, f"ENTER: {self.continue_label}    ·    ESC: Hauptmenü", f.medium,
                  tuple(int(c * pulse) for c in WHITE), (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 32), anchor="center")


class PodiumScreen:

    def __init__(self, game: "Game", session: "RaceSession", on_continue: Callable[[], None],
                 continue_label: str = "zurück zum Hauptmenü") -> None:
        self.game = game
        self.on_continue = on_continue
        self.continue_label = continue_label
        self.track_name = session.track.name
        order = session.standings()
        self.rows = session.results_rows()
        self.podium = order[:3]
        self.player_car = session.player
        self.player_place = order.index(session.player) + 1 if session.player is not None else 0
        gains = [(c.grid_slot - (k + 1), -k, c) for k, c in enumerate(order) if not c.dnf and c.grid_slot]
        self.driver_of_day = max(gains, key=lambda g: (g[0], g[1]))[::2] if gains else None
        self.sprites = [pygame.transform.rotozoom(build_car_sprite(c.color, c.profile.helmet, 3.0), 90, 1.0)
                        for c in self.podium]
        self.bg = _Background()
        self.t = 0.0
        self.confetti = [self._new_confetti(random.uniform(-SCREEN_HEIGHT, 0)) for _ in range(140)]

    @staticmethod
    def _new_confetti(y: float) -> list:
        return [random.uniform(0, 700), y, random.uniform(-30, 30), random.uniform(60, 160),
                random.choice([(255, 215, 0), (225, 6, 0), (255, 255, 255), (0, 200, 255), (60, 220, 90)]),
                random.uniform(0, math.tau)]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE,
                                                          pygame.K_ESCAPE):
            self.on_continue()

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)
        for c in self.confetti:
            c[0] += c[2] * dt + math.sin(self.t * 3 + c[5]) * 20 * dt
            c[1] += c[3] * dt
            c[5] += dt * 5
            if c[1] > SCREEN_HEIGHT:
                c[:] = self._new_confetti(-10)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        draw_text(screen, f"PODIUM · GRAND PRIX VON {self.track_name.upper()}", f.large, WHITE, (40, 30))
        place_txt = {1: "SIEG! Herzlichen Glückwunsch!", 2: "Platz 2 - starkes Rennen!",
                     3: "Platz 3 - aufs Podium gefahren!"}
        if self.player_place == 0:
            headline = f"Sieg für {self.podium[0].name} ({self.podium[0].profile.team})"
        elif self.podium and self.player_car is not None and getattr(self.player_car, "dsq", False):
            headline = "DISQUALIFIZIERT - " + self.player_car.dsq_reason
        elif self.podium and session_dnf(self.player_car):
            headline = "Ausgefallen - nächstes Mal!"
        else:
            headline = place_txt.get(self.player_place, f"Du bist auf Platz {self.player_place} ins Ziel gekommen.")
        draw_text(screen, headline, f.medium, CYAN, (40, 72))
        if self.driver_of_day is not None and self.driver_of_day[0] > 0:
            gain, car = self.driver_of_day
            draw_text(screen, "FAHRER DES TAGES", f.tiny, (255, 200, 40), (40, 108), shadow=False)
            draw_text(screen, f"{car.name}  (+{gain} Plätze, von P{car.grid_slot})", f.small_bold,
                      CYAN if car.is_player else WHITE, (40, 124))

        base_y = 600
        layout = [(1, 70, 150), (0, 260, 220), (2, 450, 110)]
        medal = [(255, 215, 0), (200, 200, 210), (205, 127, 50)]
        for idx, x, height in layout:
            if idx >= len(self.podium):
                continue
            car = self.podium[idx]
            rise = min(1.0, self.t * 1.5 - idx * 0.2)
            if rise <= 0:
                continue
            h = int(height * rise)
            rect = pygame.Rect(x, base_y - h, 180, h)
            pygame.draw.rect(screen, (40, 42, 52), rect, border_top_left_radius=8, border_top_right_radius=8)
            pygame.draw.rect(screen, medal[idx], (x, base_y - h, 180, 6), border_radius=3)
            draw_text(screen, str(idx + 1), f.huge, medal[idx], (rect.centerx, rect.y + 50), anchor="center")
            if rise >= 1.0:
                spr = self.sprites[idx]
                screen.blit(spr, spr.get_rect(midbottom=(rect.centerx, rect.y - 46)))
                name_col = CYAN if car.is_player else WHITE
                draw_text(screen, car.name, f.medium, name_col, (rect.centerx, rect.y - 34), anchor="center")
                draw_text(screen, car.profile.team, f.tiny, GREY, (rect.centerx, rect.y - 14), anchor="center")
        pygame.draw.rect(screen, (60, 62, 72), (50, base_y, 600, 10))

        for x, y, _, _, col, rot in self.confetti:
            w = 3 + 3 * abs(math.sin(rot))
            pygame.draw.rect(screen, col, (x + 30, y, w, 6))

        bx, by = 690, 110
        rh = min(30, (SCREEN_HEIGHT - by - 90) // max(1, len(self.rows)))
        draw_panel(screen, (bx, by, 560, 40 + rh * len(self.rows)), PANEL, 220)
        draw_text(screen, "KLASSEMENT", f.tiny, GREY, (bx + 14, by + 12), shadow=False)
        draw_text(screen, "ABSTAND (+STRAFE)", f.tiny, GREY, (bx + 300, by + 12), shadow=False)
        draw_text(screen, "BESTE RUNDE", f.tiny, GREY, (bx + 462, by + 12), shadow=False)
        for i, row in enumerate(self.rows):
            y = by + 36 + i * rh
            is_player = row[1] == self.game.player_name
            if is_player:
                pygame.draw.rect(screen, (0, 80, 110), (bx + 6, y - 3, 548, rh - 3), border_radius=5)
            pos_col = medal[i] if i < 3 else WHITE
            draw_text(screen, row[0], f.small_bold, pos_col, (bx + 14, y), shadow=False)
            draw_text(screen, _fit(row[1], f.small_bold, 240), f.small_bold, CYAN if is_player else WHITE, (bx + 50, y),
                      shadow=False)
            draw_text(screen, row[3], f.mono, WHITE, (bx + 300, y + 2), shadow=False)
            draw_text(screen, row[4], f.mono, (200, 200, 200), (bx + 462, y + 2), shadow=False)

        pulse = 0.6 + 0.4 * math.sin(self.t * 4)
        draw_text(screen, f"ENTER: {self.continue_label}", f.medium, tuple(int(c * pulse) for c in WHITE),
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30), anchor="center")


class ChampionshipScreen:

    SETUP_ROWS = ["Teilnahme", "Format", "Rennrunden", "KI-Stärke", "Fahrerfeld", "Dein Team", "START", "ZURÜCK"]
    SEASON_ROWS = ["WEITER", "ZURÜCK", "SAISON ABBRECHEN"]

    def __init__(self, game: "Game") -> None:
        self.game = game
        self.bg = _Background()
        self.t = 0.0
        self.diffs = list(DIFFICULTY_LEVELS.keys())
        self.spectator = False
        self.format = 0
        self.confirm_abort = False
        self.sel = 0
        self.c["opponents"] = max(2, min(len(game.drivers), self.c["opponents"]))

    @property
    def c(self) -> dict[str, int]:
        return self.game.menu_choice

    @property
    def champ(self) -> "Championship | None":
        return self.game.championship

    @property
    def rows(self) -> list[str]:
        if self.champ is None:
            return self.SETUP_ROWS if not self.spectator else [r for r in self.SETUP_ROWS if r != "Dein Team"]
        return self.SEASON_ROWS

    def _change(self, delta: int) -> None:
        row = self.rows[self.sel]
        if row == "Teilnahme":
            self.spectator = not self.spectator
        elif row == "Format":
            self.format = (self.format + delta) % len(FORMATS)
        elif row == "Rennrunden":
            self.c["laps"] = max(1, min(30, self.c["laps"] + delta))
        elif row == "KI-Stärke":
            self.c["diff"] = (self.c["diff"] + delta) % len(self.diffs)
        elif row == "Fahrerfeld":
            self.c["opponents"] = max(2, min(len(self.game.drivers), self.c["opponents"] + delta))
        elif row == "Dein Team":
            self.c["team"] = (self.c["team"] + delta) % max(1, len(self.game.teams))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        rows = self.rows
        if event.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(rows)
            self.confirm_abort = False
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(rows)
            self.confirm_abort = False
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._change(-1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._change(1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate(rows[self.sel])
        elif event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()

    def _activate(self, row: str) -> None:
        game = self.game
        if row == "ZURÜCK":
            game.go_to_menu()
        elif row == "START":
            team = game.teams[self.c["team"]].name if game.teams and not self.spectator else ""
            game.championship = Championship(
                rounds=[d.key for d in TRACK_DEFS], format=FORMATS[self.format][0], laps=self.c["laps"],
                difficulty=self.diffs[self.c["diff"]], field_size=self.c["opponents"], spectator=self.spectator,
                player_name=game.settings.player_name, team=team)
            game.championship.save()
            self.sel = 0
        elif row == "WEITER":
            if self.champ is not None and self.champ.finished:
                Championship.delete()
                game.championship = None
                self.sel = 0
            else:
                game.start_championship_round()
        elif row == "SAISON ABBRECHEN":
            if self.confirm_abort:
                Championship.delete()
                game.championship = None
                self.sel = 0
                self.confirm_abort = False
            else:
                self.confirm_abort = True
        elif row in self.SETUP_ROWS:
            self._change(1)

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, (255, 200, 40), (60, 40, 8, 60))
        draw_text(screen, "WELTMEISTERSCHAFT", f.big, WHITE, (84, 36))
        champ = self.champ
        if champ is None:
            draw_text(screen, f"Neue Saison · {len(TRACK_DEFS)} Rennen · Punkte 25-18-15-12-10-8-6-4-2-1 "
                              f"+1 schnellste Runde", f.small, GREY, (86, 86))
            self._draw_setup(screen)
            self._draw_calendar(screen, pygame.Rect(600, 128, 640, 300), None)
            return
        sub = (f"Runde {min(champ.round + 1, len(champ.rounds))}/{len(champ.rounds)} · "
               f"{dict(FORMATS)[champ.format]} · {champ.laps} Rd. · KI {champ.difficulty}"
               + (" · Zuschauer" if champ.spectator else f" · {champ.player_name} ({champ.team})"))
        draw_text(screen, sub, f.small, GREY, (86, 86))
        self._draw_driver_table(screen, champ)
        self._draw_calendar(screen, pygame.Rect(680, 128, 560, 232), champ)
        self._draw_team_table(screen, champ)
        self._draw_season_buttons(screen, champ)

    def _draw_setup(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        px, py, pw = 60, 128, 500
        accent = (255, 200, 40)
        draw_panel(screen, (px, py, pw, 470), PANEL, 215)
        for i, row in enumerate(self.rows):
            ry = py + 14 + i * 50
            selected = i == self.sel
            if row in ("START", "ZURÜCK"):
                ry += 6
                h = 48 if row == "START" else 34
                pulse = 0.5 + 0.5 * math.sin(self.t * 4) if selected else 0.0
                base = accent if row == "START" else (90, 90, 100)
                col = tuple(int(c * (0.75 + 0.25 * pulse)) for c in base) if selected else tuple(c // 3 for c in base)
                pygame.draw.rect(screen, col, (px + 20, ry, pw - 40, h), border_radius=8)
                label = "SAISON STARTEN" if row == "START" else "ZURÜCK"
                draw_text(screen, label, f.large if row == "START" else f.medium, WHITE if row != "START" or not
                          selected else (30, 20, 0), (px + pw // 2, ry + h // 2), anchor="center")
                continue
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 12, ry, pw - 24, 40), border_radius=6)
                pygame.draw.rect(screen, accent, (px + 12, ry, 5, 40), border_radius=2)
            draw_text(screen, row.upper(), f.tiny, GREY, (px + 28, ry + 13), shadow=False)
            draw_text(screen, self._value(row), f.small_bold, WHITE, (px + 165, ry + 11), shadow=False)
            if selected:
                draw_text(screen, "<  >", f.medium, YELLOW, (px + pw - 24, ry + 20), anchor="midright")
        draw_text(screen, "Der Stand wird nach jedem Rennen gespeichert (data/championship.json).", f.tiny,
                  (120, 200, 255), (px, py + 482), shadow=False)

    def _value(self, row: str) -> str:
        if row == "Teilnahme":
            return "Zuschauer (nur KI)" if self.spectator else f"Fahrer: {self.game.settings.player_name}"
        if row == "Format":
            return FORMATS[self.format][1]
        if row == "Rennrunden":
            return f"{self.c['laps']} Runde{'n' if self.c['laps'] != 1 else ''} pro Rennen"
        if row == "KI-Stärke":
            return self.diffs[self.c["diff"]]
        if row == "Fahrerfeld":
            return f"{self.c['opponents']} KI-Fahrer"
        if row == "Dein Team":
            return self.game.teams[self.c["team"]].name if self.game.teams else "Referenzauto"
        return ""

    def _draw_calendar(self, screen: pygame.Surface, box: pygame.Rect, champ: "Championship | None") -> None:
        f = self.game.fonts
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "KALENDER", f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
        row_h = (box.h - 34) // max(1, len(TRACK_DEFS))
        for k, td in enumerate(TRACK_DEFS):
            y = box.y + 32 + k * row_h
            current = champ is not None and k == champ.round
            if current:
                pygame.draw.rect(screen, (70, 56, 10), (box.x + 6, y - 3, box.w - 12, row_h - 2), border_radius=5)
            draw_text(screen, f"{k + 1}", f.small_bold, YELLOW if current else GREY, (box.x + 16, y), shadow=False)
            draw_text(screen, td.name, f.small_bold, WHITE, (box.x + 44, y), shadow=False)
            draw_text(screen, td.country, f.tiny, GREY, (box.x + 230, y + 3), shadow=False)
            if champ is None:
                continue
            winner = champ.winner_of(k)
            if winner:
                draw_text(screen, _fit(f"Sieg: {winner}", f.tiny, box.w - 360), f.tiny, (255, 215, 0),
                          (box.x + 350, y + 3), shadow=False)
            elif current:
                draw_text(screen, "NÄCHSTES RENNEN", f.tiny, YELLOW, (box.x + 350, y + 3), shadow=False)

    def _draw_driver_table(self, screen: pygame.Surface, champ: "Championship") -> None:
        f = self.game.fonts
        table = champ.driver_table()
        box = pygame.Rect(60, 128, 600, 400)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "FAHRERWERTUNG", f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
        for x, h in ((330, "SIEGE"), (400, "PODIEN"), (480, "PUNKTE")):
            draw_text(screen, h, f.tiny, GREY, (box.x + x, box.y + 10), shadow=False)
        if not table:
            draw_text(screen, "Noch keine Rennen gefahren.", f.small, GREY, (box.x + 14, box.y + 44), shadow=False)
        row_h = min(28, (box.h - 40) // max(1, len(table)))
        medal = [(255, 215, 0), (200, 200, 210), (205, 127, 50)]
        colors = {t.name: t.color for t in self.game.teams}
        name_font = f.small_bold if row_h >= 20 else f.tiny
        for i, e in enumerate(table):
            y = box.y + 34 + i * row_h
            if y + row_h > box.bottom:
                break
            if e["player"]:
                pygame.draw.rect(screen, (0, 80, 110), (box.x + 6, y - 2, box.w - 12, row_h - 2), border_radius=5)
            draw_text(screen, f"{i + 1}", name_font, medal[i] if i < 3 else WHITE, (box.x + 14, y), shadow=False)
            pygame.draw.rect(screen, colors.get(e["team"], (150, 150, 150)), (box.x + 44, y + 2, 5, row_h - 4))
            draw_text(screen, _fit(e["name"], name_font, 140), name_font, CYAN if e["player"] else WHITE,
                      (box.x + 56, y), shadow=False)
            draw_text(screen, _fit(e["team"], f.tiny, 120), f.tiny, GREY, (box.x + 204, y + 3), shadow=False)
            draw_text(screen, str(e["wins"]), f.mono, WHITE, (box.x + 346, y + 1), shadow=False)
            draw_text(screen, str(e["podiums"]), f.mono, WHITE, (box.x + 420, y + 1), shadow=False)
            draw_text(screen, str(e["points"]), f.mono, YELLOW, (box.x + 520, y + 1), anchor="topright", shadow=False)
            if e["last"]:
                draw_text(screen, f"+{e['last']}", f.tiny, GREEN, (box.x + 530, y + 3), shadow=False)

    def _draw_team_table(self, screen: pygame.Surface, champ: "Championship") -> None:
        f = self.game.fonts
        table = champ.team_table()
        box = pygame.Rect(680, 372, 560, 300)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "TEAMWERTUNG", f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
        colors = {t.name: t.color for t in self.game.teams}
        row_h = min(24, (box.h - 40) // max(1, len(table)))
        best = max([e["points"] for e in table] + [1])
        for i, e in enumerate(table):
            y = box.y + 32 + i * row_h
            col = colors.get(e["team"], (150, 150, 150))
            draw_text(screen, f"{i + 1}", f.tiny, WHITE, (box.x + 14, y + 2), shadow=False)
            draw_text(screen, _fit(e["team"], f.tiny, 140), f.tiny, WHITE, (box.x + 40, y + 2), shadow=False)
            bar_w = int(300 * e["points"] / best)
            pygame.draw.rect(screen, (45, 45, 52), (box.x + 190, y + 5, 300, 10), border_radius=4)
            pygame.draw.rect(screen, col if sum(col) > 120 else (90, 100, 200), (box.x + 190, y + 5, bar_w, 10),
                             border_radius=4)
            draw_text(screen, str(e["points"]), f.mono, YELLOW, (box.right - 14, y), anchor="topright", shadow=False)

    def _draw_season_buttons(self, screen: pygame.Surface, champ: "Championship") -> None:
        f = self.game.fonts
        x, y, w = 60, 544, 600
        labels = {
            "WEITER": ("NEUE SAISON" if champ.finished else
                       f"WEITER: RUNDE {champ.round + 1} · {self.game.tracks[champ.next_track].name.upper()}"),
            "ZURÜCK": "HAUPTMENÜ",
            "SAISON ABBRECHEN": "WIRKLICH ABBRECHEN? ENTER = JA" if self.confirm_abort else "SAISON ABBRECHEN",
        }
        heights = {"WEITER": 52, "ZURÜCK": 34, "SAISON ABBRECHEN": 34}
        for i, row in enumerate(self.rows):
            h = heights[row]
            selected = i == self.sel
            base = (255, 200, 40) if row == "WEITER" else (200, 60, 60) if row == "SAISON ABBRECHEN" else (90, 90, 100)
            if row != "WEITER":
                bw = (w - 10) // 2
                bx = x if row == "ZURÜCK" else x + bw + 10
                rect = pygame.Rect(bx, y + 62, bw, h)
            else:
                rect = pygame.Rect(x, y, w, h)
            pulse = 0.5 + 0.5 * math.sin(self.t * 4) if selected else 0.0
            col = tuple(int(c * (0.75 + 0.25 * pulse)) for c in base) if selected else tuple(c // 3 for c in base)
            pygame.draw.rect(screen, col, rect, border_radius=8)
            text_col = (30, 20, 0) if row == "WEITER" and selected else WHITE
            draw_text(screen, labels[row], f.medium if row == "WEITER" else f.small_bold, text_col, rect.center,
                      anchor="center", shadow=False)
        if champ.finished:
            table = champ.driver_table()
            if table:
                pulse = 0.7 + 0.3 * math.sin(self.t * 3)
                draw_text(screen, f"WELTMEISTER: {table[0]['name']}", f.large,
                          tuple(int(c * pulse) for c in (255, 215, 0)), (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30),
                          anchor="center")
                return
        draw_text(screen, "Pfeile wählen · ENTER bestätigen · ESC Hauptmenü", f.tiny, (150, 150, 160),
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 26), anchor="center", shadow=False)


class AnalysisScreen:

    def __init__(self, game: "Game", session: "RaceSession", on_continue: Callable[[], None],
                 continue_label: str) -> None:
        self.game = game
        self.on_continue = on_continue
        self.continue_label = continue_label
        self.bg = _Background()
        self.t = 0.0
        order = session.standings()
        self.track_name = session.track.name
        self.laps = session.total_laps
        self.rows = []
        for k, car in enumerate(order):
            hist = list(session.pos_history.get(car, [car.grid_slot]))
            if not car.dnf:
                hist = hist[:self.laps]
                hist += [hist[-1]] * (self.laps - len(hist))
                hist.append(k + 1)
            self.rows.append((car, hist, k + 1))
        self.periods = list(session.rc.periods)
        if session.rc.active:
            self.periods.append(f"{session.rc.mode} bis Rennende")
        fastest = min((c for c in order if c.best_lap), key=lambda c: c.best_lap, default=None)
        gains = [(c.grid_slot - (k + 1), c) for k, c in enumerate(order) if not c.dnf and c.grid_slot]
        best_gain = max(gains, key=lambda g: g[0], default=None)
        losses = min(gains, key=lambda g: g[0], default=None)
        self.facts = []
        if fastest:
            self.facts.append(("Schnellste Runde", f"{fastest.short} {format_time(fastest.best_lap)}"))
        if best_gain and best_gain[0] > 0:
            self.facts.append(("Meiste Plätze gewonnen", f"{best_gain[1].short} +{best_gain[0]}"))
        if losses and losses[0] < 0:
            self.facts.append(("Meiste Plätze verloren", f"{losses[1].short} {losses[0]}"))
        trap = max(order, key=lambda c: c.vmax, default=None)
        if trap is not None and trap.vmax > 0:
            v, unit = speed_in(trap.vmax * PX_PER_S_TO_KMH, game.settings.units)
            self.facts.append(("Speedtrap", f"{trap.short} {v:.0f} {unit}"))
        stops = sum(c.pit_stops for c in order)
        self.facts.append(("Boxenstopps gesamt", str(stops)))
        dnfs = [c.short for c in order if c.dnf]
        self.facts.append(("Ausfälle", ", ".join(dnfs) if dnfs else "keine"))
        self.facts.append(("Safety Car / VSC", " · ".join(self.periods) if self.periods else "keine"))
        self.highlight = {c for c in order[:3]} | {c for c in order if c.is_player}
        focus_team = session.config.focus_team
        if focus_team:
            self.highlight |= {c for c in order if c.profile.team == focus_team}

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE,
                                                          pygame.K_ESCAPE):
            self.on_continue()

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, (60, 160, 255), (60, 30, 8, 56))
        draw_text(screen, "RENNANALYSE", f.big, WHITE, (84, 24))
        draw_text(screen, f"Grand Prix von {self.track_name} · Positionsverlauf über {self.laps} Runden", f.small,
                  GREY, (86, 72))
        box = pygame.Rect(60, 106, 840, 560)
        draw_panel(screen, box, PANEL, 220)
        n = max(1, len(self.rows))
        laps = max(1, self.laps)
        gx, gy, gw, gh = box.x + 50, box.y + 24, box.w - 120, box.h - 60

        def pt(lap: int, pos: int) -> tuple[float, float]:
            return gx + gw * lap / laps, gy + gh * (pos - 1) / max(1, n - 1)
        for pos in range(1, n + 1):
            y = pt(0, pos)[1]
            pygame.draw.line(screen, (34, 36, 44), (gx, y), (gx + gw, y), 1)
            if pos in (1, 5, 10, 15, 20) or pos == n:
                draw_text(screen, f"P{pos}", f.tiny, GREY, (gx - 10, y - 7), anchor="topright", shadow=False)
        for lap in range(laps + 1):
            x = pt(lap, 1)[0]
            pygame.draw.line(screen, (34, 36, 44), (x, gy), (x, gy + gh), 1)
            if laps <= 15 or lap % 2 == 0:
                draw_text(screen, "S" if lap == 0 else str(lap), f.tiny, GREY, (x, gy + gh + 8), anchor="midtop",
                          shadow=False)
        progress = min(1.0, self.t * 0.8)
        for car, hist, final in sorted(self.rows, key=lambda r: r[0] in self.highlight):
            strong = car in self.highlight
            col = car.color if strong else tuple(int(c * 0.45 + 20) for c in car.color)
            pts = [pt(k, p) for k, p in enumerate(hist)]
            cut = max(2, int(len(pts) * progress + 0.999))
            pts = pts[:cut]
            if len(pts) >= 2:
                pygame.draw.lines(screen, col, False, pts, 3 if strong else 1)
            for lap in car.pit_laps:
                if lap < len(hist) and lap < cut:
                    x, y = pt(lap, hist[lap])
                    pygame.draw.circle(screen, (255, 200, 40), (x, y), 4)
            if progress >= 1.0:
                ex, ey = pts[-1]
                label = f"{car.short}" + (" DNF" if car.dnf else "")
                draw_text(screen, label, f.tiny, WHITE if strong else GREY, (ex + 6, ey - 7), shadow=False)
        draw_text(screen, "gelber Punkt = Boxenstopp", f.tiny, (255, 200, 40), (gx, box.bottom - 18), shadow=False)
        fb = pygame.Rect(920, 106, 320, 560)
        draw_panel(screen, fb, PANEL, 220)
        draw_text(screen, "FAKTEN", f.tiny, GREY, (fb.x + 16, fb.y + 12), shadow=False)
        y = fb.y + 38
        for label, val in self.facts:
            draw_text(screen, label, f.tiny, GREY, (fb.x + 16, y), shadow=False)
            for k, line in enumerate(_wrap(val, f.small_bold, fb.w - 32)[:3]):
                draw_text(screen, line, f.small_bold, WHITE, (fb.x + 16, y + 16 + k * 20), shadow=False)
            y += 26 + 20 * min(3, len(_wrap(val, f.small_bold, fb.w - 32)))
        pulse = 0.6 + 0.4 * math.sin(self.t * 4)
        draw_text(screen, f"ENTER: {self.continue_label}", f.medium, tuple(int(c * pulse) for c in WHITE),
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30), anchor="center")
