# Copyright Olivenda (Oliver Petz) 2026
"""Digital flag panels: the LED marshal panels along the track and the flag each driver is being shown.

Panel states: "off", "green", "yellow", "yellow2" (double yellow, right before the incident), "blue", "sc",
"vsc", "chequered". The 3D renderer draws the panels, the HUD shows the flag of the focused car."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from .car import Car
    from .sessions import Session
    from .track import Track

GREEN_TIME = 6.0          # green panels after a yellow / safety car period has ended
DOUBLE_YELLOW = 420.0     # panels this close before the incident show double yellow
BLUE_AHEAD = 260.0        # a panel shows blue while a blue-flagged car is this far before it
CHEQUERED_TIME = 8.0

FLAG_COLORS = {
    "green": (40, 230, 90), "yellow": (255, 210, 20), "yellow2": (255, 210, 20), "blue": (40, 120, 255),
    "sc": (255, 210, 20), "vsc": (255, 210, 20), "bw": (235, 235, 235), "chequered": (240, 240, 240),
}
FLAG_NAMES = {
    "green": "GRÜNE FLAGGE", "yellow": "GELBE FLAGGE", "yellow2": "DOPPELT GELB", "blue": "BLAUE FLAGGE",
    "sc": "SAFETY CAR", "vsc": "VIRTUAL SAFETY CAR", "bw": "SCHWARZ-WEISS", "chequered": "ZIELFLAGGE",
}


def marshal_posts(track: "Track") -> list[tuple[int, float]]:
    """The marshal posts with a digital panel: (waypoint index, side) - built once per track. Posts sit on the
    outside of corners where possible; the first one stands just before the finish line."""
    cached = getattr(track, "_marshal_posts", None)
    if cached is not None:
        return cached
    n = track.n
    pit_side = track.pit.side if track.pit is not None else 1.0
    posts = [((n - 3) % n, -pit_side)]
    count = max(10, min(22, int(track.length / 380)))
    step = n / count
    for k in range(1, count):
        i = int(k * step) % n
        a, b = track.tangents[(i - 6) % n], track.tangents[(i + 6) % n]
        bend = a.x * b.y - a.y * b.x
        side = (-1.0 if bend > 0 else 1.0) if abs(bend) > 0.04 else (1.0 if k % 2 else -1.0)
        posts.append((i, side))
    track._marshal_posts = posts
    return posts


def _sector(track: "Track", s: float) -> int:
    return min(2, int((s % track.length) / track.length * 3))


def post_states(session: "Session") -> list[str]:
    """What every marshal panel shows right now."""
    track = session.track
    posts = marshal_posts(track)
    L = track.length
    rc = getattr(session, "rc", None)
    now = session.time
    states = ["off"] * len(posts)
    if rc is not None and rc.active:
        restart = rc.mode == "SC" and rc.phase == "restart"
        return [("green" if restart and k == 0 else "sc") if rc.mode == "SC" else "vsc"
                for k in range(len(posts))]
    if rc is not None and now < getattr(rc, "green_until", 0.0):
        return ["green"] * len(posts)
    yellow = rc.yellow if rc is not None else {}
    spots = getattr(rc, "yellow_at", {}) if rc is not None else {}
    cleared = getattr(rc, "cleared", {}) if rc is not None else {}
    blue_cars = [c.s for c in session.cars if getattr(c, "blue_for", None) is not None and not c.in_pit]
    winner = getattr(session, "winner_time", None)
    for k, (i, _side) in enumerate(posts):
        s = track.cum[i]
        sector = _sector(track, s)
        if k == 0 and winner is not None:
            states[k] = "chequered"
        elif sector in yellow:
            spot = spots.get(sector)
            ahead = (spot - s) % L if spot is not None else L
            states[k] = "yellow2" if ahead < DOUBLE_YELLOW else "yellow"
        elif (sector - 1) % 3 in yellow or cleared.get(sector, 0.0) > now:
            # first panel after a yellow sector (or a sector just cleared): green, the danger is over
            states[k] = "green"
        elif any(0.0 < (s - cs) % L < BLUE_AHEAD for cs in blue_cars):
            states[k] = "blue"
    return states


def car_flag(session: "Session", car: "Car") -> str | None:
    """The flag shown to this driver right now (most important first), or None."""
    rc = getattr(session, "rc", None)
    now = session.time
    finished = getattr(car, "finished_at", None)
    if car.session_done:
        return "chequered" if finished is not None and now - finished < CHEQUERED_TIME else None
    if car.in_pit or car.dnf:
        return None
    if rc is not None:
        if rc.active:
            return "sc" if rc.mode == "SC" else "vsc"
        if now < getattr(rc, "green_until", 0.0):
            return "green"
    if getattr(car, "blue_for", None) is not None and session.kind == "race":
        return "blue"
    if rc is not None:
        track = session.track
        sector = _sector(track, car.s)
        if sector in rc.yellow:
            spot = getattr(rc, "yellow_at", {}).get(sector)
            ahead = (spot - car.s) % track.length if spot is not None else track.length
            return "yellow2" if ahead < DOUBLE_YELLOW else "yellow"
        if getattr(rc, "cleared", {}).get(sector, 0.0) > now:
            return "green"
    if now < getattr(car, "bw_until", 0.0):
        return "bw"
    return None


def hazard_ahead(session: "Session", car: "Car") -> tuple[float, float] | None:
    """A stopped or very slow car on the track ahead: (distance, lateral offset), or None."""
    if car.in_pit or car.session_done:
        return None
    L = session.track.length
    best = None
    for other in session.cars:
        if other is car or other.in_pit or other.session_done or getattr(other, "is_ghost", False):
            continue
        if other.speed_fwd > 70.0 and not other.dnf:
            continue
        if other.dnf and getattr(other, "retired_ghost", False):
            continue
        ahead = (other.s - car.s) % L
        if 40.0 < ahead < 520.0 and (best is None or ahead < best[0]):
            best = (ahead, other.lateral)
    return best


_BOARDS: dict[tuple, pygame.Surface] = {}
_TEXT_MASKS: dict[str, pygame.Surface] = {}


def _text_mask(text: str, cols: int, rows: int) -> pygame.Surface:
    mask = _TEXT_MASKS.get(text)
    if mask is None:
        font = pygame.font.SysFont("arial,dejavusans", rows - 3, bold=True)
        img = font.render(text, False, (255, 255, 255), (0, 0, 0))
        mask = pygame.Surface((cols, rows))
        mask.fill((0, 0, 0))
        mask.blit(img, img.get_rect(center=(cols // 2, rows // 2 + 1)))
        _TEXT_MASKS[text] = mask
    return mask


def led_board(state: str, phase: int, cols: int = 32, rows: int = 18, pitch: int = 4) -> pygame.Surface:
    """A digital flag panel as an LED dot matrix (cached). phase 0/1 = the two blink states."""
    key = (state, phase, cols, rows, pitch)
    board = _BOARDS.get(key)
    if board is not None:
        return board
    board = pygame.Surface((cols * pitch + 8, rows * pitch + 8))
    board.fill((10, 10, 12))
    pygame.draw.rect(board, (46, 48, 54), board.get_rect(), 2)
    dark = (34, 35, 40)
    col = FLAG_COLORS.get(state, dark)
    dim = tuple(int(c * 0.22) for c in col)
    mask = _text_mask("SC" if state == "sc" else "VSC", cols, rows) if state in ("sc", "vsc") else None
    for y in range(rows):
        for x in range(cols):
            c = dark
            if state in ("green", "yellow", "blue"):
                c = col if phase == 0 or state == "green" else dim
            elif state == "yellow2":
                c = col if (y < rows // 2) == (phase == 0) else dim
            elif state == "chequered":
                c = (240, 240, 240) if ((x * 4 // cols) + (y * 3 // rows)) % 2 == phase else (16, 16, 18)
            elif state == "bw":
                c = (240, 240, 240) if x * rows > y * cols else (16, 16, 18)
            elif mask is not None:
                text = mask.get_at((x, y))[0] > 110
                c = ((20, 16, 4) if text else col) if phase == 0 else (col if text else dim)
            px, py = 4 + x * pitch + pitch // 2, 4 + y * pitch + pitch // 2
            pygame.draw.circle(board, c, (px, py), pitch * 0.42)
    if len(_BOARDS) > 64:
        _BOARDS.clear()
    _BOARDS[key] = board
    return board
