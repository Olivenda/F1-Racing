/* Copyright Olivenda (Oliver Petz) 2026
 *
 * Training simulation shared by the CPU (C, double precision) and the GPU (OpenCL C, float) trainer.
 * A 1:1 port of what f1game/training.py runs: car.py physics (no tyres/damage/fuel, as in training),
 * physics.py collisions, sensors.py inputs, the neural driver and ai_car.py racecraft, Evaluation.step
 * and Evaluation.fitness. Keep it in sync with the Python code - the brains it trains drive in the game.
 */
#ifndef F1_SIM_H
#define F1_SIM_H

#ifdef __OPENCL_VERSION__
typedef float real;
#define G __global
#define FN static inline
#else
#include <math.h>
typedef double real;
#define G
#define FN static inline
#endif

/* network shape (training.py NETWORK_SIZES) */
#define N_IN 16
#define H1 12
#define H2 8
#define N_OUT 2
#define N_PARAMS (H1 * N_IN + H1 + H2 * H1 + H2 + N_OUT * H2 + N_OUT)
#define MAX_HEAT 11
#define N_SETUP 11

/* settings.py */
#define PI_R 3.14159265358979323846
#define TAU_R 6.28318530717958647692
#define PHYSICS_STEP (1.0 / 120.0)
#define CAR_LENGTH 34.0
#define CAR_WIDTH 16.0
#define WHEELBASE 24.0
#define CAR_MASS 1.0
#define CAR_INERTIA (CAR_MASS * (CAR_LENGTH * CAR_LENGTH + CAR_WIDTH * CAR_WIDTH) / 12.0)
#define TOP_SPEED 500.0
#define ENGINE_ACCEL 100.0
#define ENGINE_FADE 0.30
#define DRAG_SHARE (1.0 - ENGINE_FADE)
#define BRAKE_DECEL 250.0
#define BRAKE_LOW_SPEED 0.48
#define BRAKE_HIGH_SPEED 0.86
#define REVERSE_ACCEL 160.0
#define REVERSE_MAX_SPEED 90.0
#define ROLLING_FRICTION 22.0
#define COAST_DRAG 0.6
#define LATERAL_GRIP 620.0
#define MAX_STEER_ANGLE 0.50
#define STEER_RATE 7.0
#define SLIP_RECOVERY 2.2
#define SPIN_DAMPING 3.0
#define STRAIGHT_MODE_DRAG 0.12
#define STRAIGHT_MODE_GRIP 0.82
#define STRAIGHT_STEER_LIMIT 0.45
#define GRASS_GRIP_FACTOR 0.60
#define GRASS_ENGINE_FACTOR 0.45
#define GRASS_DRAG 1.1
#define RESTITUTION_CAR 0.25
#define RESTITUTION_WALL 0.12
#define CAR_FRICTION_COEFF 0.25
#define SPIN_TRANSFER 0.55
#define AI_CONTROL_INTERVAL (1.0 / 30.0)
#define IMPACT_THRESHOLD 230.0
#define WAYPOINT_SPACING 12.0
/* sensors.py */
#define RADAR_RANGE 280.0
#define RADAR_FRONT_CENTER 11
/* stewards.py */
#define TL_MARGIN CAR_WIDTH
#define TL_MIN_TIME 0.45
/* training.py */
#define CRASH_PENALTY 400.0
#define TRACK_LIMIT_PENALTY 250.0
#define OFFTRACK_PENALTY 150.0
#define CHECK_INTERVAL 1.5
#define MIN_PROGRESS 60.0
/* ai_car.py racecraft */
#define LOOK_TIME 0.8
#define TTC_AI 0.55
#define ROOM_AI 6.0

/* ---------------------------------------------------------------- data shared with the host (4-byte fields) */
typedef struct {
    int n, off;                 /* waypoint count, offset into the concatenated track arrays */
    float length, half_width, wall_limit;
    float sf[N_SETUP];          /* setup factors, order of ctrain.py SETUP_FIELDS */
} TrackInfo;

typedef struct {
    int track, traffic, stop_after_lap, n;
    int genome[MAX_HEAT];
    float start_s, duration;
} Job;

typedef struct {
    float w_wall, w_car, w_gain, w_tailgate;
} Style;

enum { SF_GRIP, SF_DRAG, SF_ENGINE, SF_REV, SF_BRAKE, SF_STEER_RATE, SF_TURN, SF_SLIP, SF_BRAKE_SLIP, SF_BRAKE_TURN,
       SF_GRASS_GRIP };

/* ---------------------------------------------------------------- simulation state */
typedef struct {
    G const real *cx, *cy, *tx, *ty, *nx, *ny, *cum, *lo;
    G const int *aero;
    int n;
    real length, hw, wl;
    real sf[N_SETUP];
} Track;

