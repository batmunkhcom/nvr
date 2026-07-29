# Architecture

> Reflects actual deployed state as of 2026-07-25 (v0.01.21).

## Service Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Docker Compose (nvr-net)                         │
│                                                                           │
│  ┌──────────┐   RTSP sub     ┌─────────────────┐                         │
│  │ IP Cams   │───────────────→│  AI Engine        │   Redis pub/sub        │
│  │ (11×      │                 │  YOLOv8n ONNX     │──────────────────┐     │
│  │  Dahua)   │                 │  FrameSampler     │  nvr:motion        │     │
│  │           │                 │  MOG2 gate        │  nvr:events        │     │
│  └────┬─────┘                 └─────────────────┘                    │     │
│       │                                                             │     │
│       │ RTSP sub                   ┌──────────────┐                   ▼     │
│        ├──────────────────────────→│ Stream Mgr    │     ┌────────────────┐ │
│        │                            │ FFmpeg relay │     │ Redis           │ │
│        │                            │ libx264       │     │ pub/sub/cache   │ │
│        │                            │ circuit brkr │     └────────┬───────┘ │
│        │                            └──────┬───────┘              │          │
│        │                                   │ RTSP libx264          │          │
│        │                                   ▼                       │          │
│        │                            ┌──────────────┐              │          │
│        │                            │ MediaMTX      │              │          │
│        │                            │ LL-HLS        │              │          │
│        │                            │ RTSP→HLS      │              │          │
│        │                            └──────┬───────┘              │          │
│        │                                   │ HLS                   │          │
│        │                                   ▼                       │          │
│        │                            ┌──────────────┐              │          │
│        │                            │ Browser       │              │          │
│        │                            │ hls.js        │              │          │
│        │                            └──────────────┘              │          │
│        │                                                          │          │
│        │ RTSP sub              ┌──────────────────┐                │          │
│        ├─────────────────────→│ Recording Engine │←─────────────┘          │
│        │                       │ -c:v copy FFmpeg │  motion trigger         │
│        │                       │ 300s MP4 segs     │                         │
│        │                       │ MotionRecorder    │                         │
│        │                       │ SegmentCatalog    │                         │
│        │                       │ CircularRetention│                         │
│        │                       │ DiskAnalytics     │                         │
│        │                       └────────┬─────────┘                         │
│        │                                │                                   │
│        │                                ▼                                   │
│        │                       ┌──────────────────┐                         │
│        │                       │ Disk              │                         │
│        │                       │ /data/recordings │                         │
│        │                       └────────┬─────────┘                         │
│        │                                │ HTTP Range                        │
│        │                                ▼                                   │
│        │                       ┌──────────────────┐                         │
│   ┌────┴──────────────────────│ FastAPI (nvr-api)│                         │
│   │                             │ REST + WS         │                         │
│   │                             └────────┬─────────┘                         │
│   │                                      │ SQL                              │
│   │                                      ▼                                  │
│   │                             ┌──────────────────┐                         │
│   │                             │ PostgreSQL 16     │                         │
│   │                             │ (nvr-db)          │                         │
│   │                             └──────────────────┘                         │
│   └── cameras table, recordings, events, system_config                     │
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

## FFmpeg Pipelines

### Sub Streams: MediaMTX sourceOnDemand Pull (default — no FFmpeg)

Stream-manager creates a pull path via the MediaMTX API with the camera RTSP
URI as `source`. MediaMTX fetches the camera itself while readers exist and
closes 10s after the last reader leaves — zero transcode CPU.

### Main Streams: FFmpeg Relay-Push (Stream Manager → MediaMTX)

```bash
ffmpeg -rtsp_transport tcp -timeout 5000000 \
    -i rtsp://<username>:<password>@camera:554/Streaming/Channels/101 \
   -c:v libx264 -preset ultrafast -tune zerolatency -g 15 \
   -b:v 2500k -maxrate 2500k -bufsize 5000k \
   -c:a aac -b:a 64k -ac 1 -pkt_size 1200 -threads 1 \
   -f rtsp -rtsp_transport tcp \
  rtsp://nvr-mediamtx:8554/{camera_id}
```

**Notes:**
- `libx264` transcode for relay-pushes (Dahua H.264 FU-A packet ordering causes MediaMTX HLS errors with `-c:v copy` pushes)
- Sub-stream relay (pull disabled): 500k; Main-stream: 2500k
- GOP 15 (1s at 15fps — suits 2s LL-HLS segments)
- Circuit breaker: 15s→120s cooldown; reset only after a 60s stable run
- Idle reaper (FFmpeg relays only): stops relay after 600s with zero readers

### Recording Engine (Direct to Disk)

