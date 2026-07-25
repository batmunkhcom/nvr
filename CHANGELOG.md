# Changelog

All notable changes to the NVR system. Versions follow the format `v{major}.{minor}.{patch}`.

---

## v0.01.15 (2026-07-25) — Server Load Tuning

- **AI FPS 2→0.5** — YOLO inference rate reduced (CPU: 166%→74%)
- **ONNX threads 2→1** — reduced thread contention
- **MOG2 sensitivity medium→low** on all 11 cameras — fewer frames reach YOLO
- **Sub-stream bitrate 2000k→1000k** — lighter FFmpeg encode
- **AI engine Docker CPU limit 4→2** — cgroup enforcement
- **cam3 AI disabled** — `recording_mode=never` camera no longer runs YOLO
- Result: Load avg 41→21 (-48%), AI RAM 955MB→565MB (-41%)

## v0.01.14 (2026-07-25) — HLS Stability

- **Fixed FFmpeg `-stimeout` → `-timeout`** — FFmpeg 5.1.9 doesn't support `-stimeout`, causing startup crashes every few seconds
- **Removed `-reconnect` flags** — not supported for RTSP in FFmpeg 5.1.9
- **Monitor loop**: `returncode=0` clean exits bypass circuit breaker, 5 quick reconnect attempts
- **Monitor loop**: `returncode≠0` errors get 3 attempts with transport fallback
- **HLS.js `maxBufferHole: 0.5`** — tighter gap tolerance
- FFmpeg crash rate: 17/5min → ~1/3min

## v0.01.13 (2026-07-25) — Recording Playback Restore

- Fixed recording stream endpoint (`HEAD` for browser pre-flight)
- Fixed download filename sanitization (removed `:+T` characters)
- Reverted to simple `<video>` element RecordingPlayer (removed complex useVideoZoom)
- Camera name column added to recordings list via JOIN

## v0.01.12 (2026-07-25) — Network + UX

- Network alerts JSON serialization fix
- Multi-line overlay chart with per-camera colors
- Camera name in recordings list via proper FK join
- User profile page — password change, username display

## v0.01.11 (2026-07-24) — LL-HLS + Audio

- **Low-latency HLS** — 10-15s → 1-3s glass-to-glass (hlsVariant: lowLatency)
- **Audio enabled** in stream-manager FFmpeg relay (was `-an`)
- **Audio controls** in live view (mute/unmute)
- **Digital zoom** — 2D CSS zoom+pan on any stream
- **ONVIF PTZ** in modal (ExpandedView)
- Removed unused MinIO container, volume, and S3 config

## v0.01.10 (2026-07-24) — Recording UX

- **Download recordings** (`?download=true` query param)
- **Playback speed controls** — 0.125x, 0.25x, 0.5x, 0.75x, 1x, 1.5x, 2x, 4x, 8x
- **Recording thumbnails** — auto-generated sidecar JPEG per segment via ffmpeg
- **Thumbnail resilience** — `-ss 2` fallback to `-ss 0` for short segments
- **Bulk delete** — by ID list, all per camera, or before date
- **Timeline click-to-play** — click time bar to jump to segment
- Date-time range filter on recordings

## v0.01.09 (2026-07-24) — Motion-Only Recording + AI Zones

- **Motion-only recording** — FFmpeg starts on motion, stops after 30s idle
- **AI zone editor** — draw polygon zones on camera snapshot, apply to detections
- **Position-aware dedup** — static object: 1 event/5min, moved: immediate
- Motion state publishing to Redis `nvr:motion` (on change + 30s heartbeat)
- Recording engine `MotionRecorderController` with separate registry
- Catalog marks segments with `recording_type='motion'`

## v0.01.08 (2026-07-24) — Recording Engine + AI Engine Rewrite

- **Recording engine** — per-camera FFmpeg supervisors, `-c:v copy`, 300s segments
- **Circular retention** — disk ≥85% or <2GB free → delete oldest first
- **Segment Catalog** — 60s scan registers closed segments in `recordings` table
- **Disk Analytics** — hourly GB/day per camera, capacity projection
- **AI engine** — YOLOv8n ONNX, MOG2 motion gate, correct post-processing
- Events + JPEG snapshots + Redis broadcast
- Docker log rotation on all 13 services
- Disk budget config: `storage.max_usage_percent=85`, `storage.min_free_gb=2`, `recording.segment_seconds=300`, `retention.default_days=7`

## v0.01.07 (2026-07-24) — Performance & Stability

- **Idle stream reaper** — 10min zero-readers → stop FFmpeg relay
- MediaMTX v1.19 API auth fix (internal users config)
- Alembic 0008: events/recordings performance indexes
- `restart: unless-stopped` on all 7 core services
- `health_check_loop` `probe_ip(port=)` bug fix (crashed every 60s)
- Docker build cache pruned: 9.6GB → 13GB free

## v0.01.06 (2026-07-24) — Settings & Storage UI

- Settings page — storage category with select inputs
- Config descriptions: 13 keys with Mongolian descriptions + English help
- Storage page: Recording Disk Analysis card (GB/day, days-fit, per-camera table)
- Camera form hints on every field

## v0.01.05 (2026-07-24) — Events UI + Design System

- Events page with snapshot thumbnails (token auth)
- Object badges (car/person icon)
- Camera filter on events
- Design token system (surface/semantic/typography)
- Toast notification system
- Dark scrollbar, page transitions

## v0.01.04 (2026-07-23) — Testing Suite

- Backend: 59 pytest passing (rtsp_check, services, live_relay, locations, system_config)
- Frontend: 34 vitest passing (useCameras, useEvents, AppShell, useLocations, CameraGrid, Cameras, LiveViewPage)
- `tsc --noEmit` clean

## v0.01.03 (2026-07-23) — Dashboard + Live View

- Configurable dashboard columns (1/2/3/4), persisted in DB
- Sidebar collapsible (56px icon-only ↔ 224px full)
- Sub-stream relay for bandwidth-efficient dashboard previews
- Auto-restart with exponential backoff (5s→60s)
- Camera `connection_error` field for auth/network errors
- Camera auto-health-check background loop

## v0.01.02 (2026-07-23) — Discovery + Locations

- 6-phase camera discovery (ONVIF/RTSP/ARP/mDNS/vendor broadcast)
- Locations entity with CRUD
- IP-range discovery (e.g. `10.10.0.200-230`)
- Backup & restore scripts (AES-256-CBC encrypted)
- Dahua digest auth single-connection fix
- Sub-stream relay for dashboard bandwidth reduction
- `func.now()` → `lambda: datetime.now(UTC)` fix across 20+ models

## v0.01.01 (2026-07-22) — Foundation

- Docker compose setup (8 core services)
- FastAPI backend with modular API v1 routers
- React + Vite + TypeScript frontend with TanStack Query
- ALBEMIC database migrations (0001–0005: initial schema, connection_error, locations, storage, AI config)
- JWT authentication with RBAC (admin/operator/viewer)
- Camera CRUD with ONVIF capabilities detection
- RTSP auth check (basic/digest, Dahua nonce binding)
- Camera connection testing
- Live relay with circuit breaker (60s→600s)
- `system_config` DB-driven configuration
- MediaMTX integration (RTSP server + HLS output)
- Config seed from `default.yml`
- PWA support with service worker + offline cache
- Open source prep — secret sanitization, Apache-2.0 license
