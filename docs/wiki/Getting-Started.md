# Getting Started

## Prerequisites

- Docker & Docker Compose v2.22+
- Python 3.13 (for scripts/seed_db.py)
- FFmpeg 5.x+ (included in stream-manager container)
- 4 CPU cores, 8 GB RAM (actual deployment specs)

## Setup

### 1. Clone and Configure

```bash
# Copy environment template
cp .env.example .env

# Edit .env — set required values:
#   POSTGRES_PASSWORD      — database password (set a strong password)
#   JWT_SECRET_KEY         — JWT signing secret (generate random key)
#   NVR_ENCRYPTION_KEY     — AES-256-GCM key for camera passwords (generate random key)
```

### 2. Start Infrastructure

```bash
# Start DB + Redis only
docker compose up -d nvr-db nvr-redis

# Or start everything
make infra
```

### 3. Seed Database

```bash
make seed
# Or: python3 scripts/seed_db.py
```

This creates the admin user and default system configuration.

### 4. Start All Services

```bash
docker compose up -d
```

### 5. Access Web UI

```
http://localhost:3000
Default login: <username> / <password> (change after first login)
```

---

## Development

```bash
# Start infrastructure only
make infra

# Seed DB
make seed

# Run API with hot-reload
make dev
# Or: cd services/api && uvicorn app.main:app --reload

# Run web frontend
make web
# Or: cd services/web && npm run dev
```

---

## Docker Networking

All services use `nvr-net` Docker network. Container hostnames (not IPs):

| Hostname | Port | Service |
|----------|------|---------|
| `nvr-db` | 5432 | PostgreSQL |
| `nvr-redis` | 6379 | Redis |
| `nvr-mediamtx` | 8554, 8888, 9997 | RTSP, HLS, API |
| `nvr-stream-manager` | 8001 | HTTP API |
| `nvr-api` | 8000 | FastAPI |
| `nvr-web` | 3000 | React dev server |

---

## Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password | (required) |
| `JWT_SECRET_KEY` | JWT signing secret | (required) |
| `NVR_ENCRYPTION_KEY` | AES-256-GCM key for camera passwords | (required) |
| `STORAGE_LOCAL_PATH` | Container path for recordings | `/data/recordings` |
| `STORAGE_HOST_PATH` | Host path bind-mounted to container | `/data` |
| `MEDIAMTX_RTSP` | MediaMTX RTSP endpoint | `rtsp://nvr-mediamtx:8554` |
| `MEDIAMTX_HLS_URL` | MediaMTX HLS origin | (configure in .env) |
| `STREAM_MANAGER_URL` | Stream manager HTTP | `http://nvr-stream-manager:8001` |
| `STREAM_IDLE_TIMEOUT_S` | Idle reaper timeout | `600` (10 min) |
| `AI_MODEL_PATH` | ONNX model directory | `/app/models` |
| `AI_YOLO_MODEL` | ONNX model filename | `yolov8n.onnx` |
| `AI_DEVICE` | ONNX provider | `cpu` |

---

## Backup & Restore

```bash
# Backup (encrypted)
./scripts/backup.sh

# Restore
./scripts/restore.sh <backup-file>
```

Backups use AES-256-CBC encryption. SHA256 checksums stored separately.
