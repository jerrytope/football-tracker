# Football Tracker

> Automated football tracking platform — converts broadcast MP4 footage into
> structured X/Y player coordinate data with zero manual tagging.

## Architecture

```
frontend/        React + Vite tactical pitch viewer
backend/         Django + DRF REST API
cv_engine/       YOLOv8 + ByteTrack computer vision pipeline
docker/          Service Dockerfiles
docker-compose.yml  Local dev infrastructure (PostgreSQL, Redis, Adminer)
```

The pipeline: upload creates a `Match` → Celery task runs the CV engine → per-frame player and
ball coordinates are projected onto a 105×68 m pitch and bulk-inserted → tactical events
(possession, passes, interceptions, shots, sprints) are derived from those coordinates → the
frontend replays it on a canvas.

## Hardware note

`cv_engine/engine/device.py` picks the inference device automatically: **CUDA if
`torch.cuda.is_available()`, otherwise CPU.** This is deliberate on Apple Silicon too — it never
requests `"mps"`, because several ops this pipeline depends on (torchvision's NMS among them)
are not implemented for the MPS backend, and requesting it outright breaks inference instead of
just running slower. So on a Mac (or any machine with no NVIDIA GPU) inference runs on CPU, same
as this Windows machine's Intel UHD Graphics 620 (torch `2.12.1+cpu`), at roughly **4–6 seconds
per frame**. That is expected, not a hang. The Celery queue is still named `gpu`; it is only a
label — it does not mean the code requires one.

Measured runtimes for the bundled test clips are in [Testing the pipeline](#testing-the-pipeline).

---

## Prerequisites

- **Docker Desktop** — provides PostgreSQL and Redis. [Windows](https://www.docker.com/products/docker-desktop/) /
  [Mac](https://www.docker.com/products/docker-desktop/) (Apple Silicon or Intel build, matching your Mac).
- **Python 3** and **Node** — `python3 --version` / `node --version`. On Mac, install both with
  Homebrew if missing: `brew install python node`.
- `start-local.ps1` is a PowerShell script and runs on both platforms:
  - Windows: the built-in `powershell.exe` (5.1) is enough.
  - Mac: install PowerShell 7 first — `brew install --cask powershell` — then run scripts with
    `pwsh`, not `powershell`.
- `ffmpeg` / `ffprobe` — used only to cut and inspect test clips, not by the app itself.
  Windows: expected at `C:\ffmpeg\bin`. Mac: `brew install ffmpeg`.

`frontend/node_modules` and `backend/.venv` are **not** committed to git (they're gitignored), so
a fresh clone — including on a teammate's Mac — starts without them. `npm install` sets up the
former; `start-local.ps1` now creates and populates `backend/.venv` for you automatically on
first run if it doesn't already exist, using whichever `python3`/`python` it finds on `PATH`, so
there's no manual venv/pip step on either platform.

## Quick start

```powershell
# Windows
.\start-local.ps1

# Mac
pwsh ./start-local.ps1
```

That creates `backend/.venv` if it's missing, starts Docker if needed, brings up Postgres and
Redis, waits for Postgres to pass its healthcheck, applies migrations, and launches the Django
server and Celery worker. Add `-Adminer` to also start the database inspector, `-Restart` to
restart just the Celery worker after a code change, or `-Stop` to stop Django and Celery.

On Windows, Django and Celery each launch in their own console window (and the worker needs
`--pool=solo`, since the default prefork pool relies on `fork()`, which Windows doesn't have). On
Mac, both run in the background instead — there's no cross-platform way to pop open a new
terminal window from a script — with output going to `logs/django.log` and `logs/celery.log`
(`tail -f` them to watch progress), and the worker runs with Celery's normal prefork pool since
`fork()` works fine there.

Then, for the UI:

```powershell
cd frontend
npm run dev
```

<details>
<summary>Manual equivalent, if you prefer to run the steps yourself</summary>

```powershell
# 1. Infrastructure (NOT the cv_engine service - it sits behind the "cv" compose profile)
docker compose up -d db redis

# 2. Database
cd backend
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser   # first time only

# 3. API (leave running)
.venv\Scripts\python.exe manage.py runserver

# 4. Celery worker, in a second terminal (leave running)
cd backend
.venv\Scripts\celery.exe -A config worker --loglevel=info --pool=solo --concurrency=1 -Q default,gpu

# 5. Frontend, in a third terminal
cd frontend
npm run dev
```

`--pool=solo` is **mandatory on Windows** — the default prefork pool relies on `fork()` and will
hang. `-Q default,gpu` is required because match processing is dispatched to the `gpu` queue.

On Mac, swap `.venv\Scripts\python.exe` → `.venv/bin/python` and `.venv\Scripts\celery.exe` →
`.venv/bin/celery`, and drop `--pool=solo --concurrency=1` from the worker command — `fork()`
works fine there, so the default prefork pool is what you want.
</details>

## Development services

| Service | URL | Notes |
|---------|-----|-------|
| Django API | http://localhost:8000 | — |
| Django Admin | http://localhost:8000/admin | superuser |
| Frontend (Vite) | http://localhost:5173 | proxies `/api` to port 8000 |
| PostgreSQL | localhost:**5434** | `ft_user` / `ft_password` / `football_tracker` |
| Redis | localhost:6379 | broker on db 0, results on db 1 |
| Adminer | http://localhost:8080 | `-Adminer` flag; Server: `db` |

**Postgres is on host port 5434, not 5432** — `docker-compose.yml` remaps it to avoid clashing with
any local Postgres install. `DATABASE_URL` in `.env` must match.

Flower (Celery monitoring) is installed. It has no standalone executable — it registers as a Celery
subcommand:

```powershell
cd backend
.venv\Scripts\celery.exe -A config flower    # http://localhost:5555
```

---

## Python environment

**You do not need to activate the virtual environment.** Every command in this README and in
`start-local.ps1` calls the interpreter by full path (`.venv\Scripts\python.exe` on Windows,
`.venv/bin/python` on Mac; `.venv\Scripts\celery.exe` / `.venv/bin/celery`), which uses that venv
directly. Activation only puts the venv's binary directory on your `PATH`.

Activate it only if you want to type bare `python` / `celery`:

```powershell
# Windows
cd backend
.venv\Scripts\Activate.ps1
python manage.py runserver      # now resolves to the venv interpreter
deactivate

# Mac
cd backend
source .venv/bin/activate
python manage.py runserver
deactivate
```

### Dependency files

| File | Purpose |
|------|---------|
| `backend/requirements.txt` | Curated list of direct dependencies, versions matching the working venv |
| `backend/requirements.lock.txt` | `pip freeze` of the whole venv — exact rebuild, transitive deps included. It's a freeze of a Windows venv, so use `requirements.txt` on Mac instead and let pip resolve each package's own Mac wheel. |
| `cv_engine/requirements.txt` | Used only by `docker/Dockerfile.cv_engine`; not used by the local flow |

Rebuilding the environment from scratch (this is exactly what `start-local.ps1` does automatically
the first time it doesn't find `backend/.venv`):

```powershell
# Windows
cd backend
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt

# Mac
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Use `requirements.lock.txt` instead only when you want an exact, reproducible rebuild **on
Windows** — see the note in the table above for why it's not portable to Mac.

Two things to know about these files:

- **`torch` and `torchvision` are listed in `backend/requirements.txt`.** They previously were not,
  with a comment saying to install them separately for RunPod's CUDA version. That made the file
  unable to produce a working environment on its own. A plain `pip install` of the pinned versions
  gets you a working build on any platform: PyPI's default wheel on Windows and Mac only supports
  CPU (Mac has no CUDA at all), which is exactly what those machines need; on Linux the default
  wheel bundles CUDA support and transparently falls back to CPU when no GPU is present.
  `cv_engine/engine/device.py` picks CPU vs. CUDA at runtime either way — see
  [Hardware note](#hardware-note).
- **Keep these files ASCII-only.** pip on Windows decodes requirements files as cp1252, so a single
  non-ASCII character *anywhere* — including inside a comment — fails the whole file with a
  `UnicodeDecodeError`. Box-drawing characters in the header comments used to do exactly this, which
  is why the pinned versions drifted out of sync with the installed ones.

After changing dependencies, regenerate the lockfile:

```powershell
.venv\Scripts\python.exe -m pip freeze > requirements.lock.txt
```

---

## Testing the pipeline

```powershell
cd backend

# Smoke test - 21 frames, ~3 minutes. Proves the wiring.
.venv\Scripts\python.exe test_e2e.py clip_3min.mp4

# Real test - 90 frames with measured calibration, ~8 minutes.
.venv\Scripts\python.exe test_e2e.py wide_3s.mp4 cv_engine/engine/calibration_test5s.json
```

`test_e2e.py` takes an optional clip name and an optional calibration config. It creates a test
user and match, dispatches the task, polls until completion, and prints the results.

### Test clips

| File | Frames | fps | Runtime | Notes |
|------|--------|-----|---------|-------|
| `clip_3min.mp4` | 21 | 20 | ~3 min | Misnamed — it is a 1-second clip. Fastest smoke test |
| `wide_3s.mp4` | 90 | 25 | ~8 min | Wide shot, **no camera cuts**. The good test clip |
| `test_5s.mp4` | 125 | 25 | ~11 min | Contains a camera cut at frame 33 — kept as the cut example |
| `1new.mp4` | 300 | 25 | ~25 min | The 12-second original |

### Reading the result

`E2E Test PASSED!` only means the pipeline ran — it does not mean the data is sound. The script
prints four things specifically so you can judge that:

- **Coordinate spread** should sit well inside `0–105` / `0–68`. Values pinned at exactly `0.0` and
  `105.0` mean the clipping in `project_point()` is saturating and the homography does not match
  this footage.
- **Both `team_a` and `team_b` present.** Only one team means the classifier fit its two colour
  clusters during a stretch where only one team was visible.
- **Ball rows > 0.** Without them, no possession, pass, or shot event can fire at all.
- **No shot above 50 m/s and no sprint above 12.5 m/s.** Those ceilings exist precisely to reject
  tracking artifacts. If an impossible value appears, the worker is running stale code — restart it.

A known-good run against `wide_3s.mp4`:

```
Detected fps: 25.0
Pitch coordinate spread: x 25.2-90.5 (of 0-105), y 1.4-68.0 (of 0-68)
Team classifications present: ['ball', 'referee', 'team_a', 'team_b']
Ball rows (player_id=-1): 177
E2E Test PASSED!
```

---

## Two rules that will otherwise cost you an afternoon

### 1. Restart the Celery worker after changing code

**Celery does not reload changed code.** The worker holds imported modules for its whole lifetime,
so edits to `cv_engine/` or `backend/matches/` have no effect on a worker that was already running
— and you will misread stale behaviour as a fix that did not work.

```powershell
.\start-local.ps1 -Restart
```

### 2. Calibration is per camera position

Uploads made through the Dashboard carry **no calibration of their own**. Without one the extractor
falls back to a generic trapezoid rescaled to the clip's resolution — a guess at the camera angle,
and wrong for most footage. On the bundled test clip that guess puts the centre circle at pitch
y≈50 instead of y=34, so a kickoff renders with every player bunched along the bottom touchline.

Set `DEFAULT_CALIBRATION_PATH` in `.env` so uploads get a real homography:

```
DEFAULT_CALIBRATION_PATH=./cv_engine/engine/calibration_test5s.json
```

To override per clip, `POST /api/matches/` also accepts an optional `calibration_matrix` field
(the parsed contents of a `calibrate.py` config). Resolution order is:
**match's own `calibration_matrix` → `DEFAULT_CALIBRATION_PATH` → rescaled generic trapezoid.**


The homography maps image pixels to pitch metres, so it is only valid for the camera position it was
measured against. `cv_engine/engine/calibration_test5s.json` was measured for one specific wide
shot. New footage needs its own:

```powershell
.venv\Scripts\python.exe cv_engine/engine/calibrate.py `
  --points "323,177:52.5,0; 323,290:52.5,68; 248,230:43.35,34; 398,230:61.65,34" `
  --output cv_engine/engine/calibration_myclip.json
```

Each correspondence is `pixel_x,pixel_y:pitch_x,pitch_y`, at least four of them. Without `--points`
the script opens a click-to-calibrate GUI instead.

**Measuring the landmarks.** Extract a frame, overlay a grid in *native* resolution, and read off
features whose pitch coordinates you know exactly — the halfway line's intersections with both
touchlines (`52.5,0` and `52.5,68`) and the centre circle's left and right extremities
(`43.35,34` and `61.65,34`) work well and are spread far enough apart to condition the fit. Then
validate against landmarks you deliberately left *out* of the fit: the two points where the circle
crosses the halfway line (`52.5,24.85` and `52.5,43.15`). The bundled calibration validates at
0.14 m and 0.37 m error on those held-out points.

**Check for camera cuts first.** A single homography cannot describe two camera positions, and a cut
also produces enormous phantom speeds as everything appears to teleport:

```powershell
ffprobe -v error -f lavfi "movie=clip.mp4,select=gt(scene\,0.25)" -show_entries frame=pts_time -of csv=p=0
```

Any output means the clip cuts. Broadcast footage cuts constantly — for usable tracking data you
want a fixed tactical camera, or a segment trimmed to a single shot (which is what `wide_3s.mp4` is).

---

## Project documentation

See [`plans/explaination.md`](plans/explaination.md) for a component-by-component walkthrough.
[`runpod-setup.md`](runpod-setup.md) describes a GPU deployment on RunPod — it is **not** the
current setup and is kept only for reference.