typedef struct {
    real px, py, vx, vy, heading, spin, steer_angle, speed_fwd;
    real throttle, brake, steer_input;
    real s, lateral, distance;
    real lap_start_time, best_lap;
    real wall_impulse, car_impulse, grass_time;
    real timer, out_steer, out_pedal, radar_c;
    real rc_timer, rc_lift, rc_brake, rc_steer, rc_side;
    real start_distance, check_distance, tailgate, tl_off;
    int idx, lap_floor, on_grass, timing_started, laps_done;
    int frozen, retired, straight_mode, collide, sees_others, has_inputs;
    int crashes, alive, tl_violations, start_rank, genome;
} Car;

typedef struct {
    real time, check_timer, duration;
    int n, traffic, stop_after_lap, finished, track;
    Car cars[MAX_HEAT];
} Eval;

/* ---------------------------------------------------------------- helpers (utils.py) */
FN real clampr(real v, real lo, real hi) { return v < lo ? lo : (v > hi ? hi : v); }
FN real approach(real cur, real target, real d) { return cur < target ? fmin(cur + d, target) : fmax(cur - d, target); }
FN real pymod(real a, real m) { return a - m * floor(a / m); }
FN real wrap_angle(real a) { return pymod(a + (real)PI_R, (real)TAU_R) - (real)PI_R; }
FN int imod(int a, int m) { int r = a % m; return r < 0 ? r + m : r; }

/* ---------------------------------------------------------------- track.py */
FN int nearest_index(const Track *t, real px, real py, int hint, int back, int fwd) {
    int best_i = 0;
    real best_d = (real)1e18;
    if (hint >= 0) {
        best_i = hint;
        for (int k = -back; k <= fwd; k++) {
            int i = imod(hint + k, t->n);
            real dx = t->cx[i] - px, dy = t->cy[i] - py, d = dx * dx + dy * dy;
            if (d < best_d) { best_i = i; best_d = d; }
        }
        real limit = t->wl + 80;
        if (best_d < limit * limit) return best_i;
        best_i = 0;
        best_d = (real)1e18;
    }
    for (int i = 0; i < t->n; i++) {
        real dx = t->cx[i] - px, dy = t->cy[i] - py, d = dx * dx + dy * dy;
        if (d < best_d) { best_i = i; best_d = d; }
    }
    return best_i;
}

FN void project(const Track *t, real px, real py, int hint, int back, int fwd, int *idx, real *s, real *lat) {
    int i = nearest_index(t, px, py, hint, back, fwd);
    real rx = px - t->cx[i], ry = py - t->cy[i];
    *idx = i;
    *s = pymod(t->cum[i] + rx * t->tx[i] + ry * t->ty[i], t->length);
    *lat = rx * t->nx[i] + ry * t->ny[i];
}

FN void pose_at(const Track *t, real s, real lat, real *x, real *y, real *h) {
    s = pymod(s, t->length);
    int lo = 0, hi = t->n;              /* bisect_right(cum, s) - 1 */
    while (lo < hi) {
        int mid = (lo + hi) / 2;
        if (s < t->cum[mid]) hi = mid; else lo = mid + 1;
    }
    int i = lo - 1 < 0 ? 0 : lo - 1;
    real d = s - t->cum[i];
    *x = t->cx[i] + t->tx[i] * d + t->nx[i] * lat;
    *y = t->cy[i] + t->ty[i] * d + t->ny[i] * lat;
    *h = atan2(t->ty[i], t->tx[i]);
}

FN void grid_pose(const Track *t, int slot, real *x, real *y, real *h) {
    int row = slot / 2, col = slot % 2;
    real back = (real)30.0 + row * (real)62.0 + col * (real)31.0;
    real lat = (col == 0 ? -1 : 1) * t->hw * (real)0.42;
    pose_at(t, -back, lat, x, y, h);
}

/* ---------------------------------------------------------------- car.py */
FN void car_place(const Track *t, Car *c, real x, real y, real h) {
    c->px = x; c->py = y; c->heading = h;
    c->vx = c->vy = c->spin = c->steer_angle = c->speed_fwd = 0;
    project(t, x, y, -1, 0, 0, &c->idx, &c->s, &c->lateral);
    real L = t->length;
    c->distance = c->s > L / 2 ? c->s - L : c->s;
    c->lap_floor = (int)floor(c->distance / L);
}

FN void corners(const Car *c, real *xs, real *ys) {
    real fx = cos(c->heading) * (real)(CAR_LENGTH / 2), fy = sin(c->heading) * (real)(CAR_LENGTH / 2);
    real rx = -sin(c->heading) * (real)(CAR_WIDTH / 2), ry = cos(c->heading) * (real)(CAR_WIDTH / 2);
    xs[0] = c->px + fx + rx; ys[0] = c->py + fy + ry;
    xs[1] = c->px + fx - rx; ys[1] = c->py + fy - ry;
    xs[2] = c->px - fx - rx; ys[2] = c->py - fy - ry;
    xs[3] = c->px - fx + rx; ys[3] = c->py - fy + ry;
}

