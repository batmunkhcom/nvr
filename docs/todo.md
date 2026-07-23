# mBm NVR System — Development TODO

> **Status legend:** `[ ]` not started, `[~]` in progress, `[x]` done, `[-]` blocked/not applicable

---

## Phase 0: Project Init

### 0.1 Git & Project
- [x] `AGENTS.md` — AI development guide
- [x] `docs/PLAN.md` — Architecture plan (2,791 lines)
- [x] `docs/todo.md` — This file
- [x] `config/default.yml` — Default system config
- [x] `config/vendor_patterns.yml` — Camera fingerprint DB (11 vendors)
- [x] `pyproject.toml` — Python project metadata + deps
- [x] `Makefile` — 27 shortcut commands
- [x] `.env.example` — Environment variables template
- [x] `.gitignore` — Git ignore rules
- [x] `.github/workflows/ci.yml` — CI/CD pipeline
- [x] `README.md` — Project overview
- [x] `scripts/seed_db.py` — Config seeder
- [x] `scripts/setup-hooks.sh` — Pre-commit hooks
- [x] Discovery engine skeleton (`stream-manager/app/discovery/`)
- [x] Package `__init__.py` files (full structure)
- [x] Git init & first commit & push

---

## Phase 1: Foundation (Week 1–2)

### 1.1 Docker Compose
- [x] `docker-compose.yml` — all services (api, stream-manager, mediamtx, recording-engine, ai-engine, db, redis, minio, mosquitto, mqtt-bridge, nginx, web, chrony)
- [ ] `docker-compose.prod.yml` — production override
- [x] `config/mediamtx.yml` — MediaMTX configuration
- [ ] `config/mosquitto.conf` — MQTT broker config
- [x] `docker/api/Dockerfile` — FastAPI image
- [x] `docker/stream-manager/Dockerfile` — Stream manager image
- [ ] `docker/recording-engine/Dockerfile` — Recording engine image
- [ ] `docker/ai-engine/Dockerfile` — AI engine image
- [x] `docker/web/Dockerfile` — React dev + production
- [x] `docker/nginx/Dockerfile` — NGINX reverse proxy
- [ ] `docker/mqtt-bridge/Dockerfile` — MQTT event bridge
- [x] `docker-compose up` works

### 1.2 PostgreSQL + TimescaleDB
- [x] `services/api/alembic/` setup + `alembic.ini`
- [x] Initial migration (`alembic revision --autogenerate -m "initial_schema"`)
- [x] `CREATE EXTENSION` SQL agents
- [x] ENUM types DDL
- [x] `users` table + indexes
- [x] `cameras` table + indexes
- [x] `stream_profiles` table
- [x] `discovery_scans` table
- [x] `storage_backends` table
- [ ] `recordings` hypertable + indexes + UNIQUE id
- [ ] `events` hypertable + indexes + UNIQUE id
- [ ] `event_rules` table
- [ ] `recording_schedules` table
- [ ] `storage_tiers` table
- [ ] `storage_migrations` table
- [ ] `discovery_log` table
- [ ] `notifications` table
- [ ] `notification_templates` table
- [ ] `alert_log` table
- [ ] `api_keys` table
- [ ] `audit_log` hypertable
- [x] `system_config` table
- [ ] `camera_ip_history` table
- [ ] `system_upgrades` table
- [ ] `audio_levels` hypertable
- [x] Migration down tested (`alembic downgrade -1` → `upgrade head`)

### 1.3 SQLAlchemy Models
- [x] `app/core/database.py` — async engine + session factory
- [x] `app/models/base.py` — declarative base
- [ ] `app/models/user.py`
- [x] `app/models/camera.py`
- [ ] `app/models/stream_profile.py`
- [ ] `app/models/discovery_scan.py`
- [ ] `app/models/storage_backend.py`
- [ ] `app/models/recording.py`
- [ ] `app/models/event.py`
- [ ] `app/models/event_rule.py`
- [ ] `app/models/recording_schedule.py`
- [ ] `app/models/storage_tier.py`
- [ ] `app/models/storage_migration.py`
- [ ] `app/models/discovery_log.py`
- [ ] `app/models/notification.py`
- [ ] `app/models/notification_template.py`
- [ ] `app/models/alert_log.py`
- [ ] `app/models/api_key.py`
- [ ] `app/models/audit_log.py`
- [x] `app/models/system_config.py`
- [ ] `app/models/camera_ip_history.py`
- [ ] `app/models/system_upgrade.py`
- [ ] `app/models/audio_level.py`

