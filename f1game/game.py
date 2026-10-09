# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import gc
from dataclasses import replace
import time
from typing import Callable, Protocol

import pygame

from .car_setup import CarSetup, load_setups, recommended, save_setups
from .career import Career, migrate_legacy
from .controls import Controls
from .i18n import set_language, tr
from .records import Records
from .championship import Championship
from .garage import GarageScreen
from .hud import HUD, Fonts
from .profiles import DATA_DIR, BrainLibrary, Team, load_drivers, load_teams, player_profile
from .tyres import ALL_COMPOUNDS
from .screens import AnalysisScreen, ChampionshipScreen, MainMenu, PodiumScreen, ResultsScreen, SettingsScreen, SetupScreen
from .sessions import PracticeSession, QualifyingSession, RaceSession, Session, WeekendConfig
from .settings import FPS, GREY, MAX_FRAME_DT, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE
from .track import TRACK_DEFS, Track
from .sound import SoundSystem
from .training_screen import TrainingScreen
from .user_settings import UserSettings
from .utils import clear_render_caches, draw_panel, draw_text, vertical_gradient


class GameState(Protocol):
    def handle_event(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, screen: pygame.Surface) -> None: ...


class Game:

    def __init__(self) -> None:
        pygame.mixer.pre_init(22050, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption("Gulivers Gieles F1 Game")
        self.settings = UserSettings.load()
        set_language(self.settings.language)
        self.sound = SoundSystem(self.settings.sound)
        self.controls = Controls()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.apply_display()
        self.clock = pygame.time.Clock()
        self.fonts = Fonts()
        self.hud = HUD(self.fonts)
        self.tracks: dict[str, Track] = {d.key: Track(d) for d in TRACK_DEFS}
        self.menu_choice: dict[str, int] = {"track": 0, "mode": 0, "laps": 8, "diff": 1, "opponents": 21,
                                            "team": 4, "tyre": 1}
        self.player_name = self.settings.player_name
        self.brains = BrainLibrary()
        self.teams = load_teams()
        self.drivers = load_drivers(self.brains, self.teams)
        self.menu_choice["team"] = min(self.menu_choice["team"], max(0, len(self.teams) - 1))
        self.config: WeekendConfig | None = None
        self.championship: Championship | None = Championship.load()
        self.setups: dict[str, CarSetup] = load_setups()
        migrate_legacy()
        self.career: Career | None = None
        self.records = Records()
        self.running = True
        self.toast: tuple[str, int] | None = None
        self.state: GameState = MainMenu(self)

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(self.settings.fps or FPS) / 1000.0, MAX_FRAME_DT)
            in_session = isinstance(self.state, Session)
            events = []
            for event in pygame.event.get():
                events.append(event)
                if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYHATMOTION, pygame.JOYDEVICEADDED,
                                  pygame.JOYDEVICEREMOVED):
                    events.extend(self.controls.translate(event, in_session))
            events.extend(self.controls.menu_stick(dt, in_session))
            if not in_session or self.state.paused or self.state.finished or                     not any(p.autopilot is None for p in self.state.players):
                self.controls.ffb_idle()
            for event in events:
                if in_session and event.type == pygame.KEYDOWN and not getattr(event, "from_joystick", False):
                    # rebound keyboard actions arrive as the keys the session knows
                    mapped = self.controls.session_key(event.key)
                    if mapped is None:
                        continue
                    if mapped != event.key:
                        event = pygame.event.Event(pygame.KEYDOWN, key=mapped, mod=event.mod, unicode="",
                                                   scancode=0)
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F12:
                    self.screenshot()
                else:
                    if event.type == pygame.KEYDOWN and not isinstance(self.state, Session):
                        if event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
                            self.sound.ui("click")
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            self.sound.ui("confirm")
                        elif event.key == pygame.K_ESCAPE:
                            self.sound.ui("back")
                    self.state.handle_event(event)
            if isinstance(self.state, Session) and self.state.config.instant:
                self._simulate_instant(self.state)
            else:
                self.state.update(dt)
                self.state.draw(self.screen)
            self._draw_toast()
            pygame.display.flip()
        pygame.quit()

    def screenshot(self) -> None:
        folder = DATA_DIR / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"f1_{time.strftime('%Y%m%d_%H%M%S')}.png"
        pygame.image.save(self.screen, str(path))
        self.sound.ui("confirm")
        self.toast = (f"Screenshot gespeichert: data/screenshots/{path.name}", pygame.time.get_ticks() + 2500)

    def _draw_toast(self) -> None:
        if self.toast is None:
            return
        text, until = self.toast
        if pygame.time.get_ticks() > until:
            self.toast = None
            return
        f = self.fonts.small_bold
        w = f.size(tr(text))[0] + 40
        rect = pygame.Rect((SCREEN_WIDTH - w) // 2, 14, w, 36)
        draw_panel(self.screen, rect, (20, 22, 30), 230, border=(255, 200, 40))
        draw_text(self.screen, text, f, WHITE, rect.center, anchor="center", shadow=False)

    def _simulate_instant(self, session: Session) -> None:
        session.time_scale = 8.0
        start = pygame.time.get_ticks()
        while self.state is session and pygame.time.get_ticks() - start < 70:
            session.update(1 / 60)
        if self.state is not session:
            return
        self.sound.stop()
        f = self.fonts
        self.screen.blit(vertical_gradient((SCREEN_WIDTH, SCREEN_HEIGHT), (24, 26, 34), (8, 8, 12)), (0, 0))
        draw_text(self.screen, f"{session.title.upper()} WIRD SIMULIERT", f.big, WHITE,
                  (SCREEN_WIDTH // 2, 200), anchor="center")
        draw_text(self.screen, session.track.name, f.medium, GREY, (SCREEN_WIDTH // 2, 250), anchor="center")
        order = session.standings()
        total = getattr(session, "total_laps", 3)
        lead = order[0]
        done = min(1.0, (lead.laps_done + max(0.0, lead.distance % session.track.length) / session.track.length)
                   / max(1, total))
        bar = pygame.Rect(SCREEN_WIDTH // 2 - 300, 290, 600, 14)
        pygame.draw.rect(self.screen, (50, 52, 60), bar, border_radius=7)
        pygame.draw.rect(self.screen, (255, 200, 40), (bar.x, bar.y, int(bar.w * done), bar.h), border_radius=7)
        own = self.career.team if self.career is not None else ""
        for k, car in enumerate(order[:24]):
            col_x = SCREEN_WIDTH // 2 - 520 + (k // 12) * 540
            y = 330 + (k % 12) * 26
            col = (0, 220, 255) if car.profile.team == own or car.is_player else WHITE
            draw_text(self.screen, f"{k + 1:>2}. {car.name}", f.small_bold, col, (col_x, y))
            draw_text(self.screen, car.profile.team, f.small, GREY, (col_x + 320, y))
        draw_text(self.screen, "ESC: abbrechen", f.tiny, GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 24), anchor="center")

    def go_to_menu(self) -> None:
        self.sound.stop()
        self.controls.stop_rumble()
        self.controls.assign_players(1)
        if isinstance(self.state, Session):
            self.state.save_recording()
        self.state = MainMenu(self)
        self.free_memory()

    def free_memory(self) -> None:
        for track in self.tracks.values():
            track.release_surface()
            track.wetness = 0.0
            if hasattr(track, "_pit_edges_3d"):
                del track._pit_edges_3d
        clear_render_caches()
        self.hud.clear_caches()
        gc.collect()

    def open_setup(self, spectator: bool) -> None:
        self.state = SetupScreen(self, spectator)

    def open_championship(self) -> None:
        self.state = ChampionshipScreen(self)
        self.free_memory()

    def open_career_slots(self) -> None:
        from .career_screens import CareerSlotScreen
        self.free_memory()
        self.state = CareerSlotScreen(self)

    def open_career(self) -> None:
        from .career_screens import CareerHub, CareerSlotScreen, OfferScreen, PressScreen
        self.free_memory()
        if self.career is None:
            self.state = CareerSlotScreen(self)
        elif self.career.press:
            self.state = PressScreen(self)
        elif self.career.needs_contract or (self.career.kind == "driver" and self.career.offers
                                            and not self.career.season_over and not self.career.team):
            self.state = OfferScreen(self)
        else:
            self.state = CareerHub(self)

    def start_career_round(self, instant: bool = False) -> None:
        career = self.career
        if career is None or not career.ready_to_race()[0]:
            return
        champ = career.championship
        st = self.settings
        player = career.player()
        cfg = WeekendConfig(track_key=champ.next_track or champ.rounds[0], mode=career.format,
                            race_laps=career.laps, difficulty_name=career.difficulty,
                            ai_profiles=career.field_profiles(), player=player,
                            start_compound=ALL_COMPOUNDS[self.menu_choice["tyre"]], assists=st.assists,
                            view3d=st.view3d, damage=st.damage, tyre_wear_factor=st.tyre_wear_factor,
                            auto_camera=st.auto_camera, championship=champ,
                            pit_stop_times=career.pit_stop_times(), instant=instant and player is None,
                            rival=career.rival if career.kind == "driver" else None, career=True,
                            focus_team=career.team if career.kind == "team" else None,
                            reliability=career.reliability_map(), safety_car=st.safety_car,
                            weather=st.weather, gearbox=st.gearbox,
                            objective=career.weekend_goal.get("text") if career.kind == "driver" else None)
        self.config = cfg
        first = {"weekend": "practice", "practice": "practice", "qualifying": "qualifying", "race": "race"}[cfg.mode]
        self.start_session(first)

    def start_championship_round(self) -> None:
        champ = self.championship
        if champ is None or champ.finished:
            return
        team_idx = next((k for k, t in enumerate(self.teams) if t.name == champ.team), self.menu_choice["team"])
        self.menu_choice["team"] = team_idx
        self.start_weekend(champ.next_track, champ.format, champ.laps, champ.difficulty, champ.field_size,
                           spectator=champ.spectator, championship=champ)

    def setup_for(self, track: Track) -> CarSetup:
        return self.setups.get(track.definition.key) or recommended(track)

    def save_setups(self) -> None:
        save_setups(self.setups)

    def open_garage(self, track_key: str, team: Team | None, on_done: Callable[[], None]) -> None:
        self.state = GarageScreen(self, self.tracks[track_key], team, on_done)

    def open_settings(self) -> None:
        self.state = SettingsScreen(self)

    def apply_display(self) -> None:
        flags = (pygame.SCALED | pygame.FULLSCREEN) if self.settings.fullscreen else 0
        try:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)
        except pygame.error:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))

    def apply_player_name(self) -> None:
        self.player_name = self.settings.player_name

    def open_training(self) -> None:
        self.state = TrainingScreen(self)

    def reload_brains(self) -> None:
        self.brains.reload()
        self.drivers = load_drivers(self.brains, self.teams)

    def start_weekend(self, track_key: str, mode: str, laps: int, difficulty: str, opponents: int,
                      spectator: bool = False, championship: Championship | None = None) -> None:
        c = self.menu_choice
        st = self.settings
        team = self.teams[c["team"]] if self.teams else None
        profiles = self.field_preview(spectator, opponents)
        name = championship.player_name if championship is not None else st.player_name
        player = None if spectator else player_profile(team, name)
        player2 = None
        if player is not None and championship is None and c.get("players", 1) == 2:
            # player 2 drives the team-mate's car
            player2 = replace(player_profile(team, "Spieler 2"), short="SP2", helmet=(255, 200, 40))
            player = replace(player, short="SP1")
            profiles = profiles[:max(1, len(profiles) - 1)]
        self.config = WeekendConfig(track_key=track_key, mode=mode, race_laps=laps, difficulty_name=difficulty,
                                    ai_profiles=profiles, player=player,
                                    start_compound=ALL_COMPOUNDS[c["tyre"]], assists=st.assists,
                                    view3d=st.view3d, damage=st.damage, tyre_wear_factor=st.tyre_wear_factor,
                                    auto_camera=st.auto_camera, championship=championship,
                                    safety_car=st.safety_car, weather=st.weather, player2=player2,
                                    gearbox=st.gearbox)
        first = {"weekend": "practice", "practice": "practice", "qualifying": "qualifying", "race": "race"}[mode]
        self.start_session(first)

    def field_preview(self, spectator: bool, opponents: int) -> list:
        team = self.teams[self.menu_choice["team"]] if self.teams else None
        pool = self.drivers if spectator or team is None else \
            [d for d in self.drivers if not (d.pool and d.team == team.name)]
        return pool[:opponents]

    def start_session(self, kind: str) -> None:
        assert self.config is not None
        player = self.config.player
        self.player_name = player.name if player is not None else self.settings.player_name
        self._loading_screen(kind)
        track = self.tracks[self.config.track_key]
        for other in self.tracks.values():
            if other is not track:
                other.release_surface()
        cls: type[Session] = {"practice": PracticeSession, "qualifying": QualifyingSession,
                              "race": RaceSession}[kind]
        self.state = cls(self, track, self.config)

    def _loading_screen(self, kind: str) -> None:
        assert self.config is not None
        names = {"practice": "Freies Training", "qualifying": "Qualifying", "race": "Rennen"}
        self.screen.blit(vertical_gradient((SCREEN_WIDTH, SCREEN_HEIGHT), (24, 26, 34), (8, 8, 12)), (0, 0))
        title = names[kind].upper()
        champ = self.config.championship
        if champ is not None:
            title = f"{'KARRIERE' if self.config.career else 'WM'}-LAUF {champ.round + 1}/{len(champ.rounds)}  ·  {title}"
        draw_text(self.screen, title, self.fonts.big, WHITE,
                  (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20), anchor="center")
        draw_text(self.screen, f"{self.tracks[self.config.track_key].name} wird vorbereitet ...", self.fonts.medium,
                  GREY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30), anchor="center")
        pygame.display.flip()

    def session_finished(self, session: Session) -> None:
        self.sound.stop()
        cfg = session.config
        track = session.track.name
        session.save_recording()
        if isinstance(session, PracticeSession):
            if cfg.mode == "weekend":
                label, nxt = "weiter zum Qualifying", lambda: self.start_session("qualifying")
            else:
                label, nxt = "zurück zum Menü", self.go_to_menu
            player = session.player
            if player is not None and player.lap_log:
                from .practice_analysis import PracticeAnalysisScreen
                after, after_label = nxt, label

                def nxt() -> None:
                    self.state = PracticeAnalysisScreen(self, player, cfg.race_laps, after, after_label)
                label = "zur Datenanalyse"
            self.state = ResultsScreen(self, "Ergebnis Freies Training", f"{track} · nach Bestzeit",
                                       ["POS", "FAHRER", "TEAM", "BESTZEIT", "ABSTAND", "RUNDEN"],
                                       session.results_rows(), self.player_name, label, nxt)
        elif isinstance(session, QualifyingSession):
            cfg.grid = [c.name for c in session.standings()]
            if cfg.career and self.career is not None:
                self.career.note_quali(cfg.grid)
            self.state = ResultsScreen(self, "Startaufstellung", f"Qualifying {track} · Bestzeit aus 3 Runden",
                                       ["POS", "FAHRER", "TEAM", "BESTZEIT", "ABSTAND", "RUNDENZEITEN"],
                                       session.results_rows(), self.player_name, "zum Rennen",
                                       lambda: self.start_session("race"))
        elif isinstance(session, RaceSession):
            disqualified = session.scrutineering()
            if disqualified:
                names = ", ".join(c.short for c in disqualified)
                self.toast = (f"DISQUALIFIKATION (Planke): {names}", pygame.time.get_ticks() + 6000)
            if cfg.career and self.career is not None:
                result = cfg.championship.award(session)
                self.career.after_race(session, result)
                nxt, label = self.open_career, "zur Karriere"
            elif cfg.championship is not None:
                cfg.championship.award(session)
                nxt, label = self.open_championship, "zur WM-Wertung"
            else:
                nxt, label = self.go_to_menu, "zurück zum Hauptmenü"

            def analysis() -> None:
                self.state = AnalysisScreen(self, session, nxt, label)
            self.state = PodiumScreen(self, session, analysis, "zur Rennanalyse")