FN void notify_collision(Car *c, real impulse, int is_car) {
    if (impulse > (real)IMPACT_THRESHOLD) c->crashes++;
    if (is_car) c->car_impulse += impulse; else c->wall_impulse += impulse;
}

FN void physics_step(const Track *t, Car *c, real dt) {
    if (c->frozen) { c->vx = c->vy = c->spin = c->speed_fwd = 0; return; }
    const real *sf = t->sf;
    real fx = cos(c->heading), fy = sin(c->heading), rx = -fy, ry = fx;
    real vf = c->vx * fx + c->vy * fy, vl = c->vx * rx + c->vy * ry;
    real top = (real)TOP_SPEED;
    real grip = (real)LATERAL_GRIP * sf[SF_GRIP] * (c->on_grass ? (real)GRASS_GRIP_FACTOR * sf[SF_GRASS_GRIP] : 1) *
                (c->straight_mode ? (real)STRAIGHT_MODE_GRIP : 1);
    real engine = (real)ENGINE_ACCEL * sf[SF_ENGINE] * (c->on_grass ? (real)GRASS_ENGINE_FACTOR : 1);
    real r = fmin((real)1, fmax((real)0, vf) / (real)TOP_SPEED);
    real brake_force = (real)BRAKE_DECEL * ((real)BRAKE_LOW_SPEED + (real)(BRAKE_HIGH_SPEED - BRAKE_LOW_SPEED) * r * r) *
                       sf[SF_BRAKE];
    if (c->on_grass) c->grass_time += dt;

    real steer_target = clampr(c->steer_input, -1, 1);
    c->steer_angle = approach(c->steer_angle, steer_target, (real)STEER_RATE * sf[SF_STEER_RATE] * dt);

    real acc = 0;
    if (c->throttle > 0) {
        if (vf >= (real)-5.0)
            acc += engine * c->throttle * (1 - (real)ENGINE_FADE * clampr(vf / top, 0, 1));
        else
            acc += (real)(BRAKE_DECEL * 0.6) * c->throttle;
    }
    real ratio = vf / top;
    real drag_factor = sf[SF_DRAG] * (c->straight_mode ? (real)(1.0 - STRAIGHT_MODE_DRAG) : 1);
    if (c->throttle <= 0 && c->brake <= 0) drag_factor *= (real)COAST_DRAG;
    acc -= (real)(ENGINE_ACCEL * DRAG_SHARE) * ratio * fabs(ratio) * drag_factor;
    int braking_forward = 0;
    if (c->brake > 0) {
        if (vf > 8) {
            acc -= brake_force * c->brake * (c->on_grass ? (real)0.6 : 1);
            braking_forward = 1;
        } else if (vf > (real)-REVERSE_MAX_SPEED) {
            acc -= (real)REVERSE_ACCEL * c->brake;
        }
    }
    if (c->throttle <= 0 && c->brake <= 0 && fabs(vf) > (real)0.5)
        acc -= vf > 0 ? (real)ROLLING_FRICTION : (real)-ROLLING_FRICTION;
    if (c->on_grass) acc -= (real)GRASS_DRAG * vf;
    real new_vf = vf + acc * dt;
    if (vf > 0 && new_vf < 0 && (braking_forward || c->brake <= 0)) new_vf = 0;
    if (vf < 0 && new_vf > 0 && c->throttle <= 0) new_vf = 0;
    real rev_cap = top * sf[SF_REV];
    if (new_vf > rev_cap) new_vf = vf > rev_cap ? fmax(rev_cap, vf - 400 * dt) : rev_cap;

    real speed = fmax(fabs(new_vf), (real)1);
    real turn = sf[SF_TURN] * (braking_forward ? sf[SF_BRAKE_TURN] : 1);
    real k_geom = (real)(0.54630248984379051 / WHEELBASE);     /* tan(MAX_STEER_ANGLE) / WHEELBASE */
    real k_grip = grip * turn / (speed * speed);
    real k_max = fmin(k_geom, k_grip);
    real yaw_rate = new_vf * c->steer_angle * k_max;
    c->heading = wrap_angle(c->heading + (yaw_rate + c->spin) * dt);
    c->spin *= exp((real)-SPIN_DAMPING * dt);

    real wvx = fx * new_vf + rx * vl, wvy = fy * new_vf + ry * vl;
    real fx2 = cos(c->heading), fy2 = sin(c->heading), rx2 = -fy2, ry2 = fx2;
    real vf2 = wvx * fx2 + wvy * fy2;
    real slip_hold = sf[SF_SLIP] * (braking_forward ? sf[SF_BRAKE_SLIP] : 1);
    real vl2 = approach(wvx * rx2 + wvy * ry2, 0, grip * (real)SLIP_RECOVERY * slip_hold * dt);
    c->vx = fx2 * vf2 + rx2 * vl2;
    c->vy = fy2 * vf2 + ry2 * vl2;
    c->speed_fwd = vf2;
    c->px += c->vx * dt;
    c->py += c->vy * dt;
}

