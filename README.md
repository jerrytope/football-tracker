# Football Tracker

> Automated football tracking platform — converts broadcast MP4 footage into
> structured X/Y player coordinate data with zero manual tagging.

## Architecture

```
frontend/        React/Vue tactical pitch viewer
backend/         Django + DRF REST API
cv_engine/       YOLOv8 + ByteTrack computer vision pipeline
docker/          Service Dockerfiles
docker-compose.yml  Local dev infrastructure (PostgreSQL, Redis, Adminer)
```

## Quick Start (Development)

### Prerequisites
- Docker Desktop installed and running
- Python 3.11
- Node.js 20+

### 1. Clone and configure environment
```bash
git clone <your-repo-url>
cd football-tracker
cp .env.example .env
# Edit .env with your values
```

### 2. Start infrastructure services
```bash
docker compose up -d
```
This starts:
- **PostgreSQL 15** on port `5432`
- **Redis 7** on port `6379`
- **Adminer** (DB inspector) on port `8080` → http://localhost:8080

### 3. Set up the Django backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
API available at: http://localhost:8000

### 4. Start the Celery worker (separate terminal)
```bash
cd backend
venv\Scripts\activate
celery -A config worker --loglevel=info -Q default,gpu
```

### 5. Set up the frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend at: http://localhost:5173

### 6. Set up the CV engine (requires GPU)
See [`cv_engine/README.md`](cv_engine/README.md) for GPU environment setup.

---

## Development Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Django API | http://localhost:8000 | — |
| Django Admin | http://localhost:8000/admin | superuser |
| React/Vue Frontend | http://localhost:5173 | — |
| Adminer (DB) | http://localhost:8080 | Server: `db`, User: `ft_user`, Pass: `ft_password` |
| Flower (Celery) | http://localhost:5555 | — |

---

## Project Status

See [`tasks.md`](../tasks.md) for the full task breakdown and current progress.
See [`plans/Implementation_Plan.md`](../plans/Implementation_Plan.md) for architecture details.
