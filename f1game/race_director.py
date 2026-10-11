# Copyright Olivenda (Oliver Petz) 2026
"""Race director for spectator races: the viewer runs race control - flags, safety car, penalties,
disqualifications. An assistant either decides on its own as usual, only suggests (the director accepts or
rejects), or stays out of it entirely."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .race_control import GIVE_BACK_TIME, YELLOW_TIME
from .stewards import DRIVE_PENALTY_NAME
from .settings import CYAN, GREY, ORANGE, PANEL, PANEL_LIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .utils import draw_panel, draw_text

if TYPE_CHECKING:
    from .car import Car
    from .sessions import RaceSession

ASSIST_MODES = [("auto", "Automatisch"), ("suggest", "Nur Vorschläge"), ("off", "Aus - du entscheidest alles")]
PENALTY_STEPS: list = [5.0, 10.0, 20.0, "DT", "SG"]     # time penalties, drive-through, 10 s stop & go
VSC_TIMES: list = [None, 15.0, 30.0, 45.0, 60.0, 90.0, 120.0, float("inf")]    # None: race control's own pick
SUGGESTION_TIME = 40.0          # a suggestion nobody answers lapses after this long (race time)
RED = (240, 60, 50)
GREEN = (60, 220, 90)

# (key, label) - the label of some rows depends on the race state, see _label
WARN_REASONS = ["Track Limits", "Gefährliches Fahren", "Blockieren", "Blaue Flaggen ignoriert",
                "Unsportliches Verhalten", "Kollision", "Zu langsam unter SC/VSC"]
SORT_MODES = [("infr", "Verstöße"), ("pos", "Position")]
# (label, rain from now on)
WEATHER_STEPS = [("Trocken", 0.0), ("Leichter Regen", 0.35), ("Starker Regen", 0.8)]
WEATHER_RAMP = 25.0         # s until the new rain has fully set in
LIVE_ONLY = ("sc", "vsc", "red", "green", "chequered")     # not while watching the replay

ROWS = [("assist", "Assistent"), ("car", "Fahrer"), ("warning", "Verwarnung"), ("penalty", "Zeitstrafe"),
        ("warn", "Schwarz-weiße Flagge"),
        ("pit", "An die Box rufen"), ("clear", "Offene Strafen aufheben"), ("dsq", "Disqualifizieren"),
        ("green", "Grüne Flagge"), ("yellow", "Gelbe Flagge"), ("sc", "Safety Car"), ("vsc", "Virtual Safety Car"),
        ("red", "Rote Flagge"), ("chequered", "Zielflagge nach dieser Runde"), ("sort", "Verstöße-Liste"),
        ("give", "Platz zurückgeben"), ("pitlane", "Boxengasse"),
        ("weather", "Wetter")]
PANEL_X, PANEL_W = SCREEN_WIDTH - 372, 356     # the panel's place on the right of the screen
VALUE_ROWS = ("assist", "car", "warning", "penalty", "yellow", "vsc", "sort", "weather")
DRIVER_ROWS = ("car", "warn", "pit", "clear", "dsq", "give")    # left/right picks the driver


def penalty_label(p) -> str:
    if isinstance(p, str):
        return DRIVE_PENALTY_NAME[p] + (" 10s" if p == "SG" else "")
    return f"{p:.0f}s"


def vsc_label(t) -> str:
    if t is None:
        return "Dauer: auto"
    if t == float("inf"):
        return "bis Grün"
    return f"{t:.0f}s"


class RaceDirector:

    def __init__(self, session: "RaceSession") -> None:
        self.s = session
        self.open = False
        self.sel = 0
        self.assist = "suggest"     # the director decides: race control only suggests (Y/N)
        self.target: "Car | None" = None
        self.penalty_i = 0
        self.vsc_i = 2
        self.reason_i = 0
        self.sort = "infr"          # the Verstöße list: most infringements first, or race order
        self.sector = 0
        self.weather_i = 0
        self.suggestions: list[dict] = []
        self._confirm_dsq: "Car | None" = None
        session.stewards.director = self
        session.rc.director = self

    # ------------------------------------------------------------------ the assistant's decisions
    def intercept_penalty(self, car: "Car", seconds, reason: str) -> bool:
        """The stewards want to hand out a penalty (seconds, or "DT"/"SG"): True = the director takes it over
        (held or dropped)."""
        if self.assist == "auto":
            return False
        if self.assist == "suggest":
            self._suggest({"kind": "penalty", "car": car, "seconds": seconds, "reason": reason,
                           "text": f"{penalty_label(seconds)} Strafe für {car.short} - {reason}"})
        return True

    def intercept_deploy(self, mode: str, reason: str) -> bool:
        """Race control wants to neutralise the race: True = the director takes it over."""
        if self.assist == "auto":
            return False
        if self.assist == "suggest":
            name = {"SC": "Safety Car", "RED": "Rote Flagge"}.get(mode, "Virtual Safety Car")
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
                self._give_penalty(car, sug["seconds"], sug["reason"])
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
        if key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            # QoL: step through the drivers from anywhere, the camera follows
            self._pick_driver(-1 if key == pygame.K_PAGEUP else 1)
            return True
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
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):     # (SPACE is the active pause)
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
        elif row == "warning":
            self.reason_i = (self.reason_i + d) % len(WARN_REASONS)
        elif row == "sort":
            keys = [k for k, _ in SORT_MODES]
            self.sort = keys[(keys.index(self.sort) + d) % len(keys)]
        elif row == "yellow":
            self.sector = (self.sector + d) % 3
        elif row == "weather":
            self.weather_i = (self.weather_i + d) % len(WEATHER_STEPS)
        elif row == "vsc":
            self.vsc_i = (self.vsc_i + d) % len(VSC_TIMES)
            rc = self.s.rc
            if rc.mode == "VSC":
                # the VSC is out: the new duration counts from now
                t = VSC_TIMES[self.vsc_i]
                rc.until = self.s.time + (t if t is not None else 30.0)
                self.s.message(f"VSC: {vsc_label(t)}", CYAN, 1.5)
        elif row in DRIVER_ROWS:
            self._pick_driver(d)

    def _pick_driver(self, d: int) -> None:
        """The driver the decisions are about - the camera follows."""
        order = self.s.standings()
        cur = order.index(self.target) if self.target in order else (order.index(self.s.focus)
                                                                     if self.s.focus in order else 0)
        self.target = order[(cur + d) % len(order)]
        self.s.focus_car(self.target)
        self._confirm_dsq = None

    # ------------------------------------------------------------------ actions
    def _execute(self, row: str) -> None:
        s, rc = self.s, self.s.rc
        car = self.target or s.focus
        replay = getattr(s, "replay", None)
        if row in LIVE_ONLY and replay is not None and replay.active:
            s.message("Im Replay nicht möglich - erst zurück zum Rennen (R)", ORANGE, 2.0)
            return
        if row == "assist":
            self._change(row, 1)
        elif row == "give":
            self._give_place_back(car)
        elif row == "pitlane":
            s.pit_lane_closed = not s.pit_lane_closed
            s.stewards.announce("Boxengasse GESCHLOSSEN" if s.pit_lane_closed else "Boxengasse wieder offen",
                                "investigation" if s.pit_lane_closed else "info", 6.0)
        elif row == "weather":
            self._set_weather(*WEATHER_STEPS[self.weather_i])
        elif row == "car":
            s.focus_car(car)
        elif row == "penalty":
            if car.dsq:
                return
            self._give_penalty(car, PENALTY_STEPS[self.penalty_i], "Entscheidung der Rennleitung")
        elif row == "warning":
            if car.dsq or car.dnf:
                return
            s.stewards.warn(car, WARN_REASONS[self.reason_i])
        elif row == "sort":
            self._change(row, 1)
        elif row == "warn":
            s.stewards.black_white(car, "Verwarnung der Rennleitung")
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
            if car.drive_penalty is not None:
                s.stewards.announce(f"Strafe aufgehoben: {car.short} ({DRIVE_PENALTY_NAME[car.drive_penalty]})",
                                    "info")
                car.drive_penalty = None
            s.stewards.log_incident(car, "info", "Offene Strafen aufgehoben")
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
            if rc.mode == "RED":
                rc.restart_red()            # (the restart procedure runs on its own from there)
            elif rc.active:
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
            leader = rc._leader()
            if rc.mode == "RED":
                rc.restart_red()
            elif rc.active:
                s.message("Erst die laufende Neutralisation beenden (Grüne Flagge)", ORANGE, 2.0)
            elif s.race_started and s.winner_time is None and leader is not None and \
                    s.total_laps - leader.laps_done >= 2:
                rc.deploy("RED", "Entscheidung der Rennleitung")
        elif row == "chequered":
            leader = rc._leader()
            if leader is not None and s.race_started and s.winner_time is None:
                s.total_laps = min(s.total_laps, leader.laps_done + 1)
                s.stewards.announce(f"Rennen endet nach Runde {s.total_laps}", "info", 8.0)
                s.add_feed("Rennleitung: Zielflagge am Ende dieser Runde")

    def _give_place_back(self, car: "Car") -> None:
        """The driver has to let the car behind through (the AI lifts until it is by, a penalty otherwise)."""
        s, rc = self.s, self.s.rc
        order = [c for c in s.standings() if not c.dnf and not c.session_done]
        if car not in order or order.index(car) + 1 >= len(order):
            s.message(f"Hinter {car.short} ist niemand", ORANGE, 2.0)
            return
        victim = order[order.index(car) + 1]
        rc.give_back[(car, victim)] = s.time + GIVE_BACK_TIME
        s.stewards.log_incident(car, "warn", f"Platz an {victim.short} zurückgeben")
        s.stewards.announce(f"Rennleitung: {car.short} muss {victim.short} vorbeilassen ({GIVE_BACK_TIME:.0f} s)",
                            "investigation")

    def _set_weather(self, label: str, rain: float) -> None:
        """From now on this rain (the track gets wet or dries on its own, as with the forecast)."""
        s = self.s
        w = s.weather
        t = w.time
        w.points = [p for p in w.points if p[0] < t] + [(t, w.rain), (t + WEATHER_RAMP, rain),
                                                        (t + 1e6, rain)]
        s.stewards.announce(f"Wetter: {label}", "info", 6.0)

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
        rc.deploy(mode, "Entscheidung der Rennleitung", VSC_TIMES[self.vsc_i] if mode == "VSC" else None)

    def _give_penalty(self, car: "Car", what, reason: str) -> None:
        if isinstance(what, str):
            self.s.stewards.drive_penalty(car, what, reason, auto=False)
        else:
            self.s.stewards.penalty(car, what, reason, auto=False)

    def _disqualify(self, car: "Car") -> None:
        self.s.disqualify(car, "von der Rennleitung disqualifiziert")

    # ------------------------------------------------------------------ drawing
    def _label(self, key: str, base: str) -> str:
        rc = self.s.rc
        if key == "sc":
            return "Safety Car reinholen" if rc.mode == "SC" else "Safety Car rausschicken"
        if key == "vsc":
            return "VSC beenden" if rc.mode == "VSC" else "Virtual Safety Car"
        if key == "red":
            if rc.mode == "RED":
                return {"frozen": "Neustart: alle an die Box, dann Grid", "pit_in": "Rote Flagge: Feld fährt an die Box",
                        "grid": "Rote Flagge: Startaufstellung"}.get(rc.phase, "Rote Flagge")
            return "Rote Flagge (Rennen einfrieren)"
        if key == "green":
            return "Grüne Flagge (Neustart)" if rc.frozen else "Grüne Flagge (alles freigeben)"
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
            if car.drive_penalty is not None:
                pen += f" · {car.drive_penalty} offen"
            return f"P{pos} {car.short}{status}{pen}"
        if key == "penalty":
            return penalty_label(PENALTY_STEPS[self.penalty_i])
        if key == "warning":
            return f"{WARN_REASONS[self.reason_i]} · {car.warnings}x"
        if key == "sort":
            return dict(SORT_MODES)[self.sort]
        if key == "vsc":
            rc = self.s.rc
            if rc.mode == "VSC":
                return "bis Grün" if rc.until == float("inf") else f"noch {max(0.0, rc.until - self.s.time):.0f}s"
            return vsc_label(VSC_TIMES[self.vsc_i])
        if key == "yellow":
            return f"Sektor {self.sector + 1}"
        if key == "pitlane":
            return "geschlossen" if self.s.pit_lane_closed else "offen"
        if key == "weather":
            return f"{WEATHER_STEPS[self.weather_i][0]} · jetzt {self.s.weather.wetness * 100:.0f}% nass"
        if key == "give":
            order = [c for c in self.s.standings() if not c.dnf and not c.session_done]
            k = order.index(car) + 1 if car in order else len(order)
            return f"{car.short} -> {order[k].short}" if k < len(order) else "-"
        return ""

    def draw(self, screen: pygame.Surface) -> None:
        f = self.s.game.fonts
        x, w = PANEL_X, PANEL_W
        if not self.open:
            if self.suggestions:
                # bottom centre: the right side belongs to the Verstöße list
                h = 30 + 20 * min(3, len(self.suggestions))
                x, sy = (SCREEN_WIDTH - w) // 2, 520 - h
                draw_panel(screen, (x, sy, w, h), PANEL, 225)
                draw_text(screen, "RENNLEITUNG · Y annehmen · N ablehnen", f.tiny, CYAN, (x + 12, sy + 7),
                          shadow=False)
                for i, g in enumerate(self.suggestions[:3]):
                    draw_text(screen, g["text"], f.tiny, WHITE if i == 0 else GREY, (x + 12, sy + 27 + i * 20),
                              shadow=False)
            return
        row_h = 20
        h = 58 + len(ROWS) * row_h + (24 + 20 * min(3, len(self.suggestions)) if self.suggestions else 0)
        y = 192
        draw_panel(screen, (x, y, w, h), PANEL, 235)
        pygame.draw.rect(screen, RED, (x, y, w, 3), border_radius=2)
        draw_text(screen, "RENNLEITUNG", f.small_bold, WHITE, (x + 12, y + 8), shadow=False)
        draw_text(screen, "R Replay · X schließen", f.tiny, GREY, (x + w - 12, y + 12), anchor="topright",
                  shadow=False)
        draw_text(screen, "Pfeile wählen · ENTER ausführen · BILD auf/ab Fahrer", f.tiny, GREY, (x + 12, y + 32),
                  shadow=False)
        ry = y + 52
        for i, (key, base) in enumerate(ROWS):
            sel = i == self.sel
            if sel:
                pygame.draw.rect(screen, PANEL_LIGHT, (x + 6, ry, w - 12, row_h - 2), border_radius=4)
                pygame.draw.rect(screen, RED, (x + 6, ry, 4, row_h - 2), border_radius=2)
            col = self._row_color(key)
            label = self._label(key, base)
            if key == "dsq" and self._confirm_dsq is not None:
                label = "Wirklich? ENTER bestätigt"
            draw_text(screen, label, f.tiny, col, (x + 16, ry + 2), shadow=False)
            value = self._value(key)
            if value:
                arrows = key in VALUE_ROWS and sel
                draw_text(screen, f"< {value} >" if arrows else value, f.tiny, YELLOW if sel else (200, 200, 208),
                          (x + w - 14, ry + 2), anchor="topright", shadow=False)
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
        if key in ("warning", "give"):
            return YELLOW
        if key == "weather":
            return (120, 180, 255)
        if key == "pitlane":
            return ORANGE if self.s.pit_lane_closed else WHITE
        if key in ("yellow", "sc", "vsc"):
            return YELLOW if not (key == "sc" and rc.mode == "SC" or key == "vsc" and rc.mode == "VSC") else ORANGE
        return WHITE
