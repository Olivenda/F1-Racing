# Copyright Olivenda (Oliver Petz) 2026
"""Online lobby: host a game on a forwarded port or join one by address."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .net import DEFAULT_PORT, NetPlay, local_addresses
from .screens import _Background, _wrap
from .settings import CYAN, GREEN, GREY, PANEL, PANEL_LIGHT, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .utils import draw_panel, draw_text

if TYPE_CHECKING:
    from .game import Game

ACCENT = (40, 190, 120)


class NetLobbyScreen:

    def __init__(self, game: "Game") -> None:
        self.game = game
        self.bg = _Background()
        self.t = 0.0
        st = game.settings
        self.role = "host"
        self.address = st.net_address
        self.port = str(st.net_port or DEFAULT_PORT)
        self.sel = 0
        self.ips = local_addresses()

    @property
    def rows(self) -> list[str]:
        if self.role == "host":
            return ["Rolle", "Port", "HOST STARTEN", "ZURÜCK"]
        return ["Rolle", "Adresse", "Port", "VERBINDEN", "ZURÜCK"]

    @property
    def busy(self) -> bool:
        net = self.game.net
        return net is not None and net.status in ("listening", "connecting", "handshake")

    def _port(self) -> int | None:
        try:
            p = int(self.port)
        except ValueError:
            return None
        return p if 1024 <= p <= 65535 else None

    def _start(self) -> None:
        port = self._port()
        if port is None:
            self.game.toast_text("Port muss zwischen 1024 und 65535 liegen")
            return
        if self.role == "client" and not self.address.strip():
            self.game.toast_text("Adresse des Hosts eingeben")
            return
        st = self.game.settings
        st.net_port, st.net_address = port, self.address.strip()
        st.save()
        if self.game.net is not None:
            self.game.net.close()
        self.game.net = NetPlay(self.game, self.role, port, self.address.strip())

    def _cancel(self) -> None:
        if self.game.net is not None:
            self.game.net.close()
            self.game.net = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        rows = self.rows
        row = rows[min(self.sel, len(rows) - 1)]
        if event.key == pygame.K_ESCAPE:
            if self.busy:
                self._cancel()
            else:
                self._cancel()
                self.game.go_to_menu()
            return
        if self.busy:
            return
        if event.key == pygame.K_UP:
            self.sel = (self.sel - 1) % len(rows)
        elif event.key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % len(rows)
        elif row == "Rolle" and event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.role = "client" if self.role == "host" else "host"
            self.sel = 0
        elif row in ("Adresse", "Port") and event.key == pygame.K_BACKSPACE:
            if row == "Adresse":
                self.address = self.address[:-1]
            else:
                self.port = self.port[:-1]
        elif row in ("Adresse", "Port") and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
            self.sel = rows.index("VERBINDEN" if self.role == "client" else "HOST STARTEN")
        elif row == "Adresse" and event.unicode and event.unicode.isprintable() and len(self.address) < 60:
            if event.unicode not in " /\\":
                self.address += event.unicode
        elif row == "Port" and event.unicode and event.unicode.isdigit() and len(self.port) < 5:
            self.port += event.unicode
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            if row == "ZURÜCK":
                self._cancel()
                self.game.go_to_menu()
            elif row in ("HOST STARTEN", "VERBINDEN"):
                self._start()

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)
        net = self.game.net
        if net is not None and net.connected:
            if net.role == "host":
                self.game.open_setup(spectator=False)
            else:
                self.game.state = NetWaitScreen(self.game)

    def _value(self, row: str) -> str:
        cursor = "_" if int(self.t * 2) % 2 and self.rows[min(self.sel, len(self.rows) - 1)] == row else ""
        if row == "Rolle":
            return "Host (Spiel eröffnen)" if self.role == "host" else "Beitreten"
        if row == "Adresse":
            return (self.address or "") + cursor
        if row == "Port":
            return self.port + cursor
        return ""

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, ACCENT, (60, 40, 8, 60))
        draw_text(screen, "ONLINE-MEHRSPIELER", f.big, WHITE, (84, 36))
        draw_text(screen, "Zwei Fahrer über das Internet gegen das KI-Feld", f.small, GREY, (86, 86))
        rows = self.rows
        px, py, pw, rh = 60, 130, 600, 52
        draw_panel(screen, (px, py, pw, 20 + rh * len(rows)), PANEL, 215)
        for i, row in enumerate(rows):
            ry = py + 10 + i * rh
            selected = i == self.sel and not self.busy
            if row in ("HOST STARTEN", "VERBINDEN", "ZURÜCK"):
                col = (ACCENT if row != "ZURÜCK" else (120, 120, 130)) if selected else (50, 50, 58)
                pygame.draw.rect(screen, col, (px + 20, ry + 4, pw - 40, rh - 8), border_radius=8)
                draw_text(screen, row, f.medium, WHITE, (px + pw // 2, ry + rh // 2), anchor="center")
                continue
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 12, ry, pw - 24, rh - 4), border_radius=6)
                pygame.draw.rect(screen, ACCENT, (px + 12, ry, 5, rh - 4), border_radius=2)
            mid = ry + (rh - 4) // 2
            draw_text(screen, row.upper(), f.tiny, GREY, (px + 28, mid), anchor="midleft", shadow=False)
            draw_text(screen, self._value(row), f.medium, CYAN if row != "Rolle" else WHITE, (px + 200, mid),
                      anchor="midleft", shadow=False)
            if selected and row == "Rolle":
                draw_text(screen, "<  >", f.medium, YELLOW, (px + pw - 24, mid), anchor="midright")

        sy = py + 40 + rh * len(rows)
        net = self.game.net
        if net is not None:
            if net.status == "listening":
                dots = "." * (1 + int(self.t * 2) % 3)
                draw_text(screen, f"Warte auf Mitspieler an Port {net.port}{dots}", f.medium, YELLOW, (px, sy))
                draw_text(screen, "ESC bricht ab", f.small, GREY, (px, sy + 32))
            elif net.status in ("connecting", "handshake"):
                draw_text(screen, f"Verbinde mit {net.address}:{net.port} ...", f.medium, YELLOW, (px, sy))
            elif net.error:
                for k, line in enumerate(_wrap(net.error, f.small_bold, pw)):
                    draw_text(screen, line, f.small_bold, (255, 110, 100), (px, sy + k * 24))

        hb = pygame.Rect(700, 130, 540, 540)
        draw_panel(screen, hb, PANEL, 215)
        y = hb.y + 16
        if self.role == "host":
            port = self._port() or DEFAULT_PORT
            draw_text(screen, "SO GEHT'S (HOST)", f.medium, WHITE, (hb.x + 18, y))
            y += 40
            steps = [
                f"1. Im Router eine Portweiterleitung (Port-Forwarding) anlegen: TCP-Port {port} an diesen PC.",
                f"2. Die Windows-Firewall fragt beim ersten Start - Zugriff erlauben (oder TCP {port} freigeben).",
                "3. Deinem Mitspieler deine öffentliche IP geben (z.B. auf whatismyip.com nachsehen). Im selben "
                "Netzwerk reicht die lokale IP unten.",
                "4. HOST STARTEN, dann Strecke und Modus wählen. Mitspieler können jederzeit beitreten (bis zu 21 Fahrer), "
                "jeder wählt sein eigenes Team.",
            ]
        else:
            draw_text(screen, "SO GEHT'S (BEITRETEN)", f.medium, WHITE, (hb.x + 18, y))
            y += 40
            steps = [
                "1. Adresse des Hosts eingeben: seine öffentliche IP (oder lokale IP im selben Netzwerk).",
                "2. Port wie beim Host einstellen.",
                "3. VERBINDEN - der Host wählt Strecke und Modus, du wählst dein Team (bis zu 21 Fahrer).",
                "Dein Setup aus der Garage, deine Fahrhilfen, dein Getriebe und dein Lenkrad werden verwendet.",
            ]
        for step in steps:
            for line in _wrap(step, f.small, hb.w - 36):
                draw_text(screen, line, f.small, (210, 210, 215), (hb.x + 18, y), shadow=False)
                y += 23
            y += 8
        y += 6
        draw_text(screen, "LOKALE IP-ADRESSEN DIESES PCS", f.tiny, GREY, (hb.x + 18, y), shadow=False)
        y += 22
        for ip in self.ips[:4] or ["-"]:
            draw_text(screen, ip, f.medium, GREEN, (hb.x + 18, y), shadow=False)
            y += 28
        draw_text(screen, "Hinweis: Ports gehen nur bis 65535 - Standard ist "
                  f"{DEFAULT_PORT}.", f.tiny, GREY, (hb.x + 18, hb.bottom - 30), shadow=False)
        draw_text(screen, "Pfeile wählen · Tippen zum Eingeben · ENTER bestätigen · ESC zurück", f.small, GREY,
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30), anchor="center")


class NetWaitScreen:
    """Guest in the lobby / between sessions: pick a team, see who is connected and what the host chose."""

    def __init__(self, game: "Game") -> None:
        self.game = game
        self.bg = _Background()
        self.t = 0.0

    def _teams(self) -> list[str]:
        return [t.name for t in self.game.teams]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        net = self.game.net
        if event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()
        elif event.key == pygame.K_g:
            self._garage()
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d) and net is not None:
            teams = self._teams()
            if teams:
                k = teams.index(net.team) if net.team in teams else -1
                step = -1 if event.key in (pygame.K_LEFT, pygame.K_a) else 1
                net.choose_team(teams[(k + step) % len(teams)])

    def _garage(self) -> None:
        from .track import TRACK_DEFS
        game = self.game
        net = game.net
        key = net.lobby.get("track") if net is not None else None
        if key not in game.tracks:
            key = game.config.track_key if game.config is not None else TRACK_DEFS[0].key
        team = next((t for t in game.teams if net is not None and t.name == net.team), None)
        game.open_garage(key, team, lambda: setattr(game, "state", NetWaitScreen(game)))

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        net = self.game.net
        if net is None:
            return
        pygame.draw.rect(screen, ACCENT, (60, 40, 8, 60))
        draw_text(screen, "ONLINE  ·  VERBUNDEN", f.big, WHITE, (84, 36))
        sub = f"Host: {net.remote_name}" + (f"  ·  Ping {net.ping_ms:.0f} ms" if net.ping_ms else "")
        draw_text(screen, sub, f.small, GREY, (86, 86))

        # team choice
        box = pygame.Rect(60, 130, 560, 200)
        draw_panel(screen, box, PANEL, 220)
        draw_text(screen, "DEIN TEAM", f.tiny, GREY, (box.x + 18, box.y + 16), shadow=False)
        team = next((t for t in self.game.teams if t.name == net.team), None)
        name = team.name if team is not None else "wie der Host"
        if team is not None:
            pygame.draw.rect(screen, team.color, (box.x + 18, box.y + 48, 10, 40), border_radius=3)
        draw_text(screen, name, f.large, WHITE, (box.x + 40, box.y + 50))
        draw_text(screen, "<  >", f.large, YELLOW, (box.right - 20, box.y + 50), anchor="topright")
        draw_text(screen, "Links/rechts wechselt das Team - es gilt ab dem nächsten Wochenende.", f.small,
                  (200, 200, 205), (box.x + 18, box.y + 104), shadow=False)
        dots = "." * (1 + int(self.t * 2) % 3)
        draw_text(screen, f"Warte, bis der Host die Session startet{dots}", f.medium, YELLOW,
                  (box.x + 18, box.y + 140))

        info = pygame.Rect(60, 346, 560, 150)
        draw_panel(screen, info, PANEL, 220)
        draw_text(screen, "VOM HOST GEWÄHLT", f.tiny, GREY, (info.x + 18, info.y + 14), shadow=False)
        text = net.lobby.get("text") or "Host wählt noch Strecke und Modus"
        draw_text(screen, text, f.medium, WHITE, (info.x + 18, info.y + 40))
        if net.lobby.get("note"):
            draw_text(screen, net.lobby["note"], f.small_bold, ORANGE_NOTE, (info.x + 18, info.y + 78))
        draw_text(screen, "G: Garage (Setup für diese Strecke)", f.small, GREY, (info.x + 18, info.y + 112))

        # everyone in the lobby
        players = net.lobby.get("players") or []
        pl = pygame.Rect(650, 130, 590, 540)
        draw_panel(screen, pl, PANEL, 220)
        draw_text(screen, f"FAHRER ONLINE  ·  {len(players)}/21", f.tiny, GREY, (pl.x + 18, pl.y + 14), shadow=False)
        colors = {t.name: t.color for t in self.game.teams}
        for k, (pname, tname) in enumerate(players[:21]):
            y = pl.y + 40 + k * 23
            pygame.draw.rect(screen, colors.get(tname, (150, 150, 150)), (pl.x + 18, y + 3, 6, 16))
            col = CYAN if pname == net.my_name else WHITE
            label = f"{pname}" + ("  (Host)" if k == 0 else "")
            draw_text(screen, label, f.small_bold, col, (pl.x + 32, y), shadow=False)
            draw_text(screen, tname, f.small, GREY, (pl.x + 330, y), shadow=False)
        draw_text(screen, "ESC: Verbindung trennen", f.small, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30),
                  anchor="center")


ORANGE_NOTE = (255, 170, 60)
