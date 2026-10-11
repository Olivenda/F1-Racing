# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Sequence

import pygame
import pygame.gfxdraw
from pygame.math import Vector2

from .settings import CAR_LENGTH, SCREEN_HEIGHT, SCREEN_WIDTH, TOP_SPEED, Color
from .flags import marshal_posts
from .i18n import tr
from .utils import clamp, draw_panel, vertical_gradient, wrap_angle

if TYPE_CHECKING:
    from .car import Car
    from .effects import Effects
    from .track import Track

CamPoint = tuple[float, float, float]

FOCAL = 720.0
NEAR = 6.0
FAR = 3400.0
FOG_END = 0.94           # share of the view distance where the fog is complete: nothing pops in at the edge
HORIZON_Y = 300.0
WALL_HEIGHT = 13.0
FOG: Color = (178, 196, 214)
TAU = math.tau


@dataclass(frozen=True)
class CamMode:
    """One camera. chase/heli: dist behind the car, height above the road. onboard: dist is the eye position
    along the car (+ = forward), height above the road. track: fixed trackside TV cameras that pan and zoom."""
    name: str
    kind: str
    dist: float = 0.0
    height: float = 0.0
    pitch: float = 0.0
    focal: float = FOCAL
    near: float = NEAR
    hide: tuple[str, ...] = ()       # parts of the followed car the camera sits inside
    cockpit: bool = False
    shake: float = 0.0
    lens: bool = False               # rain drops collect on the lens


CAMERA_MODES: list[CamMode] = [
    CamMode("Verfolger", "chase", 150.0, 62.0, 0.11, shake=0.35),
    CamMode("Weit", "chase", 300.0, 150.0, 0.24, shake=0.15),
    CamMode("Cockpit", "onboard", -0.2, 7.7, 0.0, focal=560.0, near=0.35, hide=("helmet", "visor", "halo", "mirror"),
            cockpit=True, shake=1.0, lens=True),
    CamMode("T-Cam", "onboard", -2.3, 10.5, 0.12, focal=560.0, near=0.5, hide=("tcam",), shake=0.8, lens=True),
    CamMode("Nasenkamera", "onboard", 12.4, 4.9, 0.05, focal=500.0, near=0.35, shake=1.1, lens=True),
    CamMode("Streckenkamera", "track", shake=0.0),
    CamMode("TV-Helikopter", "heli", 430.0, 380.0, 0.62),
]

# per track: sky colours, sun position and what lies on the horizon
_SKY_DAY = ((58, 112, 188), (182, 200, 218))
_TRACK_LOOK: dict[str, dict] = {
    "monaco": {"sky": ((52, 108, 196), (190, 208, 226)), "sun": (2.3, 0.20),
               "pano": [("mountains", 0.060, (86, 102, 96), 0.62), ("skyline", 0.030, (176, 160, 140), 0.75)]},
    "monza": {"sky": ((64, 118, 190), (188, 204, 214)), "sun": (-0.9, 0.17),
              "pano": [("hills", 0.024, (92, 112, 110), 0.50), ("trees", 0.018, (40, 74, 42), 0.80)]},
    "silverstone": {"sky": ((88, 128, 182), (196, 206, 216)), "sun": (0.6, 0.14),
                    "pano": [("hills", 0.018, (90, 112, 100), 0.50), ("trees", 0.016, (44, 80, 46), 0.80)]},
    "spa": {"sky": ((82, 116, 166), (178, 190, 204)), "sun": (1.4, 0.18),
            "pano": [("mountains", 0.050, (52, 80, 62), 0.60), ("conifers", 0.028, (28, 56, 36), 0.85)]},
    "interlagos": {"sky": ((70, 124, 196), (206, 206, 200)), "sun": (-2.2, 0.22),
                   "pano": [("hills", 0.024, (104, 116, 96), 0.50), ("skyline", 0.034, (150, 146, 142), 0.65)]},
    "marinabay": {"night": True, "sky": ((6, 8, 22), (40, 36, 62)), "sun": (0.4, 0.30),
                  "pano": [("skyline", 0.060, (22, 22, 40), 0.9), ("skyline", 0.030, (14, 14, 26), 1.0)]},
}
_RAIN_SKY = ((74, 80, 92), (146, 152, 162))
SPONSORS: list[tuple[Color, Color]] = [
    ((215, 20, 35), (250, 250, 250)), ((255, 200, 0), (30, 30, 30)), ((20, 80, 190), (250, 250, 250)),
    ((26, 26, 30), (240, 60, 40)), ((0, 140, 85), (250, 250, 250)), ((245, 245, 245), (210, 20, 30)),
    ((240, 120, 0), (20, 20, 24)), ((120, 40, 160), (250, 220, 60)),
]
CROWD = [(220, 40, 40), (250, 250, 250), (255, 205, 40), (40, 90, 210), (30, 30, 34), (240, 130, 30),
         (60, 170, 80), (200, 200, 210)]

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
    *_part((15.4, 17.3), (-1.0, 1.0), (1.4, 3.0), "accent", top_x=(15.4, 16.6), top_y=(-0.7, 0.7)),  # nose tip
    # sidepods with the modern undercut: narrow at the floor, widest at the shoulder, tapering to the top
    *_mirrored((-8.6, 3.0), (3.6, 5.6), (1.2, 2.8), "body", top_x=(-9.2, 3.4), top_y=(3.6, 7.2), lod=True),
    *_mirrored((-9.2, 3.4), (3.6, 7.2), (2.8, 4.6), "body", top_x=(-6.0, 2.5), top_y=(3.6, 6.2), lod=True),
    *_mirrored((-10.5, 4.5), (6.4, 7.6), (0.5, 1.1), "carbon", top_x=(-10.0, 4.0)),            # floor edge wing
    *_mirrored((4.0, 7.0), (5.6, 6.6), (0.6, 2.4), "carbon", top_x=(4.4, 6.6)),               # bargeboard
    *_mirrored((-5.0, 2.0), (6.0, 7.25), (2.0, 3.0), "accent"),                                # sidepod stripe
    *_mirrored((2.5, 3.6), (3.6, 7.0), (1.4, 4.2), "dark"),                                   # pod inlets
    *_part((-14.5, -2.0), (-3.6, 3.6), (4.6, 7.6), "body", top_x=(-9.0, -2.5), top_y=(-1.3, 1.3), lod=True),
    *_part((-4.6, -1.8), (-1.5, 1.5), (6.4, 9.6), "body", top_x=(-4.2, -2.4), top_y=(-1.0, 1.0)),  # airbox
    *_part((-3.6, -2.2), (-0.9, 0.9), (8.2, 9.0), "dark"),                                    # intake
    *_part((-3.8, -2.6), (-0.45, 0.45), (9.6, 10.2), "tcam"),                                 # T-cam pod
    *_part((-12.0, -4.0), (-0.3, 0.3), (7.4, 9.0), "accent", top_x=(-11.0, -4.2)),            # shark fin
    *_part((-1.6, 4.8), (-2.3, 2.3), (4.6, 5.0), "carbon"),                                   # cockpit opening
    *_part((-0.2, 3.0), (-1.6, 1.6), (4.9, 7.4), "helmet", top_x=(0.2, 2.6), top_y=(-1.3, 1.3)),
    *_part((1.2, 3.0), (-1.62, 1.62), (6.0, 6.7), "visor"),                                   # visor band
    *_part((4.6, 5.4), (-0.4, 0.4), (4.8, 8.0), "halo"),                                      # halo pillar
    *_mirrored((-1.2, 5.2), (2.2, 2.8), (7.4, 8.0), "halo"),                                  # halo hoop
    *_part((-1.6, -0.8), (-2.8, 2.8), (7.4, 8.0), "halo"),                                    # halo rear
    *_mirrored((3.0, 4.6), (4.0, 5.6), (5.0, 6.0), "mirror"),                                 # mirrors
    *_part((5.0, 10.5), (-0.6, 0.6), (4.75, 4.85), "accent"),                                 # livery stripe
    # front wing: main plane, flap, endplates
    *_part((14.4, 18.0), (-8.4, 8.4), (0.4, 1.0), "carbon", lod=True),
    *_part((14.6, 16.6), (-8.2, 8.2), (1.0, 1.9), "accent", top_x=(14.6, 15.8)),
    *_part((14.5, 15.7), (-7.9, 7.9), (1.9, 2.6), "body", top_x=(14.4, 15.0)),                # second flap
    *_mirrored((13.8, 18.2), (8.2, 8.9), (0.4, 3.0), "body"),
    # rear wing: main plane, DRS flap (closed / open), endplates, pylon, beam wing, rain light
    *_part((-17.8, -14.8), (-6.8, 6.8), (7.6, 8.4), "carbon", lod=True),
    *_part((-17.4, -15.6), (-6.6, 6.6), (8.6, 10.0), "body", top_x=(-17.2, -16.2), lod=True),
    *_part((-17.8, -15.0), (-6.6, 6.6), (9.7, 10.1), "body"),
    *_mirrored((-18.2, -14.0), (6.6, 7.4), (3.0, 10.4), "accent"),
    *_part((-16.6, -15.4), (-0.4, 0.4), (4.4, 7.6), "carbon"),
    *_part((-17.2, -15.4), (-5.0, 5.0), (3.4, 4.0), "carbon"),
    *_part((-17.9, -17.2), (-0.6, 0.6), (2.8, 3.8), "rainlight"),
    *_part((-16.8, -13.0), (-1.4, 1.4), (1.6, 3.4), "carbon", top_x=(-16.4, -13.0), top_y=(-1.0, 1.0)),  # crash box
    *_part((-16.0, -14.2), (-0.55, 0.55), (4.1, 5.0), "dark"),                                # exhaust
    # suspension arms (front, rear)
    *_mirrored((8.6, 10.4), (3.8, 6.0), (2.4, 2.8), "carbon"),
    *_mirrored((-11.4, -9.6), (3.6, 5.8), (2.6, 3.0), "carbon"),
    # wheels: round, spinning - built separately (see _wheel_parts)
]

