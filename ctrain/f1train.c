/* Copyright Olivenda (Oliver Petz) 2026
 *
 * f1train - native trainer for the F1 game's neural drivers (the C/GPU version of train.py).
 *
 *   f1train base|balanced|aggressive|cautious|all [--generations N] [--population N] [--device auto|cpu|gpu]
 *           [--gpu best|all|N]   (which OpenCL GPU: the strongest, all of them or one by its number;
 *                                 --list-gpus shows them)
 *           [--threads N] [--seed N] [--warm] [--fresh] [--data data/train_data.bin] [--brains data/brains]
 *
 * data/train_data.bin comes from the game (python train.py --export, or the KI-Training screen writes it).
 * After every generation the full state is saved to <brains>/<mode>.ctrain.state - quit any time (Ctrl+C,
 * closing the window), the next start continues from the last finished generation. --fresh starts over.
 * The result is written to <brains>/<mode>.json in the same format as the Python trainer.
 *
 * Build: gcc -std=gnu23 -O3 -march=native -ffast-math -o f1train.exe f1train.c -static   (see build.bat)
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "sim.h"

static const char SIM_SOURCE[] = {
#embed "sim.h"
    , 0};

#define MAX_TRACKS 32
#define MAX_STYLES 16
#define MAX_GENS 100000
#define STATE_VERSION 1
#define SOLO_DURATION 24.0
#define SOLO_STARTS 2
#define TRAFFIC_DURATION 40.0
#define HEAT_SIZE MAX_HEAT
#define ELITE 3
#define BENCHMARK_CANDIDATES 5
#define CROSSOVER_RATE 0.6
#define MUTATION_RATE 0.12

/* ================================================================ data file */
typedef struct {
    char key[64];
    TrackInfo info;
    double ref_lap, ref_speed;
} TrackMeta;

typedef struct {
    char key[32], title[128], description[512];
    double w[4];
} StyleDef;

static int n_tracks, n_styles, n_input_names;
static TrackMeta tracks[MAX_TRACKS];
static StyleDef styles[MAX_STYLES];
static char input_names[N_IN][64];
static double *T_cx, *T_cy, *T_tx, *T_ty, *T_nx, *T_ny, *T_cum, *T_lo;
static int *T_aero, T_total;

static void die(const char *msg) {
    printf("@ERR %s\n%s\n", msg, msg);
    fflush(stdout);
    exit(1);
}

static void rd(FILE *f, void *p, size_t n) {
    if (fread(p, 1, n, f) != n) die("train_data.bin ist beschädigt (zu kurz).");
}
static uint32_t rd_u32(FILE *f) { uint32_t v; rd(f, &v, 4); return v; }
static double rd_f64(FILE *f) { double v; rd(f, &v, 8); return v; }
static void rd_str(FILE *f, char *out, size_t cap) {
    uint32_t n = rd_u32(f);
    char *tmp = malloc(n + 1);
    rd(f, tmp, n);
    tmp[n] = 0;
    snprintf(out, cap, "%s", tmp);
    free(tmp);
}

static void load_data(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        char msg[600];
        snprintf(msg, sizeof msg, "%s fehlt - zuerst 'python train.py --export' ausführen.", path);
        die(msg);
    }
    char magic[4];
    rd(f, magic, 4);
    if (memcmp(magic, "F1TD", 4) || rd_u32(f) != 1) die("train_data.bin: unbekanntes Format.");
    uint32_t sizes[4];
    for (int i = 0; i < 4; i++) sizes[i] = rd_u32(f);
    if (sizes[0] != N_IN || sizes[1] != H1 || sizes[2] != H2 || sizes[3] != N_OUT)
        die("Netzgröße passt nicht zum C-Trainer (sim.h N_IN/H1/H2/N_OUT anpassen).");
    n_input_names = (int)rd_u32(f);
    if (n_input_names != N_IN) die("Anzahl der Netz-Eingänge passt nicht.");
    for (int i = 0; i < N_IN; i++) rd_str(f, input_names[i], sizeof input_names[i]);
    n_styles = (int)rd_u32(f);
    if (n_styles > MAX_STYLES) die("zu viele Stile");
    for (int i = 0; i < n_styles; i++) {
        rd_str(f, styles[i].key, sizeof styles[i].key);
        rd_str(f, styles[i].title, sizeof styles[i].title);
        rd_str(f, styles[i].description, sizeof styles[i].description);
        for (int k = 0; k < 4; k++) styles[i].w[k] = rd_f64(f);
    }
    n_tracks = (int)rd_u32(f);
    if (n_tracks < 1 || n_tracks > MAX_TRACKS) die("train_data.bin: keine Strecken.");
    long pos = ftell(f);
    /* first pass: sizes */
    T_total = 0;
    for (int t = 0; t < n_tracks; t++) {
        rd_str(f, tracks[t].key, sizeof tracks[t].key);
        int n = (int)rd_u32(f);
        tracks[t].info.n = n;
        tracks[t].info.off = T_total;
        T_total += n;
        fseek(f, 5 * 8 + N_SETUP * 8 + (long)n * (8 * 8 + 4), SEEK_CUR);
    }
    T_cx = malloc(sizeof(double) * T_total); T_cy = malloc(sizeof(double) * T_total);
    T_tx = malloc(sizeof(double) * T_total); T_ty = malloc(sizeof(double) * T_total);
    T_nx = malloc(sizeof(double) * T_total); T_ny = malloc(sizeof(double) * T_total);
    T_cum = malloc(sizeof(double) * T_total); T_lo = malloc(sizeof(double) * T_total);
    T_aero = malloc(sizeof(int) * T_total);
    fseek(f, pos, SEEK_SET);
    for (int t = 0; t < n_tracks; t++) {
        TrackMeta *m = &tracks[t];
        rd_str(f, m->key, sizeof m->key);
        int n = (int)rd_u32(f), off = m->info.off;
        m->info.length = (float)rd_f64(f);
        m->info.half_width = (float)rd_f64(f);
        m->info.wall_limit = (float)rd_f64(f);
        m->ref_lap = rd_f64(f);
        m->ref_speed = rd_f64(f);
        for (int k = 0; k < N_SETUP; k++) m->info.sf[k] = (float)rd_f64(f);
        double *arrs[8] = {T_cx, T_cy, T_tx, T_ty, T_nx, T_ny, T_cum, T_lo};
        for (int a = 0; a < 8; a++) rd(f, arrs[a] + off, sizeof(double) * n);
        rd(f, T_aero + off, sizeof(int) * n);
    }
    fclose(f);
}

/* the CPU path keeps the exact double values; TrackInfo carries floats for the GPU */
static double track_len_d[MAX_TRACKS], track_hw_d[MAX_TRACKS], track_wl_d[MAX_TRACKS];

static void cpu_track(int k, Track *t) {
    const TrackInfo *ti = &tracks[k].info;
    make_track(t, ti, T_cx, T_cy, T_tx, T_ty, T_nx, T_ny, T_cum, T_lo, T_aero);
    t->length = track_len_d[k];
    t->hw = track_hw_d[k];
    t->wl = track_wl_d[k];
}

/* ================================================================ rng (xoshiro256**) */
typedef struct { uint64_t s[4]; } Rng;
static uint64_t rotl(uint64_t x, int k) { return (x << k) | (x >> (64 - k)); }
static uint64_t rng_next(Rng *r) {
    uint64_t *s = r->s, out = rotl(s[1] * 5, 7) * 9, t = s[1] << 17;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t; s[3] = rotl(s[3], 45);
    return out;
}
static void rng_seed(Rng *r, uint64_t seed) {
    for (int i = 0; i < 4; i++) {
        uint64_t z = (seed += 0x9E3779B97F4A7C15ull);
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
        r->s[i] = z ^ (z >> 31);
    }
}
static double rng_uniform(Rng *r) { return (rng_next(r) >> 11) * (1.0 / 9007199254740992.0); }
static int rng_int(Rng *r, int n) { return (int)(rng_uniform(r) * n); }
static double rng_gauss(Rng *r, double mu, double sigma) {
    double u1 = rng_uniform(r), u2 = rng_uniform(r);
    if (u1 < 1e-300) u1 = 1e-300;
    return mu + sigma * sqrt(-2.0 * log(u1)) * cos(TAU_R * u2);
}

/* ================================================================ minimal JSON reader (for base.json) */
typedef struct JV {
    char type;                  /* o a n s t f z */
    double num;
    char *str;
    int n;
    char **keys;
    struct JV **items;
} JV;