### 1.4 FastAPI Skeleton
- [x] `app/core/config.py` — Pydantic Settings (from env + DB)
- [x] `app/core/security.py` — JWT create/verify, password hashing
- [ ] `app/core/redis.py` — Redis async client
- [x] `app/middleware/auth.py` — JWT dependency + RBAC checker
- [x] `app/middleware/cors.py` — CORS middleware
- [ ] `app/middleware/logging.py` — Request logging + trace ID
- [x] `app/main.py` — FastAPI app factory, lifespan, exception handlers
- [x] `app/schemas/auth.py` — LoginRequest, TokenResponse
- [ ] `app/schemas/user.py` — UserCreate, UserResponse, UserUpdate
- [x] `app/schemas/camera.py` — CameraCreate, CameraResponse, CameraUpdate
- [x] `app/schemas/common.py` — PaginatedResponse, ErrorResponse
- [x] `app/api/v1/auth.py` — `/api/v1/auth/*` endpoints
- [ ] `app/api/v1/users.py` — `/api/v1/users/*` endpoints
- [x] `app/api/v1/system.py` — `/api/v1/system/*` endpoints
- [x] OpenAPI docs accessible at `/docs`

### 1.5 Auth & RBAC
- [x] `POST /api/v1/auth/login` — JWT issue
- [ ] `POST /api/v1/auth/refresh` — token refresh
- [ ] `POST /api/v1/auth/logout` — token blacklist
- [ ] `POST /api/v1/auth/api-keys` — create API key
- [ ] `GET /api/v1/auth/api-keys` — list keys
- [ ] `DELETE /api/v1/auth/api-keys/{id}` — revoke key
- [x] RBAC middleware: admin/operator/viewer role check
- [ ] Rate limiting (slowapi or custom)
- [ ] Camera password AES-256-GCM encrypt/decrypt service

### 1.6 Config Seed
- [x] `scripts/seed_db.py` finalized
- [x] Seed vendor_patterns.yml → `system_config` + vendor patterns cache
- [x] Seed default.yml → `system_config`
- [x] Create default admin user (admin/admin)

### 1.7 Web UI Skeleton
- [x] Vite + React + TypeScript setup
- [x] `npm install` dependencies: tailwindcss, radix-ui, tanstack-query, zustand, react-router, hls.js
- [x] `src/App.tsx` — Router + AuthProvider
- [x] `src/pages/Login.tsx`
- [x] `src/components/layout/AppShell.tsx` — sidebar + topbar layout
- [x] `src/components/layout/Sidebar.tsx`
- [x] `src/components/layout/Topbar.tsx`
- [x] `src/store/authStore.ts` — Zustand auth
- [x] `src/api/client.ts` — Axios/fetch wrapper + interceptors
- [x] `src/api/endpoints.ts` — API endpoint constants
- [x] `src/hooks/useAuth.ts`
- [x] Protected route wrapper component
- [x] Empty placeholder pages for most routes

### 1.8 CI/CD
- [x] `.github/workflows/ci.yml` verified
- [ ] Linting step: `ruff check` passes on all code
- [x] Testing step: `pytest` passes
- [ ] Docker build step: all images build

---

## Phase 2: Camera Integration (Week 3–4)

### 2.1 ONVIF Discovery
- [x] `onvif_scanner.py` — WS-Discovery multicast probe implementation
- [x] SOAP message construction / parsing
- [x] `GetDeviceInformation` → manufacturer, model, firmware
- [x] `GetCapabilities` → media, PTZ, events service URLs
- [x] `GetProfiles` → stream URIs, codec, resolution
- [ ] `GetNetworkInterfaces` → IP, MAC
- [x] ONVIF auth: WS-Security UsernameToken header
- [ ] Unit tests: mock ONVIF responses

### 2.2 RTSP Scanner
- [x] `rtsp_scanner.py` — TCP port connect scan
- [x] RTSP `OPTIONS` request → supported methods
- [x] RTSP `DESCRIBE` → SDP parse (codec, resolution, audio tracks)
- [x] Vendor detection from Server header
- [x] Concurrent scan with `asyncio.Semaphore`
- [x] Unit tests: mock RTSP server