FN void update_aero(const Track *t, Car *c) {
    int zone = t->aero[c->idx];
    if (c->straight_mode) {
        if (zone < 0 || c->brake > (real)0.1 || fabs(c->steer_input) > (real)STRAIGHT_STEER_LIMIT || c->on_grass ||
            c->frozen)
            c->straight_mode = 0;
        return;
    }
    if (zone < 0 || c->frozen || c->on_grass || c->brake > 0 || c->speed_fwd < 150) return;
    if (c->throttle > (real)0.9 && fabs(c->steer_input) < (real)0.25) c->straight_mode = 1;
}

/* ---------------------------------------------------------------- physics.py collisions */
FN int inside_obb(real px, real py, const Car *c) {
    real dx = px - c->px, dy = py - c->py;
    real fx = cos(c->heading), fy = sin(c->heading);
    return fabs(dx * fx + dy * fy) <= (real)(CAR_LENGTH / 2 + 0.5) && fabs(-dx * fy + dy * fx) <= (real)(CAR_WIDTH / 2 + 0.5);
}

FN int sat_test(const Car *a, const Car *b, real *nx, real *ny, real *depth) {
    real ax[4], ay[4], bx[4], by[4];
    corners(a, ax, ay);
    corners(b, bx, by);
    real axes[8] = {cos(a->heading), sin(a->heading), -sin(a->heading), cos(a->heading),
                    cos(b->heading), sin(b->heading), -sin(b->heading), cos(b->heading)};
    real best = (real)1e9, bnx = 0, bny = 0;
    for (int k = 0; k < 4; k++) {
        real ux = axes[2 * k], uy = axes[2 * k + 1];
        real mina = (real)1e18, maxa = (real)-1e18, minb = (real)1e18, maxb = (real)-1e18;
        for (int i = 0; i < 4; i++) {
            real va = ax[i] * ux + ay[i] * uy, vb = bx[i] * ux + by[i] * uy;
            mina = fmin(mina, va); maxa = fmax(maxa, va);
            minb = fmin(minb, vb); maxb = fmax(maxb, vb);
        }
        real overlap = fmin(maxa, maxb) - fmax(mina, minb);
        if (overlap <= 0) return 0;
        if (overlap < best) { best = overlap; bnx = ux; bny = uy; }
    }
    if ((b->px - a->px) * bnx + (b->py - a->py) * bny < 0) { bnx = -bnx; bny = -bny; }
    *nx = bnx; *ny = bny; *depth = best;
    return 1;
}

FN void resolve_car_collision(Car *a, Car *b, real nx, real ny, real depth) {
    if (a->frozen && b->frozen) return;
    real push = depth + (real)0.05;
    if (a->frozen) { b->px += nx * push; b->py += ny * push; }
    else if (b->frozen) { a->px -= nx * push; a->py -= ny * push; }
    else {
        a->px -= nx * push * (real)0.5; a->py -= ny * push * (real)0.5;
        b->px += nx * push * (real)0.5; b->py += ny * push * (real)0.5;
    }
    real ax[4], ay[4], bx[4], by[4], sx = 0, sy = 0;
    int cnt = 0;
    corners(a, ax, ay);
    corners(b, bx, by);
    for (int i = 0; i < 4; i++) {
        if (inside_obb(ax[i], ay[i], b)) { sx += ax[i]; sy += ay[i]; cnt++; }
    }
    for (int i = 0; i < 4; i++) {
        if (inside_obb(bx[i], by[i], a)) { sx += bx[i]; sy += by[i]; cnt++; }
    }
    real cx = cnt ? sx / cnt : (a->px + b->px) * (real)0.5, cy = cnt ? sy / cnt : (a->py + b->py) * (real)0.5;
    real rax = cx - a->px, ray = cy - a->py, rbx = cx - b->px, rby = cy - b->py;
    real vrx = (b->vx - b->spin * rby) - (a->vx - a->spin * ray);
    real vry = (b->vy + b->spin * rbx) - (a->vy + a->spin * rax);
    real vn = vrx * nx + vry * ny;
    if (vn >= 0) return;
    real inv_ma = a->frozen ? 0 : (real)(1.0 / CAR_MASS), inv_mb = b->frozen ? 0 : (real)(1.0 / CAR_MASS);
    real inv_ia = a->frozen ? 0 : (real)(1.0 / CAR_INERTIA), inv_ib = b->frozen ? 0 : (real)(1.0 / CAR_INERTIA);
    real ra_n = rax * ny - ray * nx, rb_n = rbx * ny - rby * nx;
    real denom = inv_ma + inv_mb + ra_n * ra_n * inv_ia + rb_n * rb_n * inv_ib;
    real j = -(1 + (real)RESTITUTION_CAR) * vn / denom;
    a->vx -= nx * j * inv_ma; a->vy -= ny * j * inv_ma;
    b->vx += nx * j * inv_mb; b->vy += ny * j * inv_mb;
    a->spin -= ra_n * j * inv_ia * (real)SPIN_TRANSFER;
    b->spin += rb_n * j * inv_ib * (real)SPIN_TRANSFER;
    real tx = -ny, ty = nx;
    real vt = vrx * tx + vry * ty;
    real jt = clampr(-vt / (inv_ma + inv_mb + (real)1e-9), (real)-CAR_FRICTION_COEFF * j, (real)CAR_FRICTION_COEFF * j);
    a->vx -= tx * jt * inv_ma; a->vy -= ty * jt * inv_ma;
    b->vx += tx * jt * inv_mb; b->vy += ty * jt * inv_mb;
    notify_collision(a, j, 1);
    notify_collision(b, j, 1);
}