static const char *jp;
static void jws(void) { while (*jp == ' ' || *jp == '\n' || *jp == '\r' || *jp == '\t') jp++; }
static JV *jparse(void);
static char *jstr(void) {
    jp++;
    const char *start = jp;
    size_t cap = 16, len = 0;
    char *out = malloc(cap);
    while (*jp && *jp != '"') {
        char ch = *jp++;
        if (ch == '\\' && *jp) {
            ch = *jp++;
            if (ch == 'u') { jp += 4; ch = '?'; }
            else if (ch == 'n') ch = '\n';
            else if (ch == 't') ch = '\t';
        }
        if (len + 2 > cap) out = realloc(out, cap *= 2);
        out[len++] = ch;
    }
    (void)start;
    if (*jp == '"') jp++;
    out[len] = 0;
    return out;
}
static JV *jparse(void) {
    jws();
    JV *v = calloc(1, sizeof(JV));
    if (*jp == '{' || *jp == '[') {
        char close = *jp == '{' ? '}' : ']';
        v->type = *jp == '{' ? 'o' : 'a';
        jp++;
        int cap = 4;
        v->items = malloc(sizeof(JV *) * cap);
        v->keys = malloc(sizeof(char *) * cap);
        jws();
        while (*jp && *jp != close) {
            if (v->n == cap) {
                cap *= 2;
                v->items = realloc(v->items, sizeof(JV *) * cap);
                v->keys = realloc(v->keys, sizeof(char *) * cap);
            }
            v->keys[v->n] = NULL;
            if (v->type == 'o') {
                jws();
                v->keys[v->n] = jstr();
                jws();
                if (*jp == ':') jp++;
            }
            v->items[v->n++] = jparse();
            jws();
            if (*jp == ',') jp++;
            jws();
        }
        if (*jp) jp++;
    } else if (*jp == '"') {
        v->type = 's';
        v->str = jstr();
    } else if (!strncmp(jp, "true", 4)) { v->type = 't'; jp += 4; }
    else if (!strncmp(jp, "false", 5)) { v->type = 'f'; jp += 5; }
    else if (!strncmp(jp, "null", 4)) { v->type = 'z'; jp += 4; }
    else {
        char *end;
        v->type = 'n';
        v->num = strtod(jp, &end);
        if (end == jp) jp++; else jp = end;
    }
    return v;
}
static JV *jget(JV *o, const char *key) {
    if (!o || o->type != 'o') return NULL;
    for (int i = 0; i < o->n; i++) if (!strcmp(o->keys[i], key)) return o->items[i];
    return NULL;
}
static JV *jload(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc(n + 1);
    if (fread(buf, 1, n, f) != (size_t)n) { fclose(f); free(buf); return NULL; }
    buf[n] = 0;
    fclose(f);
    jp = buf;
    return jparse();            /* the buffer stays alive: tiny, one file */
}

/* network {"sizes","weights","biases"} -> flat params (W1 b1 W2 b2 W3 b3) */
static int json_network(JV *net, double *p) {
    JV *W = jget(net, "weights"), *B = jget(net, "biases");
    const int sz[4] = {N_IN, H1, H2, N_OUT};
    if (!W || !B || W->n != 3 || B->n != 3) return 0;
    int k = 0;
    for (int l = 0; l < 3; l++) {
        JV *Wl = W->items[l], *Bl = B->items[l];
        if (Wl->n != sz[l + 1] || Bl->n != sz[l + 1]) return 0;
        for (int j = 0; j < sz[l + 1]; j++) {
            if (Wl->items[j]->n != sz[l]) return 0;
            for (int i = 0; i < sz[l]; i++) p[k++] = Wl->items[j]->items[i]->num;
        }
        for (int j = 0; j < sz[l + 1]; j++) p[k++] = Bl->items[j]->num;
    }
    return k == N_PARAMS;
}

/* ================================================================ trainer state */
typedef struct { int gen; double best, mean; } Hist;
typedef struct {
    char label[16];
    int generation;
    double fitness;
    double bench[MAX_TRACKS];   /* < 0: no lap */
    double net[N_PARAMS];
} Ckpt;

typedef struct {
    char mode[32];
    int style, traffic, warm;
    int target, pop, generation;
    double sigma0;
    Rng rng;
    double *population;         /* pop * N_PARAMS */
    double *fitness;
    Hist *history;
    int n_ckpt;
    Ckpt ckpt[8];
    int base_generations;       /* parent info for the traffic styles, -1 unknown */
    double sim_time;
} Trainer;

static char brains_dir[512] = "data/brains";
static int g_threads, g_use_gpu, g_force_gpu;
static int g_gpu_pick = -2;    /* -2 the strongest GPU, -1 all GPUs, else the number from --list-gpus */
/* "auto": the GPU only pays off with many independent jobs (big solo populations); a handful of traffic heats
   or the checkpoint benchmarks run much faster on the CPU threads */
#define GPU_MIN_JOBS 1000
static volatile LONG g_stop;

static void path_in(char *out, size_t cap, const char *dir, const char *name) { snprintf(out, cap, "%s/%s", dir, name); }

static int py_round(double v) { return (int)nearbyint(v); }     /* banker's rounding like Python round() */

static const char *checkpoint_label(const Trainer *tr, int gen) {
    int g = tr->target;
    if (gen == g) return "final";
    if (!strcmp(tr->mode, "base")) {
        int e = py_round(g * 0.3) < 1 ? 1 : py_round(g * 0.3);
        int m = py_round(g * 0.6) < 1 ? 1 : py_round(g * 0.6);
        if (gen == e) return "early";
        if (gen == m) return "mid";
    } else {
        int m = g / 2 < 1 ? 1 : g / 2;
        if (gen == m) return "mid";
    }
    return NULL;
}

/* ---------------------------------------------------------------- save / resume */
static void state_path(const Trainer *tr, char *out, size_t cap) {
    char name[64];
    snprintf(name, sizeof name, "%s.ctrain.state", tr->mode);
    path_in(out, cap, brains_dir, name);
}

