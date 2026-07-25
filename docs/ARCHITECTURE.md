# NVR System Architecture

> Reflects actual deployed state as of 2026-07-25 (v0.01.15).

---

## Service Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Docker Compose (nvr-net)                        │
│                                                                          │
│  ┌──────────┐   RTSP sub     ┌─────────────────┐                        │
│  │ IP Cams  │───────────────→│  AI Engine       │   Redis pub/sub       │
│  │ (11×     │                │  YOLOv8n ONNX    │──────────────────┐    │
│  │  Dahua)  │                │  FrameSampler    │  nvr:motion       │    │
│  │          │                │  MOG2 gate       │  nvr:events       │    │
│  └────┬─────┘                └─────────────────┘                   │    │
│       │                                                             │    │
│       │ RTSP sub                  ┌──────────────┐                  ▼    │
│       ├──────────────────────────→│ Stream Mgr   │    ┌────────────────┐ │
│       │                           │ FFmpeg relay │    │ Redis          │ │
│       │                           │ libx264      │    │ pub/sub/cache  │ │
│       │                           │ circuit brkr │    └────────┬───────┘ │
│       │                           └──────┬───────┘             │         │
│       │                                  │ RTSP libx264         │         │
│       │                                  ▼                      │         │
│       │                           ┌──────────────┐             │         │
│       │                           │ MediaMTX     │             │         │
│       │                           │ LL-HLS       │             │         │
│       │                           │ RTSP→HLS     │             │         │
│       │                           └──────┬───────┘             │         │
│       │                                  │ HLS                  │         │
│       │                                  ▼                      │         │
│       │                           ┌──────────────┐             │         │
│       │                           │ Browser      │             │         │
│       │                           │ hls.js       │             │         │
│       │                           └──────────────┘             │         │
│       │                                                         │         │
│       │ RTSP sub             ┌──────────────────┐               │         │
│       ├─────────────────────→│ Recording Engine │←─────────────┘         │
│       │                      │ -c:v copy FFmpeg │  motion trigger        │
│       │                      │ 300s MP4 segs    │                        │
│       │                      │ MotionRecorder   │                        │
│       │                      │ SegmentCatalog   │                        │
│       │                      │ CircularRetention│                        │
│       │                      │ DiskAnalytics    │                        │
│       │                      └────────┬─────────┘                        │
│       │                               │                                  │
│       │                               ▼                                  │
│       │                      ┌──────────────────┐                        │
│       │                      │ Disk             │                        │
│       │                      │ /data/recordings │                        │
│       │                      └────────┬─────────┘                        │
│       │                               │ HTTP Range                       │
│       │                               ▼                                  │
│       │                      ┌──────────────────┐                        │
│  ┌────┴──────────────────────│ FastAPI (nvr-api)│                        │
│  │                            │ REST + WS        │                        │
│  │                            └────────┬─────────┘                        │
│  │                                     │ SQL                             │
│  │                                     ▼                                 │
│  │                            ┌──────────────────┐                        │
│  │                            │ PostgreSQL 16    │                        │
│  │                            │ (nvr-db)         │                        │
│  │                            └──────────────────┘                        │
│  └── cameras table, recordings, events, system_config                    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Containers

| Container | Image | CPU Limit | Memory Limit | Ports |
|-----------|-------|-----------|--------------|-------|
| `nvr-db` | timescale/timescaledb:2.16-pg16 | 2 | 2G | 5432 |
| `nvr-redis` | redis:7-alpine | — | — | 6379 |
| `nvr-api` | python:3.13-slim | 1 | 1G | 8000 |
| `nvr-web` | node:22-slim (Vite dev) | — | — | 3000 |
| `nvr-stream-manager` | python:3.13-slim (+FFmpeg 5.1) | 4 | 4G | 8001 |
| `nvr-mediamtx` | bluenviron/mediamtx:1.19.2 | — | — | 8554, 8888, 9997 |
| `nvr-recording-engine` | python:3.13-slim (+FFmpeg 5.1) | 2 | 2G | — |
| `nvr-ai-engine` | python:3.13-slim (+ONNX) | 2 | 4G | — |

## Database Schema

### Core Tables

```
cameras ───────────┐
  id (UUID PK)     │
  name, ip_address  │
  stream_main_uri   │
  stream_sub_uri    │
  encrypted_password│
  recording_mode    │── motion / continuous / never / disabled
  ai_enabled        │
  ai_objects        │── JSON: ["person","car",...]
  ai_zones          │── JSON: [{"name":"...","points":[...]}]
  ai_sensitivity    │── low / medium / high
  ai_min_confidence │── 0.05–0.95
  motion_source     │── server / camera (ONVIF)
  status            │── online / offline / degraded / unknown
  connection_error  │
  location_id ←─────┤
                    │
locations ──────────┘
  id, name, description, color

recordings ─────────┐
  id (UUID)         │
  camera_id ←───────┘
  file_path
  file_size_bytes
  duration_seconds
  start_time, end_time
  recording_type ──── continuous / motion / event
  has_audio, codec, resolution
  is_corrupt
  storage_backend_id

events ──────────────┐
  id (UUID)          │
  camera_id ←────────┘
  event_type ──────── motion_detected / object_detected / person_detected / ...
  severity ────────── info / warning / critical
  start_time, end_time
  metadata ────────── JSON: {objects: [{label, confidence, box}], zone_id, ...}
  snapshot_path
  is_acknowledged

system_config
  key (VARCHAR PK), value (JSONB), description, updated_at

users
  id, username, hashed_password, role (admin/operator/viewer), is_active

api_keys
  id, user_id, name, key_hash, key_prefix, permissions[], expires_at

network_metrics
  id, camera_id, recorded_at, inbound_mbps, outbound_mbps
  rtt_ms, jitter_ms, packet_loss_pct, fps_current, bitrate_current

network_alerts
  id, camera_id, alert_type, severity, message, triggered_at
  acknowledged_at, resolved_at, metadata

camera_network_config
  camera_id (PK), poll_interval, ping_enabled, thresholds
```

