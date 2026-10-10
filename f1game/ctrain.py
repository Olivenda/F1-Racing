# Copyright Olivenda (Oliver Petz) 2026
"""Bridge to the native trainer (ctrain/f1train.exe): exports the tracks and the reward styles into
data/train_data.bin, builds the trainer with gcc when needed and runs it as a child process for the UI.

The trainer saves its state after every generation (data/brains/<mode>.ctrain.state), so it can be stopped at
any time and continues where it left off on the next start."""

from __future__ import annotations

import queue
import shutil
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Sequence

from .car_setup import recommended
from .profiles import BRAIN_DIR, DATA_DIR
from .sensors import INPUT_NAMES, LOOKAHEAD, N_INPUTS, N_OUTPUTS, RADAR_RANGE
from .track import TRACK_DEFS, Track

ROOT = Path(__file__).resolve().parent.parent
CTRAIN_DIR = ROOT / "ctrain"
EXE = CTRAIN_DIR / ("f1train.exe" if sys.platform == "win32" else "f1train")
DATA_FILE = DATA_DIR / "train_data.bin"
FORMAT_VERSION = 1
SETUP_FIELDS = ("grip", "drag", "engine", "rev_limit", "brake", "steer_rate", "turn", "slip", "brake_slip",
                "brake_turn", "grass_grip")


def _str(out: bytearray, text: str) -> None:
    raw = text.encode("utf-8")
    out += struct.pack("<I", len(raw)) + raw


