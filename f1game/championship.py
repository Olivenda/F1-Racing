# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from .profiles import DATA_DIR

if TYPE_CHECKING:
    from .sessions import RaceSession

CHAMPIONSHIP_FILE = DATA_DIR / "championship.json"
POINTS: list[int] = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
FASTEST_LAP_POINT = 1
FORMATS: list[tuple[str, str]] = [
    ("weekend", "Training + Qualifying + Rennen"),
    ("qualifying", "Qualifying + Rennen"),
    ("race", "Nur Rennen"),
]


@dataclass
class Championship:
    rounds: list[str]
    format: str
    laps: int
    difficulty: str
    field_size: int
    spectator: bool
    player_name: str
    team: str
    results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def round(self) -> int:
        return len(self.results)

    @property
    def finished(self) -> bool:
        return self.round >= len(self.rounds)

    @property
    def next_track(self) -> str | None:
        return None if self.finished else self.rounds[self.round]

    def award(self, session: "RaceSession") -> dict[str, Any]:
        order = session.standings()
        fastest = session.fastest_lap[1] if session.fastest_lap else None
        rows = []
        for pos, car in enumerate(order):
            pts = 0 if car.dnf else (POINTS[pos] if pos < len(POINTS) else 0)
            fl = car.short == fastest and not car.dnf and pos < len(POINTS)
            if fl:
                pts += FASTEST_LAP_POINT
            rows.append({"name": car.name, "team": car.profile.team, "points": pts, "dnf": car.dnf,
                         "fastest": fl, "player": car is session.player})
        result = {"track": session.track.definition.key, "track_name": session.track.name, "rows": rows}
        self.results.append(result)
        self.save()
        return result

    def driver_table(self) -> list[dict[str, Any]]:
        table: dict[str, dict[str, Any]] = {}
        for k, res in enumerate(self.results):
            for pos, row in enumerate(res["rows"]):
                entry = table.setdefault(row["name"], {"name": row["name"], "team": row["team"], "points": 0,
                                                       "finishes": [0] * 20, "last": 0, "player": False,
                                                       "wins": 0, "podiums": 0})
                entry["team"] = row["team"]
                entry["points"] += row["points"]
                entry["player"] = entry["player"] or row.get("player", False)
                if not row["dnf"] and pos < 20:
                    entry["finishes"][pos] += 1
                    entry["wins"] += pos == 0
                    entry["podiums"] += pos < 3
                if k == len(self.results) - 1:
                    entry["last"] = row["points"]
        return sorted(table.values(), key=lambda e: (-e["points"], [-c for c in e["finishes"]]))

    def team_table(self) -> list[dict[str, Any]]:
        table: dict[str, dict[str, Any]] = {}
        for res in self.results:
            for row in res["rows"]:
                entry = table.setdefault(row["team"], {"team": row["team"], "points": 0, "wins": 0})
                entry["points"] += row["points"]
            if res["rows"] and not res["rows"][0]["dnf"]:
                table[res["rows"][0]["team"]]["wins"] += 1
        return sorted(table.values(), key=lambda e: (-e["points"], -e["wins"]))

    def winner_of(self, round_index: int) -> str | None:
        if round_index >= len(self.results):
            return None
        rows = self.results[round_index]["rows"]
        return rows[0]["name"] if rows else None

    def save(self) -> None:
        hook = getattr(self, "_hook", None)
        if hook is not None:
            hook()
            return
        CHAMPIONSHIP_FILE.parent.mkdir(parents=True, exist_ok=True)
        CHAMPIONSHIP_FILE.write_text(json.dumps(asdict(self), indent=1, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls) -> "Championship | None":
        try:
            raw = json.loads(CHAMPIONSHIP_FILE.read_text(encoding="utf-8"))
            return cls(**raw)
        except (OSError, ValueError, TypeError):
            return None

    @staticmethod
    def delete() -> None:
        try:
            CHAMPIONSHIP_FILE.unlink()
        except OSError:
            pass
