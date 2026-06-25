# CV Engine — Docker Setup (CPU)

This pipeline runs inside Docker — **no local Python or GPU required**.
CPU inference is slower than GPU but fully functional for development and validation.

> **Performance expectations (CPU):**
> - 3-minute test clip: ~10–20 minutes to process
> - 90-minute full match: several hours (production will use a GPU worker)

---

## Prerequisites

- Docker Desktop running ✅
- The root `docker-compose.yml` services are up (`docker compose up -d`)
- A `.env` file exists at the project root (copy from `.env.example`)

---

## One-Time Setup: Build the Image

From the `football-tracker/` root directory:

```bash
docker compose build cv_engine
```

This installs CPU-only PyTorch, OpenCV, ultralytics, supervision, etc.
**This takes 5–10 minutes on first build.** Subsequent builds use the cache.

---

## How to Use the CV Container

The `cv_engine` service uses a Docker Compose **profile** (`cv`) so it doesn't
start automatically with `docker compose up -d`. You launch it on-demand only.

### Drop into an interactive shell
```bash
docker compose --profile cv run --rm cv_engine
```
You are now inside the container at `/app`. Your local `cv_engine/` source code
is mounted live — any edits you make locally are instantly visible inside.

### Run a specific script
```bash
docker compose --profile cv run --rm cv_engine \
  python cv_engine/validation/validate_output.py --video cv_engine/test_data/clip_3min.mp4
```

### Run the visualizer
```bash
docker compose --profile cv run --rm cv_engine \
  python cv_engine/validation/visualize_pitch.py --video cv_engine/test_data/clip_3min.mp4
```
Output PNGs are saved to `cv_engine/output/` on your local machine.

---

## Providing Input Files

### Test video clip
Place your 3-minute clip here (on your local machine):
```
football-tracker/cv_engine/test_data/clip_3min.mp4
```
It will be instantly available inside the container at:
```
/app/cv_engine/test_data/clip_3min.mp4
```

### YOLO weights
Place the downloaded `.pt` file here:
```
football-tracker/cv_engine/weights/yolov8x.pt
```
Weights are stored in a **named Docker volume** (`cv_weights`) so they persist
across container restarts without re-downloading.

---

## Directory Structure

```
cv_engine/
├── engine/              # Core AI pipeline modules
│   ├── extractor.py     # Main coordinate extraction generator
│   ├── calibrate.py     # Homography calibration helper
│   └── classifier.py    # K-Means team classification
├── validation/          # Output validation and debug scripts
│   ├── validate_output.py
│   └── visualize_pitch.py
├── tests/               # Unit tests
│   └── test_extractor.py
├── test_data/           # Local test video clips  ← put your clip here
├── weights/             # YOLO .pt weight files   ← put weights here
├── output/              # Validation PNGs land here (git-ignored)
├── requirements.txt
└── README.md
```

---

## Upgrading to GPU (Production)

When you are ready to run production-speed processing, switch the base image in
[`docker/Dockerfile.cv_engine`](../docker/Dockerfile.cv_engine):

```diff
-FROM python:3.11-slim
+FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime
```

And remove the explicit CPU torch install step. No other code changes needed.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `docker compose build cv_engine` fails on `ffmpeg` | Re-run; sometimes apt mirrors are slow |
| `torch.cuda.is_available()` returns False | Expected on CPU build — not an error |
| `No such file: clip_3min.mp4` | Make sure the file is in `cv_engine/test_data/` on your local machine |
| Inference is very slow | Normal for CPU. Reduce test clip to 30 seconds for rapid iteration |
