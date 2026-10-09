# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Sequence

import pygame
import pygame.gfxdraw
from pygame.math import Vector2

from .settings import SCREEN_HEIGHT, SCREEN_WIDTH, Color
from .i18n import tr
from .utils import lerp, vertical_gradient, wrap_angle

if TYPE_CHECKING:
    from .car import Car
    from .track import Track

CamPoint = tuple[float, float, float]

FOCAL = 720.0
NEAR = 6.0
FAR = 3400.0
CAMERA_MODES: list[tuple[str, float, float, float]] = [
    ("Verfolger", 150.0, 62.0, 0.11),
    ("Weit", 300.0, 150.0, 0.24),
    ("Onboard", -4.0, 13.0, 0.02),
    ("TV-Helikopter", 430.0, 380.0, 0.62),
]
HORIZON_Y = 300.0
WALL_HEIGHT = 13.0
FOG: Color = (178, 196, 214)

# Car model: tapered slabs (bottom rectangle at z0, top rectangle at z1) in car space, x forward, y right, z up.
# (bottom x0, x1, y0, y1), (top x0, x1, y0, y1), z0, z1, role, kept at distance (LOD)
_Slab = tuple[tuple[float, float, float, float], tuple[float, float, float, float], float, float, str, bool]


def _mirrored(x: tuple[float, float], y: tuple[float, float], z: tuple[float, float], role: str,
              top_x: tuple[float, float] | None = None, top_y: tuple[float, float] | None = None,
              lod: bool = False) -> list[_Slab]:
    """A part and its mirror image on the other side of the car (y given for the right-hand side)."""
    tx, ty = top_x or x, top_y or y
    return [((x[0], x[1], y[0], y[1]), (tx[0], tx[1], ty[0], ty[1]), z[0], z[1], role, lod),
            ((x[0], x[1], -y[1], -y[0]), (tx[0], tx[1], -ty[1], -ty[0]), z[0], z[1], role, lod)]


def _part(x: tuple[float, float], y: tuple[float, float], z: tuple[float, float], role: str,
          top_x: tuple[float, float] | None = None, top_y: tuple[float, float] | None = None,
          lod: bool = False) -> list[_Slab]:
    tx, ty = top_x or x, top_y or y
    return [((x[0], x[1], y[0], y[1]), (tx[0], tx[1], ty[0], ty[1]), z[0], z[1], role, lod)]


