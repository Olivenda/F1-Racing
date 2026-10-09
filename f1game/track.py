# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass

import pygame
from pygame.math import Vector2

from .settings import BRAKE_DECEL, CAR_LENGTH, CAR_WIDTH, LATERAL_GRIP, TOP_SPEED, Color
from .pitlane import PitLane

TRACK_SIZE: float = 1.25
from .utils import centripetal_catmull_rom, circumradius, clamp, resample_closed


@dataclass(frozen=True)
class TrackDef:
    key: str
    name: str
    country: str
    character: str
    points: tuple[tuple[float, float], ...]
    half_width: float
    runoff: float
    scale: float
    grass: Color
    runoff_color: Color
    asphalt: Color
    wall_a: Color
    wall_b: Color
    scenery: str


TRACK_DEFS: list[TrackDef] = [
    TrackDef(
        key="monaco", name="Monaco", country="Monte Carlo",
        character="Enger Stadtkurs - Mauern direkt an der Strecke, kaum Platz zum Überholen.",
        points=((800, 1098), (1000, 1085), (1085, 1000), (1100, 800), (1150, 600),
                (1250, 450), (1400, 380), (1550, 420), (1620, 540), (1750, 600), (1850, 520),
                (1880, 400), (1950, 300), (2050, 320), (2060, 430), (1990, 560), (2050, 700),
                (2200, 760), (2250, 900), (2200, 1100), (2050, 1250), (1850, 1300), (1780, 1250),
                (1700, 1320), (1550, 1350), (1400, 1300), (1300, 1380), (1200, 1320), (1100, 1400),
                (950, 1420), (800, 1350), (700, 1420), (500, 1420), (300, 1350), (220, 1220),
                (300, 1100), (520, 1100)),
        half_width=52.0, runoff=22.0, scale=1.9,
        grass=(52, 92, 50), runoff_color=(70, 70, 76), asphalt=(58, 59, 64),
        wall_a=(200, 200, 205), wall_b=(210, 30, 40), scenery="city"),
    TrackDef(
        key="monza", name="Monza", country="Italien",
        character="Tempel der Geschwindigkeit - lange Geraden, Schikanen, viel Windschatten.",
        points=((1300, 1300), (1900, 1300), (2010, 1300), (2070, 1210), (2150, 1195), (2260, 1150),
                (2420, 1030), (2540, 860), (2580, 680), (2575, 600), (2490, 545), (2560, 470),
                (2560, 380), (2470, 270), (2350, 240), (2260, 330), (2150, 300), (2050, 360),
                (1700, 460), (1320, 560), (1200, 590), (1120, 500), (1030, 560), (960, 650),
                (820, 680), (600, 710), (380, 750), (250, 800), (190, 900), (175, 1100),
                (260, 1250), (420, 1300), (800, 1300)),
        half_width=72.0, runoff=60.0, scale=2.1,
        grass=(48, 120, 52), runoff_color=(70, 140, 62), asphalt=(62, 63, 68),
        wall_a=(40, 70, 160), wall_b=(230, 230, 230), scenery="park"),
    TrackDef(
        key="silverstone", name="Silverstone", country="Großbritannien",
        character="Schnelle Kurvenkombinationen - Maggotts/Becketts belohnen Präzision.",
        points=((950, 1250), (1100, 1250), (1350, 1220), (1500, 1100), (1520, 960), (1450, 860),
                (1470, 740), (1600, 690), (2000, 700), (2250, 650), (2310, 520), (2250, 420),
                (2130, 410), (2030, 440), (1900, 380), (1800, 250), (1600, 180), (1450, 260), (1300, 180),
                (1150, 260), (1000, 200), (700, 220), (450, 300), (350, 450), (420, 600),
                (350, 700), (250, 850), (280, 1050), (380, 1200), (520, 1250), (750, 1250)),
        half_width=64.0, runoff=50.0, scale=2.0,
        grass=(56, 112, 58), runoff_color=(176, 160, 120), asphalt=(60, 61, 66),
        wall_a=(220, 220, 220), wall_b=(30, 30, 35), scenery="park"),
    TrackDef(
        key="spa", name="Spa-Francorchamps", country="Belgien",
        character="Lang und schnell: La Source, Eau Rouge, Kemmel-Gerade und die Bus-Stop-Schikane.",
        points=((1200, 1100), (900, 1100), (700, 1100), (620, 1050), (630, 985), (720, 950), (850, 935),
                (950, 900), (1010, 840), (1080, 800), (1300, 690), (1600, 520), (1700, 455), (1760, 475),
                (1800, 420), (1870, 385), (1960, 420), (1990, 520), (1960, 640), (2010, 750), (2110, 800),
                (2210, 770), (2290, 830), (2310, 950), (2240, 1045), (2050, 1080), (1820, 1065), (1740, 1110),
                (1660, 1065), (1560, 1100)),
        half_width=64.0, runoff=50.0, scale=2.2,
        grass=(40, 98, 46), runoff_color=(165, 150, 112), asphalt=(58, 59, 64),
        wall_a=(220, 220, 220), wall_b=(200, 30, 30), scenery="park"),
    TrackDef(
        key="interlagos", name="Interlagos", country="Brasilien",
        character="Kompakt und hügelig: Senna-S, lange Gegengerade und ein verwinkeltes Infield.",
        points=((1550, 600), (1550, 900), (1500, 1000), (1400, 1000), (1340, 1070), (1240, 1090), (900, 1085),
                (520, 1050), (390, 1000), (350, 900), (420, 810), (600, 780), (740, 720), (815, 630),
                (790, 530), (700, 470), (690, 400), (790, 350), (1000, 300), (1300, 240),
                (1490, 290), (1550, 400)),
        half_width=60.0, runoff=45.0, scale=2.1,
        grass=(58, 118, 52), runoff_color=(70, 140, 62), asphalt=(60, 61, 66),
        wall_a=(240, 200, 30), wall_b=(30, 120, 60), scenery="park"),
    TrackDef(
        key="marinabay", name="Marina Bay", country="Singapur",
        character="Nächtlicher Stadtkurs: 90-Grad-Ecken zwischen Mauern - Präzision vor Tempo.",
        points=((700, 1200), (1250, 1200), (1330, 1140), (1330, 1020), (1420, 960), (1700, 960), (1760, 900),
                (1760, 600), (1700, 540), (1450, 540), (1390, 480), (1390, 300), (1330, 240), (1000, 240),
                (940, 300), (940, 520), (880, 580), (600, 580), (540, 640), (540, 820), (480, 880),
                (300, 880), (240, 940), (240, 1140), (300, 1200)),
        half_width=54.0, runoff=20.0, scale=1.9,
        grass=(30, 44, 40), runoff_color=(62, 62, 70), asphalt=(48, 49, 56),
        wall_a=(230, 230, 235), wall_b=(220, 40, 120), scenery="city"),
]


