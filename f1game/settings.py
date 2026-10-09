# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

SCREEN_WIDTH: int = 1280
SCREEN_HEIGHT: int = 720
FPS: int = 60
PHYSICS_STEP: float = 1.0 / 120.0
MAX_FRAME_DT: float = 1.0 / 20.0
WINDOW_TITLE: str = "F1 Grand Prix Weekend - KI mit Persönlichkeit"

PX_PER_S_TO_KMH: float = 0.61

CAR_LENGTH: float = 34.0
CAR_WIDTH: float = 16.0
WHEELBASE: float = 24.0
CAR_MASS: float = 1.0
CAR_INERTIA: float = CAR_MASS * (CAR_LENGTH ** 2 + CAR_WIDTH ** 2) / 12.0

TOP_SPEED: float = 540.0
ENGINE_ACCEL: float = 350.0
ENGINE_FADE: float = 0.35
DRAG_SHARE: float = 1.0 - ENGINE_FADE
BRAKE_DECEL: float = 800.0
REVERSE_ACCEL: float = 160.0
REVERSE_MAX_SPEED: float = 90.0
ROLLING_FRICTION: float = 45.0
LATERAL_GRIP: float = 620.0
MAX_STEER_ANGLE: float = 0.60
STEER_RATE: float = 8.0
SLIP_RECOVERY: float = 2.2
SPIN_DAMPING: float = 3.0

SLIPSTREAM_DRAG: float = 0.11
SLIPSTREAM_RANGE: float = 240.0
STRAIGHT_MODE_DRAG: float = 0.12
STRAIGHT_MODE_GRIP: float = 0.82

GRASS_GRIP_FACTOR: float = 0.60
GRASS_ENGINE_FACTOR: float = 0.45
GRASS_DRAG: float = 1.1

RESTITUTION_CAR: float = 0.25
RESTITUTION_WALL: float = 0.12
CAR_FRICTION_COEFF: float = 0.25
SPIN_TRANSFER: float = 0.55

GEAR_THRESHOLDS: tuple[float, ...] = (85.0, 153.0, 220.0, 288.0, 355.0, 423.0, 486.0)

DIFFICULTY_LEVELS: dict[str, float] = {"Leicht": 0.86, "Mittel": 0.94, "Schwer": 1.0}
AI_CONTROL_INTERVAL: float = 1.0 / 30.0

Color = tuple[int, int, int]

WHITE: Color = (245, 245, 245)
BLACK: Color = (10, 10, 12)
GREY: Color = (130, 135, 145)
DARK_GREY: Color = (40, 42, 48)
PANEL: Color = (18, 20, 26)
PANEL_LIGHT: Color = (34, 37, 46)
F1_RED: Color = (225, 6, 0)
YELLOW: Color = (255, 210, 40)
GREEN: Color = (40, 210, 90)
PURPLE: Color = (175, 80, 255)
CYAN: Color = (0, 220, 255)
ORANGE: Color = (255, 140, 30)

PLAYER_COLOR: Color = (0, 215, 255)