CAR_MODEL: list[_Slab] = [
    *_part((-14.0, 12.0), (-6.4, 6.4), (0.5, 1.2), "carbon", lod=True),                         # floor
    *_part((-17.2, -13.4), (-5.2, 5.2), (0.5, 2.8), "carbon", top_x=(-16.0, -13.4)),           # diffuser
    *_part((-6.0, 10.5), (-3.8, 3.8), (1.2, 4.8), "body", top_y=(-3.0, 3.0), lod=True),       # monocoque
    *_part((10.5, 17.2), (-2.2, 2.2), (1.3, 3.8), "body", top_x=(10.5, 16.2), top_y=(-1.3, 1.3), lod=True),
    *_mirrored((-9.5, 3.5), (3.6, 7.2), (1.2, 4.6), "body", top_x=(-6.0, 2.5), top_y=(3.6, 6.2), lod=True),
    *_mirrored((2.5, 3.6), (3.6, 7.0), (1.4, 4.2), "dark"),                                   # pod inlets
    *_part((-14.5, -2.0), (-3.6, 3.6), (4.6, 7.6), "body", top_x=(-9.0, -2.5), top_y=(-1.3, 1.3), lod=True),
    *_part((-4.6, -1.8), (-1.5, 1.5), (6.4, 9.6), "body", top_x=(-4.2, -2.4), top_y=(-1.0, 1.0)),  # airbox
    *_part((-3.6, -2.2), (-0.9, 0.9), (8.2, 9.0), "dark"),                                    # intake
    *_part((-12.0, -4.0), (-0.3, 0.3), (7.4, 9.0), "accent", top_x=(-11.0, -4.2)),            # shark fin
    *_part((-1.6, 4.8), (-2.3, 2.3), (4.6, 5.0), "carbon"),                                   # cockpit opening
    *_part((-0.2, 3.0), (-1.6, 1.6), (4.9, 7.4), "helmet", top_x=(0.2, 2.6), top_y=(-1.3, 1.3)),
    *_part((1.2, 3.0), (-1.62, 1.62), (6.0, 6.7), "visor"),                                   # visor band
    *_part((4.6, 5.4), (-0.4, 0.4), (4.8, 8.0), "carbon"),                                    # halo pillar
    *_mirrored((-1.2, 5.2), (2.2, 2.8), (7.4, 8.0), "carbon"),                                # halo hoop
    *_part((-1.6, -0.8), (-2.8, 2.8), (7.4, 8.0), "carbon"),                                  # halo rear
    *_mirrored((3.0, 4.6), (4.0, 5.6), (5.0, 6.0), "carbon"),                                 # mirrors
    *_part((5.0, 10.5), (-0.6, 0.6), (4.75, 4.85), "accent"),                                 # livery stripe
    # front wing: main plane, flap, endplates
    *_part((14.4, 18.0), (-8.4, 8.4), (0.4, 1.0), "carbon", lod=True),
    *_part((14.6, 16.6), (-8.2, 8.2), (1.0, 1.9), "body", top_x=(14.6, 15.8)),
    *_mirrored((13.8, 18.2), (8.2, 8.9), (0.4, 3.0), "body"),
    # rear wing: main plane, DRS flap, endplates, pylon, beam wing
    *_part((-17.8, -14.8), (-6.8, 6.8), (7.6, 8.4), "carbon", lod=True),
    *_part((-17.4, -15.6), (-6.6, 6.6), (8.6, 10.0), "body", top_x=(-17.2, -16.2), lod=True),
    *_mirrored((-18.2, -14.0), (6.6, 7.4), (3.0, 10.4), "body"),
    *_part((-16.6, -15.4), (-0.4, 0.4), (4.4, 7.6), "carbon"),
    *_part((-17.2, -15.4), (-5.0, 5.0), (3.4, 4.0), "carbon"),
    # suspension arms (front, rear)
    *_mirrored((8.6, 10.4), (3.8, 6.0), (2.4, 2.8), "carbon"),
    *_mirrored((-11.4, -9.6), (3.6, 5.8), (2.6, 3.0), "carbon"),
    # wheels and rims (rim colour = tyre compound)
    # each tyre is two slabs (lower half widening, upper half narrowing) for a rounder, hexagonal profile
    *_mirrored((8.1, 11.5), (5.2, 8.8), (0.0, 2.5), "tyre", top_x=(7.0, 12.6), lod=True),
    *_mirrored((7.0, 12.6), (5.2, 8.8), (2.5, 5.0), "tyre", top_x=(8.1, 11.5), lod=True),
    *_mirrored((8.9, 10.7), (8.8, 9.05), (1.6, 3.4), "rim"),
    *_mirrored((-12.4, -8.2), (5.0, 9.3), (0.0, 2.8), "tyre", top_x=(-13.6, -7.0), lod=True),
    *_mirrored((-13.6, -7.0), (5.0, 9.3), (2.8, 5.6), "tyre", top_x=(-12.4, -8.2), lod=True),
    *_mirrored((-11.4, -9.2), (9.3, 9.55), (1.8, 3.8), "rim"),
]

_Face = tuple[tuple[int, ...], tuple[float, float, float], tuple[float, float, float]]