### 2.3 HTTP Scanner
- [x] `http_scanner.py` — HTTP GET on common ports
- [x] Extract `Server` header
- [x] Extract `<title>` tag
- [x] Camera-specific path probing (`/cgi-bin/`, `/ISAPI/`, `/axis-cgi/`)
- [ ] Unit tests

### 2.4 ARP Scanner
- [x] `arp_scanner.py` finalized
- [x] Parse `/proc/net/arp`
- [x] MAC OUI → vendor lookup via fingerprinter
- [ ] Unit tests

### 2.5 mDNS Scanner
- [x] `mdns_scanner.py` — zeroconf library integration
- [x] Browse `_onvif._tcp`, `_axis-video._tcp`, `_rtsp._tcp`
- [x] Resolve hostname → IP
- [ ] Unit tests

### 2.6 Vendor Broadcast Scanner
- [x] `vendor_scanner.py` — Hikvision UDP port 37020
- [x] Dahua UDP port 37810
- [x] Response parsing + vendor identification
- [ ] Unit tests

### 2.7 Discovery Engine Integration
- [x] `engine.py` — 6-phase pipeline tested end-to-end
- [x] `engine_merge.py` — merge + dedup
- [x] Confidence scoring calibrated
- [x] Background task via FastAPI `BackgroundTasks`
- [x] `POST /api/v1/cameras/discover` endpoint
- [x] `GET /api/v1/cameras/discover/{scan_id}/status` endpoint
- [x] `GET /api/v1/cameras/discover/{scan_id}/results` endpoint
- [ ] Integration test: mock full network with fake cameras

### 2.8 Camera CRUD API
- [x] `app/schemas/camera.py` — all request/response schemas
- [x] `app/services/camera_service.py` — business logic
- [x] `app/services/discovery_service.py` — discovery orchestration
- [x] `GET /api/v1/cameras` — paginated, filtered, sorted list
- [x] `POST /api/v1/cameras` — manual add
- [x] `GET /api/v1/cameras/{id}` — detail with stream_profiles
- [x] `PATCH /api/v1/cameras/{id}` — partial update
- [x] `DELETE /api/v1/cameras/{id}` — with `keep_recordings` query param
- [x] `POST /api/v1/cameras/{id}/test` — connection test
- [ ] Integration tests for all CRUD endpoints

### 2.9 Stream Manager
- [x] `services/stream-manager/app/manager.py` — FFmpeg process lifecycle
- [x] FFmpeg subprocess spawn per camera (main + sub)
- [x] `_kill_ffmpeg()` — SIGTERM → 5s → SIGKILL
- [ ] `_monitor_ffmpeg()` — stderr parse, memory check
- [x] `_reconnect_camera()` — exponential backoff with jitter
- [ ] Singleton enforcement (zombie prevention)
- [ ] Restart cooldown (10 min)
- [ ] Circuit breaker per camera (30s→300s cooldown)
- [ ] Redis heartbeat: `nvr:component:stream-manager` TTL 120s
- [x] `nvr-mediamtx` integration (RTSP→WebRTC relay)
- [ ] Transport auto-fallback: tcp → udp → http
- [ ] Bandwidth monitor (FFmpeg progress bitrate read)
- [ ] Adaptive quality (auto-switch main↔sub stream)
- [ ] Multi-NIC binding support

### 2.10 Live View API
- [ ] `GET /api/v1/cameras/{id}/live` — WebSocket endpoint
- [ ] WebRTC signaling: offer/answer/ICE exchange
- [x] HLS fallback: `GET /api/v1/streams/{id}/live.m3u8`
- [ ] `POST /api/v1/cameras/{id}/snapshot` — JPEG capture
- [ ] Camera status push: online/offline/fps/resolution

