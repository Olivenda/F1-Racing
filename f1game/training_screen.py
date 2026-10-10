# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from . import ctrain
from .hud import draw_network
from .profiles import recording_stats
from .settings import CYAN, GREY, PANEL, PANEL_LIGHT, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, YELLOW
from .track import Track
from .training import REWARD_STYLES, Trainer
from .i18n import tr
from .utils import draw_panel, draw_text, mouse_item

if TYPE_CHECKING:
    from .game import Game

MODES = ["base", "balanced", "aggressive", "cautious", "clone"]
DEFAULT_GENS = {"base": 60, "balanced": 20, "aggressive": 20, "cautious": 20, "clone": 15}
# training engines: the native trainer (ctrain/f1train.exe, ~1000x faster) on GPU+CPU or CPU only, or Python
ENGINES = [("c", "auto", "C - GPU + CPU (schnellste)"), ("c", "cpu", "C - nur CPU"),
           ("py", "", "Python (langsam, mit Live-Ansicht)")]
POPULATION_STEPS = {"py": (16, 96, 8), "c": (16, 8000, 0)}


class TrainingScreen:
    ROWS = ["Modus", "Trainer", "GPU", "Generationen", "Population", "START"]
    FRAME_BUDGET = 0.028
    TURBO_BUDGET = 0.075

    def __init__(self, game: "Game") -> None:
        self.game = game
        self.sel = 5
        self.mode_i = 0
        self.engine_i = 0
        self.gens = DEFAULT_GENS["base"]
        self.population = 400
        self.trainer: Trainer | None = None
        self.native: ctrain.NativeTraining | None = None
        self.error: str | None = None
        self.log: list[str] = []
        self.turbo = False
        self.started_at = 0.0
        self._overview: dict[str, tuple[pygame.Surface, float, Vector2]] = {}
        self.rec_files, self.rec_samples = recording_stats()
        self._load_saved()

    @property
    def mode(self) -> str:
        return MODES[self.mode_i]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if self.native is not None:
            if event.key == pygame.K_ESCAPE or (self.native.done and event.key == pygame.K_RETURN):
                self.native.stop()
                self._leave()
            return
        if self.trainer is not None:
            if event.key == pygame.K_t:
                self.turbo = not self.turbo
            elif event.key == pygame.K_ESCAPE or (self.trainer.done and event.key == pygame.K_RETURN):
                self._leave()
            return
        if event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()
        elif event.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % len(self.ROWS)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % len(self.ROWS)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            d = -1 if event.key in (pygame.K_LEFT, pygame.K_a) else 1
            row = self.ROWS[self.sel]
            if row == "Modus":
                was = self.engine
                self.mode_i = (self.mode_i + d) % len(MODES)
                self.gens = DEFAULT_GENS[self.mode]
                if self.engine != was:
                    self.population = 400 if self.engine == "c" else 40
                self._load_saved()
            elif row == "Trainer":
                self.engine_i = (self.engine_i + d) % len(ENGINES)
                self.population = 400 if self.engine == "c" else 40
                self._load_saved()
            elif row == "GPU" and self._uses_gpu:
                choices = self._gpu_choices()
                keys = [k for k, _ in choices]
                cur = self.game.settings.train_gpu
                k = keys.index(cur) if cur in keys else 0
                self.game.settings.train_gpu = keys[(k + d) % len(keys)]
                self.game.settings.save()
            elif row == "Generationen":
                self.gens = max(2, min(1000 if self.engine == "c" else 300, self.gens + d * 5))
            elif row == "Population":
                lo, hi, step = POPULATION_STEPS[self.engine]
                if not step:        # C: big populations are cheap - grow in ~25 % steps
                    step = max(8, int(self.population * 0.25) // 8 * 8)
                self.population = max(lo, min(hi, self.population + d * step))
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._start()

    @property
    def _uses_gpu(self) -> bool:
        return self.engine == "c" and ENGINES[self.engine_i][1] != "cpu"

    def _gpu_choices(self) -> list[tuple[str, str]]:
        """(setting value, label): the strongest GPU, every single one and - with several - all together."""
        gpus = ctrain.list_gpus()
        if not gpus:
            return [("best", "automatisch")]
        strongest = max(gpus, key=lambda g: g[1])
        out = [("best", f"Stärkste: {strongest[2]}")]
        out += [(str(n), f"{n + 1}: {name}") for n, _cu, name in gpus]
        if len(gpus) > 1:
            out.append(("all", f"Alle {len(gpus)} GPUs zusammen"))
        return out

    def _gpu_label(self) -> str:
        if not self._uses_gpu:
            return "- (nur bei C - GPU + CPU)"
        cur = self.game.settings.train_gpu
        return next((lb for k, lb in self._gpu_choices() if k == cur), "automatisch")

    @property
    def engine(self) -> str:
        """'c' or 'py' - clone training (backprop on your recordings) only exists in Python."""
        return "py" if self.mode == "clone" else ENGINES[self.engine_i][0]

    def _saved_progress(self) -> tuple[int, int, int] | None:
        """(generation, target, population) of a paused native run of this mode."""
        try:
            with open(ctrain.state_file(self.mode), "rb") as fh:
                raw = fh.read(32)
        except OSError:
            return None
        if len(raw) < 32 or raw[:4] != b"F1CS":
            return None
        target, pop, gen = (int.from_bytes(raw[k:k + 4], "little") for k in (8, 12, 16))
        return gen, target, pop

    def _load_saved(self) -> None:
        """A paused C run of this mode: show its settings, START continues it."""
        saved = self._saved_progress() if self.engine == "c" else None
        if saved is not None:
            self.gens, self.population = saved[1], saved[2]

    def _start(self) -> None:
        self.error = None
        if self.mode != "base" and self.mode != "clone" and not self.game.brains.has("base"):
            self.error = "Zuerst das Basis-Netz trainieren."
            return
        tracks = list(self.game.tracks.values())
        if self.engine == "c":
            self._start_native(tracks)
            return
        try:
            self.trainer = Trainer(self.mode, tracks, self.gens, self.population, self.game.brains,
                                   log=self._log)
        except (ValueError, FileNotFoundError) as exc:
            self.error = str(exc)
            self.trainer = None
            return
        self.started_at = time.time()

    def _start_native(self, tracks: list[Track]) -> None:
        try:
            ctrain.export_training_data(tracks)
        except OSError as exc:
            self.error = f"Streckendaten konnten nicht geschrieben werden: {exc}"
            return
        build_log: list[str] = []
        if not ctrain.build(build_log.append):
            self.error = build_log[-1] if build_log else "C-Trainer fehlt (ctrain/build.bat)."
            return
        try:
            saved = self._saved_progress()
            fresh = saved is not None and saved[2] != self.population      # other population: start over
            self.native = ctrain.NativeTraining(self.mode, self.gens, self.population, ENGINES[self.engine_i][1],
                                                fresh=fresh, gpu=self.game.settings.train_gpu)
        except OSError as exc:
            self.error = f"C-Trainer startet nicht: {exc}"
            return
        self.started_at = time.time()

    def _log(self, msg: str) -> None:
        self.log.append(msg)
        self.log = self.log[-9:]

    def _leave(self) -> None:
        if (self.trainer is not None and self.trainer.done) or (self.native is not None and self.native.saved_path):
            self.game.reload_brains()
        self.game.go_to_menu()

    def update(self, dt: float) -> None:
        if self.native is not None:
            self.native.poll()
            return
        tr = self.trainer
        if tr is None or tr.done:
            return
        budget = self.TURBO_BUDGET if self.turbo else self.FRAME_BUDGET
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < budget and not tr.done:
            tr.step(40)

    def _overview_for(self, track: Track, box: pygame.Rect) -> tuple[pygame.Surface, float, Vector2]:
        key = track.definition.key
        if key not in self._overview:
            surf = pygame.Surface(box.size, pygame.SRCALPHA)
            scale, off = track.minimap_transform(pygame.Rect(0, 0, box.w, box.h), pad=20)
            pts = [(p.x * scale + off.x, p.y * scale + off.y) for p in track.center]
            w = max(3, int(track.half_width * 2 * scale))
            for p in pts:
                pygame.draw.circle(surf, (70, 72, 80), p, w / 2 + 2)
            for p in pts:
                pygame.draw.circle(surf, (48, 50, 56), p, w / 2)
            s0 = track.center[0] * scale + off
            n0 = track.normals[0] * (w / 2)
            pygame.draw.line(surf, WHITE, s0 - n0, s0 + n0, 2)
            self._overview[key] = (surf, scale, off)
        return self._overview[key]

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill((14, 15, 20))
        if self.native is not None:
            self._draw_native(screen)
        elif self.trainer is None:
            self._draw_setup(screen)
        else:
            self._draw_training(screen)

    def _draw_setup(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        pygame.draw.rect(screen, (40, 110, 200), (60, 40, 8, 60))
        draw_text(screen, "KI-TRAINING", f.big, WHITE, (84, 36))
        draw_text(screen, "Neuroevolution: Netze fahren, die besten vererben ihre Gewichte weiter.", f.small, GREY,
                  (86, 86))
        px, py, pw = 60, 140, 560
        draw_panel(screen, (px, py, pw, 340), PANEL, 220)
        values = {"Modus": REWARD_STYLES[self.mode].title, "Generationen": str(self.gens),
                  "Population": f"{self.population} Netze",
                  "Trainer": "Python (Klon-Training)" if self.mode == "clone" else ENGINES[self.engine_i][2],
                  "GPU": self._gpu_label()}
        for i, row in enumerate(self.ROWS):
            ry = py + 6 + i * 55
            sel = i == self.sel
            if row == "START":
                col = (40, 110, 200) if sel else (20, 50, 90)
                pygame.draw.rect(screen, col, (px + 20, ry + 6, pw - 40, 46), border_radius=8)
                mouse_item((px + 20, ry + 6, pw - 40, 46), self, i)
                draw_text(screen, "TRAINING STARTEN", f.large, WHITE, (px + pw // 2, ry + 29), anchor="center")
                continue
            mouse_item((px + 12, ry, pw - 24, 50), self, i, key=None, arrows=True)
            if sel:
                pygame.draw.rect(screen, PANEL_LIGHT, (px + 12, ry, pw - 24, 50), border_radius=6)
                pygame.draw.rect(screen, (40, 110, 200), (px + 12, ry, 5, 50), border_radius=2)
                draw_text(screen, "<  >", f.large, YELLOW, (px + pw - 40, ry + 25), anchor="midright")
            draw_text(screen, row.upper(), f.tiny, GREY, (px + 30, ry + 8), shadow=False)
            draw_text(screen, values[row], f.medium, WHITE, (px + 30, ry + 24), shadow=False)

        info = pygame.Rect(650, 140, 570, 330)
        draw_panel(screen, info, PANEL, 220)
        style = REWARD_STYLES[self.mode]
        draw_text(screen, style.title.upper(), f.large, WHITE, (info.x + 20, info.y + 16))
        draw_text(screen, style.description, f.small, (200, 200, 205), (info.x + 20, info.y + 58))
        lines = ["Belohnungsfunktion (Fitness):",
                 "  + gefahrene Strecke (px)",
                 f"  - {style.w_wall} x Mauer-Aufprallimpuls,  - 150 x Sek. neben der Strecke",
                 "  - 400 pro Unfall,  - 250 pro Track-Limits-Verstoß"]
        if style.w_car or style.w_gain:
            lines += [f"  - {style.w_car} x Auto-Kontaktimpuls",
                      f"  + {style.w_gain:.0f} x gewonnene Positionen",
                      f"  {'+' if style.w_tailgate >= 0 else '-'} {abs(style.w_tailgate):.0f} x Sek. dicht hinter Gegner"]
        if self.mode == "clone":
            lines += ["", f"Trainingsdaten: {self.rec_files} Aufnahmen, {self.rec_samples} Samples",
                      "Jede deiner Sessions wird automatisch aufgezeichnet."]
        lines += ["", f"Ergebnis: data/brains/{self.mode}.json (Backup der alten Datei)"]
        saved = self._saved_progress() if self.engine == "c" else None
        if saved is not None:
            lines.append(f"Pausiert bei Gen. {saved[0]}/{saved[1]} (Pop. {saved[2]}) - START setzt fort")
            if saved[2] != self.population:
                lines.append("Andere Population gewählt: START beginnt neu")
        for i, line in enumerate(lines):
            draw_text(screen, line, f.mono, (210, 210, 215), (info.x + 20, info.y + 96 + i * 21), shadow=False)
        if self.error:
            for i, chunk in enumerate(_chunks(self.error, 110)[:4]):
                draw_text(screen, chunk, f.small_bold, (255, 110, 110), (60, 492 + i * 22))
        draw_text(screen, "ENTER Start · ESC zurück · Pfeiltasten wählen", f.small, GREY,
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30), anchor="center")

    def _draw_training(self, screen: pygame.Surface) -> None:
        f = self.game.fonts
        tr = self.trainer
        assert tr is not None
        view = tr.view
        world = pygame.Rect(16, 16, 800, 470)
        draw_panel(screen, world, PANEL, 230)
        if view is not None and not self.turbo:
            surf, scale, off = self._overview_for(view.track, world)
            screen.blit(surf, world)
            leader = view.leader()
            for car, alive in zip(view.cars, view.alive):
                p = Vector2(world.x + car.pos.x * scale + off.x, world.y + car.pos.y * scale + off.y)
                fwd = car.forward
                tip, back = p + fwd * 7, p - fwd * 5
                side = Vector2(-fwd.y, fwd.x) * 4
                col = car.color if alive else (90, 90, 95)
                pygame.draw.polygon(screen, col, [tip, back + side, back - side])
            lp = Vector2(world.x + leader.pos.x * scale + off.x, world.y + leader.pos.y * scale + off.y)
            pygame.draw.circle(screen, YELLOW, lp, 12, 2)
            draw_text(screen, f"{view.track.name} · {'Rennen mit Kollisionen' if view.traffic else 'Solo (Geister)'}"
                              f" · {sum(view.alive)}/{len(view.cars)} aktiv · t={view.time:4.1f}s",
                      f.small_bold, WHITE, (world.x + 14, world.y + 10))
        elif self.turbo:
            draw_text(screen, "TURBO - Darstellung aus, volle Rechenleistung fürs Training", f.medium, YELLOW,
                      world.center, anchor="center")

        st = pygame.Rect(832, 16, 432, 150)
        draw_panel(screen, st, PANEL, 230)
        draw_text(screen, REWARD_STYLES[tr.mode].title.upper(), f.medium, CYAN, (st.x + 14, st.y + 10))
        gen_shown = min(tr.generation + 1, tr.target_generations)
        draw_text(screen, f"Generation {gen_shown}/{tr.target_generations}", f.large, WHITE, (st.x + 14, st.y + 38))
        elapsed = time.time() - self.started_at
        draw_text(screen, f"Lauf {tr.task_index}/{tr.task_total} · Population {tr.pop_size} · "
                          f"{tr.champion.parameter_count if tr.champion else tr.population[0].parameter_count} Gewichte",
                  f.tiny, GREY, (st.x + 14, st.y + 80), shadow=False)
        draw_text(screen, f"Echtzeit {elapsed / 60:4.1f} min · simuliert {tr.sim_time / 60:5.1f} min "
                          f"(x{tr.sim_time / max(elapsed, 1e-6):.0f})", f.tiny, GREY, (st.x + 14, st.y + 98),
                  shadow=False)
        prog = (tr.generation + tr.task_index / max(1, tr.task_total)) / tr.target_generations
        pygame.draw.rect(screen, (45, 45, 52), (st.x + 14, st.y + 122, st.w - 28, 10), border_radius=4)
        pygame.draw.rect(screen, (40, 110, 200), (st.x + 14, st.y + 122, (st.w - 28) * min(1, prog), 10),
                         border_radius=4)

        lg = pygame.Rect(832, 176, 432, 310)
        draw_panel(screen, lg, PANEL, 230)
        draw_text(screen, "PROTOKOLL", f.tiny, GREY, (lg.x + 14, lg.y + 8), shadow=False)
        y = lg.y + 28
        for line in self.log:
            for chunk in _chunks(line, 58):
                draw_text(screen, chunk, f.tiny, (210, 210, 215), (lg.x + 14, y), shadow=False)
                y += 17

        self._draw_chart(screen, pygame.Rect(16, 498, 520, 206))
        nn = pygame.Rect(548, 498, 716, 206)
        draw_panel(screen, nn, PANEL, 230)
        if view is not None and not self.turbo:
            draw_text(screen, "NETZ DES FÜHRENDEN GENOMS (live)", f.tiny, GREY, (nn.x + 12, nn.y + 8), shadow=False)
            draw_network(screen, nn.inflate(-24, -30).move(0, 8), view.leader().driver.net, f.tiny)

        if tr.done:
            shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 170))
            screen.blit(shade, (0, 0))
            draw_text(screen, "TRAINING ABGESCHLOSSEN", f.big, WHITE, (SCREEN_WIDTH // 2, 290), anchor="center")
            draw_text(screen, f"Gespeichert: {tr.saved_path}", f.small, GREY, (SCREEN_WIDTH // 2, 340),
                      anchor="center")
            draw_text(screen, "ENTER: zurück zum Menü (neue Gehirne werden sofort verwendet)", f.medium, CYAN,
                      (SCREEN_WIDTH // 2, 390), anchor="center")
        else:
            draw_text(screen, "T Turbo · ESC abbrechen (ohne Speichern)", f.tiny, GREY,
                      (SCREEN_WIDTH - 20, SCREEN_HEIGHT - 8), anchor="bottomright")

    def _draw_native(self, screen: pygame.Surface) -> None:
        """Progress of the C trainer running in its own process."""
        f = self.game.fonts
        nt = self.native
        assert nt is not None
        top = pygame.Rect(16, 16, 1248, 150)
        draw_panel(screen, top, PANEL, 230)
        draw_text(screen, f"{REWARD_STYLES[nt.mode].title.upper()} · C-TRAINER", f.medium, CYAN,
                  (top.x + 14, top.y + 10))
        gen_shown = min(nt.generation + (0 if nt.done else 1), max(1, nt.target))
        draw_text(screen, f"Generation {gen_shown}/{nt.target}", f.large, WHITE, (top.x + 14, top.y + 38))
        elapsed = time.time() - self.started_at
        speed = f"{nt.speed:,.0f}".replace(",", ".")
        draw_text(screen, f"{nt.device or 'startet ...'} · Lauf {nt.task_done}/{nt.task_total} · "
                          f"Population {nt.population} · Echtzeit {elapsed / 60:.1f} min · x{speed} Echtzeit",
                  f.tiny, GREY, (top.x + 14, top.y + 84), shadow=False)
        prog = (nt.generation + nt.task_done / max(1, nt.task_total)) / max(1, nt.target)
        if nt.saved_path:
            prog = 1.0
        pygame.draw.rect(screen, (45, 45, 52), (top.x + 14, top.y + 116, top.w - 28, 12), border_radius=4)
        pygame.draw.rect(screen, (40, 110, 200), (top.x + 14, top.y + 116, (top.w - 28) * min(1.0, prog), 12),
                         border_radius=4)

        lg = pygame.Rect(16, 176, 1248, 310)
        draw_panel(screen, lg, PANEL, 230)
        draw_text(screen, "PROTOKOLL", f.tiny, GREY, (lg.x + 14, lg.y + 8), shadow=False)
        lines = [chunk for line in nt.log for chunk in _chunks(line, 150)][-15:]
        for i, chunk in enumerate(lines):
            draw_text(screen, chunk, f.tiny, (210, 210, 215), (lg.x + 14, lg.y + 28 + i * 18), shadow=False)
        self._draw_chart(screen, pygame.Rect(16, 498, 1248, 206), nt.history)

        if nt.done:
            shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 170))
            screen.blit(shade, (0, 0))
            title = "TRAINING ABGESCHLOSSEN" if nt.saved_path else "C-TRAINER BEENDET"
            draw_text(screen, title, f.big, WHITE, (SCREEN_WIDTH // 2, 290), anchor="center")
            sub = f"Gespeichert: {nt.saved_path}" if nt.saved_path else (nt.log[-1] if nt.log else "")
            draw_text(screen, sub, f.small, GREY, (SCREEN_WIDTH // 2, 340), anchor="center")
            draw_text(screen, "ENTER: zurück zum Menü (neue Gehirne werden sofort verwendet)" if nt.saved_path
                      else "ENTER: zurück zum Menü", f.medium, CYAN, (SCREEN_WIDTH // 2, 390), anchor="center")
        else:
            draw_text(screen, "ESC pausieren - jede fertige Generation ist gespeichert, START setzt später fort",
                      f.tiny, GREY, (SCREEN_WIDTH - 20, SCREEN_HEIGHT - 8), anchor="bottomright")

    def _draw_chart(self, screen: pygame.Surface, rect: pygame.Rect,
                    hist: list[dict[str, float]] | None = None) -> None:
        f = self.game.fonts
        if hist is None:
            assert self.trainer is not None
            hist = self.trainer.history
        draw_panel(screen, rect, PANEL, 230)
        draw_text(screen, "FITNESS PRO GENERATION", f.tiny, GREY, (rect.x + 12, rect.y + 8), shadow=False)
        draw_text(screen, "beste", f.tiny, YELLOW, (rect.right - 110, rect.y + 8), shadow=False)
        draw_text(screen, "Durchschnitt", f.tiny, (90, 160, 255), (rect.right - 70, rect.y + 8), shadow=False)
        best = max(hist, key=lambda h: h["best"]) if hist else None
        best_mean = max(hist, key=lambda h: h["mean"]) if hist else None
        # the records so far, always in view
        x = rect.x + 12
        stats = [("BESTE", f"{best['best']:.0f}  (Gen {best['gen']})" if best else "-", YELLOW),
                 ("BESTER Ø", f"{best_mean['mean']:.0f}  (Gen {best_mean['gen']})" if best_mean else "-",
                  (90, 160, 255)),
                 ("LETZTE GEN", f"{hist[-1]['best']:.0f} / Ø {hist[-1]['mean']:.0f}" if hist else "-", WHITE)]
        for label, value, col in stats:
            draw_text(screen, label, f.tiny, GREY, (x, rect.y + 26), shadow=False)
            r = draw_text(screen, value, f.medium, col, (x + f.tiny.size(tr(label))[0] + 8, rect.y + 22),
                          shadow=False)
            x = r.right + 26
        if len(hist) < 2:
            draw_text(screen, "Kurve erscheint nach der 2. Generation", f.small, GREY, rect.move(0, 14).center,
                      anchor="center")
            return
        area = rect.inflate(-40, -76).move(8, 22)
        lo = min(min(h["mean"] for h in hist), 0.0)
        hi = max(h["best"] for h in hist)
        span = max(1.0, hi - lo)
        pygame.draw.line(screen, (60, 60, 70), area.bottomleft, area.bottomright)
        for key, col in (("mean", (90, 160, 255)), ("best", YELLOW)):
            pts = [(area.x + area.w * i / (len(hist) - 1), area.bottom - area.h * (h[key] - lo) / span)
                   for i, h in enumerate(hist)]
            pygame.draw.lines(screen, col, False, pts, 2)
        # dashed line at the best result so far
        by = area.bottom - area.h * (best["best"] - lo) / span
        for dx in range(0, area.w, 14):
            pygame.draw.line(screen, (150, 130, 40), (area.x + dx, by), (area.x + min(area.w, dx + 7), by))
        draw_text(screen, f"{hi:.0f}", f.tiny, GREY, (rect.x + 6, area.y - 4), shadow=False)
        draw_text(screen, f"{lo:.0f}", f.tiny, GREY, (rect.x + 6, area.bottom - 10), shadow=False)


def _chunks(text: str, width: int) -> list[str]:
    return [text[i:i + width] for i in range(0, len(text), width)] or [""]
