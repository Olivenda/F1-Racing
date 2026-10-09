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