### System Config Keys (operational tuning)

| Key | Default | Description |
|-----|---------|-------------|
| `storage.max_usage_percent` | `85` | Disk % at which circular cleanup triggers |
| `storage.min_free_gb` | `2` | Free GB floor for circular cleanup |
| `storage.analysis` | (computed) | Hourly GB/day + days-fit analytics |
| `recording.segment_seconds` | `300` | MP4 segment duration |
| `recording.stream` | `sub` | Which stream to record (sub/main) |
| `recording.motion_stop_delay_s` | `30` | Idle seconds before stopping motion recorder |
| `retention.default_days` | `7` | Age-based deletion threshold |
| `ai.enabled` | `false` | Global AI toggle |
| `ai.confidence_threshold` | `0.5` | Per-camera default (overridden by `ai_min_confidence`) |
| `ui.dashboard_columns` | `2` | Grid column count (persisted per user) |
| `ui.sidebar_collapsed` | `false` | Sidebar state |

---

## FFmpeg Pipelines

### Stream Relay (Stream Manager → MediaMTX)

```
ffmpeg -rtsp_transport tcp -timeout 10000000 \
  -i rtsp://admin:pass@camera:554/Streaming/Channels/102 \
  -c:v libx264 -preset ultrafast -tune zerolatency -g 5 \
  -b:v 1000k -maxrate 1000k -bufsize 2000k \
  -c:a aac -b:a 64k -ac 1 -pkt_size 1200 \
  -f rtsp -rtsp_transport tcp \
  rtsp://nvr-mediamtx:8554/{camera_id}_sub
```

**Notes:**
- Always `libx264` transcode (H.264 FU-A packet ordering from Dahua cameras causes MediaMTX HLS errors with `-c:v copy`)
- Sub-stream bitrate: 1000k (was 2000k, reduced for CPU savings)
- Main-stream bitrate: 4000k
- GOP 5 (ultra-short for LL-HLS)
- Circuit breaker: 15s→120s cooldown; `returncode=0` (clean exit) bypasses breaker
- Idle reaper: stops relay after `STREAM_IDLE_TIMEOUT_S` (600s) with zero MediaMTX readers

### Recording Engine (Direct to Disk)

```
ffmpeg -rtsp_transport tcp -timeout 15000000 \
  -i rtsp://admin:pass@camera:554/Streaming/Channels/102 \
  -c:v copy \                              # Zero video CPU
  -c:a aac -b:a 64k \                      # Lightweight audio re-encode
  -f segment -segment_format mp4 \
  -segment_format_options movflags=+faststart \
  -segment_time 300 -segment_atclocktime 1 \
  -reset_timestamps 1 -strftime 1 \
  /data/recordings/{camera_id}/%Y/%m/%d/%Y%m%d_%H%M%S.mp4
```

**Notes:**
- `-c:v copy` — no video transcode (very low CPU)
- 300s segments with `+faststart` (enables seeking before download complete)
- Motion-only mode: FFmpeg starts/stops based on Redis `nvr:motion` state
- Circuit breaker: 60s→600s cooldown

---

## AI Pipeline

```
RTSP Sub-stream (0.5 FPS, 640px width)
         │
         ▼
┌───────────────────┐
│  FrameSampler     │  OpenCV cap.read()
│  per camera       │  cv2.CAP_PROP_BUFFERSIZE=1 (minimal latency)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  MOG2 Motion Gate │  history=500, detectShadows=False
│  (OpenCV)         │  countNonZero > 500 pixels → motion
│                   │  Threshold: low=40, med=25, high=16
└────────┬──────────┘
         │ motion detected
         ▼
┌───────────────────┐
│  YOLOv8n ONNX     │  Shared singleton session
│  (ONNX Runtime)   │  Intra-op threads: 1
│  INPUT_SIZE=640   │  CPUExecutionProvider
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Post-processing  │  Transpose (1,84,8400) → per-class argmax
│                   │  NMS (IoU=0.45), confidence clamp [0.05, 0.95]
│  Letterbox unscale│
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Zone Filter      │  cv2.pointPolygonTest on bbox bottom-center
│  Confidence check │  Only objects inside zones pass
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Position Dedup   │  Static object: 1 event/5min (STATIC_COOLDOWN_S)
│                   │  Moved (>0.10 normalized): immediate event
│  Min event gap: 5s│  per class (MIN_EVENT_GAP_S)
└────────┬──────────┘
         │
    ┌────┴────┐
    ▼         ▼
  Events     JPEG
  Table      Snapshot
```

