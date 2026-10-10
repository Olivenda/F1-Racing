# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import argparse
import os
import subprocess
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


def run_native(args: argparse.Namespace) -> None:
    """The C trainer (ctrain/f1train.exe): same training, ~1000x faster, GPU for big populations, saves after
    every generation and continues there after Ctrl+C."""
    from f1game import ctrain
    print(f"Streckendaten: {ctrain.export_training_data()}")
    if not ctrain.build():
        raise SystemExit(1)
    cmd = [str(ctrain.EXE), args.mode, "--population", str(args.population), "--device", args.device,
           "--data", str(ctrain.DATA_FILE), "--brains", str(ctrain.BRAIN_DIR)]
    if args.generations:
        cmd += ["--generations", str(args.generations)]
    if args.seed is not None:
        cmd += ["--seed", str(args.seed)]
    cmd += ["--warm"] if args.warm else []
    cmd += ["--fresh"] if args.fresh else []
    try:
        raise SystemExit(subprocess.call(cmd))
    except KeyboardInterrupt:
        raise SystemExit(130)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", nargs="?", choices=list(REWARD_STYLES) + ["all"])
    parser.add_argument("--generations", type=int)
    parser.add_argument("--population", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--warm", action="store_true",
                        help="Basis-Netz vom vorhandenen Stand weitertrainieren (z. B. nach neuen Strecken)")
    parser.add_argument("--c", action="store_true",
                        help="C-Trainer (ctrain/f1train.exe) statt Python: viel schneller, GPU, Zwischenstand je Generation")
    parser.add_argument("--device", default="auto", choices=("auto", "cpu", "gpu"), help="nur mit --c")
    parser.add_argument("--fresh", action="store_true", help="nur mit --c: gespeicherten Zwischenstand verwerfen")
    parser.add_argument("--export", action="store_true",
                        help="nur data/train_data.bin für den C-Trainer schreiben")
    args = parser.parse_args()
    pygame.init()
    if args.export:
        from f1game.ctrain import export_training_data
        print(export_training_data())
        return
    if args.mode is None:
        parser.error("mode fehlt")
    if args.c:
        args.population = args.population or 400
        run_native(args)
    args.population = args.population or 40
    modes = ["base", *TRAFFIC_STYLES] if args.mode == "all" else [args.mode]
    for mode in modes:
        gens = args.generations
        if args.warm and mode == "base" and gens is None:
            gens = 30
        run(mode, gens, args.population, args.seed, warm=args.warm)


if __name__ == "__main__":
    main()
