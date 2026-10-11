# Copyright Olivenda (Oliver Petz) 2026
"""Race director for spectator races: the viewer runs race control - flags, safety car, penalties,
disqualifications. An assistant either decides on its own as usual, only suggests (the director accepts or
rejects), or stays out of it entirely."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .race_control import YELLOW_TIME
from .settings import CYAN, GREY, ORANGE, PANEL, PANEL_LIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .utils import draw_panel, draw_text

if TYPE_CHECKING:
    from .car import Car
    from .sessions import RaceSession

ASSIST_MODES = [("auto", "Automatisch"), ("suggest", "Nur Vorschläge"), ("off", "Aus - du entscheidest alles")]
PENALTY_STEPS = [5.0, 10.0, 20.0]
SUGGESTION_TIME = 40.0          # a suggestion nobody answers lapses after this long (race time)
RED = (240, 60, 50)
GREEN = (60, 220, 90)

# (key, label) - the label of some rows depends on the race state, see _label
ROWS = [("assist", "Assistent"), ("car", "Fahrer"), ("penalty", "Zeitstrafe"), ("warn", "Schwarz-weiße Flagge"),
        ("pit", "An die Box rufen"), ("clear", "Offene Strafen aufheben"), ("dsq", "Disqualifizieren"),
        ("green", "Grüne Flagge"), ("yellow", "Gelbe Flagge"), ("sc", "Safety Car"), ("vsc", "Virtual Safety Car"),
        ("red", "Rote Flagge"), ("chequered", "Zielflagge nach dieser Runde")]
VALUE_ROWS = ("assist", "car", "penalty", "yellow")


class RaceDirector:

    def __init__(self, session: "RaceSession") -> None:
        self.s = session
        self.open = False
        self.sel = 0
        self.assist = "auto"
        self.target: "Car | None" = None
        self.penalty_i = 0
        self.sector = 0
        self.suggestions: list[dict] = []
        self._confirm_dsq: "Car | None" = None
        session.stewards.director = self
        session.rc.director = self

    # ------------------------------------------------------------------ the assistant's decisions
    def intercept_penalty(self, car: "Car", seconds: float, reason: str) -> bool:
        """The stewards want to hand out a penalty: True = the director takes it over (held or dropped)."""
        if self.assist == "auto":
            return False
        if self.assist == "suggest":
            self._suggest({"kind": "penalty", "car": car, "seconds": seconds, "reason": reason,
                           "text": f"{seconds:.0f}s Strafe für {car.short} - {reason}"})
        return True

    def intercept_deploy(self, mode: str, reason: str) -> bool:
        """Race control wants to neutralise the race: True = the director takes it over."""
        if self.assist == "auto":
            return False
        if self.assist == "suggest":
            name = "Safety Car" if mode == "SC" else "Virtual Safety Car"
            self._suggest({"kind": "deploy", "mode": mode, "reason": reason, "text": f"{name} - {reason}"})
        return True

    def _suggest(self, sug: dict) -> None:
        sug["until"] = self.s.time + SUGGESTION_TIME
        self.suggestions.append(sug)
        self.suggestions = self.suggestions[-6:]
        self.s.message(f"Rennleitung: {sug['text']}  (Y annehmen · N ablehnen)", CYAN, 4.0)

    def _answer(self, accept: bool) -> None:
        if not self.suggestions:
            return
        sug = self.suggestions.pop(0)
        s = self.s
        if not accept:
            s.stewards.announce(f"Keine weitere Maßnahme: {sug['text']}", "info", 5.0)
            return
        if sug["kind"] == "penalty":
            car = sug["car"]
            if not car.dsq:
                s.stewards.penalty(car, sug["seconds"], sug["reason"], auto=False)
        elif not s.rc.active and s.race_started and s.winner_time is None:
            s.rc.deploy(sug["mode"], sug["reason"])

    def update(self) -> None:
        now = self.s.time
        self.suggestions = [g for g in self.suggestions if g["until"] > now]
        if self.target is not None and self.target not in self.s.cars:
            self.target = None

    # ------------------------------------------------------------------ input
    def handle_key(self, key: int) -> bool:
        """True when the key was the director's."""
        if key == pygame.K_x:
            self.open = not self.open
            self._confirm_dsq = None
            if self.open:
                self.target = self.s.focus
            return True
        if key in (pygame.K_y, pygame.K_n) and self.suggestions:
            self._answer(key == pygame.K_y)
            return True
        if not self.open:
            return False
        row = ROWS[self.sel][0]
        if key == pygame.K_ESCAPE:
            self.open = False
        elif key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(ROWS)
            self._confirm_dsq = None
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(ROWS)
            self._confirm_dsq = None
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            self._change(row, -1 if key in (pygame.K_LEFT, pygame.K_a) else 1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._execute(row)
        else:
            return False        # camera, time-lapse etc. keep working with the panel open
        return True

    def _change(self, row: str, d: int) -> None:
        if row == "assist":
            keys = [k for k, _ in ASSIST_MODES]
            self.assist = keys[(keys.index(self.assist) + d) % len(keys)]
            label = dict(ASSIST_MODES)[self.assist]
            self.s.message(f"Assistent der Rennleitung: {label}", CYAN, 2.0)
        elif row == "penalty":
            self.penalty_i = (self.penalty_i + d) % len(PENALTY_STEPS)
        elif row == "yellow":
            self.sector = (self.sector + d) % 3
        elif row in ("car", "warn", "pit", "clear", "dsq"):
            # the driver the decisions are about - the camera follows
            order = self.s.standings()
            cur = order.index(self.target) if self.target in order else 0
            self.target = order[(cur + d) % len(order)]
            self.s.focus_car(self.target)
            self._confirm_dsq = None

    # ------------------------------------------------------------------ actions
    def _execute(self, row: str) -> None:
        s, rc = self.s, self.s.rc
        car = self.target or s.focus
        if row == "assist":
            self._change(row, 1)
        elif row == "car":
            s.focus_car(car)
        elif row == "penalty":
            if car.dsq:
                return
            secs = PENALTY_STEPS[self.penalty_i]
            s.stewards.penalty(car, secs, "Entscheidung der Rennleitung", auto=False)
        elif row == "warn":
            car.bw_until = s.time + 10.0
            s.stewards.announce(f"Schwarz-weiße Flagge: {car.short} (Verwarnung der Rennleitung)", "investigation")
        elif row == "pit":
            if car.dnf or car.session_done or car.in_pit:
                return
            car.pit_request = s.plan_pit(car) or (car.tyres.compound.key if car.tyres else "medium")
            s.add_feed(f"Rennleitung: {car.short} an die Box gerufen")
        elif row == "clear":
            if car.penalty_unserved > 0:
                car.penalty_total -= car.penalty_unserved
                s.stewards.announce(f"Strafe aufgehoben: {car.short} ({car.penalty_unserved:.0f}s)", "info")
                car.penalty_unserved = 0.0
        elif row == "dsq":
            if car.dsq:
                return
            if self._confirm_dsq is not car:
                self._confirm_dsq = car                 # ENTER a second time to really do it
                s.message(f"{car.short} disqualifizieren? Nochmal ENTER zum Bestätigen", ORANGE, 2.5)
                return
            self._confirm_dsq = None
            self._disqualify(car)
        elif row == "green":
            if rc.active:
                rc._end()
            rc.yellow.clear()
        elif row == "yellow":
            L = s.track.length
            rc.yellow[self.sector] = s.time + YELLOW_TIME * 2.0
            rc.yellow_at[self.sector] = (self.sector + 0.5) * L / 3
            s.stewards.announce(f"Gelbe Flagge in Sektor {self.sector + 1}", "investigation", 6.0)
        elif row == "sc":
            self._neutralise("SC")
        elif row == "vsc":
            self._neutralise("VSC")
        elif row == "red":
            if rc.mode == "RED":
                rc.deploy("SC", "Neustart nach der roten Flagge")
            elif s.race_started and s.winner_time is None:
                rc.deploy("RED", "Entscheidung der Rennleitung")
        elif row == "chequered":
            leader = rc._leader()
            if leader is not None and s.race_started and s.winner_time is None:
                s.total_laps = min(s.total_laps, leader.laps_done + 1)
                s.stewards.announce(f"Rennen endet nach Runde {s.total_laps}", "info", 8.0)
                s.add_feed("Rennleitung: Zielflagge am Ende dieser Runde")

    def _neutralise(self, mode: str) -> None:
        s, rc = self.s, self.s.rc
        if rc.mode == mode:
            if mode == "SC":
                if rc.phase == "out":
                    leader = rc._leader()
                    rc.sc_end_lap = leader.laps_done if leader is not None else 0   # "in this lap"
            else:
                rc._end()
            return
        if rc.active or not s.race_started or s.winner_time is not None or rc._leader() is None:
            s.message("Erst die laufende Neutralisation beenden (Grüne Flagge)", ORANGE, 2.0)
            return
        rc.deploy(mode, "Entscheidung der Rennleitung")

    def _disqualify(self, car: "Car") -> None:
        s = self.s
        car.dsq = car.dnf = True
        car.dsq_reason = "von der Rennleitung disqualifiziert"
        car.session_done = car.retired_ghost = car.frozen = True
        car.penalty_unserved = 0.0
        if car.pit_request is not None:
            car.pit_request = None
        s.stewards.announce(f"SCHWARZE FLAGGE: {car.short} disqualifiziert", "penalty", 10.0)
        s.add_feed(f"DISQUALIFIZIERT: {car.name}")
        if all(c.session_done for c in s.cars) and s.end_timer is None:
            s.end_timer = 3.0

    # ------------------------------------------------------------------ drawing
    def _label(self, key: str, base: str) -> str:
        rc = self.s.rc
        if key == "sc":
            return "Safety Car reinholen" if rc.mode == "SC" else "Safety Car rausschicken"
        if key == "vsc":
            return "VSC beenden" if rc.mode == "VSC" else "Virtual Safety Car"
        if key == "red":
            return "Neustart hinter dem Safety Car" if rc.mode == "RED" else "Rote Flagge (Rennen unterbrechen)"
        if key == "green":
            return "Grüne Flagge (alles freigeben)"
        return base

    def _value(self, key: str) -> str:
        car = self.target or self.s.focus
        if key == "assist":
            return dict(ASSIST_MODES)[self.assist]
        if key == "car":
            order = self.s.standings()
            pos = order.index(car) + 1 if car in order else 0
            status = " DSQ" if car.dsq else " DNF" if car.dnf else ""
            pen = f" · {car.penalty_unserved:.0f}s offen" if car.penalty_unserved > 0 else ""
            return f"P{pos} {car.short}{status}{pen}"
        if key == "penalty":
            return f"{PENALTY_STEPS[self.penalty_i]:.0f}s"
        if key == "yellow":
            return f"Sektor {self.sector + 1}"
        return ""

    def draw(self, screen: pygame.Surface) -> None:
        f = self.s.game.fonts
        x, w = SCREEN_WIDTH - 372, 356
        if not self.open:
            if self.suggestions:
                h = 30 + 20 * min(3, len(self.suggestions))
                draw_panel(screen, (x, 200, w, h), PANEL, 225)
                draw_text(screen, "RENNLEITUNG · Y annehmen · N ablehnen", f.tiny, CYAN, (x + 12, 207), shadow=False)
                for i, g in enumerate(self.suggestions[:3]):
                    draw_text(screen, g["text"], f.tiny, WHITE if i == 0 else GREY, (x + 12, 227 + i * 20),
                              shadow=False)
            return
        row_h = 26
        h = 64 + len(ROWS) * row_h + (24 + 20 * min(3, len(self.suggestions)) if self.suggestions else 0)
        y = 196
        draw_panel(screen, (x, y, w, h), PANEL, 235)
        pygame.draw.rect(screen, RED, (x, y, w, 3), border_radius=2)
        draw_text(screen, "RENNLEITUNG", f.small_bold, WHITE, (x + 12, y + 8), shadow=False)
        draw_text(screen, "X schließen", f.tiny, GREY, (x + w - 12, y + 12), anchor="topright", shadow=False)
        draw_text(screen, "Pfeile wählen · ENTER ausführen", f.tiny, GREY, (x + 12, y + 32), shadow=False)
        ry = y + 54
        for i, (key, base) in enumerate(ROWS):
            sel = i == self.sel
            if sel:
                pygame.draw.rect(screen, PANEL_LIGHT, (x + 6, ry, w - 12, row_h - 2), border_radius=4)
                pygame.draw.rect(screen, RED, (x + 6, ry, 4, row_h - 2), border_radius=2)
            col = self._row_color(key)
            label = self._label(key, base)
            if key == "dsq" and self._confirm_dsq is not None:
                label = "Wirklich? ENTER bestätigt"
            draw_text(screen, label, f.tiny, col, (x + 16, ry + 5), shadow=False)
            value = self._value(key)
            if value:
                arrows = key in VALUE_ROWS and sel
                draw_text(screen, f"< {value} >" if arrows else value, f.tiny, YELLOW if sel else (200, 200, 208),
                          (x + w - 14, ry + 5), anchor="topright", shadow=False)
            ry += row_h
        if self.suggestions:
            draw_text(screen, "VORSCHLÄGE · Y annehmen · N ablehnen", f.tiny, CYAN, (x + 12, ry + 4), shadow=False)
            for i, g in enumerate(self.suggestions[:3]):
                draw_text(screen, g["text"], f.tiny, WHITE if i == 0 else GREY, (x + 12, ry + 24 + i * 20),
                          shadow=False)

    def _row_color(self, key: str) -> tuple[int, int, int]:
        rc = self.s.rc
        if key == "red":
            return RED
        if key == "dsq":
            return (255, 120, 110)
        if key == "green":
            return GREEN
        if key in ("yellow", "sc", "vsc"):
            return YELLOW if not (key == "sc" and rc.mode == "SC" or key == "vsc" and rc.mode == "VSC") else ORANGE
        return WHITE
