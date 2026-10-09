# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import argparse
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from f1game.profiles import BrainLibrary
from f1game.track import TRACK_DEFS, Track
from f1game.training import REWARD_STYLES, TRAFFIC_STYLES, Trainer

DEFAULT_GENERATIONS = {"base": 60, "clone": 15, **{s: 20 for s in TRAFFIC_STYLES}}


def run(mode: str, generations: int | None, population: int, seed: int | None, warm: bool = False) -> None:
    library = BrainLibrary()
    tracks = [Track(d) for d in TRACK_DEFS]
    gens = generations or DEFAULT_GENERATIONS[mode]
    print(f"\n=== Training '{mode}': {gens} Generationen, Population {population} ===")
    t0 = time.time()
    trainer = Trainer(mode, tracks, gens, population, library, seed=seed, log=print, warm_start=warm)
    while not trainer.done:
        trainer.step(2000)
    print(f"=== fertig in {time.time() - t0:.0f}s (Simulationszeit {trainer.sim_time / 60:.0f} min) ===")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=list(REWARD_STYLES) + ["all"])
    parser.add_argument("--generations", type=int)
    parser.add_argument("--population", type=int, default=40)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--warm", action="store_true",
                        help="Basis-Netz vom vorhandenen Stand weitertrainieren (z. B. nach neuen Strecken)")
    args = parser.parse_args()
    pygame.init()
    modes = ["base", *TRAFFIC_STYLES] if args.mode == "all" else [args.mode]
    for mode in modes:
        gens = args.generations
        if args.warm and mode == "base" and gens is None:
            gens = 30
        run(mode, gens, args.population, args.seed, warm=args.warm)


if __name__ == "__main__":
    main()
