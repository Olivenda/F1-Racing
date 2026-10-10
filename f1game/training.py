# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Callable, Sequence

import pygame

from .ai_car import AI_Car
from .car_setup import recommended
from .neural import NeuralNetwork
from .physics import handle_collisions
from .profiles import RECORDING_DIR, BrainLibrary, DriverProfile
from .sensors import INPUT_NAMES, N_INPUTS, N_OUTPUTS
from .settings import PHYSICS_STEP
from .stewards import TL_MARGIN, TL_MIN_TIME
from .track import Track

NETWORK_SIZES: list[int] = [N_INPUTS, 12, 8, N_OUTPUTS]
RADAR_FRONT_CENTER = INPUT_NAMES.index("Radar VM")
CRASH_PENALTY: float = 400.0
TRACK_LIMIT_PENALTY: float = 250.0
OFFTRACK_PENALTY: float = 150.0


@dataclass(frozen=True)
class RewardStyle:
    key: str
    title: str
    description: str
    w_wall: float
    w_car: float
    w_gain: float
    w_tailgate: float


REWARD_STYLES: dict[str, RewardStyle] = {
    "base": RewardStyle("base", "Basis (Fahren lernen)",
                        "Solo von Null: weit fahren, Mauern und Rasen meiden.", 0.6, 0.0, 0.0, 0.0),
    "balanced": RewardStyle("balanced", "Ausgewogen",
                            "Verkehr: Positionen gewinnen, Kontakt vermeiden.", 0.6, 1.0, 250.0, 0.0),
    "aggressive": RewardStyle("aggressive", "Aggressiv",
                              "Verkehr: Positionen zählen viel, Kontakt kaum bestraft, Druck lohnt sich.",
                              0.5, 0.25, 600.0, 25.0),
    "cautious": RewardStyle("cautious", "Vorsichtig",
                            "Verkehr: Kontakt teuer, dichtes Auffahren bestraft.", 0.7, 3.0, 120.0, -40.0),
    "clone": RewardStyle("clone", "Klon (deine Daten)",
                         "Lernt deinen Fahrstil aus Aufnahmen, danach kurz verfeinert.", 0.6, 0.0, 0.0, 0.0),
}
TRAFFIC_STYLES = ("balanced", "aggressive", "cautious")


def _genome_color(k: int) -> tuple[int, int, int]:
    c = pygame.Color(0)
    c.hsva = ((k * 47) % 360, 75, 100, 100)
    return c.r, c.g, c.b


