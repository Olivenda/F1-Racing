# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from .controls import ACTIONS, AXES, DEVICE_KINDS, KEY_ACTIONS, KEY_DRIVE, AxisBinding, DeviceProfile
from .screens import _Background, _wrap
from .settings import CYAN, GREEN, GREY, PANEL, PANEL_LIGHT, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .utils import draw_panel, draw_text

if TYPE_CHECKING:
    from .game import Game

AXIS_PROMPTS = {
    "steer": "Lenkrad ganz nach RECHTS drehen (Stick nach rechts) und halten ...",
    "throttle": "Gaspedal VOLL durchtreten (Gas-Trigger ganz drücken) und halten ...",
    "brake": "Bremspedal VOLL durchtreten (Brems-Trigger ganz drücken) und halten ...",
}


class ControlsScreen:
    """Wheelbase / pedal / gamepad set-up: device choice, axis calibration, steering feel, button mapping."""

    HELP = {
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
        "Lenkbereich": "Anteil des Lenkwegs, der schon vollen Einschlag ergibt. Lenkrad mit 900°: 50% = "
                       "voller Einschlag bei 225° pro Seite. Kleiner = direktere Lenkung.",
        "Lenk-Totzone": "Ignorierter Bereich um die Mitte. Gamepad-Sticks ~6%, Lenkräder 0%.",
        "Lenk-Linearität": "1.0 = linear. Höher = feinfühliger um die Mitte, schneller am Anschlag.",
        "Pedal-Totzone": "Ignorierter Weg am Anfang und Ende der Pedale (gegen Rauschen).",
        "Vibration / Force-Feedback": "Stöße bei Einschlägen, Kies, Rutschen und durchdrehenden Rädern. "
                                      "Gamepads vibrieren; Lenkräder bekommen Rüttel-Impulse, soweit der "
                                      "Treiber SDL-Rumble unterstützt.",
        "Standard wiederherstellen": "Setzt Achsen, Tasten und Lenkgefühl dieses Geräts zurück.",
        "Pedal-Achsen": "Gas und Bremse brauchen ZWEI getrennte Achsen, sonst kann man nicht gleichzeitig bremsen "
                        "und Gas geben. Zeigt dies 'kombiniert': im Lenkrad-Treiber (Logitech G HUB: 'Kombinierte "
                        "Pedale' aus, Thrustmaster/Fanatec: 'separate axes') umstellen und Gas + Bremse neu "
                        "kalibrieren. Eine separate Pedalbox (eigenes USB-Gerät) wird beim Kalibrieren erkannt.",
        "Tastatur zurücksetzen": "Alle Tastatur-Belegungen auf Standard (Pfeile/WASD, Leertaste, B, R ...).",
        "ZURÜCK": "Wird automatisch in data/controls.json gespeichert (pro Gerät).",
    }

    def __init__(self, game: "Game") -> None:
        self.game = game
        self.sel = 0
        self.bg = _Background()
        self.t = 0.0
        self.capture_axis: str | None = None
        self.capture_button: str | None = None
        self.capture_key: str | None = None
        self.baseline: dict[tuple[str, int], float] = {}
        self.scroll = 0
        self.hold = 0.0
        self.peak = 0.0
        self.swallow_until = 0

    @property
    def c(self):
        return self.game.controls

    @property
    def rows(self) -> list[str]:
        rows = ["Gerät", "Controller-Eingabe"]
        if self.c.profile is not None:
            rows += ["Gerätetyp", "Lenkung kalibrieren", "Gaspedal kalibrieren", "Bremspedal kalibrieren",
                     "Lenkbereich", "Lenk-Totzone", "Lenk-Linearität", "Pedal-Totzone",
                     "Vibration / Force-Feedback"]
            rows.insert(rows.index("Lenkbereich"), "Pedal-Achsen")
            rows += [f"Taste: {ACTIONS[a][0]}" for a in ACTIONS]
            rows += ["Standard wiederherstellen"]
        rows += [f"Tastatur: {name}" for name, _ in KEY_DRIVE.values()]
        rows += [f"Tastatur: {ACTIONS[a][0]}" for a in KEY_ACTIONS]
        return rows + ["Tastatur zurücksetzen", "ZURÜCK"]

    def _value(self, row: str) -> str:
        c, p = self.c, self.c.profile
        if row == "Gerät":
            n = len(c.joys)
            return f"{c.device_name()}" + (f"  ({n} Geräte)" if n > 1 else "")
        if row == "Controller-Eingabe":
            return "An" if c.enabled else "Aus"
        if row.startswith("Tastatur: "):
            keys = c.keys[self._key_action(row)]
            return " / ".join(pygame.key.name(k).upper() for k in keys) if keys else "nicht belegt"
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
        if row == "Lenkbereich":
            return f"{p.saturation * 100:.0f}%"
        if row == "Lenk-Totzone":
            return f"{p.deadzone * 100:.0f}%"
        if row == "Lenk-Linearität":
            return f"{p.linearity:.1f}"
        if row == "Pedal-Totzone":
            return f"{p.pedal_deadzone * 100:.0f}%"
        if row == "Vibration / Force-Feedback":
            return f"{p.rumble * 100:.0f}%"
        if row.startswith("Taste: "):
            action = self._action_of(row)
            b = p.buttons.get(action, -1)
            return "nicht belegt" if b < 0 else f"Knopf {b}"
        return ""

    def _combined(self) -> bool:
        p = self.c.profile
        return p is not None and p.throttle.axis >= 0 and \
            (p.throttle.axis, p.throttle.device) == (p.brake.axis, p.brake.device)

    @staticmethod
    def _key_action(row: str) -> str:
        label = row[len("Tastatur: "):]
        for action, (name, _) in KEY_DRIVE.items():
            if name == label:
                return action
        return next(a for a in KEY_ACTIONS if ACTIONS[a][0] == label)

    def _all_axes(self) -> list[tuple[str, int]]:
        return [(j.get_name(), k) for j in self.c.joys.values() for k in range(j.get_numaxes())]

    def _axis_value(self, name: str, axis: int) -> float:
        joy = next((j for j in self.c.joys.values() if j.get_name() == name), None)
        return joy.get_axis(axis) if joy is not None and axis < joy.get_numaxes() else 0.0

    def _pick_axis(self, which: str, delta: int) -> None:
        """Left/right on a calibration row: step through every axis of every device by hand."""
        p, joy = self.c.profile, self.c.joystick
        axes = self._all_axes()
        if p is None or joy is None or not axes:
            return
        b: AxisBinding = getattr(p, which)
        current = (b.device or joy.get_name(), b.axis)
        k = axes.index(current) if current in axes else -1
        name, axis = axes[(k + delta) % len(axes)]
        rest = self._axis_value(name, axis)
        if which == "steer":
            full = 1.0
        else:
            full = -1.0 if rest > 0.5 else 1.0     # pedals rest at one end of the axis or in the middle
        setattr(p, which, AxisBinding(axis, round(rest, 3), full, "" if name == joy.get_name() else name))
        self.c.save()

    @staticmethod
    def _action_of(row: str) -> str:
        label = row[len("Taste: "):]
        return next(a for a, (name, _) in ACTIONS.items() if name == label)

    def _change(self, row: str, delta: int) -> None:
        c, p = self.c, self.c.profile
        if row == "Gerät":
            c.cycle_device()
        elif row == "Controller-Eingabe":
            c.enabled = not c.enabled
        elif p is None:
            return
        elif row == "Gerätetyp":
            p.kind = "gamepad" if p.kind == "wheel" else "wheel"
        elif row == "Lenkbereich":
            p.saturation = round(max(0.2, min(1.0, p.saturation + 0.05 * delta)), 2)
        elif row == "Lenk-Totzone":
            p.deadzone = round(max(0.0, min(0.3, p.deadzone + 0.01 * delta)), 2)
        elif row == "Lenk-Linearität":
            p.linearity = round(max(1.0, min(3.0, p.linearity + 0.1 * delta)), 1)
        elif row == "Pedal-Totzone":
            p.pedal_deadzone = round(max(0.0, min(0.2, p.pedal_deadzone + 0.01 * delta)), 2)
        elif row == "Vibration / Force-Feedback":
            p.rumble = round(max(0.0, min(1.0, p.rumble + 0.1 * delta)), 1)
            c.rumble(0.6, 0.6, 250)
        elif row.endswith("kalibrieren"):
            self._pick_axis({"Lenkung": "steer", "Gaspedal": "throttle", "Bremspedal": "brake"}[row.split()[0]],
                            delta)
            return
        else:
            return
        c.save()

    def _activate(self, row: str) -> None:
        c, joy = self.c, self.c.joystick
        if row == "ZURÜCK":
            c.save()
            from .screens import SettingsScreen
            self.game.state = SettingsScreen(self.game)
        elif row == "Standard wiederherstellen" and joy is not None:
            c.profiles[joy.get_name()] = DeviceProfile.for_device(joy.get_name(), joy.get_numaxes())
            c.save()
        elif row.endswith("kalibrieren") and joy is not None:
            self.capture_axis = {"Lenkung": "steer", "Gaspedal": "throttle", "Bremspedal": "brake"}[row.split()[0]]
            self.baseline = {(n, k): self._axis_value(n, k) for n, k in self._all_axes()}
            self.hold = 0.0
            self.peak = 0.0
        elif row.startswith("Tastatur: "):
            self.capture_key = self._key_action(row)
        elif row == "Tastatur zurücksetzen":
            c.reset_keys()
        elif row.startswith("Taste: ") and joy is not None:
            self.capture_button = self._action_of(row)
        else:
            self._change(row, 1)

    def _finish_axis(self) -> None:
        joy, p = self.c.joystick, self.c.profile
        if joy is None or p is None or self.capture_axis is None:
            self.capture_axis = None
            return
        (name, axis), delta = self._moved_axis()
        if axis >= 0 and delta > 0.3:
            rest, now = self.baseline[(name, axis)], self._axis_value(name, axis)
            # steering is symmetric: the end stop is the end of the axis, however far it was turned
            full = (1.0 if now > rest else -1.0) if self.capture_axis == "steer" else now
            device = "" if name == joy.get_name() else name
            setattr(p, self.capture_axis, AxisBinding(axis, round(rest, 3), round(full, 3), device))
            self.c.save()
        self.capture_axis = None

    def _moved_axis(self) -> tuple[tuple[str, int], float]:
        """The axis (on any device - pedal boxes are often a separate USB device) that moved the most.
        Calibrating the brake ignores the throttle's axis unless nothing else moved (combined pedals)."""
        p = self.c.profile
        skip = None
        if p is not None and self.capture_axis == "brake" and p.throttle.axis >= 0:
            joy = self.c.joystick
            skip = (p.throttle.device or (joy.get_name() if joy else ""), p.throttle.axis)
        moved = sorted(((abs(self._axis_value(n, k) - v), (n, k)) for (n, k), v in self.baseline.items()),
                       reverse=True)
        if not moved:
            return ("", -1), 0.0
        for d, key in moved:
            if key != skip and d > 0.3:
                return key, d
        return moved[0][1], moved[0][0]

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.capture_key is not None:
            if event.type == pygame.KEYDOWN and not getattr(event, "from_joystick", False):
                if event.key != pygame.K_ESCAPE:
                    self.c.bind_key(self.capture_key, event.key)
                self.capture_key = None
            return
        if self.capture_button is not None:
            if event.type == pygame.JOYBUTTONDOWN and event.instance_id == self.c.active:
                p = self.c.profile
                if p is not None:
                    # a button can only do one thing in the car
                    for a, b in list(p.buttons.items()):
                        if b == event.button:
                            p.buttons[a] = -1
                    p.buttons[self.capture_button] = event.button
                    self.c.save()
                self.capture_button = None
                self.swallow_until = pygame.time.get_ticks() + 250
            elif event.type == pygame.KEYDOWN and not getattr(event, "from_joystick", False):
                if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE) and self.c.profile is not None:
                    self.c.profile.buttons[self.capture_button] = -1
                    self.c.save()
                self.capture_button = None
            return
        if self.capture_axis is not None:
            if event.type == pygame.KEYDOWN and not getattr(event, "from_joystick", False):
                if event.key == pygame.K_ESCAPE:
                    self.capture_axis = None
                else:
                    self._finish_axis()
            return
        if event.type != pygame.KEYDOWN:
            return
        if getattr(event, "from_joystick", False) and pygame.time.get_ticks() < self.swallow_until:
            return
        rows = self.rows
        self.sel = min(self.sel, len(rows) - 1)
        row = rows[self.sel]
        if event.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(rows)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(rows)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._change(row, -1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._change(row, 1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate(row)
        elif event.key == pygame.K_ESCAPE:
            self._activate("ZURÜCK")

    def update(self, dt: float) -> None:
        self.t += dt
        self.bg.update(dt)
        if self.capture_axis is not None:
            if self.c.joystick is None:
                self.capture_axis = None
                return
            _, delta = self._moved_axis()
            # wait until the pedal / wheel stops moving at its furthest point
            self.hold = self.hold + dt if delta > 0.6 and delta >= self.peak - 0.03 else 0.0
            self.peak = max(self.peak, delta)
            if self.hold > 0.8:
                self._finish_axis()
                self.swallow_until = pygame.time.get_ticks() + 250

    def draw(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        self.bg.draw(screen)
        pygame.draw.rect(screen, (200, 200, 210), (60, 40, 8, 60))
        draw_text(screen, "LENKRAD & CONTROLLER", f.big, WHITE, (84, 36))
        draw_text(screen, "Wheelbase, Pedale und Gamepads · gespeichert in data/controls.json", f.small, GREY,
                  (86, 86))
        rows = self.rows
        self.sel = min(self.sel, len(rows) - 1)
        px, py, pw, ph = 60, 124, 700, 560
        draw_panel(screen, (px, py, pw, ph), PANEL, 215)
        rh = 32
        visible = (ph - 20) // rh
        self.scroll = max(min(self.scroll, self.sel), self.sel - visible + 1, 0)
        for i, row in enumerate(rows):
            if not self.scroll <= i < self.scroll + visible:
                continue
            ry = py + 10 + (i - self.scroll) * rh
            selected = i == self.sel
            if row == "ZURÜCK":
                col = (120, 120, 130) if selected else (50, 50, 58)
                pygame.draw.rect(screen, col, (px + 20, ry + 3, pw - 40, rh - 4), border_radius=8)
                draw_text(screen, "ZURÜCK", f.small_bold, WHITE, (px + pw // 2, ry + 1 + rh // 2), anchor="center")
                continue
            if selected:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 12, ry, pw - 24, rh - 2), border_radius=6)
                pygame.draw.rect(screen, (200, 200, 210), (px + 12, ry, 5, rh - 2), border_radius=2)
            mid = ry + (rh - 2) // 2
            draw_text(screen, row.upper(), f.tiny, GREY, (px + 28, mid), anchor="midleft", shadow=False)
            capturing = selected and (self.capture_axis or self.capture_button or self.capture_key)
            value = "... warte auf Eingabe ..." if capturing else self._value(row)
            warn = row == "Pedal-Achsen" and self._combined()
            draw_text(screen, value, f.small_bold, YELLOW if capturing else (255, 90, 90) if warn else WHITE,
                      (px + 330, mid), anchor="midleft", shadow=False)
        self._draw_live(screen)
        hb = pygame.Rect(790, 420, 450, 264)
        draw_panel(screen, hb, PANEL, 215)
        row = rows[self.sel]
        if self.capture_axis is not None:
            title, text = "KALIBRIERUNG", AXIS_PROMPTS[self.capture_axis] + \
                " Übernahme automatisch nach kurzem Halten, ENTER übernimmt sofort, ESC bricht ab."
        elif self.capture_key is not None:
            title, text = "TASTE BELEGEN", "Gewünschte Taste auf der Tastatur drücken. ESC bricht ab. Die Taste " \
                "wird dabei von jeder anderen Aktion entfernt."
        elif self.capture_button is not None:
            title, text = "TASTE BELEGEN", f"Knopf am Lenkrad/Controller drücken für: " \
                f"{ACTIONS[self.capture_button][0]}. Entf löscht die Belegung, andere Taste bricht ab."
        else:
            title = row.upper() if not row.startswith(("Taste: ", "Tastatur: ")) else "TASTENBELEGUNG"
            if row.startswith("Tastatur: "):
                text = "ENTER, dann die neue Taste drücken. Im Splitscreen fährt Spieler 1 mit diesen Tasten " \
                       "(ohne Pfeile), Spieler 2 mit den Pfeiltasten."
            elif row.endswith("kalibrieren"):
                text = self.HELP[row] + " Links/rechts: Achse von Hand wählen (alle Geräte, auch separate " \
                                        "Pedalboxen)."
            else:
                text = self.HELP.get(row, "ENTER, dann den gewünschten Knopf drücken. Jede Aktion geht "
                                          "weiterhin auch über die Tastatur.")
        draw_text(screen, title, f.medium, WHITE, (hb.x + 18, hb.y + 14))
        for k, line in enumerate(_wrap(text, f.small, hb.w - 36)[:8]):
            draw_text(screen, line, f.small, (205, 205, 210), (hb.x + 18, hb.y + 50 + k * 24), shadow=False)
        draw_text(screen, "Pfeile wählen · links/rechts ändern · ENTER kalibrieren/belegen · ESC zurück", f.small,
                  GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 26), anchor="center")

    def _draw_live(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        box = pygame.Rect(790, 124, 450, 284)
        draw_panel(screen, box, PANEL, 215)
        draw_text(screen, "LIVE-EINGABE", f.medium, WHITE, (box.x + 18, box.y + 12))
        c, joy = self.c, self.c.joystick
        if joy is None:
            for k, line in enumerate(_wrap("Kein Lenkrad oder Controller gefunden. Gerät anschließen - es wird "
                                           "automatisch erkannt.", f.small, box.w - 36)):
                draw_text(screen, line, f.small, GREY, (box.x + 18, box.y + 56 + k * 24), shadow=False)
            return
        steer = c.steering() or 0.0
        # steering: centred bar
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
        # raw axes help to spot the right pedal
        y0 = by + 100
        draw_text(screen, "Rohachsen", f.tiny, GREY, (box.x + 18, y0))
        n = joy.get_numaxes()
        for k in range(min(n, 8)):
            col_x = box.x + 18 + (k % 4) * 106
            y = y0 + 20 + (k // 4) * 24
            v = joy.get_axis(k)
            draw_text(screen, f"{k}: {v:+.2f}", f.mono, YELLOW if abs(v) > 0.5 else WHITE, (col_x, y), shadow=False)
        pressed = [str(b) for b in range(joy.get_numbuttons()) if joy.get_button(b)]
        draw_text(screen, "Knöpfe: " + (", ".join(pressed) if pressed else "-"), f.small, WHITE,
                  (box.x + 18, y0 + 76), shadow=False)
        draw_text(screen, f"{n} Achsen · {joy.get_numbuttons()} Knöpfe · {joy.get_numhats()} Steuerkreuz",
                  f.tiny, GREY, (box.x + 18, y0 + 104), shadow=False)
