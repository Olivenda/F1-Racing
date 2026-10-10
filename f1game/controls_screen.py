# Copyright Olivenda (Oliver Petz) 2026
"""Wheel & controller set-up: a hub with three pages.

wizard  step-by-step wheelbase calibration (centre, left/right end stops, rotation, throttle, brake, test)
binds   one table for every action: wheel/controller button and keyboard key side by side
tuning  device choice, steering feel, deadzones, vibration, single-axis recalibration
"""

from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING

import pygame

from .controls import ACTIONS, AXES, DEVICE_KINDS, KEY_ACTIONS, KEY_DRIVE, AxisBinding, DeviceProfile
from .screens import _Background, _wrap
from .settings import CYAN, GREEN, GREY, PANEL, PANEL_LIGHT, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .utils import draw_panel, draw_text, mouse_item

if TYPE_CHECKING:
    from .game import Game

RED = (255, 90, 90)
ACCENT = (200, 200, 210)

AXIS_PROMPTS = {
    "steer": "Lenkrad ganz nach RECHTS drehen (Stick nach rechts) und halten ...",
    "throttle": "Gaspedal VOLL durchtreten (Gas-Trigger ganz drücken) und halten ...",
    "brake": "Bremspedal VOLL durchtreten (Brems-Trigger ganz drücken) und halten ...",
}

HUB_ROWS = ["Wheelbase kalibrieren (Assistent)", "Tastenbelegung", "Feineinstellung", "ZURÜCK"]
HUB_HELP = {
    "Wheelbase kalibrieren (Assistent)": "Schritt für Schritt: Mitte, linker und rechter Anschlag, Drehbereich "
                                         "und Lenkwinkel, Gaspedal, Bremspedal - danach Probefahrt mit "
                                         "Live-Anzeige. Funktioniert auch für Gamepads.",
    "Tastenbelegung": "Alle Aktionen in einer Tabelle: Knopf am Lenkrad/Controller und Taste auf der Tastatur "
                      "nebeneinander. Links/rechts wählt die Spalte, ENTER belegt neu.",
    "Feineinstellung": "Gerät wählen, Lenkbereich, Totzonen, Linearität, Vibration und einzelne Achsen neu "
                       "kalibrieren oder von Hand wählen.",
    "ZURÜCK": "Alles wird automatisch in data/controls.json gespeichert (pro Gerät).",
}

TUNING_HELP = {
    "Gerät": "Angeschlossene Lenkräder und Controller. Links/rechts wechselt das aktive Gerät. Geräte "
             "können auch während des Spiels angesteckt werden.",
    "Controller-Eingabe": "Aus = nur Tastatur. Tastatur funktioniert immer zusätzlich.",
    "Gerätetyp": "Lenkrad: Lenkachse wird direkt ohne Glättung übernommen. Gamepad: Stick wird bei "
                 "hohem Tempo leicht entschärft.",
    "Lenkung kalibrieren": "ENTER, dann Lenkrad bzw. Stick ganz nach rechts drehen und kurz halten. "
                           "Die Mittelstellung wird beim Start der Kalibrierung gemessen - Lenkrad gerade "
                           "halten!",
    "Gaspedal kalibrieren": "ENTER mit losgelassenem Pedal, dann voll durchtreten und kurz halten. "
                            "Invertierte und kombinierte Pedalachsen werden automatisch erkannt.",
    "Bremspedal kalibrieren": "ENTER mit losgelassenem Pedal, dann voll durchtreten und kurz halten.",
    "Drehbereich": "Lenkwinkel von Anschlag zu Anschlag, wie im Lenkrad-Treiber eingestellt (G HUB, "
                   "Thrustmaster Control Panel, Fanatec, Moza Pit House). Meist 900°.",
    "Lenkbereich": "Anteil des Lenkwegs, der schon vollen Einschlag ergibt. Lenkrad mit 900°: 50% = "
                   "voller Einschlag bei 225° pro Seite. Kleiner = direktere Lenkung.",
    "Lenk-Totzone": "Ignorierter Bereich um die Mitte. Gamepad-Sticks ~6%, Lenkräder 0%.",
    "Lenk-Linearität": "1.0 = linear. Höher = feinfühliger um die Mitte, schneller am Anschlag.",
    "Pedal-Totzone": "Ignorierter Weg am Anfang und Ende der Pedale (gegen Rauschen).",
    "Vibration / Force-Feedback": "Stöße bei Einschlägen, Kies, Rutschen und durchdrehenden Rädern. "
                                  "Gamepads vibrieren; Lenkräder bekommen Rüttel-Impulse, soweit der "
                                  "Treiber SDL-Rumble unterstützt.",
    "Standard wiederherstellen": "Setzt Achsen, Tasten und Lenkgefühl dieses Geräts zurück.",
    "Force Feedback": "Echte Lenkkräfte über den Motor des Lenkrads: Rückstellkraft der Vorderreifen (schwerer mit "
                      "Tempo, leicht wenn die Front schiebt), das Lenkrad dreht beim Übersteuern ins Gegenlenken, "
                      "Schläge bei Kontakt, Rütteln auf Randsteinen und Kies, Zug bei kaputter Aufhängung. 0% = aus.",
    "Force Feedback umkehren": "Falls das Lenkrad in die falsche Richtung zieht (Kurve verstärkt statt zurückstellen): "
                               "umkehren. Moza-Wheelbases sind automatisch umgekehrt.",
    "Force Feedback testen": "ENTER: das Lenkrad zieht kurz nach rechts, dann nach links. Zieht es anders herum: "
                             "'Force Feedback umkehren' einschalten.",
    "Pedal-Achsen": "Gas und Bremse brauchen ZWEI getrennte Achsen, sonst kann man nicht gleichzeitig bremsen "
                    "und Gas geben. Zeigt dies 'kombiniert': im Lenkrad-Treiber (Logitech G HUB: 'Kombinierte "
                    "Pedale' aus, Thrustmaster/Fanatec: 'separate axes') umstellen und Gas + Bremse neu "
                    "kalibrieren. Eine separate Pedalbox (eigenes USB-Gerät) wird beim Kalibrieren erkannt.",
    "ZURÜCK": "Wird automatisch in data/controls.json gespeichert (pro Gerät).",
}