FN void resolve_wall_collision(const Track *t, Car *c) {
    if (c->retired) return;
    real xs[4], ys[4];
    corners(c, xs, ys);
    real best_pen = 0, wnx = 0, wny = 0, cxp = 0, cyp = 0;
    int found = 0;
    for (int k = 0; k < 4; k++) {
        int i = nearest_index(t, xs[k], ys[k], c->idx, 6, 6);
        real d = (xs[k] - t->cx[i]) * t->nx[i] + (ys[k] - t->cy[i]) * t->ny[i];
        real pen = fabs(d) - t->wl;
        if (pen > 0 && (!found || pen > best_pen)) {
            real sgn = d > 0 ? -1 : 1;
            best_pen = pen; wnx = t->nx[i] * sgn; wny = t->ny[i] * sgn; cxp = xs[k]; cyp = ys[k];
            found = 1;
        }
    }
    if (!found) return;
    c->px += wnx * (best_pen + (real)0.1);
    c->py += wny * (best_pen + (real)0.1);
    real rx = cxp - c->px, ry = cyp - c->py;
    real vcx = c->vx - c->spin * ry, vcy = c->vy + c->spin * rx;
    real vn = vcx * wnx + vcy * wny;
    if (vn >= 0) return;
    real r_n = rx * wny - ry * wnx;
    real j = -(1 + (real)RESTITUTION_WALL) * vn / ((real)(1.0 / CAR_MASS) + r_n * r_n / (real)CAR_INERTIA);
    c->vx += wnx * j / (real)CAR_MASS;
    c->vy += wny * j / (real)CAR_MASS;
    c->spin += r_n * j / (real)CAR_INERTIA * (real)(SPIN_TRANSFER * 0.4);
    real tx = -wny, ty = wnx;
    real vt = c->vx * tx + c->vy * ty;
    real k = fmin((real)0.25, j / (real)1300.0);
    c->vx -= tx * vt * k;
    c->vy -= ty * vt * k;
    notify_collision(c, j, 0);
}

/* ---------------------------------------------------------------- sensors.py + neural.py */
FN void compute_inputs(const Track *t, const Eval *e, const Car *c, real *in) {
    real fx = cos(c->heading), fy = sin(c->heading), rx = -fy, ry = fx;
    int i0 = c->idx;
    in[0] = c->speed_fwd / (real)TOP_SPEED;
    in[1] = clampr((c->vx * rx + c->vy * ry) / 200, -2, 2);
    in[2] = clampr(c->lateral / t->hw, -2, 2);
    in[3] = wrap_angle(c->heading - atan2(t->ty[i0], t->tx[i0])) / (real)(PI_R / 2);
    const int ahead[6] = {4, 9, 15, 24, 35, 48};        /* int(LOOKAHEAD / WAYPOINT_SPACING) */
    for (int k = 0; k < 6; k++) {
        int j = (i0 + ahead[k]) % t->n;
        real dx = t->cx[j] - c->px, dy = t->cy[j] - c->py;
        in[4 + k] = atan2(dx * rx + dy * ry, dx * fx + dy * fy) / (real)PI_R;
    }
    real front_l = 0, front_c = 0, front_r = 0, side_l = 0, side_r = 0, closing = 0;
    if (c->sees_others && !c->retired) {
        real L = t->length;
        for (int k = 0; k < e->n; k++) {
            const Car *o = &e->cars[k];
            if (o == c || o->retired) continue;
            real ds = o->s - c->s;
            if (ds > L / 2) ds -= L;
            else if (ds < -L / 2) ds += L;
            real dl = o->lateral - c->lateral;
            if (fabs(dl) > (real)(CAR_WIDTH * 3.0)) continue;
            if (fabs(ds) < (real)(CAR_LENGTH * 1.2)) {
                real prox = clampr(1 - (fabs(dl) - (real)CAR_WIDTH) / (real)(CAR_WIDTH * 2.0), 0, 1);
                if (dl < 0) side_l = fmax(side_l, prox); else side_r = fmax(side_r, prox);
            } else if (ds > 0 && ds < (real)RADAR_RANGE) {
                real prox = 1 - ds / (real)RADAR_RANGE;
                if (dl < (real)(-CAR_WIDTH * 0.8)) front_l = fmax(front_l, prox);
                else if (dl > (real)(CAR_WIDTH * 0.8)) front_r = fmax(front_r, prox);
                else if (prox > front_c) {
                    front_c = prox;
                    closing = clampr((c->speed_fwd - o->speed_fwd) / 200, -1, 1);
                }
            }
        }
    }
    in[10] = front_l; in[11] = front_c; in[12] = front_r; in[13] = side_l; in[14] = side_r; in[15] = closing;
}

