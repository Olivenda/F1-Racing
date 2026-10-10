# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pygame

from .car import build_car_sprite
from .career import (AREAS, COST_CAP, FACILITIES, FACILITY_COST, FACILITY_UPKEEP, HELMET_COLORS, MAX_CREW, MAX_LEVEL,
                     MAX_PROJECTS, NATIONALITIES, SLOTS, TEAM_COLORS, Career, crew_cost, crew_stop_time, load_pool,
                     slot_summary, team_rank)
from .career_achievements import ACHIEVEMENTS, available
from .championship import FORMATS
from .settings import CYAN, DIFFICULTY_LEVELS, GREEN, GREY, PANEL, PANEL_LIGHT, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, \
    YELLOW
from .track import TRACK_DEFS
from .i18n import tr
from .utils import draw_panel, draw_text, mouse_item

if TYPE_CHECKING:
    from .game import Game

GOLD = (255, 200, 40)
RED = (255, 90, 80)
MEDAL = [(255, 215, 0), (200, 200, 210), (205, 127, 50)]


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


def _fit(text: str, font: pygame.font.Font, width: int) -> str:
    text = tr(text)
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "...")[0] > width:
        text = text[:-1]
    return text + "..."


def _visible(col: tuple[int, int, int]) -> tuple[int, int, int]:
    return col if sum(col) > 150 else (90, 100, 200)


