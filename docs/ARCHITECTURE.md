# NVR System Architecture

> Reflects actual deployed state as of 2026-07-27 (post-audit fixes: MediaMTX pull mode, WebRTC WHEP, two-stage tracking).

---

## Service Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Docker Compose (nvr-net)                        │
│                                                                          │
│  ┌──────────┐                 ┌─────────────────┐                        │
│  │ IP Cams  │←── RTSP pull ───│  MediaMTX        │   sourceOnDemand      │
│  │ (11×     │   (sub streams) │  pulls camera    │   (sub)               │
│  │  Dahua)  │                 │  itself while    │                       │
│  │          │←── RTSP push ───│  readers exist   │  FFmpeg libx264       │
│  │          │  (main streams, │  LL-HLS :8888    │  relay (main only)    │
│  │          │   libx264)      │  WebRTC :8889    │                       │
│  └────┬─────┘                 │  RTSP :8554      │                       │
│       │                       └───┬────┬────┬────┘                       │
│       │                           │    │    │                            │
│       │              RTSP sub ────┘    │    │ HLS / WHEP                │
│       │              (shared path)     │    ▼                           │
│       │              ┌─────────────────┐│  ┌──────────────┐             │
│       │              │  AI Engine       ││  │ Browser      │             │
│       │              │  YOLOv8n ONNX    ││  │ WebRTC first │             │
│       │              │  FrameSampler    ││  │ LL-HLS fallback            │
│       │              │  MOG2 gate       ││  └──────────────┘             │
│       │              └────────┬────────┘│                              │
│       │                       │ Redis pub/sub (nvr:motion, nvr:events)   │
│       │ RTSP sub/direct       ▼                     ┌────────────────┐   │
│       ├────────────────→┌──────────────────┐        │ Redis          │   │
│       │                 │ Recording Engine │←───────│ pub/sub/cache  │   │
│       │                 │ -c:v copy FFmpeg │ motion └────────────────┘   │
│       │                 │ 300s MP4 segs    │ trigger                     │
│       │                 │ MotionRecorder   │ (via relay path, warm)      │
│       │                 │ SegmentCatalog   │                             │
│       │                 │ CircularRetention│                             │
│       │                 │ DiskAnalytics    │                             │
│       │                 └────────┬─────────┘                             │
│       │                          ▼                                       │
│       │                 ┌──────────────────┐                             │
│       │                 │ Disk /data        │                            │
│       │                 └────────┬─────────┘                             │
│       │                          │ HTTP Range                            │
│       │                          ▼                                       │
│  ┌────┴─────────────────→┌──────────────────┐                            │
│  │                       │ FastAPI (nvr-api)│                            │
│  │                       │ REST + WS        │                            │
│  │                       └────────┬─────────┘                            │
│  │                                │ SQL                                  │
│  │                                ▼                                      │
│  │                       ┌──────────────────┐                             │
│  │                       │ PostgreSQL 16    │                             │
│  │                       │ (nvr-db)         │                             │
│  │                       └──────────────────┘                             │
│  └── cameras table, recordings, events, system_config                    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Containers

| Container | Image | CPU Limit | Memory Limit | Ports |
|-----------|-------|-----------|--------------|-------|
| `nvr-db` | timescale/timescaledb:latest-pg16 | 2 | 2G | 5432 |
| `nvr-redis` | redis:7-alpine | — | — | 6379 |
| `nvr-api` | python:3.13-slim | 2 | 1G | 8000 |
| `nvr-web` | node:22-slim (Vite dev) | — | — | 3000 |
| `nvr-stream-manager` | python:3.13-slim (+FFmpeg 5.1) | 4 | 4G | 8001 |
| `nvr-mediamtx` | bluenviron/mediamtx:latest (v1.19.2) | — | — | 8554, 8888, 8889, 9997, 8189/udp |
| `nvr-recording-engine` | python:3.13-slim (+FFmpeg 5.1) | 2 | 2G | — |
| `nvr-ai-engine` | python:3.13-slim (+ONNX) | 2 | 4G | — |
| `nvr-nginx` | nginx (reverse proxy) | — | — | 80, 443 |
| `nvr-mosquitto` | eclipse-mosquitto:2 | — | — | 1883 |
| `nvr-chrony` | cturra/ntp | — | — | 123/udp |
| `nvr-mqtt-bridge` | python (Redis→MQTT) | — | — | — |

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

### Sub Streams: MediaMTX sourceOnDemand Pull (no FFmpeg)

```
stream-manager → POST /v3/config/paths/add/{cid}_sub
  {source: rtsp://admin:pass@camera:554/Streaming/Channels/102,
   sourceOnDemand: true, sourceOnDemandStartTimeout: 20s,
   sourceOnDemandCloseAfter: 10s, rtspTransport: tcp}
```

MediaMTX fetches the camera itself while readers (HLS/WHEP/RTSP/AI-sampler)
exist and closes 10s after the last reader. **Zero transcode CPU.**