FN void nn_forward(G const real *w, const real *in, real *out) {
    real a1[H1], a2[H2];
    G const real *W1 = w, *B1 = W1 + H1 * N_IN, *W2 = B1 + H1, *B2 = W2 + H2 * H1, *W3 = B2 + H2, *B3 = W3 + N_OUT * H2;
    for (int j = 0; j < H1; j++) {
        real s = B1[j];
        for (int i = 0; i < N_IN; i++) s += W1[j * N_IN + i] * in[i];
        a1[j] = tanh(s);
    }
    for (int j = 0; j < H2; j++) {
        real s = B2[j];
        for (int i = 0; i < H1; i++) s += W2[j * H1 + i] * a1[i];
        a2[j] = tanh(s);
    }
    for (int j = 0; j < N_OUT; j++) {
        real s = B3[j];
        for (int i = 0; i < H2; i++) s += W3[j * H2 + i] * a2[i];
        out[j] = tanh(s);
    }
}

/* ---------------------------------------------------------------- ai_car.py */
FN void racecraft_assess(const Track *t, const Eval *e, const Car *c, real *lift, real *brake, real *steer,
                         real *side) {
    real L = t->length;
    real v = fmax((real)0, c->speed_fwd);
    real look = (real)CAR_LENGTH + v * (real)LOOK_TIME;
    *lift = *brake = *steer = *side = 0;
    for (int k = 0; k < e->n; k++) {
        const Car *o = &e->cars[k];
        if (o == c || o->retired || !o->collide) continue;
        real ds = pymod(o->s - c->s + L / 2, L) - L / 2;
        if (ds < (real)(-CAR_LENGTH * 1.5) || ds > look) continue;
        real dlat = o->lateral - c->lateral;
        real room = (real)(CAR_WIDTH + ROOM_AI);
        real away = dlat > 0 ? -1 : 1;
        if (ds > (real)(CAR_LENGTH * 0.6)) {
            if (fabs(dlat) >= room) continue;
            real gap = ds - (real)CAR_LENGTH;
            real closing = v - fmax((real)0, o->speed_fwd);
            real limit = (real)TTC_AI;
            if (gap < 5) {
                *lift = 1;
                *brake = fmax(*brake, (real)0.6);
            } else if (closing > 0 && gap / closing < limit) {
                real need = 1 - (gap / closing) / limit;
                *lift = fmax(*lift, fmin((real)1, (real)0.4 + need));
                real required = closing * closing / (2 * fmax((real)1, gap - 8));
                *brake = fmax(*brake, fmin((real)1, required / (real)(BRAKE_DECEL * 0.55)));
                if (o->brake > (real)0.2 && gap < closing * limit + 25) *brake = fmax(*brake, fmin((real)1, o->brake));
            }
            real pull = closing > 30 ? (real)0.32 : (real)0.15;
            *steer += pull * away * (1 - fabs(dlat) / room);
        } else if (fabs(dlat) < room + 8) {
            real squeeze = 1 - fabs(dlat) / (room + 8);
            *steer += (real)0.3 * away * squeeze;
            *side = dlat > 0 ? 1 : -1;
        }
    }
    *steer = clampr(*steer, (real)-0.6, (real)0.6);
}

FN void control(const Track *t, const Eval *e, Car *c, G const real *nets, real dt) {
    c->timer -= dt;
    if (c->timer <= 0) {
        c->timer += (real)AI_CONTROL_INTERVAL;
        real in[N_IN], out[N_OUT];
        compute_inputs(t, e, c, in);
        nn_forward(nets + (long)c->genome * N_PARAMS, in, out);
        c->out_steer = out[0];
        c->out_pedal = out[1];
        c->radar_c = in[RADAR_FRONT_CENTER];
        c->has_inputs = 1;
    }
    c->throttle = fmax((real)0, c->out_pedal);
    c->brake = fmax((real)0, -c->out_pedal);
    c->steer_input = c->out_steer;
    if (c->sees_others && c->collide) {
        c->rc_timer -= dt;
        if (c->rc_timer <= 0) {
            c->rc_timer = (real)AI_CONTROL_INTERVAL;
            racecraft_assess(t, e, c, &c->rc_lift, &c->rc_brake, &c->rc_steer, &c->rc_side);
        }
        if (c->rc_lift > 0) c->throttle = fmin(c->throttle, fmax((real)0, 1 - c->rc_lift));
        if (c->rc_brake > 0) c->brake = fmax(c->brake, c->rc_brake);
        if (c->rc_side != 0 && c->steer_input * c->rc_side > 0) c->steer_input *= (real)0.35;
        if (c->rc_steer != 0) {
            real hw = t->hw - 14, lat = c->lateral;
            if (!((c->rc_steer > 0 && lat > hw) || (c->rc_steer < 0 && lat < -hw)))
                c->steer_input = clampr(c->steer_input + c->rc_steer, -1, 1);
        }
    }
}