# wizard steps: (key, title, instruction)
WIZARD = [
    ("device", "1 · GERÄT", "Wähle mit links/rechts dein Lenkrad (oder Gamepad). Gerätetyp mit hoch/runter. "
                            "ENTER = weiter."),
    ("center", "2 · MITTELSTELLUNG", "Lenkrad GERADE halten und alle Pedale LOSLASSEN. Wird übernommen, sobald "
                                     "alles ruhig ist (oder ENTER)."),
    ("left", "3 · LINKER ANSCHLAG", "Lenkrad ganz nach LINKS bis zum Anschlag drehen und halten."),
    ("right", "4 · RECHTER ANSCHLAG", "Lenkrad ganz nach RECHTS bis zum Anschlag drehen und halten."),
    ("rotation", "5 · DREHBEREICH & LENKWINKEL", "Hoch/runter wählt die Zeile, links/rechts ändert. Drehbereich = "
                                                 "Einstellung im Lenkrad-Treiber. Volleinschlag = bei welchem "
                                                 "Lenkradwinkel die Vorderräder voll eingeschlagen sind."),
    ("throttle", "6 · GASPEDAL", "Gaspedal VOLL durchtreten und halten (Gamepad: Gas-Trigger)."),
    ("brake", "7 · BREMSPEDAL", "Bremspedal VOLL durchtreten und halten (Gamepad: Brems-Trigger)."),
    ("test", "8 · PROBEFAHRT", "Lenken, Gas geben, bremsen - alle Balken müssen passen. ENTER speichert, "
                               "RÜCKTASTE geht einen Schritt zurück."),
]
CAPTURE_STEPS = ("left", "right", "throttle", "brake")

# keybind table: (action, label); drive rows have no controller button (they are axes)
BIND_ROWS: list[tuple[str, str]] = [(a, name) for a, (name, _) in KEY_DRIVE.items()] + \
    [(a, ACTIONS[a][0]) for a in ("gear_up", "gear_down", "drs", "pit", "pit_up", "pit_down", "pit_left",
                                  "pit_right", "pit_ok", "reset", "camera", "view", "map", "pause", "menu", "continue")]
BIND_EXTRA = ["Controller-Tasten zurücksetzen", "Tastatur zurücksetzen", "ZURÜCK"]
FIXED_KEYS = {"menu": "ESC", "continue": "ENTER"}