class Evaluation:

    CHECK_INTERVAL = 1.5
    MIN_PROGRESS = 60.0

    def __init__(self, track: Track, nets: Sequence[NeuralNetwork], duration: float, traffic: bool,
                 start_s: float, stop_after_lap: bool = False) -> None:
        self.track = track
        self.time = 0.0
        self.duration = duration
        self.traffic = traffic
        self.stop_after_lap = stop_after_lap
        self.is_race_start_phase = False
        self.kind = "training"          # AI_Car racecraft asks the session kind
        self.cars: list[AI_Car] = []
        setup = recommended(track)
        for k, net in enumerate(nets):
            prof = DriverProfile(f"Genom {k + 1}", f"G{k + 1}", "", _genome_color(k), (255, 255, 255), "train")
            car = AI_Car(prof, track, net, marshal=False)
            car.driver.timer = 0.0
            car.apply_setup(setup)
            pos, heading = track.grid_pose(k) if traffic else track.pose_at(start_s, 0.0)
            car.place(pos, heading)
            if not traffic:
                car.collide_cars = False
                car.sees_others = False
            self.cars.append(car)
        self.start_distance = [c.distance for c in self.cars]
        self.start_rank = self._ranks()
        self.alive = [True] * len(self.cars)
        self.check_distance = list(self.start_distance)
        self.check_timer = 0.0
        self.tailgate = [0.0] * len(self.cars)
        self.tl_off = [0.0] * len(self.cars)
        self.tl_violations = [0] * len(self.cars)
        self.finished = False

    def _ranks(self) -> list[int]:
        order = sorted(range(len(self.cars)), key=lambda i: -self.cars[i].distance)
        ranks = [0] * len(self.cars)
        for r, i in enumerate(order):
            ranks[i] = r
        return ranks

    def on_lap_completed(self, car: AI_Car, lap_time: float) -> None:
        if self.stop_after_lap:
            self._kill(self.cars.index(car))

    def _kill(self, k: int) -> None:
        self.alive[k] = False
        car = self.cars[k]
        car.frozen = True
        car.retired_ghost = True

    def step(self, h: float) -> None:
        for car, alive in zip(self.cars, self.alive):
            if alive:
                car.control(h, self)
        for car in self.cars:
            car.physics_step(h)
        handle_collisions(self.cars, self.track)
        hw = self.track.half_width
        for k, car in enumerate(self.cars):
            car.update_track_state(self)
            car.update_aero(h)
            lat = abs(car.lateral)
            if self.tl_off[k] == 0.0 and lat > hw + TL_MARGIN:
                self.tl_off[k] = self.time + 1e-6
            elif self.tl_off[k] and lat < hw:
                if self.time - self.tl_off[k] >= TL_MIN_TIME:
                    self.tl_violations[k] += 1
                self.tl_off[k] = 0.0
            if self.traffic and self.alive[k] and car.driver.inputs and \
                    car.driver.inputs[RADAR_FRONT_CENTER] > 0.7:
                self.tailgate[k] += h
        self.time += h
        self.check_timer += h
        if self.check_timer >= self.CHECK_INTERVAL:
            self.check_timer = 0.0
            for k, car in enumerate(self.cars):
                if self.alive[k] and car.distance - self.check_distance[k] < self.MIN_PROGRESS:
                    self._kill(k)
                self.check_distance[k] = car.distance
        if self.time >= self.duration or not any(self.alive):
            self.finished = True

    def leader(self) -> AI_Car:
        alive = [c for c, a in zip(self.cars, self.alive) if a] or self.cars
        return max(alive, key=lambda c: c.distance)

    def fitness(self, style: RewardStyle) -> list[float]:
        end_rank = self._ranks()
        out = []
        for k, car in enumerate(self.cars):
            f = car.distance - self.start_distance[k]
            f -= style.w_wall * car.wall_impulse + OFFTRACK_PENALTY * car.grass_time + CRASH_PENALTY * car.crashes
            f -= TRACK_LIMIT_PENALTY * self.tl_violations[k]
            if self.traffic:
                f += style.w_gain * (self.start_rank[k] - end_rank[k])
                f -= style.w_car * car.car_impulse
                f += style.w_tailgate * self.tailgate[k]
            out.append(f)
        return out