### 2.11 Web UI — Camera Pages
- [x] `src/types/camera.ts` — TypeScript interfaces
- [x] `src/hooks/useCamera.ts` — TanStack Query hooks
- [ ] `src/hooks/useCameraLive.ts` — WebSocket live stream hook
- [ ] `src/store/cameraStore.ts` — grid, layout, selection
- [x] `src/pages/Cameras.tsx` — CRUD table
- [x] `src/components/camera/CameraForm.tsx` — add/edit dialog
- [x] `src/components/camera/DiscoveryDialog.tsx` — scan progress + results
- [x] `src/pages/Dashboard.tsx` — multi-camera grid
- [x] `src/components/camera/CameraGrid.tsx`
- [x] `src/components/camera/CameraTile.tsx` — live player + status
- [x] `src/components/live/LivePlayer.tsx` — WebRTC/HLS player
- [x] `src/pages/LiveView.tsx` — fullscreen single camera
- [ ] `src/pages/CameraDetail.tsx` — detail + live preview + settings

### 2.12 Camera Setup Wizard
- [ ] `src/pages/wizard/Welcome.tsx`
- [ ] `src/pages/wizard/AutoDiscovery.tsx` — scan progress
- [ ] `src/pages/wizard/ReviewDevices.tsx` — select + configure
- [ ] `src/pages/wizard/Credentials.tsx` — per-camera auth + test
- [ ] `src/pages/wizard/RecordingSettings.tsx`
- [ ] `src/pages/wizard/Ready.tsx` — summary

---

## Phase 3: Recording (Week 5–6)

### 3.1 Recording Engine Core
- [ ] `services/recording-engine/app/recorder.py` — `ContinuousRecorder`
- [ ] FFmpeg `-f segment` writer with 15-min segments
- [ ] Atomic segment rotation + metadata DB insert
- [ ] Stream duplication: connect to stream-manager relay or direct RTSP
- [ ] `services/recording-engine/app/motion.py` — OpenCV MOG2/KNN
- [ ] `services/recording-engine/app/scheduler.py` — cron-based schedule
- [ ] Pre-record buffer (5 sec) + post-record extension (10 sec)
- [ ] `services/recording-engine/app/retention.py` — auto-delete
- [ ] `services/recording-engine/app/tier_manager.py` — hot→warm→cold
- [ ] Corrupt segment recovery (`ffmpeg -err_detect ignore_err`)
- [ ] Redis heartbeat: `nvr:component:recording-engine` TTL 120s
- [ ] Circuit breaker per storage backend (120s→600s)
- [ ] Singleton enforcement + restart cooldown
- [ ] Unit tests: mock FFmpeg output, storage backend
- [ ] Integration tests: end-to-end record + verify

### 3.2 ONVIF Native Motion
- [ ] `ONVIFMotionHandler` — CreatePullPointSubscription
- [ ] PullMessages loop → motion event → recording trigger
- [ ] Fallback: server-side OpenCV when ONVIF motion unavailable
- [ ] Per-camera `motion_source` config: 'onvif' | 'server' | 'both'

### 3.3 Storage Backend Implementations
- [ ] `packages/common/nvr_common/storage.py` — `StorageBackend` ABC
- [ ] `LocalStorage` — POSIX file I/O with `aiofiles`
- [ ] `NFSStorage` — mount manager + file I/O
- [ ] `SMBStorage` — pysmb integration
- [ ] `S3Storage` — aiobotocore/minio integration
- [ ] `health_check()` — all backends
- [ ] `free_space()` / `total_space()` — all backends
- [ ] `read_stream()` / `write_stream()` — chunked I/O
- [ ] `move()` / `copy()` — with checksum verify
- [ ] Unit tests: each backend with temp directory/mock

### 3.4 Storage Tier Migration
- [ ] Migration scheduler (runs every hour)
- [ ] `emergency_cleanup()` — 4-level protocol
- [ ] Checksum verify (SHA-256, streaming)
- [ ] Crash recovery: resume pending migrations on startup
- [ ] Migration status tracking in DB
- [ ] Alert on migration failure

### 3.5 Storage API
- [ ] `app/services/storage_service.py`
- [ ] `GET /api/v1/storage/backends`
- [ ] `POST /api/v1/storage/backends`
- [ ] `GET /api/v1/storage/backends/{id}`
- [ ] `PATCH /api/v1/storage/backends/{id}`
- [ ] `DELETE /api/v1/storage/backends/{id}`
- [ ] `GET /api/v1/storage/backends/{id}/health`
- [ ] `GET /api/v1/storage/usage`
- [ ] `GET /api/v1/storage/tiers`
- [ ] `POST /api/v1/storage/tiers`