static void save_state(const Trainer *tr) {
    char path[600], tmp[620];
    state_path(tr, path, sizeof path);
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "wb");
    if (!f) { printf("Warnung: Zwischenstand konnte nicht gespeichert werden (%s)\n", tmp); return; }
    uint32_t hdr[8] = {0x53433146u, STATE_VERSION, (uint32_t)tr->target, (uint32_t)tr->pop, (uint32_t)tr->generation,
                       (uint32_t)n_tracks, (uint32_t)N_PARAMS, (uint32_t)tr->n_ckpt};
    fwrite(hdr, sizeof hdr, 1, f);
    fwrite(tr->mode, sizeof tr->mode, 1, f);
    fwrite(&tr->warm, sizeof(int), 1, f);
    fwrite(&tr->sigma0, sizeof(double), 1, f);
    fwrite(&tr->rng, sizeof(Rng), 1, f);
    fwrite(&tr->base_generations, sizeof(int), 1, f);
    fwrite(&tr->sim_time, sizeof(double), 1, f);
    fwrite(tr->history, sizeof(Hist), tr->generation, f);
    fwrite(tr->ckpt, sizeof(Ckpt), tr->n_ckpt, f);
    fwrite(tr->population, sizeof(double), (size_t)tr->pop * N_PARAMS, f);
    int ok = fflush(f) == 0;
    ok &= fclose(f) == 0;
    if (!ok || !MoveFileExA(tmp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        printf("Warnung: Zwischenstand konnte nicht gespeichert werden (%s)\n", path);
}

static int load_state(Trainer *tr) {
    char path[600];
    state_path(tr, path, sizeof path);
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    uint32_t hdr[8];
    char mode[32];
    int ok = fread(hdr, sizeof hdr, 1, f) == 1 && hdr[0] == 0x53433146u && hdr[1] == STATE_VERSION &&
             hdr[5] == (uint32_t)n_tracks && hdr[6] == N_PARAMS && hdr[7] <= 8;
    ok = ok && fread(mode, sizeof mode, 1, f) == 1 && !strcmp(mode, tr->mode);
    if (!ok) { fclose(f); printf("Zwischenstand %s passt nicht - starte neu.\n", path); return 0; }
    tr->target = (int)hdr[2];
    tr->pop = (int)hdr[3];
    tr->generation = (int)hdr[4];
    tr->n_ckpt = (int)hdr[7];
    tr->population = malloc(sizeof(double) * tr->pop * N_PARAMS);
    tr->fitness = calloc(tr->pop, sizeof(double));
    tr->history = malloc(sizeof(Hist) * (MAX_GENS + 1));
    ok = fread(&tr->warm, sizeof(int), 1, f) == 1 && fread(&tr->sigma0, sizeof(double), 1, f) == 1 &&
         fread(&tr->rng, sizeof(Rng), 1, f) == 1 && fread(&tr->base_generations, sizeof(int), 1, f) == 1 &&
         fread(&tr->sim_time, sizeof(double), 1, f) == 1 &&
         fread(tr->history, sizeof(Hist), tr->generation, f) == (size_t)tr->generation &&
         fread(tr->ckpt, sizeof(Ckpt), tr->n_ckpt, f) == (size_t)tr->n_ckpt &&
         fread(tr->population, sizeof(double), (size_t)tr->pop * N_PARAMS, f) == (size_t)tr->pop * N_PARAMS;
    fclose(f);
    if (!ok) { printf("Zwischenstand %s ist beschädigt - starte neu.\n", path); return 0; }
    return 1;
}

/* ================================================================ evaluation: CPU threads */
typedef struct {
    const Job *jobs;
    int njobs;
    const double *nets;
    Style st;
    float *fit, *laps;
    volatile LONG next, done;
} Batch;

static DWORD WINAPI cpu_worker(LPVOID arg) {
    Batch *b = arg;
    for (;;) {
        LONG j = InterlockedIncrement(&b->next) - 1;
        if (j >= b->njobs) break;
        const Job *job = &b->jobs[j];
        Track t;
        cpu_track(job->track, &t);
        Eval *e = malloc(sizeof(Eval));
        eval_init(&t, job, e);
        while (!e->finished) eval_step(&t, e, b->nets);
        double f[MAX_HEAT];
        eval_fitness(e, b->st, f);
        for (int k = 0; k < e->n; k++) {
            b->fit[j * MAX_HEAT + k] = (float)f[k];
            b->laps[j * MAX_HEAT + k] = (float)e->cars[k].best_lap;
        }
        free(e);
        InterlockedIncrement(&b->done);
    }
    return 0;
}

static void run_cpu(Batch *b, int report) {
    b->next = b->done = 0;
    int n = g_threads < b->njobs ? g_threads : b->njobs;
    HANDLE th[256];
    for (int i = 0; i < n; i++) th[i] = CreateThread(NULL, 0, cpu_worker, b, 0, NULL);
    while (WaitForMultipleObjects(n, th, TRUE, 250) == WAIT_TIMEOUT) {
        if (report) { printf("@TASK %ld %d\n", b->done, b->njobs); fflush(stdout); }
    }
    for (int i = 0; i < n; i++) CloseHandle(th[i]);
}

/* ================================================================ evaluation: GPU (OpenCL, loaded at runtime) */
typedef int32_t cl_int;
typedef uint32_t cl_uint;
typedef uint64_t cl_ulong;
typedef void *cl_platform_id, *cl_device_id, *cl_context, *cl_command_queue, *cl_mem, *cl_program, *cl_kernel,
    *cl_event;
#define CL_DEVICE_TYPE_GPU (1 << 2)
#define CL_MEM_READ_WRITE (1 << 0)
#define CL_MEM_READ_ONLY (1 << 2)
#define CL_MEM_COPY_HOST_PTR (1 << 5)
#define CL_DEVICE_NAME 0x102B
#define CL_DEVICE_BOARD_NAME_AMD 0x4038
#define CL_DEVICE_MAX_COMPUTE_UNITS 0x1002
#define CL_PROGRAM_BUILD_LOG 0x1183

static struct {
    cl_int (*GetPlatformIDs)(cl_uint, cl_platform_id *, cl_uint *);
    cl_int (*GetDeviceIDs)(cl_platform_id, cl_ulong, cl_uint, cl_device_id *, cl_uint *);
    cl_int (*GetDeviceInfo)(cl_device_id, cl_uint, size_t, void *, size_t *);
    cl_context (*CreateContext)(const intptr_t *, cl_uint, const cl_device_id *, void *, void *, cl_int *);
    cl_command_queue (*CreateCommandQueue)(cl_context, cl_device_id, cl_ulong, cl_int *);
    cl_program (*CreateProgramWithSource)(cl_context, cl_uint, const char **, const size_t *, cl_int *);
    cl_int (*BuildProgram)(cl_program, cl_uint, const cl_device_id *, const char *, void *, void *);
    cl_int (*GetProgramBuildInfo)(cl_program, cl_device_id, cl_uint, size_t, void *, size_t *);
    cl_kernel (*CreateKernel)(cl_program, const char *, cl_int *);
    cl_mem (*CreateBuffer)(cl_context, cl_ulong, size_t, void *, cl_int *);
    cl_int (*SetKernelArg)(cl_kernel, cl_uint, size_t, const void *);
    cl_int (*EnqueueNDRangeKernel)(cl_command_queue, cl_kernel, cl_uint, const size_t *, const size_t *,
                                   const size_t *, cl_uint, const cl_event *, cl_event *);
    cl_int (*EnqueueReadBuffer)(cl_command_queue, cl_mem, cl_uint, size_t, size_t, void *, cl_uint,
                                const cl_event *, cl_event *);
    cl_int (*EnqueueWriteBuffer)(cl_command_queue, cl_mem, cl_uint, size_t, size_t, const void *, cl_uint,
                                 const cl_event *, cl_event *);
    cl_int (*Finish)(cl_command_queue);
    cl_int (*ReleaseMemObject)(cl_mem);
} cl;

typedef struct {
    cl_device_id dev;
    cl_context ctx;
    cl_command_queue q;
    cl_kernel k_init, k_run;
    cl_mem tinfo, arr[8], aero;
    int eval_size;
    cl_uint units;
    double rate;                /* measured jobs per second (load balancing between GPUs), 0 = not yet */
    char name[256];
} Gpu;

#define MAX_GPUS 8
static Gpu gpus[MAX_GPUS];
static int n_gpus;

static int cl_load(void) {
    static int loaded = -1;
    if (loaded >= 0) return loaded;
    loaded = 0;
    HMODULE lib = LoadLibraryA("OpenCL.dll");
    if (!lib) { printf("GPU: OpenCL.dll nicht gefunden.\n"); return 0; }
#define LOAD(f) cl.f = (typeof(cl.f))(void (*)(void))GetProcAddress(lib, "cl" #f); if (!cl.f) { printf("GPU: cl" #f " fehlt.\n"); return 0; }
    LOAD(GetPlatformIDs) LOAD(GetDeviceIDs) LOAD(GetDeviceInfo) LOAD(CreateContext) LOAD(CreateCommandQueue)
    LOAD(CreateProgramWithSource) LOAD(BuildProgram) LOAD(GetProgramBuildInfo) LOAD(CreateKernel) LOAD(CreateBuffer)
    LOAD(SetKernelArg) LOAD(EnqueueNDRangeKernel) LOAD(EnqueueReadBuffer) LOAD(EnqueueWriteBuffer) LOAD(Finish)
    LOAD(ReleaseMemObject)
#undef LOAD
    loaded = 1;
    return 1;
}

/* AMD's driver names the chip ("gfx1036"); its board-name query has the product name ("AMD Radeon(TM) Graphics") */
static void device_name(cl_device_id dev, char *out, size_t cap) {
    out[0] = 0;
    char board[256] = "";
    if (cl.GetDeviceInfo(dev, CL_DEVICE_BOARD_NAME_AMD, sizeof board, board, NULL) == 0 && board[0])
        snprintf(out, cap, "%s", board);
    else
        cl.GetDeviceInfo(dev, CL_DEVICE_NAME, cap, out, NULL);
}

/* every OpenCL GPU of every platform (NVIDIA, AMD, Intel...), numbered in a stable order */
static int gpu_list(cl_device_id *out, int cap) {
    if (!cl_load()) return 0;
    cl_platform_id plats[8];
    cl_uint np = 0;
    if (cl.GetPlatformIDs(8, plats, &np) != 0 || np == 0) return 0;
    int n = 0;
    for (cl_uint i = 0; i < np && n < cap; i++) {
        cl_device_id devs[MAX_GPUS];
        cl_uint nd = 0;
        if (cl.GetDeviceIDs(plats[i], CL_DEVICE_TYPE_GPU, MAX_GPUS, devs, &nd) != 0) continue;
        for (cl_uint k = 0; k < nd && n < cap; k++) out[n++] = devs[k];
    }
    return n;
}

static int gpu_setup(Gpu *g, cl_device_id dev) {
    g->dev = dev;
    device_name(dev, g->name, sizeof g->name);
    cl.GetDeviceInfo(dev, CL_DEVICE_MAX_COMPUTE_UNITS, sizeof g->units, &g->units, NULL);
    if (g->units < 1) g->units = 1;
    cl_int err;
    g->ctx = cl.CreateContext(NULL, 1, &dev, NULL, NULL, &err);
    if (err) return 0;
    g->q = cl.CreateCommandQueue(g->ctx, dev, 0, &err);
    if (err) return 0;
    const char *src = SIM_SOURCE;
    cl_program prog = cl.CreateProgramWithSource(g->ctx, 1, &src, NULL, &err);
    if (err) return 0;
    if (cl.BuildProgram(prog, 1, &dev, "-cl-single-precision-constant -cl-fast-relaxed-math", NULL, NULL) != 0) {
        static char logbuf[16384];
        cl.GetProgramBuildInfo(prog, dev, CL_PROGRAM_BUILD_LOG, sizeof logbuf - 1, logbuf, NULL);
        printf("GPU %s: Kernel lässt sich nicht bauen:\n%.3000s\n", g->name, logbuf);
        return 0;
    }
    cl_kernel k_size = cl.CreateKernel(prog, "eval_size", &err);
    g->k_init = cl.CreateKernel(prog, "eval_init_k", &err);
    g->k_run = cl.CreateKernel(prog, "eval_run_k", &err);
    if (err) return 0;
    cl_mem out = cl.CreateBuffer(g->ctx, CL_MEM_READ_WRITE, sizeof(int), NULL, &err);
    size_t one = 1;
    cl.SetKernelArg(k_size, 0, sizeof(cl_mem), &out);
    cl.EnqueueNDRangeKernel(g->q, k_size, 1, NULL, &one, NULL, 0, NULL, NULL);
    cl.EnqueueReadBuffer(g->q, out, 1, 0, sizeof(int), &g->eval_size, 0, NULL, NULL);
    cl.ReleaseMemObject(out);
    /* tracks as float */
    TrackInfo ti[MAX_TRACKS];
    for (int k = 0; k < n_tracks; k++) ti[k] = tracks[k].info;
    g->tinfo = cl.CreateBuffer(g->ctx, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, sizeof(TrackInfo) * n_tracks, ti, &err);
    double *src_arr[8] = {T_cx, T_cy, T_tx, T_ty, T_nx, T_ny, T_cum, T_lo};
    float *tmp = malloc(sizeof(float) * T_total);
    for (int a = 0; a < 8; a++) {
        for (int i = 0; i < T_total; i++) tmp[i] = (float)src_arr[a][i];
        g->arr[a] = cl.CreateBuffer(g->ctx, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, sizeof(float) * T_total, tmp, &err);
    }
    free(tmp);
    g->aero = cl.CreateBuffer(g->ctx, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, sizeof(int) * T_total, T_aero, &err);
    return err == 0 && g->eval_size > 0;
}

/* the chosen GPU (g_gpu_pick) or all usable ones */
static int gpu_init(void) {
    cl_device_id devs[MAX_GPUS];
    int n = gpu_list(devs, MAX_GPUS);
    if (n == 0) { printf("GPU: kein OpenCL-Grafikchip gefunden.\n"); return 0; }
    if (g_gpu_pick >= n) { printf("GPU %d gibt es nicht (nur 0-%d) - nehme die stärkste.\n", g_gpu_pick, n - 1); g_gpu_pick = -2; }
    if (g_gpu_pick == -2) {     /* the one with the most compute units (usually the graphics card) */
        cl_uint best = 0;
        for (int i = 0; i < n; i++) {
            cl_uint cu = 0;
            cl.GetDeviceInfo(devs[i], CL_DEVICE_MAX_COMPUTE_UNITS, sizeof cu, &cu, NULL);
            if (cu > best || g_gpu_pick < 0) { best = cu; g_gpu_pick = i; }
        }
    }
    n_gpus = 0;
    for (int i = 0; i < n; i++) {
        if (g_gpu_pick >= 0 && i != g_gpu_pick) continue;
        if (gpu_setup(&gpus[n_gpus], devs[i])) n_gpus++;
        else printf("GPU %d nicht nutzbar - übersprungen.\n", i);
    }
    return n_gpus > 0;
}

static void gpu_names(char *out, size_t cap) {
    out[0] = 0;
    for (int i = 0; i < n_gpus; i++) {
        size_t len = strlen(out);
        snprintf(out + len, cap - len, "%s%s", i ? " + " : "", gpus[i].name);
    }
}

static void set_track_args(Gpu *g, cl_kernel k, int first) {
    cl.SetKernelArg(k, first, sizeof(cl_mem), &g->tinfo);
    for (int a = 0; a < 8; a++) cl.SetKernelArg(k, first + 1 + a, sizeof(cl_mem), &g->arr[a]);
    cl.SetKernelArg(k, first + 9, sizeof(cl_mem), &g->aero);
}

/* one GPU's share of the jobs */
typedef struct {
    int first, count;
    cl_mem jobs, nets, states, fit, laps, dbuf;
    int *done;
    size_t global, local;
    int finished;
} Slice;

static int slice_start(Gpu *g, Slice *sl, Batch *b, const float *netf, int npop) {
    cl_int err;
    int nj = sl->count;
    sl->jobs = cl.CreateBuffer(g->ctx, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, sizeof(Job) * nj,
                               (void *)(b->jobs + sl->first), &err);
    if (err) return 0;
    sl->nets = cl.CreateBuffer(g->ctx, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, sizeof(float) * npop * N_PARAMS,
                               (void *)netf, &err);
    if (err) return 0;
    sl->states = cl.CreateBuffer(g->ctx, CL_MEM_READ_WRITE, (size_t)g->eval_size * nj, NULL, &err);
    if (err) return 0;
    sl->fit = cl.CreateBuffer(g->ctx, CL_MEM_READ_WRITE, sizeof(float) * nj * MAX_HEAT, NULL, &err);
    if (err) return 0;
    sl->laps = cl.CreateBuffer(g->ctx, CL_MEM_READ_WRITE, sizeof(float) * nj * MAX_HEAT, NULL, &err);
    if (err) return 0;
    sl->done = calloc(nj, sizeof(int));
    sl->dbuf = cl.CreateBuffer(g->ctx, CL_MEM_READ_WRITE | CL_MEM_COPY_HOST_PTR, sizeof(int) * nj, sl->done, &err);
    if (err) return 0;
    sl->local = 64;
    sl->global = ((size_t)nj + sl->local - 1) / sl->local * sl->local;
    cl.SetKernelArg(g->k_init, 0, sizeof(cl_mem), &sl->jobs);
    cl.SetKernelArg(g->k_init, 1, sizeof(cl_mem), &sl->states);
    cl.SetKernelArg(g->k_init, 2, sizeof(int), &nj);
    set_track_args(g, g->k_init, 3);
    if (cl.EnqueueNDRangeKernel(g->q, g->k_init, 1, NULL, &sl->global, &sl->local, 0, NULL, NULL)) return 0;
    int steps = 600;
    Style st = b->st;
    cl.SetKernelArg(g->k_run, 0, sizeof(cl_mem), &sl->states);
    cl.SetKernelArg(g->k_run, 1, sizeof(int), &nj);
    cl.SetKernelArg(g->k_run, 2, sizeof(int), &steps);
    cl.SetKernelArg(g->k_run, 3, sizeof(cl_mem), &sl->nets);
    cl.SetKernelArg(g->k_run, 4, sizeof(cl_mem), &sl->fit);
    cl.SetKernelArg(g->k_run, 5, sizeof(cl_mem), &sl->laps);
    cl.SetKernelArg(g->k_run, 6, sizeof(cl_mem), &sl->dbuf);
    cl.SetKernelArg(g->k_run, 7, sizeof(Style), &st);
    set_track_args(g, g->k_run, 8);
    return 1;
}

static void slice_free(Slice *sl) {
    cl_mem *m[] = {&sl->jobs, &sl->nets, &sl->states, &sl->fit, &sl->laps, &sl->dbuf};
    for (int i = 0; i < 6; i++) if (*m[i]) cl.ReleaseMemObject(*m[i]);
    free(sl->done);
}

static double now_s(void);

typedef struct {
    Gpu *g;
    Slice *sl;
    Batch *b;
    double t0;
    int multi, ok;
    volatile LONG progress;
} GpuRun;

/* run in slices (~5 s of sim time) so no single kernel trips the Windows GPU watchdog */
static DWORD WINAPI gpu_thread(LPVOID arg) {
    GpuRun *r = arg;
    Gpu *g = r->g;
    Slice *sl = r->sl;
    r->ok = 1;
    for (;;) {
        if (cl.EnqueueNDRangeKernel(g->q, g->k_run, 1, NULL, &sl->global, &sl->local, 0, NULL, NULL) ||
            cl.EnqueueReadBuffer(g->q, sl->dbuf, 1, 0, sizeof(int) * sl->count, sl->done, 0, NULL, NULL)) {
            r->ok = 0;
            return 0;
        }
        int c = 0;
        for (int j = 0; j < sl->count; j++) c += sl->done[j];
        r->progress = c;
        if (c == sl->count) break;
    }
    if (r->multi) {
        double rate = sl->count / fmax(1e-3, now_s() - r->t0);
        g->rate = g->rate > 0 ? 0.5 * g->rate + 0.5 * rate : rate;
    }
    size_t off = (size_t)sl->first * MAX_HEAT, n = sizeof(float) * sl->count * MAX_HEAT;
    if (cl.EnqueueReadBuffer(g->q, sl->fit, 1, 0, n, r->b->fit + off, 0, NULL, NULL) ||
        cl.EnqueueReadBuffer(g->q, sl->laps, 1, 0, n, r->b->laps + off, 0, NULL, NULL))
        r->ok = 0;
    return 0;
}

static int run_gpu(Batch *b, int npop, int report) {
    int nj = b->njobs;
    float *netf = malloc(sizeof(float) * (size_t)npop * N_PARAMS);
    for (size_t i = 0; i < (size_t)npop * N_PARAMS; i++) netf[i] = (float)b->nets[i];
    /* split the jobs over the GPUs by their measured speed (first run: compute units, the fast one gets more) */
    Slice sl[MAX_GPUS];
    memset(sl, 0, sizeof sl);
    double weight[MAX_GPUS], total = 0;
    for (int g = 0; g < n_gpus; g++) total += weight[g] = gpus[g].rate > 0 ? gpus[g].rate : (double)gpus[g].units;
    int first = 0, ok = 1, used = 0;
    double t0 = now_s();
    for (int g = 0; g < n_gpus && first < nj; g++) {
        int share = g == n_gpus - 1 ? nj - first : (int)(nj * weight[g] / total);
        if (share <= 0) continue;
        sl[g].first = first;
        sl[g].count = share;
        first += share;
        used = g + 1;
        if (!slice_start(&gpus[g], &sl[g], b, netf, npop)) { ok = 0; break; }
    }
    free(netf);
    if (ok) {
        /* every GPU runs its share in its own thread, so a slow one never holds up a fast one */
        HANDLE th[MAX_GPUS];
        GpuRun run[MAX_GPUS];
        int nth = 0;
        for (int g = 0; g < used; g++) {
            if (!sl[g].count) continue;
            run[nth] = (GpuRun){.g = &gpus[g], .sl = &sl[g], .b = b, .t0 = t0, .multi = n_gpus > 1};
            th[nth] = CreateThread(NULL, 0, gpu_thread, &run[nth], 0, NULL);
            nth++;
        }
        while (WaitForMultipleObjects(nth, th, TRUE, 250) == WAIT_TIMEOUT) {
            if (report) {
                long cnt = 0;
                for (int k = 0; k < nth; k++) cnt += run[k].progress;
                printf("@TASK %ld %d\n", cnt, nj);
                fflush(stdout);
            }
        }
        for (int k = 0; k < nth; k++) { CloseHandle(th[k]); ok &= run[k].ok; }
    }
    for (int g = 0; g < used; g++) slice_free(&sl[g]);
    return ok;
}

/* "auto" times both on the real workload (the first generations) and then keeps the faster one: solo runs
   are thousands of independent jobs (GPU), traffic heats are a few hundred long jobs (usually CPU) */
static double m_cpu, m_gpu;
static int m_nj = -1, m_using = -1;

static void announce(int gpu_now, const char *why) {
    if (gpu_now == m_using) return;
    m_using = gpu_now;
    char gname[1024];
    gpu_names(gname, sizeof gname);
    if (gpu_now) printf("@USING GPU %s - %s\n", gname, why);
    else printf("@USING CPU (%d Threads) - %s\n", g_threads, why);
    fflush(stdout);
}

static void evaluate(const Job *jobs, int nj, const double *nets, int npop, Style st, float *fit, float *laps,
                     int report) {
    Batch b = {.jobs = jobs, .njobs = nj, .nets = nets, .st = st, .fit = fit, .laps = laps};
    int gpu = 0;
    const char *why = "";
    if (g_use_gpu && g_force_gpu) {
        gpu = 1;
        why = "nur GPU gewählt";
    } else if (g_use_gpu && !report) {
        gpu = nj >= GPU_MIN_JOBS;       /* checkpoint benchmarks: small, quick */
    } else if (g_use_gpu) {
        if (nj != m_nj) { m_nj = nj; m_cpu = m_gpu = 0.0; }
        if (m_gpu == 0.0 && m_cpu == 0.0) { gpu = nj >= GPU_MIN_JOBS; why = "messe Tempo"; }
        else if (m_gpu == 0.0) { gpu = 1; why = "messe Tempo"; }
        else if (m_cpu == 0.0) { gpu = 0; why = "messe Tempo"; }
        else {
            /* switch only for a clear gain (10 %), not back and forth on noise */
            gpu = m_using == 1 ? !(m_cpu < 0.9 * m_gpu) : m_gpu < 0.9 * m_cpu;
            static char buf[160];
            snprintf(buf, sizeof buf, "schneller (GPU %.2fs, CPU %.2fs pro Generation)", m_gpu, m_cpu);
            why = buf;
        }
    }
    if (report) announce(gpu, why);
    double t0 = now_s();
    if (gpu) {
        if (run_gpu(&b, npop, report)) {
            if (report && !g_force_gpu) m_gpu = now_s() - t0;
            return;
        }
        printf("GPU-Lauf fehlgeschlagen - weiter auf der CPU.\n@DEVICE CPU (%d Threads)\n", g_threads);
        g_use_gpu = 0;
        if (report) announce(0, "GPU-Fehler");
        t0 = now_s();
    }
    run_cpu(&b, report);
    if (report && g_use_gpu) m_cpu = now_s() - t0;
}

/* ================================================================ genetic algorithm (training.py Trainer) */
static void random_net(Rng *r, double *p) {
    const int sz[4] = {N_IN, H1, H2, N_OUT};
    int k = 0;
    for (int l = 0; l < 3; l++) {
        for (int j = 0; j < sz[l + 1]; j++)
            for (int i = 0; i < sz[l]; i++) p[k++] = rng_gauss(r, 0, 1.0 / sqrt((double)sz[l]));
        for (int j = 0; j < sz[l + 1]; j++) p[k++] = 0;
    }
}

static void mutate(Rng *r, double *p, double rate, double sigma) {
    const int sz[4] = {N_IN, H1, H2, N_OUT};
    int k = 0;
    for (int l = 0; l < 3; l++) {
        for (int j = 0; j < sz[l + 1] * sz[l]; j++, k++) {
            double u = rng_uniform(r);
            if (u < 0.02 * rate) p[k] = rng_gauss(r, 0, 1);
            else if (u < rate) p[k] += rng_gauss(r, 0, sigma);
        }
        for (int j = 0; j < sz[l + 1]; j++, k++)
            if (rng_uniform(r) < rate) p[k] += rng_gauss(r, 0, sigma);
    }
}

static void crossover(Rng *r, const double *a, const double *b, double *child) {
    const int sz[4] = {N_IN, H1, H2, N_OUT};
    int k = 0;
    for (int l = 0; l < 3; l++) {
        int wbase = k, bbase = k + sz[l + 1] * sz[l];
        for (int j = 0; j < sz[l + 1]; j++) {
            const double *src = rng_uniform(r) < 0.5 ? a : b;
            memcpy(child + wbase + j * sz[l], src + wbase + j * sz[l], sizeof(double) * sz[l]);
            child[bbase + j] = src[bbase + j];
        }
        k = bbase + sz[l + 1];
    }
}

static int load_base_network(double *p, int *generations) {
    char path[600];
    path_in(path, sizeof path, brains_dir, "base.json");
    JV *root = jload(path);
    if (!root) return 0;
    JV *g = jget(root, "generations");
    *generations = g && g->type == 'n' ? (int)g->num : -1;
    JV *cps = jget(root, "checkpoints");
    if (!cps || cps->type != 'a' || cps->n == 0) return 0;
    JV *net = NULL;
    for (int i = 0; i < cps->n; i++) {
        JV *lab = jget(cps->items[i], "label");
        if (lab && lab->type == 's' && !strcmp(lab->str, "final")) net = jget(cps->items[i], "network");
    }
    if (!net) net = jget(cps->items[cps->n - 1], "network");
    return net && json_network(net, p);
}

static void init_population(Trainer *tr) {
    tr->population = malloc(sizeof(double) * tr->pop * N_PARAMS);
    tr->fitness = calloc(tr->pop, sizeof(double));
    tr->history = malloc(sizeof(Hist) * (MAX_GENS + 1));
    tr->base_generations = -1;
    if (!strcmp(tr->mode, "base") && !tr->warm) {
        printf("Neue Population: %d zufällige Netze [%d, %d, %d, %d]\n", tr->pop, N_IN, H1, H2, N_OUT);
        for (int i = 0; i < tr->pop; i++) random_net(&tr->rng, tr->population + (size_t)i * N_PARAMS);
        return;
    }
    double seed[N_PARAMS];
    if (!load_base_network(seed, &tr->base_generations)) die("Zuerst das Basis-Netz trainieren (base.json fehlt).");
    if (tr->warm) printf("Warmstart: Population aus dem vorhandenen Basis-Netz\n");
    memcpy(tr->population, seed, sizeof seed);
    for (int i = 1; i < tr->pop; i++) {
        double *c = tr->population + (size_t)i * N_PARAMS;
        memcpy(c, seed, sizeof seed);
        mutate(&tr->rng, c, 0.3, tr->sigma0);
    }
}

static int plan_generation(Trainer *tr, Job *jobs) {
    int nj = 0;
    if (tr->traffic) {
        int *ids = malloc(sizeof(int) * tr->pop);
        for (int i = 0; i < tr->pop; i++) ids[i] = i;
        for (int round = 0; round < 2; round++) {
            int track = rng_int(&tr->rng, n_tracks);
            for (int i = tr->pop - 1; i > 0; i--) {
                int j = rng_int(&tr->rng, i + 1), t = ids[i];
                ids[i] = ids[j]; ids[j] = t;
            }
            for (int i = 0; i < tr->pop; i += HEAT_SIZE) {
                Job *jb = &jobs[nj++];
                memset(jb, 0, sizeof *jb);
                jb->track = track;
                jb->traffic = 1;
                jb->n = tr->pop - i < HEAT_SIZE ? tr->pop - i : HEAT_SIZE;
                for (int k = 0; k < jb->n; k++) jb->genome[k] = ids[i + k];
                jb->duration = (float)TRAFFIC_DURATION;
            }
        }
        free(ids);
    } else {
        for (int t = 0; t < n_tracks; t++) {
            for (int s = 0; s < SOLO_STARTS; s++) {
                float start = (float)(rng_uniform(&tr->rng) * track_len_d[t]);
                for (int g = 0; g < tr->pop; g++) {
                    Job *jb = &jobs[nj++];
                    memset(jb, 0, sizeof *jb);
                    jb->track = t;
                    jb->n = 1;
                    jb->genome[0] = g;
                    jb->start_s = start;
                    jb->duration = (float)SOLO_DURATION;
                }
            }
        }
    }
    return nj;
}

static Style style_of(const Trainer *tr) {
    const double *w = styles[tr->style].w;
    return (Style){(float)w[0], (float)w[1], (float)w[2], (float)w[3]};
}

/* best lap per track for one network (240 s from just before the line, stops after a lap) */
static void benchmark(const Trainer *tr, const double *nets, int ncand, double bench[][MAX_TRACKS]) {
    Job *jobs = calloc(ncand * n_tracks, sizeof(Job));
    int nj = 0;
    for (int c = 0; c < ncand; c++)
        for (int t = 0; t < n_tracks; t++) {
            Job *jb = &jobs[nj++];
            jb->track = t; jb->n = 1; jb->genome[0] = c; jb->start_s = -30.0f; jb->duration = 240.0f;
            jb->stop_after_lap = 1;
        }
    float *fit = malloc(sizeof(float) * nj * MAX_HEAT), *laps = malloc(sizeof(float) * nj * MAX_HEAT);
    evaluate(jobs, nj, nets, ncand, style_of(tr), fit, laps, 0);
    for (int c = 0; c < ncand; c++)
        for (int t = 0; t < n_tracks; t++) {
            double v = laps[(c * n_tracks + t) * MAX_HEAT];
            bench[c][t] = v > 0 ? floor(v * 1000 + 0.5) / 1000 : -1;
        }
    free(jobs); free(fit); free(laps);
}

static void add_checkpoint(Trainer *tr, const char *label, const int *ranked) {
    int ncand = tr->pop < BENCHMARK_CANDIDATES ? tr->pop : BENCHMARK_CANDIDATES;
    double *cand = malloc(sizeof(double) * ncand * N_PARAMS);
    for (int c = 0; c < ncand; c++) memcpy(cand + c * N_PARAMS, tr->population + (size_t)ranked[c] * N_PARAMS, sizeof(double) * N_PARAMS);
    double bench[BENCHMARK_CANDIDATES][MAX_TRACKS];
    benchmark(tr, cand, ncand, bench);
    int best = 0, best_laps = -1;
    double best_sum = 0;
    for (int c = 0; c < ncand; c++) {
        int laps = 0;
        double sum = 0;
        for (int t = 0; t < n_tracks; t++)
            if (bench[c][t] > 0) { laps++; sum += bench[c][t] / tracks[t].ref_lap; }
        if (laps > best_laps || (laps == best_laps && -sum > -best_sum)) { best = c; best_laps = laps; best_sum = sum; }
    }
    Ckpt *cp = &tr->ckpt[tr->n_ckpt < 8 ? tr->n_ckpt++ : 7];
    snprintf(cp->label, sizeof cp->label, "%s", label);
    cp->generation = tr->generation;
    cp->fitness = tr->history[tr->generation - 1].best;
    memcpy(cp->bench, bench[best], sizeof cp->bench);
    memcpy(cp->net, cand + best * N_PARAMS, sizeof cp->net);
    printf("Checkpoint '%s' (Gen. %d) Rundenzeiten: ", label, tr->generation);
    for (int t = 0; t < n_tracks; t++) {
        if (bench[best][t] > 0) printf("%s%s %.2fs", t ? ", " : "", tracks[t].key, bench[best][t]);
        else printf("%s%s --", t ? ", " : "", tracks[t].key);
    }
    printf("\n");
    free(cand);
}

static void evolve(Trainer *tr, const int *ranked) {
    double sigma = tr->sigma0 * pow(0.97, tr->generation);
    if (sigma < 0.03) sigma = 0.03;
    double *next = malloc(sizeof(double) * tr->pop * N_PARAMS);
    int n = 0;
    for (; n < ELITE && n < tr->pop; n++)
        memcpy(next + (size_t)n * N_PARAMS, tr->population + (size_t)ranked[n] * N_PARAMS, sizeof(double) * N_PARAMS);
    while (n < tr->pop) {
        int par[2];
        for (int p = 0; p < 2; p++) {
            int c[3];               /* rng.sample(range(pop), 3) */
            c[0] = rng_int(&tr->rng, tr->pop);
            do c[1] = rng_int(&tr->rng, tr->pop); while (c[1] == c[0]);
            do c[2] = rng_int(&tr->rng, tr->pop); while (c[2] == c[0] || c[2] == c[1]);
            int best = c[0];
            for (int k = 1; k < 3; k++) if (tr->fitness[c[k]] > tr->fitness[best]) best = c[k];
            par[p] = best;
        }
        double *child = next + (size_t)n * N_PARAMS;
        const double *p1 = tr->population + (size_t)par[0] * N_PARAMS, *p2 = tr->population + (size_t)par[1] * N_PARAMS;
        if (rng_uniform(&tr->rng) < CROSSOVER_RATE) crossover(&tr->rng, p1, p2, child);
        else memcpy(child, p1, sizeof(double) * N_PARAMS);
        mutate(&tr->rng, child, MUTATION_RATE, sigma);
        n++;
    }
    free(tr->population);
    tr->population = next;
}

static double *g_fit_sort;
static int cmp_rank(const void *a, const void *b) {
    double fa = g_fit_sort[*(const int *)a], fb = g_fit_sort[*(const int *)b];
    if (fa != fb) return fa < fb ? 1 : -1;
    return *(const int *)a - *(const int *)b;
}

/* ---------------------------------------------------------------- result file (BrainLibrary.save format) */
static void json_str(FILE *f, const char *s) {
    fputc('"', f);
    for (; *s; s++) {
        if (*s == '"' || *s == '\\') fputc('\\', f);
        fputc(*s, f);
    }
    fputc('"', f);
}
static void json_num(FILE *f, double v, int digits) {
    char buf[64];
    snprintf(buf, sizeof buf, "%.*f", digits, v);
    if (strchr(buf, '.')) {
        char *e = buf + strlen(buf) - 1;
        while (*e == '0' && e[-1] != '.') *e-- = 0;
    }
    if (!strcmp(buf, "-0.0")) strcpy(buf, "0.0");
    fputs(buf, f);
}
static void json_network_out(FILE *f, const double *p) {
    const int sz[4] = {N_IN, H1, H2, N_OUT};
    fprintf(f, "{\"sizes\":[%d,%d,%d,%d],\"weights\":[", N_IN, H1, H2, N_OUT);
    int k = 0, bk[3];
    for (int l = 0; l < 3; l++) {
        fputs(l ? ",[" : "[", f);
        for (int j = 0; j < sz[l + 1]; j++) {
            fputs(j ? ",[" : "[", f);
            for (int i = 0; i < sz[l]; i++) { if (i) fputc(',', f); json_num(f, p[k++], 5); }
            fputc(']', f);
        }
        fputc(']', f);
        bk[l] = k;
        k += sz[l + 1];
    }
    fputs("],\"biases\":[", f);
    for (int l = 0; l < 3; l++) {
        fputs(l ? ",[" : "[", f);
        for (int j = 0; j < sz[l + 1]; j++) { if (j) fputc(',', f); json_num(f, p[bk[l] + j], 5); }
        fputc(']', f);
    }
    fputs("]}", f);
}

static void finish(Trainer *tr) {
    char path[600], backup[600], tmp[620], name[64];
    snprintf(name, sizeof name, "%s.json", tr->mode);
    path_in(path, sizeof path, brains_dir, name);
    snprintf(name, sizeof name, "%s.backup.json", tr->mode);
    path_in(backup, sizeof backup, brains_dir, name);
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "wb");
    if (!f) die("Ergebnis konnte nicht geschrieben werden.");
    const StyleDef *sd = &styles[tr->style];
    fputs("{\"style\":", f); json_str(f, tr->mode);
    fputs(",\"title\":", f); json_str(f, sd->title);
    fputs(",\"description\":", f); json_str(f, sd->description);
    fputs(",\"reward\":{\"wall\":", f); json_num(f, sd->w[0], 6);
    fputs(",\"car\":", f); json_num(f, sd->w[1], 6);
    fputs(",\"gain\":", f); json_num(f, sd->w[2], 6);
    fputs(",\"tailgate\":", f); json_num(f, sd->w[3], 6);
    fprintf(f, "},\"sizes\":[%d,%d,%d,%d],\"inputs\":[", N_IN, H1, H2, N_OUT);
    for (int i = 0; i < N_IN; i++) { if (i) fputc(',', f); json_str(f, input_names[i]); }
    fprintf(f, "],\"population\":%d,\"generations\":%d,\"trained_on\":[", tr->pop, tr->generation);
    for (int t = 0; t < n_tracks; t++) { if (t) fputc(',', f); json_str(f, tracks[t].key); }
    fputs("],\"parent\":", f);
    if (tr->traffic) {
        if (tr->base_generations >= 0) fprintf(f, "{\"style\":\"base\",\"generations\":%d}", tr->base_generations);
        else fputs("{\"style\":\"base\",\"generations\":null}", f);
    } else fputs("null", f);
    fputs(",\"clone_loss\":[],\"trainer\":\"c\",\"history\":[", f);
    for (int g = 0; g < tr->generation; g++) {
        fprintf(f, "%s{\"gen\":%d,\"best\":", g ? "," : "", tr->history[g].gen);
        json_num(f, tr->history[g].best, 1);
        fputs(",\"mean\":", f);
        json_num(f, tr->history[g].mean, 1);
        fputc('}', f);
    }
    fputs("],\"checkpoints\":[", f);
    for (int c = 0; c < tr->n_ckpt; c++) {
        const Ckpt *cp = &tr->ckpt[c];
        fprintf(f, "%s{\"label\":\"%s\",\"generation\":%d,\"fitness\":", c ? "," : "", cp->label, cp->generation);
        json_num(f, cp->fitness, 1);
        fputs(",\"benchmark\":{", f);
        for (int t = 0; t < n_tracks; t++) {
            if (t) fputc(',', f);
            json_str(f, tracks[t].key);
            fputc(':', f);
            if (cp->bench[t] > 0) json_num(f, cp->bench[t], 3); else fputs("null", f);
        }
        fputs("},\"network\":", f);
        json_network_out(f, cp->net);
        fputc('}', f);
    }
    fputs("]}", f);
    if (fclose(f) != 0) die("Ergebnis konnte nicht geschrieben werden.");
    if (GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES) MoveFileExA(path, backup, MOVEFILE_REPLACE_EXISTING);
    if (!MoveFileExA(tmp, path, MOVEFILE_REPLACE_EXISTING)) die("Ergebnis konnte nicht gespeichert werden.");
    char sp[600];
    state_path(tr, sp, sizeof sp);
    DeleteFileA(sp);
    printf("Gespeichert: %s\n@DONE %s\n", path, path);
    fflush(stdout);
}