### Main Streams: FFmpeg Relay-Push (Stream Manager → MediaMTX)

```
ffmpeg -rtsp_transport tcp -timeout 5000000 \
  -i rtsp://admin:pass@camera:554/Streaming/Channels/101 \
  -c:v libx264 -preset ultrafast -tune zerolatency -g 15 \
  -b:v 2500k -maxrate 2500k -bufsize 5000k \
  -c:a aac -b:a 64k -ac 1 -pkt_size 1200 -threads 1 \
  -f rtsp -rtsp_transport tcp \
  rtsp://nvr-mediamtx:8554/{camera_id}
```

**Notes:**
- `libx264` transcode for relay-pushes (H.264 FU-A packet ordering from Dahua cameras causes MediaMTX HLS errors with `-c:v copy` pushes)
- Sub-stream relay (if pull mode disabled): `-b:v 500k -bufsize 1000k`
- Main-stream bitrate: 2500k (`stream.main_bitrate_kbps` in system_config)
- GOP 15 (1s at 15fps sub — suits 2s LL-HLS segments)
- Circuit breaker: 15s→120s cooldown, reset only after a 60s stable run (never on spawn); trips once after reconnect exhaustion
- Idle reaper (FFmpeg relays only): stops relay after `STREAM_IDLE_TIMEOUT_S` (600s) with zero MediaMTX readers; pull paths are managed by MediaMTX itself

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
- **Codec normalization** — auto-detected via ffprobe before FFmpeg spawns (cached per URL for 1h):
  - HEVC → `-c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p -g 30`
  - H.264 → `-bsf:v h264_metadata=video_full_range_flag=0` (normalizes `yuvj420p color_range=pc` → `yuv420p tv`)
  - Audio copied when already AAC, transcoded to AAC 64k otherwise
- 300s segments with `+faststart` (enables seeking before download complete)
- Motion-only mode: FFmpeg starts/stops based on Redis `nvr:motion` state; motion sub-recording reads the warm MediaMTX relay path (`RECORD_VIA_RELAY=1`)
- Circuit breaker: 5s→600s escalating, reset only after a 300s stable session
- **Progress watchdog**: active segment's size must grow within `max(2×segment_seconds, 180s)` or the hung FFmpeg is killed and restarted

---

## AI Pipeline

```
MediaMTX relay sub-stream (AI_TARGET_FPS, default 1.0 FPS, 640px width)
         │
         ▼
┌───────────────────┐
│  Drainer thread   │  continuously drains RTSP, keeps freshest frame only
│  (per camera)     │  15s frame staleness → reconnect (half-dead detection)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  MOG2 Motion Gate │  history=200, detectShadows=False
│  (OpenCV)         │  countNonZero > 800 pixels → motion
│                   │  Threshold: low=50, med=30, high=20
│                   │  3-frame warm-up suppress after (re)connect
└────────┬──────────┘
         │ motion detected (2 consecutive frames → active)
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
│  Two-stage Track  │  Stage 1: IoU ≥ 0.3 AND centre dist ≤ 0.15
│                   │  Stage 2: relaxed centre dist ≤ 0.30 (movers at 1 FPS)
│  Per-class gap 5s │  New: immediate event (class-gap throttled)
│                   │  Moving: 1/15s · Static: person 5min, vehicle 20min
└────────┬──────────┘
         │
     ┌───┴────┐
     ▼         ▼
   Events     JPEG
   Table      Snapshot
```

**Config per camera:** `ai_enabled`, `ai_objects` (COCO classes), `ai_zones` (polygons), `ai_sensitivity` (MOG2 threshold), `ai_min_confidence` (0.05–0.95).

**Worker lifecycle:** `POLL_INTERVAL=15s` — reconcile loop queries cameras for config changes. Any change (zones/objects/stream URI/credentials/storage) recreates the worker within 15s. A missing YOLO model never disables workers — detection no-ops until the model loads.

**Motion-only mode:** Cameras with `recording_mode='motion'` and `ai_enabled=False` get a motion-only sampler (MOG2 only, no YOLO) that publishes to Redis `nvr:motion` (both states, 30s heartbeat).

---

## Resilience Patterns

### Circuit Breaker
Every FFmpeg process is guarded by a circuit breaker:

| Context | Base Cooldown | Max Cooldown | Formula |
|---------|---------------|--------------|---------|
| Stream relay | 15s | 120s | `min(15 × 2^trips, 120)` |
| Recording recorder | 5s | 600s | `min(5 × 2^trips, 600)` |
| AI frame sampler | 5s | 120s | `min(5 × 2^trips, 120)` |

- Reset only after a proven stable run (60s stream / 300s recording), never on spawn
- Reconnect attempts run first; the breaker trips once on exhaustion (no double-trip)

### Idle Reaper
Stream-manager queries MediaMTX API (`/v3/paths/list`) for active readers. FFmpeg relays with zero readers for `STREAM_IDLE_TIMEOUT_S` (600s) are stopped. Pull-mode paths manage themselves via `sourceOnDemandCloseAfter`.

