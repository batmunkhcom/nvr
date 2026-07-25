# NVR System — Current State

> Last updated: 2026-07-25 (v0.01.15)
> Sources: `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, git log

---

## System Status

| Metric | Value |
|--------|-------|
| Cameras | 11 Dahua, all online |
| Recording mode | motion-only (all 11 cameras) |
| AI detection | 10/11 cameras active (cam3 disabled) |
| AI model | YOLOv8n ONNX, 0.5 FPS, MOG2 gate (sensitivity: low) |
| Stream relay | 11 sub-stream FFmpeg transcodes (libx264, 1000k) |
| HLS latency | ~1-3s LL-HLS |
| Server load | ~21 (4 cores, down from 41 after tuning) |
| Disk | 29GB total, circular retention active |
| Tests | 64 pytest + 34 vitest (all passing) |
| Last deploy | v0.01.15 (server performance tuning) |

---

## What's Working

### Core Systems
- **Live streaming** — LL-HLS with 1-3s glass-to-glass, audio+video, digital zoom
- **Recording** — motion-triggered FFmpeg `-c:v copy`, 300s MP4 segments, 30s stop delay
- **Circular retention** — disk ≥85% or <2GB free triggers oldest deletion, disk can never fill
- **AI detection** — YOLOv8n ONNX, position-aware dedup, zone filtering, event snapshots
- **Idle reaper** — relays with zero viewers stop after 10 min (CPU savings)
- **Health checks** — camera auto-health background loop, connection testing

### Frontend
- **Dashboard** — 1-4 column grid, camera tiles with live preview
- **Live View** — full-screen single camera with PTZ, audio, zoom
- **Recordings page** — list, filter, bulk delete, thumbnail previews, playback with speed controls
- **Events page** — feed with snapshots, object badges, camera filter, acknowledge
- **Network dashboard** — bandwidth/latency/packet loss charts, time-range selector, alerts
- **Storage page** — disk analysis, GB/day projection, per-camera table
- **Settings page** — full system_config editor (storage, recording, AI categories)
- **Locations** — CRUD management
- **User profile** — password change

### API (14 routers under `/api/v1`)
- Cameras CRUD + discovery + test + PTZ + snapshot
- Recordings list/stream/thumbnail/timeline/bulk-delete/download
- Events list/snapshot/acknowledge + WebSocket stream
- Network metrics/history/summary/alerts
- Storage usage, Locations CRUD, Users CRUD
- System health/config, Auth (login/refresh/logout)
- WebSocket (`/ws` — camera status, events, network metrics)

### Infrastructure
- Docker compose with 8 active services (DB, Redis, API, Web, Stream Mgr, MediaMTX, Recording Engine, AI Engine)
- Circuit breakers on all FFmpeg processes (15s-600s cooldown)
- Docker log rotation (10m × 3) on all services
- `restart: unless-stopped` on core services
- Backup & restore scripts (AES-256-CBC encrypted)

---

## Current Limitations

1. **PostgreSQL connection pool** (5 base + 5 overflow) can saturate under high load → "too many clients" errors on `psql`
2. **Stream relay must transcode** — Dahua H.264 FU-A packet ordering causes MediaMTX HLS errors with `-c:v copy`
3. **No Telegram/webhook notifications** — `notification_service.py` skeleton exists, not wired up
4. **29GB disk** — limited capacity; motion-only recording significantly reduced usage from 26GB/day (continuous) to ~5-8GB/day
5. **FFmpeg 5.1.9** in stream-manager — can't use `-reconnect` on RTSP input. Monitor loop handles reconnection instead.

---

## Recent Fix History (last 10 commits)

| Commit | Date | Description |
|--------|------|-------------|
| `8e1571a` | Jul 25 | Server load tuning — AI FPS 0.5, ONNX threads 1, bitrate 1000k |
| `cd40fdc` | Jul 25 | HLS stability — correct FFmpeg `-timeout` option |
| `bf37ca1` | Jul 25 | HLS stability — stop retry disconnect loop |
| `c017f1d` | Jul 25 | Recording playback and download restored |
| `ef1cdf8` | Jul 25 | Network alerts JSON serialization fix |
| `0b008cd` | Jul 25 | Camera name column in recordings list |
| `ad9294e` | Jul 25 | User profile page, password change, username dropdown |
| `e539ea1` | Jul 24 | Low-latency HLS — 10-15s → 1-3s glass-to-glass |
| `f8eb510` | Jul 24 | Enable audio in stream-manager FFmpeg relay |
| `876424e` | Jul 24 | Audio controls + digital zoom everywhere, ONVIF PTZ in modal |

---

## Immediate Priorities

1. Fix PostgreSQL connection pool saturation
2. Wire up Telegram/webhook notifications for AI events
3. Add `cpus` reservation for stream-manager to prevent starvation
4. Test `-c:v copy` relay to eliminate FFmpeg transcode CPU