class Track:

    WAYPOINT_SPACING: float = 12.0

    def __init__(self, definition: TrackDef) -> None:
        self.definition = definition
        self.name = definition.name
        self.half_width = definition.half_width
        self.wetness = 0.0      # set by the session's weather every step
        self.wall_limit = definition.half_width + definition.runoff

        raw = [Vector2(p) * (definition.scale * TRACK_SIZE) for p in definition.points]
        pts = resample_closed(centripetal_catmull_rom(raw), self.WAYPOINT_SPACING)

        margin = self.wall_limit + 220
        min_x = min(p.x for p in pts)
        min_y = min(p.y for p in pts)
        shift = Vector2(margin - min_x, margin - min_y)
        self.center: list[Vector2] = [p + shift for p in pts]
        self.n = len(self.center)
        self.world_size = (int(max(p.x for p in self.center) + margin),
                           int(max(p.y for p in self.center) + margin))
        self._cx = [p.x for p in self.center]
        self._cy = [p.y for p in self.center]

        self.tangents: list[Vector2] = []
        self.normals: list[Vector2] = []
        for i in range(self.n):
            t = (self.center[(i + 1) % self.n] - self.center[i - 1]).normalize()
            self.tangents.append(t)
            self.normals.append(Vector2(-t.y, t.x))

        self.cum: list[float] = [0.0]
        for i in range(1, self.n):
            self.cum.append(self.cum[-1] + (self.center[i] - self.center[i - 1]).length())
        self.length = self.cum[-1] + (self.center[0] - self.center[-1]).length()

        self.line_offset: list[float] = []
        self.racing_line: list[Vector2] = []
        self.max_speed: list[float] = []
        self.brake_zone: list[bool] = []
        self.scenery: list[tuple] = []
        self.wall_edges: tuple[list[Vector2 | None], list[Vector2 | None]] = ([], [])
        self.curb_segment: list[bool] = []
        self.pit: PitLane | None = None
        self.aero_zones: list[tuple[int, int]] = []
        self.aero_zone_at: list[int] = []
        self.surface: pygame.Surface | None = None
        self._built = False

    def ensure_geometry(self) -> None:
        if self.line_offset:
            return
        self._compute_racing_line()
        self._compute_speed_profile()
        self._compute_aero_zones()
        self.pit = PitLane(self)
        lane = self.pit.outline(24.0)
        self.scenery = [item for item in self._build_scenery()
                        if min((item[1] - (l + r) * 0.5).length() for l, r in lane) > self.pit.HALF_WIDTH + 90]
        self.wall_edges = self._edge_points(self.wall_limit + 2)
        pit_wall = self.wall_edges[0] if self.pit.side < 0 else self.wall_edges[1]
        for i in self.pit.ramp_indices():
            pit_wall[i] = None
        self.curb_segment = [circumradius(self.center[i - 4], self.center[i], self.center[(i + 4) % self.n]) <= 320
                             for i in range(self.n)]

    def ensure_built(self) -> None:
        if self._built:
            return
        self.ensure_geometry()
        self.surface = self._render()
        self._built = True

    def release_surface(self) -> None:
        self.surface = None
        self._built = False

    def _compute_racing_line(self) -> None:
        n = self.n
        limit = self.half_width - CAR_WIDTH * 0.9
        off = [0.0] * n
        for k, iterations in ((16, 30), (8, 30), (4, 40), (2, 40), (1, 60)):
            for _ in range(iterations):
                for i in range(n):
                    ia, ib = (i - k) % n, (i + k) % n
                    na, nb, ni = self.normals[ia], self.normals[ib], self.normals[i]
                    mx = (self._cx[ia] + na.x * off[ia] + self._cx[ib] + nb.x * off[ib]) * 0.5
                    my = (self._cy[ia] + na.y * off[ia] + self._cy[ib] + nb.y * off[ib]) * 0.5
                    target = (mx - self._cx[i]) * ni.x + (my - self._cy[i]) * ni.y
                    off[i] = clamp(off[i] + (target - off[i]) * 0.8, -limit, limit)
        for _ in range(3):
            off = [(off[i - 1] + 2 * off[i] + off[(i + 1) % n]) * 0.25 for i in range(n)]
        self.line_offset = off
        self.racing_line = [self.center[i] + self.normals[i] * off[i] for i in range(n)]

    def _compute_speed_profile(self) -> None:
        n = self.n
        line = self.racing_line
        v = [min(TOP_SPEED, math.sqrt(LATERAL_GRIP * 0.92 * circumradius(line[i - 3], line[i], line[(i + 3) % n])))
             for i in range(n)]
        for _ in range(2):
            for i in range(n - 1, -1, -1):
                j = (i + 1) % n
                ds = (line[j] - line[i]).length()
                v[i] = min(v[i], math.sqrt(v[j] ** 2 + 2.0 * BRAKE_DECEL * 0.8 * ds))
        self.max_speed = v
        self.brake_zone = [v[(i + 1) % n] < v[i] - 0.5 for i in range(n)]

    AERO_MIN_LENGTH: float = 650.0
    AERO_MAX_ZONES: int = 4

    def _compute_aero_zones(self) -> None:
        n = self.n
        flat = [v >= TOP_SPEED * 0.97 for v in self.max_speed]
        self.aero_zone_at = [-1] * n
        if all(flat):
            return
        start0 = next(i for i in range(n) if not flat[i])
        runs: list[tuple[int, int]] = []
        i = 0
        while i < n:
            k = (start0 + i) % n
            if flat[k]:
                length = 0
                while i + length < n and flat[(start0 + i + length) % n]:
                    length += 1
                runs.append((k, length))
                i += length
            else:
                i += 1
        sp = self.WAYPOINT_SPACING
        runs.sort(key=lambda r: -r[1])
        runs = [r for r in runs if r[1] * sp >= self.AERO_MIN_LENGTH][:self.AERO_MAX_ZONES]
        lead = int(120 / sp)
        for zone, (start, length) in enumerate(sorted(runs)):
            a = (start + lead) % n
            b = (start + length - 1) % n
            self.aero_zones.append((a, b))
            for k in range(length - 1 - lead):
                self.aero_zone_at[(a + k) % n] = zone

    def _local_min_dist(self, p: Vector2, i: int, window: int = 70) -> float:
        best = 1e18
        for k in range(-window, window + 1):
            j = (i + k) % self.n
            dx, dy = self._cx[j] - p.x, self._cy[j] - p.y
            d = dx * dx + dy * dy
            if d < best:
                best = d
        return math.sqrt(best)

    def _edge_points(self, distance: float) -> tuple[list[Vector2 | None], list[Vector2 | None]]:
        left: list[Vector2 | None] = []
        right: list[Vector2 | None] = []
        for i in range(self.n):
            for side, out in ((-1, left), (1, right)):
                p = self.center[i] + self.normals[i] * (distance * side)
                out.append(p if self._local_min_dist(p, i) >= distance - 1.5 else None)
        return left, right

    def _render(self) -> pygame.Surface:
        d = self.definition
        surf = pygame.Surface(self.world_size).convert()
        surf.fill(d.grass)
        stripe = tuple(min(255, c + 7) for c in d.grass)
        for x in range(0, self.world_size[0], 80):
            pygame.draw.rect(surf, stripe, (x, 0, 40, self.world_size[1]))
        rng = random.Random(sum(map(ord, d.key)) * 7)
        self._speckle(surf, rng, d.grass, self.world_size[0] * self.world_size[1] // 260, 9)

        self._render_scenery(surf)

        for p in self.center:
            pygame.draw.circle(surf, d.runoff_color, p, self.wall_limit)
        self._render_gravel(surf, rng)
        for i in range(self.n):
            j = (i + 1) % self.n
            a, b = self.center[i], self.center[j]
            na, nb = self.normals[i], self.normals[j]
            hw = self.half_width
            pygame.draw.polygon(surf, d.asphalt, [a - na * hw, b - nb * hw, b + nb * hw, a + na * hw])
            pygame.draw.circle(surf, d.asphalt, a, hw)
        self._render_asphalt_detail(surf, rng)

        self._render_pit_lane(surf)
        self._render_aero_zones(surf)

        curb_l, curb_r = self._edge_points(self.half_width)
        for i in range(self.n):
            j = (i + 1) % self.n
            r = circumradius(self.center[i - 4], self.center[i], self.center[(i + 4) % self.n])
            if r > 320:
                continue
            col = (220, 30, 30) if (i // 2) % 2 == 0 else (240, 240, 240)
            for edge, side in ((curb_l, -1), (curb_r, 1)):
                if edge[i] is None or edge[j] is None:
                    continue
                inner_i = self.center[i] + self.normals[i] * (side * (self.half_width - 6))
                inner_j = self.center[j] + self.normals[j] * (side * (self.half_width - 6))
                pygame.draw.polygon(surf, col, [inner_i, inner_j, edge[j], edge[i]])

        line_l, line_r = self._edge_points(self.half_width - 1)
        for edge in (line_l, line_r):
            for i in range(self.n):
                a, b = edge[i], edge[(i + 1) % self.n]
                if a is not None and b is not None:
                    pygame.draw.line(surf, (235, 235, 235), a, b, 2)

        wall_l, wall_r = self.wall_edges
        for edge in (wall_l, wall_r):
            for i in range(self.n):
                a, b = edge[i], edge[(i + 1) % self.n]
                if a is not None and b is not None:
                    col = d.wall_a if (i // 3) % 2 == 0 else d.wall_b
                    pygame.draw.line(surf, (20, 20, 20), a, b, 7)
                    pygame.draw.line(surf, col, a, b, 4)

        self._render_start_and_grid(surf)
        return surf

    @staticmethod
    def _speckle(surf: pygame.Surface, rng: random.Random, base: Color, count: int, spread: int) -> None:
        w, h = surf.get_size()
        shades = [tuple(max(0, min(255, c + k)) for c in base) for k in (-spread, -spread // 2, spread // 2, spread)]
        fill = surf.fill
        for _ in range(count):
            fill(shades[rng.randrange(4)], (rng.randrange(w), rng.randrange(h), 2, 2))

    def _render_gravel(self, surf: pygame.Surface, rng: random.Random) -> None:
        """Sand-coloured gravel traps on the outside of tight corners."""
        inner, outer = self.half_width + 12, self.wall_limit - 4
        if outer - inner < 10:
            return
        sand = (196, 178, 128) if self.definition.scenery != "city" else (120, 118, 112)
        n = self.n
        for i in range(n):
            j = (i + 1) % n
            if circumradius(self.center[i - 5], self.center[i], self.center[(i + 5) % n]) > 260:
                continue
            bend = self.tangents[(i + 4) % n] - self.tangents[i - 4]
            side = -1.0 if bend.dot(self.normals[i]) > 0 else 1.0
            ni, nj = self.normals[i] * side, self.normals[j] * side
            ci, cj = self.center[i], self.center[j]
            pygame.draw.polygon(surf, sand, [ci + ni * inner, cj + nj * inner, cj + nj * outer, ci + ni * outer])
            for _ in range(6):
                u, v = rng.uniform(inner, outer), rng.random()
                p = ci + (cj - ci) * v + ni * u
                shade = tuple(max(0, c - rng.randint(15, 45)) for c in sand)
                surf.fill(shade, (int(p.x), int(p.y), 2, 2))

    def _render_asphalt_detail(self, surf: pygame.Surface, rng: random.Random) -> None:
        """Grain in the tarmac and a darker rubbered-in racing line."""
        a = self.definition.asphalt
        if self.racing_line:
            pts = self.racing_line
            for width, k in ((26, 4), (14, 8)):
                col = tuple(max(0, c - k) for c in a)
                pygame.draw.lines(surf, col, True, pts, width)
        hw = self.half_width - 3
        shades = [tuple(max(0, min(255, c + k)) for c in a) for k in (-8, -4, 5, 9)]
        for i in range(self.n):
            c, nrm, t = self.center[i], self.normals[i], self.tangents[i]
            for _ in range(10):
                p = c + nrm * rng.uniform(-hw, hw) + t * rng.uniform(-6, 6)
                surf.fill(shades[rng.randrange(4)], (int(p.x), int(p.y), 2, 2))

    def _build_scenery(self) -> list[tuple]:
        rng = random.Random(sum(map(ord, self.definition.key)))
        d = self.definition
        w, h = self.world_size
        clearance = self.wall_limit + 45
        out: list[tuple] = []
        for _ in range(1400):
            if len(out) > 260:
                break
            p = Vector2(rng.uniform(0, w), rng.uniform(0, h))
            if min(math.hypot(self._cx[i] - p.x, self._cy[i] - p.y) for i in range(0, self.n, 3)) < clearance:
                continue
            if d.scenery == "city":
                size = rng.randint(30, 70)
                shade = rng.randint(90, 160)
                col = (shade, shade - rng.randint(0, 30), shade - rng.randint(10, 50))
                out.append(("building", p, size, int(size * rng.uniform(0.6, 1.4)), col, rng.randint(40, 140)))
            else:
                r = rng.randint(10, 22)
                out.append(("tree", p, r, (40 + rng.randint(0, 25), 95 + rng.randint(0, 30), 45), r * 3))
        return out

    def _render_scenery(self, surf: pygame.Surface) -> None:
        for item in self.scenery:
            if item[0] == "building":
                _, p, w, h, col, height = item
                rect = pygame.Rect(0, 0, w, h)
                rect.center = p
                drop = max(5, height // 12)
                pygame.draw.rect(surf, (24, 26, 30), rect.move(drop, drop), border_radius=3)
                pygame.draw.rect(surf, col, rect, border_radius=3)
                roof = rect.inflate(-8, -8)
                pygame.draw.rect(surf, tuple(min(255, c + 14) for c in col), roof, border_radius=2)
                pygame.draw.rect(surf, tuple(max(0, c - 40) for c in col), rect, 2, border_radius=3)
                pygame.draw.line(surf, tuple(min(255, c + 45) for c in col), rect.topleft, rect.topright, 2)
                for k in range(max(1, w // 26)):
                    unit = pygame.Rect(roof.x + 4 + k * 22, roof.y + 4, 9, 7)
                    if unit.right < roof.right:
                        pygame.draw.rect(surf, (150, 152, 158), unit)
                        pygame.draw.rect(surf, (90, 92, 98), unit, 1)
            else:
                _, p, r, col, _height = item
                pygame.draw.circle(surf, (22, 52, 26), p + Vector2(r * 0.35, r * 0.45), r)
                dark = tuple(max(0, c - 22) for c in col)
                pygame.draw.circle(surf, dark, p, r)
                pygame.draw.circle(surf, col, p - Vector2(r * 0.12, r * 0.12), r * 0.78)
                light = tuple(min(255, c + 30) for c in col)
                pygame.draw.circle(surf, light, p - Vector2(r * 0.32, r * 0.32), r * 0.38)

    def _render_pit_lane(self, surf: pygame.Surface) -> None:
        pit = self.pit
        if pit is None:
            return
        edges = pit.outline(8.0)
        for (l0, r0), (l1, r1) in zip(edges, edges[1:]):
            pygame.draw.polygon(surf, (52, 53, 58), [l0, l1, r1, r0])
        for k in range(len(edges) - 1):
            for side in (0, 1):
                pygame.draw.line(surf, (235, 235, 235), edges[k][side], edges[k + 1][side], 2)
        font = pygame.font.SysFont("arial", 18, bold=True)
        for u, text in ((pit.RAMP, "PIT  100"), (pit.length - pit.RAMP, "END")):
            p, heading = pit.pose(u)
            nrm = Vector2(-math.sin(heading), math.cos(heading)) * pit.HALF_WIDTH
            pygame.draw.line(surf, (255, 210, 40), p - nrm, p + nrm, 3)
            img = font.render(text, True, (255, 210, 40))
            surf.blit(img, img.get_rect(center=p + nrm * 2.2))

    def _render_aero_zones(self, surf: pygame.Surface) -> None:
        font = pygame.font.SysFont("arial", 16, bold=True)
        hw = self.half_width
        col = (70, 170, 255)
        for start, end in self.aero_zones:
            for idx, text in ((start, "STRAIGHT MODE"), (end, None)):
                c, nrm, t = self.center[idx], self.normals[idx], self.tangents[idx]
                if text:
                    pygame.draw.line(surf, col, c - nrm * hw, c + nrm * hw, 3)
                    img = pygame.transform.rotate(font.render(text, True, col), -math.degrees(math.atan2(t.y, t.x)))
                    surf.blit(img, img.get_rect(center=c + nrm * (hw + 24)))
                else:
                    for k in range(-int(hw), int(hw), 12):
                        pygame.draw.line(surf, col, c + nrm * k, c + nrm * (k + 6), 3)

    def _render_start_and_grid(self, surf: pygame.Surface) -> None:
        c, t, nrm = self.center[0], self.tangents[0], self.normals[0]
        sq = 6.0
        cols = int(self.half_width * 2 / sq)
        for row in range(2):
            for col in range(cols):
                color = (245, 245, 245) if (row + col) % 2 == 0 else (15, 15, 15)
                lat = -self.half_width + col * sq
                base = c + nrm * lat + t * (row * sq - sq)
                pygame.draw.polygon(surf, color, [base, base + nrm * sq, base + nrm * sq + t * sq, base + t * sq])
        for slot in range(14):
            pos, heading = self.grid_pose(slot)
            fwd = Vector2(math.cos(heading), math.sin(heading))
            right = Vector2(-fwd.y, fwd.x)
            front = pos + fwd * (CAR_LENGTH * 0.6)
            pygame.draw.line(surf, (235, 235, 235), front - right * 11, front + right * 11, 2)
            pygame.draw.line(surf, (235, 235, 235), front - right * 11, front - right * 11 - fwd * 14, 2)
            pygame.draw.line(surf, (235, 235, 235), front + right * 11, front + right * 11 - fwd * 14, 2)

    def nearest_index(self, pos: Vector2, hint: int | None = None, back: int = 6, fwd: int = 22) -> int:
        px, py = pos.x, pos.y
        if hint is not None:
            best_i, best_d = hint, 1e18
            for k in range(-back, fwd + 1):
                i = (hint + k) % self.n
                dx, dy = self._cx[i] - px, self._cy[i] - py
                d = dx * dx + dy * dy
                if d < best_d:
                    best_i, best_d = i, d
            limit = self.wall_limit + 80
            if best_d < limit * limit:
                return best_i
        best_i, best_d = 0, 1e18
        for i in range(self.n):
            dx, dy = self._cx[i] - px, self._cy[i] - py
            d = dx * dx + dy * dy
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    def project(self, pos: Vector2, hint: int | None = None, back: int = 6, fwd: int = 22) -> tuple[int, float, float]:
        i = self.nearest_index(pos, hint, back, fwd)
        rel = pos - self.center[i]
        s = (self.cum[i] + rel.dot(self.tangents[i])) % self.length
        return i, s, rel.dot(self.normals[i])

    def lateral_at(self, pos: Vector2, hint: int) -> tuple[float, Vector2]:
        i = self.nearest_index(pos, hint, back=6, fwd=6)
        return (pos - self.center[i]).dot(self.normals[i]), self.normals[i]

    def pose_at(self, s: float, lateral: float) -> tuple[Vector2, float]:
        s %= self.length
        i = max(0, bisect.bisect_right(self.cum, s) - 1)
        t = self.tangents[i]
        pos = self.center[i] + t * (s - self.cum[i]) + self.normals[i] * lateral
        return pos, math.atan2(t.y, t.x)

    def grid_pose(self, slot: int) -> tuple[Vector2, float]:
        row, col = divmod(slot, 2)
        back = 30.0 + row * 62.0 + col * 31.0
        lateral = (-1 if col == 0 else 1) * self.half_width * 0.42
        return self.pose_at(-back, lateral)

    def minimap_transform(self, box: pygame.Rect, pad: int = 8) -> tuple[float, Vector2]:
        min_x, max_x = min(self._cx), max(self._cx)
        min_y, max_y = min(self._cy), max(self._cy)
        scale = min((box.w - 2 * pad) / (max_x - min_x), (box.h - 2 * pad) / (max_y - min_y))
        off = Vector2(box.x + (box.w - (max_x - min_x) * scale) / 2 - min_x * scale,
                      box.y + (box.h - (max_y - min_y) * scale) / 2 - min_y * scale)
        return scale, off

    def draw_outline(self, surface: pygame.Surface, box: pygame.Rect, color: Color = (230, 230, 230),
                     width: int = 4) -> tuple[float, Vector2]:
        scale, off = self.minimap_transform(box)
        pts = [(p.x * scale + off.x, p.y * scale + off.y) for p in self.center[::2]]
        pygame.draw.lines(surface, (10, 10, 12), True, pts, width + 4)
        pygame.draw.lines(surface, color, True, pts, width)
        s = self.center[0] * scale + off
        nrm = self.normals[0] * 8
        pygame.draw.line(surface, (225, 6, 0), s - nrm, s + nrm, 3)
        return scale, off
