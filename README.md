# mBm NVR System

Centralized Network Video Recorder for managing multiple IP cameras (ONVIF, RTSP, Hikvision, Dahua, Axis, Reolink, etc.) with live monitoring, recording, AI object detection, and motion detection.

> NVR is developed with **mBm AI Assistant** — an AI-powered engineering and operations assistant by [mBm TECHNOLOGY LLC](https://mbm.mn) that handles rapid coding, server management, deployments, and full-stack troubleshooting.
>
> Powered by **DeepSeek V4 Pro** model.
>
> Try it at: **[console.mbm.mn](https://console.mbm.mn)**

## Features

- **Live Monitoring** — Real-time HLS streaming with sub-stream support for bandwidth-efficient dashboard previews
- **Recording** — Continuous and event-based recording with configurable retention policies
- **AI Object Detection** — YOLO-based detection pipeline for people, vehicles, and other objects
- **Motion Detection** — Camera-side and server-side motion detection
- **IP Camera Discovery** — Auto-discover ONVIF/RTSP cameras on local subnets
- **PTZ Control** — Pan, tilt, and zoom control for supported cameras
- **Multi-User** — Role-based access (admin, operator, viewer)
- **Locations** — Organize cameras by physical location
- **Backup & Restore** — Encrypted backup scripts for database and configuration

## Architecture

| Service | Role |
|---------|------|
| `nvr-api` | FastAPI backend — camera management, live relay orchestration, REST API |
| `nvr-web` | React + Vite frontend — dashboard, live view, settings |
| `nvr-db` | TimescaleDB (PostgreSQL) — time-series recording storage |
| `nvr-redis` | Redis — job queue, caching, WebSocket pub/sub |
| `nvr-minio` | MinIO (S3-compatible) — recording clip storage |
| `nvr-mediamtx` | MediaMTX — RTSP relay input, HLS output for browsers |
| `nvr-nginx` | Reverse proxy — routes `/api`, `/hls`, `/ws` to appropriate services |
| `nvr-recording-engine` | Recording scheduler and segment writer |
| `nvr-ai-engine` | YOLO-based object detection pipeline |
| `nvr-mqtt-bridge` | MQTT integration for external event consumption |

## Quick Start

### Prerequisites

- Docker & Docker Compose (v2.22+)
- Make
- FFmpeg (for local development)

### Setup

```bash
# 1. Copy environment template and edit
cp .env.example .env
# Edit .env with your configuration (database passwords, secrets, camera credentials)

# 2. Start all services
docker compose up -d

# 3. Apply database migrations
make seed

# 4. Access the web UI
open http://localhost:3000
```

### Development

```bash
# Start infrastructure services only (DB, Redis, MinIO, MediaMTX)
make infra

# Seed database with initial schema
make seed

# Run API in dev mode with hot-reload
make dev

# Run web frontend in dev mode
make web
```

### Environment Variables

Key configuration variables (see `.env.example` for the full list):

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | Database password |
| `JWT_SECRET_KEY` | Secret key for JWT token signing |
| `MEDIAMTX_RTSP` | MediaMTX RTSP endpoint (default: `rtsp://host.docker.internal:8554`) |
| `MEDIAMTX_HLS_URL` | MediaMTX HLS endpoint (default: `http://host.docker.internal:8888`) |
| `NVR_ENCRYPTION_KEY` | Key for encrypting camera passwords at rest |

## API

The REST API is available at `/api/v1/`. Key endpoints:

- `GET /api/v1/cameras` — List all cameras
- `POST /api/v1/cameras` — Add a camera
- `POST /api/v1/cameras/{id}/live/start` — Start a live relay stream
- `POST /api/v1/cameras/discover` — Discover cameras on local subnets
- `POST /api/v1/cameras/{id}/test` — Test camera connection
- `GET /api/v1/locations` — List locations
- `GET /api/v1/recordings` — Query recorded clips

## License

Apache-2.0
