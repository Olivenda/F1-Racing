# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
import time
from typing import Any

from .profiles import DATA_DIR

RECORDS_FILE = DATA_DIR / "records.json"


class Records:
    def __init__(self) -> None:
        try:
            raw = json.loads(RECORDS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        self.tracks: dict[str, dict[str, Any]] = raw.get("tracks", {})
        self.player: dict[str, dict[str, Any]] = raw.get("player", {})

    def check(self, track: str, lap: float, driver: str, team: str, is_player: bool) -> str | None:
        result = None
        stamp = time.strftime("%d.%m.%Y")
        if is_player and (track not in self.player or lap < self.player[track]["time"]):
            self.player[track] = {"time": round(lap, 3), "team": team, "date": stamp}
            result = "personal"
        if track not in self.tracks or lap < self.tracks[track]["time"]:
            self.tracks[track] = {"time": round(lap, 3), "driver": driver, "team": team, "date": stamp}
            result = "track"
        if result:
            self.save()
        return result

    def save(self) -> None:
        RECORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECORDS_FILE.write_text(json.dumps({"tracks": self.tracks, "player": self.player}, indent=1,
                                           ensure_ascii=False), encoding="utf-8")
