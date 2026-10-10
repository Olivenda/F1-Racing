# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
from collections import OrderedDict
from typing import Callable, Sequence

import pygame
from pygame.math import Vector2

from .i18n import tr


def clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def approach(current: float, target: float, max_delta: float) -> float:
    if current < target:
        return min(current + max_delta, target)
    return max(current - max_delta, target)


def wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def cross2(a: Vector2, b: Vector2) -> float:
    return a.x * b.y - a.y * b.x


def format_time(t: float | None) -> str:
    if t is None:
        return "-:--.---"
    minutes = int(t // 60)
    seconds = t - minutes * 60
    return f"{minutes}:{seconds:06.3f}"


def format_gap(gap: float | None) -> str:
    if gap is None:
        return "--"
    sign = "+" if gap >= 0 else "-"
    return f"{sign}{abs(gap):.3f}"


def centripetal_catmull_rom(points: Sequence[Vector2], step: float = 4.0) -> list[Vector2]:
    def knot(t_i: float, p_i: Vector2, p_j: Vector2) -> float:
        return t_i + max((p_j - p_i).length(), 1e-3) ** 0.5

    n = len(points)
    out: list[Vector2] = []
    for i in range(n):
        p0, p1, p2, p3 = points[(i - 1) % n], points[i], points[(i + 1) % n], points[(i + 2) % n]
        t0 = 0.0
        t1 = knot(t0, p0, p1)
        t2 = knot(t1, p1, p2)
        t3 = knot(t2, p2, p3)
        samples = max(4, int((p2 - p1).length() / step))
        for k in range(samples):
            t = t1 + (t2 - t1) * k / samples
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            out.append(b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1)))
    return out


def resample_closed(points: Sequence[Vector2], spacing: float) -> list[Vector2]:
    pts = list(points) + [points[0]]
    seg_lengths = [(pts[i + 1] - pts[i]).length() for i in range(len(pts) - 1)]
    total = sum(seg_lengths)
    count = max(8, int(total / spacing))
    step = total / count
    out: list[Vector2] = []
    seg, seg_pos = 0, 0.0
    for k in range(count):
        target = k * step
        while seg < len(seg_lengths) - 1 and seg_pos + seg_lengths[seg] < target:
            seg_pos += seg_lengths[seg]
            seg += 1
        length = seg_lengths[seg] if seg_lengths[seg] > 1e-9 else 1e-9
        u = (target - seg_pos) / length
        out.append(pts[seg].lerp(pts[seg + 1], clamp(u, 0.0, 1.0)))
    return out


def circumradius(a: Vector2, b: Vector2, c: Vector2) -> float:
    cross = abs(cross2(b - a, c - a))
    if cross < 1e-6:
        return 1e9
    return (b - a).length() * (c - b).length() * (a - c).length() / (2.0 * cross)


class _LRU(OrderedDict):

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit

    def fetch(self, key: object, build: Callable[[], object]) -> object:
        if key in self:
            self.move_to_end(key)
            return self[key]
        value = build()
        self[key] = value
        if len(self) > self.limit:
            self.popitem(last=False)
        return value


_TEXT_CACHE = _LRU(1500)
_PANEL_CACHE = _LRU(300)


def _render_text(text: str, font: pygame.font.Font, color: tuple[int, int, int],
                 shadow: bool) -> tuple[pygame.Surface, pygame.Surface | None]:
    def build() -> tuple[pygame.Surface, pygame.Surface | None]:
        img = font.render(text, True, color)
        sh = None
        if shadow:
            sh = font.render(text, True, (0, 0, 0))
            sh.set_alpha(150)
        return img, sh
    return _TEXT_CACHE.fetch((text, id(font), color, shadow), build)


def draw_text(surface: pygame.Surface, text: str, font: pygame.font.Font, color: tuple[int, int, int],
              pos: tuple[float, float], anchor: str = "topleft", shadow: bool = True) -> pygame.Rect:
    img, sh = _render_text(tr(text), font, tuple(color), shadow)
    rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    if sh is not None:
        surface.blit(sh, rect.move(2, 2))
    surface.blit(img, rect)
    return rect