**Config per camera:** `ai_enabled`, `ai_objects` (COCO classes), `ai_zones` (polygons), `ai_sensitivity` (MOG2 threshold), `ai_min_confidence` (0.05–0.95).

**Worker lifecycle:** `POLL_INTERVAL=15s` — reconcile loop queries cameras for config changes. Any change (zones/objects/stream URI) recreates the worker within 15s.

**Motion-only mode:** Cameras with `recording_mode='motion'` and `ai_enabled=False` get a motion-only sampler (MOG2 only, no YOLO) that publishes to Redis `nvr:motion`.

---

## Resilience Patterns

### Circuit Breaker
Every FFmpeg process is guarded by a circuit breaker:

| Context | Base Cooldown | Max Cooldown | Formula |
|---------|---------------|--------------|---------|
| Stream relay | 15s | 120s | `min(15 × 2^trips, 120)` |
| Recording recorder | 60s | 600s | `min(60 × 2^trips, 600)` |
| AI frame sampler | 5s | 120s | `min(5 × 2^trips, 120)` |

- `returncode=0` (clean exit) → breaker NOT tripped, immediate reconnect up to 5 attempts
- `returncode≠0` → breaker tripped, up to 3 attempts with transport fallback
- Reset on successful connection

### Idle Reaper
Stream-manager queries MediaMTX API (`/v3/paths/list`) for active readers. Relays with zero readers for `STREAM_IDLE_TIMEOUT_S` (600s) are stopped. Saves CPU when nobody is watching.

### Circular Retention
Every 5 minutes: check disk usage. If ≥85% full or <2GB free → delete oldest segments first (files <10min protected). Also age-based (7 days). Max 500 deletes/run. DB rows synced.

### Heartbeat / Recovery
- AI engine motion state: published on change + every 30s to `nvr:motion`
- Stream-manager: main loop heartbeat at 120s intervals
- All core services: `restart: unless-stopped` in docker compose
- Docker healthchecks: `nvr-db` (pg_isready), `nvr-redis` (ping)

---

## Frontend Architecture

```
React 19 + TypeScript 5.7
├── Vite 6 (dev server + HLS proxy)
├── TanStack Query 5 (server state)
├── Zustand 5 (auth/client state)
├── React Router 6 (routing)
├── Tailwind CSS + Radix UI (components)
├── hls.js (LL-HLS player)
├── Recharts (network charts)
└── lucide-react (icons)

Key hooks:
├── useStreamPlayer      # Shared HLS player (used by MiniLivePreview, CameraGrid ExpandedView, LiveViewPage)
├── useNvrWebSocket      # WS for camera_status + event + network_metric pushes
├── useCamera, useCameras # Camera CRUD hooks
├── useRecordings         # Recording list/stream/bulk-delete hooks
├── useEvents             # Event list/acknowledge hooks
├── useNetwork*           # Network monitoring hooks
└── useAuth               # JWT login/refresh/logout
```

### HLS Proxy
Vite dev server proxies `/hls` → MediaMTX HLS origin (`http://10.10.0.229:8888`) with `changeOrigin: true` and Location header rewrite for redirects.

---

## Security

- **JWT**: Access token 24h (in-memory), refresh token 7d (httpOnly cookie). Redis blacklist for revoked tokens.
- **RBAC**: admin → operator → viewer. Enforced via FastAPI dependency injection (`get_current_user`, `require_admin`, `require_operator`).
- **Camera passwords**: AES-256-GCM encrypted at rest (`nvr_common.security`). Decrypted in-memory only when FFmpeg spawns.
- **Media auth**: `?token=` query parameter on `<img>/<video>` tags passes through `get_current_user`.
- **API keys**: bcrypt hashed, prefix-identifiable (`nvr_a3f2...`), permission-scoped.

---

## Key Technical Decisions

1. **FFmpeg 5.1.9** (not 7.x) — stream-manager container uses Debian bookworm apt package. `-stimeout` not supported; use `-timeout`.
2. **`libx264` transcode always** — Dahua camera H.264 FU-A packet ordering causes MediaMTX HLS errors with `-c:v copy`. Must transcode.
3. **`-c:v copy` for recording** — recording engine uses direct copy (zero video CPU) since it writes to disk not through MediaMTX.
4. **Sub-stream for AI** — 640px width, 0.5 FPS. Reduces inference load dramatically vs main stream.
5. **Motion-only recording** — all 11 cameras use `recording_mode='motion'`. Recording starts only when AI/motion sensor detects activity.
6. **No TimescaleDB hypertables** — plain PostgreSQL tables with DESC time indexes provide adequate performance for current scale.
7. **No MinIO/S3** — all recordings stored on local disk volume (`/data/recordings`).
8. **No NGINX** — Vite dev server proxies directly to API and MediaMTX. NGINX planned for production.
