# NVR System — TODO & Backlog

> Last updated: 2026-07-25
> See also: `docs/todo-improvements.md` (rewrite execution log), `docs/todo_network.md` (network monitoring plan)

---

## Completed Phases

### Phase R — Recording & AI Activation ✅
- [x] Recording engine with per-camera FFmpeg supervisors, 300s MP4 segments, `-c:v copy`
- [x] Circular retention — disk watermark (85% / <2GB) triggers oldest segment deletion
- [x] SegmentCatalog (60s) — registers closed segments in `recordings` table
- [x] DiskAnalytics (hourly) — GB/day per camera, capacity projection
- [x] AI engine — YOLOv8n ONNX, MOG2 motion gate, position-aware dedup
- [x] Events + JPEG snapshots + Redis pub
- [x] Motion-only recording (motion → record, idle 30s → stop)

### Phase 1 — Performance & Reliability ✅
- [x] Idle stream reaper (10min zero-readers → stop relay)
- [x] Circuit breaker per camera (15s→120s cooldown)
- [x] LL-HLS low-latency (1-3s glass-to-glass)
- [x] Audio playback in live stream
- [x] DB indexes for events/recordings time queries
- [x] Docker log rotation (10m × 3) on all services
- [x] `restart: unless-stopped` on core services
- [x] HLS stability — FFmpeg `-timeout` (not `-stimeout`), transport fallback

### Phase 2 — UX ✅
- [x] PTZ controls (ONVIF)
- [x] Digital zoom in live view
- [x] Recording playback with speed controls (0.125x–8x)
- [x] Recording download (`?download=true`)
- [x] Recording thumbnails (sidecar JPEG, backfill)
- [x] Recording bulk delete (by ID, all, before date)
- [x] Timeline click-to-play (seek to segment)
- [x] Camera name JOIN in recordings list
- [x] Settings page — storage category, select inputs
- [x] Storage page — Recording Disk Analysis card
- [x] Dark scrollbar, page transitions
- [x] User profile page + password change

### Phase 3 — Features ✅
- [x] IP camera discovery (ONVIF/RTSP/ARP/mDNS/vendor) — 6-phase pipeline
- [x] Multi-user RBAC (admin/operator/viewer)
- [x] Locations entity with camera assignment
- [x] AI zone editor — polygon drawing on snapshot overlay
- [x] Network monitoring dashboard (bandwidth/latency/packet loss charts)
- [x] Camera auto-health-check background loop
- [x] Backup & restore scripts (AES-256-CBC encrypted)
- [x] PWA support (service worker, offline cache, install prompt)

### Phase 4 — Server Tuning (v0.01.15) ✅
- [x] AI FPS 2→0.5 — AI CPU 166%→74%
- [x] ONNX threads 2→1
- [x] MOG2 sensitivity medium→low (all cameras)
- [x] Sub-stream bitrate 2000k→1000k
- [x] AI engine docker CPU limit 4→2

---

## Immediate Backlog

### 🔴 High Priority
- [ ] Telegram/webhook notifications for AI events (notification_service.py skeleton exists)
- [ ] Increase PostgreSQL max_connections (too many clients error under load)
- [ ] Add CPU reservation for stream-manager (prevent starvation)
- [ ] Try `-c:v copy` for stream relay (FU-A packet ordering — test if MediaMTX handles it)
- [ ] Storage backend expansion — move recordings volume to larger disk

### 🟡 Medium Priority
- [ ] Stream transport auto-fallback tcp→udp
- [ ] Zone editor UX — show detection heatmap overlay
- [ ] Snapshot preview on camera tiles (instead of full HLS stream)
- [ ] i18n foundation — Mongolian/English toggle
- [ ] Face/person recognition (RetinaFace + ArcFace)
- [ ] Audio event detection (YAMNet)

### 🟢 Nice to Have
- [ ] Recording export — concatenate segments, re-encode
- [ ] Notification templates UI
- [ ] Camera setup wizard
- [ ] Schedules page — merge into recordings tab
- [ ] Mobile native app (React Native)
- [ ] Hardware acceleration (VAAPI/NVENC)
- [ ] Kubernetes migration (k3s)

---

*Status legend: `[x]` done, `[ ]` not started, `[~]` in progress*