class Trainer:

    SOLO_DURATION = 24.0
    SOLO_STARTS = 2
    TRAFFIC_DURATION = 40.0
    HEAT_SIZE = 11
    ELITE = 3
    BENCHMARK_CANDIDATES = 5
    CROSSOVER_RATE = 0.6
    MUTATION_RATE = 0.12

    def __init__(self, mode: str, tracks: Sequence[Track], generations: int, population: int,
                 library: BrainLibrary, seed: int | None = None, log: Callable[[str], None] | None = None,
                 warm_start: bool = False) -> None:
        self.mode = mode
        self.style = REWARD_STYLES[mode]
        self.tracks = list(tracks)
        self.target_generations = generations
        self.pop_size = population
        self.library = library
        self.rng = random.Random(seed)
        self.log = log or (lambda msg: None)
        self.traffic = mode in TRAFFIC_STYLES
        self.warm_start = warm_start and mode == "base" and library.has("base")
        self.sigma0 = 0.35 if mode == "base" and not self.warm_start else 0.08
        self.generation = 0
        self.history: list[dict[str, float]] = []
        self.checkpoints: list[dict] = []
        self.champion: NeuralNetwork | None = None
        self.clone_loss: list[float] = []
        self.done = False
        self.saved_path: str | None = None
        self.sim_time = 0.0

        self.ref_lap: dict[str, float] = {}
        self.ref_speed: dict[str, float] = {}
        for t in self.tracks:
            t.ensure_geometry()
            lap = sum((t.racing_line[(i + 1) % t.n] - t.racing_line[i]).length() / max(30.0, t.max_speed[i])
                      for i in range(t.n))
            self.ref_lap[t.definition.key] = lap
            self.ref_speed[t.definition.key] = t.length / lap
        self.population = self._initial_population()
        self.fitness = [0.0] * self.pop_size
        self.scores: list[list[float]] = [[] for _ in range(self.pop_size)]
        self.tasks: list[tuple[Track, list[int], bool, float]] = []
        self.task_total = 0
        self.current: Evaluation | None = None
        self.current_ids: list[int] = []
        self.view: Evaluation | None = None
        self.checkpoint_at = self._checkpoint_plan()
        self._plan_generation()

    def _initial_population(self) -> list[NeuralNetwork]:
        if self.mode == "base" and not self.warm_start:
            self.log(f"Neue Population: {self.pop_size} zufällige Netze {NETWORK_SIZES}")
            return [NeuralNetwork(NETWORK_SIZES, self.rng) for _ in range(self.pop_size)]
        if self.warm_start:
            self.log("Warmstart: Population aus dem vorhandenen Basis-Netz")
        seed_net = self._clone_network() if self.mode == "clone" else self.library.network("base", "final")
        pop = [seed_net]
        for _ in range(self.pop_size - 1):
            child = seed_net.copy()
            child.mutate(self.rng, 0.3, self.sigma0)
            pop.append(child)
        return pop

    def _clone_network(self) -> NeuralNetwork:
        samples: list[tuple[list[float], list[float]]] = []
        for f in sorted(RECORDING_DIR.glob("*.json")) if RECORDING_DIR.exists() else []:
            for row in json.loads(f.read_text(encoding="utf-8")).get("samples", []):
                if len(row) == N_INPUTS + N_OUTPUTS:
                    samples.append((row[:N_INPUTS], row[N_INPUTS:]))
        if len(samples) < 200:
            raise ValueError("Zu wenige Fahrdaten für einen Klon - fahre zuerst ein paar Runden "
                             "(Training/Qualifying/Rennen werden automatisch aufgezeichnet).")
        if len(samples) > 20000:
            samples = self.rng.sample(samples, 20000)
        self.log(f"Behavior Cloning auf {len(samples)} Samples ...")
        net = NeuralNetwork(NETWORK_SIZES, self.rng)
        self.clone_loss = net.train_supervised(samples, epochs=25, lr=0.01, rng=self.rng)
        self.log(f"Fehler (MSE): {self.clone_loss[0]:.3f} -> {self.clone_loss[-1]:.3f}")
        return net

    def _checkpoint_plan(self) -> dict[int, str]:
        g = self.target_generations
        plan = {g: "final"}
        if self.mode == "base":
            plan.setdefault(max(1, round(g * 0.3)), "early")
            plan.setdefault(max(1, round(g * 0.6)), "mid")
        else:
            plan.setdefault(max(1, g // 2), "mid")
        return plan

    def _plan_generation(self) -> None:
        ids = list(range(self.pop_size))
        self.tasks = []
        if self.traffic:
            for _ in range(2):
                track = self.rng.choice(self.tracks)
                self.rng.shuffle(ids)
                for i in range(0, len(ids), self.HEAT_SIZE):
                    self.tasks.append((track, ids[i:i + self.HEAT_SIZE], True, 0.0))
        else:
            for track in self.tracks:
                for _ in range(self.SOLO_STARTS):
                    self.tasks.append((track, ids, False, self.rng.uniform(0.0, track.length)))
        self.task_total = len(self.tasks)

    @property
    def task_index(self) -> int:
        return self.task_total - len(self.tasks)

    def step(self, substeps: int) -> None:
        for _ in range(substeps):
            if self.done:
                return
            if self.current is None:
                if not self.tasks:
                    self._end_generation()
                    continue
                track, ids, traffic, start_s = self.tasks.pop(0)
                duration = self.TRAFFIC_DURATION if traffic else self.SOLO_DURATION
                self.current = Evaluation(track, [self.population[i] for i in ids], duration, traffic, start_s)
                self.current_ids = ids
                self.view = self.current
            self.current.step(PHYSICS_STEP)
            self.sim_time += PHYSICS_STEP
            if self.current.finished:
                key = self.current.track.definition.key
                norm = self.ref_speed[key] * self.current.duration
                for k, f in zip(self.current_ids, self.current.fitness(self.style)):
                    self.scores[k].append(f / norm)
                self.current = None

    def _aggregate(self) -> None:
        for k, sc in enumerate(self.scores):
            if not sc:
                self.fitness[k] = -1e9
            elif self.traffic:
                self.fitness[k] = 1000.0 * sum(sc) / len(sc)
            else:
                self.fitness[k] = 1000.0 * (0.6 * sum(sc) / len(sc) + 0.4 * min(sc))

    def _end_generation(self) -> None:
        self._aggregate()
        ranked = sorted(range(self.pop_size), key=lambda i: self.fitness[i], reverse=True)
        best, mean = self.fitness[ranked[0]], sum(self.fitness) / self.pop_size
        self.champion = self.population[ranked[0]].copy()
        self.generation += 1
        self.history.append({"gen": self.generation, "best": round(best, 1), "mean": round(mean, 1)})
        self.log(f"Gen. {self.generation}/{self.target_generations} · beste Fitness {best:.0f} · "
                 f"Schnitt {mean:.0f}")
        label = self.checkpoint_at.get(self.generation)
        if label:
            self._add_checkpoint(label, [self.population[i] for i in ranked[:self.BENCHMARK_CANDIDATES]])
        if self.generation >= self.target_generations:
            self._finish()
            return
        self.population = self._evolve(ranked)
        self.fitness = [0.0] * self.pop_size
        self.scores = [[] for _ in range(self.pop_size)]
        self._plan_generation()

    def _evolve(self, ranked: list[int]) -> list[NeuralNetwork]:
        sigma = max(0.03, self.sigma0 * 0.97 ** self.generation)
        new = [self.population[i].copy() for i in ranked[:self.ELITE]]

        def tournament() -> NeuralNetwork:
            contenders = self.rng.sample(range(self.pop_size), 3)
            return self.population[max(contenders, key=lambda i: self.fitness[i])]

        while len(new) < self.pop_size:
            p1, p2 = tournament(), tournament()
            child = NeuralNetwork.crossover(p1, p2, self.rng) if self.rng.random() < self.CROSSOVER_RATE \
                else p1.copy()
            child.mutate(self.rng, self.MUTATION_RATE, sigma)
            new.append(child)
        return new

    def benchmark(self, net: NeuralNetwork) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        for track in self.tracks:
            ev = Evaluation(track, [net], duration=240.0, traffic=False, start_s=-30.0, stop_after_lap=True)
            while not ev.finished:
                ev.step(PHYSICS_STEP)
            result[track.definition.key] = round(ev.cars[0].best_lap, 3) if ev.cars[0].best_lap else None
        return result

    def _add_checkpoint(self, label: str, candidates: list[NeuralNetwork]) -> None:
        best_net, best_bench, best_key = candidates[0], {}, (-1, 0.0)
        for net in candidates:
            bench = self.benchmark(net)
            laps = [v for v in bench.values() if v]
            key = (len(laps), -sum(v / self.ref_lap[k] for k, v in bench.items() if v))
            if key > best_key:
                best_net, best_bench, best_key = net, bench, key
        self.champion = best_net.copy()
        self.log(f"Checkpoint '{label}' (Gen. {self.generation}) Rundenzeiten: "
                 + ", ".join(f"{k} {v:.2f}s" if v else f"{k} --" for k, v in best_bench.items()))
        self.checkpoints.append({"label": label, "generation": self.generation,
                                 "fitness": self.history[-1]["best"], "benchmark": best_bench,
                                 "network": self.champion.to_dict()})

    def _finish(self) -> None:
        parent = None
        if self.mode in TRAFFIC_STYLES:
            base = self.library.data("base")
            parent = {"style": "base", "generations": base.get("generations") if base else None}
        data = {"style": self.mode, "title": self.style.title, "description": self.style.description,
                "reward": {"wall": self.style.w_wall, "car": self.style.w_car, "gain": self.style.w_gain,
                           "tailgate": self.style.w_tailgate},
                "sizes": NETWORK_SIZES, "inputs": INPUT_NAMES, "population": self.pop_size,
                "generations": self.generation, "trained_on": [t.definition.key for t in self.tracks],
                "parent": parent, "clone_loss": [round(v, 4) for v in self.clone_loss],
                "history": self.history, "checkpoints": self.checkpoints}
        self.saved_path = str(self.library.save(self.mode, data))
        self.log(f"Gespeichert: {self.saved_path}")
        self.done = True