def draw_panel(surface: pygame.Surface, rect: pygame.Rect | tuple[int, int, int, int],
               color: tuple[int, int, int] = (18, 20, 26), alpha: int = 205, radius: int = 8,
               border: tuple[int, int, int] | None = None) -> None:
    rect = pygame.Rect(rect)

    def build() -> pygame.Surface:
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*color, alpha), panel.get_rect(), border_radius=radius)
        if border:
            pygame.draw.rect(panel, (*border, 255), panel.get_rect(), width=2, border_radius=radius)
        return panel
    key = (rect.w, rect.h, tuple(color), int(alpha) // 8 * 8, radius, border)
    surface.blit(_PANEL_CACHE.fetch(key, build), rect)


def clear_render_caches() -> None:
    _TEXT_CACHE.clear()
    _PANEL_CACHE.clear()


def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int],
                      bottom: tuple[int, int, int]) -> pygame.Surface:
    surf = pygame.Surface(size)
    w, h = size
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(lerp(top[i], bottom[i], t)) for i in range(3))
        pygame.draw.line(surf, col, (0, y), (w, y))
    return surf


# ---------------------------------------------------------------------------------------------- mouse in menus
# Menus are keyboard driven. While drawing, a menu registers its rows with mouse_item(); the game loop turns
# the mouse into the keys the menu already understands: hovering selects a row, a click confirms it (ENTER) or,
# on the arrow zones of a value row, changes the value (LEFT/RIGHT), the wheel scrolls, right click goes back.
_MOUSE_ITEMS: list[tuple[pygame.Rect, object, str, int, "int | None", bool]] = []
ARROW_W = 34


def mouse_item(rect: pygame.Rect | tuple[int, int, int, int], owner: object, index: int, attr: str = "sel",
               key: int | None = pygame.K_RETURN, arrows: bool = False) -> None:
    """Register a clickable menu entry for this frame. owner.<attr> = index selects it; key is sent on a click
    (None: a click only selects); arrows: the right end of the row has < > zones sending LEFT/RIGHT."""
    _MOUSE_ITEMS.append((pygame.Rect(rect), owner, attr, index, key, arrows))


def mouse_items_reset() -> None:
    _MOUSE_ITEMS.clear()


def _mouse_hit(pos: tuple[int, int]):
    for item in reversed(_MOUSE_ITEMS):
        if item[0].collidepoint(pos):
            return item
    return None


def _arrow_zone(item, pos: tuple[int, int]) -> int:
    rect, arrows = item[0], item[5]
    if not arrows:
        return 0
    if rect.right - ARROW_W <= pos[0] <= rect.right:
        return 1
    if rect.right - 2 * ARROW_W - 4 <= pos[0] < rect.right - ARROW_W:
        return -1
    return 0


def mouse_to_keys(event: pygame.event.Event) -> list[pygame.event.Event]:
    """Mouse event -> key events for the current menu (selection on hover is applied directly)."""
    def key(k: int) -> pygame.event.Event:
        return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0, from_mouse=True)

    if event.type == pygame.MOUSEMOTION:
        item = _mouse_hit(event.pos)
        if item is not None and getattr(item[1], item[2], None) != item[3]:
            setattr(item[1], item[2], item[3])
        return []
    if event.type == pygame.MOUSEWHEEL:
        return [key(pygame.K_UP if event.y > 0 else pygame.K_DOWN)] if event.y else []
    if event.type != pygame.MOUSEBUTTONDOWN:
        return []
    if event.button == 3:
        return [key(pygame.K_ESCAPE)]
    if event.button != 1:
        return []
    item = _mouse_hit(event.pos)
    if item is None:
        return []
    setattr(item[1], item[2], item[3])
    zone = _arrow_zone(item, event.pos)
    if zone:
        return [key(pygame.K_RIGHT if zone > 0 else pygame.K_LEFT)]
    return [key(item[4])] if item[4] is not None else []


def draw_mouse_hints(surface: pygame.Surface) -> None:
    """Show the < > zones of the value row under the mouse."""
    pos = pygame.mouse.get_pos()
    item = _mouse_hit(pos)
    if item is None or not item[5]:
        return
    rect = item[0]
    zone = _arrow_zone(item, pos)
    for d, x in ((-1, rect.right - 2 * ARROW_W - 4), (1, rect.right - ARROW_W)):
        r = pygame.Rect(x, rect.y + 4, ARROW_W, rect.h - 8)
        pygame.draw.rect(surface, (225, 30, 40) if zone == d else (60, 62, 74), r, border_radius=6)
        cx, cy = r.center
        pts = [(cx + 4 * d, cy), (cx - 3 * d, cy - 6), (cx - 3 * d, cy + 6)]
        pygame.draw.polygon(surface, (245, 245, 245), pts)