### 3.6 Recordings API
- [ ] `app/services/recording_service.py`
- [ ] `GET /api/v1/recordings` — paginated, filtered (date, camera, type)
- [ ] `GET /api/v1/recordings/{id}`
- [ ] `GET /api/v1/recordings/{id}/stream` — HTTP range + HLS fallback
- [ ] `DELETE /api/v1/recordings/{id}`
- [ ] `POST /api/v1/recordings/export`
- [ ] `GET /api/v1/recordings/export/{export_id}/status`
- [ ] `GET /api/v1/recordings/timeline`

### 3.7 Web UI — Recording Pages
- [ ] `src/types/recording.ts`
- [ ] `src/hooks/useRecording.ts`
- [ ] `src/store/recordingStore.ts`
- [ ] `src/pages/Recordings.tsx` — list + filters
- [ ] `src/components/recording/RecordingFilters.tsx`
- [ ] `src/components/recording/RecordingList.tsx`
- [ ] `src/components/recording/ExportDialog.tsx`
- [ ] `src/pages/Timeline.tsx` — 24h horizontal scroll
- [ ] `src/components/recording/RecordingPlayer.tsx` — hls.js playback

### 3.8 Web UI — Storage Pages
- [ ] `src/types/storage.ts`
- [ ] `src/hooks/useStorage.ts`
- [ ] `src/store/storageStore.ts`
- [ ] `src/pages/Storage.tsx`
- [ ] `src/components/storage/StorageBackendForm.tsx`

---

## Phase 4: AI & Advanced (Week 7–8)

### 4.1 AI Engine Core
- [ ] `services/ai-engine/app/detector.py` — YOLOv8n ONNX pipeline
- [ ] Frame consumer from Redis stream `nvr:frames:camera_{id}`
- [ ] Preprocessing: resize, normalize, BGR→RGB, to tensor
- [ ] Batch inference accumulator (merge frames from multiple cameras)
- [ ] Post-processing: NMS (IoU 0.45), confidence filter
- [ ] `services/ai-engine/app/face_recognition.py` — RetinaFace + ArcFace
- [ ] Face embedding DB (512-dim vector comparison, cosine similarity)
- [ ] `services/ai-engine/app/motion_detector.py` — frame-diff MOG2
- [ ] `services/ai-engine/app/audio_detector.py` — YAMNet
- [ ] FFmpeg audio extraction: 16kHz mono → YAMNet inference
- [ ] Model download/cache management
- [ ] Redis heartbeat: `nvr:component:ai-engine` TTL 120s
- [ ] Circuit breaker per model (30s→300s cooldown)
- [ ] GPU/CUDA provider auto-detect (ONNX)
- [ ] CPU fallback when GPU unavailable
- [ ] Unit tests: sample images, pre-recorded audio

### 4.2 Event Rules Engine
- [ ] `app/services/event_service.py`
- [ ] Event rule evaluation: confidence threshold, object class filter
- [ ] Zone-based detection (point-in-polygon)
- [ ] Schedule-based activation (time of day, day of week)
- [ ] Cooldown enforcement (no duplicate events within N seconds)
- [ ] Action dispatch: record trigger, notification, snapshot
- [ ] Audio level threshold rules
- [ ] Redis pub/sub: `nvr:events` channel

### 4.3 Events API
- [x] `GET /api/v1/events` — paginated, filtered
- [ ] `GET /api/v1/events/{id}`
- [ ] `PATCH /api/v1/events/{id}/acknowledge`
- [ ] `WS /api/v1/events/stream` — real-time event push
- [ ] Event rules CRUD endpoints (`GET/POST/PATCH/DELETE /api/v1/event-rules`)

### 4.4 PTZ Control
- [x] `app/services/camera_service_ptz.py`
- [x] ONVIF PTZ: `AbsoluteMove`, `RelativeMove`, `ContinuousMove`, `Stop`
- [x] Vendor-specific PTZ (Hikvision ISAPI, Dahua CGI, Axis VAPIX)
- [x] PTZ preset save/recall
- [x] `POST /api/v1/cameras/{id}/ptz`