/* ================================================================ main loop */
static void on_sigint(int sig) {
    (void)sig;
    if (InterlockedIncrement(&g_stop) > 1) {
        printf("\nAbbruch. Letzte fertige Generation ist gespeichert.\n");
        fflush(stdout);
        _exit(130);
    }
    printf("\nStopp nach dieser Generation (nochmal Strg+C = sofort, der letzte Stand ist gespeichert) ...\n");
    fflush(stdout);
    signal(SIGINT, on_sigint);
}

static double now_s(void) {
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}

static int train(const char *mode, int generations, int population, uint64_t seed, int warm, int fresh) {
    Trainer tr;
    memset(&tr, 0, sizeof tr);
    snprintf(tr.mode, sizeof tr.mode, "%s", mode);
    tr.style = -1;
    for (int i = 0; i < n_styles; i++) if (!strcmp(styles[i].key, mode)) tr.style = i;
    if (tr.style < 0) die("Unbekannter Modus.");
    if (!strcmp(mode, "clone")) die("Klon-Training (deine Fahrdaten) läuft nur im Python-Trainer.");
    tr.traffic = strcmp(mode, "base") != 0;

    int resumed = !fresh && load_state(&tr);
    if (resumed) {
        if (generations > 0 && generations != tr.target) {
            if (generations < tr.generation + 1) generations = tr.generation + 1;
            tr.target = generations;
        }
        printf("Fortsetzen: '%s' ab Generation %d/%d (Population %d)\n", mode, tr.generation + 1, tr.target, tr.pop);
        for (int g = 0; g < tr.generation; g++)
            printf("@HIST %d %.1f %.1f\n", tr.history[g].gen, tr.history[g].best, tr.history[g].mean);
    } else {
        /* train.py defaults */
        tr.target = generations > 0 ? generations : !strcmp(mode, "base") ? (warm ? 30 : 60) : 20;
        tr.pop = population;
        tr.warm = warm && !strcmp(mode, "base");
        rng_seed(&tr.rng, seed);
        tr.sigma0 = !strcmp(mode, "base") && !tr.warm ? 0.35 : 0.08;
        printf("\n=== Training '%s': %d Generationen, Population %d ===\n", mode, tr.target, tr.pop);
        init_population(&tr);
    }
    fflush(stdout);

    Job *jobs = malloc(sizeof(Job) * (tr.pop * n_tracks * SOLO_STARTS + 2 * (tr.pop / HEAT_SIZE + 2)));
    float *fit = malloc(sizeof(float) * MAX_HEAT * (tr.pop * n_tracks * SOLO_STARTS + 2 * (tr.pop / HEAT_SIZE + 2)));
    float *laps = malloc(sizeof(float) * MAX_HEAT * (tr.pop * n_tracks * SOLO_STARTS + 2 * (tr.pop / HEAT_SIZE + 2)));
    double *sum = malloc(sizeof(double) * tr.pop), *mn = malloc(sizeof(double) * tr.pop);
    int *cnt = malloc(sizeof(int) * tr.pop), *ranked = malloc(sizeof(int) * tr.pop);
    double t0 = now_s();

    while (tr.generation < tr.target) {
        double tg = now_s();
        int nj = plan_generation(&tr, jobs);
        evaluate(jobs, nj, tr.population, tr.pop, style_of(&tr), fit, laps, 1);
        for (int i = 0; i < tr.pop; i++) { sum[i] = 0; mn[i] = 1e18; cnt[i] = 0; }
        double sim = 0;
        for (int j = 0; j < nj; j++) {
            double norm = tracks[jobs[j].track].ref_speed * jobs[j].duration;
            sim += jobs[j].duration;
            for (int k = 0; k < jobs[j].n; k++) {
                int g = jobs[j].genome[k];
                double s = fit[j * MAX_HEAT + k] / norm;
                sum[g] += s;
                if (s < mn[g]) mn[g] = s;
                cnt[g]++;
            }
        }
        double total = 0;
        for (int i = 0; i < tr.pop; i++) {
            if (!cnt[i]) tr.fitness[i] = -1e9;
            else if (tr.traffic) tr.fitness[i] = 1000.0 * sum[i] / cnt[i];
            else tr.fitness[i] = 1000.0 * (0.6 * sum[i] / cnt[i] + 0.4 * mn[i]);
            total += tr.fitness[i];
            ranked[i] = i;
        }
        g_fit_sort = tr.fitness;
        qsort(ranked, tr.pop, sizeof(int), cmp_rank);
        double best = tr.fitness[ranked[0]], mean = total / tr.pop;
        tr.generation++;
        tr.sim_time += sim;
        tr.history[tr.generation - 1] = (Hist){tr.generation, floor(best * 10 + 0.5) / 10, floor(mean * 10 + 0.5) / 10};
        double secs = now_s() - tg;
        printf("Gen. %d/%d · beste Fitness %.0f · Schnitt %.0f · %.1fs (%.0fx Echtzeit)\n", tr.generation, tr.target,
               best, mean, secs, sim / secs);
        printf("@GEN %d %d %.1f %.1f %.1f\n", tr.generation, tr.target, best, mean, sim / secs);
        fflush(stdout);
        const char *label = checkpoint_label(&tr, tr.generation);
        if (label) add_checkpoint(&tr, label, ranked);
        if (tr.generation >= tr.target) break;
        evolve(&tr, ranked);
        save_state(&tr);
        if (g_stop) {
            printf("Gestoppt nach Generation %d - Zwischenstand gespeichert, beim nächsten Start geht es weiter.\n",
                   tr.generation);
            fflush(stdout);
            return 2;
        }
    }
    finish(&tr);
    printf("=== fertig in %.0fs (Simulationszeit %.0f min) ===\n", now_s() - t0, tr.sim_time / 60);
    fflush(stdout);
    free(jobs); free(fit); free(laps); free(sum); free(mn); free(cnt); free(ranked);
    return 0;
}

