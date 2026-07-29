# Changelog

All notable changes to the NVR system. Versions follow the format `v{major}.{minor}.{patch}`.

---

## v0.02.00 (2026-07-27) — Full-System Audit: Stream/Recording/Detection Reliability + MediaMTX First

**Stream reliability (dashboard):**
- **CRITICAL: `_monitor()` swallowed CancelledError** — every intentional stop (live/stop, idle reaper) auto-restarted the stream 1-2s later. Idle reaper was fully defeated; unwatched streams transcoded 24/7. Fixed: re-raise after cleanup. Verified: zero reconnects after stop.
- **Per-relay-key `asyncio.Lock`** in connect/disconnect — duplicate FFmpeg publisher race (orphan zombie + poisoned breaker) eliminated.
- **Breaker double-trip fix** — a 1s camera blip no longer causes a 30-120s outage; trips once after reconnect exhaustion; resets only after a 60s stable run (never on spawn).
- useStreamPlayer rewrite: per-run token (SUB↔MAIN race), escalating fatal backoff (was pinned at 2s), 45s cold-start poll budget (was 15.6s → needless 60s penalties), stall soft-recovery before full restart, visibilitychange stop/resume for hidden tabs.

**Real-time playback:**
- **WebRTC (WHEP) playback** — `useStreamPlayer` connects via `/mtx/{path}/whep` (MediaMTX :8889, ICE UDP 8189) with automatic LL-HLS fallback. Dashboard latency: 12-15s → **<1s (WebRTC) / ~2-4s (LL-HLS)**.
- **LL-HLS client enabled** (`lowLatencyMode: true`) — server variant was configured but unused.
- MediaMTX WebRTC NAT config (`MTX_WEBRTCADDITIONALHOSTS` = host LAN IP), `8189/udp` published, `/mtx` proxies in Vite + nginx (buffering off).

**MediaMTX first — sub streams via `sourceOnDemand` pull:**
- Stream-manager creates pull paths via the MediaMTX API; MediaMTX fetches cameras itself while readers exist (closes 10s after last reader). **stream-manager CPU: ~100% → 0.00%.** FFmpeg libx264 relay kept for main streams (Dahua FU-A). `MEDIAMTX_PULL_MODE=sub|all|` env flag.

**Recording reliability:**
- **CRITICAL: ONVIF motion published only `active:True`** — motion-mode recorders never stopped. Now publishes the real event value; subscription auto-renews (480s).
- **CRITICAL: catalog `_purge_missing` deleted DB rows of S3-migrated recordings** — `s3://` paths now guarded.
- **CRITICAL: tier migration never deleted the source file** — catalog re-registered it → infinite duplicate loop. Source deleted after DB commit.
- Recording breaker: reset-on-spawn removed (flat 60s gap per blip) → 5s→600s escalating, reset only after a 300s stable session.
- **Progress watchdog** — hung FFmpeg (dead RTSP over live TCP) is killed when the active segment stops growing for `max(2×segment, 180s)`.
- Motion pipeline: heartbeat in BOTH states (30s), True=keepalive, 90s staleness sweep, mode-flip dual-writer guard, `MOTION_COOLDOWN_S` 60→10 (was > stop delay → guaranteed unrecorded window).
- Motion start latency 8-15s → ~2-5s: 2-frame arming + MOG2 warm-up, codec probe cached 1h, **`RECORD_VIA_RELAY=1`** (warm relay attach ~100ms, ≤1s keyframe wait).
- Retention: per-root oldest deletion in batches (was global-oldest regardless of root), S3 objects deleted via backend, orphan camera-dir cleanup, today/tomorrow dirs protected from pruning.
- Catalog: unreadable segments registered `is_corrupt=true` (duration never fabricated), deleted-camera FK spam stopped, `.thumb_failed` retry marker (1/day), UUID-dir walk filter.

**Detection quality:**
- **CRITICAL: two-stage tracking** — strict IoU+dist match plus relaxed centre-distance fallback (movers have IoU≈0 at 1 FPS → previously fired a NEW event EVERY frame). Per-class 5s global event gap backstop. Verified: 11 walking frames → 0 events (was 11).
- **Drainer thread** per sampler — freshest-frame-only reads (stale-frame lag eliminated) + 15s staleness reconnect + socket timeout (OpenCV `|` separator fix).
- Missing YOLO model no longer disables motion-only/ONVIF workers; relay start re-POSTed on capture failure (authed URI — fixes MediaMTX pull 401s); worker signature includes credentials+storage path.
- Event pipeline: snapshot → event insert → broadcast; counter upserts independent (a counter failure never loses the event); Redis publish retries once.

**Docs:** AGENTS.md — "MediaMTX First" section + 10 Engineering Rules; ARCHITECTURE.md/wiki corrected (GOP 15, 500/2500k, 1.0 FPS, MOG2 200/800, 20min vehicles, 300s tracklets, breaker values, 13 containers, WebRTC ports).

## v0.01.21 (2026-07-25) — Recording Playback Fix + Codec Normalization

- **CSP fix — remove hls.js from RecordingPlayer** — `hls.js` uses `new Function()` which triggers CSP `script-src` block in Chrome (Chrome strict, Safari lenient). RecordingPlayer now uses native `<video>` progressive MP4 only.
- **HEVC→H.264 transcode** in recording engine — ffprobe auto-detects codec; HEVC streams transcoded with `libx264 ultrafast crf20 pix_fmt yuv420p`
- **H.264 bitstream filter** — normalizes `yuvj420p color_range=pc` → `yuv420p tv` via `-bsf:v h264_metadata=video_full_range_flag=0`
- **HTTP Range handling fix** — returns `200 OK` for full-file requests, `206 Partial Content` only for partial ranges (fixes Chrome rejection of full-range 206 responses)
- **RecordingPlayer cleanup** — removed complex spinner/playBlocked overlay, restored working `controls={controls}`, fixed `video.playbackRate` useEffect for speed controls
- **Recordings.tsx** — added `key={activePlaybackId}` to force clean remount on recording switch
- **AGENTS.md** — comprehensive Recording Playback troubleshooting section added (CSP, codec, Range, browser differences)

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