### 4.5 Two-Way Audio Talkback
- [ ] `app/services/camera_service_audio.py`
- [ ] ONVIF `AddAudioEncoderConfiguration` + `AddAudioSourceConfiguration`
- [ ] FFmpeg: send audio to RTSP backchannel
- [ ] Vendor-specific talkback (Hikvision ISAPI TwoWayAudio, Dahua CGI)
- [ ] `POST /api/v1/cameras/{id}/talk` — start talk session
- [ ] `WS /api/v1/cameras/{id}/talk` — bidirectional audio WebSocket

### 4.6 Notification Service
- [ ] `services/notification-svc/` (or integrated in API)
- [ ] Email sender (SMTP + Jinja2 templates)
- [ ] Webhook dispatcher (HTTP POST with JSON body)
- [ ] Push notification (FCM)
- [ ] Notification template rendering (Jinja2)
- [ ] Circuit breaker per notification channel (300s→3600s)

### 4.7 MQTT Event Bridge
- [ ] `services/mqtt-bridge/` — subscribe to `nvr:events` Redis channel
- [ ] MQTT topic mapping: `nvr/cameras/{name}/motion`, etc.
- [ ] Snapshot JPEG publish per camera
- [ ] Home Assistant auto-discovery MQTT messages

### 4.8 Web UI — Event & AI Pages
- [x] `src/types/event.ts`
- [x] `src/hooks/useEvents.ts`
- [ ] `src/hooks/useEventStream.ts` — WebSocket real-time hook
- [ ] `src/store/eventStore.ts`
- [x] `src/pages/Events.tsx` — event feed
- [ ] `src/components/events/EventCard.tsx` — thumbnail + details
- [ ] `src/components/events/EventFilter.tsx`
- [ ] `src/components/events/EventDetailDrawer.tsx`
- [ ] `src/components/ai/DetectionZoneEditor.tsx` — zone polygon editor
- [ ] `src/components/ai/FaceLibrary.tsx` — known faces management
- [x] `src/components/camera/PTZControls.tsx` — directional pad + zoom
- [ ] `src/components/camera/TalkButton.tsx` — push-to-talk

### 4.9 Privacy Features
- [ ] Face blur filter (OpenCV GaussianBlur on face ROI)
- [ ] Privacy zone masking (overlay black rectangles on coordinates)
- [ ] Privacy mode toggle per camera (none / mask_zones / blur_faces)
- [ ] `POST /api/v1/compliance/delete-person-data` — right to deletion

---

## Phase 5: Production (Week 9–10)

### 5.1 Performance Optimization
- [ ] Profile API request hot paths (cProfile / py-spy)
- [ ] DB query optimization (EXPLAIN ANALYZE)
- [ ] Connection pool tuning (DB + Redis)
- [ ] FFmpeg hardware acceleration (VAAPI/NVENC) if GPU available
- [ ] AI model quantization (INT8) for CPU performance
- [ ] Lazy loading for recording segments in UI
- [ ] Image lazy loading in event feed
- [ ] Frontend code splitting (React.lazy)