class ControlsScreen:

    def __init__(self, game: "Game", page: str = "hub") -> None:
        self.game = game
        self.page = page
        self.sel = 0
        self.col = 0                 # binds page: 0 = controller column, 1 = keyboard column
        self.scroll = 0
        self.bg = _Background()
        self.t = 0.0
        # single-axis capture (tuning page) and button/key capture (binds page)
        self.capture_axis: str | None = None
        self.capture_button: str | None = None
        self.capture_key: str | None = None
        self.baseline: dict[tuple[str, int], float] = {}
        self.hold = 0.0
        self.peak = 0.0
        self.swallow_until = 0
        # wizard
        self.step = 0
        self.backup: DeviceProfile | None = None
        self.found: dict[str, tuple[tuple[str, int], float]] = {}
        self.rot_sel = 0
        self.ffb_test = 0.0          # seconds left of the right/left pull test
        self.armed = False           # capture steps listen only after everything went back to rest
        self.note = ""

    @property
    def c(self):
        return self.game.controls

    # ================================================================== shared helpers
    def _all_axes(self) -> list[tuple[str, int]]:
        return [(j.get_name(), k) for j in self.c.joys.values() for k in range(j.get_numaxes())]

    def _axis_value(self, name: str, axis: int) -> float:
        joy = next((j for j in self.c.joys.values() if j.get_name() == name), None)
        return joy.get_axis(axis) if joy is not None and axis < joy.get_numaxes() else 0.0

    def _snapshot(self) -> dict[tuple[str, int], float]:
        return {(n, k): self._axis_value(n, k) for n, k in self._all_axes()}

    def _moved(self, skip: set[tuple[str, int]] = frozenset()) -> tuple[tuple[str, int], float]:
        """Axis (on any device - pedal boxes are often their own USB device) that moved most since the baseline.
        Axes in `skip` are only chosen when nothing else moved (combined pedals)."""
        moved = sorted(((abs(self._axis_value(n, k) - v), (n, k)) for (n, k), v in self.baseline.items()),
                       reverse=True)
        if not moved:
            return ("", -1), 0.0
        for d, key in moved:
            if key not in skip and d > 0.3:
                return key, d
        return moved[0][1], moved[0][0]

    def _binding_key(self, b: AxisBinding) -> tuple[str, int]:
        joy = self.c.joystick
        return b.device or (joy.get_name() if joy else ""), b.axis

    def _combined(self) -> bool:
        p = self.c.profile
        return p is not None and p.throttle.axis >= 0 and \
            (p.throttle.axis, p.throttle.device) == (p.brake.axis, p.brake.device)

    def _hold_update(self, dt: float, delta: float) -> bool:
        """True once the wheel/pedal has been held still at its furthest point for a moment."""
        self.hold = self.hold + dt if delta > 0.6 and delta >= self.peak - 0.03 else 0.0
        self.peak = max(self.peak, delta)
        return self.hold > 0.8

    def _go(self, page: str) -> None:
        self.page, self.sel, self.col, self.scroll = page, 0, 0, 0

    def _leave(self) -> None:
        self.c.save()
        from .screens import SettingsScreen
        self.game.state = SettingsScreen(self.game)

    # ================================================================== input
    def handle_event(self, event: pygame.event.Event) -> None:
        joy_key = getattr(event, "from_joystick", False)
        if event.type == pygame.KEYDOWN and joy_key and pygame.time.get_ticks() < self.swallow_until:
            return
        if self.page == "wizard":
            self._wizard_event(event)
            return
        if self.capture_key is not None:
            if event.type == pygame.KEYDOWN and not joy_key:
                if event.key != pygame.K_ESCAPE:
                    self.c.bind_key(self.capture_key, event.key)
                self.capture_key = None
            return
        if self.capture_button is not None:
            self._button_capture(event)
            return
        if self.capture_axis is not None:
            if event.type == pygame.KEYDOWN and not joy_key:
                if event.key == pygame.K_ESCAPE:
                    self.capture_axis = None
                else:
                    self._finish_axis()
            return
        if event.type != pygame.KEYDOWN:
            return
        rows = self._rows()
        self.sel = min(self.sel, len(rows) - 1)
        key = event.key
        if key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(rows)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(rows)
        elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
            delta = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
            if self.page == "binds":
                self.col = 0 if delta < 0 else 1
            elif self.page == "tuning":
                self._tune(rows[self.sel], delta)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate(rows[self.sel])
        elif key in (pygame.K_DELETE, pygame.K_BACKSPACE) and self.page == "binds":
            self._clear_bind(rows[self.sel])
        elif key == pygame.K_ESCAPE:
            if self.page == "hub":
                self._leave()
            else:
                self._go("hub")

    @property
    def mouse_blocked(self) -> bool:
        """While waiting for a key/button/axis to bind, the mouse must not send keys."""
        return bool(self.capture_axis or self.capture_button or self.capture_key)

    def _rows(self) -> list[str]:
        if self.page == "hub":
            return HUB_ROWS
        if self.page == "binds":
            return [a for a, _ in BIND_ROWS] + BIND_EXTRA
        return self._tuning_rows()

    def _activate(self, row: str) -> None:
        if self.page == "hub":
            if row == "ZURÜCK":
                self._leave()
            elif row == "Tastenbelegung":
                self._go("binds")
            elif row == "Feineinstellung":
                self._go("tuning")
            else:
                self._start_wizard()
            return
        if row == "ZURÜCK":
            self._go("hub")
        elif self.page == "binds":
            self._activate_bind(row)
        else:
            self._activate_tuning(row)

    def _button_capture(self, event: pygame.event.Event) -> None:
        if event.type == pygame.JOYBUTTONDOWN and event.instance_id in self.c.joys:
            if event.instance_id != self.c.active:
                self.c.active = event.instance_id   # a button on another device: bind it on that device
            p = self.c.profile
            if p is not None:
                # a button can only do one thing in the car
                for a, b in list(p.buttons.items()):
                    if b == event.button:
                        p.buttons[a] = -1
                p.buttons[self.capture_button] = event.button
                self.c.save()
            self.capture_button = None
            self.swallow_until = pygame.time.get_ticks() + 300
        elif event.type == pygame.KEYDOWN and not getattr(event, "from_joystick", False):
            if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE) and self.c.profile is not None:
                self.c.profile.buttons[self.capture_button] = -1
                self.c.save()
            self.capture_button = None

    # ================================================================== binds page
    def _activate_bind(self, row: str) -> None:
        if row == "Controller-Tasten zurücksetzen":
            joy, p = self.c.joystick, self.c.profile
            if joy is not None and p is not None:
                p.buttons = DeviceProfile.for_device(joy.get_name(), joy.get_numaxes()).buttons
                self.c.save()
            return
        if row == "Tastatur zurücksetzen":
            self.c.reset_keys()
            return
        if self.col == 0:
            if row in KEY_DRIVE:
                # axes are set in the wizard
                self._start_wizard(step="left" if row in ("left", "right") else row)
            elif self.c.profile is not None:
                self.capture_button = row
        elif row not in FIXED_KEYS:
            self.capture_key = row

    def _clear_bind(self, row: str) -> None:
        if row in BIND_EXTRA:
            return
        if self.col == 0 and row in ACTIONS and self.c.profile is not None:
            self.c.profile.buttons[row] = -1
            self.c.save()
        elif self.col == 1 and row in self.c.keys:
            self.c.clear_key(row)

    def _bind_cells(self, action: str) -> tuple[str, str]:
        c, p = self.c, self.c.profile
        if action in KEY_DRIVE:
            if p is None:
                pad = "-"
            elif action in ("left", "right"):
                pad = "Lenkachse" if p.steer.axis >= 0 else "nicht belegt"
            else:
                b = getattr(p, action)
                pad = f"Achse {b.axis}" if b.axis >= 0 else "nicht belegt"
        else:
            b = p.buttons.get(action, -1) if p is not None else -1
            pad = "-" if p is None else ("nicht belegt" if b < 0 else f"Knopf {b}")
        if action in FIXED_KEYS:
            kb = FIXED_KEYS[action]
        else:
            keys = c.keys.get(action, [])
            kb = " / ".join(pygame.key.name(k).upper() for k in keys) if keys else "nicht belegt"
        return pad, kb

    # ================================================================== tuning page
    def _tuning_rows(self) -> list[str]:
        rows = ["Gerät", "Controller-Eingabe"]
        p = self.c.profile
        if p is not None:
            rows += ["Gerätetyp", "Lenkung kalibrieren", "Gaspedal kalibrieren", "Bremspedal kalibrieren",
                     "Pedal-Achsen"]
            if p.kind == "wheel":
                rows.append("Drehbereich")
            rows += ["Lenkbereich", "Lenk-Totzone", "Lenk-Linearität", "Pedal-Totzone"]
            if p.kind == "wheel":
                rows += ["Force Feedback", "Force Feedback umkehren", "Force Feedback testen"]
            rows += ["Vibration / Force-Feedback", "Standard wiederherstellen"]
        return rows + ["ZURÜCK"]

    def _tuning_value(self, row: str) -> str:
        c, p = self.c, self.c.profile
        if row == "Gerät":
            n = len(c.joys)
            return f"{c.device_name()}" + (f"  ({n} Geräte)" if n > 1 else "")
        if row == "Controller-Eingabe":
            return "An" if c.enabled else "Aus"
        if p is None:
            return ""
        if row == "Gerätetyp":
            return DEVICE_KINDS[p.kind]
        for key, label in (("steer", "Lenkung"), ("throttle", "Gaspedal"), ("brake", "Bremspedal")):
            if row.startswith(label):
                b: AxisBinding = getattr(p, key)
                where = f"{b.device[:14]}: " if b.device else ""
                return "nicht belegt" if b.axis < 0 else f"{where}Achse {b.axis}  ({b.rest:+.2f} -> {b.full:+.2f})"
        if row == "Pedal-Achsen":
            return "KOMBINIERT - siehe Hilfe!" if self._combined() else "getrennt (Gas + Bremse gleichzeitig möglich)"
        if row == "Drehbereich":
            return f"{p.rotation}°"
        if row == "Lenkbereich":
            lock = f"  (Volleinschlag bei {p.saturation * p.rotation:.0f}°)" if p.kind == "wheel" and p.rotation \
                else ""
            return f"{p.saturation * 100:.0f}%{lock}"
        if row == "Lenk-Totzone":
            return f"{p.deadzone * 100:.0f}%"
        if row == "Lenk-Linearität":
            return f"{p.linearity:.1f}"
        if row == "Pedal-Totzone":
            return f"{p.pedal_deadzone * 100:.0f}%"
        if row == "Vibration / Force-Feedback":
            return f"{p.rumble * 100:.0f}%"
        if row == "Force Feedback":
            return f"{p.ffb * 100:.0f}%  ({self._ffb_status()})"
        if row == "Force Feedback umkehren":
            return "An" if p.ffb_invert else "Aus"
        if row == "Force Feedback testen":
            return "... läuft ..." if self.ffb_test > 0 else "ENTER"
        return ""

    def _ffb_status(self) -> str:
        if self.c.ffb_device(0):
            return "aktiv"
        return "kein FFB-Motor erkannt - nur Vibration"

    def _tune(self, row: str, delta: int) -> None:
        c, p = self.c, self.c.profile
        if row == "Gerät":
            c.cycle_device()
        elif row == "Controller-Eingabe":
            c.enabled = not c.enabled
        elif p is None:
            return
        elif row == "Gerätetyp":
            p.kind = "gamepad" if p.kind == "wheel" else "wheel"
            if p.kind == "wheel" and not p.rotation:
                p.rotation = 900
        elif row == "Drehbereich":
            lock = p.saturation * p.rotation
            p.rotation = max(180, min(2520, p.rotation + 90 * delta))
            p.saturation = round(max(0.1, min(1.0, lock / p.rotation)), 3)
        elif row == "Lenkbereich":
            p.saturation = round(max(0.1, min(1.0, p.saturation + 0.05 * delta)), 2)
        elif row == "Lenk-Totzone":
            p.deadzone = round(max(0.0, min(0.3, p.deadzone + 0.01 * delta)), 2)
        elif row == "Lenk-Linearität":
            p.linearity = round(max(1.0, min(3.0, p.linearity + 0.1 * delta)), 1)
        elif row == "Pedal-Totzone":
            p.pedal_deadzone = round(max(0.0, min(0.2, p.pedal_deadzone + 0.01 * delta)), 2)
        elif row == "Vibration / Force-Feedback":
            p.rumble = round(max(0.0, min(1.0, p.rumble + 0.1 * delta)), 1)
            c.rumble(0.6, 0.6, 250)
        elif row == "Force Feedback":
            p.ffb = round(max(0.0, min(1.0, p.ffb + 0.1 * delta)), 1)
        elif row == "Force Feedback umkehren":
            p.ffb_invert = not p.ffb_invert
            p.ffb_checked = True
        elif row.endswith("kalibrieren"):
            self._pick_axis({"Lenkung": "steer", "Gaspedal": "throttle", "Bremspedal": "brake"}[row.split()[0]],
                            delta)
            return
        else:
            return
        c.save()

    def _pick_axis(self, which: str, delta: int) -> None:
        """Left/right on a calibration row: step through every axis of every device by hand."""
        p, joy = self.c.profile, self.c.joystick
        axes = self._all_axes()
        if p is None or joy is None or not axes:
            return
        current = self._binding_key(getattr(p, which))
        k = axes.index(current) if current in axes else -1
        name, axis = axes[(k + delta) % len(axes)]
        rest = self._axis_value(name, axis)
        full = 1.0 if which == "steer" else (-1.0 if rest > 0.5 else 1.0)
        setattr(p, which, AxisBinding(axis, round(rest, 3), full, "" if name == joy.get_name() else name))
        self.c.save()

    def _activate_tuning(self, row: str) -> None:
        c, joy = self.c, self.c.joystick
        if row == "Standard wiederherstellen" and joy is not None:
            c.profiles[joy.get_name()] = DeviceProfile.for_device(joy.get_name(), joy.get_numaxes())
            c.profiles[joy.get_name()].apply_brand_defaults(joy.get_name())
            c.save()
        elif row == "Force Feedback testen":
            self.ffb_test = 1.6
        elif row.endswith("kalibrieren") and joy is not None:
            self.capture_axis = {"Lenkung": "steer", "Gaspedal": "throttle", "Bremspedal": "brake"}[row.split()[0]]
            self.baseline = self._snapshot()
            self.hold = self.peak = 0.0
        else:
            self._tune(row, 1)

    def _finish_axis(self) -> None:
        joy, p = self.c.joystick, self.c.profile
        which, self.capture_axis = self.capture_axis, None
        if joy is None or p is None or which is None:
            return
        skip = {self._binding_key(p.throttle)} if which == "brake" and p.throttle.axis >= 0 else set()
        (name, axis), delta = self._moved(skip)
        if axis >= 0 and delta > 0.3:
            rest, now = self.baseline[(name, axis)], self._axis_value(name, axis)
            # steering is symmetric here: the end stop is the end of the axis, however far it was turned
            full = (1.0 if now > rest else -1.0) if which == "steer" else now
            device = "" if name == joy.get_name() else name
            setattr(p, which, AxisBinding(axis, round(rest, 3), round(full, 3), device))
            self.c.save()

    # ================================================================== wizard
    def _start_wizard(self, step: str = "device") -> None:
        p = self.c.profile
        if self.c.joystick is None or p is None:
            self.note = "Kein Lenkrad oder Controller gefunden."
            return
        self.backup = copy.deepcopy(p)
        self.page = "wizard"
        self.found = {}
        self.rot_sel = 0
        self._enter_step(next(k for k, (key, _, _) in enumerate(WIZARD) if key == step))
        if step != "device":
            # jumping straight to one axis: the current position is the rest position
            self.found["center"] = (("", -1), 0.0)

    @property
    def wkey(self) -> str:
        return WIZARD[self.step][0]

    def _enter_step(self, k: int) -> None:
        self.step = max(0, min(len(WIZARD) - 1, k))
        self.hold = self.peak = 0.0
        self.armed = False
        if self.wkey in ("center",):
            self.baseline = self._snapshot()
        elif self.wkey in CAPTURE_STEPS and self.wkey != "right":
            # pedals and the left end stop are measured against the centre snapshot
            if "center" not in self.found or not self.baseline:
                self.baseline = self._snapshot()

    def _wizard_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        joy_key = getattr(event, "from_joystick", False)
        key, w = event.key, self.wkey
        if key == pygame.K_ESCAPE:
            # cancel: everything goes back to how it was
            if self.backup is not None and self.c.joystick is not None:
                self.c.profiles[self.c.joystick.get_name()] = self.backup
            self._go("hub")
            return
        if key == pygame.K_BACKSPACE and not joy_key:
            self._enter_step(self.step - 1)
            return
        if key == pygame.K_TAB and not joy_key:
            self._enter_step(self.step + 1)     # skip (e.g. no clutch-less pedal set)
            return
        if w == "device":
            if key in (pygame.K_LEFT, pygame.K_RIGHT):
                self.c.cycle_device()
                self.backup = copy.deepcopy(self.c.profile)
            elif key in (pygame.K_UP, pygame.K_DOWN) and self.c.profile is not None:
                p = self.c.profile
                p.kind = "gamepad" if p.kind == "wheel" else "wheel"
                if p.kind == "wheel" and not p.rotation:
                    p.rotation = 900
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._enter_step(self.step + 1)
            return
        if w == "rotation":
            p = self.c.profile
            if p is None:
                return
            if key in (pygame.K_UP, pygame.K_DOWN):
                self.rot_sel = 1 - self.rot_sel
            elif key in (pygame.K_LEFT, pygame.K_RIGHT):
                d = -1 if key == pygame.K_LEFT else 1
                lock = p.saturation * max(1, p.rotation)
                if self.rot_sel == 0:
                    p.rotation = max(180, min(2520, (p.rotation or 900) + 90 * d))
                else:
                    lock = max(90.0, min(float(p.rotation), lock + 30 * d))
                p.saturation = round(max(0.1, min(1.0, lock / max(1, p.rotation))), 3)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._enter_step(self.step + 1)
            return
        if w == "test":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.c.save()
                self.backup = None
                self.note = "Kalibrierung gespeichert."
                self._go("hub")
            return
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            # accept the current position right away
            self._capture_now()

    def _wizard_update(self, dt: float) -> None:
        if self.c.joystick is None:
            self._go("hub")
            self.note = "Gerät getrennt - Kalibrierung abgebrochen."
            return
        w = self.wkey
        if w == "center":
            # still for a second: everything at rest
            now = self._snapshot()
            jitter = max((abs(now[k] - v) for k, v in self.baseline.items() if k in now), default=0.0)
            if jitter > 0.04:
                self.baseline = now
                self.hold = 0.0
            else:
                self.hold += dt
            if self.hold > 1.0:
                self._capture_now()
        elif w in CAPTURE_STEPS:
            if not self.armed:
                # wait until the previous pedal is released / the wheel is back near the centre
                rest = max((abs(self._axis_value(*k) - v) for k, v in self.baseline.items()), default=0.0)
                self.armed = rest < 0.25
                return
            _, delta = self._step_delta(w)
            if self._hold_update(dt, delta):
                self._capture_now()

    def _step_delta(self, w: str) -> tuple[tuple[str, int], float]:
        """Movement that counts for this step. The right end stop must be on the steering axis found on the left,
        in the other direction."""
        if w == "right" and "left" in self.found:
            key, left = self.found["left"]
            rest = self.baseline.get(key, 0.0)
            toward_left = 1.0 if left > rest else -1.0
            return key, max(0.0, -(self._axis_value(*key) - rest) * toward_left)
        return self._moved(self._skip_for(w))

    def _skip_for(self, w: str) -> set[tuple[str, int]]:
        skip: set[tuple[str, int]] = set()
        if w in ("throttle", "brake") and "steer" in self.found:
            skip.add(self.found["steer"][0])
        if w == "brake" and "throttle" in self.found:
            skip.add(self.found["throttle"][0])
        return skip

    def _capture_now(self) -> None:
        w, p, joy = self.wkey, self.c.profile, self.c.joystick
        if p is None or joy is None:
            return
        self.swallow_until = pygame.time.get_ticks() + 300
        if w == "center":
            self.found["center"] = (("", -1), 0.0)
            self._enter_step(self.step + 1)
            return
        key, delta = self._step_delta(w)
        if key[1] < 0 or delta < 0.3:
            self.note = "Keine Bewegung erkannt - bitte weiter drehen/drücken."
            return
        self.note = ""
        name, axis = key
        rest, now = self.baseline[key], self._axis_value(name, axis)
        device = "" if name == joy.get_name() else name
        if w == "left":
            self.found["left"] = (key, now)
        elif w == "right":
            left = self.found.get("left", (key, rest - (now - rest)))[1]
            p.steer = AxisBinding(axis, round(rest, 3), round(now, 3), device, round(left, 3))
            self.found["steer"] = (key, now)
        else:
            setattr(p, w, AxisBinding(axis, round(rest, 3), round(now, 3), device))
            self.found[w] = (key, now)
            if w == "brake" and "throttle" in self.found and self.found["throttle"][0] == key:
                self.note = "Gas und Bremse liegen auf DERSELBEN Achse (kombinierte Pedale) - im Lenkrad-Treiber " \
                            "auf getrennte Achsen umstellen!"
        self._enter_step(self.step + 1)

    # ================================================================== loop
    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)
        if self.ffb_test > 0:
            self.ffb_test = max(0.0, self.ffb_test - dt)
            torque = 0.0 if self.ffb_test <= 0 else (0.5 if self.ffb_test > 0.8 else -0.5)
            self.c.force(torque, 0.1, 0.1, 0.0, 60)
        elif self.page == "wizard" and self.wkey == "test":
            # test drive: a light centring force so the wheel feels alive
            self.c.force(0.0, 0.4, 0.15, 0.0, 60)
        if self.page == "wizard":
            self._wizard_update(dt)
        elif self.capture_axis is not None:
            if self.c.joystick is None:
                self.capture_axis = None
                return
            skip = set()
            p = self.c.profile
            if self.capture_axis == "brake" and p is not None and p.throttle.axis >= 0:
                skip = {self._binding_key(p.throttle)}
            _, delta = self._moved(skip)
            if self._hold_update(dt, delta):
                self._finish_axis()
                self.swallow_until = pygame.time.get_ticks() + 250

    # ================================================================== drawing
    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, ACCENT, (60, 40, 8, 60))
        title = {"hub": "LENKRAD & CONTROLLER", "wizard": "WHEELBASE-KALIBRIERUNG", "binds": "TASTENBELEGUNG",
                 "tuning": "FEINEINSTELLUNG"}[self.page]
        draw_text(screen, title, f.big, WHITE, (84, 36))
        sub = f"{self.c.device_name()} · gespeichert in data/controls.json"
        draw_text(screen, sub, f.small, GREY, (86, 86))
        if self.page == "wizard":
            self._draw_wizard(screen)
        else:
            self._draw_list(screen)
            self._draw_live(screen, pygame.Rect(790, 124, 450, 284))
            self._draw_help(screen)
        hints = {"hub": "Pfeile wählen · ENTER öffnen · ESC zurück",
                 "binds": "Pfeile hoch/runter Aktion · links/rechts Spalte · ENTER neu belegen · ENTF löschen · "
                          "ESC zurück",
                 "tuning": "Pfeile wählen · links/rechts ändern · ENTER kalibrieren · ESC zurück",
                 "wizard": "ENTER übernehmen · RÜCKTASTE Schritt zurück · TAB überspringen · ESC abbrechen"}
        draw_text(screen, hints[self.page], f.small, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 26), anchor="center")

    def _draw_list(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        rows = self._rows()
        self.sel = min(self.sel, len(rows) - 1)
        px, py, pw, ph = 60, 124, 700, 560
        draw_panel(screen, (px, py, pw, ph), PANEL, 215)
        top = py + 10
        if self.page == "binds":
            draw_text(screen, "AKTION", f.tiny, GREY, (px + 28, top + 4), shadow=False)
            for k, name in enumerate(("LENKRAD / CONTROLLER", "TASTATUR")):
                col = YELLOW if k == self.col else GREY
                draw_text(screen, name, f.tiny, col, (px + 300 + k * 200, top + 4), shadow=False)
            top += 26
        rh = 56 if self.page == "hub" else 30
        visible = (py + ph - 10 - top) // rh
        self.scroll = max(min(self.scroll, self.sel), self.sel - visible + 1, 0)
        capturing = self.capture_axis or self.capture_button or self.capture_key
        for i, row in enumerate(rows):
            if not self.scroll <= i < self.scroll + visible:
                continue
            ry = top + (i - self.scroll) * rh
            selected = i == self.sel
            if row == "ZURÜCK":
                col = (120, 120, 130) if selected else (50, 50, 58)
                pygame.draw.rect(screen, col, (px + 20, ry + 3, pw - 40, rh - 4), border_radius=8)
                draw_text(screen, "ZURÜCK", f.small_bold, WHITE, (px + pw // 2, ry + 1 + rh // 2), anchor="center")
                mouse_item((px + 20, ry + 3, pw - 40, rh - 4), self, i)
                continue
            if self.page == "hub":
                mouse_item((px + 12, ry, pw - 24, rh - 2), self, i)
            elif self.page == "tuning":
                mouse_item((px + 12, ry, pw - 24, rh - 2), self, i, key=None, arrows=True)
            else:
                mouse_item((px + 12, ry, pw - 24, rh - 2), self, i, key=None)
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 12, ry, pw - 24, rh - 2), border_radius=6)
                pygame.draw.rect(screen, ACCENT, (px + 12, ry, 5, rh - 2), border_radius=2)
            mid = ry + (rh - 2) // 2
            if self.page == "hub":
                draw_text(screen, row, f.medium, WHITE, (px + 30, mid), anchor="midleft", shadow=False)
                continue
            if self.page == "binds":
                label = dict(BIND_ROWS).get(row, row)
                draw_text(screen, label.upper(), f.tiny, GREY if row in BIND_EXTRA else WHITE, (px + 28, mid),
                          anchor="midleft", shadow=False)
                if row in BIND_EXTRA:
                    continue
                cells = self._bind_cells(row)
                for k, text in enumerate(cells):
                    x = px + 300 + k * 200
                    mouse_item((x - 8, ry + 2, 190, rh - 6), self, (i, k), attr=("sel", "col"))
                    if selected and k == self.col:
                        pygame.draw.rect(screen, (60, 62, 74), (x - 8, ry + 2, 190, rh - 6), border_radius=5)
                        if capturing:
                            text = "... drücken ..."
                    col = YELLOW if selected and k == self.col else (130, 130, 140) if text == "nicht belegt" \
                        else WHITE
                    draw_text(screen, text, f.small_bold, col, (x, mid), anchor="midleft", shadow=False)
                continue
            draw_text(screen, row.upper(), f.tiny, GREY, (px + 28, mid), anchor="midleft", shadow=False)
            value = "... warte auf Eingabe ..." if selected and capturing else self._tuning_value(row)
            warn = row == "Pedal-Achsen" and self._combined()
            draw_text(screen, value, f.small_bold, YELLOW if selected and capturing else RED if warn else WHITE,
                      (px + 300, mid), anchor="midleft", shadow=False)
        if self.page == "hub":
            p = self.c.profile
            y = py + 4 * 56 + 30
            status = []
            if p is None:
                status.append(("Kein Lenkrad/Controller angeschlossen - Tastatur aktiv.", GREY))
            else:
                status.append((f"Gerät: {self.c.device_name()} ({DEVICE_KINDS[p.kind]})", WHITE))
                status.append(("Lenkung: " + ("kalibriert" if p.steer.axis >= 0 else "nicht belegt"),
                               GREEN if p.steer.axis >= 0 else RED))
                status.append(("Pedale: " + ("KOMBINIERT (eine Achse)" if self._combined() else "getrennt"),
                               RED if self._combined() else GREEN))
                if p.kind == "wheel" and p.rotation:
                    status.append((f"Drehbereich {p.rotation}° · Volleinschlag bei {p.saturation * p.rotation:.0f}°",
                                   WHITE))
                if p.kind == "wheel":
                    active = self.c.ffb_device(0)
                    status.append(("Force Feedback: " + (f"aktiv ({p.ffb * 100:.0f}%)" if active
                                                         else "kein FFB-Motor erkannt - nur Vibration"),
                                   GREEN if active else GREY))
            if self.note:
                status.append((self.note, YELLOW))
            for k, (text, col) in enumerate(status):
                draw_text(screen, text, f.small, col, (px + 30, y + k * 26), shadow=False)

    def _draw_help(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        hb = pygame.Rect(790, 420, 450, 264)
        draw_panel(screen, hb, PANEL, 215)
        rows = self._rows()
        row = rows[min(self.sel, len(rows) - 1)]
        if self.capture_axis is not None:
            title, text = "KALIBRIERUNG", AXIS_PROMPTS[self.capture_axis] + \
                " Übernahme automatisch nach kurzem Halten, ENTER übernimmt sofort, ESC bricht ab."
        elif self.capture_key is not None:
            title, text = "TASTE BELEGEN", "Gewünschte Taste auf der Tastatur drücken. ESC bricht ab. Die Taste " \
                "wird dabei von jeder anderen Aktion entfernt."
        elif self.capture_button is not None:
            title, text = "TASTE BELEGEN", f"Knopf am Lenkrad/Controller drücken für: " \
                f"{ACTIONS[self.capture_button][0]}. Entf löscht die Belegung, andere Taste bricht ab."
        elif self.page == "hub":
            title, text = row.upper(), HUB_HELP.get(row, "")
        elif self.page == "binds":
            title = "TASTENBELEGUNG"
            if row in KEY_DRIVE and self.col == 0:
                text = "Lenkung und Pedale sind Achsen: ENTER startet den Kalibrier-Assistenten für diese Achse."
            elif row in FIXED_KEYS and self.col == 1:
                text = "ESC und ENTER sind auf der Tastatur fest belegt."
            else:
                text = "ENTER, dann den Knopf am Lenkrad/Controller bzw. die Taste drücken. Jeder Knopf / jede " \
                       "Taste macht nur eine Sache - die alte Belegung wird entfernt. ENTF löscht. Im Splitscreen " \
                       "fährt Spieler 1 mit diesen Tasten (ohne Pfeile), Spieler 2 mit den Pfeiltasten."
        else:
            title = row.upper()
            text = TUNING_HELP.get(row, "")
            if row.endswith("kalibrieren"):
                text += " Links/rechts: Achse von Hand wählen (alle Geräte, auch separate Pedalboxen)."
        draw_text(screen, title, f.medium, WHITE, (hb.x + 18, hb.y + 14))
        for k, line in enumerate(_wrap(text, f.small, hb.w - 36)[:8]):
            draw_text(screen, line, f.small, (205, 205, 210), (hb.x + 18, hb.y + 50 + k * 24), shadow=False)

    def _draw_wizard(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        key, title, text = WIZARD[self.step]
        # step bar
        bx, by = 60, 124
        n = len(WIZARD)
        for k in range(n):
            col = GREEN if k < self.step else YELLOW if k == self.step else (60, 62, 72)
            pygame.draw.rect(screen, col, (bx + k * (1160 // n), by, 1160 // n - 8, 6), border_radius=3)
        box = pygame.Rect(60, 144, 700, 540)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, title, f.large, WHITE, (box.x + 24, box.y + 18))
        for k, line in enumerate(_wrap(text, f.medium, box.w - 48)[:4]):
            draw_text(screen, line, f.medium, (220, 220, 228), (box.x + 24, box.y + 70 + k * 30), shadow=False)
        p, joy = self.c.profile, self.c.joystick
        y = box.y + 200
        if key == "device" and p is not None:
            draw_text(screen, "<  " + self.c.device_name() + "  >", f.large, YELLOW, (box.centerx, y + 20),
                      anchor="center")
            draw_text(screen, f"Gerätetyp: {DEVICE_KINDS[p.kind]}  (hoch/runter)", f.medium, WHITE,
                      (box.centerx, y + 70), anchor="center")
            if joy is not None:
                draw_text(screen, f"{joy.get_numaxes()} Achsen · {joy.get_numbuttons()} Knöpfe", f.small, GREY,
                          (box.centerx, y + 104), anchor="center")
        elif key == "center":
            draw_text(screen, "Ruhig halten ...", f.medium, WHITE, (box.centerx, y + 20), anchor="center")
            self._progress(screen, box.centerx, y + 60, min(1.0, self.hold / 1.0))
        elif key in CAPTURE_STEPS:
            target, delta = self._step_delta(key)
            name, axis = target
            if not self.armed:
                draw_text(screen, "Erst loslassen / Lenkrad in die Mitte ...", f.medium, YELLOW,
                          (box.centerx, y - 20), anchor="center")
            where = f"{name[:22]} · Achse {axis}" if axis >= 0 else "-"
            draw_text(screen, f"Erkannt: {where}", f.medium, WHITE if delta > 0.3 else GREY, (box.centerx, y + 20),
                      anchor="center")
            self._progress(screen, box.centerx, y + 60, min(1.0, delta / 1.6), GREEN if delta > 0.6 else YELLOW)
            draw_text(screen, "Halten ..." if delta > 0.6 else "weiter ...", f.small, GREY, (box.centerx, y + 92),
                      anchor="center")
            if key in ("left", "right"):
                self._draw_wheel(screen, box.centerx, y + 200, 70)
        elif key == "rotation" and p is not None:
            rows = [("Drehbereich (Treiber)", f"{p.rotation}°"),
                    ("Volleinschlag bei", f"{p.saturation * p.rotation:.0f}°  (± {p.saturation * p.rotation / 2:.0f}°)")]
            for k, (label, value) in enumerate(rows):
                ry = y + k * 50
                if k == self.rot_sel:
                    pygame.draw.rect(screen, PANEL_LIGHT, (box.x + 20, ry - 4, box.w - 40, 40), border_radius=6)
                draw_text(screen, label, f.medium, GREY, (box.x + 40, ry + 16), anchor="midleft", shadow=False)
                draw_text(screen, f"<  {value}  >" if k == self.rot_sel else value, f.medium,
                          YELLOW if k == self.rot_sel else WHITE, (box.x + 380, ry + 16), anchor="midleft",
                          shadow=False)
            draw_text(screen, "Tipp: 900° Drehbereich, Volleinschlag 360-540° fühlt sich wie ein F1-Auto an.",
                      f.small, GREY, (box.x + 40, y + 110), shadow=False)
            self._draw_wheel(screen, box.centerx, y + 230, 70)
        elif key == "test":
            if self._combined():
                for k, line in enumerate(_wrap(TUNING_HELP["Pedal-Achsen"], f.small, box.w - 48)[:5]):
                    draw_text(screen, line, f.small, RED, (box.x + 24, y + k * 22), shadow=False)
            else:
                draw_text(screen, "Gas und Bremse auf getrennten Achsen - gleichzeitig nutzbar.", f.medium, GREEN,
                          (box.centerx, y + 10), anchor="center")
            self._draw_wheel(screen, box.centerx, y + 200, 80)
        if self.note:
            for k, line in enumerate(_wrap(self.note, f.small, box.w - 48)[:2]):
                draw_text(screen, line, f.small, YELLOW, (box.x + 24, box.bottom - 56 + k * 22), shadow=False)
        self._draw_live(screen, pygame.Rect(790, 144, 450, 300))

    def _progress(self, screen: pygame.Surface, cx: int, y: int, frac: float, col=GREEN) -> None:
        w = 420
        pygame.draw.rect(screen, (50, 52, 60), (cx - w // 2, y, w, 16), border_radius=8)
        pygame.draw.rect(screen, col, (cx - w // 2, y, int(w * frac), 16), border_radius=8)

    def _draw_wheel(self, screen: pygame.Surface, cx: int, cy: int, r: int) -> None:
        """Steering wheel turned by the physical angle; the in-game lock angle is shown next to it."""
        f = self.game.fonts
        p = self.c.profile
        steer = self.c.steering() or 0.0
        rotation = p.rotation if p is not None and p.rotation else 0
        if rotation:
            # physical angle: what the calibrated axis says, before the lock/saturation is applied
            raw = p.steer.read(self.c.axis_device(p.steer, self.c.joystick)) if p is not None else None
            angle = (raw or 0.0) * rotation / 2
        else:
            angle = steer * 90
        a = math.radians(angle)
        pygame.draw.circle(screen, (40, 42, 50), (cx, cy), r + 6)
        pygame.draw.circle(screen, (20, 20, 24), (cx, cy), r, 10)
        for spoke in (math.pi / 2, math.pi * 7 / 6, -math.pi / 6):
            ex = cx + math.cos(spoke + a) * (r - 6)
            ey = cy + math.sin(spoke + a) * (r - 6)
            pygame.draw.line(screen, (60, 62, 70), (cx, cy), (ex, ey), 8)
        top = (cx + math.sin(a) * r, cy - math.cos(a) * r)
        pygame.draw.circle(screen, YELLOW, top, 7)
        pygame.draw.circle(screen, (30, 30, 36), (cx, cy), 16)
        draw_text(screen, f"{angle:+.0f}°", f.medium, WHITE, (cx + r + 30, cy - 14), anchor="midleft")
        draw_text(screen, f"Lenkung im Spiel {steer * 100:+.0f}%", f.small, CYAN, (cx + r + 30, cy + 14),
                  anchor="midleft", shadow=False)

    def _draw_live(self, screen: pygame.Surface, box: pygame.Rect) -> None:
        f = self.game.fonts
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "LIVE-EINGABE", f.medium, WHITE, (box.x + 18, box.y + 12))
        c, joy = self.c, self.c.joystick
        if joy is None:
            for k, line in enumerate(_wrap("Kein Lenkrad oder Controller gefunden. Gerät anschließen - es wird "
                                           "automatisch erkannt.", f.small, box.w - 36)):
                draw_text(screen, line, f.small, GREY, (box.x + 18, box.y + 56 + k * 24), shadow=False)
            return
        steer = c.steering() or 0.0
        bx, by, bw = box.x + 130, box.y + 58, box.w - 150
        draw_text(screen, AXES["steer"], f.small_bold, GREY, (box.x + 18, by + 7), anchor="midleft")
        pygame.draw.rect(screen, (50, 52, 60), (bx, by, bw, 14), border_radius=7)
        mid = bx + bw // 2
        end = mid + int(steer * bw / 2)
        pygame.draw.rect(screen, CYAN, (min(mid, end), by, abs(end - mid) + 2, 14), border_radius=7)
        pygame.draw.line(screen, WHITE, (mid, by - 3), (mid, by + 16), 2)
        for k, (key, col) in enumerate((("throttle", GREEN), ("brake", (255, 70, 60)))):
            y = by + 32 + k * 28
            v = c.pedal(key) or 0.0
            draw_text(screen, AXES[key], f.small_bold, GREY, (box.x + 18, y + 7), anchor="midleft")
            pygame.draw.rect(screen, (50, 52, 60), (bx, y, bw, 14), border_radius=7)
            pygame.draw.rect(screen, col, (bx, y, int(bw * v), 14), border_radius=7)
        # raw axes of every device help to spot the right pedal
        y0 = by + 100
        draw_text(screen, "Rohachsen", f.tiny, GREY, (box.x + 18, y0))
        axes = self._all_axes()[:12]
        for k, (name, axis) in enumerate(axes):
            col_x = box.x + 18 + (k % 4) * 106
            y = y0 + 18 + (k // 4) * 22
            v = self._axis_value(name, axis)
            other = joy is not None and name != joy.get_name()
            label = f"{'*' if other else ''}{axis}: {v:+.2f}"
            draw_text(screen, label, f.mono, YELLOW if abs(v) > 0.5 else WHITE, (col_x, y), shadow=False)
        pressed = [str(b) for b in range(joy.get_numbuttons()) if joy.get_button(b)]
        yb = y0 + 18 + ((len(axes) + 3) // 4) * 22 + 4
        draw_text(screen, "Knöpfe: " + (", ".join(pressed) if pressed else "-"), f.small, WHITE, (box.x + 18, yb),
                  shadow=False)
        if len(self.c.joys) > 1:
            draw_text(screen, "* = Achse eines anderen Geräts (z.B. Pedalbox)", f.tiny, GREY,
                      (box.x + 18, yb + 26), shadow=False)
