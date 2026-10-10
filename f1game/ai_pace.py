# Copyright Olivenda (Oliver Petz) 2026
"""How fast the AI really drives at every point of a track - the reference for easier difficulty levels.

The trained nets corner at the limit whatever their engine power, so less engine alone hardly slows them down.
Easier levels cap the AI at a share of this reference speed instead. It ships pre-recorded in
data/ai_pace.json (full-strength AI races) and keeps learning in memory: every AI car that is not being held
back adds its speed, so retrained (faster) brains raise the reference on their own."""

from __future__ import annotations

import json

from .profiles import DATA_DIR

PACE_FILE = DATA_DIR / "ai_pace.json"
_profiles: dict[str, list[float]] | None = None


def _load() -> dict[str, list[float]]:
    global _profiles
    if _profiles is None:
        try:
            raw = json.loads(PACE_FILE.read_text(encoding="utf-8"))
            _profiles = {k: [float(v) for v in vals] for k, vals in raw.items() if isinstance(vals, list)}
        except (OSError, ValueError, TypeError):
            _profiles = {}
    return _profiles


def profile(track_key: str, n: int) -> list[float]:
    """Reference speed per waypoint (0 = not known yet). Shared by all cars on that track."""
    profiles = _load()
    ref = profiles.get(track_key)
    if ref is None or len(ref) != n:
        ref = [0.0] * n
        profiles[track_key] = ref
    return ref


def save() -> None:
    PACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PACE_FILE.write_text(json.dumps({k: [round(v, 1) for v in vals] for k, vals in _load().items()}),
                         encoding="utf-8")