### 5.2 Security Hardening
- [ ] TLS/HTTPS enforced (NGINX + Let's Encrypt)
- [ ] All passwords/secrets via Docker secrets or vault
- [ ] Rate limiting: per-endpoint limits configured
- [ ] Input validation audit (Pydantic strict mode)
- [ ] SQL injection audit (verify parameterized queries)
- [ ] XSS audit (React auto-escapes, check dangerouslySetInnerHTML)
- [ ] CSRF protection for API routes
- [ ] GDPR compliance: data export, deletion, audit trail
- [ ] Security headers audit (CSP, HSTS, X-Frame-Options)
- [ ] Penetration test (basic: OWASP ZAP scan)

### 5.3 Monitoring
- [ ] Prometheus metrics: `api_request_duration_seconds`, `camera_online_count`
- [ ] Prometheus metrics: `recording_bytes_written_total`, `storage_free_bytes`
- [ ] Prometheus metrics: `ffmpeg_process_count`, `ai_inference_duration_seconds`
- [ ] Grafana dashboard: System Overview (CPU, RAM, disk, cameras)
- [ ] Grafana dashboard: Recording Status (active recordings, errors, storage)
- [ ] Grafana dashboard: AI Performance (inference time, detection rate)
- [ ] Alert rules: camera offline > 2 min
- [ ] Alert rules: storage > 90%
- [ ] Alert rules: recording engine crash
- [ ] Alert rules: API error rate > 1%

### 5.4 Backup & Recovery
- [ ] `scripts/backup.sh` — `pg_dump -Fc` + S3 upload
- [ ] TimescaleDB WAL-G continuous archiving
- [ ] AI model backup (versioned)
- [ ] Backup retention: daily x 7, weekly x 4, monthly x 12
- [ ] `scripts/restore.sh` — step-by-step recovery guide
- [ ] Recovery test: restore from backup, verify data integrity

### 5.5 Upgrade/Rollback
- [ ] `system_upgrades` table tracking
- [ ] Pre-upgrade checklist (backup completed, health check green)
- [ ] Canary upgrade (1 instance → health check → all)
- [ ] Rollback procedure: old image tag + backup restore
- [ ] Upgrade test: upgrade → verify → rollback → verify

### 5.6 Self-Test / Diagnostics
- [ ] `POST /api/v1/system/self-test`
- [ ] Database connectivity + latency check
- [ ] Redis connectivity + latency check
- [ ] MinIO connectivity + latency check
- [ ] FFmpeg version + availability check
- [ ] Disk space per backend check
- [ ] Camera stream test (per camera: connect, read 1 frame, disconnect)

### 5.7 IPv6 Support
- [ ] INET type handles IPv4+IPv6 (DB already supports)
- [ ] ONVIF IPv6 multicast discovery (ff02::c)
- [ ] mDNS IPv6 multicast (ff02::fb)
- [ ] RTSP over IPv6 URL format support
- [ ] NGINX IPv6 listen directive
- [ ] Docker IPv6 network config

### 5.8 PWA Mobile Support
- [ ] Service Worker setup (vite-plugin-pwa)
- [ ] Offline cache: AppShell, static assets
- [ ] Push notification Web API
- [ ] Install prompt (manifest.json + icons)
- [ ] Touch-optimized UI (larger hit targets, swipe gestures)
- [ ] Mobile camera grid (responsive: 1x1 default, 2x2 max)

### 5.9 Testing
- [ ] Unit tests: ALL services — target >80% line coverage
- [ ] Integration tests: ALL API endpoints with test DB
- [ ] E2E tests: Playwright for critical workflows
  - [ ] Login → Dashboard → Camera Grid
  - [ ] Add Camera (manual) → Verify in list
  - [ ] Camera Discovery → Select → Add
  - [ ] Recording Playback → Timeline scrub
  - [ ] Event filter → Acknowledge
- [ ] Load test: artillery/k6 — 32 cameras simulation
- [ ] Stress test: camera offline/online churn, storage full scenario
- [ ] `pytest --cov=services --cov-report=term-missing --cov-fail-under=80`

### 5.10 Documentation
- [ ] `docs/API.md` — OpenAPI auto-generated + manual examples
- [ ] `docs/DEPLOYMENT.md` — production deployment step-by-step
- [ ] `docs/DEVELOPMENT.md` — local dev setup + architecture overview
- [ ] `docs/ARCHITECTURE.md` — Architecture Decision Records (ADR)
- [x] `README.md` — project overview exists
- [ ] `CHANGELOG.md` — version history

### 5.11 Production Deploy
- [ ] `docker-compose.prod.yml` finalized
- [ ] Production `.env` generated (strong secrets)
- [ ] TLS certificates (Let's Encrypt certbot)
- [ ] Backup schedule configured (cron)
- [ ] Monitoring alerts configured
- [ ] Health check endpoint verified
- [ ] Production smoke test: all cameras streaming + recording
- [ ] `docker compose -f docker-compose.prod.yml up -d`
- [ ] 24-hour burn-in: zero crashes, zero data loss

---

## Phase 6: Future (v1.1+)

- [ ] Horizontal scaling: multiple stream-manager instances
- [ ] GPU inference pool (load-balanced AI workers)
- [ ] Kubernetes migration (k3s single-node)
- [ ] Mobile native app (React Native)
- [ ] Cloud backup integration (AWS S3 Glacier, Backblaze B2)
- [ ] License plate recognition (LPR/ANPR)
- [ ] People counting + heatmap analytics
- [ ] Multi-site NVR federation (parent ↔ child NVR sync)

---

*Last updated: 2026-07-23*
*Total tasks: ~300+*