/* ---------------------------------------------------------------- training.py Evaluation */
FN void kill_car(Car *c) {
    c->alive = 0;
    c->frozen = 1;
    c->retired = 1;
}

FN void update_track_state(const Track *t, Eval *e, Car *c) {
    real L = t->length;
    int idx;
    real s, lat;
    project(t, c->px, c->py, c->idx, 4, 6, &idx, &s, &lat);
    real ds = s - c->s;
    if (ds < -L / 2) ds += L;
    else if (ds > L / 2) ds -= L;
    c->distance += ds;
    c->idx = idx; c->s = s; c->lateral = lat;
    c->on_grass = fabs(lat) > t->hw;
    int floor_now = (int)floor(c->distance / L);
    if (floor_now > c->lap_floor) {
        c->lap_floor = floor_now;
        if (floor_now == 0) {
            if (!c->timing_started) { c->timing_started = 1; c->lap_start_time = e->time; }
        } else if (c->timing_started) {
            real lap = e->time - c->lap_start_time;
            c->lap_start_time = e->time;
            c->laps_done++;
            if (c->best_lap < 0 || lap < c->best_lap) c->best_lap = lap;
            if (e->stop_after_lap) kill_car(c);
        }
    }
}

FN void ranks(const Eval *e, int *out) {
    /* sorted(range(n), key=-distance): stable, ties keep the index order */
    for (int i = 0; i < e->n; i++) {
        int r = 0;
        for (int k = 0; k < e->n; k++) {
            if (e->cars[k].distance > e->cars[i].distance || (e->cars[k].distance == e->cars[i].distance && k < i)) r++;
        }
        out[i] = r;
    }
}

FN void eval_init(const Track *t, const Job *job, Eval *e) {
    e->time = e->check_timer = 0;
    e->duration = job->duration;
    e->n = job->n;
    e->traffic = job->traffic;
    e->stop_after_lap = job->stop_after_lap;
    e->finished = 0;
    e->track = job->track;
    for (int k = 0; k < e->n; k++) {
        Car *c = &e->cars[k];
        c->throttle = c->brake = c->steer_input = 0;
        c->lap_start_time = 0; c->best_lap = -1;
        c->wall_impulse = c->car_impulse = c->grass_time = 0;
        c->timer = 0; c->out_steer = c->out_pedal = c->radar_c = 0;
        c->rc_timer = c->rc_lift = c->rc_brake = c->rc_steer = c->rc_side = 0;
        c->tailgate = c->tl_off = 0;
        c->on_grass = c->timing_started = c->laps_done = 0;
        c->frozen = c->retired = c->straight_mode = c->has_inputs = 0;
        c->crashes = c->tl_violations = 0;
        c->alive = 1;
        c->collide = c->sees_others = job->traffic;
        c->genome = job->genome[k];
        c->idx = 0; c->s = 0;
        real x, y, h;
        if (job->traffic) grid_pose(t, k, &x, &y, &h);
        else pose_at(t, job->start_s, 0, &x, &y, &h);
        car_place(t, c, x, y, h);
        c->start_distance = c->check_distance = c->distance;
    }
    int r[MAX_HEAT];
    ranks(e, r);
    for (int k = 0; k < e->n; k++) e->cars[k].start_rank = r[k];
}