### Circular Retention
Every 5 minutes: check disk usage per root. If ≥85% full or <2GB free → delete oldest segments of THAT root in batches of 50 (files <10min protected). Also age-based (7 days). Max 500 deletes/run. DB rows synced; S3 objects deleted via the storage backend; orphan camera dirs removed after the age grace.

### Heartbeat / Recovery
- AI engine motion state: published on change + every 30s to `nvr:motion` in BOTH states; recording engine staleness sweep stops recorders after 90s without keepalive
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

### Live Playback Protocol

```
Browser → useStreamPlayer
  ├── 1. POST /api/v1/cameras/{id}/live/start?stream=sub
  ├── 2. WebRTC (WHEP): POST /mtx/{path}/whep → MediaMTX :8889 (<1s latency)
  │      └── any failure → automatic fallback:
  └── 3. LL-HLS: /hls/{path}/index.m3u8 via hls.js (lowLatencyMode: true, ~2-4s)
```

Hidden tabs stop consuming (visibilitychange destroys the player; MediaMTX
reader count drops → idle teardown works). Stall recovery: soft live-edge
resync first, full restart only after 2 failed soft attempts.

### HLS/WHEP Proxy
Vite dev server proxies `/hls` → MediaMTX HLS origin (:8888) and `/mtx` →
MediaMTX WebRTC origin (:8889), `changeOrigin: true` with Location header
rewrite. nginx mirrors both with `proxy_buffering off` (LL-HLS blocking
requests must not be buffered).

### Recording Playback Architecture

```
Browser → RecordingPlayer.tsx
  ├── Progressive MP4 download (no hls.js — avoids CSP unsafe-eval conflict)
  ├── <video controls muted autoPlay playsInline preload="auto">
  ├── HTTP Range: 200 OK (full file) / 206 Partial Content (seeking)
  ├── playbackRate controls: 0.125x ... 8x (slow/fast color coded)
  └── Token auth via ?token= query parameter
```

**Why no hls.js in RecordingPlayer:**
- `hls.js` internally uses `new Function()` which triggers CSP `script-src` blocks in Chrome
- RecordingPlayer only plays MP4 progressive downloads (not HLS)
- LiveView uses `useStreamPlayer` with hls.js — that's the correct HLS context

### CSP Strategy

| Context | Stack | HLS? | CSP Safe? |
|---------|-------|------|-----------|
| RecordingPlayer | Native `<video>` + MP4 | No | ✅ |
| MiniLivePreview | `useStreamPlayer` + hls.js | Yes | ⚠️ Requires `unsafe-eval` |
| CameraGrid ExpandedView | `useStreamPlayer` + hls.js | Yes | ⚠️ Requires `unsafe-eval` |
| LiveViewPage | `useStreamPlayer` + hls.js | Yes | ⚠️ Requires `unsafe-eval` |

For production, add `script-src 'self' 'unsafe-eval'` to CSP header — hls.js requires it. RecordingPlayer deliberately avoids this dependency.

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
2. **MediaMTX pull for sub streams** — `sourceOnDemand` paths let MediaMTX fetch cameras itself (zero transcode CPU, reader-driven lifecycle). FFmpeg `libx264` relay-push is kept for main streams because Dahua FU-A packet ordering breaks MediaMTX HLS with `-c:v copy` pushes.
3. **`-c:v copy` for recording** — recording engine uses direct copy (zero video CPU) since it writes to disk not through MediaMTX. Continuous recording stays direct (independent of relay uptime); motion sub-recording reads the warm relay path for ~100ms attach (`RECORD_VIA_RELAY=1`).
4. **Codec auto-detection + normalization** — ffprobe detects HEVC/H.264 before FFmpeg spawns (cached 1h). HEVC→H.264 transcode, H.264 `video_full_range_flag=0` bsf. Ensures Chrome-compatible output (yuv420p tv range).
5. **Sub-stream for AI** — 640px width, 1.0 FPS (`AI_TARGET_FPS`). Reduces inference load dramatically vs main stream. Tracking constants are tuned to this rate.
6. **Motion-only recording** — all 11 cameras use `recording_mode='motion'`. Recording starts only when AI/motion sensor detects activity.
7. **No TimescaleDB hypertables** — plain PostgreSQL tables with DESC time indexes provide adequate performance for current scale.
8. **No MinIO/S3** — all recordings stored on local disk volume (`/data/recordings`). S3 backends are supported via the storage abstraction (catalog/retention guard `s3://` paths).
9. **NGINX as reverse proxy** — serves the web app and proxies `/api`, `/hls`, `/mtx` (WHEP) with buffering off. Vite dev server mirrors the same proxy routes in development.
10. **No hls.js in RecordingPlayer** — uses native `<video>` progressive MP4 only. Avoids CSP `unsafe-eval` conflict in Chrome. hls.js reserved for LiveView streams only (WebRTC-preferred, LL-HLS fallback).