def export_training_data(tracks: Sequence[Track] | None = None, path: Path = DATA_FILE) -> Path:
    """Everything the native trainer needs to know about the game: network shape, input names, reward styles and
    the track geometry with each track's recommended setup."""
    from .training import NETWORK_SIZES, REWARD_STYLES      # late: training imports pygame-heavy modules

    assert NETWORK_SIZES[0] == N_INPUTS and NETWORK_SIZES[-1] == N_OUTPUTS and len(NETWORK_SIZES) == 4
    assert LOOKAHEAD == (50.0, 110.0, 190.0, 290.0, 420.0, 580.0) and RADAR_RANGE == 280.0
    tracks = list(tracks) if tracks is not None else [Track(d) for d in TRACK_DEFS]
    out = bytearray(b"F1TD")
    out += struct.pack("<I", FORMAT_VERSION)
    out += struct.pack("<4I", *NETWORK_SIZES)
    out += struct.pack("<I", len(INPUT_NAMES))
    for name in INPUT_NAMES:
        _str(out, name)
    out += struct.pack("<I", len(REWARD_STYLES))
    for st in REWARD_STYLES.values():
        _str(out, st.key)
        _str(out, st.title)
        _str(out, st.description)
        out += struct.pack("<4d", st.w_wall, st.w_car, st.w_gain, st.w_tailgate)
    out += struct.pack("<I", len(tracks))
    for t in tracks:
        t.ensure_geometry()
        n = t.n
        lap = sum((t.racing_line[(i + 1) % n] - t.racing_line[i]).length() / max(30.0, t.max_speed[i])
                  for i in range(n))
        sf = recommended(t).factors()
        _str(out, t.definition.key)
        out += struct.pack("<I", n)
        out += struct.pack("<5d", t.length, t.half_width, t.wall_limit, lap, t.length / lap)
        out += struct.pack(f"<{len(SETUP_FIELDS)}d", *(getattr(sf, f) for f in SETUP_FIELDS))
        for arr in ([p.x for p in t.center], [p.y for p in t.center], [v.x for v in t.tangents],
                    [v.y for v in t.tangents], [v.x for v in t.normals], [v.y for v in t.normals],
                    t.cum, t.line_offset):
            out += struct.pack(f"<{n}d", *arr)
        out += struct.pack(f"<{n}i", *t.aero_zone_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(bytes(out))
    tmp.replace(path)
    return path


def state_file(mode: str) -> Path:
    return BRAIN_DIR / f"{mode}.ctrain.state"


def build(log=print) -> bool:
    """Compile the trainer with gcc (MSYS2/MinGW or any gcc >= 15 for #embed). True when the exe is ready."""
    sources = [CTRAIN_DIR / "f1train.c", CTRAIN_DIR / "sim.h"]
    if EXE.exists() and all(EXE.stat().st_mtime >= s.stat().st_mtime for s in sources):
        return True
    gcc = shutil.which("gcc")
    if gcc is None:
        log("gcc nicht gefunden - ctrain/build.bat mit MSYS2 (ucrt64) ausführen.")
        return False
    cmd = [gcc, "-std=gnu23", "-O3", "-march=native", "-ffast-math", "-o", str(EXE), "f1train.c", "-static"]
    log("Baue den C-Trainer: " + " ".join(cmd[1:]))
    res = subprocess.run(cmd, cwd=CTRAIN_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        log((res.stderr or res.stdout).strip()[-600:])
        return False
    return True


_gpus: list[tuple[int, int, str]] | None = None


def list_gpus(refresh: bool = False) -> list[tuple[int, int, str]]:
    """The OpenCL GPUs the C trainer can use: (number, compute units, name). Asked once and remembered - an
    empty answer (trainer missing or an old build) is asked again on the next refresh."""
    global _gpus
    if _gpus is None or (refresh and not _gpus):
        _gpus = []
        if EXE.exists():
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                out = subprocess.run([str(EXE), "x", "--list-gpus"], capture_output=True, text=True, timeout=15,
                                     encoding="utf-8", errors="replace", creationflags=flags).stdout
            except (OSError, subprocess.SubprocessError):
                out = ""
            for line in out.splitlines():
                parts = line.split(maxsplit=3)
                if len(parts) == 4 and parts[0] == "@GPU" and parts[1].isdigit() and parts[2].isdigit():
                    _gpus.append((int(parts[1]), int(parts[2]), parts[3].strip()))
    return _gpus


class NativeTraining:
    """The C trainer as a child process; stdout lines are parsed for the UI ('@'-lines carry progress)."""

    def __init__(self, mode: str, generations: int, population: int, device: str = "auto",
                 fresh: bool = False, gpu: str = "best") -> None:
        self.mode = mode
        self.target = generations
        self.population = population
        self.generation = 0
        self.task_done = 0
        self.task_total = 0
        self.history: list[dict[str, float]] = []
        self.log: list[str] = []
        self.device = ""
        self.using = ""                 # what is computing right now and why (auto picks the faster one)
        self.speed = 0.0                # simulated seconds per real second
        self.done = False
        self.failed = False
        self.saved_path: str | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        cmd = [str(EXE), mode, "--generations", str(generations), "--population", str(population),
               "--device", device, "--gpu", gpu, "--data", str(DATA_FILE), "--brains", str(BRAIN_DIR)]
        if fresh:
            cmd.append("--fresh")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", bufsize=1, creationflags=flags)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._lines.put(line.rstrip("\n"))
        self._lines.put("@EXIT")

    def poll(self) -> None:
        while True:
            try:
                line = self._lines.get_nowait()
            except queue.Empty:
                return
            parts = line.split()
            tag = parts[0] if parts else ""
            if tag == "@TASK" and len(parts) >= 3:
                self.task_done, self.task_total = int(parts[1]), int(parts[2])
            elif tag == "@GEN" and len(parts) >= 6:
                self.generation, self.target = int(parts[1]), int(parts[2])
                self.history.append({"gen": self.generation, "best": float(parts[3]), "mean": float(parts[4])})
                self.speed = float(parts[5])
            elif tag == "@HIST" and len(parts) >= 4:
                self.history.append({"gen": int(parts[1]), "best": float(parts[2]), "mean": float(parts[3])})
                self.generation = int(parts[1])
            elif tag == "@USING":
                self.using = line[len("@USING "):]
                self.log.append("Rechnet jetzt auf: " + self.using)
            elif tag == "@DEVICE":
                self.device = line[len("@DEVICE "):]
            elif tag == "@DONE":
                self.saved_path = line[len("@DONE "):]
                self.done = True
            elif tag == "@EXIT":
                if not self.done:
                    self.failed = True
                    self.done = True
            elif not tag.startswith("@"):
                self.log.append(line)
                del self.log[:-200]

    def stop(self) -> None:
        """Quit now - the last finished generation is already saved."""
        if self.proc.poll() is None:
            self.proc.terminate()