FN void eval_step(const Track *t, Eval *e, G const real *nets) {
    const real h = (real)PHYSICS_STEP;
    int n = e->n;
    for (int k = 0; k < n; k++) {
        if (e->cars[k].alive) control(t, e, &e->cars[k], nets, h);
    }
    for (int k = 0; k < n; k++) physics_step(t, &e->cars[k], h);
    if (e->traffic) {
        const real bp = (real)(CAR_LENGTH * 1.15 * CAR_LENGTH * 1.15);
        for (int i = 0; i < n; i++) {
            Car *a = &e->cars[i];
            if (a->retired || !a->collide) continue;
            for (int k = i + 1; k < n; k++) {
                Car *b = &e->cars[k];
                if (b->retired || !b->collide) continue;
                real dx = a->px - b->px, dy = a->py - b->py;
                if (dx * dx + dy * dy > bp) continue;
                real nx, ny, depth;
                if (sat_test(a, b, &nx, &ny, &depth)) resolve_car_collision(a, b, nx, ny, depth);
            }
        }
    }
    for (int k = 0; k < n; k++) resolve_wall_collision(t, &e->cars[k]);
    real hw = t->hw;
    for (int k = 0; k < n; k++) {
        Car *c = &e->cars[k];
        update_track_state(t, e, c);
        update_aero(t, c);
        real lat = fabs(c->lateral);
        if (c->tl_off == 0 && lat > hw + (real)TL_MARGIN) {
            c->tl_off = e->time + (real)1e-6;
        } else if (c->tl_off != 0 && lat < hw) {
            if (e->time - c->tl_off >= (real)TL_MIN_TIME) c->tl_violations++;
            c->tl_off = 0;
        }
        if (e->traffic && c->alive && c->has_inputs && c->radar_c > (real)0.7) c->tailgate += h;
    }
    e->time += h;
    e->check_timer += h;
    if (e->check_timer >= (real)CHECK_INTERVAL) {
        e->check_timer = 0;
        for (int k = 0; k < n; k++) {
            Car *c = &e->cars[k];
            if (c->alive && c->distance - c->check_distance < (real)MIN_PROGRESS) kill_car(c);
            c->check_distance = c->distance;
        }
    }
    int any = 0;
    for (int k = 0; k < n; k++) any |= e->cars[k].alive;
    if (e->time >= e->duration || !any) e->finished = 1;
}

/* raw fitness per car (not yet normalised by ref_speed * duration) */
FN void eval_fitness(const Eval *e, Style st, real *out) {
    int end_rank[MAX_HEAT];
    ranks(e, end_rank);
    for (int k = 0; k < e->n; k++) {
        const Car *c = &e->cars[k];
        real f = c->distance - c->start_distance;
        f -= st.w_wall * c->wall_impulse + (real)OFFTRACK_PENALTY * c->grass_time + (real)CRASH_PENALTY * c->crashes;
        f -= (real)TRACK_LIMIT_PENALTY * c->tl_violations;
        if (e->traffic) {
            f += st.w_gain * (c->start_rank - end_rank[k]);
            f -= st.w_car * c->car_impulse;
            f += st.w_tailgate * c->tailgate;
        }
        out[k] = f;
    }
}

FN void make_track(Track *t, G const TrackInfo *ti, G const real *cx, G const real *cy, G const real *tx,
                   G const real *ty, G const real *nx, G const real *ny, G const real *cum, G const real *lo,
                   G const int *aero) {
    int off = ti->off;
    t->cx = cx + off; t->cy = cy + off; t->tx = tx + off; t->ty = ty + off;
    t->nx = nx + off; t->ny = ny + off; t->cum = cum + off; t->lo = lo + off; t->aero = aero + off;
    t->n = ti->n;
    t->length = ti->length; t->hw = ti->half_width; t->wl = ti->wall_limit;
    for (int k = 0; k < N_SETUP; k++) t->sf[k] = ti->sf[k];
}

#ifdef __OPENCL_VERSION__
#define TRACK_ARGS __global const TrackInfo *tinfo, __global const real *cx, __global const real *cy, \
    __global const real *tx, __global const real *ty, __global const real *nx, __global const real *ny, \
    __global const real *cum, __global const real *lo, __global const int *aero

__kernel void eval_size(__global int *out) { out[0] = (int)sizeof(Eval); }

__kernel void eval_init_k(__global const Job *jobs, __global Eval *states, int njobs, TRACK_ARGS) {
    int gid = get_global_id(0);
    if (gid >= njobs) return;
    Job job = jobs[gid];
    Track t;
    make_track(&t, &tinfo[job.track], cx, cy, tx, ty, nx, ny, cum, lo, aero);
    Eval e;
    eval_init(&t, &job, &e);
    states[gid] = e;
}

__kernel void eval_run_k(__global Eval *states, int njobs, int steps, __global const real *nets,
                         __global float *fit, __global float *laps, __global int *done, Style st, TRACK_ARGS) {
    int gid = get_global_id(0);
    if (gid >= njobs || done[gid]) return;
    Eval e = states[gid];
    Track t;
    make_track(&t, &tinfo[e.track], cx, cy, tx, ty, nx, ny, cum, lo, aero);
    for (int s = 0; s < steps && !e.finished; s++) eval_step(&t, &e, nets);
    if (e.finished) {
        real f[MAX_HEAT];
        eval_fitness(&e, st, f);
        for (int k = 0; k < e.n; k++) {
            fit[gid * MAX_HEAT + k] = (float)f[k];
            laps[gid * MAX_HEAT + k] = (float)e.cars[k].best_lap;
        }
        done[gid] = 1;
    }
    states[gid] = e;
}
#endif

#endif
