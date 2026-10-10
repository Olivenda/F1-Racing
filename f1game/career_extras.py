# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

from .career import NATIONALITIES, PERSONAL, PERSONAL_COST, REBRAND_COST
from .career_achievements import ACHIEVEMENTS, available
from .career_screens import GOLD, MEDAL, RED, _fit, _Screen, _wrap, draw_form, draw_livery
from .championship import FORMATS
from .settings import CYAN, DIFFICULTY_LEVELS, GREEN, GREY, PANEL, PANEL_LIGHT, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, \
    YELLOW
from .utils import draw_panel, draw_text, mouse_item

if TYPE_CHECKING:
    from .game import Game


def _to_hsv(rgb: tuple[int, int, int] | list[int]) -> list[float]:
    h, s, v, _ = pygame.Color(*[int(c) for c in rgb]).hsva
    return [h, s, v]


def _to_rgb(hsv: list[float]) -> tuple[int, int, int]:
    col = pygame.Color(0, 0, 0)
    col.hsva = (hsv[0] % 360, max(0.0, min(100.0, hsv[1])), max(0.0, min(100.0, hsv[2])), 100)
    return col.r, col.g, col.b


class _RowScreen(_Screen):
    """Vertical list of selectable rows with a coloured highlight - shared by the small career screens."""

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self.sel = 0

    def rows(self) -> list[str]:
        return []

    def move(self, event: pygame.event.Event) -> bool:
        rows = self.rows()
        if event.key == pygame.K_UP:
            self.sel = (self.sel - 1) % len(rows)
        elif event.key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % len(rows)
        else:
            return False
        return True

    @property
    def row(self) -> str:
        rows = self.rows()
        self.sel = min(self.sel, len(rows) - 1)
        return rows[self.sel]

    def highlight(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        pygame.draw.rect(screen, PANEL_LIGHT, rect, border_radius=6)
        pygame.draw.rect(screen, self.accent, (rect.x, rect.y, 5, rect.h), border_radius=2)


# ------------------------------------------------------------------------------------------------ design studio

class DesignScreen(_RowScreen):

    accent = (255, 120, 200)
    HSV_ROWS = {"Auto: Farbton": ("car", 0, 10), "Auto: Sättigung": ("car", 1, 5), "Auto: Helligkeit": ("car", 2, 5),
                "Helm: Farbton": ("helmet", 0, 10), "Helm: Sättigung": ("helmet", 1, 5),
                "Helm: Helligkeit": ("helmet", 2, 5)}
    TEXT_ROWS = {"Teamname": ("team_name", 20), "Fahrername": ("name", 20), "Dein Name": ("name", 20),
                 "Kürzel": ("short", 3)}

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        c = self.career
        self.name = c.player_name
        self.short = c.short_code
        self.number = c.player_number or 1
        self.nation = NATIONALITIES.index(c.player_nationality) if c.player_nationality in NATIONALITIES else 0
        self.helmet = _to_hsv(c.helmet)
        team_col = c.teams[c.team]["color"] if c.team else [150, 150, 158]
        self.car = _to_hsv(team_col)
        self.team_name = c.team
        self._repeat = pygame.key.get_repeat()
        pygame.key.set_repeat(280, 45)

    def rows(self) -> list[str]:
        c = self.career
        rows: list[str] = []
        if c.kind == "team":
            rows += ["Teamname", "Auto: Farbton", "Auto: Sättigung", "Auto: Helligkeit"]
        if c.player_drives:
            rows += ["Fahrername", "Kürzel", "Startnummer", "Nationalität", "Helm: Farbton", "Helm: Sättigung",
                     "Helm: Helligkeit"]
        else:
            rows += ["Dein Name"]
        return rows + ["SPEICHERN", "ZURÜCK"]

    def _leave(self) -> None:
        pygame.key.set_repeat(*self._repeat)
        self.game.open_career()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        row = self.row
        text = self.TEXT_ROWS.get(row)
        if self.move(event):
            return
        if text and event.key == pygame.K_BACKSPACE:
            setattr(self, text[0], getattr(self, text[0])[:-1])
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
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            d = -1 if event.key == pygame.K_LEFT else 1
            if row in self.HSV_ROWS:
                target, idx, step = self.HSV_ROWS[row]
                hsv = getattr(self, target)
                hsv[idx] = (hsv[idx] + d * step) % 360 if idx == 0 else max(0.0, min(100.0, hsv[idx] + d * step))
            elif row == "Startnummer":
                self.number = (self.number - 1 + d) % 99 + 1
            elif row == "Nationalität":
                self.nation = (self.nation + d) % len(NATIONALITIES)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if row == "SPEICHERN":
                self._apply()
            elif row == "ZURÜCK":
                self._leave()
            else:
                self.sel = (self.sel + 1) % len(self.rows())
        elif event.key == pygame.K_ESCAPE:
            self._leave()

    def _apply(self) -> None:
        c = self.career
        msgs = []
        if not self.name.strip():
            self.say("Der Name darf nicht leer sein")
            return
        if c.kind == "team" and self.team_name.strip() and self.team_name.strip() != c.team:
            msg = c.rename_team(self.team_name)
            if msg and not msg.startswith("Team heißt"):
                self.say(msg)
                return
            msgs.append(msg)
        if self.name.strip() != c.player_name:
            msg = c.rename_player(self.name)
            if msg and not msg.startswith("Name geändert"):
                self.say(msg)
                return
            msgs.append(msg)
        if c.player_drives:
            c.set_identity(self.short, self.number, NATIONALITIES[self.nation], _to_rgb(self.helmet))
        if c.kind == "team":
            c.teams[c.team]["color"] = list(_to_rgb(self.car))
        c.save()
        self.say(" · ".join(m for m in msgs if m) or "Design gespeichert")

    def _value(self, row: str) -> str:
        cursor = "_" if int(self.t * 2) % 2 and row == self.row else ""
        if row == "Teamname":
            return self.team_name + cursor
        if row in ("Fahrername", "Dein Name"):
            return self.name + cursor
        if row == "Kürzel":
            return self.short + cursor
        if row == "Startnummer":
            return f"#{self.number}"
        if row == "Nationalität":
            return NATIONALITIES[self.nation] or "- keine -"
        return ""

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        self.header(screen, "DESIGN-STUDIO", "Lackierung, Helm, Startnummer und Namen anpassen"
                    + (f" · Team umbenennen kostet {REBRAND_COST:.0f} Mio" if c.kind == "team" else ""))
        box = pygame.Rect(60, 106, 560, 560)
        draw_panel(screen, box, PANEL, 215)
        rows = self.rows()
        rh = min(44, (box.h - 20) // len(rows))
        for i, row in enumerate(rows):
            y = box.y + 10 + i * rh
            selected = i == self.sel
            if row in ("SPEICHERN", "ZURÜCK"):
                self.button(screen, pygame.Rect(box.x + 20, y + 2, box.w - 40, rh - 8), row, selected,
                            GOLD if row == "SPEICHERN" else (110, 110, 125))
                mouse_item((box.x + 20, y + 2, box.w - 40, rh - 8), self, i)
                continue
            r = pygame.Rect(box.x + 10, y, box.w - 20, rh - 4)
            mouse_item(r, self, i, key=None, arrows=True)
            if selected:
                self.highlight(screen, r)
            draw_text(screen, row.upper(), f.tiny, GREY, (box.x + 26, r.centery), anchor="midleft", shadow=False)
            if row in self.HSV_ROWS:
                target, idx, _ = self.HSV_ROWS[row]
                hsv = getattr(self, target)
                sx, sw = box.x + 200, 260
                steps = 24
                for k in range(steps):
                    probe = list(hsv)
                    probe[idx] = k / (steps - 1) * (359 if idx == 0 else 100)
                    pygame.draw.rect(screen, _to_rgb(probe), (sx + k * sw // steps, r.centery - 7,
                                                              sw // steps + 1, 14))
                frac = hsv[idx] / (360 if idx == 0 else 100)
                kx = sx + int(frac * sw)
                pygame.draw.rect(screen, WHITE, (kx - 3, r.centery - 11, 6, 22), border_radius=2)
                draw_text(screen, f"{hsv[idx]:.0f}", f.tiny, WHITE, (box.right - 26, r.centery), anchor="midright",
                          shadow=False)
            else:
                draw_text(screen, self._value(row), f.small_bold, CYAN if row in self.TEXT_ROWS else WHITE,
                          (box.x + 200, r.centery), anchor="midleft", shadow=False)
                if selected and row not in self.TEXT_ROWS:
                    draw_text(screen, "<  >", f.medium, YELLOW, (box.right - 24, r.centery), anchor="midright")
        pb = pygame.Rect(640, 106, 600, 560)
        draw_panel(screen, pb, PANEL, 215)
        body = _to_rgb(self.car)
        helmet = _to_rgb(self.helmet) if c.player_drives else (60, 60, 66)
        draw_livery(screen, f, pygame.Rect(pb.x + 20, pb.y + 20, pb.w - 40, 280), body, helmet,
                    self.number if c.player_drives else 0, self.short if c.player_drives else "", self.t)
        y = pb.y + 316
        draw_text(screen, _fit(self.name or "?", f.large, pb.w - 40), f.large, WHITE, (pb.x + 20, y))
        team = self.team_name if c.kind == "team" else (c.team or "ohne Team")
        draw_text(screen, f"{team} · {NATIONALITIES[self.nation] or '-'}", f.small_bold, GREY, (pb.x + 22, y + 40),
                  shadow=False)
        draw_text(screen, "SO SIEHT ES IM TIMING-TOWER AUS", f.tiny, GREY, (pb.x + 20, y + 80), shadow=False)
        tower = pygame.Rect(pb.x + 20, y + 98, 260, 30)
        pygame.draw.rect(screen, (12, 12, 16), tower, border_radius=4)
        draw_text(screen, "3", f.small_bold, WHITE, (tower.x + 12, tower.centery), anchor="midleft", shadow=False)
        pygame.draw.rect(screen, body, (tower.x + 34, tower.y + 6, 5, tower.h - 12))
        draw_text(screen, (self.short or "YOU") if c.player_drives else "---", f.small_bold, CYAN,
                  (tower.x + 48, tower.centery), anchor="midleft", shadow=False)
        draw_text(screen, "+1.234", f.mono, GREY, (tower.right - 10, tower.centery), anchor="midright", shadow=False)
        if c.kind == "driver":
            note = "Die Autofarbe bestimmt dein Team - Helm, Nummer, Kürzel und Name gehören dir."
        else:
            note = (f"Lackierung ist kostenlos. Ein neuer Teamname kostet {REBRAND_COST:.0f} Mio (Rebranding) und "
                    "wird auch in der Historie übernommen.")
        for k, line in enumerate(_wrap(note, f.small, pb.w - 40)):
            draw_text(screen, line, f.small, (205, 205, 210), (pb.x + 20, y + 146 + k * 22), shadow=False)
        draw_text(screen, "Pfeile wählen/ändern (halten = schnell) · Tippen für Text · ENTER speichern · ESC zurück",
                  f.tiny, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 44), anchor="center", shadow=False)
        self.draw_status(screen, SCREEN_HEIGHT - 20)


# ------------------------------------------------------------------------------------------------ personal

class PersonalScreen(_RowScreen):

    accent = (60, 220, 140)

    def rows(self) -> list[str]:
        return list(PERSONAL) + ["back"]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN or self.move(event):
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.row == "back":
                self.game.open_career()
            else:
                self.say(self.career.buy_personal(self.row))
        elif event.key == pygame.K_ESCAPE:
            self.game.open_career()

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        self.header(screen, "PERSÖNLICHES TEAM", f"Konto {c.bank:.1f} Mio · investiere dein Gehalt in deine Karriere")
        box = pygame.Rect(60, 106, 760, 560)
        draw_panel(screen, box, PANEL, 215)
        for i, key in enumerate(self.rows()):
            selected = i == self.sel
            if key == "back":
                self.button(screen, pygame.Rect(box.x + 20, box.bottom - 60, box.w - 40, 40), "ZURÜCK", selected,
                            (110, 110, 125))
                mouse_item((box.x + 20, box.bottom - 60, box.w - 40, 40), self, i)
                continue
            r = pygame.Rect(box.x + 12, box.y + 14 + i * 150, box.w - 24, 136)
            mouse_item(r, self, i, key=None)
            if selected:
                self.highlight(screen, r)
            name, desc = PERSONAL[key]
            lvl = c.personal.get(key, 0)
            draw_text(screen, name.upper(), f.large, WHITE, (r.x + 22, r.y + 12))
            for k, line in enumerate(_wrap(desc, f.small, r.w - 260)):
                draw_text(screen, line, f.small, (205, 205, 210), (r.x + 22, r.y + 54 + k * 22), shadow=False)
            for k in range(len(PERSONAL_COST)):
                pygame.draw.rect(screen, self.accent if k < lvl else (50, 52, 60),
                                 (r.right - 220 + k * 66, r.y + 20, 58, 12), border_radius=4)
            draw_text(screen, f"Stufe {lvl}/{len(PERSONAL_COST)}", f.small_bold, WHITE, (r.right - 220, r.y + 42),
                      shadow=False)
            if lvl < len(PERSONAL_COST):
                cost = PERSONAL_COST[lvl]
                draw_text(screen, f"{cost:.1f} Mio", f.medium, GREEN if c.bank >= cost else RED,
                          (r.right - 22, r.y + 92), anchor="topright")
            else:
                draw_text(screen, "MAX", f.medium, GREY, (r.right - 22, r.y + 92), anchor="topright")
        rb = pygame.Rect(840, 106, 400, 560)
        draw_panel(screen, rb, PANEL, 215)
        x, y = rb.x + 18, rb.y + 18
        draw_text(screen, "KONTO", f.tiny, GREY, (x, y), shadow=False)
        draw_text(screen, f"{c.bank:.1f} Mio", f.big, GREEN, (x, y + 16))
        ct = c.contract
        lines = [("Gehalt", f"{ct.get('salary', 0):.1f} Mio / Saison"),
                 ("Vertrag", f"noch {max(0, ct.get('years', 0))} Saison(s)"),
                 ("Ruf", f"{c.reputation:.0f} / 100"), ("Vertrauen", f"{c.trust:.0f} / 100"),
                 ("Status", c.status if c.team else "-")]
        for k, (label, val) in enumerate(lines):
            draw_text(screen, label, f.small, GREY, (x, y + 90 + k * 30), shadow=False)
            draw_text(screen, val, f.small_bold, WHITE, (x + 130, y + 90 + k * 30), shadow=False)
        text = ("Dein Gehalt wird nach jedem Rennen anteilig ausgezahlt, dazu Punkteprämien und Boni für "
                "Wochenendziele. Investitionen wirken sofort und für den Rest der Karriere.")
        for k, line in enumerate(_wrap(text, f.small, rb.w - 36)):
            draw_text(screen, line, f.small, (205, 205, 210), (x, y + 260 + k * 22), shadow=False)
        self.draw_status(screen)


# ------------------------------------------------------------------------------------------------ statistics

class StatsScreen(_Screen):

    accent = CYAN

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.game.open_career()

    def _numbers(self) -> list[tuple[str, str]]:
        c = self.career
        log = c.race_log
        races = len(log)
        finished = [e for e in log if not e.get("dnf")]
        wins = sum(1 for e in finished if e["pos"] == 1)
        podiums = sum(1 for e in finished if e["pos"] <= 3)
        points = sum(e.get("pts", 0) for e in log)
        poles = sum(1 for e in log if e.get("q") == 1)
        best = min((e["pos"] for e in finished), default=None)
        avg = sum(e["pos"] for e in finished) / len(finished) if finished else None
        pct = (lambda n: f"{100 * n / races:.0f} %") if races else (lambda n: "-")
        rows = [("Rennen gesamt", str(races)), ("Siege", f"{wins}  ({pct(wins)})"), ("Podien", f"{podiums}  ({pct(podiums)})"),
                ("Punkte", f"{points}  (Ø {points / races:.1f})" if races else "0"),
                ("Ausfälle", str(races - len(finished))), ("Bestes Ergebnis", f"P{best}" if best else "-"),
                ("Ø Zielplatz", f"{avg:.1f}" if avg else "-")]
        if c.player_drives:
            rows.insert(3, ("Pole Positions", str(poles)))
        rows.append(("Titel", str(c.stats.get("titles", 0) if c.kind == "driver"
                                   else sum(1 for h in c.history if h.get("team_champion") == c.team))))
        return rows

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        who = c.player_name if c.player_drives else c.team
        self.header(screen, "STATISTIK", f"{who} · {len(c.race_log)} Rennen erfasst"
                    + ("" if c.player_drives else " · bestes Auto deines Teams"))
        card = pygame.Rect(60, 106, 330, 560)
        draw_panel(screen, card, PANEL, 215)
        body = tuple(c.teams[c.team]["color"]) if c.team else (150, 150, 158)
        draw_livery(screen, f, pygame.Rect(card.x + 14, card.y + 14, card.w - 28, 170), body,
                    tuple(c.helmet) if c.player_drives else (60, 60, 66),
                    c.player_number if c.player_drives else 0, c.short_code if c.player_drives else "", self.t)
        x, y = card.x + 18, card.y + 196
        draw_text(screen, _fit(who.upper(), f.medium, card.w - 36), f.medium, WHITE, (x, y))
        sub = f"{c.team or 'ohne Team'}" + (f" · {c.player_nationality}" if c.player_nationality else "")
        draw_text(screen, _fit(sub, f.small, card.w - 36), f.small, GREY, (x, y + 28), shadow=False)
        for k, (label, val) in enumerate(self._numbers()):
            yy = y + 64 + k * 30
            draw_text(screen, label, f.small, GREY, (x, yy), shadow=False)
            draw_text(screen, val, f.small_bold, WHITE, (card.right - 18, yy), anchor="topright", shadow=False)
        self._positions_chart(screen, pygame.Rect(410, 106, 830, 290))
        self._season_chart(screen, pygame.Rect(410, 406, 830, 260))
        draw_text(screen, "ENTER/ESC zurück", f.tiny, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 26), anchor="center",
                  shadow=False)

    def _positions_chart(self, screen: pygame.Surface, box: pygame.Rect) -> None:
        f, c = self.game.fonts, self.career
        draw_panel(screen, box, PANEL, 215)
        log = c.race_log[-24:]
        draw_text(screen, f"ZIELPOSITIONEN · LETZTE {len(log)} RENNEN", f.tiny, GREY, (box.x + 16, box.y + 12),
                  shadow=False)
        if not log:
            draw_text(screen, "Noch keine Rennen gefahren.", f.small, GREY, (box.x + 16, box.y + 44), shadow=False)
            return
        worst = max(10, max(e["pos"] for e in log))
        area = pygame.Rect(box.x + 46, box.y + 40, box.w - 66, box.h - 76)
        for p in (1, 3, 10, worst):
            yy = area.y + int((p - 1) / max(1, worst - 1) * area.h)
            pygame.draw.line(screen, (45, 47, 56), (area.x, yy), (area.right, yy), 1)
            draw_text(screen, f"P{p}", f.tiny, GREY, (area.x - 8, yy), anchor="midright", shadow=False)
        step = area.w / max(1, len(log))
        pts = []
        for k, e in enumerate(log):
            cx = area.x + int(step * (k + 0.5))
            yy = area.y + int((e["pos"] - 1) / max(1, worst - 1) * area.h)
            pts.append((cx, yy))
            if e.get("dnf"):
                col = RED
            elif e["pos"] <= 3:
                col = MEDAL[e["pos"] - 1]
            elif e["pos"] <= 10:
                col = GREEN
            else:
                col = (150, 150, 160)
            bw = max(4, int(step * 0.5))
            pygame.draw.rect(screen, (*[v // 3 for v in col],), (cx - bw // 2, yy, bw, area.bottom - yy),
                             border_radius=2)
            if k == 0 or e.get("s") != log[k - 1].get("s"):
                pygame.draw.line(screen, (80, 82, 96), (cx - int(step / 2), area.y - 6),
                                 (cx - int(step / 2), area.bottom), 1)
                draw_text(screen, f"S{e.get('s', '?')}", f.tiny, GREY, (cx - int(step / 2) + 4, area.bottom + 6),
                          shadow=False)
        if len(pts) > 1:
            pygame.draw.lines(screen, CYAN, False, pts, 2)
        for (cx, yy), e in zip(pts, log):
            col = RED if e.get("dnf") else MEDAL[e["pos"] - 1] if e["pos"] <= 3 else WHITE
            pygame.draw.circle(screen, col, (cx, yy), 5)

    def _season_chart(self, screen: pygame.Surface, box: pygame.Rect) -> None:
        f, c = self.game.fonts, self.career
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "PUNKTE UND PLATZIERUNG PRO SAISON", f.tiny, GREY, (box.x + 16, box.y + 12), shadow=False)
        seasons: list[tuple[int, int, int | None, bool]] = []
        for h in c.history[-12:]:
            if c.player_drives:
                pts, pos = h.get("points", 0), h.get("driver_pos")
            else:
                entry = next((e for e in h.get("team_table", []) if e["team"] == h.get("team")), {})
                pts, pos = entry.get("points", 0), h.get("team_pos")
            seasons.append((h["season"], pts, pos, False))
        if not c.season_log.get("closed"):
            if c.player_drives:
                pts = next((e["points"] for e in c.championship.driver_table() if e["player"]), 0)
                pos = c.player_driver_pos()
            else:
                pts = next((e["points"] for e in c.championship.team_table() if e["team"] == c.team), 0)
                pos = c.team_pos()
            seasons.append((c.season, pts, pos, True))
        if not seasons:
            return
        top = max(10, max(s[1] for s in seasons))
        area = pygame.Rect(box.x + 24, box.y + 44, box.w - 48, box.h - 96)
        bw = min(80, area.w // max(1, len(seasons)) - 16)
        for k, (season, pts, pos, live) in enumerate(seasons):
            cx = area.x + int(area.w * (k + 0.5) / len(seasons))
            h = int(area.h * pts / top)
            col = GOLD if pos == 1 else CYAN
            rect = pygame.Rect(cx - bw // 2, area.bottom - h, bw, h)
            pygame.draw.rect(screen, tuple(v // 2 for v in col) if live else col, rect, border_radius=4)
            if live:
                pygame.draw.rect(screen, col, rect, 2, border_radius=4)
            draw_text(screen, str(pts), f.small_bold, WHITE, (cx, rect.y - 12), anchor="center", shadow=False)
            draw_text(screen, f"Saison {season}" + (" (läuft)" if live else ""), f.tiny, GREY, (cx, area.bottom + 14),
                      anchor="center", shadow=False)
            draw_text(screen, f"P{pos}" if pos else "-", f.small_bold, GOLD if pos == 1 else WHITE,
                      (cx, area.bottom + 32), anchor="center", shadow=False)


# ------------------------------------------------------------------------------------------------ achievements

class AchievementsScreen(_Screen):

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.game.open_career()

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        keys = available(c.kind)
        got = [k for k in keys if k in c.achievements]
        self.header(screen, "ERFOLGE", f"{len(got)} von {len(keys)} freigeschaltet")
        cols = 3
        rows = (len(keys) + cols - 1) // cols
        cw = (SCREEN_WIDTH - 120 - (cols - 1) * 14) // cols
        ch = min(104, (560 - (rows - 1) * 10) // rows)
        for i, key in enumerate(sorted(keys, key=lambda k: (k not in c.achievements, keys.index(k)))):
            r = pygame.Rect(60 + (i % cols) * (cw + 14), 106 + (i // cols) * (ch + 10), cw, ch)
            unlocked = key in c.achievements
            draw_panel(screen, r, PANEL_LIGHT if unlocked else PANEL, 225)
            _, title, desc = ACHIEVEMENTS[key]
            mx, my = r.x + 34, r.centery
            if unlocked:
                pulse = 0.85 + 0.15 * abs(((self.t * 0.6 + i * 0.13) % 2) - 1)
                pygame.draw.circle(screen, tuple(int(v * pulse) for v in GOLD), (mx, my), 20)
                pygame.draw.circle(screen, (120, 80, 0), (mx, my), 20, 3)
                star = [(mx + (11 if k % 2 == 0 else 5) * math.sin(k * math.pi / 5),
                         my - (11 if k % 2 == 0 else 5) * math.cos(k * math.pi / 5)) for k in range(10)]
                pygame.draw.polygon(screen, (110, 70, 0), star)
            else:
                pygame.draw.circle(screen, (50, 52, 60), (mx, my), 20)
                draw_text(screen, "?", f.medium, (110, 112, 124), (mx, my), anchor="center", shadow=False)
            draw_text(screen, _fit(title, f.medium, cw - 90), f.medium, WHITE if unlocked else (130, 132, 142),
                      (r.x + 66, r.y + ch // 2 - 26))
            draw_text(screen, _fit(desc, f.tiny, cw - 84), f.tiny, (200, 200, 205) if unlocked else GREY,
                      (r.x + 66, r.y + ch // 2 + 2), shadow=False)
            if unlocked:
                draw_text(screen, f"Saison {c.achievements[key]}", f.tiny, GOLD, (r.x + 66, r.y + ch // 2 + 20),
                          shadow=False)
        draw_text(screen, "ENTER/ESC zurück", f.tiny, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 26), anchor="center",
                  shadow=False)


# ------------------------------------------------------------------------------------------------ options

class CareerOptionsScreen(_RowScreen):

    accent = (200, 200, 210)

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        c = self.career
        self.diffs = list(DIFFICULTY_LEVELS.keys())
        self.laps = c.laps
        self.diff = self.diffs.index(c.difficulty) if c.difficulty in self.diffs else 1
        self.fmt = next((k for k, (key, _) in enumerate(FORMATS) if key == c.format), 0)

    def rows(self) -> list[str]:
        return ["Rennrunden", "KI-Stärke", "Format", "SPEICHERN", "ZURÜCK"]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN or self.move(event):
            return
        row = self.row
        if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            d = -1 if event.key == pygame.K_LEFT else 1
            if row == "Rennrunden":
                self.laps = max(1, min(30, self.laps + d))
            elif row == "KI-Stärke":
                self.diff = (self.diff + d) % len(self.diffs)
            elif row == "Format":
                self.fmt = (self.fmt + d) % len(FORMATS)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if row == "SPEICHERN":
                self.career.set_options(self.laps, self.diffs[self.diff], FORMATS[self.fmt][0])
                self.say("Gespeichert - gilt ab dem nächsten Rennen")
            elif row == "ZURÜCK":
                self.game.open_career()
        elif event.key == pygame.K_ESCAPE:
            self.game.open_career()

    def _value(self, row: str) -> str:
        return {"Rennrunden": f"{self.laps} Runde{'n' if self.laps != 1 else ''} pro Rennen",
                "KI-Stärke": self.diffs[self.diff], "Format": FORMATS[self.fmt][1]}.get(row, "")

    def draw(self, screen: pygame.Surface) -> None:
        f, c = self.game.fonts, self.career
        self.header(screen, "KARRIERE-OPTIONEN", f"Slot {c.slot[-1]} · Einstellungen für die restlichen Rennen")
        box = pygame.Rect(60, 106, 640, 320)
        draw_panel(screen, box, PANEL, 215)
        for i, row in enumerate(self.rows()):
            y = box.y + 16 + i * 56
            selected = i == self.sel
            if row in ("SPEICHERN", "ZURÜCK"):
                self.button(screen, pygame.Rect(box.x + 20, y + 4, box.w - 40, 40), row, selected,
                            GOLD if row == "SPEICHERN" else (110, 110, 125))
                mouse_item((box.x + 20, y + 4, box.w - 40, 40), self, i)
                continue
            r = pygame.Rect(box.x + 12, y, box.w - 24, 46)
            mouse_item(r, self, i, key=None, arrows=True)
            if selected:
                self.highlight(screen, r)
                draw_text(screen, "<  >", f.medium, YELLOW, (r.right - 14, r.centery), anchor="midright")
            draw_text(screen, row.upper(), f.tiny, GREY, (r.x + 16, r.centery), anchor="midleft", shadow=False)
            draw_text(screen, self._value(row), f.small_bold, WHITE, (r.x + 170, r.centery), anchor="midleft",
                      shadow=False)
        hb = pygame.Rect(720, 106, 520, 320)
        draw_panel(screen, hb, PANEL, 215)
        text = ("Mehr Runden machen Reifen und Boxenstopps wichtiger, weniger Runden machen die Karriere schneller. "
                "Die KI-Stärke bestimmt das Tempo der Gegner. Das Format legt fest, ob es vor dem Rennen "
                "Training und Qualifying gibt. Fortschritt, Verträge und Erfolge bleiben erhalten.")
        for k, line in enumerate(_wrap(text, f.small, hb.w - 36)):
            draw_text(screen, line, f.small, (205, 205, 210), (hb.x + 18, hb.y + 18 + k * 24), shadow=False)
        changed = (self.laps, self.diffs[self.diff], FORMATS[self.fmt][0]) != (c.laps, c.difficulty, c.format)
        if changed:
            draw_text(screen, "Ungespeicherte Änderungen", f.small_bold, YELLOW, (hb.x + 18, hb.bottom - 34),
                      shadow=False)
        draw_form(screen, f, 60, 450, c.form(8), "LETZTE RENNEN")
        self.draw_status(screen)