```bash
ffmpeg -rtsp_transport tcp -timeout 15000000 \
    -i rtsp://<username>:<password>@camera:554/Streaming/Channels/102 \
   -c:v copy \                               # Zero video CPU
   -c:a aac -b:a 64k \                       # Lightweight audio re-encode
   -f segment -segment_format mp4 \
   -segment_format_options movflags=+faststart \
   -segment_time 300 -segment_atclocktime 1 \
   -reset_timestamps 1 -strftime 1 \
   /data/recordings/{camera_id}/%Y/%m/%d/%Y%m%d_%H%M%S.mp4
```

**Notes:**
- `-c:v copy` — no video transcode (very low CPU)
- **Codec normalization** via ffprobe before FFmpeg spawns:
  - HEVC → `-c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p`
  - H.264 → `-bsf:v h264_metadata=video_full_range_flag=0` (normalizes `yuvj420p color_range=pc` → `yuv420p tv`)
- 300s segments with `+faststart` (enables seeking before download complete)
- Motion-only mode: FFmpeg starts/stops based on Redis `nvr:motion` state

## AI Pipeline

```
MediaMTX relay sub-stream (AI_TARGET_FPS, default 1.0 FPS, 640px width)
           │
           ▼
┌───────────────────┐
│  Drainer thread    │  freshest frame only
│  per camera        │  15s staleness → reconnect
└────────┬──────────┘
           │
           ▼
┌───────────────────┐
│  MOG2 Motion Gate │  history=200, detectShadows=False
│   (OpenCV)          │  countNonZero > 800 pixels → motion
│                    │  Threshold: low=50, med=30, high=20
└────────┬──────────┘
           │ motion detected
           ▼
┌───────────────────┐
│  YOLOv8n ONNX      │  Shared singleton session
│   (ONNX Runtime)    │  Intra-op threads: 1
│  INPUT_SIZE=640    │  CPUExecutionProvider
└────────┬──────────┘
           │
           ▼
┌───────────────────┐
│  Post-processing   │  Transpose (1,84,8400) → per-class argmax
│                    │  NMS (IoU=0.45), confidence clamp [0.05, 0.95]
│  Letterbox unscale│
└────────┬──────────┘
           │
           ▼
┌───────────────────┐
│  Zone Filter       │  cv2.pointPolygonTest on bbox bottom-center
│  Confidence check │  Only objects inside zones pass
└────────┬──────────┘
           │
           ▼
┌───────────────────┐
│  Two-stage Track   │  Stage 1: IoU ≥ 0.3 + dist ≤ 0.15
│                    │  Stage 2: relaxed dist ≤ 0.30 (movers)
│  Per-class gap: 5s │  Static: person 5min, vehicle 20min
└────────┬──────────┘
      ┌────┴────┐
      ▼          ▼
   Events     JPEG
   Table      Snapshot
```

## Database Schema (Key Tables)

### cameras
`id (UUID PK), name, ip_address, stream_main_uri, stream_sub_uri, encrypted_password, recording_mode (motion/continuous/never/disabled), ai_enabled, ai_objects (JSON), ai_zones (JSON), ai_sensitivity, ai_min_confidence, motion_source, status, connection_error, location_id ←`

### recordings
`id (UUID), camera_id ←, file_path, file_size_bytes, duration_seconds, start_time, end_time, recording_type (continuous/motion/event), has_audio, codec, resolution, is_corrupt`

### events
`id (UUID), camera_id ←, event_type, severity, start_time, end_time, metadata (JSON), snapshot_path, is_acknowledged`

### system_config
`key (VARCHAR PK), value (JSONB), description, updated_at`

## Resilience Patterns

### Circuit Breaker

| Context | Base Cooldown | Max Cooldown | Formula |
|---------|---------------|--------------|---------|
| Stream relay | 15s | 120s | `min(15 × 2^trips, 120)` |
| Recording recorder | 5s | 600s | `min(5 × 2^trips, 600)` |
| AI frame sampler | 5s | 120s | `min(5 × 2^trips, 120)` |

- Reset only after a proven stable run (60s stream / 300s recording), never on spawn
- Breaker trips once after reconnect exhaustion (no double-trip)

### Circular Retention
Every 5 minutes: check disk usage. If ≥85% full or <2GB free → delete oldest segments first (files <10min protected). Also age-based (7 days). Max 500 deletes/run.

## Key Technical Decisions

1. **FFmpeg 5.1.9** — `-stimeout` not supported; use `-timeout`
2. **`libx264` transcode always** for stream relay — Dahua FU-A packet ordering causes HLS errors
3. **`-c:v copy` for recording** — zero video CPU since it writes to disk directly
4. **Codec auto-detection + normalization** — HEVC→H.264, H.264 full-range→tv range
5. **Sub-stream for AI** — 640px width, 0.5 FPS reduces inference load dramatically
6. **Motion-only recording** — all cameras use `recording_mode='motion'`
7. **No hls.js in RecordingPlayer** — native `<video>` progressive MP4 only; avoids CSP unsafe-eval conflict