def _slab_geometry(slab: _Slab) -> tuple[list[tuple[float, float, float]], list[_Face]]:
    """8 local vertices plus, per face, its vertex indices, outward normal and centre (all in car space)."""
    (bx0, bx1, by0, by1), (tx0, tx1, ty0, ty1), z0, z1, _, _ = slab
    v = [(bx0, by0, z0), (bx1, by0, z0), (bx1, by1, z0), (bx0, by1, z0),
         (tx0, ty0, z1), (tx1, ty0, z1), (tx1, ty1, z1), (tx0, ty1, z1)]
    cx = sum(p[0] for p in v) / 8
    cy = sum(p[1] for p in v) / 8
    cz = sum(p[2] for p in v) / 8
    faces: list[_Face] = []
    for idx in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        a, b, c = v[idx[0]], v[idx[1]], v[idx[2]]
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        wx, wy, wz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx, ny, nz = nx / length, ny / length, nz / length
        fc = (sum(v[k][0] for k in idx) / 4, sum(v[k][1] for k in idx) / 4, sum(v[k][2] for k in idx) / 4)
        if (fc[0] - cx) * nx + (fc[1] - cy) * ny + (fc[2] - cz) * nz < 0:
            nx, ny, nz = -nx, -ny, -nz
        faces.append((idx, (nx, ny, nz), fc))
    return v, faces


def _damage_tag(slab: _Slab) -> tuple[str, float]:
    """Which breakable part a slab belongs to ("fw" front wing, "rw" rear wing flap) and its side."""
    (x0, x1, y0, y1), _, z0, z1, _, _ = slab
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = 0.0 if abs(cy) < 1.0 else (1.0 if cy > 0 else -1.0)
    if cx > 13.5 and z1 <= 3.1:
        return "fw", side
    if cx < -14.0 and z0 >= 8.5:
        return "rw", side
    return "", side


_CAR_GEOMETRY = [(_slab_geometry(slab), slab[4], slab[5],
                  ((slab[0][0] + slab[0][1]) / 2, (slab[0][2] + slab[0][3]) / 2), _damage_tag(slab))
                 for slab in CAR_MODEL]
_LIGHT = (0.42, -0.52, 0.74)


_BOX_FACES: list[tuple[tuple[int, int, int, int], tuple[float, float, float]]] = [
    ((0, 2, 6, 4), (0, 0, -1)), ((1, 3, 7, 5), (0, 0, 1)),
    ((0, 1, 3, 2), (-1, 0, 0)), ((4, 5, 7, 6), (1, 0, 0)),
    ((0, 1, 5, 4), (0, -1, 0)), ((2, 3, 7, 6), (0, 1, 0)),
]


def _shade(color: Color, factor: float) -> Color:
    return (min(255, int(color[0] * factor)), min(255, int(color[1] * factor)), min(255, int(color[2] * factor)))