def draw_livery(screen: pygame.Surface, fonts, rect: pygame.Rect, body: tuple[int, int, int],
                helmet: tuple[int, int, int], number: int, short: str, t: float = 0.0) -> None:
    """Big preview of the car and helmet - used by the career setup and the design studio."""
    pygame.draw.rect(screen, (26, 28, 36), rect, border_radius=10)
    for k in range(6):
        y = rect.y + 18 + k * (rect.h - 36) // 5
        pygame.draw.line(screen, (34, 37, 46), (rect.x + 12, y), (rect.right - 12, y), 1)
    scale = max(2.0, min(7.0, (rect.w * 0.62) / 34))
    sprite = pygame.transform.rotozoom(build_car_sprite(body, helmet, scale), 3 * math.sin(t * 1.3), 1.0)
    car_rect = sprite.get_rect(center=(rect.x + rect.w * 0.40, rect.centery))
    shadow = pygame.Surface((car_rect.w, 18), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 110), shadow.get_rect())
    screen.blit(shadow, (car_rect.x, car_rect.bottom - 6))
    screen.blit(sprite, car_rect)
    hx, hy, hr = rect.right - rect.w * 0.17, rect.y + rect.h * 0.40, max(18, int(rect.h * 0.22))
    pygame.draw.circle(screen, (10, 10, 12), (hx, hy), hr + 3)
    pygame.draw.circle(screen, helmet, (hx, hy), hr)
    dark = tuple(max(0, c - 80) for c in helmet)
    pygame.draw.arc(screen, dark, (hx - hr, hy - hr, hr * 2, hr * 2), 3.6, 5.8, max(3, hr // 5))
    pygame.draw.rect(screen, (20, 22, 30), (hx - hr * 0.15, hy - hr * 0.30, hr * 1.1, hr * 0.45),
                     border_radius=max(3, hr // 4))
    pygame.draw.rect(screen, (90, 150, 220), (hx - hr * 0.05, hy - hr * 0.24, hr * 0.9, hr * 0.14),
                     border_radius=3)
    label = f"#{number}" if number else ""
    if label:
        draw_text(screen, label, fonts.large, WHITE, (hx, hy + hr + 22), anchor="center")
    if short:
        draw_text(screen, short.upper(), fonts.small_bold, GREY, (hx, hy + hr + (48 if label else 22)),
                  anchor="center", shadow=False)


def draw_form(screen: pygame.Surface, fonts, x: int, y: int, entries: list[dict[str, Any]],
              label: str = "FORM (LETZTE 5 RENNEN)") -> None:
    draw_text(screen, label, fonts.tiny, GREY, (x, y), shadow=False)
    if not entries:
        draw_text(screen, "noch keine Rennen", fonts.tiny, (90, 92, 104), (x, y + 20), shadow=False)
        return
    for k, e in enumerate(entries):
        r = pygame.Rect(x + k * 54, y + 18, 48, 24)
        pos = e.get("pos", 0)
        if e.get("dnf"):
            col, txt = (150, 40, 40), "DNF"
        elif pos <= 3:
            col, txt = MEDAL[pos - 1], f"P{pos}"
        elif pos <= 10:
            col, txt = (30, 130, 70), f"P{pos}"
        else:
            col, txt = (60, 62, 72), f"P{pos}"
        pygame.draw.rect(screen, col, r, border_radius=5)
        dark = sum(col) > 450
        draw_text(screen, txt, fonts.tiny, (20, 20, 20) if dark else WHITE, r.center, anchor="center", shadow=False)


class _Screen:

    accent = GOLD

    def __init__(self, game: "Game") -> None:
        from .screens import _Background
        self.game = game
        self.bg = _Background()
        self.t = 0.0
        self.status = ""
        self.status_timer = 0.0

    @property
    def career(self) -> Career:
        assert self.game.career is not None
        return self.game.career

    def say(self, text: str) -> None:
        self.status, self.status_timer = text, 4.0

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)
        self.status_timer = max(0.0, self.status_timer - dt)

    def header(self, screen: pygame.Surface, title: str, subtitle: str) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, self.accent, (60, 30, 8, 56))
        draw_text(screen, title, f.big, WHITE, (84, 24))
        draw_text(screen, subtitle, f.small, GREY, (86, 72))

    def button(self, screen: pygame.Surface, rect: pygame.Rect, label: str, selected: bool,
               base: tuple[int, int, int] = GOLD, font: pygame.font.Font | None = None) -> None:
        f = self.game.fonts
        pulse = 0.5 + 0.5 * math.sin(self.t * 4) if selected else 0.0
        col = tuple(int(c * (0.75 + 0.25 * pulse)) for c in base) if selected else tuple(c // 3 for c in base)
        pygame.draw.rect(screen, col, rect, border_radius=8)
        dark = selected and sum(base) > 400
        draw_text(screen, label, font or f.small_bold, (25, 20, 5) if dark else WHITE, rect.center, anchor="center",
                  shadow=False)

    def draw_status(self, screen: pygame.Surface, y: int = SCREEN_HEIGHT - 26) -> None:
        if self.status_timer > 0:
            draw_text(screen, self.status, self.game.fonts.small_bold, YELLOW, (SCREEN_WIDTH // 2, y), anchor="center")

    def bar(self, screen: pygame.Surface, x: int, y: int, w: int, frac: float, col: tuple[int, int, int],
            h: int = 8) -> None:
        pygame.draw.rect(screen, (45, 45, 52), (x, y, w, h), border_radius=3)
        pygame.draw.rect(screen, col, (x, y, int(w * max(0.0, min(1.0, frac))), h), border_radius=3)


class CareerSetupScreen(_Screen):

    TEXT_ROWS = {"Teamname": ("team_name", 20), "Fahrername": ("driver_name", 20), "Dein Name": ("driver_name", 20),
                 "Kürzel": ("short", 3)}

    def __init__(self, game: "Game", slot: str) -> None:
        super().__init__(game)
        self.slot = slot
        self.kind = slot.split("_")[0]
        base = game.settings.player_name.split(" (")[0].strip()
        self.driver_name = "" if base in ("Du", "") else base
        self.team_name = f"{self.driver_name or 'Neues'} Racing"
        self.team_name_edited = False
        self.short = ""
        self.number = (sum(ord(ch) for ch in slot) * 7) % 98 + 2
        self.nation = 0
        self.helmet = 0
        self.color = 0
        self.drives = True
        self.format = 1
        self.diffs = list(DIFFICULTY_LEVELS.keys())
        self.sel = 0

    @property
    def rows(self) -> list[str]:
        team = ["Teamname", "Teamfarbe", "Selbst fahren"] if self.kind == "team" else []
        if self.kind == "team" and not self.drives:
            ident = ["Dein Name"]
        else:
            ident = ["Fahrername", "Kürzel", "Startnummer", "Nationalität", "Helmfarbe"]
        return team + ident + ["Format", "Rennrunden", "KI-Stärke", "START", "ZURÜCK"]

    @property
    def c(self) -> dict[str, int]:
        return self.game.menu_choice

    def _short_code(self) -> str:
        if self.short:
            return self.short
        letters = "".join(ch for ch in (self.driver_name.split() or [""])[-1].upper() if ch.isalpha())
        return letters[:3] or "YOU"

    def _change(self, row: str, delta: int) -> None:
        if row == "Teamfarbe":
            self.color = (self.color + delta) % len(TEAM_COLORS)
        elif row == "Selbst fahren":
            self.drives = not self.drives
        elif row == "Startnummer":
            self.number = (self.number - 1 + delta) % 99 + 1
        elif row == "Nationalität":
            self.nation = (self.nation + delta) % len(NATIONALITIES)
        elif row == "Helmfarbe":
            self.helmet = (self.helmet + delta) % len(HELMET_COLORS)
        elif row == "Format":
            self.format = (self.format + delta) % len(FORMATS)
        elif row == "Rennrunden":
            self.c["laps"] = max(1, min(30, self.c["laps"] + delta))
        elif row == "KI-Stärke":
            self.c["diff"] = (self.c["diff"] + delta) % len(self.diffs)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        rows = self.rows
        row = rows[min(self.sel, len(rows) - 1)]
        text = self.TEXT_ROWS.get(row)
        if event.key == pygame.K_UP:
            self.sel = (self.sel - 1) % len(rows)
        elif event.key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % len(rows)
        elif text and event.key == pygame.K_BACKSPACE:
            setattr(self, text[0], getattr(self, text[0])[:-1])
            self._text_changed(row)
        elif text and event.unicode and event.unicode.isprintable() and \
                event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE, pygame.K_TAB):
            ch = event.unicode
            if row == "Kürzel":
                if not ch.isalpha():
                    return
                ch = ch.upper()
            value = getattr(self, text[0])
            if len(value) < text[1]:
                setattr(self, text[0], value + ch)
                self._text_changed(row)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self._change(row, -1 if event.key == pygame.K_LEFT else 1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if row == "START":
                self._start()
            elif row == "ZURÜCK":
                self.game.open_career_slots()
            elif text:
                self.sel = (self.sel + 1) % len(rows)
            else:
                self._change(row, 1)
        elif event.key == pygame.K_ESCAPE:
            self.game.open_career_slots()

    def _text_changed(self, row: str) -> None:
        if row == "Teamname":
            self.team_name_edited = True
        elif row in ("Fahrername", "Dein Name") and not self.team_name_edited:
            self.team_name = f"{(self.driver_name.split() or ['Neues'])[-1]} Racing"[:20]

    def _start(self) -> None:
        game = self.game
        name = self.driver_name.strip()
        taken = {d["name"] for d in load_pool()} | {t.name for t in game.teams}
        if not name:
            self.say("Bitte einen Namen eingeben")
            return
        if name in taken:
            self.say("Diesen Namen trägt schon ein Fahrer oder Team")
            return
        if self.kind == "team" and not self.team_name.strip():
            self.say("Bitte einen Teamnamen eingeben")
            return
        if self.kind == "team" and (self.team_name.strip() in taken or self.team_name.strip() == name):
            self.say("Diesen Teamnamen gibt es schon")
            return
        game.career = Career.create(self.slot, self.kind, name, self.diffs[self.c["diff"]], self.c["laps"],
                                    FORMATS[self.format][0], game.teams, self.team_name.strip(),
                                    TEAM_COLORS[self.color], self.drives, short=self._short_code(),
                                    number=self.number, nationality=NATIONALITIES[self.nation],
                                    helmet=HELMET_COLORS[self.helmet])
        game.career.save()
        game.open_career()

    def _value(self, row: str) -> str:
        cursor = "_" if int(self.t * 2) % 2 else ""
        if row == "Teamname":
            return self.team_name + (cursor if self.rows[self.sel] == row else "")
        if row in ("Fahrername", "Dein Name"):
            shown = self.driver_name or ("" if self.rows[self.sel] == row else "(Namen eintippen)")
            return shown + (cursor if self.rows[self.sel] == row else "")
        if row == "Kürzel":
            return (self.short or self._short_code()) + (cursor if self.rows[self.sel] == row else "") + \
                ("   (Timing-Tower)" if not self.short else "")
        if row == "Startnummer":
            return f"#{self.number}"
        if row == "Nationalität":
            return NATIONALITIES[self.nation] or "- keine -"
        if row in ("Teamfarbe", "Helmfarbe"):
            return ""
        if row == "Selbst fahren":
            return "Ja - Teamchef und Fahrer" if self.drives else "Nein - nur Teamchef (2 Fahrer verpflichten)"
        if row == "Format":
            return FORMATS[self.format][1]
        if row == "Rennrunden":
            return f"{self.c['laps']} Runde{'n' if self.c['laps'] != 1 else ''} pro Rennen"
        if row == "KI-Stärke":
            return self.diffs[self.c["diff"]]
        return ""

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        kind = "FAHRER" if self.kind == "driver" else "TEAM"
        self.header(screen, f"NEUE {kind}-KARRIERE · SLOT {self.slot[-1]}",
                    "Dein Name, deine Nummer, dein Helm - Verträge, Rivalen, Budget und Entwicklung")
        px, py, pw = 60, 112, 600
        draw_panel(screen, (px, py, pw, 556), PANEL, 215)
        rows = self.rows
        self.sel = min(self.sel, len(rows) - 1)
        rh = min(50, (556 - 30) // len(rows))
        for i, row in enumerate(rows):
            ry = py + 10 + i * rh
            selected = i == self.sel
            if row in ("START", "ZURÜCK"):
                h = min(44, rh + 4) if row == "START" else min(34, rh - 4)
                mouse_item((px + 20, ry + 2, pw - 40, h), self, i)
                self.button(screen, pygame.Rect(px + 20, ry + 2, pw - 40, h),
                            "KARRIERE STARTEN" if row == "START" else "ZURÜCK", selected,
                            GOLD if row == "START" else (90, 90, 100), f.large if row == "START" else f.medium)
                continue
            bh = rh - 6
            mouse_item((px + 12, ry, pw - 24, bh), self, i, key=None, arrows=row not in self.TEXT_ROWS)
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 12, ry, pw - 24, bh), border_radius=6)
                pygame.draw.rect(screen, GOLD, (px + 12, ry, 5, bh), border_radius=2)
            mid = ry + bh // 2
            draw_text(screen, row.upper(), f.tiny, GREY, (px + 28, mid), anchor="midleft", shadow=False)
            draw_text(screen, self._value(row), f.small_bold, CYAN if row in self.TEXT_ROWS else WHITE,
                      (px + 175, mid), anchor="midleft", shadow=False)
            palette = TEAM_COLORS if row == "Teamfarbe" else HELMET_COLORS if row == "Helmfarbe" else None
            if palette:
                pick = self.color if row == "Teamfarbe" else self.helmet
                size = min(26, 340 // len(palette) - 6)
                for k, col in enumerate(palette):
                    r = pygame.Rect(px + 175 + k * (size + 8), mid - size // 2, size, size)
                    pygame.draw.rect(screen, col, r, border_radius=5)
                    if k == pick:
                        pygame.draw.rect(screen, WHITE, r.inflate(6, 6), 2, border_radius=7)
            if selected and row not in self.TEXT_ROWS:
                draw_text(screen, "<  >", f.medium, YELLOW, (px + pw - 24, mid), anchor="midright")
        box = pygame.Rect(690, 112, 550, 556)
        draw_panel(screen, box, PANEL, 215)
        if self.kind == "driver":
            title = "FAHRER-KARRIERE"
            text = ("Du startest als Rookie bei einem kleinen Team. Punkte, Siege gegen Teamkollegen und Rivalen "
                    "bringen Ruf. Mit deinem Gehalt investierst du in Manager, PR und Mentaltrainer. "
                    "Am Saisonende kommen Vertragsangebote - mit genug Ruf auch von den Top-Teams.")
        else:
            title = "TEAM-KARRIERE"
            text = (f"Du gründest ein neues Team mit {45} Mio Budget und einem langsamen Auto. "
                    "Sponsoren und Preisgeld bringen Geld, Gehälter und Betrieb kosten Geld. "
                    "Entwickle das Auto, baue die Fabrik aus und verpflichte Fahrer - jede Saison "
                    "drängen neue Talente in den Fahrermarkt.")
        draw_text(screen, title, f.large, GOLD, (box.x + 20, box.y + 16))
        lines = _wrap(text, f.small, box.w - 40)
        for k, line in enumerate(lines):
            draw_text(screen, line, f.small, (210, 210, 215), (box.x + 20, box.y + 58 + k * 23), shadow=False)
        body = TEAM_COLORS[self.color] if self.kind == "team" else (150, 150, 158)
        drives = self.kind == "driver" or self.drives
        preview = pygame.Rect(box.x + 20, box.y + 80 + len(lines) * 23, box.w - 40, 230)
        draw_livery(screen, f, preview, body, HELMET_COLORS[self.helmet] if drives else (60, 60, 66),
                    self.number if drives else 0, self._short_code() if drives else "", self.t)
        who = self.driver_name or "?"
        sub = f"{who} · {NATIONALITIES[self.nation] or '-'}" if drives else f"Teamchef {who}"
        if self.kind == "team":
            sub += f" · {self.team_name or '?'}"
        draw_text(screen, _fit(sub, f.medium, box.w - 40), f.medium, WHITE, (box.x + 20, preview.bottom + 12))
        if self.kind == "driver":
            draw_text(screen, "Die Autofarbe kommt von deinem Team - Helm und Nummer gehören dir.", f.tiny, GREY,
                      (box.x + 20, preview.bottom + 46), shadow=False)
        draw_text(screen, f"Gespeichert in data/careers/{self.slot}.json · später änderbar im DESIGN-Studio",
                  f.tiny, (120, 200, 255), (box.x + 20, box.bottom - 26), shadow=False)
        self.draw_status(screen)


class OfferScreen(_Screen):

    DEMANDS = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.sel = 0
        self.demand = 2
        self.years: int | None = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        c = self.career
        offers = c.offers
        if event.key == pygame.K_UP:
            self.sel = (self.sel - 1) % max(1, len(offers))
            self.years = None
        elif event.key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % max(1, len(offers))
            self.years = None
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.demand = max(0, min(len(self.DEMANDS) - 1, self.demand + (-1 if event.key == pygame.K_LEFT else 1)))
        elif event.key == pygame.K_TAB and offers:
            cur = self.years or offers[self.sel]["years"]
            self.years = cur % 3 + 1
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and offers:
            season_end = c.season_over
            years = self.years or offers[self.sel]["years"]
            ok, msg = c.negotiate(self.sel, self.DEMANDS[self.demand], years)
            self.say(msg)
            if ok:
                if season_end:
                    c.start_next_season()
                self.game.open_career()
            else:
                self.sel = 0
                self.demand = 2
        elif event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        c = self.career
        first = not c.team or not c.history
        self.header(screen, "VERTRAGSANGEBOTE",
                    f"Saison {c.season + (0 if first and not c.season_over else 1)} · Ruf {c.reputation:.0f}/100 · "
                    "Verhandle Gehalt und Laufzeit")
        teams = c.team_ranking()
        demand = self.DEMANDS[self.demand]
        for k, o in enumerate(c.offers[:6]):
            y = 112 + k * 92
            rect = pygame.Rect(60, y, 760, 84)
            selected = k == self.sel
            mouse_item(rect, self, k, key=None)
            mouse_item((rect.x + 430, rect.y + 38, 160, 22), self, k, key=pygame.K_TAB)
            draw_panel(screen, rect, PANEL_LIGHT if selected else PANEL, 225)
            col = tuple(c.teams[o["team"]]["color"])
            pygame.draw.rect(screen, col, (rect.x, rect.y, 8, rect.h), border_radius=4)
            if selected:
                pygame.draw.rect(screen, GOLD, rect, 2, border_radius=8)
            draw_text(screen, o["team"].upper(), f.large, WHITE, (rect.x + 26, rect.y + 10))
            if o.get("current") or o["team"] == c.team:
                draw_text(screen, "AKTUELLES TEAM", f.tiny, CYAN, (rect.x + 26, rect.y + 46), shadow=False)
            draw_text(screen, f"Auto-Ranking P{o['rank']} von {len(teams)}", f.small, GREY, (rect.x + 26, rect.y + 58),
                      shadow=False)
            salary = o["salary"] * (demand if selected else 1.0)
            years = (self.years or o["years"]) if selected else o["years"]
            draw_text(screen, f"{salary:.1f} Mio / Saison", f.medium, YELLOW if selected and demand != 1.0 else GREEN,
                      (rect.x + 430, rect.y + 12))
            draw_text(screen, f"{years} Saison{'s' if years != 1 else ''}", f.small_bold, WHITE,
                      (rect.x + 430, rect.y + 40), shadow=False)
            draw_text(screen, f"Ziel: Fahrer-WM P{o['goal']}", f.small_bold, YELLOW, (rect.x + 430, rect.y + 60),
                      shadow=False)
            self.bar(screen, rect.x + 640, rect.y + 40, 100, (c.team_obj(o["team"]).rating - 0.96) / 0.08,
                     _visible(col))
        box = pygame.Rect(850, 112, 390, 540)
        draw_panel(screen, box, PANEL, 215)
        mouse_item((box.x + 8, box.y + 28, box.w - 16, 48), self, self.demand, attr="demand", key=None, arrows=True)
        draw_text(screen, "VERHANDLUNG", f.tiny, GREY, (box.x + 16, box.y + 12), shadow=False)
        risk = "kein Risiko" if demand <= 1.0 else "geringes Risiko" if demand <= 1.1 else \
            "mittleres Risiko" if demand <= 1.25 else "hohes Risiko!"
        rc = GREEN if demand <= 1.0 else YELLOW if demand <= 1.25 else RED
        draw_text(screen, f"Forderung: {demand * 100:.0f} %", f.large, rc, (box.x + 16, box.y + 34))
        draw_text(screen, risk, f.small_bold, rc, (box.x + 16, box.y + 74), shadow=False)
        text = ("Links/Rechts: Gehalt fordern (80-150 % des Angebots). TAB: Laufzeit 1-3 Saisons. "
                "Je höher dein Ruf (und beim eigenen Team das Vertrauen), desto mehr ist ein Team bereit zu zahlen. "
                "Verlangst du zu viel, zieht es sein Angebot zurück - weniger zu fordern ist immer sicher.")
        for k, line in enumerate(_wrap(text, f.small, box.w - 32)):
            draw_text(screen, line, f.small, (210, 210, 215), (box.x + 16, box.y + 110 + k * 23), shadow=False)
        draw_text(screen, f"Dein Ruf: {c.reputation:.0f}/100", f.small_bold, WHITE, (box.x + 16, box.bottom - 70),
                  shadow=False)
        if c.team:
            draw_text(screen, f"Vertrauen bei {c.team}: {c.trust:.0f}/100", f.small_bold, WHITE,
                      (box.x + 16, box.bottom - 44), shadow=False)
        draw_text(screen, "Pfeile wählen/fordern · TAB Laufzeit · ENTER unterschreiben", f.tiny, GREY,
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 44), anchor="center", shadow=False)
        self.draw_status(screen, SCREEN_HEIGHT - 20)


class CareerHub(_Screen):

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.sel = 0
        self.confirm_quit = False
        c = self.career
        if c.new_achievements:
            titles = [ACHIEVEMENTS[k][1] for k in c.new_achievements if k in ACHIEVEMENTS]
            c.new_achievements = []
            c.save()
            if titles:
                self.say("ERFOLG FREIGESCHALTET: " + ", ".join(titles))
                self.status_timer = 6.0
                game.sound.ui("fanfare")

    def actions(self) -> list[tuple[str, str]]:
        c = self.career
        acts: list[tuple[str, str]] = []
        if c.season_over:
            acts.append(("review", "SAISONABSCHLUSS"))
        elif c.kind == "team" and not c.sponsor:
            acts.append(("sponsor", "SPONSOR WÄHLEN"))
        else:
            ready, _ = c.ready_to_race()
            track = self.game.tracks[c.championship.next_track or TRACK_DEFS[0].key].name.upper()
            if ready:
                if c.player_drives:
                    acts.append(("race", f"FAHREN: {track}"))
                else:
                    acts.append(("watch", f"ANSEHEN: {track}"))
                    acts.append(("sim", "SIMULIEREN"))
        if c.player_drives and not c.season_over and c.team:
            acts.append(("garage", "GARAGE"))
        if c.kind == "team":
            acts.append(("dev", "ENTWICKLUNG"))
            acts.append(("market", "FAHRERMARKT"))
        else:
            acts.append(("personal", "PERSÖNLICH"))
        acts.append(("design", "DESIGN"))
        acts.append(("compare", "AUTO-VERGLEICH"))
        acts.append(("stats", "STATISTIK"))
        acts.append(("trophies", "ERFOLGE"))
        acts.append(("history", "HISTORIE"))
        acts.append(("options", "OPTIONEN"))
        acts.append(("slots", "SPIELSTÄNDE"))
        acts.append(("quit", "WIRKLICH LÖSCHEN?" if self.confirm_quit else "LÖSCHEN"))
        return acts

    SECOND_ROW = ("compare", "stats", "trophies", "history", "options", "slots", "quit")

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        acts = self.actions()
        if event.key in (pygame.K_LEFT, pygame.K_UP):
            self.sel = (self.sel - 1) % len(acts)
            self.confirm_quit = False
        elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
            self.sel = (self.sel + 1) % len(acts)
            self.confirm_quit = False
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._do(acts[min(self.sel, len(acts) - 1)][0])
        elif event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()

    def _do(self, act: str) -> None:
        game, c = self.game, self.career
        if act in ("race", "watch"):
            game.start_career_round(instant=False)
        elif act == "sim":
            game.start_career_round(instant=True)
        elif act == "garage":
            track = c.championship.next_track or TRACK_DEFS[0].key
            game.open_garage(track, c.team_obj(c.team), game.open_career)
        elif act == "dev":
            game.state = DevelopmentScreen(game)
        elif act == "market":
            game.state = MarketScreen(game)
        elif act == "sponsor":
            game.state = SponsorScreen(game)
        elif act == "review":
            game.state = SeasonReviewScreen(game)
        elif act == "compare":
            game.state = CarCompareScreen(game)
        elif act == "history":
            game.state = HistoryScreen(game)
        elif act in ("personal", "design", "stats", "trophies", "options"):
            from . import career_extras
            screen_cls = {"personal": career_extras.PersonalScreen, "design": career_extras.DesignScreen,
                          "stats": career_extras.StatsScreen, "trophies": career_extras.AchievementsScreen,
                          "options": career_extras.CareerOptionsScreen}[act]
            game.state = screen_cls(game)
        elif act == "slots":
            game.career = None
            game.open_career_slots()
        elif act == "quit":
            if self.confirm_quit:
                Career.delete(c.slot)
                game.career = None
                game.open_career_slots()
            else:
                self.confirm_quit = True

    def draw(self, screen: pygame.Surface) -> None:
        c = self.career
        champ = c.championship
        rnd = f"Runde {min(champ.round + 1, len(champ.rounds))}/{len(champ.rounds)}"
        if c.kind == "driver":
            sub = f"{c.player_name} · {c.team or 'ohne Vertrag'} · {c.status if c.team else ''} · {rnd}"
        else:
            sub = f"{c.team} · Teamchef {c.player_name}" + (" (fährt selbst)" if c.player_drives else "") + f" · {rnd}"
        self.header(screen, f"KARRIERE · SAISON {c.season}", sub)
        f = self.game.fonts
        pool = available(c.kind)
        got = sum(1 for k in pool if k in c.achievements)
        badge = pygame.Rect(SCREEN_WIDTH - 60 - 170, 34, 170, 46)
        draw_panel(screen, badge, PANEL, 215)
        draw_text(screen, "ERFOLGE", f.tiny, GREY, (badge.x + 12, badge.y + 6), shadow=False)
        draw_text(screen, f"{got}/{len(pool)}", f.medium, GOLD if got else WHITE, (badge.x + 12, badge.y + 20),
                  shadow=False)
        self.bar(screen, badge.x + 80, badge.y + 30, 76, got / max(1, len(pool)), GOLD, 6)
        if c.player_drives:
            nb = pygame.Rect(badge.x - 130, 34, 120, 46)
            draw_panel(screen, nb, PANEL, 215)
            pygame.draw.circle(screen, tuple(c.helmet), (nb.x + 24, nb.centery), 14)
            draw_text(screen, f"#{c.player_number}" if c.player_number else c.short_code, f.medium, WHITE,
                      (nb.x + 46, nb.centery), anchor="midleft", shadow=False)
        if c.kind == "driver":
            self._driver_card(screen)
        else:
            self._team_card(screen)
        self._standings(screen)
        self._calendar_news(screen)
        self._buttons(screen)

    def _two_bars(self, screen: pygame.Surface, x: int, y: int, w: int,
                  items: list[tuple[str, float, tuple[int, int, int]]]) -> None:
        f = self.game.fonts
        bw = (w - 16) // 2
        for k, (label, val, col) in enumerate(items):
            bx = x + k * (bw + 16)
            draw_text(screen, label, f.tiny, GREY, (bx, y), shadow=False)
            draw_text(screen, f"{val:.0f}", f.small_bold, WHITE, (bx + bw, y - 3), anchor="topright", shadow=False)
            self.bar(screen, bx, y + 17, bw, val / 100, col)

    def _driver_card(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        box = pygame.Rect(60, 106, 400, 510)
        draw_panel(screen, box, PANEL, 215)
        col = tuple(c.teams[c.team]["color"]) if c.team else (150, 150, 150)
        pygame.draw.rect(screen, col, (box.x, box.y, box.w, 6), border_radius=3)
        x, y = box.x + 18, box.y + 16
        draw_text(screen, (c.team or "OHNE TEAM").upper(), f.medium, WHITE, (x, y))
        if c.team:
            draw_text(screen, f"Auto P{team_rank(c.teams, c.team)}/{len(c.teams)}", f.tiny, GREY,
                      (box.right - 18, y + 6), anchor="topright", shadow=False)
        ct = c.contract
        draw_text(screen, f"Vertrag: {ct.get('salary', 0):.1f} Mio/Saison · noch {ct.get('years', 0)} Saison(s)",
                  f.small, WHITE, (x, y + 30), shadow=False)
        pos = c.player_driver_pos()
        goal = ct.get("goal", 10)
        ok = pos is not None and pos <= goal
        draw_text(screen, f"Saisonziel: WM P{goal}", f.small_bold, YELLOW, (x, y + 52), shadow=False)
        draw_text(screen, f"aktuell P{pos}" if pos else "noch kein Rennen", f.small_bold,
                  GREEN if ok else RED if pos else GREY, (box.right - 18, y + 52), anchor="topright", shadow=False)
        trust_col = GREEN if c.trust >= 75 else GOLD if c.trust >= 45 else (255, 140, 30) if c.trust >= 25 else RED
        self._two_bars(screen, x, y + 80, box.w - 36, [("RUF", c.reputation, GOLD), ("VERTRAUEN", c.trust, trust_col)])
        draw_text(screen, f"Status: {c.status}", f.tiny, trust_col, (x, y + 108), shadow=False)
        draw_text(screen, f"Konto {c.bank:.1f} Mio", f.tiny, GREEN, (box.right - 18, y + 108), anchor="topright",
                  shadow=False)
        wg = c.weekend_goal
        gy = y + 130
        pygame.draw.rect(screen, (60, 50, 12), (box.x + 10, gy, box.w - 20, 40), border_radius=6)
        draw_text(screen, "WOCHENENDZIEL DES TEAMS", f.tiny, GOLD, (x, gy + 4), shadow=False)
        draw_text(screen, wg.get("text", "-") if not c.season_over else "Saison beendet", f.small_bold, WHITE,
                  (x, gy + 19), shadow=False)
        log = c.season_log
        draw_text(screen, f"{log.get('goals_met', 0)}/{log.get('goals', 0)} erfüllt", f.tiny, GREY,
                  (box.right - 18, gy + 21), anchor="topright", shadow=False)
        st = c.stats
        line = f"Karriere: {st['races']} Rennen · {st['wins']} Siege · {st['podiums']} Podien · {st['titles']} Titel"
        draw_text(screen, _fit(line, f.tiny, box.w - 36), f.tiny, (200, 200, 205), (x, gy + 50), shadow=False)
        ry = gy + 72
        pygame.draw.rect(screen, (70, 20, 24), (box.x + 10, ry, box.w - 20, 62), border_radius=8)
        if c.rival and c.rival in c.drivers:
            pts = {e["name"]: e["points"] for e in c.championship.driver_table()}
            draw_text(screen, "RIVALE", f.tiny, RED, (x, ry + 6), shadow=False)
            draw_text(screen, _fit(c.rival, f.small_bold, 230), f.small_bold, WHITE, (x, ry + 22), shadow=False)
            draw_text(screen, c.drivers[c.rival]["team"], f.tiny, GREY, (x, ry + 42), shadow=False)
            draw_text(screen, f"Duelle {log.get('rival_ahead', 0)}:{log.get('rival_behind', 0)}", f.tiny, WHITE,
                      (box.right - 18, ry + 8), anchor="topright", shadow=False)
            draw_text(screen, f"Punkte {pts.get(c.player_name, 0)}:{pts.get(c.rival, 0)}", f.small_bold, YELLOW,
                      (box.right - 18, ry + 30), anchor="topright", shadow=False)
        my = ry + 70
        mates = c.lineup(c.team) if c.team else []
        if mates:
            draw_text(screen, f"TEAMKOLLEGE: {_fit(mates[0], f.tiny, 200)}", f.tiny, GREY, (x, my), shadow=False)
            draw_text(screen, f"Duelle {log.get('mate_ahead', 0)}:{log.get('mate_behind', 0)}", f.tiny, WHITE,
                      (box.right - 18, my), anchor="topright", shadow=False)
        if c.team:
            ay = my + 22
            rel = c.teams[c.team].get("reliability", 0.975)
            draw_text(screen, f"DEIN AUTO · Zuverlässigkeit {rel * 100:.1f} %", f.tiny, GREY, (x, ay), shadow=False)
            for k, (label, key, inv) in enumerate(CarCompareScreen.STATS):
                vals = [(2.0 - t[key]) if inv else t[key] for t in c.teams.values()]
                me = (2.0 - c.teams[c.team][key]) if inv else c.teams[c.team][key]
                p = 1 + sum(1 for v in vals if v > me + 1e-9)
                yy = ay + 16 + k * 15
                bc = GREEN if p <= 3 else YELLOW if p <= len(vals) // 2 + 1 else RED
                draw_text(screen, label, f.tiny, WHITE, (x, yy), shadow=False)
                self.bar(screen, x + 80, yy + 4, 210, max(0.05, 1.0 - (p - 1) / max(1, len(vals) - 1)), bc, 7)
                draw_text(screen, f"P{p}", f.tiny, bc, (box.right - 18, yy), anchor="topright", shadow=False)
        draw_form(screen, f, x, box.bottom - 58, c.form())

    def _team_card(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        box = pygame.Rect(60, 106, 400, 510)
        draw_panel(screen, box, PANEL, 215)
        col = tuple(c.teams[c.team]["color"])
        pygame.draw.rect(screen, col, (box.x, box.y, box.w, 6), border_radius=3)
        x, y = box.x + 18, box.y + 16
        draw_text(screen, c.team.upper(), f.medium, WHITE, (x, y))
        draw_text(screen, f"Budget: {c.budget:.1f} Mio", f.medium, GREEN if c.budget >= 0 else RED, (x, y + 28))
        draw_text(screen, f"Deckel noch {c.cap_left():.1f} Mio", f.tiny, GREY, (box.right - 18, y + 36),
                  anchor="topright", shadow=False)
        self._two_bars(screen, x, y + 62, box.w - 36, [("TEAMRUF", c.team_rep, GOLD),
                                                       ("SPONSOR-LAUNE", c.sponsor_mood, CYAN)])
        sp = c.sponsor
        draw_text(screen, _fit(f"Sponsor: {sp['name']} · {sp['text']}" if sp else "Kein Titelsponsor gewählt!",
                               f.tiny, box.w - 36), f.tiny, CYAN if sp else RED, (x, y + 90), shadow=False)
        pos, goal = c.team_pos(), c.team_goal()
        draw_text(screen, f"Ziel: Konstrukteure P{goal}", f.small_bold, YELLOW, (x, y + 110), shadow=False)
        draw_text(screen, f"aktuell P{pos}" if pos else "-", f.small_bold,
                  GREEN if pos and pos <= goal else RED if pos else GREY, (box.right - 18, y + 110), anchor="topright",
                  shadow=False)
        team = c.team_obj(c.team)
        draw_text(screen, f"AUTO · Ranking P{team_rank(c.teams, c.team)}/{len(c.teams)}", f.tiny, GREY, (x, y + 138),
                  shadow=False)
        rel = c.teams[c.team].get("reliability", 0.965)
        rows = (("Motor", team.engine), ("Aero", team.aero), ("Topspeed", team.top_speed), ("Bremsen", team.brakes),
                ("Reifen", 2.0 - team.tyre_wear))
        for k, (label, val) in enumerate(rows):
            yy = y + 156 + k * 18
            draw_text(screen, label, f.tiny, WHITE, (x, yy), shadow=False)
            self.bar(screen, x + 90, yy + 4, 210, (val - 0.94) / 0.12, _visible(col), 7)
            draw_text(screen, f"{(val - 1) * 100:+.1f}%", f.tiny, GREY, (box.right - 18, yy), anchor="topright",
                      shadow=False)
        yy = y + 156 + 5 * 18
        draw_text(screen, "Zuverl.", f.tiny, WHITE, (x, yy), shadow=False)
        self.bar(screen, x + 90, yy + 4, 210, (rel - 0.95) / 0.045, GREEN if rel > 0.98 else YELLOW, 7)
        draw_text(screen, f"{rel * 100:.1f}%", f.tiny, GREY, (box.right - 18, yy), anchor="topright", shadow=False)
        py = yy + 26
        if c.projects:
            for k, p in enumerate(c.projects):
                name = AREAS[p["area"]][0].split(" (")[0] if p["area"] in AREAS else "Zuverlässigkeit"
                draw_text(screen, f"In Arbeit: {name} · noch {p['races_left']} Rd.", f.tiny, (120, 200, 255),
                          (x, py + k * 16), shadow=False)
        else:
            draw_text(screen, "Keine Entwicklungsprojekte laufen", f.tiny, GREY, (x, py), shadow=False)
        dy = py + 40
        draw_text(screen, f"FAHRER · Crew-Stopp {crew_stop_time(c.crew):.2f} s", f.tiny, GREY, (x, dy), shadow=False)
        rows2 = ([(c.player_name + " (du)", "-", "-")] if c.player_drives else []) + \
            [(n, str(c.drivers[n]["rating"]), f"{c.drivers[n].get('years', 0)} J.") for n in c.own_drivers()]
        for k, (name, rating, years) in enumerate(rows2):
            ry = dy + 18 + k * 22
            draw_text(screen, _fit(name, f.small_bold, 230), f.small_bold, CYAN, (x, ry), shadow=False)
            draw_text(screen, rating, f.mono, YELLOW, (x + 260, ry), shadow=False)
            draw_text(screen, years, f.tiny, GREY, (box.right - 18, ry + 2), anchor="topright", shadow=False)
        for k in range(c.seats()):
            draw_text(screen, "- freies Cockpit -", f.small_bold, RED, (x, dy + 18 + (len(rows2) + k) * 22),
                      shadow=False)
        draw_form(screen, f, x, box.bottom - 86, c.form(), "FORM (BESTES TEAMAUTO)")
        if c.rival:
            log = c.season_log
            draw_text(screen, f"Rivalenteam: {c.rival} · Duelle {log.get('rival_ahead', 0)}:"
                              f"{log.get('rival_behind', 0)}", f.tiny, RED, (x, box.bottom - 24), shadow=False)

    def _standings(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        box = pygame.Rect(476, 106, 380, 510)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "FAHRER-WM", f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
        table = c.championship.driver_table()
        if not table:
            names = [n for t in c.teams for n in c.lineup(t)]
            table = [{"name": n, "team": c.drivers[n]["team"], "points": 0, "player": False} for n in names]
            if c.player_drives and c.team:
                table.insert(0, {"name": c.player_name, "team": c.team, "points": 0, "player": True})
        rh = 25 if len(table) <= 18 else 19 if len(table) <= 22 else 18
        font = f.small_bold if rh == 25 else f.tiny
        for i, e in enumerate(table[:24]):
            y = box.y + 32 + i * rh
            mine = e["player"] or e["team"] == c.team
            if mine:
                pygame.draw.rect(screen, (0, 70, 100), (box.x + 6, y - 2, box.w - 12, rh - 2), border_radius=4)
            elif e["name"] == c.rival or e["team"] == c.rival:
                pygame.draw.rect(screen, (80, 24, 28), (box.x + 6, y - 2, box.w - 12, rh - 2), border_radius=4)
            draw_text(screen, f"{i + 1}", font, MEDAL[i] if i < 3 and table[0]["points"] else WHITE,
                      (box.x + 14, y), shadow=False)
            colr = tuple(c.teams.get(e["team"], {}).get("color", (150, 150, 150)))
            pygame.draw.rect(screen, colr, (box.x + 40, y + 2, 4, rh - 7))
            draw_text(screen, _fit(e["name"], font, 190), font, CYAN if e["player"] else WHITE,
                      (box.x + 52, y), shadow=False)
            draw_text(screen, _fit(e["team"], f.tiny, 90), f.tiny, GREY, (box.x + 250, y + (3 if rh == 25 else 0)),
                      shadow=False)
            draw_text(screen, str(e["points"]), f.tiny if rh < 25 else f.mono, YELLOW, (box.right - 16, y + 1),
                      anchor="topright", shadow=False)
        teams = c.championship.team_table()
        if teams:
            pos = next((k + 1 for k, e in enumerate(teams) if e["team"] == c.team), None)
            draw_text(screen, f"Konstrukteure: {teams[0]['team']} führt" + (f" · {c.team} P{pos}" if pos else ""),
                      f.tiny, GREY, (box.x + 14, box.bottom - 24), shadow=False)

    def _calendar_news(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        champ = c.championship
        box = pygame.Rect(872, 106, 368, 200)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "KALENDER", f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
        for k, key in enumerate(champ.rounds):
            y = box.y + 30 + k * 27
            name = self.game.tracks[key].name
            current = k == champ.round
            if current:
                pygame.draw.rect(screen, (70, 56, 10), (box.x + 6, y - 2, box.w - 12, 24), border_radius=4)
            draw_text(screen, f"{k + 1}  {name}", f.small_bold, YELLOW if current else WHITE, (box.x + 14, y),
                      shadow=False)
            winner = champ.winner_of(k)
            if winner:
                draw_text(screen, _fit(winner, f.tiny, 140), f.tiny, GOLD, (box.right - 14, y + 3), anchor="topright",
                          shadow=False)
        self._next_race(screen, pygame.Rect(872, 314, 368, 112))
        nb = pygame.Rect(872, 434, 368, 182)
        draw_panel(screen, nb, PANEL, 215)
        draw_text(screen, "NACHRICHTEN", f.tiny, GREY, (nb.x + 14, nb.y + 10), shadow=False)
        y = nb.y + 32
        for msg in c.news:
            for line in _wrap(msg, f.tiny, nb.w - 28):
                if y > nb.bottom - 18:
                    break
                draw_text(screen, line, f.tiny, (210, 210, 215), (nb.x + 14, y), shadow=False)
                y += 17
            y += 5

    def _next_race(self, screen: pygame.Surface, box: pygame.Rect) -> None:
        f, c = self.game.fonts, self.career
        champ = c.championship
        draw_panel(screen, box, PANEL, 215)
        if champ.finished:
            draw_text(screen, "SAISON BEENDET", f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
            draw_text(screen, "Weiter zum Saisonabschluss", f.small_bold, GOLD, (box.x + 14, box.y + 40), shadow=False)
            return
        track = self.game.tracks[champ.next_track]
        draw_text(screen, "NÄCHSTES RENNEN", f.tiny, GREY, (box.x + 14, box.y + 10), shadow=False)
        thumb = pygame.Rect(box.right - 128, box.y + 8, 118, box.h - 16)
        pygame.draw.rect(screen, (26, 28, 36), thumb, border_radius=6)
        try:
            track.draw_outline(screen, thumb.inflate(-8, -8), GOLD, 2)
        except (ValueError, ZeroDivisionError):
            pass
        draw_text(screen, _fit(track.name, f.medium, box.w - 160), f.medium, WHITE, (box.x + 14, box.y + 28))
        fmt = next((label for key, label in FORMATS if key == c.format), c.format)
        draw_text(screen, f"Lauf {champ.round + 1}/{len(champ.rounds)} · {c.laps} Runden", f.tiny, YELLOW,
                  (box.x + 14, box.y + 60), shadow=False)
        draw_text(screen, _fit(fmt, f.tiny, box.w - 160), f.tiny, GREY, (box.x + 14, box.y + 76), shadow=False)
        rec = self.game.records.tracks.get(track.definition.key)
        if rec:
            from .utils import format_time
            draw_text(screen, _fit(f"Rekord {format_time(rec['time'])} {rec.get('driver', '')}", f.tiny, box.w - 160),
                      f.tiny, (120, 200, 255), (box.x + 14, box.y + 92), shadow=False)

    def _buttons(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        acts = self.actions()
        self.sel = min(self.sel, len(acts) - 1)
        rows = [[(k, a) for k, a in enumerate(acts) if a[0] not in self.SECOND_ROW],
                [(k, a) for k, a in enumerate(acts) if a[0] in self.SECOND_ROW]]
        for r, (items, y, h) in enumerate(zip(rows, (624, 672), (42, 30))):
            total_w = SCREEN_WIDTH - 120
            widths = [2.2 if a[0] in ("race", "watch", "review", "sponsor") else 1.0 for _, a in items]
            unit = (total_w - 8 * (len(items) - 1)) / max(1.0, sum(widths))
            x = 60
            for (k, (act, label)), w in zip(items, widths):
                bw = int(unit * w)
                base = GOLD if act in ("race", "watch", "review", "sponsor") else (60, 160, 255) if act == "sim" else \
                    (200, 60, 60) if act == "quit" else (110, 110, 125)
                font = f.small_bold if r == 0 else f.tiny
                self.button(screen, pygame.Rect(x, y, bw, h), _fit(label, font, bw - 12), k == self.sel, base, font)
                mouse_item((x, y, bw, h), self, k)
                x += bw + 8
        ready, why = c.ready_to_race()
        if not ready and not c.season_over:
            draw_text(screen, why, f.tiny, RED, (SCREEN_WIDTH // 2, 708), anchor="center", shadow=False)


class DevelopmentScreen(_Screen):

    accent = (60, 160, 255)

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.sel = 0
        self.rows = list(AREAS) + ["reliability", "crew"] + list(FACILITIES) + ["back"]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        c = self.career
        if event.key == pygame.K_UP:
            self.sel = (self.sel - 1) % len(self.rows)
        elif event.key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % len(self.rows)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            row = self.rows[self.sel]
            if row == "back":
                self.game.open_career()
            elif row == "crew":
                self.say(c.buy_crew())
            elif row in FACILITIES:
                self.say(c.build_facility(row))
            else:
                self.say(c.start_project(row))
        elif event.key == pygame.K_ESCAPE:
            self.game.open_career()

    def _row_info(self, row: str) -> tuple[str, str, int, int, float | None, str]:
        c = self.career
        team = c.team_obj(c.team)
        running = next((p for p in c.projects if p["area"] == row), None)
        if row == "crew":
            cost = crew_cost(c.crew) if c.crew < MAX_CREW else None
            return ("Boxencrew (sofort)", f"{crew_stop_time(c.crew):.2f} s Standzeit (KI 2.40 s)", c.crew, MAX_CREW,
                    cost, "")
        if row in FACILITIES:
            lvl = c.facilities.get(row, 0)
            cost = FACILITY_COST[lvl] if lvl < len(FACILITY_COST) else None
            return (FACILITIES[row][0], FACILITIES[row][1] + f" · {FACILITY_UPKEEP * lvl:.2f} Mio/Rennen", lvl,
                    len(FACILITY_COST), cost, "")
        lvl = c.area_level(row)
        cost = c.project_cost(row) if lvl < MAX_LEVEL else None
        status = f"in Arbeit · noch {running['races_left']} Rd." if running else \
            f"Bauzeit {c.project_duration(row)} Rd."
        if row == "reliability":
            rel = c.teams[c.team].get("reliability", 0.965)
            return ("Zuverlässigkeit", f"{rel * 100:.1f} % · Ausfallrisiko {(1 - rel) * 200:.1f} %/Rennen", lvl,
                    MAX_LEVEL, cost, status)
        name, key, step = AREAS[row]
        val = getattr(team, key)
        return (name, f"{(val - 1) * 100:+.1f} %  ·  {abs(step) * 100:+.1f} % je Stufe", lvl, MAX_LEVEL, cost, status)

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        self.header(screen, "ENTWICKLUNG", f"{c.team} · Budget {c.budget:.1f} Mio · Projekte: "
                                           f"{len(c.projects)}/{MAX_PROJECTS} · Erfolgschance {c.project_success() * 100:.0f} %")
        box = pygame.Rect(60, 106, 720, 560)
        draw_panel(screen, box, PANEL, 215)
        for i, row in enumerate(self.rows):
            y = box.y + 10 + i * 45 + (12 if row in FACILITIES or row == "back" else 0) + (12 if row == "back" else 0)
            selected = i == self.sel
            if row == "back":
                self.button(screen, pygame.Rect(box.x + 20, y, box.w - 40, 34), "ZURÜCK", selected, (110, 110, 125))
                mouse_item((box.x + 20, y, box.w - 40, 34), self, i)
                continue
            mouse_item((box.x + 8, y - 3, box.w - 16, 43), self, i, key=None)
            if row == list(FACILITIES)[0]:
                draw_text(screen, "INFRASTRUKTUR", f.tiny, GREY, (box.x + 20, y - 14), shadow=False)
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (box.x + 8, y - 3, box.w - 16, 43), border_radius=6)
                pygame.draw.rect(screen, self.accent, (box.x + 8, y - 3, 4, 43), border_radius=2)
            name, value, lvl, max_lvl, cost, status = self._row_info(row)
            draw_text(screen, name, f.small_bold, WHITE, (box.x + 22, y), shadow=False)
            draw_text(screen, value, f.tiny, GREY, (box.x + 22, y + 21), shadow=False)
            for k in range(max_lvl):
                bw = 14 if max_lvl > 5 else 26
                pygame.draw.rect(screen, self.accent if k < lvl else (50, 52, 60),
                                 (box.x + 390 + k * (bw + 3), y + 4, bw, 10), border_radius=3)
            if status:
                draw_text(screen, status, f.tiny, (120, 200, 255) if "Arbeit" in status else GREY,
                          (box.x + 390, y + 21), shadow=False)
            label = "MAX" if cost is None else f"{cost:.1f} Mio"
            col = GREY if cost is None else GREEN if c.budget >= cost else RED
            draw_text(screen, label, f.small_bold, col, (box.right - 18, y + 8), anchor="topright", shadow=False)
        rb = pygame.Rect(800, 106, 440, 560)
        draw_panel(screen, rb, PANEL, 215)
        x, y = rb.x + 18, rb.y + 16
        spent = c.season_log.get("dev_spent", 0.0)
        draw_text(screen, "BUDGETOBERGRENZE (ENTWICKLUNG)", f.tiny, GREY, (x, y), shadow=False)
        draw_text(screen, f"{spent:.1f} / {COST_CAP:.0f} Mio", f.medium, YELLOW if spent < COST_CAP else RED,
                  (x, y + 18))
        self.bar(screen, x, y + 48, rb.w - 36, spent / COST_CAP, YELLOW if spent < COST_CAP * 0.8 else RED)
        y += 76
        draw_text(screen, "LAUFENDE PROJEKTE", f.tiny, GREY, (x, y), shadow=False)
        for k, p in enumerate(c.projects):
            name = AREAS[p["area"]][0] if p["area"] in AREAS else "Zuverlässigkeit"
            draw_text(screen, f"{name} · Stufe {c.area_level(p['area']) + 1}", f.small_bold, WHITE,
                      (x, y + 20 + k * 40), shadow=False)
            draw_text(screen, f"fertig nach {p['races_left']} Rennen · {p['cost']:.1f} Mio investiert", f.tiny,
                      (120, 200, 255), (x, y + 40 + k * 40), shadow=False)
        if not c.projects:
            draw_text(screen, "keine", f.small, GREY, (x, y + 20), shadow=False)
        y += 110
        text = ("Projekte kosten sofort Geld, das neue Teil kommt aber erst nach der Bauzeit ans Auto. "
                f"Mit {(1 - c.project_success()) * 100:.0f} % Wahrscheinlichkeit bringt ein Teil nur die halbe Wirkung. "
                "Windkanal: kürzere Bauzeit + höhere Erfolgschance. Simulator: deine Fahrer werden besser. "
                "Fabrik: Teile billiger. Infrastruktur zählt nicht zur Budgetobergrenze, kostet aber laufend. "
                "Auch die KI-Teams entwickeln während der Saison weiter!")
        for k, line in enumerate(_wrap(text, f.small, rb.w - 36)):
            draw_text(screen, line, f.small, (205, 205, 210), (x, y + k * 22), shadow=False)
        self.draw_status(screen, SCREEN_HEIGHT - 26)


class SponsorScreen(_Screen):

    accent = CYAN

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.sel = 0

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        offers = self.career.sponsor_offers
        if event.key in (pygame.K_UP, pygame.K_LEFT):
            self.sel = (self.sel - 1) % max(1, len(offers))
        elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
            self.sel = (self.sel + 1) % max(1, len(offers))
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and offers:
            self.career.choose_sponsor(self.sel)
            self.game.open_career()
        elif event.key == pygame.K_ESCAPE:
            self.game.open_career()

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        self.header(screen, "TITELSPONSOR", f"Saison {c.season} · Teamruf {c.team_rep:.0f} - besserer Ruf bringt "
                                            "bessere Angebote · gilt die ganze Saison")
        races = len(c.championship.rounds)
        for k, o in enumerate(c.sponsor_offers):
            rect = pygame.Rect(60 + k * 395, 130, 370, 440)
            selected = k == self.sel
            mouse_item(rect, self, k, key=None)
            draw_panel(screen, rect, PANEL_LIGHT if selected else PANEL, 225)
            if selected:
                pygame.draw.rect(screen, CYAN, rect, 2, border_radius=8)
            draw_text(screen, o["name"].upper(), f.large, WHITE, (rect.x + 20, rect.y + 20))
            kind = {"fixed": "SICHERHEIT", "points": "LEISTUNG", "podium": "RISIKO"}[o["kind"]]
            draw_text(screen, kind, f.small_bold, CYAN, (rect.x + 20, rect.y + 62), shadow=False)
            draw_text(screen, f"{o['base']:.2f} Mio", f.big, GREEN, (rect.x + 20, rect.y + 100))
            draw_text(screen, "pro Rennen (Grundbetrag)", f.small, GREY, (rect.x + 20, rect.y + 150), shadow=False)
            for i, line in enumerate(_wrap(o["text"], f.small_bold, rect.w - 40)):
                draw_text(screen, line, f.small_bold, YELLOW, (rect.x + 20, rect.y + 190 + i * 24), shadow=False)
            draw_text(screen, f"Garantiert/Saison: {o['base'] * races:.1f} Mio", f.small, WHITE,
                      (rect.x + 20, rect.y + 280), shadow=False)
            text = ("Die Sponsor-Laune (Presse, Punkte, Defekte) verändert den Grundbetrag um -20 % bis +20 %.")
            for i, line in enumerate(_wrap(text, f.tiny, rect.w - 40)):
                draw_text(screen, line, f.tiny, GREY, (rect.x + 20, rect.y + 330 + i * 18), shadow=False)
        draw_text(screen, "Pfeile wählen · ENTER unterschreiben · ESC zurück", f.tiny, GREY,
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 40), anchor="center", shadow=False)


class PressScreen(_Screen):

    accent = (200, 200, 210)

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.sel = 0
        self.result: str | None = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if self.result is not None:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                self.game.open_career()
            return
        n = len(self.career.press.get("answers", [])) or 1
        if event.key == pygame.K_UP:
            self.sel = (self.sel - 1) % n
        elif event.key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.answers = list(self.career.press["answers"])
            self.question = self.career.press["question"]
            self.result = self.career.answer_press(self.sel)

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        self.header(screen, "PRESSEKONFERENZ", "Deine Antwort hat Folgen - wähle mit Bedacht")
        press = c.press if self.result is None else {"question": self.question, "answers": self.answers}
        if not press:
            self.game.open_career()
            return
        box = pygame.Rect(140, 130, 1000, 110)
        draw_panel(screen, box, PANEL, 225)
        draw_text(screen, "JOURNALIST", f.tiny, GREY, (box.x + 20, box.y + 14), shadow=False)
        for k, line in enumerate(_wrap(f"\"{press['question']}\"", f.large, box.w - 40)[:2]):
            draw_text(screen, line, f.large, WHITE, (box.x + 20, box.y + 34 + k * 34))
        for i, ans in enumerate(press["answers"]):
            rect = pygame.Rect(140, 270 + i * 90, 1000, 76)
            selected = i == self.sel
            mouse_item(rect, self, i)
            draw_panel(screen, rect, PANEL_LIGHT if selected else PANEL, 225)
            if selected:
                pygame.draw.rect(screen, GOLD, rect, 2, border_radius=8)
            draw_text(screen, f"{i + 1}", f.large, GOLD if selected else GREY, (rect.x + 24, rect.y + 20))
            draw_text(screen, _fit(ans["text"], f.medium, rect.w - 90), f.medium, WHITE, (rect.x + 70, rect.y + 26))
        if self.result is not None:
            draw_text(screen, f"Wirkung: {self.result}", f.medium, CYAN, (SCREEN_WIDTH // 2, 560), anchor="center")
            draw_text(screen, "ENTER: weiter", f.small, GREY, (SCREEN_WIDTH // 2, 600), anchor="center")
        else:
            draw_text(screen, "Pfeile wählen · ENTER antworten", f.tiny, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 40),
                      anchor="center", shadow=False)


class HistoryScreen(_Screen):

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.game.open_career()

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        st = c.stats
        self.header(screen, "HISTORIE", f"{c.player_name} · {c.season - (0 if not c.season_over else -1) - 1} "
                                        f"abgeschlossene Saison(s)")
        box = pygame.Rect(60, 106, 820, 560)
        draw_panel(screen, box, PANEL, 215)
        cols = [(16, "SAISON"), (90, "TEAM"), (260, "FAHRER-WM"), (360, "TEAM-WM"), (450, "SIEGE"), (510, "PODIEN"),
                (580, "PUNKTE"), (650, "WELTMEISTER")]
        for x, h in cols:
            draw_text(screen, h, f.tiny, GREY, (box.x + x, box.y + 12), shadow=False)
        if not c.history:
            draw_text(screen, "Noch keine Saison abgeschlossen.", f.small, GREY, (box.x + 16, box.y + 44),
                      shadow=False)
        for i, h in enumerate(c.history[-14:]):
            y = box.y + 38 + i * 36
            mine_title = h.get("champion") == c.player_name
            if mine_title:
                pygame.draw.rect(screen, (70, 56, 10), (box.x + 6, y - 4, box.w - 12, 32), border_radius=5)
            vals = [str(h["season"]), _fit(h.get("team", "-") or "-", f.small_bold, 160),
                    f"P{h['driver_pos']}" if h.get("driver_pos") else "-", f"P{h['team_pos']}" if h.get("team_pos")
                    else "-", str(h.get("wins", "-")), str(h.get("podiums", "-")), str(h.get("points", "-")),
                    _fit(h.get("champion", "-"), f.small_bold, 160)]
            for (x, _), v in zip(cols, vals):
                draw_text(screen, v, f.small_bold, GOLD if mine_title else WHITE, (box.x + x, y), shadow=False)
        sb = pygame.Rect(900, 106, 340, 560)
        draw_panel(screen, sb, PANEL, 215)
        draw_text(screen, "GESAMT", f.tiny, GREY, (sb.x + 18, sb.y + 14), shadow=False)
        items = [("Titel", st.get("titles", 0)), ("Rennen", st.get("races", 0)), ("Siege", st.get("wins", 0)),
                 ("Podien", st.get("podiums", 0)), ("Punkte", st.get("points", 0))]
        for k, (label, v) in enumerate(items):
            draw_text(screen, label, f.medium, GREY, (sb.x + 18, sb.y + 44 + k * 52))
            draw_text(screen, str(v), f.big, GOLD if label == "Titel" and v else WHITE, (sb.right - 18, sb.y + 34 + k * 52),
                      anchor="topright")
        best = min((h["driver_pos"] for h in c.history if h.get("driver_pos")), default=None)
        if best:
            draw_text(screen, f"Beste WM-Platzierung: P{best}", f.small_bold, CYAN, (sb.x + 18, sb.y + 320),
                      shadow=False)
        draw_text(screen, "ENTER/ESC zurück", f.tiny, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 26), anchor="center",
                  shadow=False)


class MarketScreen(_Screen):

    accent = (60, 220, 140)
    VISIBLE = 15

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.sel = 0
        self.scroll = 0
        self.years = 2
        self.confirm_release: str | None = None
        self.sort = 0

    def entries(self) -> list[str]:
        c = self.career
        free = [n for n, d in c.drivers.items() if not d.get("default") and not d["team"]]
        key = [lambda n: -c.drivers[n]["rating"], lambda n: c.drivers[n]["salary"], lambda n: c.drivers[n]["age"]]
        return c.own_drivers() + sorted(free, key=key[self.sort])

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        entries = self.entries()
        c = self.career
        if event.key == pygame.K_UP:
            self.sel = (self.sel - 1) % len(entries)
            self.confirm_release = None
        elif event.key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % len(entries)
            self.confirm_release = None
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.years = max(1, min(3, self.years + (-1 if event.key == pygame.K_LEFT else 1)))
        elif event.key == pygame.K_TAB:
            self.sort = (self.sort + 1) % 3
            self.say(["Sortiert nach Wertung", "Sortiert nach Gehalt", "Sortiert nach Alter"][self.sort])
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and entries:
            name = entries[min(self.sel, len(entries) - 1)]
            if c.drivers[name]["team"] == c.team:
                if self.confirm_release == name:
                    self.say(c.release(name))
                    self.confirm_release = None
                else:
                    self.confirm_release = name
                    self.say(f"Nochmal ENTER: {name} entlassen?")
            else:
                self.say(c.sign(name, self.years))
        elif event.key == pygame.K_ESCAPE:
            self.game.open_career()
        self.sel = min(self.sel, max(0, len(self.entries()) - 1))
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + self.VISIBLE:
            self.scroll = self.sel - self.VISIBLE + 1

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        self.header(screen, "FAHRERMARKT",
                    f"{c.team} · Budget {c.budget:.1f} Mio · Ruf {c.team_rep:.0f} · freie Cockpits: {max(0, c.seats())}")
        box = pygame.Rect(60, 106, 800, 560)
        draw_panel(screen, box, PANEL, 215)
        cols = [(16, "FAHRER"), (250, "LAND"), (300, "ALTER"), (360, "WERTUNG"), (440, "POTENZIAL"), (530, "STIL"),
                (630, "GEHALT"), (720, "RUF")]
        for x, h in cols:
            draw_text(screen, h, f.tiny, GREY, (box.x + x, box.y + 10), shadow=False)
        entries = self.entries()
        own = set(c.own_drivers())
        for i, name in enumerate(entries[self.scroll:self.scroll + self.VISIBLE]):
            idx = self.scroll + i
            d = c.drivers[name]
            y = box.y + 34 + i * 34
            mouse_item((box.x + 6, y - 4, box.w - 12, 32), self, idx, key=None)
            if idx == self.sel:
                pygame.draw.rect(screen, PANEL_LIGHT, (box.x + 6, y - 4, box.w - 12, 32), border_radius=5)
                pygame.draw.rect(screen, self.accent, (box.x + 6, y - 4, 4, 32), border_radius=2)
            if name in own:
                pygame.draw.rect(screen, (0, 70, 100), (box.x + 12, y - 2, box.w - 24, 28), border_radius=5)
            need = c.required_rep(name)
            willing = c.team_rep >= need
            draw_text(screen, _fit(name, f.small_bold, 225), f.small_bold, CYAN if name in own else WHITE,
                      (box.x + 16, y), shadow=False)
            draw_text(screen, d["nationality"], f.tiny, GREY, (box.x + 250, y + 3), shadow=False)
            draw_text(screen, str(d["age"]), f.mono, WHITE, (box.x + 300, y + 1), shadow=False)
            r = d["rating"]
            rc = GREEN if r >= 85 else YELLOW if r >= 75 else WHITE
            draw_text(screen, str(r), f.mono, rc, (box.x + 360, y + 1), shadow=False)
            self.bar(screen, box.x + 390, y + 7, 40, (r - 55) / 40, rc, 6)
            pot = d.get("potential", r)
            draw_text(screen, str(pot) + (" ↑" if pot > r + 2 else ""), f.mono, (180, 220, 255),
                      (box.x + 440, y + 1), shadow=False)
            draw_text(screen, d["style"], f.tiny, WHITE, (box.x + 530, y + 3), shadow=False)
            draw_text(screen, f"{d['salary']:.1f}", f.mono, WHITE, (box.x + 630, y + 1), shadow=False)
            if name in own:
                draw_text(screen, f"im Team · {d.get('years', 0)} J.", f.tiny, CYAN, (box.x + 700, y + 3), shadow=False)
            else:
                draw_text(screen, f"{need:.0f}", f.mono, GREEN if willing else RED, (box.x + 720, y + 1), shadow=False)
        if len(entries) > self.VISIBLE:
            frac = self.scroll / max(1, len(entries) - self.VISIBLE)
            pygame.draw.rect(screen, (60, 62, 72), (box.right - 8, box.y + 34, 4, box.h - 44), border_radius=2)
            pygame.draw.rect(screen, self.accent, (box.right - 8, box.y + 34 + frac * (box.h - 84), 4, 40),
                             border_radius=2)
        self._detail(screen, entries)
        self.draw_status(screen)

    def _detail(self, screen: pygame.Surface, entries: list[str]) -> None:
        f, c = self.game.fonts, self.career
        box = pygame.Rect(880, 106, 360, 560)
        draw_panel(screen, box, PANEL, 215)
        if not entries:
            return
        name = entries[min(self.sel, len(entries) - 1)]
        d = c.drivers[name]
        x, y = box.x + 18, box.y + 18
        pygame.draw.circle(screen, tuple(d["helmet"]), (box.right - 40, y + 22), 18)
        draw_text(screen, _fit(name, f.medium, 260), f.medium, WHITE, (x, y))
        draw_text(screen, f"{d['nationality']} · {d['age']} Jahre · Stil: {d['style']}", f.small, GREY, (x, y + 30),
                  shadow=False)
        from .career import rating_to_checkpoint, rating_to_pace
        lines = [("Wertung", f"{d['rating']}  (Potenzial {d.get('potential', d['rating'])})"),
                 ("Tempo", f"{(rating_to_pace(d['rating']) - 1) * 100:+.1f} % Leistung"),
                 ("KI-Erfahrung", rating_to_checkpoint(d["rating"])),
                 ("Reifenmanagement", f"{(1 - d['tyre_mgmt']) * 100:+.0f} % Verschleiß"),
                 ("Gehalt", f"{d['salary']:.1f} Mio / Saison"),
                 ("Ablöse", f"{d['salary'] * 0.5:.1f} Mio (einmalig)")]
        for k, (label, val) in enumerate(lines):
            draw_text(screen, label, f.tiny, GREY, (x, y + 66 + k * 30), shadow=False)
            draw_text(screen, val, f.small_bold, WHITE, (x + 140, y + 62 + k * 30), shadow=False)
        yy = y + 260
        if d["team"] == c.team:
            cost = d["salary"] * 0.5 * max(1, d.get("years", 1))
            draw_text(screen, f"Vertrag: noch {d.get('years', 0)} Saison(s)", f.small_bold, CYAN, (x, yy),
                      shadow=False)
            draw_text(screen, f"ENTER (2x): entlassen · Abfindung {cost:.1f} Mio", f.small, RED, (x, yy + 28),
                      shadow=False)
        else:
            need = c.required_rep(name)
            ok = c.team_rep >= need
            draw_text(screen, f"Vertragslänge: < {self.years} Saison{'s' if self.years > 1 else ''} >", f.small_bold,
                      YELLOW, (x, yy), shadow=False)
            draw_text(screen, ("Würde unterschreiben" if ok else f"Will ein Team mit Ruf {need:.0f}"),
                      f.small_bold, GREEN if ok else RED, (x, yy + 28), shadow=False)
            draw_text(screen, "ENTER: verpflichten", f.small, WHITE, (x, yy + 56), shadow=False)
        hint = "Pfeile hoch/runter wählen · links/rechts Vertragslänge · TAB sortieren · ESC zurück"
        for k, line in enumerate(_wrap(hint, f.tiny, box.w - 36)):
            draw_text(screen, line, f.tiny, GREY, (x, box.bottom - 50 + k * 17), shadow=False)


class SeasonReviewScreen(_Screen):

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.review: dict[str, Any] = self.career.finish_season()
        self.sel = 0

    def rows(self) -> list[str]:
        c = self.career
        return (c.expiring() if c.kind == "team" else []) + ["next"]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        rows = self.rows()
        if event.key == pygame.K_UP:
            self.sel = (self.sel - 1) % len(rows)
        elif event.key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % len(rows)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            row = rows[min(self.sel, len(rows) - 1)]
            c = self.career
            if row != "next":
                self.say(c.renew(row))
                self.sel = 0
            elif c.kind == "driver":
                self.game.state = OfferScreen(self.game)
            else:
                c.start_next_season()
                self.game.open_career()
        elif event.key == pygame.K_ESCAPE:
            self.game.open_career()

    def draw(self, screen: pygame.Surface) -> None:
        f, c, r = self.game.fonts, self.career, self.review
        self.header(screen, f"SAISON {r['season']} · ABSCHLUSS", self.career.goal_text())
        box = pygame.Rect(60, 106, 560, 540)
        draw_panel(screen, box, PANEL, 215)
        x, y = box.x + 20, box.y + 18
        pulse = 0.75 + 0.25 * math.sin(self.t * 3)
        draw_text(screen, "WELTMEISTER", f.tiny, GREY, (x, y), shadow=False)
        draw_text(screen, r["champion"], f.large, tuple(int(v * pulse) for v in (255, 215, 0)), (x, y + 16))
        draw_text(screen, f"Konstrukteurs-Weltmeister: {r['team_champion']}", f.small_bold, WHITE, (x, y + 56),
                  shadow=False)
        yy = y + 100
        if r.get("driver_pos"):
            draw_text(screen, f"Dein Platz in der Fahrer-WM: P{r['driver_pos']}", f.medium, CYAN, (x, yy))
            yy += 34
        if c.kind == "team" and r.get("team_pos"):
            draw_text(screen, f"{c.team} in der Konstrukteurs-WM: P{r['team_pos']}", f.medium, CYAN, (x, yy))
            yy += 34
        draw_text(screen, "SAISONZIEL ERREICHT!" if r["goal_met"] else "Saisonziel verfehlt", f.medium,
                  GREEN if r["goal_met"] else RED, (x, yy))
        yy += 44
        log = r["log"]
        if c.kind == "driver":
            items = [("Ruf", f"{c.reputation:.0f}/100 (vorher {log.get('start_rep', 0):.0f})"),
                     ("Gehalt + Prämien", f"{log.get('income', 0):.1f} Mio"),
                     ("Duelle gegen Rivalen", f"{log.get('rival_ahead', 0)} : {log.get('rival_behind', 0)}"),
                     ("Duelle gegen Teamkollegen", f"{log.get('mate_ahead', 0)} : {log.get('mate_behind', 0)}"),
                     ("Vertrag", f"noch {max(0, c.contract.get('years', 0))} Saison(s) bei {c.team}")]
        else:
            items = [("Einnahmen", f"{log.get('income', 0):.1f} Mio"),
                     ("Ausgaben", f"{log.get('expenses', 0):.1f} Mio"),
                     ("Preisgeld Konstrukteure", f"{r.get('prize', 0):.1f} Mio"),
                     ("Budget jetzt", f"{c.budget:.1f} Mio"),
                     ("Ruf", f"{c.team_rep:.0f}/100 (vorher {log.get('start_rep', 0):.0f})")]
        for k, (label, val) in enumerate(items):
            draw_text(screen, label, f.small, GREY, (x, yy + k * 30), shadow=False)
            draw_text(screen, val, f.small_bold, WHITE, (x + 250, yy + k * 30), shadow=False)
        rb = pygame.Rect(640, 106, 600, 540)
        draw_panel(screen, rb, PANEL, 215)
        rows = self.rows()
        self.sel = min(self.sel, len(rows) - 1)
        ry = rb.y + 18
        if c.kind == "team":
            draw_text(screen, "AUSLAUFENDE VERTRÄGE", f.tiny, GREY, (rb.x + 18, ry), shadow=False)
            ry += 22
            if not c.expiring():
                draw_text(screen, "Keine - alle Fahrer bleiben.", f.small, WHITE, (rb.x + 18, ry), shadow=False)
                ry += 30
        else:
            draw_text(screen, "Am Saisonende kommen neue Vertragsangebote." if c.contract.get("years", 0) <= 0 else
                      "Dein Vertrag läuft weiter - du kannst trotzdem wechseln.", f.small, WHITE, (rb.x + 18, ry),
                      shadow=False)
            ry += 40
        for i, row in enumerate(rows):
            selected = i == self.sel
            if row == "next":
                label = "VERTRAGSANGEBOTE ANSEHEN" if c.kind == "driver" else f"SAISON {c.season + 1} STARTEN"
                self.button(screen, pygame.Rect(rb.x + 20, rb.bottom - 70, rb.w - 40, 50), label, selected, GOLD,
                            f.medium)
                mouse_item((rb.x + 20, rb.bottom - 70, rb.w - 40, 50), self, i)
                continue
            d = c.drivers[row]
            rect = pygame.Rect(rb.x + 14, ry, rb.w - 28, 40)
            mouse_item(rect, self, i, key=None)
            pygame.draw.rect(screen, PANEL_LIGHT if selected else (30, 32, 40), rect, border_radius=6)
            draw_text(screen, f"{row} · Wertung {d['rating']} · {d['salary']:.1f} Mio", f.small_bold, WHITE,
                      (rect.x + 12, rect.y + 10), shadow=False)
            draw_text(screen, "ENTER: verlängern (+10 % Gehalt)", f.tiny, GREEN, (rect.right - 12, rect.y + 13),
                      anchor="topright", shadow=False)
            ry += 48
        if c.kind == "team" and c.expiring():
            draw_text(screen, "Nicht verlängerte Fahrer verlassen das Team zur neuen Saison.", f.tiny, GREY,
                      (rb.x + 18, ry + 6), shadow=False)
        self.draw_status(screen)


class CareerSlotScreen(_Screen):

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.col = 0
        self.row = 0
        self.confirm_delete: str | None = None
        self.summaries = {slot: slot_summary(slot) for kind in SLOTS for slot in SLOTS[kind]}

    @property
    def slot(self) -> str | None:
        return None if self.row >= 3 else SLOTS["driver" if self.col == 0 else "team"][self.row]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_UP:
            self.row = (self.row - 1) % 4
        elif event.key == pygame.K_DOWN:
            self.row = (self.row + 1) % 4
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.col = 1 - self.col
        elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE) and self.slot and self.summaries.get(self.slot):
            if self.confirm_delete == self.slot:
                Career.delete(self.slot)
                self.summaries[self.slot] = None
                self.say(f"Slot {self.slot[-1]} gelöscht")
                self.confirm_delete = None
            else:
                self.confirm_delete = self.slot
                self.say("Nochmal ENTF: Spielstand wirklich löschen?")
            return
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.slot is None:
                self.game.go_to_menu()
                return
            if self.summaries.get(self.slot):
                career = Career.load(self.slot)
                if career is None:
                    self.say("Spielstand beschädigt - mit ENTF löschen")
                    return
                self.game.career = career
                self.game.open_career()
            else:
                self.game.state = CareerSetupScreen(self.game, self.slot)
            return
        elif event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()
            return
        self.confirm_delete = None

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.header(screen, "KARRIERE · SPIELSTÄNDE", "3 Slots pro Karriere-Art · jeder Slot ist eine eigene Datei "
                                                      "in data/careers/")
        for col, (kind, title, accent) in enumerate((("driver", "FAHRER-KARRIERE", GOLD),
                                                     ("team", "TEAM-KARRIERE", (60, 160, 255)))):
            x = 60 + col * 600
            draw_text(screen, title, f.medium, accent, (x, 110))
            for row, slot in enumerate(SLOTS[kind]):
                rect = pygame.Rect(x, 146 + row * 150, 560, 136)
                selected = self.col == col and self.row == row
                mouse_item(rect, self, (col, row), attr=("col", "row"))
                draw_panel(screen, rect, PANEL_LIGHT if selected else PANEL, 225)
                if selected:
                    pygame.draw.rect(screen, accent, rect, 2, border_radius=8)
                draw_text(screen, f"SLOT {row + 1}", f.tiny, GREY, (rect.x + 18, rect.y + 12), shadow=False)
                sm = self.summaries.get(slot)
                if not sm:
                    draw_text(screen, "- leer -", f.large, (90, 92, 104), (rect.x + 18, rect.y + 36))
                    draw_text(screen, "ENTER: neue Karriere starten", f.small, GREY, (rect.x + 18, rect.y + 86),
                              shadow=False)
                    continue
                team = sm["team"] or "ohne Vertrag"
                col_rgb = tuple(self._team_color(slot, sm["team"]))
                pygame.draw.rect(screen, col_rgb, (rect.x, rect.y, 7, rect.h), border_radius=4)
                draw_text(screen, _fit(team.upper(), f.large, 360), f.large, WHITE, (rect.x + 18, rect.y + 30))
                draw_text(screen, sm["saved"], f.tiny, GREY, (rect.right - 16, rect.y + 12), anchor="topright",
                          shadow=False)
                line = f"Saison {sm['season']} · Rennen {sm['round']}/{sm['rounds']} · {sm['player']}"
                draw_text(screen, _fit(line, f.small, 520), f.small, (210, 210, 215), (rect.x + 18, rect.y + 72),
                          shadow=False)
                if kind == "driver":
                    extra = f"Ruf {sm['reputation']:.0f} · Siege {sm['wins']} · Titel {sm['titles']}"
                else:
                    extra = f"Budget {sm['budget']:.1f} Mio · Ruf {sm['reputation']:.0f} · Titel {sm['titles']}"
                draw_text(screen, extra, f.small_bold, accent, (rect.x + 18, rect.y + 98), shadow=False)
                if self.confirm_delete == slot:
                    draw_text(screen, "ENTF = LÖSCHEN", f.small_bold, RED, (rect.right - 16, rect.y + 98),
                              anchor="topright", shadow=False)
        self.button(screen, pygame.Rect(SCREEN_WIDTH // 2 - 150, 610, 300, 40), "ZURÜCK", self.row == 3,
                    (110, 110, 125))
        mouse_item((SCREEN_WIDTH // 2 - 150, 610, 300, 40), self, 3, attr="row")
        draw_text(screen, "Pfeile wählen · ENTER laden/neu · ENTF löschen · ESC Hauptmenü", f.tiny, GREY,
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 40), anchor="center", shadow=False)
        self.draw_status(screen, SCREEN_HEIGHT - 18)

    def _team_color(self, slot: str, team: str) -> tuple[int, int, int]:
        for t in self.game.teams:
            if t.name == team:
                return t.color
        return (255, 0, 140) if slot.startswith("team") else (150, 150, 150)


class CarCompareScreen(_Screen):

    STATS = [("Motor", "engine", False), ("Aero", "aero", False), ("Topspeed", "top_speed", False),
             ("Bremsen", "brakes", False), ("Reifen", "tyre_wear", True)]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.game.open_career()

    def _val(self, team: str, key: str, inverse: bool) -> float:
        v = self.career.teams[team][key]
        return 2.0 - v if inverse else v

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        mine = c.team
        ranking = c.team_ranking()
        self.header(screen, "AUTO-VERGLEICH", (f"Dein Auto ({mine}): P{ranking.index(mine) + 1} von {len(ranking)}"
                                               if mine else "Noch kein Team") + " · Werte relativ zum Referenzauto")
        box = pygame.Rect(60, 106, 440, 540)
        draw_panel(screen, box, PANEL, 215)
        if mine:
            col = tuple(c.teams[mine]["color"])
            pygame.draw.rect(screen, col, (box.x, box.y, box.w, 6), border_radius=3)
            draw_text(screen, mine.upper(), f.large, WHITE, (box.x + 18, box.y + 18))
            for k, (label, key, inv) in enumerate(self.STATS):
                y = box.y + 80 + k * 76
                vals = {t: self._val(t, key, inv) for t in c.teams}
                order = list(vals)
                avg = sum(vals.values()) / len(vals)
                best = max(vals.values())
                lo, hi = min(vals.values()) - 0.01, best + 0.01
                me = vals[mine]
                rank = 1 + sum(1 for v in vals.values() if v > me + 1e-9)
                draw_text(screen, label, f.medium, WHITE, (box.x + 18, y))
                draw_text(screen, f"P{rank}/{len(order)}", f.small_bold, GREEN if rank <= 3 else YELLOW if
                          rank <= len(order) // 2 + 1 else RED, (box.right - 18, y + 2), anchor="topright",
                          shadow=False)
                bx, bw = box.x + 18, box.w - 36

                def px(v: float) -> int:
                    return bx + int(bw * (v - lo) / max(1e-6, hi - lo))
                pygame.draw.rect(screen, (45, 45, 52), (bx, y + 32, bw, 10), border_radius=4)
                pygame.draw.rect(screen, _visible(col), (bx, y + 32, px(me) - bx, 10), border_radius=4)
                pygame.draw.line(screen, WHITE, (px(avg), y + 26), (px(avg), y + 48), 2)
                pygame.draw.line(screen, GOLD, (px(best), y + 26), (px(best), y + 48), 2)
                diff = (me - best) * 100
                draw_text(screen, f"{(me - 1) * 100:+.1f}%  ·  zum Besten {diff:+.1f}%", f.tiny, GREY,
                          (bx, y + 50), shadow=False)
            draw_text(screen, "weiß = Feld-Schnitt · gold = bestes Auto", f.tiny, GREY, (box.x + 18, box.bottom - 26),
                      shadow=False)
        tb = pygame.Rect(520, 106, 720, 540)
        draw_panel(screen, tb, PANEL, 215)
        cols = [(16, "TEAM"), (230, "MOTOR"), (320, "AERO"), (410, "SPEED"), (500, "BREMSE"), (590, "REIFEN"),
                (668, "GESAMT")]
        for x, h in cols:
            draw_text(screen, h, f.tiny, GREY, (tb.x + x, tb.y + 12), shadow=False)
        best = {key: max(self._val(t, key, inv) for t in c.teams) for _, key, inv in self.STATS}
        row_h = min(38, (tb.h - 50) // max(1, len(ranking)))
        for i, team in enumerate(ranking):
            y = tb.y + 40 + i * row_h
            own = team == mine
            if own:
                pygame.draw.rect(screen, (0, 70, 100), (tb.x + 6, y - 4, tb.w - 12, row_h - 4), border_radius=5)
            tc = tuple(c.teams[team]["color"])
            pygame.draw.rect(screen, tc, (tb.x + 14, y, 5, row_h - 12))
            draw_text(screen, f"{i + 1}. {_fit(team, f.small_bold, 175)}", f.small_bold, CYAN if own else WHITE,
                      (tb.x + 26, y), shadow=False)
            for (x, _), (_, key, inv) in zip(cols[1:6], self.STATS):
                v = self._val(team, key, inv)
                colv = GOLD if v >= best[key] - 1e-9 else WHITE if v >= 1.0 else (220, 150, 140)
                draw_text(screen, f"{(v - 1) * 100:+.1f}", f.mono, colv, (tb.x + x, y + 1), shadow=False)
            draw_text(screen, f"{(c.team_obj(team).rating - 1) * 100:+.1f}", f.mono, YELLOW, (tb.x + 668, y + 1),
                      shadow=False)
        draw_text(screen, "ENTER/ESC zurück", f.tiny, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 26), anchor="center",
                  shadow=False)