# Safety car: a GT road car (front axle at the same x as the F1 car, so the steering pivot fits)
SC_MODEL: list[_Slab] = [
    *_part((-15.0, 14.6), (-6.6, 6.6), (1.0, 4.2), "body", top_x=(-14.4, 13.4), top_y=(-6.4, 6.4), lod=True),
    *_part((3.0, 13.4), (-6.2, 6.2), (4.2, 5.0), "body", top_x=(4.6, 12.0), top_y=(-5.4, 5.4), lod=True),   # bonnet
    *_part((-15.0, -8.5), (-6.2, 6.2), (4.2, 5.4), "body", top_x=(-14.6, -8.0), top_y=(-5.8, 5.8), lod=True),
    *_part((-8.6, 3.2), (-5.6, 5.6), (4.2, 7.4), "glass", top_x=(-6.6, 0.6), top_y=(-4.4, 4.4), lod=True),
    *_part((-6.6, 0.6), (-4.4, 4.4), (7.4, 7.8), "body", top_x=(-6.0, 0.0), top_y=(-4.2, 4.2), lod=True),   # roof
    *_part((13.0, 15.4), (-6.2, 6.2), (0.6, 1.4), "carbon"),                                   # splitter
    *_part((14.3, 15.0), (-3.0, 3.0), (1.6, 3.4), "dark"),                                     # grille
    *_mirrored((12.4, 14.2), (3.2, 5.6), (3.4, 4.4), "headlight"),
    *_part((-15.3, -13.4), (-5.4, 5.4), (5.4, 6.2), "carbon"),                                 # spoiler
    *_mirrored((-15.4, -14.8), (3.0, 5.8), (3.4, 4.4), "taillight"),
    *_mirrored((-12.0, 11.0), (6.5, 6.75), (2.3, 3.0), "accent"),                              # side stripe
    *_mirrored((1.0, 2.4), (5.6, 7.0), (5.0, 5.8), "body"),                                    # mirrors
    *_part((-3.8, -1.4), (-3.9, 3.9), (7.8, 8.3), "dark"),                                     # light bar base
    *_part((-3.6, -1.6), (-3.7, -0.2), (8.3, 9.2), "sc_l"),
    *_part((-3.6, -1.6), (0.2, 3.7), (8.3, 9.2), "sc_r"),
    # wheels: see _wheel_parts
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


def _tag(slab: _Slab) -> tuple[str, float, int]:
    """Special parts: breakable front wing ("fw") / rear wing flap ("rw"), the two DRS flap positions and the
    steered front wheels ("steer"). Plus the side of the car the part is on and, for tyres and rims, which wheel
    it belongs to (0 front left, 1 front right, 2 rear left, 3 rear right; -1 = not a wheel)."""
    (x0, x1, y0, y1), (tx0, _tx1, _ty0, _ty1), z0, z1, role, _ = slab
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = 0.0 if abs(cy) < 1.0 else (1.0 if cy > 0 else -1.0)
    if role in ("tyre", "rim", "band"):
        wheel = (0 if cx > 0 else 2) + (1 if cy > 0 else 0)
        return ("steer" if cx > 5 else ""), side, wheel
    if cx > 13.5 and z1 <= 3.1 and role != "accent" or cx > 13.5 and role == "accent" and z1 < 2.0:
        return "fw", side, -1
    if cx < -14.0 and z0 >= 8.5:
        if z0 >= 9.6:
            return "drs_open", side, -1
        return "rw", side, -1
    return "", side, -1


# Wheels per side (right-hand side; the left is mirrored): (axle x, radius, inner y, outer y). The tyres are
# cylinders, so they look round from every angle; the rims carry spokes that turn with the car's speed.
_CAR_WHEELS: list[tuple[float, float, float, float]] = [(9.8, 2.5, 5.2, 8.8), (-10.3, 2.8, 5.0, 9.3)]
_SC_WHEELS: list[tuple[float, float, float, float]] = [(9.8, 2.6, 5.0, 6.9), (-9.8, 2.6, 5.0, 6.9)]
WHEEL_SIDES = 14
SPOKES = 5
SPIN_BLUR = 24.0            # rad/s: faster than this the spokes smear into a disc


def _disc_face(cx: float, cz: float, r: float, y: float, side: float, n: int, rot: float = 0.0
               ) -> tuple[tuple[float, float, float], ...]:
    return tuple((cx + r * math.cos(rot + k * TAU / n), y, cz + r * math.sin(rot + k * TAU / n)) for k in range(n))


def _faces_part(polys: list[tuple[tuple[float, float, float], ...]], normals: list[tuple[float, float, float]]
                ) -> tuple[list[tuple[float, float, float]], list[_Face]]:
    """Geometry from loose polygons (each with its outward normal) in the format of _slab_geometry."""
    verts: list[tuple[float, float, float]] = []
    faces: list[_Face] = []
    for poly, nrm in zip(polys, normals):
        start = len(verts)
        verts.extend(poly)
        fc = (sum(v[0] for v in poly) / len(poly), sum(v[1] for v in poly) / len(poly),
              sum(v[2] for v in poly) / len(poly))
        faces.append((tuple(range(start, start + len(poly))), nrm, fc))
    return verts, faces


def _wheel_static(specs: list[tuple[float, float, float, float]]) -> list[tuple]:
    """Tyre cylinders, compound-coloured sidewall rings and rims of the four wheels (parts as in _CAR_GEOMETRY)."""
    out = []
    n = WHEEL_SIDES
    for axle, (x, r, y0, y1) in enumerate(specs):
        cz = r
        for side in (1.0, -1.0):
            wheel = (0 if axle == 0 else 2) + (1 if side > 0 else 0)
            tag = ("steer" if axle == 0 else "", side, wheel)
            a, b = y0 * side, y1 * side
            ring_a = [(x + r * math.cos(k * TAU / n), a, cz + r * math.sin(k * TAU / n)) for k in range(n)]
            ring_b = [(vx, b, vz) for vx, _, vz in ring_a]
            polys, normals = [], []
            for k in range(n):
                m = (k + 1) % n
                ang = (k + 0.5) * TAU / n
                polys.append((ring_a[k], ring_a[m], ring_b[m], ring_b[k]))
                normals.append((math.cos(ang), 0.0, math.sin(ang)))
            polys += [tuple(ring_a), tuple(ring_b)]
            normals += [(0.0, -side, 0.0), (0.0, side, 0.0)]
            out.append((_faces_part(polys, normals), "tyre", True, (x, (y0 + y1) / 2 * side), tag))
            face = b + 0.06 * side
            for role, rr, dy in (("band", r * 0.84, 0.0), ("tyre", r * 0.74, 0.04), ("rim", r * 0.66, 0.08)):
                out.append((_faces_part([_disc_face(x, cz, rr, face + dy * side, side, n)], [(0.0, side, 0.0)]),
                            role, False, (x, face * 1.0 + (0.1 + dy) * side), tag))
    return out


SPOKE_STEPS = 24            # wheel angles precomputed per 1/SPOKES turn (the pattern repeats after that)
_SPOKE_CACHE: dict[tuple, tuple] = {}


def _spoke_part(spec: tuple[float, float, float, float], axle: int, side: float, step: int, blur: bool) -> tuple:
    """One rim's spokes as a single star-shaped polygon (or, spinning fast, a smeared disc), cached per angle."""
    key = (spec, axle, side, -1 if blur else step)
    part = _SPOKE_CACHE.get(key)
    if part is not None:
        return part
    x, r, _y0, y1 = spec
    cz = r
    y = (y1 + 0.2) * side
    wheel = (0 if axle == 0 else 2) + (1 if side > 0 else 0)
    tag = ("steer" if axle == 0 else "", side, wheel)
    if blur:
        poly = _disc_face(x, cz, r * 0.6, y, side, 10)
        role = "spoke_blur"
    else:
        rot = step * TAU / SPOKES / SPOKE_STEPS
        hub, tip = r * 0.2, r * 0.62
        half_hub, half_tip = 0.32 / hub, 0.32 / tip         # half the spoke width as an angle at each radius
        pts = []
        for k in range(SPOKES):
            a = rot + k * TAU / SPOKES
            for ang, rad in ((a - half_hub, hub), (a - half_tip, tip), (a + half_tip, tip), (a + half_hub, hub)):
                pts.append((x + rad * math.cos(ang), y, cz + rad * math.sin(ang)))
        poly = tuple(pts)
        role = "spoke"
    part = (_faces_part([poly], [(0.0, side, 0.0)]), role, False, (x, y + 0.1 * side), tag)
    _SPOKE_CACHE[key] = part
    return part


def _wheel_spokes(specs: list[tuple[float, float, float, float]], rot: tuple[float, float], blur: tuple[bool, bool]
                  ) -> list[tuple]:
    """The spokes of all four rims at this frame's wheel angles."""
    out = []
    for axle, spec in enumerate(specs):
        step = int(rot[axle] % (TAU / SPOKES) / (TAU / SPOKES) * SPOKE_STEPS) % SPOKE_STEPS
        for side in (1.0, -1.0):
            out.append(_spoke_part(spec, axle, side, step, blur[axle]))
    return out


_CAR_GEOMETRY = [(_slab_geometry(slab), slab[4], slab[5],
                  ((slab[0][0] + slab[0][1]) / 2, (slab[0][2] + slab[0][3]) / 2), _tag(slab))
                 for slab in CAR_MODEL]
_SC_GEOMETRY = [(_slab_geometry(slab), slab[4], slab[5],
                 ((slab[0][0] + slab[0][1]) / 2, (slab[0][2] + slab[0][3]) / 2), _tag(slab))
                for slab in SC_MODEL]
_CAR_GEOMETRY += _wheel_static(_CAR_WHEELS)
_SC_GEOMETRY += _wheel_static(_SC_WHEELS)
_LIGHT = (0.42, -0.52, 0.74)
_SHADOW_OFF = (-_LIGHT[0] / _LIGHT[2] * 3.0, -_LIGHT[1] / _LIGHT[2] * 3.0)
_WHEEL_PIVOT = 9.8          # x of the front axle (car space)


_BOX_FACES: list[tuple[tuple[int, int, int, int], tuple[float, float, float]]] = [
    ((0, 2, 6, 4), (0, 0, -1)), ((1, 3, 7, 5), (0, 0, 1)),
    ((0, 1, 3, 2), (-1, 0, 0)), ((4, 5, 7, 6), (1, 0, 0)),
    ((0, 1, 5, 4), (0, -1, 0)), ((2, 3, 7, 6), (0, 1, 0)),
]


def _shade(color: Color, factor: float) -> Color:
    return (min(255, int(color[0] * factor)), min(255, int(color[1] * factor)), min(255, int(color[2] * factor)))


def _clip_screen(pts: list[tuple[float, float]], x0: float, y0: float, x1: float, y1: float
                 ) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a screen polygon to a rectangle. pygame fills polygons scanline by scanline over
    their whole height, so a vertex projected 50000 px off-screen (close to the near plane) costs milliseconds."""
    for axis, limit, keep_greater in ((0, x0, True), (0, x1, False), (1, y0, True), (1, y1, False)):
        if not pts:
            return pts
        out = []
        prev = pts[-1]
        prev_in = prev[axis] >= limit if keep_greater else prev[axis] <= limit
        for cur in pts:
            cur_in = cur[axis] >= limit if keep_greater else cur[axis] <= limit
            if cur_in != prev_in:
                t = (limit - prev[axis]) / (cur[axis] - prev[axis])
                if axis == 0:
                    out.append((limit, prev[1] + (cur[1] - prev[1]) * t))
                else:
                    out.append((prev[0] + (cur[0] - prev[0]) * t, limit))
            if cur_in:
                out.append(cur)
            prev, prev_in = cur, cur_in
        pts = out
    return pts


def _mix(a: Color, b: Color, t: float) -> Color:
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _fade(col: Color, base: Color, fwd: float, cut: float) -> Color:
    """A detail drawn only up to the distance cut: towards the cut it melts into the colour under it, so it fades
    in while driving instead of popping in as a line."""
    k = (cut - fwd) / (cut * 0.3)
    if k >= 1.0:
        return col
    return _mix(base, col, max(0.0, k))


@dataclass
class _Env:
    zenith: Color
    haze: Color
    fog_far: float
    night: bool
    sun: bool
    rain: float
    wet: float
    look: dict


class Renderer3D:
    _fonts: dict[str, pygame.font.Font] = {}
    _glow_cache: dict[tuple[int, Color], pygame.Surface] = {}
    _blob_cache: dict[tuple[int, Color, int], pygame.Surface] = {}

    def __init__(self) -> None:
        self.cam_heading = 0.0
        self.cam_pos = Vector2()
        self.cam_z = 62.0
        self.pitch = 0.11
        self.roll = 0.0
        self.focal = FOCAL
        self.near = NEAR
        self._initialized = False
        self.mode = 0
        # anti-aliasing: "off", "edges" (smoothed polygon borders) or "high" (2x supersampling)
        self.antialias = "edges"
        # graphics detail: "low" (bare track), "medium" (+ trackside detail), "high" (+ post effects, mirrors)
        self.detail = "high"
        self.ss = 1
        self.aa = True
        self.time = 0.0
        self.target: "Car | None" = None
        self._buf: pygame.Surface | None = None
        self._scaled: dict[object, pygame.Surface] = {}
        self._half_w, self._focal, self._hy = SCREEN_WIDTH / 2, FOCAL, HORIZON_Y
        self._clip_w, self._clip_h = SCREEN_WIDTH, SCREEN_HEIGHT
        self._fog_col: Color = FOG
        self._fog_inv = 1.0 / (FAR * FOG_END)
        self._far = FAR
        self._amb: tuple[float, float, float] | None = None
        self._glows: list[tuple[float, float, float, Color]] | None = []
        self._sun_screen: tuple[float, float] | None = None
        self._last_speed = 0.0
        self._last_heading = 0.0
        self._accel = 0.0
        self._lat = 0.0
        self._jolt = 0.0
        self._tv_cam: int | None = None
        self._heat: dict[int, float] = {}
        self._wheel_rot: dict[int, tuple[float, float]] = {}
        self._drops: list[list[float]] = []
        self._mirror: pygame.Surface | None = None
        self._mirror_tick = 0
        self._wheel_cache: dict[Color, pygame.Surface] = {}
        self.to_cam: Callable[[float, float, float], CamPoint] = self._to_cam_flat
        self._setup()

    # ------------------------------------------------------------------ camera
    @property
    def cam(self) -> CamMode:
        return CAMERA_MODES[self.mode % len(CAMERA_MODES)]

    @property
    def mode_name(self) -> str:
        return self.cam.name

    @property
    def onboard(self) -> bool:
        return self.cam.kind == "onboard"

    @property
    def cockpit(self) -> bool:
        return self.cam.cockpit

    def next_mode(self, step: int = 1) -> str:
        self.mode = (self.mode + step) % len(CAMERA_MODES)
        self._initialized = False
        self._drops.clear()
        return self.mode_name

    def update_camera(self, target: "Car", dt: float) -> None:
        m = self.cam
        self.target = target
        vel = getattr(target, "vel", None)
        vf = getattr(target, "speed_fwd", vel.length() if vel is not None else getattr(target, "speed", 0.0))
        if not self._initialized:
            self.cam_heading = target.heading
            self._last_heading = target.heading
            self._last_speed = vf
            self._accel = self._lat = self._jolt = 0.0
            self._tv_cam = None
            self._initialized = True
        if dt > 0:
            self.time += dt
            acc = (vf - self._last_speed) / dt
            yaw = wrap_angle(target.heading - self._last_heading) / dt
            k = min(1.0, dt * 6.0)
            self._accel += (clamp(acc, -900.0, 900.0) - self._accel) * k
            self._lat += (clamp(yaw * vf, -1500.0, 1500.0) - self._lat) * k
            if getattr(target, "collision_flash", 0.0) > 0.2:
                self._jolt = 1.0
            self._jolt = max(0.0, self._jolt - dt * 2.5)
        self._last_speed, self._last_heading = vf, target.heading
        sr = min(1.0, max(0.0, vf) / TOP_SPEED)
        self.near = m.near
        self.focal = m.focal
        self.roll = 0.0
        if m.kind == "onboard":
            h = target.heading
            self.cam_heading = h
            self.cam_pos = target.pos + Vector2(math.cos(h), math.sin(h)) * m.dist
            self.cam_z = m.height
            # the nose dives under braking and lifts under power, the car leans out of the corner
            self.pitch = m.pitch + clamp(-self._accel * 0.00012, -0.025, 0.04)
            self.roll = clamp(-self._lat * 0.00004, -0.05, 0.05)
            self.focal = m.focal * (1.0 - 0.08 * sr)
        elif m.kind == "track":
            self._update_tv(target, dt)
        else:
            diff = wrap_angle(target.heading - self.cam_heading)
            rate = 6.0 if m.kind == "chase" else 3.0
            self.cam_heading = wrap_angle(self.cam_heading + diff * min(1.0, dt * rate))
            fwd = Vector2(math.cos(self.cam_heading), math.sin(self.cam_heading))
            # pulls back under acceleration, closes in on the car when it brakes
            dist = m.dist * (1.0 + clamp(self._accel * 0.00012, -0.07, 0.09))
            self.cam_pos = target.pos - fwd * dist
            self.cam_z = m.height
            self.pitch = m.pitch
            if m.kind == "chase":
                self.focal = m.focal * (1.0 - 0.07 * sr)
        self._apply_shake(target, m, sr)

    def _apply_shake(self, target: "Car", m: CamMode, sr: float) -> None:
        amp = m.shake * sr * sr
        track = getattr(target, "track", None)
        idx = getattr(target, "idx", None)
        if track is not None and idx is not None and track.curb_segment and m.shake:
            if getattr(target, "on_grass", False):
                amp += m.shake * 1.6 * min(1.0, sr * 3)
            elif track.curb_segment[idx % track.n] and \
                    abs(getattr(target, "lateral", 0.0)) > track.half_width - 9:
                amp += m.shake * 1.2 * min(1.0, sr * 3)
        amp += self._jolt * (2.5 if m.kind == "onboard" else 1.2 if m.kind == "chase" else 0.0)
        if amp <= 0:
            return
        t = self.time
        n1 = math.sin(t * 37.0) * 0.6 + math.sin(t * 61.0 + 1.3) * 0.4
        n2 = math.sin(t * 43.0 + 0.7) * 0.6 + math.sin(t * 71.0 + 2.1) * 0.4
        n3 = math.sin(t * 29.0 + 2.9) * 0.7 + math.sin(t * 53.0) * 0.3
        self.cam_z += n1 * amp * (0.10 if m.kind == "onboard" else 0.6)
        self.pitch += n2 * amp * 0.0035
        self.roll += n3 * amp * 0.004

    def _tv_spots(self, track: "Track") -> list[tuple[int, Vector2, float]]:
        """Trackside TV camera positions (cached on the track): on the outside of bends, high on a gantry."""
        spots = getattr(track, "_tv_spots", None)
        if spots is not None:
            return spots
        spots = []
        n = track.n
        step = max(24, n // 18)
        cx, cy = track._cx, track._cy
        for k, i in enumerate(range(0, n - step // 2, step)):
            a, b = track.tangents[i - 8], track.tangents[(i + 8) % n]
            bend = a.x * b.y - a.y * b.x
            side = (-1.0 if bend > 0 else 1.0) if abs(bend) > 0.05 else (1.0 if k % 2 else -1.0)
            for s in (side, -side):
                p = track.center[i] + track.normals[i] * s * (track.wall_limit + 55)
                if min(math.hypot(cx[j] - p.x, cy[j] - p.y) for j in range(0, n, 3)) > track.wall_limit + 25:
                    spots.append((i, p, 34.0 + 10 * (k % 3)))
                    break
        if not spots:
            spots = [(0, track.center[0] + track.normals[0] * (track.wall_limit + 55), 40.0)]
        track._tv_spots = spots
        return spots

    def _update_tv(self, target: "Car", dt: float) -> None:
        track = target.track
        spots = self._tv_spots(track)
        n = track.n
        idx = getattr(target, "idx", None)
        if idx is None:
            idx = track.nearest_index(target.pos)

        def rel(k: int) -> int:
            r = (spots[k][0] - idx) % n
            return r - n if r > n // 2 else r
        step = max(24, n // 18)
        cur = self._tv_cam
        snap = False
        if cur is None or rel(cur) < -step // 2 or rel(cur) > step * 2 + 10:
            ahead = [k for k in range(len(spots)) if rel(k) >= -4]
            cur = min(ahead, key=rel) if ahead else 0
            snap = True
        self._tv_cam = cur
        _, pos, z = spots[cur]
        d = target.pos - pos
        dist = max(1.0, d.length())
        want = math.atan2(d.y, d.x)
        if snap or not self._initialized:
            self.cam_heading = want
        else:
            self.cam_heading = wrap_angle(self.cam_heading + wrap_angle(want - self.cam_heading) * min(1.0, dt * 12))
        self.cam_pos = Vector2(pos)
        self.cam_z = z
        self.pitch = math.atan2(z - 6.0, dist)
        self.focal = clamp(dist * 2.3, 520.0, 3000.0)

    # ------------------------------------------------------------------ projection
    def _setup(self) -> None:
        h = self.cam_heading
        self.fx, self.fy = math.cos(h), math.sin(h)
        self.rx, self.ry = -math.sin(h), math.cos(h)
        self.cx, self.cy, self.cz = self.cam_pos.x, self.cam_pos.y, self.cam_z
        self.cp, self.sp = math.cos(self.pitch), math.sin(self.pitch)
        self.cr, self.sr = math.cos(self.roll), math.sin(self.roll)
        self.to_cam = self._to_cam_roll if abs(self.roll) > 1e-4 else self._to_cam_flat

    def _to_cam_flat(self, x: float, y: float, z: float) -> CamPoint:
        dx, dy, up = x - self.cx, y - self.cy, z - self.cz
        fwd = dx * self.fx + dy * self.fy
        side = dx * self.rx + dy * self.ry
        return side, fwd * self.sp + up * self.cp, fwd * self.cp - up * self.sp

    def _to_cam_roll(self, x: float, y: float, z: float) -> CamPoint:
        dx, dy, up = x - self.cx, y - self.cy, z - self.cz
        fwd = dx * self.fx + dy * self.fy
        side = dx * self.rx + dy * self.ry
        v = fwd * self.sp + up * self.cp
        return side * self.cr - v * self.sr, side * self.sr + v * self.cr, fwd * self.cp - up * self.sp

    def _dir_to_screen(self, daz: float, el: float) -> tuple[float, float] | None:
        """Screen position of a direction (azimuth relative to the camera, elevation) at infinity."""
        ce = math.cos(el)
        side, up, fwd = math.sin(daz) * ce, math.sin(el), math.cos(daz) * ce
        v = fwd * self.sp + up * self.cp
        depth = fwd * self.cp - up * self.sp
        if depth <= 0.02:
            return None
        x, y = side * self.cr - v * self.sr, side * self.sr + v * self.cr
        return self._half_w + self._focal * x / depth, self._hy - self._focal * y / depth

    def project(self, p: CamPoint) -> tuple[float, float]:
        return self._half_w + self._focal * p[0] / p[2], self._hy - self._focal * p[1] / p[2]

    def _viewport(self, w: int, h: int, focal: float | None = None) -> None:
        self._clip_w, self._clip_h = w, h
        self._half_w = w / 2
        self._hy = h * HORIZON_Y / SCREEN_HEIGHT
        self._focal = (focal if focal is not None else self.focal) * w / SCREEN_WIDTH

    def _clip(self, pts: Sequence[CamPoint]) -> list[CamPoint]:
        near = self.near
        out: list[CamPoint] = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            a_in, b_in = a[2] >= near, b[2] >= near
            if a_in:
                out.append(a)
            if a_in != b_in:
                t = (near - a[2]) / (b[2] - a[2])
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, near))
        return out

    def poly(self, surf: pygame.Surface, pts: Sequence[CamPoint], color: Color, fog_depth: float | None = None,
             smooth: bool = True, seal: bool = False) -> None:
        near = self.near
        zs = [p[2] for p in pts]
        zmin = min(zs)
        if zmin < near:
            if max(zs) < near:
                return
            pts = self._clip(pts)
            if len(pts) < 3:
                return
            zmin = near
        if fog_depth is None or fog_depth >= 0:     # negative: the colour is already final
            color = self.fog(color, zmin if fog_depth is None else fog_depth)
        hw, f, hy = self._half_w, self._focal, self._hy
        screen_pts = [(hw + f * p[0] / p[2], hy - f * p[1] / p[2]) for p in pts]
        xs = [p[0] for p in screen_pts]
        ys = [p[1] for p in screen_pts]
        lx, hx, ly, hy_ = min(xs), max(xs), min(ys), max(ys)
        cw, ch = self._clip_w, self._clip_h
        if hx < 0 or lx > cw or hy_ < 0 or ly > ch:
            return      # entirely off-screen
        if lx < -64 or hx > cw + 64 or ly < -64 or hy_ > ch + 64:
            screen_pts = _clip_screen(screen_pts, -2.0, -2.0, cw + 2.0, ch + 2.0)
            if len(screen_pts) < 3:
                return
        pygame.draw.polygon(surf, color, screen_pts)
        if seal:
            pygame.draw.polygon(surf, color, screen_pts, 1)    # covers the 1 px gaps to the next strip
        if smooth and self.aa:
            # blend the border into what is behind it: removes the stair steps on polygon edges
            pygame.draw.aalines(surf, color, True, screen_pts)

    def fog(self, color: Color, depth: float) -> Color:
        a = self._amb
        if a is not None:
            color = (color[0] * a[0], color[1] * a[1], color[2] * a[2])
        t = depth * self._fog_inv
        t = 0.0 if t <= 0 else 1.0 if t >= 1 else t ** 1.8
        fc = self._fog_col
        return (int(color[0] + (fc[0] - color[0]) * t), int(color[1] + (fc[1] - color[1]) * t),
                int(color[2] + (fc[2] - color[2]) * t))

    def _line3d(self, surf: pygame.Surface, a: CamPoint, b: CamPoint, color: Color, width: int = 1) -> None:
        near = self.near
        if a[2] < near and b[2] < near:
            return
        if a[2] < near or b[2] < near:
            if a[2] < near:
                a, b = b, a
            t = (near - a[2]) / (b[2] - a[2])
            b = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, near)
        col = self.fog(color, min(a[2], b[2]))
        pa, pb = self.project(a), self.project(b)
        if width <= 1 and self.aa:
            pygame.draw.aaline(surf, col, pa, pb)
        else:
            pygame.draw.line(surf, col, pa, pb, max(1, width))

    def _glow(self, x: float, y: float, radius: float, color: Color) -> None:
        if self._glows is not None and len(self._glows) < 160:
            self._glows.append((x, y, radius, color))

    # ------------------------------------------------------------------ environment
    def _env(self, track: "Track", rain: float) -> _Env:
        look = _TRACK_LOOK.get(track.definition.key, {"sky": _SKY_DAY, "sun": (0.0, 0.18),
                                                      "pano": [("hills", 0.02, (110, 120, 130), 0.4)]})
        night = bool(look.get("night"))
        level = 0 if rain <= 0.03 else max(1, round(min(1.0, rain * 1.6) * 16))
        mix = level / 16
        zenith, haze = look["sky"]
        if not night:
            zenith, haze = _mix(zenith, _RAIN_SKY[0], mix), _mix(haze, _RAIN_SKY[1], mix)
        else:
            zenith, haze = _mix(zenith, (14, 16, 24), mix), _mix(haze, (44, 46, 56), mix)
        fog_far = FAR * (0.62 if night else 1.0) * (1.0 - 0.45 * mix)
        return _Env(zenith, haze, fog_far, night, not night and mix < 0.45, mix, track.wetness, look)

    # sun light for everything in the world: same direction as the sun drawn in the sky (a bit higher, so the
    # shadows stay readable), weak and diffuse under clouds, floodlights from above at night
    _sunv = (0.42, -0.52, 0.74)
    _sun_h = (0.63, -0.78)
    _sun_k = 1.0
    _shadow_dir = (-0.57, 0.70)

    def _set_sun(self, env: _Env) -> None:
        if env.night:
            sx, sy, sz, k = 0.22, -0.18, 0.96, 0.45
        else:
            az, el = env.look.get("sun", (0.0, 0.18))
            elv = clamp(el * 2.6, 0.5, 1.0)
            sx, sy, sz = math.cos(az) * math.cos(elv), math.sin(az) * math.cos(elv), math.sin(elv)
            k = 1.0 if env.sun else 0.35
        self._sunv = (sx, sy, sz)
        self._sun_k = k
        hl = math.hypot(sx, sy) or 1.0
        self._sun_h = (sx / hl, sy / hl)
        reach = min(1.3, hl / sz) * (0.5 + 0.5 * k)          # shadow length per unit of height
        self._shadow_dir = (-sx / hl * reach, -sy / hl * reach)

    def _face_light(self, nx: float, ny: float, base: float = 0.66, gain: float = 0.42) -> float:
        """Brightness of a vertical face with horizontal normal (nx, ny) in the current sun."""
        k = self._sun_k
        d = nx * self._sun_h[0] + ny * self._sun_h[1]
        return base + 0.12 * (1.0 - k) + gain * k * max(0.0, d) - 0.06 * k * max(0.0, -d)

    def _sky_layers(self, track: "Track") -> dict:
        """Horizon silhouettes, clouds and stars, generated once per track."""
        cached = getattr(track, "_sky3d", None)
        if cached is not None:
            return cached
        key = track.definition.key
        look = _TRACK_LOOK.get(key, {"pano": [("hills", 0.02, (110, 120, 130), 0.4)]})
        rng = random.Random(sum(map(ord, key)) * 7 + 3)
        N = 720
        layers = []
        for kind, amp, color, strength in look["pano"]:
            heights = [0.0] * N
            if kind in ("mountains", "hills"):
                waves = [(rng.uniform(0, TAU), rng.randint(2, 9), rng.uniform(0.3, 1.0)) for _ in range(7)]
                for k in range(N):
                    a = k / N * TAU
                    v = sum(w * math.sin(a * f + ph) for ph, f, w in waves) / sum(w for _, _, w in waves)
                    v = (v + 1) / 2
                    heights[k] = amp * (0.15 + 0.85 * v ** (1.8 if kind == "mountains" else 1.2))
            elif kind in ("trees", "conifers"):
                base = [(rng.uniform(0, TAU), rng.randint(3, 12)) for _ in range(4)]
                for k in range(N):
                    a = k / N * TAU
                    v = sum(math.sin(a * f + ph) for ph, f in base) / 4
                    bump = rng.uniform(0.0, 0.35 if kind == "trees" else 0.7)
                    if kind == "conifers" and k % 2:
                        bump *= 0.25
                    heights[k] = amp * (0.45 + 0.25 * v + bump)
            else:   # skyline: blocks of buildings with gaps
                k = 0
                while k < N:
                    width = rng.randint(2, 7)
                    h = 0.0 if rng.random() < 0.18 else amp * rng.uniform(0.25, 1.0) ** 1.4
                    for j in range(width):
                        heights[(k + j) % N] = h
                    k += width
            windows = []
            if kind == "skyline":
                for _ in range(500):
                    k = rng.randrange(N)
                    if heights[k] > 0.008:
                        windows.append((k / N * TAU, rng.uniform(0.002, heights[k] - 0.003), rng.random()))
            layers.append({"kind": kind, "h": heights, "color": color, "strength": strength, "windows": windows})
        clouds = [(rng.uniform(0, TAU), rng.uniform(0.05, 0.22), rng.randrange(4), rng.uniform(0.7, 1.4))
                  for _ in range(14)]
        stars = [(rng.uniform(0, TAU), rng.uniform(0.03, 0.55), rng.randint(110, 255)) for _ in range(260)]
        landmark = key == "marinabay"
        out = {"layers": layers, "clouds": clouds, "stars": stars, "landmark": landmark}
        track._sky3d = out
        return out

    def _cloud_sprite(self, k: int, scale: float, rain: float = 0.0) -> pygame.Surface:
        q = max(1, int(scale * self.ss * 8))
        key = ("cloud", k, q, round(rain * 16))
        img = self._scaled.get(key)
        if img is None and rain > 0.03:
            img = self._cloud_sprite(k, scale, 0.0).copy()
            img.fill((200, 200, 205, int(255 * (1 - rain))), special_flags=pygame.BLEND_RGBA_MULT)
            self._scaled[key] = img
        if img is None:
            rng = random.Random(k * 31 + 5)
            w, h = 260, 90
            base = pygame.Surface((w, h), pygame.SRCALPHA)
            for _ in range(16):
                r = rng.randint(16, 36)
                x = rng.randint(r, w - r)
                y = rng.randint(h // 2 - 6, h - r)
                for layer in range(4):
                    rr = int(r * (1 - layer * 0.18))
                    blob = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
                    pygame.draw.circle(blob, (255, 255, 255, 22 + layer * 10), (rr, rr), rr)
                    base.blit(blob, (x - rr, y - rr - layer * 3))
            size = (max(4, int(w * q / 8)), max(2, int(h * q / 8)))
            img = pygame.transform.smoothscale(base, size)
            self._scaled[key] = img
        return img

    def _glow_sprite(self, radius: int, color: Color) -> pygame.Surface:
        """Radial falloff on black for additive blending."""
        key = (radius, color)
        img = self._glow_cache.get(key)
        if img is None:
            size = radius * 2 + 2
            img = pygame.Surface((size, size))
            steps = max(3, min(14, radius // 2))
            for k in range(steps, 0, -1):
                t = k / steps
                strength = (1 - t) ** 1.8 * 0.95 + 0.05
                col = (int(color[0] * strength), int(color[1] * strength), int(color[2] * strength))
                pygame.draw.circle(img, col, (radius + 1, radius + 1), max(1, int(radius * t)))
            if len(self._glow_cache) > 500:
                self._glow_cache.clear()
            self._glow_cache[key] = img
        return img

    def _add_glow(self, surf: pygame.Surface, x: float, y: float, radius: float, color: Color) -> None:
        r = int(radius)
        r = r if r < 16 else r // 4 * 4 if r < 64 else r // 16 * 16
        r = max(2, min(r, 220))
        surf.blit(self._glow_sprite(r, color), (x - r - 1, y - r - 1), special_flags=pygame.BLEND_RGB_ADD)

    def _horizon(self, w: int) -> tuple[float, float]:
        """Screen y of the horizon at the left and right edge of the view."""
        f, hw, hy = self._focal, self._half_w, self._hy
        yc = hy - f * math.tan(self.pitch) / max(0.2, self.cr)
        slope = -self.sr / max(0.2, self.cr)
        return yc + slope * (0 - hw), yc + slope * (w - hw)

    def _draw_sky(self, surf: pygame.Surface, track: "Track", env: _Env, lite: bool) -> None:
        w, h = surf.get_size()
        yl, yr = self._horizon(w)
        y_lo, y_hi = min(yl, yr), max(yl, yr)
        key = ("sky", env.zenith, env.haze, w, h)
        sky = self._scaled.get(key)
        if sky is None:
            sky = vertical_gradient((w, h), env.zenith, env.haze).convert()
            self._scaled[key] = sky
        if int(y_hi) - h + 2 > 0:
            surf.fill(env.zenith, (0, 0, w, int(y_hi) - h + 2))
        surf.blit(sky, (0, int(y_hi) - h + 2))
        layers = self._sky_layers(track)
        heading = self.cam_heading
        if not lite:
            if env.night:
                self._draw_stars(surf, layers["stars"], env)
            else:
                self._draw_sun(surf, env)
                if env.rain < 0.75:
                    for az, el, k, scale in layers["clouds"]:
                        daz = wrap_angle(az - heading)
                        if abs(daz) > 1.4:
                            continue
                        p = self._dir_to_screen(daz, el)
                        if p is None:
                            continue
                        img = self._cloud_sprite(k, min(2.0, scale * self._focal / FOCAL), env.rain)
                        if p[0] + img.get_width() < 0 or p[0] - img.get_width() > w:
                            continue
                        surf.blit(img, (p[0] - img.get_width() / 2, p[1] - img.get_height() / 2))
        # ground: gradient from the haze at the horizon to the grass colour close by
        grass = track.definition.grass
        if env.night:
            grass = _shade(grass, 0.45)
        far_grass = _mix(grass, env.haze, 0.9)     # the far ground melts into the same haze as the fog
        gkey = ("ground", grass, env.haze, w, h)
        ground = self._scaled.get(gkey)
        if ground is None:
            ground = vertical_gradient((w, h + 40), far_grass, grass).convert()
            self._scaled[gkey] = ground
        surf.blit(ground, (0, int(y_lo)))
        if int(y_lo) + h + 40 < h:
            surf.fill(grass, (0, int(y_lo) + h + 40, w, h))
        if y_hi - y_lo > 0.5:
            # tilted horizon (camera roll): give the wedge above the line back to the sky
            pygame.draw.polygon(surf, env.haze, [(0, yl), (0, y_lo - 1), (w, y_lo - 1), (w, yr)])
        self._draw_panorama(surf, layers, env, lite)

    def _draw_sun(self, surf: pygame.Surface, env: _Env) -> None:
        self._sun_screen = None
        az, el = env.look.get("sun", (0.0, 0.18))
        daz = wrap_angle(az - self.cam_heading)
        if abs(daz) > 1.5:
            return
        p = self._dir_to_screen(daz, el)
        if p is None:
            return
        w, h = surf.get_size()
        if not (-300 < p[0] < w + 300 and -300 < p[1] < h + 100):
            return
        s = self.ss
        k = 1.0 - env.rain
        self._add_glow(surf, p[0], p[1], 210 * s, (int(90 * k), int(80 * k), int(50 * k)))
        self._add_glow(surf, p[0], p[1], 70 * s, (int(160 * k), int(150 * k), int(110 * k)))
        pygame.draw.circle(surf, _mix((255, 252, 235), env.haze, env.rain), p, max(2, int(16 * s)))
        self._sun_screen = p

    def _draw_stars(self, surf: pygame.Surface, stars: list, env: _Env) -> None:
        if env.rain > 0.3:
            return
        heading = self.cam_heading
        w, h = surf.get_size()
        for az, el, b in stars:
            daz = wrap_angle(az - heading)
            if abs(daz) > 1.2:
                continue
            p = self._dir_to_screen(daz, el)
            if p is None or not (0 <= p[0] < w and 0 <= p[1] < h):
                continue
            b = int(b * (1 - env.rain))
            surf.fill((b, b, min(255, b + 20)), (int(p[0]), int(p[1]), round(self.ss), round(self.ss)))
        moon = self._dir_to_screen(wrap_angle(2.6 - heading), 0.32)
        if moon is not None and -100 < moon[0] < w + 100:
            self._add_glow(surf, moon[0], moon[1], 60 * self.ss, (40, 44, 60))
            pygame.draw.circle(surf, (236, 236, 222), moon, int(11 * self.ss))
            pygame.draw.circle(surf, (210, 210, 198), (moon[0] + 3 * self.ss, moon[1] - 2 * self.ss), int(3 * self.ss))

    def _draw_panorama(self, surf: pygame.Surface, layers: dict, env: _Env, lite: bool) -> None:
        w, _ = surf.get_size()
        heading = self.cam_heading
        hw, f = self._half_w, self._focal
        step = int(12 * self.ss)
        cols = list(range(-step, w + 2 * step, step))
        dazs = [math.atan2(x - hw, f) for x in cols]
        bottom = [self._dir_to_screen(d, -0.012) for d in dazs]
        if any(p is None for p in bottom):
            return
        for layer in layers["layers"]:
            heights = layer["h"]
            n = len(heights)
            col = layer["color"]
            if not env.night:
                col = _mix(env.haze, col, layer["strength"] * (1 - 0.6 * env.rain))
            else:
                col = _mix(env.haze, col, 0.85)
            top = []
            for d in dazs:
                u = ((heading + d) / TAU * n) % n
                k = int(u)
                fr = u - k
                el = heights[k] * (1 - fr) + heights[(k + 1) % n] * fr if layer["kind"] != "skyline" \
                    else heights[k]
                p = self._dir_to_screen(d, max(el, -0.01))
                if p is None:
                    return
                top.append(p)
            if layer["kind"] == "skyline":
                # square tops: step the outline instead of sloping between samples
                stepped = []
                for a, b in zip(top, top[1:]):
                    stepped.append(a)
                    stepped.append((b[0], a[1]))
                stepped.append(top[-1])
                top = stepped
            pygame.draw.polygon(surf, col, top + bottom[::-1])
            if not env.night and layer["kind"] in ("mountains", "hills"):
                # sunlit ridge: gives the silhouette shape instead of a flat band
                pygame.draw.aalines(surf, _mix(col, (255, 250, 236), 0.25), False, top)
            if env.night and layer["windows"] and not lite:
                for az, el, r in layer["windows"]:
                    daz = wrap_angle(az - heading)
                    if abs(daz) > 1.0:
                        continue
                    p = self._dir_to_screen(daz, el)
                    if p is None or not (0 <= p[0] < w):
                        continue
                    c = (255, 214, 140) if r < 0.7 else (170, 210, 255) if r < 0.9 else (255, 120, 200)
                    surf.fill(c, (int(p[0]), int(p[1]), round(self.ss), round(self.ss)))
        if layers["landmark"] and not lite:
            self._draw_landmark(surf, env)

    def _draw_landmark(self, surf: pygame.Surface, env: _Env) -> None:
        """Marina Bay: three towers carrying a sky deck, and the big observation wheel."""
        heading = self.cam_heading
        base_az = 0.9
        pts = []
        for k in range(3):
            a0, a1 = base_az + k * 0.03, base_az + k * 0.03 + 0.016
            pa = [self._dir_to_screen(wrap_angle(a - heading), e) for a, e in
                  ((a0, -0.01), (a1, -0.01), (a1 - 0.002, 0.075), (a0, 0.075))]
            if any(p is None for p in pa):
                return
            pts.append(pa)
        for pa in pts:
            pygame.draw.polygon(surf, (26, 26, 42), pa)
            for k in range(8):
                y = pa[0][1] + (pa[3][1] - pa[0][1]) * (k + 1) / 9
                pygame.draw.line(surf, (255, 220, 150), (pa[0][0] + 2, y), (pa[1][0] - 2, y), 1)
        deck = [self._dir_to_screen(wrap_angle(a - heading), e) for a, e in
                ((base_az - 0.012, 0.075), (base_az + 0.09, 0.075), (base_az + 0.085, 0.084),
                 (base_az - 0.01, 0.084))]
        if all(p is not None for p in deck):
            pygame.draw.polygon(surf, (30, 30, 48), deck)
            pygame.draw.line(surf, (120, 220, 255), deck[0], deck[1], 1)
        c = self._dir_to_screen(wrap_angle(base_az - 0.32 - heading), 0.045)
        e = self._dir_to_screen(wrap_angle(base_az - 0.32 - heading), 0.0)
        if c is not None and e is not None:
            r = max(4, int(abs(e[1] - c[1])))
            pygame.draw.line(surf, (40, 40, 60), e, (c[0] - r * 0.4, e[1]), 2)
            pygame.draw.line(surf, (40, 40, 60), e, (c[0] + r * 0.4, e[1]), 2)
            ring = (200, 120, 255) if int(self.time * 2) % 2 else (120, 200, 255)
            pygame.draw.circle(surf, ring, c, r, 2)
            for k in range(12):
                a = k / 12 * TAU + self.time * 0.05
                pygame.draw.line(surf, (60, 60, 90), c, (c[0] + math.cos(a) * r, c[1] + math.sin(a) * r), 1)

    # ------------------------------------------------------------------ frame
    def draw(self, surf: pygame.Surface, track: "Track", cars: Sequence["Car"], target: "Car",
             racing_line: bool, label_font: pygame.font.Font,
             garages: Sequence[tuple[Vector2, float, Color, str]] = (), rain: float = 0.0,
             guide: Sequence[Vector2] = (), fx: "Effects | None" = None, lights: int | None = None,
             positions: dict | None = None, frame_dt: float = 1 / 60, crews: Sequence[tuple] = (),
             flags: Sequence[str] = ()) -> None:
        self.guide = guide
        self._spin_cars(cars, frame_dt)
        self._flag_states = flags
        # "high": 1.5x supersampling (2.25x the pixels - 2x cost four times the fill work for little gain)
        self.ss = 1.5 if self.antialias == "high" else 1
        self.aa = self.antialias == "edges"
        out = surf
        w, h = out.get_size()
        if self.ss > 1:
            size = (int(w * self.ss), int(h * self.ss))
            if self._buf is None or self._buf.get_size() != size:
                self._buf = pygame.Surface(size).convert()
            surf = self._buf
        env = self._env(track, rain)
        self._set_sun(env)
        self._fog_col = env.haze
        # the fog is complete just before the view distance, so the end of the drawn world (track, scenery,
        # cars) is hidden in the haze instead of showing as a line that jumps forward
        self._fog_inv = 1.0 / (env.fog_far * FOG_END)
        self._glows = []
        self._sun_screen = None
        self._viewport(*surf.get_size())
        labels = self._draw_world(surf, track, cars, target, racing_line, garages, env, fx, lights, crews=crews)
        if surf is not out:
            try:
                pygame.transform.smoothscale(surf, out.get_size(), out)
            except (ValueError, pygame.error):
                out.blit(pygame.transform.smoothscale(surf, out.get_size()), (0, 0))
        hi = self.detail == "high"
        s = self.ss
        for x, y, r, col in self._glows or ():
            self._add_glow(out, x / s, y / s, r / s, col)
        self._glows = None
        if hi and self._sun_screen is not None:
            self._lens_flare(out, self._sun_screen[0] / s, self._sun_screen[1] / s, env)
        self._draw_labels(out, labels, label_font, positions, target)
        if hi:
            # colour grade: warm low sun, cool grey rain, slightly blue night (rounded so the cache stays small)
            if env.night:
                grade = (0.97, 0.97, 1.0)
            else:
                k = round(env.rain * 4) / 4
                grade = (round(1.0 - 0.05 * k, 3), round(0.985 - 0.01 * k, 3), round(0.95 + 0.05 * k, 3))
            self._grade = grade
            self._vignette(out, target)
        flash = getattr(target, "collision_flash", 0.0)
        if flash > 0 and self.cam.kind in ("onboard", "chase"):
            k = min(1.0, flash * 4)
            out.fill((int(70 * k), int(18 * k), int(10 * k)), special_flags=pygame.BLEND_RGB_ADD)
        if self.cam.lens and hi:
            self._lens_rain(out, env, target, frame_dt)
        if self.cam.cockpit:
            if hi and self.detail != "low":
                self._mirror_tick += 1
                if self._mirror is None or self._mirror_tick % 4 == 0:
                    self._render_mirror(track, cars, target, env)
            self._draw_halo(out, target)
            self._draw_cockpit(out, target, env)

    def _draw_labels(self, out: pygame.Surface, labels: list, font: pygame.font.Font, positions: dict | None,
                     target: "Car") -> None:
        s = self.ss
        for (x, y), car, depth in labels:
            txt = tr("DU") if car.is_player and car.short == "YOU" else tr(car.short)
            pos = positions.get(car) if positions else None
            if pos is not None:
                txt = f"{pos}  {txt}"
            img = font.render(txt, True, (0, 230, 255) if car.is_player else (250, 250, 250))
            rect = img.get_rect(midbottom=(x / s, y / s))
            box = rect.inflate(14, 4)
            box.x -= 3
            alpha = 200 if depth < 700 else int(200 * max(0.0, 1 - (depth - 700) / 400))
            if alpha < 20:
                continue
            draw_panel(out, box, (12, 14, 20), alpha, radius=4)
            pygame.draw.rect(out, car.color, (box.x, box.y, 4, box.h), border_radius=2)
            out.blit(img, (rect.x + 3, rect.y))

    # ------------------------------------------------------------------ world
    def _draw_world(self, surf: pygame.Surface, track: "Track", cars: Sequence["Car"], target: "Car",
                    racing_line: bool, garages: Sequence[tuple[Vector2, float, Color, str]], env: _Env,
                    fx: "Effects | None" = None, lights: int | None = None, lite: bool = False,
                    crews: Sequence[tuple] = ()
                    ) -> list[tuple[tuple[float, float], "Car", float]]:
        self._setup()
        d = track.definition
        self._amb = None
        self._draw_sky(surf, track, env, lite)
        detail = 0 if self.detail == "low" else 1 if self.detail == "medium" else 2
        if lite:
            detail = 0
        far = env.fog_far if not lite else 800.0
        self._far = far
        night = env.night
        amb_track = (0.80, 0.80, 0.88) if night else None
        amb_far = (0.36, 0.38, 0.52) if night else None
        self._amb = amb_track

        n = track.n
        visible: list[tuple[float, int]] = []
        cx, cy = self.cx, self.cy
        fov = self._half_w / self._focal * 1.2
        margin = track.wall_limit * 2 + 60
        tcx, tcy = track._cx, track._cy
        sfx, sfy, srx, sry = self.fx, self.fy, self.rx, self.ry
        back = -track.wall_limit - 40
        for i in range(n):
            dx, dy = tcx[i] - cx, tcy[i] - cy
            fwd = dx * sfx + dy * sfy
            if fwd < back or fwd > far:
                continue
            side = dx * srx + dy * sry
            if abs(side) > fwd * fov + margin:
                continue
            visible.append((fwd, i))
        visible.sort(reverse=True)
        # level of detail: further away, several track segments are merged into one polygon. Walked in track order
        # so the pieces always meet: skipping the odd segment where the step changes left a crack that blinked
        # as the camera moved
        fwd_of = {i: fwd for fwd, i in visible}
        segments: list[tuple[float, int, int]] = []
        cursor = -1
        for i in sorted(fwd_of):
            if i < cursor:
                continue
            fwd = fwd_of[i]
            step = 1 if fwd < 450 else 2 if fwd < 1100 else 4
            j = i + step - i % step            # next aligned index: neighbouring pieces share their end points
            segments.append((fwd, i, j % n))
            cursor = j

        hw, wl = track.half_width, track.wall_limit
        to_cam = self.to_cam
        center, normals = track.center, track.normals
        # projection is affine: project each centre point and its normal once, then every point across the
        # track is centre + offset * normal (instead of a full projection per polygon corner)
        bases: dict[int, tuple[float, float, float, float, float, float]] = {}
        need = {0, 1}
        for _, i, j in segments:
            need.add(i)
            need.add(j)
            need.add((i + 2) % n)
        for i in need:
            c, nv = center[i], normals[i]
            ax, ay, az = to_cam(c.x, c.y, 0.0)
            bx, by, bz = to_cam(c.x + nv.x, c.y + nv.y, 0.0)
            bases[i] = (ax, ay, az, bx - ax, by - ay, bz - az)

        def edge(i: int, off: float) -> CamPoint:
            b = bases.get(i)
            if b is None:       # points between the LOD steps (track decals): project on demand
                c, nv = center[i], normals[i]
                ax, ay, az = to_cam(c.x, c.y, 0.0)
                bx, by, bz = to_cam(c.x + nv.x, c.y + nv.y, 0.0)
                b = bases[i] = (ax, ay, az, bx - ax, by - ay, bz - az)
            ax, ay, az, nx, ny, nz = b
            return ax + nx * off, ay + ny * off, az + nz * off

        # consecutive segments are merged into strips: one polygon per strip instead of one per segment
        curb = track.curb_segment
        runs: list[list] = []
        cur: list | None = None
        for fwd, i, j in sorted(segments, key=lambda sg: sg[1]):
            st = (j - i) % n
            key = (i // (8 if st <= 2 else 16), st, curb[i])
            if cur is not None and cur[0] == key and cur[2][-1] == i:
                cur[2].append(j)
                cur[1] = max(cur[1], fwd)
            else:
                cur = [key, fwd, [i, j]]
                runs.append(cur)
        runs.sort(key=lambda r: -r[1])

        def strip(idx: list[int], off_a: float, off_b: float) -> list[CamPoint]:
            return [edge(k, off_a) for k in idx] + [edge(k, off_b) for k in reversed(idx)]
        if detail:
            # mown grass stripes beyond the barriers (the ground is already grass coloured: only dark stripes)
            self._amb = amb_far
            g0 = _shade(d.grass, 0.9) if not night else _shade(d.grass, 0.4)
            for key, fwd, idx in runs:
                if fwd < 1100 and key[0] % 2:
                    stripe = _fade(g0, d.grass if not night else _shade(d.grass, 0.45), fwd, 1100)
                    for side in (-1, 1):
                        self.poly(surf, strip(idx, side * (wl + 2), side * (wl + 100)), stripe, smooth=False)
            self._amb = amb_track
        if detail and not night and not lite:
            # shadows of buildings and trees fall on the ground only: drawn before the run-off and the road so
            # they never end up as dark patches on top of the asphalt
            self._amb = amb_far
            self._draw_scenery_shadows(surf, track, far, fov)
            self._amb = amb_track
        runoff = d.runoff_color
        for key, fwd, idx in runs:
            for side in (-1, 1):
                self.poly(surf, strip(idx, side * hw, side * wl), runoff, smooth=False, seal=True)
        if detail and d.runoff >= 40:
            # gravel traps on the outside of the corners (permanent circuits: wide run-off)
            beds = self._gravel(track)
            gravel = _shade((196, 178, 140), 1.0 - 0.3 * clamp(env.wet, 0.0, 1.0))
            rake = _shade(gravel, 0.88)
            g0, g1 = hw + 9.0, min(wl - 4.0, hw + 9.0 + 64.0)
            # consecutive bed segments of a road strip become one polygon (and one per rake line)
            for key, fwd, idx in runs:
                if fwd > 1300:
                    continue
                k = 0
                while k < len(idx) - 1:
                    side = beds.get(idx[k])
                    if side is None:
                        k += 1
                        continue
                    m = k + 1
                    while m < len(idx) - 1 and beds.get(idx[m]) == side:
                        m += 1
                    part = idx[k:m + 1]
                    self.poly(surf, strip(part, side * g0, side * g1), _fade(gravel, runoff, fwd, 1300), smooth=False)
                    if fwd < 500:
                        for frac in (0.3, 0.62):
                            a = g0 + (g1 - g0) * frac
                            self.poly(surf, strip(part, side * a, side * (a + 1.6)), _fade(rake, gravel, fwd, 500),
                                      smooth=False)
                    k = m
        self._draw_pit_lane(surf, track)
        if detail and crews:
            self._draw_box_marks(surf, crews, target)
        wet = clamp(env.wet, 0.0, 1.0)
        asphalt = _shade(d.asphalt, 1.0 - 0.32 * wet)
        for key, fwd, idx in runs:
            # one even colour: strips in two shades showed every seam as a line across the road; the outline
            # closes the hairline gaps the polygon fill leaves between neighbouring strips
            self.poly(surf, strip(idx, -hw, hw), asphalt, smooth=False, seal=True)
        if detail and track.line_offset:
            # rubbered-in racing line (on a wet track: the drying line), soft-edged: a faint wide band under a
            # narrower darker core
            k_out, k_in = (0.95, 0.90) if wet < 0.25 else (1.0 + 0.15 * wet, 1.0 + 0.3 * wet)
            lo = track.line_offset
            for width, k in ((15.0, k_out), (7.0, k_in)):
                rub = _shade(asphalt, k)
                for key, fwd, idx in runs:
                    if fwd < 1400:
                        self.poly(surf, [edge(m, lo[m] - width) for m in idx] +
                                  [edge(m, lo[m] + width) for m in reversed(idx)], _fade(rub, asphalt, fwd, 1400),
                                  smooth=fwd < 600)
            # skid marks in the braking zones and repaired patches of asphalt, only close to the camera
            close = {i: fwd for fwd, i in visible if fwd < 900}
            fade_asphalt = asphalt
            if close:
                skid = _shade(asphalt, 0.8 + 0.12 * wet)
                patch_hi, patch_lo = _shade(asphalt, 1.07), _shade(asphalt, 0.93)
                for i0, kind, a, b, ks in self._decals(track):
                    if i0 not in close:
                        continue
                    dist = close[i0]
                    if kind == "patch":
                        self.poly(surf, [edge(k, a) for k in ks] + [edge(k, b) for k in reversed(ks)],
                                  _fade(patch_hi if (i0 // 3) % 2 else patch_lo, fade_asphalt, dist, 900), smooth=False)
                    else:
                        self.poly(surf, [edge(k, lo[k] + a) for k in ks] + [edge(k, lo[k] + b) for k in reversed(ks)],
                                  _fade(skid, fade_asphalt, dist, 900), smooth=False)
        for key, fwd, idx in runs:
            if fwd < 1600 and not key[2]:
                line = _fade((230, 230, 230), asphalt, fwd, 1600)
                for side in (-1, 1):
                    self.poly(surf, strip(idx, side * (hw - 3), side * (hw - 1)), line)
        turf = (62, 132, 70) if d.scenery != "city" else None
        for fwd, i, j in segments:
            if track.curb_segment[i]:
                col = (215, 30, 30) if (i // max(2, (j - i) % n)) % 2 == 0 else (238, 238, 238)
                for side in (-1, 1):
                    self.poly(surf, [edge(i, side * (hw - 7)), edge(j, side * (hw - 7)), edge(j, side * (hw + 1)),
                                     edge(i, side * (hw + 1))], col)
                    if turf and detail and fwd < 1500:
                        self.poly(surf, [edge(i, side * (hw + 1)), edge(j, side * (hw + 1)),
                                         edge(j, side * (hw + 9)), edge(i, side * (hw + 9))],
                                  _fade(turf, runoff, fwd, 1500))
            if i == 0 or j == 0 and i > n - 3:
                for k in range(8):
                    lat = -hw + k * hw / 4
                    self.poly(surf, [edge(0, lat), edge(0, lat + hw / 8), edge(1, lat + hw / 8), edge(1, lat)],
                              (240, 240, 240))
        if detail:
            self._draw_grid_marks(surf, track)
        if racing_line and track.max_speed:
            self._draw_racing_line(surf, track, target)
        if getattr(self, "guide", None):
            self._draw_guide(surf, self.guide)

        cam = self.cam
        hide_target = cam.kind == "onboard"
        objects: list[tuple[float, int, object]] = []
        # barriers: consecutive segments of one colour stripe become a single wall object
        for edge_pts in track.wall_edges:
            run: list | None = None
            for fwd, i, j in sorted(segments, key=lambda sg: sg[1]):
                a, b = edge_pts[i], edge_pts[j]
                if a is None or b is None:
                    run = None
                    continue
                st = (j - i) % n
                key = (i // (3 * st), st)
                if run is not None and run[0] == key and run[3] == i:
                    run[2].append(b)
                    run[1] += fwd
                    run[3] = j
                    run[4] += 1
                else:
                    run = [key, fwd, [a, b], j, 1, i]
                    objects.append(run)     # type: ignore[arg-type]
        for k, obj in enumerate(objects):
            if isinstance(obj, list):
                key, total, pts, _, count, first = obj
                objects[k] = (total / count, 0, (pts, key[0] % 2, first))
        if not lite:
            for item in track.scenery:
                p = item[1]
                dx, dy = p.x - cx, p.y - cy
                fwd = dx * sfx + dy * sfy
                if 20 < fwd < far * FOG_END and abs(dx * srx + dy * sry) < fwd * fov + 100:
                    objects.append((fwd, 1, item))
            if detail:
                for prop in self._props(track, night):
                    if prop[0] == "flood" and not night:
                        continue
                    p = prop[1]
                    dx, dy = p.x - cx, p.y - cy
                    fwd = dx * sfx + dy * sfy
                    reach = prop[-1]
                    if -reach < fwd < far * FOG_END and abs(dx * srx + dy * sry) < fwd * fov + reach + 40:
                        objects.append((fwd, 5, prop))
            if fx is not None and fx.enabled and fx.parts and detail:
                for p in fx.parts:
                    dx, dy = p.x - cx, p.y - cy
                    fwd = dx * sfx + dy * sfy
                    if 4 < fwd < 1600 and abs(dx * srx + dy * sry) < fwd * fov + 30:
                        objects.append((fwd, 4, p))
        for g in garages:
            dx, dy = g[0].x - cx, g[0].y - cy
            fwd = dx * sfx + dy * sfy
            if 10 < fwd < far * FOG_END:
                objects.append((fwd, 3, g))
        for car in cars:
            if car is target and (hide_target and lite):
                continue
            dx, dy = car.pos.x - cx, car.pos.y - cy
            fwd = dx * sfx + dy * sfy
            if -30 < fwd < far * FOG_END and abs(dx * srx + dy * sry) < fwd * fov + 60:
                objects.append((fwd if not (car is target and hide_target) else -1e9, 2, car))
        objects.sort(key=lambda o: -o[0])
        labels: list[tuple[tuple[float, float], "Car", float]] = []
        city = d.scenery == "city"
        if detail and crews and not lite:
            for person in self._crew_people(crews):
                p = person[0]
                dx, dy = p.x - cx, p.y - cy
                fwd = dx * sfx + dy * sfy
                if 4 < fwd < 1000 and abs(dx * srx + dy * sry) < fwd * fov + 20:
                    objects.append((fwd, 6, person))
            objects.sort(key=lambda o: -o[0])
        for fwd, kind, obj in objects:
            if kind == 0:
                self._draw_wall(surf, obj, d, fwd, detail, city)
            elif kind == 1:
                self._amb = amb_far
                self._draw_scenery(surf, obj, fwd, detail, night, track)
                self._amb = amb_track
            elif kind == 3:
                pos, heading, color, _team = obj
                self._draw_garage(surf, pos, heading, color, track.pit.side if track.pit else 1, night)
                if night:
                    p = to_cam(pos.x, pos.y, 20)
                    if p[2] > self.near:
                        sx, sy = self.project(p)
                        self._glow(sx, sy, self._focal * 22 / p[2], (60, 56, 40))
            elif kind == 4:
                self._draw_particle(surf, obj, night)
            elif kind == 6:
                self._draw_person(surf, obj)
            elif kind == 5:
                self._draw_prop(surf, obj, lights, night)
            else:
                car = obj
                hide = cam.hide if car is target else ()
                if car is target and hide_target:
                    self._draw_car(surf, car, 0.0, hide, env, own=True)
                    continue
                self._draw_car(surf, car, fwd, hide, env)
                if fwd < 1100 and car is not target and not lite:
                    top = to_cam(car.pos.x, car.pos.y, 22)
                    if top[2] > self.near:
                        labels.append((self.project(top), car, fwd))
        self._amb = None
        return labels

    def _draw_wall(self, surf: pygame.Surface, obj: tuple, d, fwd: float, detail: int, city: bool) -> None:
        pts, alt, i = obj
        to_cam = self.to_cam
        col = d.wall_a if alt else d.wall_b

        def row(z: float) -> list[CamPoint]:
            return [to_cam(p.x, p.y, z) for p in pts]
        # the face we see: its normal points to the camera
        a, b = pts[0], pts[-1]
        dx, dy = b.x - a.x, b.y - a.y
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        if (self.cx - a.x) * nx + (self.cy - a.y) * ny < 0:
            nx, ny = -nx, -ny
        light = self._face_light(nx, ny, 0.78, 0.34)
        col = _shade(col, light)
        bottom, top = row(0.0), row(WALL_HEIGHT)
        if detail and not city and fwd < 1800 and (i // 7) % 3 == 1:
            # tyre barrier: rows of stacked tyres (dark treads, lighter sidewall seams) held by a coloured belt
            tyre = _fade(_shade((40, 40, 45), light), col, fwd, 1800)
            self.poly(surf, bottom + top[::-1], tyre)
            if fwd < 1100:
                seam = _fade(_shade((70, 70, 76), light), tyre, fwd, 1100)
                for z in (WALL_HEIGHT * 0.25, WALL_HEIGHT * 0.5):
                    self.poly(surf, row(z - 0.35) + row(z + 0.35)[::-1], seam, smooth=False)
            self.poly(surf, row(WALL_HEIGHT * 0.62) + row(WALL_HEIGHT * 0.84)[::-1], col)
        else:
            self.poly(surf, bottom + top[::-1], col)
            if detail and fwd < 1400:
                # a darker base where the barrier meets the ground and a lit rim along the top: reads as a
                # solid concrete block instead of a paper-thin wall
                self.poly(surf, bottom + row(1.6)[::-1], _fade(_shade(col, 0.72), col, fwd, 1400), smooth=False)
                self.poly(surf, row(WALL_HEIGHT - 1.0) + top[::-1], _fade(_shade(col, 1.18), col, fwd, 1400),
                          smooth=False)
        if not detail:
            return
        if fwd < 1900 and (i // 9) % 5 == 0:
            primary, secondary = SPONSORS[(i // 45) % len(SPONSORS)]
            primary = _fade(primary, self._fog_col, fwd, 1900)
            self.poly(surf, top + row(WALL_HEIGHT + 9)[::-1], primary)
            if fwd < 1300:
                self.poly(surf, row(WALL_HEIGHT + 3.2) + row(WALL_HEIGHT + 5.6)[::-1],
                          _fade(secondary, primary, fwd, 1300))
        elif city and fwd < 1300:
            # catch fence on top of the street circuit barriers: two wires and a post per stripe
            fence = (70, 72, 78)
            high = WALL_HEIGHT + 24
            for wire in (row(high), row(WALL_HEIGHT + 12)):
                if min(p[2] for p in wire) > self.near:
                    col_w = self.fog(fence, wire[0][2])
                    line = [self.project(p) for p in wire]
                    if self.aa:
                        pygame.draw.aalines(surf, col_w, False, line)
                    else:
                        pygame.draw.lines(surf, col_w, False, line)
                else:
                    for p, q in zip(wire, wire[1:]):
                        self._line3d(surf, p, q, fence)
            self._line3d(surf, top[0], to_cam(pts[0].x, pts[0].y, high + 2), (50, 52, 56), 2)

    def _draw_grid_marks(self, surf: pygame.Surface, track: "Track") -> None:
        marks = getattr(track, "_grid_marks", None)
        if marks is None:
            marks = []
            for slot in range(22):
                pos, heading = track.grid_pose(slot)
                f = Vector2(math.cos(heading), math.sin(heading))
                r = Vector2(-f.y, f.x)
                front = pos + f * 18
                marks.append([front - r * 10, front + r * 10, front + r * 10 + f * 2.2, front - r * 10 + f * 2.2])
                marks.append([front + r * 10 - f * 14, front + r * 10, front + r * 8.4, front + r * 8.4 - f * 14])
                marks.append([front - r * 10 - f * 14, front - r * 10, front - r * 8.4, front - r * 8.4 - f * 14])
            track._grid_marks = marks
        to_cam = self.to_cam
        for quad in marks:
            p = quad[0]
            fwd = (p.x - self.cx) * self.fx + (p.y - self.cy) * self.fy
            if -20 < fwd < 1200:
                self.poly(surf, [to_cam(q.x, q.y, 0.2) for q in quad], (236, 236, 236))

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
        geo = getattr(track, "_pit_geo_3d", None)
        if geo is None:
            geo = track._pit_geo_3d = self._pit_geometry(track)
        to_cam = self.to_cam
        cx, cy, fx, fy = self.cx, self.cy, self.fx, self.fy
        for quad, color, z in geo:
            mid = quad[0]
            fwd = (mid.x - cx) * fx + (mid.y - cy) * fy
            if fwd > self._far or fwd < -60:
                continue
            if z > 0.0 and fwd > 900:
                continue                            # paint is lost in the distance anyway
            self.poly(surf, [to_cam(q.x, q.y, z) for q in quad], color, smooth=False)

    @staticmethod
    def _pit_geometry(track: "Track") -> list[tuple[list[Vector2], Color, float]]:
        """The pit lane as ground quads, built once: concrete apron by the garages, asphalt, white edge lines and
        the yellow limiter lines. Each: (corners, colour, height)."""
        pit = track.pit
        assert pit is not None
        hw = pit.HALF_WIDTH

        def at(u: float, d: float) -> Vector2:
            return track.pose_at(pit.entry_s + u, pit.lateral(u) + pit.side * d)[0]

        out: list[tuple[list[Vector2], Color, float]] = []

        def band(u0: float, u1: float, d0: float, d1: float, color: Color, z: float, step: float) -> None:
            u = u0
            while u < u1 - 1e-6:
                v = min(u1, u + step)
                out.append(([at(u, d0), at(v, d0), at(v, d1), at(u, d1)], color, z))
                u = v

        work0, work1 = pit.RAMP - 20, pit.length - pit.RAMP + 20
        band(work0, work1, hw, hw + 50, (118, 120, 124), 0.0, 48.0)
        band(0.0, pit.length, -hw, hw, (52, 53, 58), 0.0, 24.0)
        for d in (-hw, hw - 1.4):
            band(0.0, pit.length, d, d + 1.4, (225, 225, 225), 0.12, 24.0)
        for u in (pit.RAMP, pit.length - pit.RAMP):
            band(u - 1.5, u + 1.5, -hw, hw, (255, 205, 40), 0.15, 3.0)
        return out

    def _draw_garage(self, surf: pygame.Surface, pos: Vector2, heading: float, color: Color, side: int,
                     night: bool) -> None:
        """A pit garage: concrete walls, a team-coloured fascia and roof, and a lit opening towards the lane."""
        self._draw_oriented_box(surf, pos, heading, 26, 16, 22, (150, 152, 158))
        self._draw_oriented_box(surf, pos, heading, 26.5, 16.5, 8, color, z0=22)
        self._draw_oriented_box(surf, pos, heading, 27.5, 17.5, 1.5, _shade(color, 0.55), z0=30)
        fx, fy = math.cos(heading), math.sin(heading)
        ox, oy = fy * side, -fx * side            # towards the lane
        face_x, face_y = pos.x + ox * 16.2, pos.y + oy * 16.2
        if (self.cx - face_x) * ox + (self.cy - face_y) * oy <= 0:
            return                                  # opening faces away from the camera
        inner = (78, 74, 62) if night else (36, 38, 44)
        corners = [(-22, 0.0), (22, 0.0), (22, 18.0), (-22, 18.0)]
        self.poly(surf, [self.to_cam(face_x + fx * a, face_y + fy * a, z) for a, z in corners], inner)
        # a sliver of the back wall and the team's logo board inside
        self.poly(surf, [self.to_cam(face_x + fx * a, face_y + fy * a, z)
                         for a, z in ((-10, 11.0), (10, 11.0), (10, 15.0), (-10, 15.0))], _shade(color, 0.8))

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
                light = self._face_light(wnx, wny, 0.72, 0.4)
            else:
                if self.cz < z0 + height:
                    continue
                light = 0.92 + 0.22 * self._sunv[2]
            self.poly(surf, [corners[k] for k in idx], _shade(color, light))

    # ------------------------------------------------------------------ scenery
    def _draw_scenery_shadows(self, surf: pygame.Surface, track: "Track", far: float, fov: float) -> None:
        """Ground shadows of the buildings (footprint swept away from the sun) and contact shadows of the trees."""
        cx, cy, sfx, sfy, srx, sry = self.cx, self.cy, self.fx, self.fy, self.rx, self.ry
        grass = track.definition.grass
        building_col, tree_col = _shade(grass, 0.58), _shade(grass, 0.55)
        sdx, sdy = self._shadow_dir
        for item in track.scenery:
            p = item[1]
            dx, dy = p.x - cx, p.y - cy
            fwd = dx * sfx + dy * sfy
            if not 20 < fwd < far * FOG_END or abs(dx * srx + dy * sry) > fwd * fov + 220:
                continue
            if item[0] == "building":
                if fwd < 1700:
                    _, p, w, h, _col, height = item
                    self._ground_shadow(surf, (p.x - w / 2, p.x + w / 2, p.y - h / 2, p.y + h / 2, 0.0,
                                               float(height)), building_col)
            elif fwd < 900:
                _, p, r, _col, height = item
                ox, oy = sdx * height * 0.45, sdy * height * 0.45
                shadow = [self.to_cam(p.x + ox + math.cos(a) * r * 0.9, p.y + oy + math.sin(a) * r * 0.9, 0.15)
                          for a in (0, 1.05, 2.1, 3.14, 4.19, 5.24)]
                self.poly(surf, shadow, tree_col)

    def _draw_scenery(self, surf: pygame.Surface, item: tuple, fwd: float, detail: int, night: bool,
                      track: "Track") -> None:
        if item[0] == "building":
            _, p, w, h, col, height = item
            box = (p.x - w / 2, p.x + w / 2, p.y - h / 2, p.y + h / 2, 0.0, float(height))
            self._draw_box_world(surf, box, col, windows=detail >= 2 and fwd < 900, night=night,
                                 seed=int(p.x * 7 + p.y), smooth=fwd < 1400)
            return
        _, p, r, col, height = item
        base = self.to_cam(p.x, p.y, 0)
        top = self.to_cam(p.x, p.y, height)
        if base[2] < self.near or top[2] < self.near:
            return
        bx, by = self.project(base)
        tx, ty = self.project(top)
        trunk_w = max(1, int(self._focal * 2.5 / base[2]))
        rad = max(2, int(self._focal * r / top[2]))
        conifer = track.definition.key == "spa" or (detail and int(p.x + p.y) % 4 == 0)
        if conifer:
            pygame.draw.line(surf, self.fog((80, 56, 34), base[2]), (bx, by), (tx, ty + rad * 0.6), trunk_w)
            dark, mid, light = (self.fog(_shade(col, k), top[2]) for k in (0.55, 0.72, 0.9))
            span = by - (ty - rad * 0.9)
            for k, c in enumerate((dark, mid, light)):
                y0 = ty - rad * 0.9 + span * (0.18 + k * 0.22)
                hw = rad * (0.75 + k * 0.18)
                tip = ty - rad * 0.9 + span * k * 0.2
                pts = [(tx, tip), (tx + hw, y0 + span * 0.32), (tx - hw, y0 + span * 0.32)]
                pygame.draw.polygon(surf, c, pts)
                if self.aa:
                    pygame.draw.aalines(surf, c, True, pts)
            return
        pygame.draw.line(surf, self.fog((90, 60, 35), base[2]), (bx, by), (tx, ty), trunk_w)
        if detail and rad > 6:
            # a fuller crown: shaded clumps at the bottom and the far side, lit clumps towards the sun
            seed = int(p.x * 13 + p.y * 7)
            lean = 0.12 if seed % 2 else -0.12
            fog = top[2]
            blobs = (((tx, ty + rad * 0.2), rad, self.fog(_shade(col, 0.62), fog)),
                     ((tx + rad * (0.38 + lean), ty + rad * 0.05), int(rad * 0.68), self.fog(_shade(col, 0.75), fog)),
                     ((tx - rad * 0.4, ty + rad * 0.02), int(rad * 0.7), self.fog(_shade(col, 0.88), fog)),
                     ((tx + rad * lean, ty - rad * 0.32), int(rad * 0.72), self.fog(col, fog)),
                     ((tx - rad * 0.3, ty - rad * 0.36), int(rad * 0.42), self.fog(_shade(col, 1.18), fog)),
                     ((tx - rad * 0.42, ty - rad * 0.5), max(2, int(rad * 0.18)), self.fog(_shade(col, 1.35), fog)))
        else:
            blobs = (((tx, ty + rad * 0.15), rad, self.fog(_shade(col, 0.7), top[2])),
                     ((tx - rad * 0.15, ty), int(rad * 0.85), self.fog(col, top[2])))
        for (ccx, ccy), cr, cc in blobs:
            pygame.draw.circle(surf, cc, (ccx, ccy), cr)
            if self.aa:
                pygame.gfxdraw.aacircle(surf, int(ccx), int(ccy), cr, cc)

    def _ground_shadow(self, surf: pygame.Surface, box: tuple[float, ...], color: Color) -> None:
        """The shadow a box throws on the ground: its footprint swept away from the sun (convex hull)."""
        x0, x1, y0, y1, _z0, z1 = box
        sx, sy = self._shadow_dir
        reach = min(z1, 120.0)
        ox, oy = sx * reach, sy * reach
        if abs(ox) + abs(oy) < 2:
            return
        foot = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        pts = sorted(foot + [(x + ox, y + oy) for x, y in foot])

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lower: list = []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper: list = []
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        hull = lower[:-1] + upper[:-1]
        self.poly(surf, [self.to_cam(x, y, 0.1) for x, y in hull], color, smooth=False)

    def _draw_box_world(self, surf: pygame.Surface, box: tuple[float, ...], color: Color, windows: bool = False,
                        night: bool = False, seed: int = 0, smooth: bool = True) -> None:
        x0, x1, y0, y1, z0, z1 = box
        cam = [self.to_cam(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        fl = self._face_light
        sides = [((0, 1, 3, 2), self.cx < x0, fl(-1, 0), (x0, None)), ((4, 5, 7, 6), self.cx > x1, fl(1, 0), (x1, None)),
                 ((0, 1, 5, 4), self.cy < y0, fl(0, -1), (None, y0)), ((2, 3, 7, 6), self.cy > y1, fl(0, 1), (None, y1))]
        for idx, visible, shade, plane in sides:
            if not visible:
                continue
            self.poly(surf, [cam[k] for k in idx], _shade(color, shade), smooth=smooth)
            if windows and z1 - z0 > 24:
                self._window_bands(surf, box, plane, color, night, seed)
        if self.cz > z1:
            self.poly(surf, [cam[1], cam[3], cam[7], cam[5]], _shade(color, 1.15), smooth=smooth)

    def _window_bands(self, surf: pygame.Surface, box: tuple[float, ...], plane: tuple, color: Color, night: bool,
                      seed: int) -> None:
        x0, x1, y0, y1, z0, z1 = box
        px, py = plane
        inset = 4.0
        if px is not None:
            ends = ((px, y0 + inset), (px, y1 - inset))
        else:
            ends = ((x0 + inset, py), (x1 - inset, py))
        (ax, ay), (bx, by) = ends
        z = z0 + 10
        k = 0
        saved = self._amb
        while z + 6 < z1 - 4:
            if night:
                lit = (seed + k * 7) % 5 != 0
                col = (255, 208, 130) if lit else (34, 36, 48)
                self._amb = None
            else:
                col = _mix(_shade(color, 0.5), (120, 150, 190), 0.35)
            self.poly(surf, [self.to_cam(ax, ay, z), self.to_cam(bx, by, z), self.to_cam(bx, by, z + 6),
                             self.to_cam(ax, ay, z + 6)], col)
            self._amb = saved
            z += 14
            k += 1

    # ------------------------------------------------------------------ trackside props
    @staticmethod
    def _gravel(track: "Track") -> dict[int, float]:
        """Waypoint -> side (+1/-1) of a gravel trap: the outside of every corner, a little past its kerbs."""
        cached = getattr(track, "_gravel3d", None)
        if cached is not None:
            return cached
        n = track.n
        beds: dict[int, float] = {}
        curb = track.curb_segment
        for i in range(n):
            if not curb[i]:
                continue
            a, b = track.tangents[(i - 6) % n], track.tangents[(i + 6) % n]
            bend = a.x * b.y - a.y * b.x
            if abs(bend) < 0.05:
                continue
            side = -1.0 if bend > 0 else 1.0
            for k in range(-2, 7):          # the bed starts at the apex and runs on past the corner exit
                beds.setdefault((i + k) % n, side)
        track._gravel3d = beds
        return beds

    @staticmethod
    def _decals(track: "Track") -> list[tuple]:
        """Marks on the asphalt, built once per track: (first waypoint, kind, lateral from, lateral to, waypoints).
        Skid marks follow the racing line into every braking zone (two tyres, a few cars); patches are repaired
        rectangles of asphalt."""
        cached = getattr(track, "_decals3d", None)
        if cached is not None:
            return cached
        rng = random.Random(sum(map(ord, track.definition.key)) * 31 + 5)
        n, hw = track.n, track.half_width
        out: list[tuple] = []
        bz = track.brake_zone
        if bz and track.line_offset:
            for i in range(n):
                if bz[i] and not bz[i - 1]:
                    for _car in range(rng.randint(2, 3)):
                        start = i + rng.randint(1, 5)
                        length = rng.randint(6, 14)
                        ks = [(start + k) % n for k in range(0, length + 1, 2)]
                        jitter = rng.uniform(-3.0, 3.0)
                        for tyre in (-5.2, 5.2):
                            off = tyre + jitter
                            out.append((ks[0], "skid", off - 0.8, off + 0.8, ks))
        for i in range(0, n, 37):
            if rng.random() < 0.35:
                lat0 = rng.uniform(-hw + 4, hw - 24)
                ks = [(i + k) % n for k in range(rng.randint(2, 4))]
                out.append((ks[0], "patch", lat0, lat0 + rng.uniform(8, 20), ks))
        track._decals3d = out
        return out

    def _props(self, track: "Track", night: bool) -> list[tuple]:
        """Grandstands, start gantry, brake boards and (at night) floodlights, built once per track.
        Each prop: (kind, position, ..., reach) - reach is how far it extends from its position."""
        cached = getattr(track, "_props3d", None)
        if cached is not None:
            return cached
        rng = random.Random(sum(map(ord, track.definition.key)) * 13 + 1)
        n, hw, wl = track.n, track.half_width, track.wall_limit
        cx, cy = track._cx, track._cy
        pit_side = track.pit.side if track.pit is not None else 1.0
        props: list[tuple] = []

        def clear(p: Vector2, r: float) -> bool:
            return min(math.hypot(cx[j] - p.x, cy[j] - p.y) for j in range(0, n, 2)) > r

        def heading_at(i: int) -> float:
            t = track.tangents[i % n]
            return math.atan2(t.y, t.x)
        # start gantry over the grid
        props.append(("gantry", Vector2(track.center[2]), heading_at(2), hw, hw + 30))
        # grandstands: the main one along the start straight, more on the outside of corners
        spots: list[tuple[int, float]] = [((n - 14) % n, -pit_side)]
        corners = [i for i in range(0, n, 6) if track.curb_segment[i]]
        rng.shuffle(corners)
        for i in corners:
            if len(spots) >= 5:
                break
            if any(min((i - j) % n, (j - i) % n) < n // 8 for j, _ in spots):
                continue
            a, b = track.tangents[i - 8], track.tangents[(i + 8) % n]
            bend = a.x * b.y - a.y * b.x
            spots.append((i, -1.0 if bend > 0 else 1.0))
        for i, side in spots:
            nv = track.normals[i]
            depth = 48.0
            length = 170.0 if not props[1:] else 120.0
            pos = track.center[i] + nv * side * (wl + 18 + depth / 2)
            heading = heading_at(i)
            f = Vector2(math.cos(heading), math.sin(heading))
            if not all(clear(pos + f * k * length / 2 + nv * side * depth / 2 * m, wl + 10)
                       for k in (-1, 0, 1) for m in (-1, 1)):
                continue
            out = nv * side
            crowd = []
            for tier in range(4):
                for j in range(int(length / 5)):
                    along = -length / 2 + 2 + j * 5 + rng.uniform(-1, 1)
                    q = pos + f * along + out * (-depth / 2 + 6 + tier * 11)
                    crowd.append((q.x, q.y, 7.0 + tier * 8 + 1.6, rng.choice(CROWD), rng.random() * TAU))
            props.append(("stand", pos, heading, out, length, depth, crowd, length / 2 + depth))
        # brake marker boards (3-2-1) before every braking zone
        bz = track.brake_zone
        if bz:
            for i in range(n):
                if bz[i] and not bz[i - 1]:
                    for k, back in enumerate((0, 9, 18)):
                        j = (i - back) % n
                        side = -1.0 if (i // 3) % 2 else 1.0
                        p = track.center[j] + track.normals[j] * side * (hw + 16)
                        props.append(("board", p, heading_at(j), k + 1, 12.0))
        # digital marshal panels (LED flag boards on posts beside the track)
        for k, (i, side) in enumerate(marshal_posts(track)):
            p = track.center[i] + track.normals[i] * side * min(wl - 3.0, hw + 26.0)
            props.append(("panel", p, heading_at(i), k, 14.0))
        # floodlights (night race)
        for i in range(0, n, 16):
            side = 1.0 if (i // 16) % 2 else -1.0
            p = track.center[i] + track.normals[i] * side * (wl + 24)
            if clear(p, wl + 12):
                props.append(("flood", p, heading_at(i), side, 30.0))
        track._props3d = props
        return props

    def _draw_prop(self, surf: pygame.Surface, prop: tuple, lights: int | None, night: bool) -> None:
        kind = prop[0]
        to_cam = self.to_cam
        if kind == "stand":
            _, pos, heading, out, length, depth, crowd, _ = prop
            seat = (64, 70, 88)
            # back tiers first (higher, further from the track), then the ones in front
            for tier in range(3, -1, -1):
                c = pos + out * (-depth / 2 + 6 + tier * 11)
                self._draw_oriented_box(surf, c, heading, length / 2, 5.5, 7.0 + tier * 8,
                                        _shade(seat, 0.85 + tier * 0.08))
                self._draw_crowd(surf, crowd, tier, length)
            roof_c = pos + out * (depth / 2 - 18)
            self._draw_oriented_box(surf, roof_c, heading, length / 2 + 4, 26, 2.5, (210, 212, 220), z0=46)
            f = Vector2(math.cos(heading), math.sin(heading))
            for k in (-1, 1):
                b = pos + f * k * length / 2 + out * (depth / 2 - 4)
                self._line3d(surf, to_cam(b.x, b.y, 0), to_cam(b.x, b.y, 46), (150, 152, 160), 2)
            if night:
                for k in (-0.3, 0.3):
                    b = roof_c + f * k * length
                    p = to_cam(b.x, b.y, 44)
                    if p[2] > self.near:
                        sx, sy = self.project(p)
                        self._glow(sx, sy, self._focal * 26 / p[2], (90, 90, 80))
        elif kind == "gantry":
            _, pos, heading, hw, _ = prop
            f = Vector2(math.cos(heading), math.sin(heading))
            r = Vector2(-f.y, f.x)
            for side in (-1, 1):
                self._draw_oriented_box(surf, pos + r * side * (hw + 8), heading, 2.2, 2.2, 54, (70, 72, 80))
            self._draw_oriented_box(surf, pos, heading, 3.0, hw + 10, 10, (236, 236, 240), z0=44)
            self._draw_oriented_box(surf, pos, heading, 3.1, hw + 10.2, 2.5, (220, 20, 30), z0=44)
            face = pos - f * 3.4
            for k in range(5):
                c = face + r * (k - 2) * 10
                p = to_cam(c.x, c.y, 49)
                if p[2] <= self.near:
                    continue
                sx, sy = self.project(p)
                rad = max(1.5, self._focal * 2.4 / p[2])
                for row in (-1, 1):
                    yy = sy + row * rad * 1.15
                    if lights is not None and lights < 0:
                        on, colr = True, (40, 255, 110)
                    else:
                        on, colr = lights is not None and k < lights, (255, 36, 30)
                    pygame.draw.circle(surf, colr if on else (44, 14, 14) if lights is not None and lights >= 0
                                       else (20, 40, 26), (sx, yy), rad)
                    if on:
                        self._glow(sx, yy, rad * 5, (110, 30, 24) if colr[1] < 100 else (20, 110, 50))
        elif kind == "board":
            _, pos, heading, stripes, _ = prop
            f = Vector2(math.cos(heading), math.sin(heading))
            r = Vector2(-f.y, f.x)
            a, b = pos - r * 5, pos + r * 5
            self._line3d(surf, to_cam(pos.x, pos.y, 0), to_cam(pos.x, pos.y, 6), (90, 90, 96), 2)
            self.poly(surf, [to_cam(a.x, a.y, 6), to_cam(b.x, b.y, 6), to_cam(b.x, b.y, 17),
                             to_cam(a.x, a.y, 17)], (240, 240, 240))
            for k in range(stripes):
                z = 7.5 + k * 3.2
                self.poly(surf, [to_cam(a.x, a.y, z), to_cam(b.x, b.y, z), to_cam(b.x, b.y, z + 1.6),
                                 to_cam(a.x, a.y, z + 1.6)], (24, 24, 28))
        elif kind == "panel":
            self._draw_flag_panel(surf, prop, night)
        elif kind == "flood" and night:
            _, pos, heading, side, _ = prop
            base, top = to_cam(pos.x, pos.y, 0), to_cam(pos.x, pos.y, 78)
            self._line3d(surf, base, top, (90, 92, 100), 3)
            f = Vector2(math.cos(heading), math.sin(heading))
            for k in (-1, 1):
                c = pos + f * k * 5
                p = to_cam(c.x, c.y, 78)
                if p[2] > self.near:
                    sx, sy = self.project(p)
                    pygame.draw.circle(surf, (255, 250, 230), (sx, sy), max(1, self._focal * 1.6 / p[2]))
                    self._glow(sx, sy, self._focal * 34 / p[2], (130, 124, 104))

    def _draw_flag_panel(self, surf: pygame.Surface, prop: tuple, night: bool) -> None:
        """A digital marshal panel: black LED board on a post, facing the oncoming cars."""
        _, pos, heading, k, _ = prop
        states = getattr(self, "_flag_states", ())
        state = states[k] if k < len(states) else "off"
        to_cam = self.to_cam
        f = Vector2(math.cos(heading), math.sin(heading))
        r = Vector2(-f.y, f.x)
        if (pos.x - self.cx) * self.fx + (pos.y - self.cy) * self.fy < 0:
            return
        self._line3d(surf, to_cam(pos.x, pos.y, 0), to_cam(pos.x, pos.y, 9), (80, 82, 90), 2)
        face = pos - f * 0.4
        a, b = face - r * 6.5, face + r * 6.5
        self.poly(surf, [to_cam(a.x, a.y, 8.5), to_cam(b.x, b.y, 8.5), to_cam(b.x, b.y, 18.5),
                         to_cam(a.x, a.y, 18.5)], (14, 14, 16))
        face = pos - f * 0.6
        t = pygame.time.get_ticks()
        blink = (t // 280) % 2 == 0

        def quad(u0: float, u1: float, z0: float, z1: float, col: Color) -> None:
            p0, p1 = face + r * u0, face + r * u1
            self.poly(surf, [to_cam(p0.x, p0.y, z0), to_cam(p1.x, p1.y, z0), to_cam(p1.x, p1.y, z1),
                             to_cam(p0.x, p0.y, z1)], col)

        lit = None
        if state == "off":
            quad(-5.6, 5.6, 9.4, 17.6, (30, 32, 36))
        elif state == "chequered":
            for row in range(3):
                for col in range(4):
                    c = (236, 236, 236) if (row + col) % 2 else (18, 18, 20)
                    quad(-5.6 + col * 2.8, -2.8 + col * 2.8, 9.4 + row * 2.73, 12.13 + row * 2.73, c)
            lit = (90, 90, 90)
        elif state in ("sc", "vsc"):
            on = blink
            quad(-5.6, 5.6, 9.4, 17.6, (255, 205, 20) if on else (60, 50, 10))
            # the letters as LED blocks: "SC" = two blocks, "VSC" = three
            n_blocks = 2 if state == "sc" else 3
            w = 11.2 / (n_blocks * 2 + 1)
            for j in range(n_blocks):
                u = -5.6 + w * (1 + 2 * j)
                quad(u, u + w, 11.4, 15.6, (20, 18, 10))
            lit = (110, 90, 10) if on else None
        elif state == "yellow2":
            top = blink
            quad(-5.6, 5.6, 13.6, 17.6, (255, 210, 20) if top else (60, 50, 10))
            quad(-5.6, 5.6, 9.4, 13.4, (60, 50, 10) if top else (255, 210, 20))
            lit = (120, 96, 10)
        else:
            col = {"green": (40, 235, 90), "yellow": (255, 210, 20), "blue": (40, 120, 255)}.get(state, (30, 32, 36))
            on = blink or state == "green"
            quad(-5.6, 5.6, 9.4, 17.6, col if on else _shade(col, 0.25))
            if on:
                lit = _shade(col, 0.45)
        if lit is not None:
            p = to_cam(face.x, face.y, 13.5)
            if p[2] > self.near and p[2] < 2400:
                sx, sy = self.project(p)
                self._glow(sx, sy, self._focal * (22 if night else 14) / p[2], lit)

    # ------------------------------------------------------------------ pit crews
    def _draw_box_marks(self, surf: pygame.Surface, crews: Sequence[tuple], target: "Car | None" = None) -> None:
        """Each team's pit box painted on the lane: a tinted box with a frame in the team colour and the white line
        the front wheels stop on. The box of the followed car glows while it has a stop ordered or is in the lane."""
        to_cam = self.to_cam
        mine = target.profile.team if target is not None and (target.pit_request is not None or target.in_pit) \
            else None
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.008)
        for pos, heading, color, *_ in crews:
            fwd = (pos.x - self.cx) * self.fx + (pos.y - self.cy) * self.fy
            if not -60 < fwd < 1100:
                continue
            f = Vector2(math.cos(heading), math.sin(heading))
            r = Vector2(-f.y, f.x)

            def quad(x0: float, x1: float, y0: float, y1: float, col: Color, z: float) -> None:
                pts = [pos + f * x0 + r * y0, pos + f * x1 + r * y0, pos + f * x1 + r * y1, pos + f * x0 + r * y1]
                self.poly(surf, [to_cam(q.x, q.y, z) for q in pts], col)

            quad(-21.0, 21.0, -13.0, 13.0, tuple(int(40 + c * 0.18) for c in color), 0.2)
            for x0, x1 in ((19.0, 21.0), (-21.0, -19.0)):
                quad(x0, x1, -13.0, 13.0, color, 0.25)
            for y0, y1 in ((-13.0, -11.8), (11.8, 13.0)):
                quad(-21.0, 21.0, y0, y1, color, 0.25)
            stop = CAR_LENGTH * 0.5 - 6
            quad(stop - 0.6, stop + 0.6, -11.0, 11.0, (240, 240, 240), 0.3)
        if mine is None:
            return
        for pos, heading, _color, _car, team in crews:
            if team != mine:
                continue
            f = Vector2(math.cos(heading), math.sin(heading))
            r = Vector2(-f.y, f.x)
            glow = (int(90 + 165 * pulse), 230, 255)
            for x0, x1, y0, y1 in ((23.0, 25.0, -16.0, 16.0), (-25.0, -23.0, -16.0, 16.0), (-25.0, 25.0, -16.0, -14.5),
                                   (-25.0, 25.0, 14.5, 16.0)):
                pts = [pos + f * x0 + r * y0, pos + f * x1 + r * y0, pos + f * x1 + r * y1, pos + f * x0 + r * y1]
                self.poly(surf, [to_cam(q.x, q.y, 0.35) for q in pts], glow, fog_depth=-1)

    # crew stations around the car (box frame: x forward, y right): (x, y, job, wheel)
    _STATIONS: list[tuple[float, float, str, int]] = [
        *[(wx + dx, s * dy, job, w) for w, (wx, s) in enumerate(((9.8, -1), (9.8, 1), (-10.3, -1), (-10.3, 1)))
          for dx, dy, job in ((0.0, 12.5, "gun"), (-4.5, 15.0, "off"), (4.5, 15.0, "on"))],
        (24.0, 0.0, "jack", -1), (-23.5, 0.0, "jack", -1), (0.5, -12.5, "hold", -1), (0.5, 12.5, "hold", -1),
        (17.0, -17.0, "lolli", -1),
    ]

    def _crew_people(self, crews: Sequence[tuple]) -> list[tuple]:
        """The people of every box that is expecting or servicing a car. Each: (position, heading, shirt colour,
        crouching, carried tyre ("old"/"new"/None), lollipop colour or None)."""
        people = []
        for pos, heading, color, car, *_ in crews:
            if car is None:
                continue
            fwd = (pos.x - self.cx) * self.fx + (pos.y - self.cy) * self.fy
            if not -40 < fwd < 1000:
                continue
            service = car.pit_service if car.pit_stopped else None
            working = service is not None and (car.pit_stop_timer > 0 or car.pit_hold)
            e = service["t"] if working else 0.0
            wheels = service.get("wheels") if working else None
            f = Vector2(math.cos(heading), math.sin(heading))
            r = Vector2(-f.y, f.x)
            for x, y, job, w in self._STATIONS:
                carry = None
                out = 0.0
                if job == "on":
                    carry = "new" if not wheels or e < wheels[w][1] - 0.15 else None
                elif job == "off" and wheels and e >= wheels[w][0]:
                    carry = "old"
                    out = min(4.0, (e - wheels[w][0]) * 9.0)     # carries the old tyre away from the car
                lolli = None
                if job == "lolli":
                    lolli = (40, 220, 90) if car.pit_stopped and not working else (230, 40, 40)
                side = 1.0 if y > 0 else -1.0 if y < 0 else 0.0
                p = pos + f * x + r * (y + side * out)
                face = heading + (math.pi / 2 * -side if side else (math.pi if x > 0 else 0.0))
                people.append((p, face, color, job in ("gun", "jack") and (working or job == "gun"), carry, lolli))
        return people

    def _draw_person(self, surf: pygame.Surface, person: tuple) -> None:
        pos, heading, color, crouch, carry, lolli = person
        height = 3.4 if crouch else 5.4
        self._draw_oriented_box(surf, pos, heading, 0.9, 1.5, height * 0.45, (32, 34, 40))       # legs
        self._draw_oriented_box(surf, pos, heading, 1.0, 1.6, height * 0.55, color, z0=height * 0.45)
        head = self.to_cam(pos.x, pos.y, height + 0.9)
        if head[2] > self.near:
            sx, sy = self.project(head)
            rad = max(1.0, self._focal * 1.0 / head[2])
            col = self.fog((236, 236, 240), head[2])
            pygame.draw.circle(surf, col, (sx, sy), rad)
            if rad > 3:
                pygame.draw.circle(surf, self.fog((30, 30, 36), head[2]), (sx, sy + rad * 0.15), rad * 0.55)
        f = Vector2(math.cos(heading), math.sin(heading))
        if carry:
            t = pos + f * 2.2
            self._draw_oriented_box(surf, t, heading, 1.3, 1.8, 3.4, (22, 22, 24), z0=1.0)
            if carry == "new":
                self._draw_oriented_box(surf, t, heading, 1.35, 0.6, 1.2, (220, 40, 40), z0=2.1)
        if lolli is not None:
            a = self.to_cam(pos.x, pos.y, height)
            top = pos + f * 4.0
            b = self.to_cam(top.x, top.y, 9.0)
            self._line3d(surf, a, b, (200, 200, 200), 2)
            if b[2] > self.near:
                sx, sy = self.project(b)
                pygame.draw.circle(surf, self.fog(lolli, b[2]), (sx, sy), max(2.0, self._focal * 1.8 / b[2]))

    def _draw_crowd(self, surf: pygame.Surface, crowd: list, tier: int, length: float) -> None:
        p0 = crowd[0]
        fwd = (p0[0] - self.cx) * self.fx + (p0[1] - self.cy) * self.fy
        if fwd > 1100:
            return
        per_tier = int(length / 5)
        t = self.time
        f = self._focal
        near = self.near
        for x, y, z, col, ph in crowd[tier * per_tier:(tier + 1) * per_tier]:
            p = self.to_cam(x, y, z + 0.5 * math.sin(t * 7 + ph))
            if p[2] <= near:
                continue
            sx, sy = self.project(p)
            s = f * 1.7 / p[2]
            if s < 0.8:
                surf.set_at((int(sx), int(sy)), self.fog(col, p[2]))
            else:
                surf.fill(self.fog(col, p[2]), (int(sx - s / 2), int(sy - s), max(1, int(s)), max(1, int(s * 1.6))))

    def _draw_particle(self, surf: pygame.Surface, p, night: bool) -> None:
        z = getattr(p, "z", 2.0)
        cam = self.to_cam(p.x, p.y, z)
        if cam[2] <= self.near * 2:
            return
        sx, sy = self.project(cam)
        if p.kind == "spark":
            tail = self.to_cam(p.x - p.vx * 0.03, p.y - p.vy * 0.03, z - getattr(p, "vz", 0.0) * 0.03)
            if tail[2] <= self.near:
                return
            tx, ty = self.project(tail)
            pygame.draw.line(surf, p.color, (sx, sy), (tx, ty), max(1, int(self._focal * 0.5 / cam[2])))
            if night or cam[2] < 200:
                self._glow(sx, sy, max(3.0, self._focal * 2.0 / cam[2]), (90, 60, 20))
            return
        t = p.life / p.max_life
        r = self._focal * p.size * 0.8 / cam[2]
        if r < 1:
            return
        r = int(r) if r < 20 else int(r) // 4 * 4 if r < 80 else min(160, int(r) // 16 * 16)
        base = 90 if p.kind == "smoke" else 120
        alpha = max(8, int(base * t)) // 16 * 16 + 8
        col = p.color if not night else _shade(p.color, 0.45)
        key = (r, col, alpha)
        img = self._blob_cache.get(key)
        if img is None:
            img = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            for k in range(3):
                rr = max(1, int(r * (1 - k * 0.28)))
                pygame.draw.circle(img, (*col, min(255, alpha // 3 + k * alpha // 4)), (r + 1, r + 1), rr)
            if len(self._blob_cache) > 700:
                self._blob_cache.clear()
            self._blob_cache[key] = img
        surf.blit(img, (sx - r - 1, sy - r - 1))

    # ------------------------------------------------------------------ cars
    def _spin_cars(self, cars: Sequence["Car"], dt: float) -> None:
        """Turn every car's wheels by the distance it rolled this frame (front and rear differ in size)."""
        rot = self._wheel_rot
        for car in cars:
            v = getattr(car, "speed_fwd", 0.0)
            if getattr(car, "pit_lift", 0.0) > 0.5:
                v = 0.0
            fr, rr = rot.get(id(car), (0.0, 0.0))
            # rolling forwards turns the top of the wheel towards the nose
            rot[id(car)] = ((fr - v * dt / 2.5) % TAU, (rr - v * dt / 2.8) % TAU)

    def _draw_car(self, surf: pygame.Surface, car: "Car", depth: float, hide: tuple[str, ...] = (),
                  env: _Env | None = None, own: bool = False) -> None:
        h = car.heading
        fx, fy, rx, ry = math.cos(h), math.sin(h), -math.sin(h), math.cos(h)
        px, py = car.pos.x, car.pos.y
        body = car.color
        tyres = getattr(car, "tyres", None)
        rim = tyres.compound.color if tyres is not None else (150, 150, 158)
        helmet = car.profile.helmet
        wet = env is not None and (env.rain > 0.05 or env.wet > 0.3)
        blink = wet and int(self.time * 5 + (id(car) >> 4) % 3) % 2 == 0
        is_sc = getattr(car, "short", "") == "SC"
        cid = id(car)
        # brake discs heat up under hard braking at speed and glow orange
        speed = getattr(car, "speed_fwd", 0.0)
        heat = self._heat.get(cid, 0.0)
        heat = clamp(heat + (getattr(car, "brake", 0.0) * max(0.0, speed - 120) * 0.00004 - 0.004), 0.0, 1.0)
        self._heat[cid] = heat
        tcam = (250, 205, 30) if sum(map(ord, getattr(car, "name", ""))) % 2 else (22, 22, 24)
        colors = {"body": body, "helmet": helmet, "dark": _shade(body, 0.45), "carbon": (30, 30, 34),
                  "halo": (34, 34, 38), "mirror": (30, 30, 34),
                  "tyre": (24, 24, 27), "rim": (46, 48, 54), "band": rim, "visor": (12, 12, 16), "tcam": tcam,
                  "spoke": (150, 152, 160), "spoke_blur": (96, 98, 106),
                  "rainlight": (255, 40, 36) if blink else (70, 12, 12),
                  "accent": (min(255, body[0] + 70), min(255, body[1] + 70), min(255, body[2] + 70))}
        if is_sc:
            lights = getattr(car, "lights_on", True)
            flash = int(self.time * 6) % 2
            amber, dim = (255, 170, 20), (70, 44, 8)
            colors.update({"accent": (255, 140, 0), "rim": (196, 198, 204), "glass": (34, 42, 56), "dark": (22, 22, 26),
                           "headlight": (240, 240, 226), "taillight": (190, 26, 26),
                           "sc_l": amber if lights and flash == 0 else dim,
                           "sc_r": amber if lights and flash == 1 else dim})
        ghost = getattr(car, "ghost_visual", False)
        if ghost:
            # practice/qualifying ghosts: washed out towards the fog so they read as see-through
            colors = {k: (int(c[0] * 0.45 + FOG[0] * 0.55), int(c[1] * 0.45 + FOG[1] * 0.55),
                          int(c[2] * 0.45 + FOG[2] * 0.55)) for k, c in colors.items()}
        near = depth < 380          # small parts (mirrors, rims, stripes, ...) only close to the camera
        cam_l = ((self.cx - px) * fx + (self.cy - py) * fy, (self.cx - px) * rx + (self.cy - py) * ry)
        to_cam = self.to_cam
        if not own:
            if env is not None and env.wet > 0.25 and depth < 900 and not ghost:
                self._draw_reflection(surf, car, env, fx, fy, rx, ry)
            ox, oy = self._shadow_dir[0] * 3.2, self._shadow_dir[1] * 3.2
            trk = getattr(car, "track", None)
            soft = _mix(trk.definition.asphalt if trk is not None else (58, 59, 64), (20, 20, 22), 0.45)
            for grow, col in ((1.12, soft), (0.94, (24, 24, 27))) if near else ((1.0, (28, 28, 31)),):
                shadow = [to_cam(px + ox + fx * lx * grow + rx * ly * grow, py + oy + fy * lx * grow + ry * ly * grow,
                                 0.2) for lx, ly in ((-17, -8), (17, -8), (17, 8), (-17, 8))]
                self.poly(surf, shadow, col)
        d = getattr(car, "damage", None)
        drs = bool(getattr(car, "straight_mode", False))

        def intact(tag: tuple[str, float]) -> bool:
            # broken parts fall off: first the endplate on the side that hit, then the whole wing
            kind, side = tag[0], tag[1]
            if kind == "drs_open":
                return drs and (d is None or d.rear < 0.7)
            if d is None:
                return not (kind == "rw" and drs)
            if kind == "fw":
                return d.front_wing < 0.5 or (d.front_wing < 0.85 and side != d.wing_side)
            if kind == "rw":
                return d.rear < 0.7 and not drs
            return True
        off = getattr(car, "pit_wheels_off", None)
        geometry = _SC_GEOMETRY if is_sc else _CAR_GEOMETRY
        if depth < 240 and not ghost:
            v = abs(getattr(car, "speed_fwd", 0.0))
            geometry = geometry + _wheel_spokes(_SC_WHEELS if is_sc else _CAR_WHEELS,
                                                self._wheel_rot.get(cid, (0.0, 0.0)),
                                                (v / 2.5 > SPIN_BLUR, v / 2.8 > SPIN_BLUR))
        parts = [g for g in geometry if (near or g[2]) and g[1] not in hide
                 and intact(g[4])
                 and not (off and g[4][2] >= 0 and off[g[4][2]])]
        # painter's order: far parts first (horizontal distance to the camera in car space)
        parts.sort(key=lambda g: -((g[3][0] - cam_l[0]) ** 2 + (g[3][1] - cam_l[1]) ** 2))
        # everything in car space: the camera and the sun are moved into the car's frame once, and car space ->
        # camera space is one affine map (origin + three axis vectors) instead of two transforms per vertex
        lwx, lwy, lz_ = self._sunv
        lcx, lcy = lwx * fx + lwy * fy, lwx * rx + lwy * ry
        camx, camy, camz = cam_l[0], cam_l[1], self.cz
        # specular: half vector between the sun and the view direction (once per car, car space)
        sk = self._sun_k
        vx, vy, vz = camx, camy, camz - 4.0
        vl = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
        hx, hy, hz = lcx + vx / vl, lcy + vy / vl, lz_ + vz / vl
        hl = math.sqrt(hx * hx + hy * hy + hz * hz) or 1.0
        hx, hy, hz = hx / hl, hy / hl, hz / hl
        diffuse = 0.45 * (0.55 + 0.45 * sk)
        base_l = 0.62 + 0.1 * (1.0 - sk)
        lift = getattr(car, "pit_lift", 0.0)      # up on the jacks during a pit stop
        o0, o1, o2 = to_cam(px, py, lift)
        a = to_cam(px + fx, py + fy, lift)
        b = to_cam(px + rx, py + ry, lift)
        c = to_cam(px, py, lift + 1.0)
        ex0, ex1, ex2 = a[0] - o0, a[1] - o1, a[2] - o2
        ey0, ey1, ey2 = b[0] - o0, b[1] - o1, b[2] - o2
        ez0, ez1, ez2 = c[0] - o0, c[1] - o1, c[2] - o2
        # fog and ambient light are the same for the whole car: fold them into one multiply-add per channel
        tt = depth * self._fog_inv
        t = 0.0 if tt <= 0 else 1.0 if tt >= 1 else tt ** 1.8
        amb = self._amb or (1.0, 1.0, 1.0)
        if own and self.cam.cockpit:
            amb = (amb[0] * 0.62, amb[1] * 0.62, amb[2] * 0.66)
        fc = self._fog_col
        m0, m1, m2 = amb[0] * (1 - t), amb[1] * (1 - t), amb[2] * (1 - t)
        a0, a1, a2 = fc[0] * t, fc[1] * t, fc[2] * t
        poly = self.poly
        steer = getattr(car, "steer_angle", 0.0) * 0.42 if near else 0.0
        cs, sn = math.cos(steer), math.sin(steer)
        for (verts, faces), role, _, _, tag in parts:
            cam = None
            col = colors[role]
            c0, c1, c2 = col[0] * m0, col[1] * m1, col[2] * m2
            gloss = role in ("body", "accent", "helmet", "glass")
            turn = steer and tag[0] == "steer"
            if turn:
                piv_y = 7.0 * tag[1]
                verts = [(_WHEEL_PIVOT + (vx - _WHEEL_PIVOT) * cs - (vy - piv_y) * sn,
                          piv_y + (vx - _WHEEL_PIVOT) * sn + (vy - piv_y) * cs, vz) for vx, vy, vz in verts]
            for idx, (nx, ny, nz), (fcx, fcy, fcz) in faces:
                if turn:
                    nx, ny = nx * cs - ny * sn, nx * sn + ny * cs
                    fcx, fcy = (_WHEEL_PIVOT + (fcx - _WHEEL_PIVOT) * cs - (fcy - 7.0 * tag[1]) * sn,
                                7.0 * tag[1] + (fcx - _WHEEL_PIVOT) * sn + (fcy - 7.0 * tag[1]) * cs)
                # back-face test against the camera (car space)
                if (camx - fcx) * nx + (camy - fcy) * ny + (camz - fcz) * nz <= 0:
                    continue
                if cam is None:
                    cam = [(o0 + ex0 * vx + ey0 * vy + ez0 * vz, o1 + ex1 * vx + ey1 * vy + ez1 * vz,
                            o2 + ex2 * vx + ey2 * vy + ez2 * vz) for vx, vy, vz in verts]
                light = base_l + diffuse * max(0.0, nx * lcx + ny * lcy + nz * lz_)
                if gloss:
                    if nz > 0.3:
                        light += 0.12      # glossy paint catches the sky
                    sp = nx * hx + ny * hy + nz * hz
                    if sp > 0.82:
                        # sun highlight on the paint: brighter and whiter
                        g = (sp - 0.82) * 5.6 * sk
                        g = g * g * 150.0
                        poly(surf, [cam[k] for k in idx], (min(255, int(c0 * light + a0 + g)),
                                                           min(255, int(c1 * light + a1 + g)),
                                                           min(255, int(c2 * light + a2 + g))), -1.0)
                        continue
                poly(surf, [cam[k] for k in idx], (min(255, int(c0 * light + a0)), min(255, int(c1 * light + a1)),
                                                   min(255, int(c2 * light + a2))), -1.0)
        if ghost or self._glows is None:
            return
        # lights: flashing rain light, glowing brake discs, safety car light bar
        if blink and "rainlight" not in hide:
            self._world_glow(px - fx * 17.6, py - fy * 17.6, 3.3, 9.0, (150, 24, 20))
        if heat > 0.25 and near:
            k = (heat - 0.25) / 0.75
            for side in (-1, 1):
                for ax in (9.8, -10.3):
                    self._world_glow(px + fx * ax + rx * side * 4.6, py + fy * ax + ry * side * 4.6, 2.6,
                                     3.5 + 3 * k, (int(150 * k), int(60 * k), int(10 * k)))
        if is_sc:
            on = int(self.time * 6) % 2
            if getattr(car, "lights_on", True):
                for side in (-1, 1):
                    lit = (on == 0) == (side < 0)
                    self._world_glow(px - fx * 2.6 + rx * side * 2.0, py - fy * 2.6 + ry * side * 2.0, 8.8,
                                     9.0 if lit else 4.0, (220, 130, 10) if lit else (60, 36, 4))
            if near or depth < 900:
                for side in (-1, 1):
                    self._world_glow(px + fx * 14.4 + rx * side * 4.4, py + fy * 14.4 + ry * side * 4.4, 3.9, 4.0,
                                     (150, 150, 130))
                    self._world_glow(px - fx * 15.2 + rx * side * 4.4, py - fy * 15.2 + ry * side * 4.4, 3.9, 3.0,
                                     (120, 16, 14))

    def _world_glow(self, x: float, y: float, z: float, size: float, color: Color) -> None:
        p = self.to_cam(x, y, z)
        if p[2] <= self.near:
            return
        sx, sy = self.project(p)
        self._glow(sx, sy, self._focal * size / p[2], color)

    def _draw_reflection(self, surf: pygame.Surface, car: "Car", env: _Env, fx: float, fy: float, rx: float,
                         ry: float) -> None:
        """Wet track: a smeared mirror image of the car below the road surface."""
        px, py = car.pos.x, car.pos.y
        depth = -5.5 * min(1.0, env.wet)
        col = _mix(_shade(car.color, 0.6), (40, 42, 48), 0.55)
        for lx, ly, nx, ny in ((17, 0, 1, 0), (-17, 0, -1, 0), (0, 7, 0, 1), (0, -7, 0, -1)):
            wnx, wny = fx * nx + rx * ny, fy * nx + ry * ny
            fcx, fcy = px + fx * lx + rx * ly, py + fy * lx + ry * ly
            if (self.cx - fcx) * wnx + (self.cy - fcy) * wny <= 0:
                continue
            if nx:
                a = (lx, -7.0)
                b = (lx, 7.0)
            else:
                a = (-17.0, ly)
                b = (17.0, ly)
            pa = (px + fx * a[0] + rx * a[1], py + fy * a[0] + ry * a[1])
            pb = (px + fx * b[0] + rx * b[1], py + fy * b[0] + ry * b[1])
            self.poly(surf, [self.to_cam(pa[0], pa[1], 0.1), self.to_cam(pb[0], pb[1], 0.1),
                             self.to_cam(pb[0], pb[1], depth), self.to_cam(pa[0], pa[1], depth)], col)

    # ------------------------------------------------------------------ post effects
    def _lens_flare(self, out: pygame.Surface, sx: float, sy: float, env: _Env) -> None:
        w, h = out.get_size()
        if not (0 <= sx < w and 0 <= sy < h):
            return
        c = out.get_at((int(sx), int(sy)))
        if c[0] + c[1] + c[2] < 600:
            return  # the sun is hidden behind something
        cx, cy = w / 2, h / 2
        dx, dy = cx - sx, cy - sy
        k = (1 - env.rain) * max(0.25, 1 - math.hypot(dx, dy) / (w * 0.7))
        for t, r, col in ((0.35, 26, (40, 34, 14)), (0.7, 12, (22, 40, 30)), (1.1, 44, (20, 26, 44)),
                          (1.45, 18, (40, 22, 30)), (1.8, 70, (14, 18, 26))):
            self._add_glow(out, sx + dx * t, sy + dy * t, r, (int(col[0] * k), int(col[1] * k), int(col[2] * k)))

    def _vignette(self, out: pygame.Surface, target: "Car") -> None:
        w, h = out.get_size()
        speed = max(0.0, getattr(target, "speed_fwd", 0.0)) / TOP_SPEED
        level = 1 + (int(speed * 3.9) if self.cam.kind in ("onboard", "chase") else 0)
        grade = getattr(self, "_grade", (1.0, 1.0, 1.0))
        key = ("vig", level, w, h, grade)
        img = self._scaled.get(key)
        if img is None:
            small = pygame.Surface((64, 36))
            strength = 0.16 + 0.07 * level
            for y in range(36):
                for x in range(64):
                    dx, dy = (x - 31.5) / 32, (y - 17.5) / 18
                    r = min(1.0, math.sqrt(dx * dx * 0.9 + dy * dy * 1.1))
                    v = 1.0 - strength * max(0.0, (r - 0.45) / 0.55) ** 1.8
                    small.set_at((x, y), (int(255 * v * grade[0]), int(255 * v * grade[1]), int(255 * v * grade[2])))
            img = pygame.transform.smoothscale(small, (w, h))
            self._scaled[key] = img
        out.blit(img, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    def _lens_rain(self, out: pygame.Surface, env: _Env, target: "Car", dt: float) -> None:
        w, h = out.get_size()
        drops = self._drops
        speed = max(0.0, getattr(target, "speed_fwd", 0.0)) / TOP_SPEED
        if env.rain > 0.05 and dt > 0:
            rate = env.rain * 26 * dt
            while rate > 0 and len(drops) < 40:
                if random.random() < rate:
                    drops.append([random.uniform(0, w), random.uniform(0, h * 0.85), random.uniform(3, 9), 0.0])
                rate -= 1
        cx, cy = w / 2, h * 0.42
        keep = []
        for d in drops:
            d[3] += dt
            # the airstream drags the drops outwards and down
            d[0] += (d[0] - cx) * speed * 1.4 * dt
            d[1] += (40 + (d[1] - cy) * speed * 1.2) * dt
            if d[3] > 4.0 or not (-20 < d[0] < w + 20 and -20 < d[1] < h + 20):
                continue
            keep.append(d)
            r = int(d[2])
            key = ("drop", r)
            img = self._scaled.get(key)
            if img is None:
                img = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(img, (210, 220, 235, 60), (r + 1, r + 1), r)
                pygame.draw.circle(img, (40, 46, 56, 70), (r + 1, r + 2), max(1, r - 2))
                pygame.draw.circle(img, (255, 255, 255, 150), (r - r // 3 + 1, r - r // 3 + 1), max(1, r // 4))
                self._scaled[key] = img
            out.blit(img, (d[0] - r, d[1] - r))
        self._drops = keep

    # ------------------------------------------------------------------ cockpit
    def _render_mirror(self, track: "Track", cars: Sequence["Car"], target: "Car", env: _Env) -> None:
        """Rear view for the cockpit mirrors: a small, simplified render looking backwards."""
        size = (360, 76)
        if self._mirror is None:
            self._mirror = pygame.Surface(size).convert()
        saved = (self.cam_pos, self.cam_heading, self.cam_z, self.pitch, self.roll, self.focal, self.near, self.ss,
                 self.aa, self._half_w, self._hy, self._focal, self._glows, self._sun_screen, self._clip_w, self._clip_h)
        h = target.heading
        self.cam_pos = target.pos + Vector2(math.cos(h), math.sin(h)) * 1.5
        self.cam_heading = wrap_angle(h + math.pi)
        self.cam_z, self.pitch, self.roll, self.near, self.ss, self.aa = 7.6, 0.02, 0.0, 2.0, 1, False
        self._glows = None
        self._half_w, self._hy, self._focal = size[0] / 2, size[1] * 0.40, 190.0
        self._clip_w, self._clip_h = size
        try:
            self._draw_world(self._mirror, track, cars, target, False, (), env, lite=True)
        finally:
            (self.cam_pos, self.cam_heading, self.cam_z, self.pitch, self.roll, self.focal, self.near, self.ss,
             self.aa, self._half_w, self._hy, self._focal, self._glows, self._sun_screen, self._clip_w,
             self._clip_h) = saved
            self._setup()

    def _font(self, name: str, size: int, bold: bool = True) -> pygame.font.Font:
        key = f"{name}{size}{bold}"
        f = self._fonts.get(key)
        if f is None:
            fam = "menlo,consolas,dejavusansmono,couriernew" if name == "mono" else \
                "helveticaneue,helvetica,arial,dejavusans"
            f = pygame.font.SysFont(fam, size, bold=bold)
            self._fonts[key] = f
        return f

    def _draw_cockpit(self, out: pygame.Surface, car: "Car", env: _Env) -> None:
        w, h = out.get_size()
        # mirrors on the sidepods
        if self._mirror is not None and self.detail != "low":
            img = pygame.transform.flip(self._mirror, True, False)
            mw, mh = 210, 64
            for k, rect in enumerate((pygame.Rect(34, h - 140, mw, mh), pygame.Rect(w - 34 - mw, h - 140, mw, mh))):
                housing = rect.inflate(16, 14)
                pygame.draw.rect(out, (16, 16, 18), housing, border_radius=14)
                src = pygame.Rect(0 if k == 0 else img.get_width() - mw, (img.get_height() - mh) // 2, mw, mh)
                out.blit(img, rect, src)
                pygame.draw.rect(out, (16, 16, 18), rect.inflate(6, 6), 4, border_radius=10)
                pygame.draw.line(out, (70, 70, 76), (housing.x + 10, housing.y + 2), (housing.right - 10, housing.y + 2))
                stalk = (rect.right + 8, rect.centery + 10) if k == 0 else (rect.x - 8, rect.centery + 10)
                end = (stalk[0] + (60 if k == 0 else -60), h - 40)
                pygame.draw.line(out, (18, 18, 20), stalk, end, 9)
        # steering wheel, turned with the front wheels
        glove = getattr(car.profile, "helmet", (200, 200, 200))
        base = self._wheel_base(glove)
        wheel = base.copy()
        self._wheel_display(wheel, car)
        angle = -getattr(car, "steer_angle", 0.0) * 42.0
        rot = pygame.transform.rotate(wheel, angle)
        out.blit(rot, rot.get_rect(center=(w // 2, h - 40)))

    def _draw_halo(self, out: pygame.Surface, car: "Car") -> None:
        """The halo seen from the driver's seat: a dark hoop along the top edge and the central strut, anchored
        on the real mounting point on the chassis (so it moves with the camera shake)."""
        w, h = out.get_size()
        s = self.ss
        hd = car.heading
        mx, my = car.pos.x + math.cos(hd) * 5.0, car.pos.y + math.sin(hd) * 5.0
        pb, pt = self.to_cam(mx, my, 4.9), self.to_cam(mx, my, 8.0)
        if pb[2] <= self.near or pt[2] <= self.near:
            return
        bx, by = (c / s for c in self.project(pb))
        tx, ty = (c / s for c in self.project(pt))
        ty = min(ty, 40.0)
        dark, edge = (18, 18, 21), (64, 64, 72)
        top = [(-10, -10), (w + 10, -10), (w + 10, 14), (w * 0.8, ty - 16), (tx + 70, ty), (tx - 70, ty),
               (w * 0.2, ty - 16), (-10, 14)]
        pygame.draw.polygon(out, dark, top)
        pygame.draw.aalines(out, edge, False, top[2:8])
        half_b = max(5.0, self._focal / s * 0.24 / pb[2])
        strut = [(tx - half_b * 1.7, ty - 2), (tx + half_b * 1.7, ty - 2), (bx + half_b, by), (bx - half_b, by)]
        pygame.draw.polygon(out, dark, strut)
        pygame.draw.aaline(out, edge, strut[0], strut[3])
        pygame.draw.aaline(out, (40, 40, 46), strut[1], strut[2])
        pygame.draw.ellipse(out, dark, (bx - half_b * 1.8, by - half_b * 0.6, half_b * 3.6, half_b * 1.2))

    def _wheel_base(self, glove: Color) -> pygame.Surface:
        img = self._wheel_cache.get(glove)
        if img is not None:
            return img
        img = pygame.Surface((560, 380), pygame.SRCALPHA)
        cx, cy = 280, 190
        carbon, rubber = (24, 24, 28), (36, 36, 40)
        # grips
        for side in (-1, 1):
            gx = cx + side * 190
            pygame.draw.rect(img, rubber, (gx - 38, cy - 132, 76, 176), border_radius=30)
            pygame.draw.rect(img, (52, 52, 58), (gx - 38, cy - 132, 76, 176), 3, border_radius=30)
        # body
        body = [(cx - 168, cy - 110), (cx + 168, cy - 110), (cx + 176, cy - 40), (cx + 140, cy + 40),
                (cx + 70, cy + 70), (cx - 70, cy + 70), (cx - 140, cy + 40), (cx - 176, cy - 40)]
        pygame.draw.polygon(img, carbon, body)
        pygame.draw.polygon(img, (60, 60, 66), body, 3)
        # display frame
        pygame.draw.rect(img, (8, 8, 10), (cx - 82, cy - 98, 164, 104), border_radius=8)
        # buttons and rotaries
        for k, col in enumerate(((220, 40, 40), (40, 180, 70), (250, 200, 30), (40, 110, 230))):
            for side in (-1, 1):
                bx = cx + side * (108 + (k % 2) * 26)
                by = cy - 80 + (k // 2) * 36
                pygame.draw.circle(img, (10, 10, 12), (bx, by), 12)
                pygame.draw.circle(img, col, (bx, by), 9)
                pygame.draw.circle(img, _shade(col, 1.4), (bx - 3, by - 3), 3)
        for side in (-1, 1):
            for k in range(2):
                rx_, ry_ = cx + side * (60 + k * 44), cy + 36
                pygame.draw.circle(img, (60, 62, 68), (rx_, ry_), 14)
                pygame.draw.circle(img, (120, 122, 130), (rx_, ry_), 14, 2)
                pygame.draw.line(img, (220, 220, 220), (rx_, ry_), (rx_, ry_ - 11), 2)
        # gloves on the grips
        for side in (-1, 1):
            gx = cx + side * 190
            glove_rect = pygame.Rect(gx - 46, cy - 118, 92, 96)
            pygame.draw.rect(img, _shade(glove, 0.65), glove_rect.move(0, 4), border_radius=34)
            pygame.draw.rect(img, glove, glove_rect, border_radius=34)
            for k in range(3):
                fy_ = glove_rect.y + 24 + k * 20
                pygame.draw.line(img, _shade(glove, 0.6), (glove_rect.x + 12, fy_), (glove_rect.right - 12, fy_), 3)
            pygame.draw.rect(img, (240, 240, 240), (glove_rect.x + 10, glove_rect.bottom - 18, glove_rect.w - 20, 8),
                             border_radius=3)
        self._wheel_cache[glove] = img
        return img

    def _wheel_display(self, img: pygame.Surface, car: "Car") -> None:
        cx, cy = 280, 190
        rpm = getattr(car, "rpm_fraction", 0.0) if hasattr(car, "rpm_fraction") else 0.0
        # shift lights along the top of the wheel
        for i in range(15):
            lit = rpm >= (i + 1) / 15 * 0.98
            col = (40, 230, 80) if i < 5 else (240, 40, 40) if i < 10 else (90, 130, 255)
            if rpm > 0.97 and int(self.time * 12) % 2:
                col = (90, 130, 255)
            pygame.draw.circle(img, col if lit else _shade(col, 0.18), (cx - 140 + i * 20, cy - 122), 6)
        screen = pygame.Rect(cx - 76, cy - 92, 152, 92)
        pygame.draw.rect(img, (4, 10, 14), screen, border_radius=6)
        gear = getattr(car, "gear", "N") if hasattr(car, "gear") else "-"
        g = self._font("mono", 46).render(str(gear), True, (255, 220, 60))
        img.blit(g, g.get_rect(center=(cx, cy - 52)))
        kmh = int(getattr(car, "speed_kmh", 0.0)) if hasattr(car, "speed_kmh") else 0
        sp = self._font("mono", 18).render(f"{kmh:3d}", True, (230, 240, 250))
        img.blit(sp, sp.get_rect(topleft=(screen.x + 8, screen.y + 6)))
        tyres = getattr(car, "tyres", None)
        if tyres is not None:
            t = self._font("sans", 13).render(f"{tyres.compound.letter} {int((1 - tyres.wear) * 100)}%", True,
                                              tyres.compound.color)
            img.blit(t, t.get_rect(topright=(screen.right - 8, screen.y + 8)))
        delta = car.live_delta() if hasattr(car, "live_delta") else None
        if delta is not None:
            dc = (60, 230, 110) if delta < 0 else (255, 90, 90)
            dt_img = self._font("mono", 16).render(f"{delta:+.2f}", True, dc)
            img.blit(dt_img, dt_img.get_rect(midbottom=(cx, screen.bottom - 4)))
        if getattr(car, "straight_mode", False):
            pygame.draw.rect(img, (70, 170, 255), (screen.x + 6, screen.bottom - 20, 34, 14), border_radius=3)
            lbl = self._font("sans", 11).render("DRS", True, (5, 20, 40))
            img.blit(lbl, lbl.get_rect(center=(screen.x + 23, screen.bottom - 13)))
        fuel = getattr(car, "fuel_laps", None)
        if fuel is not None:
            fl = self._font("sans", 11).render(f"F {fuel:.1f}", True, (180, 190, 200))
            img.blit(fl, fl.get_rect(bottomright=(screen.right - 6, screen.bottom - 5)))
