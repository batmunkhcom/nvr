# mBm NVR System

Centralized Network Video Recorder for managing IP cameras (ONVIF, RTSP, Hikvision, Dahua, Axis, Reolink) with live monitoring, motion-triggered recording, AI object detection, and network health monitoring.

> Built with **mBm AI Assistant** — an AI-powered engineering and operations assistant by [mBm TECHNOLOGY LLC](https://mbm.mn).

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/batmunkhcom/nvr/main/install.sh | bash
```

One command. Everything handled — Docker build, DB setup, admin user, all services started.

| Mode | Command |
|------|---------|
| **Interactive** (asks DB, admin, ports, path) | `curl -fsSL https://raw.githubusercontent.com/batmunkhcom/nvr/main/install.sh \| bash` |
| **Auto** (random passwords, printed at end) | `curl -fsSL https://raw.githubusercontent.com/batmunkhcom/nvr/main/install.sh \| bash -s -- --no-prompt` |
| **Custom path** | `INSTALL_DIR=/opt/nvr curl -fsSL https://raw.githubusercontent.com/batmunkhcom/nvr/main/install.sh \| bash` |

**Prerequisites:** Docker 20.10+, Docker Compose v2.22+, Git, curl. Linux x86_64. 4 CPU / 8 GB RAM / 20 GB disk minimum.

After install:

```
Web UI:      http://localhost:3000          Username:  admin
API Docs:    http://localhost:8000/docs      Password:  admin  (change immediately)
```

---

## Features

### Live Monitoring
- **LL-HLS streaming** with 1–3 second glass-to-glass latency
- **Sub-stream support** for bandwidth-efficient dashboard multi-camera previews
- **Idle stream reaper** — relays with zero viewers stop automatically after 10 minutes, saving CPU
- **Audio playback** — listen to camera audio during live view
- **Digital zoom** — 2D CSS zoom+pan on any stream
- **PTZ controls** — pan, tilt, zoom for supported cameras (ONVIF + vendor-specific)

### Recording
- **Motion-triggered recording** — FFmpeg starts when motion detected, stops after configurable idle delay (30s)
- **Continuous recording** mode also available per camera
- **5-minute MP4 segments** with `-c:v copy` (zero video re-encode, minimal CPU)
- **Codec normalization** — HEVC→H.264 transcode (`libx264 ultrafast crf20`), H.264 bitstream filter (`video_full_range_flag=0`) for universal browser compatibility. Auto-detected via ffprobe before FFmpeg spawns.
- **Circular retention** — disk watermark at 85% or <2GB free triggers oldest segment deletion first. Disk can never fill up.
- **Age-based retention** — configurable retention days (default 7)
- **GB/day analytics** — per-camera usage rates, capacity projection (days remaining)
- **Recording playback** — browser-native `<video>` with progressive download, HTTP Range support (206 Partial Content for seeking), speed controls (0.125x–8x with slow/fast color coding), mute toggle, download button
- **Thumbnails** — auto-generated sidecar JPEG per recording segment, ffmpeg thumbnail extraction with time-offset fallback
- **Bulk delete** — by ID list, all per camera, or before a specific date
- **Timeline view** — per-day segment bar chart, click to jump to moment
- **Stream selection** — per-camera `recording.stream` config (sub-stream ~700kbps / main-stream full resolution)
- **Scheduled recording** — day-of-week + time range schedules per camera

### AI Object Detection
- **YOLOv8n ONNX** inference on sub-stream frames (shared singleton session, CPUExecutionProvider)
- **MOG2 motion gate** — frames pass YOLO only when motion is detected (history=800, morphological close, threshold-based sensitivity). Saves ~80% CPU.
- **Configurable per camera** — object classes (80 COCO classes: person, car, truck, bus, motorcycle, bicycle, etc.), confidence threshold (clamped 0.05–0.95), sensitivity (low/medium/high)
- **Zone-based filtering** — draw polygon zones on camera snapshot; only objects whose bottom-center falls inside a zone trigger events. Empty zones = whole frame.
- **Position-aware deduplication** — static object = 1 event per 5 minutes (`STATIC_COOLDOWN_S`); moved object (>0.10 normalized distance) = immediate event. Minimum gap of 5s between same-class events (`MIN_EVENT_GAP_S`).
- **JPEG snapshots** saved with each detection event (token-authenticated)
- **Events feed** with object badges, snapshot thumbnails, camera filter, severity levels, acknowledge action
- **Motion-only mode** — cameras with `recording_mode='motion'` and `ai_enabled=False` get motion-only sampler (MOG2 gate, no YOLO) that publishes to Redis `nvr:motion`
- **Plugin architecture** — extendable AI analytics via per-camera plugin system
- **Object counter** — real-time person, vehicle, animal, livestock counting with hourly aggregation
- **License Plate Recognition (LPR)** — EasyOCR-based plate detection with 8 country pattern library (Монгол, Европ, АНУ, Япон, Хятад, Орос, Солонгос + custom regex)
- **Smart alerts** — time-based, frequency-based, and zone-violation alert rules per camera

### Network Monitoring
- **Real-time bandwidth** — inbound (RTSP) and outbound (FFmpeg relay) Mbps per camera
- **Latency monitoring** — ICMP RTT, jitter
- **Packet loss tracking**
- **Linear charts** with time-range selector (1h/6h/12h/24h/7d)
- **Multi-camera overlay** — all cameras on single chart with color-coded lines
- **Location-based filtering**
- **Alert thresholds** with configurable warning/critical levels

### Camera Management
- **6-phase auto-discovery** — ONVIF (WS-Discovery), RTSP (port scan + DESCRIBE/OPTIONS), HTTP (vendor paths), ARP (MAC OUI), mDNS (_onvif._tcp), vendor broadcast (Hikvision/Dahua UDP)
- **Connection testing** — single TCP connection for Dahua digest auth (nonce binding)
- **Auto-health-check** background loop with configurable interval
- **Locations** — organize cameras by physical location (Building, Floor, Entrance, etc.)
- **Dashboard** — configurable 1/2/3/4 column grid with drag-and-drop, persisted in DB

### Security & Multi-User
- **JWT authentication** — access (24h) + refresh (7d) tokens, Redis blacklist for revoked tokens
- **RBAC** — admin, operator, viewer roles. Enforced via FastAPI dependency injection (`require_admin`, `require_operator`).
- **Camera passwords encrypted at rest** (AES-256-GCM, shared `nvr_common.security` module). Decrypted in-memory only when FFmpeg spawns.
- **Media auth** — `?token=` query parameter passes through `get_current_user` for `<img>/<video>` tags
- **API keys** — bcrypt hashed, prefix-identifiable (`nvr_a3f2...`), permission-scoped, expirable

### System
- **Settings page** — all system_config values editable via UI (storage, recording, AI, network, UI categories)
- **User profile** — password change, username display
- **PWA support** — installable, offline AppShell cache
- **Backup & restore** — encrypted pg_dump + config backup scripts (AES-256-CBC)
- **Docker log rotation** — `max-size: 10m, max-file: 3` on all 8 services
- **Scheduled recording** — day-of-week + time range schedules per camera
- **Real-time WebSocket** — `/api/v1/ws` pushes camera status, events, and network metrics to all connected clients
- **Prometheus metrics** — `/metrics` endpoint on API server

### Browser Compatibility

| Feature | Chrome | Safari | Firefox |
|---------|--------|--------|---------|
| Live HLS (LL-HLS) | ✅ hls.js | ✅ hls.js | ✅ hls.js |
| Recording MP4 playback | ✅ Progressive `<video>` | ✅ Progressive `<video>` | ✅ Progressive `<video>` |
| CSP `script-src` enforcement | ⚠️ Strict (blocks `new Function()`) | Lenient | Moderate |
| `Range: bytes=0-` handling | Requires `206 Partial Content` | Accepts `200 OK` | Accepts `200 OK` |
| `pix_fmt=yuvj420p` full-range | ❌ Rejects | ✅ Accepts | ❌ Rejects |

**Design decisions for universal compatibility:**
1. RecordingPlayer uses progressive MP4 download (NO hls.js) — avoids CSP `unsafe-eval` conflict
2. Recording engine normalizes all codecs to H.264 `yuv420p` `color_range=tv` — Chrome-safe format
3. Stream endpoint returns `200 OK` for full-file requests, `206 Partial Content` for seeking — satisfies Chrome's strict Range handling

### Performance & Efficiency

| Metric | Value |
|--------|-------|
| CPUs / Memory | 4 cores / 8 GB (actual deployment) |
| AI CPU (10 cameras, 0.5 FPS) | ~74% (down from 166% after tuning) |
| AI RAM (shared ONNX session) | ~565 MB (down from 955 MB) |
| Stream relay FFmpeg (11 cameras) | ~11 × 1 cpu-core each, 1000k bitrate |
| Recording FFmpeg (`-c:v copy`) | Negligible CPU (zero video encode) |
| Idle reaper savings | ~0 CPU when nobody watches |
| Motion-only recording | 5-8 GB/day (vs 26 GB/day continuous) |
| LL-HLS latency | 1-3 seconds glass-to-glass |

---

## Architecture

### Service Topology

```
┌──────────────┐     RTSP sub     ┌───────────────┐     Redis     ┌──────────────────┐
│  IP Cameras  │─────────────────→│  AI Engine     │─────────────→│ Redis Pub/Sub    │
│  (11× Dahua) │                  │  YOLOv8n ONNX  │  motion,     │ nvr:motion       │
│              │                  │  MOG2 gate     │  events      │ nvr:events       │
└──────┬───────┘                  └───────────────┘              └────────┬─────────┘
       │                                                                  │
       │ RTSP sub                                                         │
       ▼                                                                  ▼
┌──────────────────┐     RTSP libx264    ┌──────────────┐     HLS     ┌──────────┐
│ Stream Manager   │───────────────────→│  MediaMTX    │───────────→│  Browser │
│ FFmpeg relays    │                    │  RTSP server │  LL-HLS    │  hls.js  │
│ (11× transcode)  │                    │  HLS server  │            │          │
└──────────────────┘                    └──────────────┘            └──────────┘
                                                │                        ▲
                                                │ RTSP                   │
┌──────────────────┐                            ▼                        │
│ Recording Engine │     RTSP -c:v copy    ┌──────────────┐    HTTP    ┌──────────┐
│ Per-camera FFmpeg│─────────────────────→│  Disk        │──Range───→│ FastAPI  │
│ Motion controller│     300s segments    │ /data/record │           │ API      │
│ Circular retention│                     └──────────────┘           └──────────┘
│ Segment catalog  │
│ Disk analytics   │
└──────────────────┘
```

### Services

| Service | Container | Role |
|---------|-----------|------|
| **API** | `nvr-api` | FastAPI backend — REST API, auth, camera management, live relay orchestration |
| **Web** | `nvr-web` | React + Vite + TypeScript frontend — dashboard, live view, settings |
| **Stream Manager** | `nvr-stream-manager` | FFmpeg relay lifecycle — transcodes RTSP sub-stream→libx264→MediaMTX, circuit breaker, idle reaper |
| **MediaMTX** | `nvr-mediamtx` | RTSP server + LL-HLS origin — receives transcoded streams, serves HLS to browsers |
| **Recording Engine** | `nvr-recording-engine` | Per-camera FFmpeg `-c:v copy` supervisors, motion controller, circular retention, segment catalog, disk analytics |
| **AI Engine** | `nvr-ai-engine` | YOLOv8n ONNX detection, MOG2 motion gate, event generation, Redis pub/sub |
| **Database** | `nvr-db` | PostgreSQL 16 — cameras, recordings, events, users, system_config |
| **Cache / PubSub** | `nvr-redis` | Redis 7 — WebSocket pub/sub, motion state, event broadcast |

Not actively used (disabled in current deploy): `nvr-mosquitto` (MQTT), `nvr-chrony` (NTP), `nvr-mqtt-bridge`, `nvr-nginx`.

### Key Data Flows

#### Live Stream
1. Frontend calls `POST /api/v1/cameras/{id}/live/start?stream=sub`
2. API delegates to stream-manager via HTTP (`http://nvr-stream-manager:8001`)
3. Stream-manager spawns FFmpeg: `rtsp://camera_sub → libx264 → rtsp://nvr-mediamtx:8554/{id}_sub`
4. MediaMTX creates LL-HLS at `/hls/{id}_sub/`
5. Frontend polls manifest → initializes hls.js → plays in `<video>`

#### Motion-Only Recording
1. AI Engine publishes `{camera_id, active}` to Redis `nvr:motion` (on change + 30s heartbeat)
2. Recording Engine `MotionRecorderController`: motion active → start FFmpeg recorder
3. Motion inactive for 30s (`recording.motion_stop_delay_s`) → stop recorder
4. New motion cancels pending stop
5. Segments marked `recording_type='motion'` by catalog

#### AI Detection
1. FrameSampler connects to camera RTSP sub-stream at 0.5 FPS
2. MOG2 background subtraction → if motion, pass frame to YOLO
3. YOLOv8n ONNX inference → bounding boxes + class labels
4. Zone filter (point-in-polygon) + confidence threshold
5. Position-aware dedup: static = 1 event/5min, moved = immediate
6. Event + JPEG snapshot → DB + Redis pub

#### Circular Retention
1. Every 5 minutes: check disk usage vs `storage.max_usage_percent` (85%) and `storage.min_free_gb` (2GB)
2. If threshold exceeded → delete oldest segments first (files < 10min protected)
3. Also age-based: delete segments older than `retention.default_days` (7 days)
4. DB rows for deleted files cleaned up
5. Max 500 deletions per run (I/O storm prevention)

---

## Development

```bash
# Start infrastructure only
make infra
# Or: docker compose up -d nvr-db nvr-redis nvr-mediamtx

# Seed DB
make seed

# Run API with hot-reload
make dev
# Or: cd services/api && uvicorn app.main:app --reload

# Run web frontend
make web
# Or: cd services/web && npm run dev
```

### Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password | (required) |
| `JWT_SECRET_KEY` | JWT signing secret | (required) |
| `NVR_ENCRYPTION_KEY` | AES-256-GCM key for camera passwords | (required) |
| `MEDIAMTX_RTSP` | MediaMTX RTSP endpoint | `rtsp://nvr-mediamtx:8554` |
| `MEDIAMTX_HLS_URL` | MediaMTX HLS origin | `http://10.10.0.229:8888` |
| `STREAM_MANAGER_URL` | Stream manager HTTP | `http://nvr-stream-manager:8001` |
| `STREAM_IDLE_TIMEOUT_S` | Idle reaper timeout | `600` (10 min) |
| `AI_MODEL_PATH` | ONNX model directory | `/app/models` |
| `AI_YOLO_MODEL` | ONNX model filename | `yolov8n.onnx` |
| `AI_DEVICE` | ONNX provider | `cpu` |

---

## API

All endpoints under `/api/v1/`. Responses wrapped in `{"data": ...}`.

```
POST   /api/v1/auth/login                    # JWT login
POST   /api/v1/auth/refresh                  # Token refresh

GET    /api/v1/cameras                       # List cameras (paginated, filtered)
POST   /api/v1/cameras                       # Add camera
GET    /api/v1/cameras/{id}                  # Get camera details
PATCH  /api/v1/cameras/{id}                  # Update camera
DELETE /api/v1/cameras/{id}                  # Delete camera
POST   /api/v1/cameras/{id}/test             # Test connection
POST   /api/v1/cameras/{id}/live/start       # Start live relay (stream=main|sub)
POST   /api/v1/cameras/{id}/live/stop        # Stop live relay
GET    /api/v1/cameras/{id}/live/status      # Relay status
POST   /api/v1/cameras/{id}/ptz              # PTZ control
POST   /api/v1/cameras/discover              # Start discovery scan
GET    /api/v1/cameras/discover/{id}/status  # Scan status

GET    /api/v1/recordings                    # List recordings (paginated, filtered)
GET    /api/v1/recordings/{id}               # Get recording details
GET    /api/v1/recordings/{id}/stream        # Stream recording (HTTP Range)
GET    /api/v1/recordings/{id}/thumbnail     # Get thumbnail JPEG
POST   /api/v1/recordings/bulk-delete        # Bulk delete
GET    /api/v1/recordings/timeline           # Per-day timeline

GET    /api/v1/events                        # List events (paginated, filtered)
GET    /api/v1/events/{id}                   # Get event details
GET    /api/v1/events/{id}/snapshot          # Get event snapshot
PATCH  /api/v1/events/{id}/acknowledge       # Acknowledge event
WS     /api/v1/events/stream                 # Real-time event WebSocket

GET    /api/v1/network/metrics               # Latest metrics all cameras
GET    /api/v1/network/metrics/{id}          # Latest metrics one camera
GET    /api/v1/network/metrics/{id}/history  # Historical metrics
GET    /api/v1/network/summary               # Dashboard summary stats

GET    /api/v1/storage/usage                 # Storage usage
GET    /api/v1/locations                     # List locations (CRUD)
GET    /api/v1/users                         # List users (admin CRUD)
GET    /api/v1/system/health                 # System health
GET    /api/v1/system/config                 # System config
PATCH  /api/v1/system/config                 # Update config

WS     /api/v1/ws                            # Camera status + events WebSocket

GET    /api/v1/counters/summary              # Object counter summary (?camera_id=&days=7)
GET    /api/v1/counters/hourly               # Hourly breakdown (?camera_id=&date=YYYY-MM-DD)

GET    /api/v1/lpr/patterns                  # LPR country pattern library
GET    /api/v1/lpr/readings                  # License plate readings (?camera_id=&plate_number=&days=7)
```

---

## Project Structure

```
nvr/
├── services/
│   ├── api/                  # FastAPI backend
│   │   ├── app/
│   │   │   ├── api/v1/       # Route handlers (14 routers)
│   │   │   ├── core/         # Config, security, database
│   │   │   ├── models/       # SQLAlchemy models
│   │   │   ├── schemas/      # Pydantic schemas
│   │   │   └── services/     # Business logic
│   │   ├── alembic/          # DB migrations (9 versions)
│   │   └── tests/            # pytest (64 tests)
│   ├── web/                  # React + Vite frontend
│   │   ├── src/
│   │   │   ├── components/   # UI components
│   │   │   ├── hooks/        # React hooks (TanStack Query)
│   │   │   ├── pages/        # Route pages
│   │   │   ├── store/        # Zustand state
│   │   │   └── api/          # API client + endpoints
│   │   └── src/test/         # vitest (34 tests)
│   ├── stream-manager/       # FFmpeg relay lifecycle
│   ├── recording-engine/     # Recording supervisor + retention
│   └── ai-engine/            # YOLOv8 ONNX detection
├── packages/
│   └── common/               # Shared Python utilities
│       └── nvr_common/
│           ├── security.py   # AES-256-GCM encryption
│           └── circuit_breaker.py
├── config/                   # MediaMTX, vendor patterns, defaults
├── docker/                   # Dockerfiles (7 services)
├── docker-compose.yml        # Service definitions (12 services)
├── docker-compose.prod.yml   # Production overrides
├── Makefile                  # Shortcut commands (27 targets)
├── scripts/                  # Bootstrap, backup, restore
└── docs/                     # Documentation
```

---

## Docker Networking

All services communicate via `nvr-net` Docker network using container hostnames:

| Hostname | Port | Service |
|----------|------|---------|
| `nvr-db` | 5432 | PostgreSQL |
| `nvr-redis` | 6379 | Redis |
| `nvr-mediamtx` | 8554, 8888, 9997 | RTSP, HLS, API |
| `nvr-stream-manager` | 8001 | HTTP API |
| `nvr-api` | 8000 | FastAPI |
| `nvr-web` | 3000 | React dev server |

---

## License

Apache-2.0 — see [LICENSE](LICENSE)