class Renderer3D:
    def __init__(self) -> None:
        self.sky = vertical_gradient((SCREEN_WIDTH, int(HORIZON_Y) + 40), (70, 120, 190), FOG)
        self.rain_sky = vertical_gradient((SCREEN_WIDTH, int(HORIZON_Y) + 40), (78, 84, 96), FOG)
        self.cam_heading = 0.0
        self.cam_pos = Vector2()
        self._initialized = False
        self._ground_cache: dict[Color, pygame.Surface] = {}
        self.font: pygame.font.Font | None = None
        self.mode = 0
        # anti-aliasing: "off", "edges" (smoothed polygon borders) or "high" (2x supersampling)
        self.antialias = "edges"
        self.ss = 1
        self.aa = True
        self._buf: pygame.Surface | None = None
        self._scaled: dict[tuple[int, int], pygame.Surface] = {}
        self._half_w, self._focal, self._hy = SCREEN_WIDTH / 2, FOCAL, HORIZON_Y

    @property
    def mode_name(self) -> str:
        return CAMERA_MODES[self.mode][0]

    @property
    def cam_dist(self) -> float:
        return CAMERA_MODES[self.mode][1]

    @property
    def cam_height(self) -> float:
        return CAMERA_MODES[self.mode][2]

    @property
    def pitch(self) -> float:
        return CAMERA_MODES[self.mode][3]

    def next_mode(self) -> str:
        self.mode = (self.mode + 1) % len(CAMERA_MODES)
        return self.mode_name

    def update_camera(self, target: "Car", dt: float) -> None:
        if not self._initialized:
            self.cam_heading = target.heading
            self._initialized = True
        diff = wrap_angle(target.heading - self.cam_heading)
        self.cam_heading = wrap_angle(self.cam_heading + diff * min(1.0, dt * 6.0))
        fwd = Vector2(math.cos(self.cam_heading), math.sin(self.cam_heading))
        self.cam_pos = target.pos - fwd * self.cam_dist

    def _setup(self) -> None:
        h = self.cam_heading
        self.fx, self.fy = math.cos(h), math.sin(h)
        self.rx, self.ry = -math.sin(h), math.cos(h)
        self.cx, self.cy, self.cz = self.cam_pos.x, self.cam_pos.y, self.cam_height
        self.cp, self.sp = math.cos(self.pitch), math.sin(self.pitch)

    def to_cam(self, x: float, y: float, z: float) -> CamPoint:
        dx, dy, up = x - self.cx, y - self.cy, z - self.cz
        fwd = dx * self.fx + dy * self.fy
        side = dx * self.rx + dy * self.ry
        return side, fwd * self.sp + up * self.cp, fwd * self.cp - up * self.sp

    def project(self, p: CamPoint) -> tuple[float, float]:
        return self._half_w + self._focal * p[0] / p[2], self._hy - self._focal * p[1] / p[2]

    def _big(self, img: pygame.Surface) -> pygame.Surface:
        """Background image at supersampling size (cached per source image)."""
        if self.ss == 1:
            return img
        key = (id(img), self.ss)
        out = self._scaled.get(key)
        if out is None:
            out = pygame.transform.smoothscale_by(img, self.ss)
            self._scaled[key] = out
        return out

    def _clip(self, pts: Sequence[CamPoint]) -> list[CamPoint]:
        out: list[CamPoint] = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            a_in, b_in = a[2] >= NEAR, b[2] >= NEAR
            if a_in:
                out.append(a)
            if a_in != b_in:
                t = (NEAR - a[2]) / (b[2] - a[2])
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, NEAR))
        return out

    def poly(self, surf: pygame.Surface, pts: Sequence[CamPoint], color: Color, fog_depth: float | None = None
             ) -> None:
        if all(p[2] < NEAR for p in pts):
            return
        if any(p[2] < NEAR for p in pts):
            pts = self._clip(pts)
            if len(pts) < 3:
                return
        if fog_depth is None:
            fog_depth = min(p[2] for p in pts)
        color = self.fog(color, fog_depth)
        screen_pts = [self.project(p) for p in pts]
        pygame.draw.polygon(surf, color, screen_pts)
        if self.aa:
            # blend the border into what is behind it: removes the stair steps on polygon edges
            pygame.draw.aalines(surf, color, True, screen_pts)

    @staticmethod
    def fog(color: Color, depth: float) -> Color:
        t = min(1.0, max(0.0, depth / FAR)) ** 1.6 * 0.85
        return (int(lerp(color[0], FOG[0], t)), int(lerp(color[1], FOG[1], t)), int(lerp(color[2], FOG[2], t)))

    def draw(self, surf: pygame.Surface, track: "Track", cars: Sequence["Car"], target: "Car",
             racing_line: bool, label_font: pygame.font.Font,
             garages: Sequence[tuple[Vector2, float, Color, str]] = (), rain: float = 0.0,
             guide: Sequence[Vector2] = ()) -> None:
        self.guide = guide
        self.ss = 2 if self.antialias == "high" else 1
        self.aa = self.antialias == "edges"
        out = surf
        if self.ss > 1:
            size = (SCREEN_WIDTH * self.ss, SCREEN_HEIGHT * self.ss)
            if self._buf is None or self._buf.get_size() != size:
                self._buf = pygame.Surface(size).convert()
            surf = self._buf
        self._half_w, self._focal, self._hy = SCREEN_WIDTH / 2 * self.ss, FOCAL * self.ss, HORIZON_Y * self.ss
        labels = self._draw_world(surf, track, cars, target, racing_line, garages, rain)
        if surf is not out:
            try:
                pygame.transform.smoothscale(surf, out.get_size(), out)
            except (ValueError, pygame.error):
                out.blit(pygame.transform.smoothscale(surf, out.get_size()), (0, 0))
        for (x, y), car in labels:
            txt = "DU" if car.is_player and car.short == "YOU" else car.short
            img = label_font.render(tr(txt), True, (0, 230, 255) if car.is_player else (250, 250, 250))
            out.blit(img, img.get_rect(midbottom=(x / self.ss, y / self.ss)))

    def _draw_world(self, surf: pygame.Surface, track: "Track", cars: Sequence["Car"], target: "Car",
                    racing_line: bool, garages: Sequence[tuple[Vector2, float, Color, str]],
                    rain: float) -> list[tuple[tuple[float, float], "Car"]]:
        self._setup()
        d = track.definition
        surf.blit(self._big(self.sky), (0, 0))
        if rain > 0.03:
            rain_sky = self._big(self.rain_sky)
            rain_sky.set_alpha(int(255 * min(1.0, rain * 1.6)))
            surf.blit(rain_sky, (0, 0))
        ground = self._ground_cache.get(d.grass)
        if ground is None:
            ground = vertical_gradient((SCREEN_WIDTH, SCREEN_HEIGHT - int(HORIZON_Y) + 120),
                                       self.fog(d.grass, FAR * 0.9), d.grass)
            self._ground_cache[d.grass] = ground
        horizon = self._hy - self._focal * math.tan(self.pitch)
        surf.blit(self._big(ground), (0, int(horizon)))

        n = track.n
        visible: list[tuple[float, int]] = []
        cx, cy = self.cx, self.cy
        for i in range(n):
            c = track.center[i]
            dx, dy = c.x - cx, c.y - cy
            fwd = dx * self.fx + dy * self.fy
            if fwd < -track.wall_limit - 40 or fwd > FAR:
                continue
            side = dx * self.rx + dy * self.ry
            if abs(side) > fwd * 1.05 + track.wall_limit * 2 + 60:
                continue
            visible.append((fwd, i))
        visible.sort(reverse=True)
        segments: list[tuple[float, int, int]] = []
        for fwd, i in visible:
            if fwd > 1300:
                if i % 2:
                    continue
                segments.append((fwd, i, (i + 2) % n))
            else:
                segments.append((fwd, i, (i + 1) % n))

        hw, wl = track.half_width, track.wall_limit
        to_cam = self.to_cam

        def edge(i: int, off: float, z: float = 0.0) -> CamPoint:
            p = track.center[i] + track.normals[i] * off
            return to_cam(p.x, p.y, z)

        for fwd, i, j in segments:
            for side in (-1, 1):
                self.poly(surf, [edge(i, side * hw), edge(j, side * hw), edge(j, side * wl), edge(i, side * wl)],
                          d.runoff_color)
        self._draw_pit_lane(surf, track)
        for fwd, i, j in segments:
            col = d.asphalt if (i // 4) % 2 else _shade(d.asphalt, 1.06)
            self.poly(surf, [edge(i, -hw), edge(j, -hw), edge(j, hw), edge(i, hw)], col)
        for fwd, i, j in segments:
            if track.curb_segment[i]:
                col = (215, 30, 30) if (i // 2) % 2 == 0 else (238, 238, 238)
                for side in (-1, 1):
                    self.poly(surf, [edge(i, side * (hw - 7)), edge(j, side * (hw - 7)), edge(j, side * (hw + 1)),
                                     edge(i, side * (hw + 1))], col)
            elif fwd < 1600:
                for side in (-1, 1):
                    self.poly(surf, [edge(i, side * (hw - 3)), edge(j, side * (hw - 3)), edge(j, side * (hw - 1)),
                                     edge(i, side * (hw - 1))], (230, 230, 230))
            if i == 0 or j == 0 and i > n - 3:
                for k in range(8):
                    lat = -hw + k * hw / 4
                    self.poly(surf, [edge(0, lat), edge(0, lat + hw / 8), edge(1, lat + hw / 8), edge(1, lat)],
                              (240, 240, 240))
        if racing_line and track.max_speed:
            self._draw_racing_line(surf, track, target)
        if getattr(self, "guide", None):
            self._draw_guide(surf, self.guide)

        objects: list[tuple[float, int, object]] = []
        wall_l, wall_r = track.wall_edges
        for fwd, i, j in segments:
            for edge_pts in (wall_l, wall_r):
                a, b = edge_pts[i], edge_pts[j]
                if a is not None and b is not None:
                    objects.append((fwd, 0, (a, b, (i // 3) % 2)))
        for item in track.scenery:
            p = item[1]
            dx, dy = p.x - cx, p.y - cy
            fwd = dx * self.fx + dy * self.fy
            if 20 < fwd < FAR * 0.9 and abs(dx * self.rx + dy * self.ry) < fwd * 1.1 + 100:
                objects.append((fwd, 1, item))
        for g in garages:
            dx, dy = g[0].x - cx, g[0].y - cy
            fwd = dx * self.fx + dy * self.fy
            if 10 < fwd < FAR * 0.8:
                objects.append((fwd, 3, g))
        for car in cars:
            if car is target and self.mode_name == "Onboard":
                continue
            dx, dy = car.pos.x - cx, car.pos.y - cy
            fwd = dx * self.fx + dy * self.fy
            if -30 < fwd < 2200 and abs(dx * self.rx + dy * self.ry) < fwd * 1.1 + 60:
                objects.append((fwd, 2, car))
        objects.sort(key=lambda o: -o[0])
        labels: list[tuple[tuple[float, float], "Car"]] = []
        for fwd, kind, obj in objects:
            if kind == 0:
                a, b, alt = obj
                col = d.wall_a if alt else d.wall_b
                self.poly(surf, [to_cam(a.x, a.y, 0), to_cam(b.x, b.y, 0), to_cam(b.x, b.y, WALL_HEIGHT),
                                 to_cam(a.x, a.y, WALL_HEIGHT)], col)
            elif kind == 1:
                self._draw_scenery(surf, obj)
            elif kind == 3:
                pos, heading, color, _team = obj
                self._draw_oriented_box(surf, pos, heading, 24, 16, 26, (88, 90, 98))
                self._draw_oriented_box(surf, pos, heading, 24.5, 16.5, 30, color, z0=26)
            else:
                car = obj
                self._draw_car(surf, car, fwd)
                if fwd < 1100 and car is not target:
                    top = to_cam(car.pos.x, car.pos.y, 22)
                    if top[2] > NEAR:
                        labels.append((self.project(top), car))
        return labels

    def _draw_racing_line(self, surf: pygame.Surface, track: "Track", car: "Car") -> None:
        n = track.n
        for k in range(0, 140, 2):
            i = (car.idx + k) % n
            j = (i + 2) % n
            col = (230, 40, 40) if track.brake_zone[i] else (240, 210, 40) if track.max_speed[i] < car.top_speed * 0.9 \
                else (40, 220, 90)
            a, b = track.racing_line[i], track.racing_line[j]
            na, nb = track.normals[i] * 3, track.normals[j] * 3
            pts = [self.to_cam(a.x - na.x, a.y - na.y, 0.3), self.to_cam(b.x - nb.x, b.y - nb.y, 0.3),
                   self.to_cam(b.x + nb.x, b.y + nb.y, 0.3), self.to_cam(a.x + na.x, a.y + na.y, 0.3)]
            self.poly(surf, pts, col)

    def _draw_guide(self, surf: pygame.Surface, pts: Sequence[Vector2]) -> None:
        """The way into the pits as a glowing strip on the road."""
        for a, b in zip(pts, pts[1:]):
            d = b - a
            if d.length_squared() < 1:
                continue
            n = Vector2(-d.y, d.x).normalize() * 2.6
            quad = [self.to_cam(a.x - n.x, a.y - n.y, 0.35), self.to_cam(b.x - n.x, b.y - n.y, 0.35),
                    self.to_cam(b.x + n.x, b.y + n.y, 0.35), self.to_cam(a.x + n.x, a.y + n.y, 0.35)]
            self.poly(surf, quad, (0, 210, 255))

    def _draw_pit_lane(self, surf: pygame.Surface, track: "Track") -> None:
        pit = track.pit
        if pit is None:
            return
        edges = getattr(track, "_pit_edges_3d", None)
        if edges is None:
            edges = pit.outline(24.0)
            track._pit_edges_3d = edges
        to_cam = self.to_cam
        for (l0, r0), (l1, r1) in zip(edges, edges[1:]):
            mid = (l0 + r1) * 0.5
            if (mid.x - self.cx) * self.fx + (mid.y - self.cy) * self.fy > FAR:
                continue
            self.poly(surf, [to_cam(l0.x, l0.y, 0), to_cam(l1.x, l1.y, 0), to_cam(r1.x, r1.y, 0),
                             to_cam(r0.x, r0.y, 0)], (52, 53, 58))

    def _draw_oriented_box(self, surf: pygame.Surface, pos: Vector2, heading: float, half_l: float,
                           half_w: float, height: float, color: Color, z0: float = 0.0) -> None:
        fx, fy = math.cos(heading), math.sin(heading)
        rx, ry = -fy, fx
        corners = []
        for lx in (-half_l, half_l):
            for ly in (-half_w, half_w):
                for z in (z0, z0 + height):
                    corners.append(self.to_cam(pos.x + fx * lx + rx * ly, pos.y + fy * lx + ry * ly, z))
        for idx, (nx, ny, nz) in _BOX_FACES:
            if nz < 0:
                continue
            if nz == 0:
                wnx, wny = fx * nx + rx * ny, fy * nx + ry * ny
                fcx = pos.x + (fx * half_l * nx + rx * half_w * ny)
                fcy = pos.y + (fy * half_l * nx + ry * half_w * ny)
                if (self.cx - fcx) * wnx + (self.cy - fcy) * wny <= 0:
                    continue
                light = 0.8 + 0.2 * (wnx * 0.6 - wny * 0.8)
            else:
                if self.cz < z0 + height:
                    continue
                light = 1.1
            self.poly(surf, [corners[k] for k in idx], _shade(color, light))

    def _draw_scenery(self, surf: pygame.Surface, item: tuple) -> None:
        if item[0] == "building":
            _, p, w, h, col, height = item
            box = (p.x - w / 2, p.x + w / 2, p.y - h / 2, p.y + h / 2, 0.0, float(height))
            self._draw_box_world(surf, box, col)
        else:
            _, p, r, col, height = item
            base = self.to_cam(p.x, p.y, 0)
            top = self.to_cam(p.x, p.y, height)
            if base[2] < NEAR or top[2] < NEAR:
                return
            bx, by = self.project(base)
            tx, ty = self.project(top)
            trunk_w = max(1, int(self._focal * 2.5 / base[2]))
            pygame.draw.line(surf, self.fog((90, 60, 35), base[2]), (bx, by), (tx, ty), trunk_w)
            rad = max(2, int(self._focal * r / top[2]))
            for (cx, cy), cr, cc in (((tx, ty + rad * 0.15), rad, self.fog(_shade(col, 0.7), top[2])),
                                     ((tx - rad * 0.15, ty), int(rad * 0.85), self.fog(col, top[2]))):
                pygame.draw.circle(surf, cc, (cx, cy), cr)
                if self.aa:
                    pygame.gfxdraw.aacircle(surf, int(cx), int(cy), cr, cc)

    def _draw_box_world(self, surf: pygame.Surface, box: tuple[float, ...], color: Color) -> None:
        x0, x1, y0, y1, z0, z1 = box
        cam = [self.to_cam(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        sides = [((0, 1, 3, 2), self.cx < x0, 0.75), ((4, 5, 7, 6), self.cx > x1, 0.75),
                 ((0, 1, 5, 4), self.cy < y0, 0.95), ((2, 3, 7, 6), self.cy > y1, 0.95)]
        for idx, visible, shade in sides:
            if visible:
                self.poly(surf, [cam[k] for k in idx], _shade(color, shade))
        if self.cz > z1:
            self.poly(surf, [cam[1], cam[3], cam[7], cam[5]], _shade(color, 1.15))

    def _draw_car(self, surf: pygame.Surface, car: "Car", depth: float) -> None:
        h = car.heading
        fx, fy, rx, ry = math.cos(h), math.sin(h), -math.sin(h), math.cos(h)
        px, py = car.pos.x, car.pos.y
        body = car.color
        rim = car.tyres.compound.color if car.tyres is not None else (150, 150, 158)
        colors = {"body": body, "helmet": car.profile.helmet, "dark": _shade(body, 0.45), "carbon": (30, 30, 34),
                  "tyre": (22, 22, 24), "rim": rim, "visor": (12, 12, 16),
                  "accent": (min(255, body[0] + 70), min(255, body[1] + 70), min(255, body[2] + 70))}
        if car.ghost_visual:
            # practice/qualifying ghosts: washed out towards the fog so they read as see-through
            colors = {k: (int(c[0] * 0.45 + FOG[0] * 0.55), int(c[1] * 0.45 + FOG[1] * 0.55),
                          int(c[2] * 0.45 + FOG[2] * 0.55)) for k, c in colors.items()}
        near = depth < 700
        cam_l = ((self.cx - px) * fx + (self.cy - py) * fy, (self.cx - px) * rx + (self.cy - py) * ry)
        shadow = [self.to_cam(px + fx * lx + rx * ly, py + fy * lx + ry * ly, 0.2)
                  for lx, ly in ((-17, -8), (17, -8), (17, 8), (-17, 8))]
        self.poly(surf, shadow, (25, 25, 28))
        d = car.damage

        def intact(tag: tuple[str, float]) -> bool:
            # broken parts fall off: first the endplate on the side that hit, then the whole wing
            kind, side = tag
            if kind == "fw":
                return d.front_wing < 0.5 or (d.front_wing < 0.85 and side != d.wing_side)
            if kind == "rw":
                return d.rear < 0.7
            return True
        parts = [g for g in _CAR_GEOMETRY if (near or g[2]) and intact(g[4])]
        # painter's order: far parts first (horizontal distance to the camera in car space)
        parts.sort(key=lambda g: -((g[3][0] - cam_l[0]) ** 2 + (g[3][1] - cam_l[1]) ** 2))
        lx_, ly_, lz_ = _LIGHT
        for (verts, faces), role, _, _, _ in parts:
            cam = None
            col = colors[role]
            for idx, (nx, ny, nz), (fcx, fcy, fcz) in faces:
                # world-space normal and face centre -> back-face test against the camera
                wnx, wny = fx * nx + rx * ny, fy * nx + ry * ny
                wcx, wcy = px + fx * fcx + rx * fcy, py + fy * fcx + ry * fcy
                if (self.cx - wcx) * wnx + (self.cy - wcy) * wny + (self.cz - fcz) * nz <= 0:
                    continue
                if cam is None:
                    cam = [self.to_cam(px + fx * vx + rx * vy, py + fy * vx + ry * vy, vz) for vx, vy, vz in verts]
                light = 0.62 + 0.45 * max(0.0, wnx * lx_ + wny * ly_ + nz * lz_)
                self.poly(surf, [cam[k] for k in idx], _shade(col, light), depth)