int main(int argc, char **argv) {
    SetConsoleOutputCP(CP_UTF8);
    setvbuf(stdout, NULL, _IOLBF, 1 << 14);
    const char *mode = NULL, *data = "data/train_data.bin", *device = "auto";
    int generations = 0, population = 40, warm = 0, fresh = 0, bench_only = 0;
    uint64_t seed = (uint64_t)time(NULL) ^ ((uint64_t)GetCurrentProcessId() << 32);
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    g_threads = (int)si.dwNumberOfProcessors;
    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--generations") && v) { generations = atoi(v); i++; }
        else if (!strcmp(a, "--population") && v) { population = atoi(v); i++; }
        else if (!strcmp(a, "--seed") && v) { seed = strtoull(v, NULL, 10); i++; }
        else if (!strcmp(a, "--threads") && v) { g_threads = atoi(v); i++; }
        else if (!strcmp(a, "--device") && v) { device = v; i++; }
        else if (!strcmp(a, "--gpu") && v) { g_gpu_pick = !strcmp(v, "all") ? -1 : !strcmp(v, "best") ? -2 : atoi(v); i++; }
        else if (!strcmp(a, "--list-gpus")) {
            /* "@GPU <n> <compute units> <name>" per OpenCL GPU, for the game's GPU picker */
            cl_device_id devs[MAX_GPUS];
            int n = gpu_list(devs, MAX_GPUS);
            for (int k = 0; k < n; k++) {
                char name[256] = "";
                cl_uint cu = 0;
                device_name(devs[k], name, sizeof name);
                cl.GetDeviceInfo(devs[k], CL_DEVICE_MAX_COMPUTE_UNITS, sizeof cu, &cu, NULL);
                printf("@GPU %d %u %s\n", k, cu, name);
            }
            return 0;
        }
        else if (!strcmp(a, "--data") && v) { data = v; i++; }
        else if (!strcmp(a, "--brains") && v) { snprintf(brains_dir, sizeof brains_dir, "%s", v); i++; }
        else if (!strcmp(a, "--warm")) warm = 1;
        else if (!strcmp(a, "--fresh")) fresh = 1;
        else if (!strcmp(a, "--bench")) bench_only = 1;
        else if (a[0] != '-' && !mode) mode = a;
        else {
            printf("Unbekannte Option: %s\n", a);
            return 1;
        }
    }
    if (!mode) {
        printf("f1train base|balanced|aggressive|cautious|all [--generations N] [--population N]\n"
               "        [--device auto|cpu|gpu] [--gpu best|all|N] [--list-gpus] [--threads N] [--seed N] [--warm] [--fresh]\n"
               "        [--data data/train_data.bin] [--brains data/brains]\n");
        return 1;
    }
    if (g_threads < 1) g_threads = 1;
    if (g_threads > 256) g_threads = 256;
    if (population < 4) population = 4;
    load_data(data);
    for (int k = 0; k < n_tracks; k++) {
        /* exact double values for the CPU path (TrackInfo holds floats for the GPU) */
        double L = T_cum[tracks[k].info.off + tracks[k].info.n - 1];
        int last = tracks[k].info.off + tracks[k].info.n - 1, first = tracks[k].info.off;
        double dx = T_cx[first] - T_cx[last], dy = T_cy[first] - T_cy[last];
        track_len_d[k] = L + sqrt(dx * dx + dy * dy);
        track_hw_d[k] = tracks[k].info.half_width;
        track_wl_d[k] = tracks[k].info.wall_limit;
    }
    if (strcmp(device, "cpu") != 0) {
        g_use_gpu = gpu_init();
        if (!g_use_gpu && !strcmp(device, "gpu")) die("Keine nutzbare GPU (OpenCL) gefunden.");
        g_force_gpu = !strcmp(device, "gpu");
    }
    char gname[1024];
    gpu_names(gname, sizeof gname);
    if (g_use_gpu && !g_force_gpu)
        printf("Gerät: GPU %s (OpenCL) für große Populationen (ab %d Läufen), sonst CPU mit %d Threads\n"
               "@DEVICE GPU %s + CPU (%d Threads)\n", gname, GPU_MIN_JOBS, g_threads, gname, g_threads);
    else if (g_use_gpu) printf("Gerät: GPU %s (OpenCL)\n@DEVICE GPU %s\n", gname, gname);
    else printf("Gerät: CPU, %d Threads\n@DEVICE CPU (%d Threads)\n", g_threads, g_threads);
    fflush(stdout);
    signal(SIGINT, on_sigint);
    if (bench_only) {
        /* lap times of the existing <mode>.json final network (checks the port against the Python trainer) */
        Trainer tr;
        memset(&tr, 0, sizeof tr);
        snprintf(tr.mode, sizeof tr.mode, "%s", mode);
        double net[N_PARAMS], bench[1][MAX_TRACKS];
        int gens;
        if (!load_base_network(net, &gens)) die("base.json fehlt.");
        benchmark(&tr, net, 1, bench);
        for (int t = 0; t < n_tracks; t++) printf("%s %.3f\n", tracks[t].key, bench[0][t]);
        return 0;
    }

    static const char *all[] = {"base", "balanced", "aggressive", "cautious"};
    int n_modes = !strcmp(mode, "all") ? 4 : 1;
    for (int m = 0; m < n_modes; m++) {
        const char *md = n_modes == 4 ? all[m] : mode;
        int rc = train(md, generations, population, seed + (uint64_t)m * 7919, warm, fresh);
        if (rc) return rc;
    }
    return 0;
}
