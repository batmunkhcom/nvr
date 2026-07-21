# NVR System — Хөгжүүлэлтийн TODO

> **Status legend:** `[ ]` not started, `[~]` in progress, `[x]` done, `[-]` blocked/not applicable

---

## Phase 0: Төсөл Эхлүүлэлт

### 0.1 Git & Project
- [x] `AGENTS.md` — AI хөгжүүлэлтийн чиглүүлэг
- [x] `docs/PLAN.md` — Архитектур төлөвлөгөө (2,791 lines)
- [x] `docs/todo.md` — Энэ файл
- [x] `config/default.yml` — Default system config
- [x] `config/vendor_patterns.yml` — Camera fingerprint DB (11 vendor)
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
- [ ] `git init & first commit & push`

---

## Phase 1: Foundation (Week 1–2)

### 1.1 Docker Compose
- [ ] `docker-compose.yml` — бүх 11 үйлчилгээ (api, stream-manager, mediamtx, recording-engine, ai-engine, db, redis, minio, mosquitto, mqtt-bridge, nginx, web, chrony)
- [ ] `docker-compose.prod.yml` — production override
- [ ] `config/mediamtx.yml` — MediaMTX configuration
- [ ] `config/mosquitto.conf` — MQTT broker config
- [ ] `docker/api/Dockerfile` — FastAPI image
- [ ] `docker/stream-manager/Dockerfile` — Stream manager image
- [ ] `docker/recording-engine/Dockerfile` — Recording engine image
- [ ] `docker/ai-engine/Dockerfile` — AI engine image
- [ ] `docker/web/Dockerfile` — React dev + production
- [ ] `docker/nginx/Dockerfile` — NGINX reverse proxy
- [ ] `docker/mqtt-bridge/Dockerfile` — MQTT event bridge
- [ ] `docker-compose up` амжилттай ажиллах

### 1.2 PostgreSQL + TimescaleDB
- [ ] `services/api/alembic/` setup + `alembic.ini`
- [ ] Initial migration (`alembic revision --autogenerate -m "initial_schema"`)
- [ ] `CREATE EXTENSION` SQL agents
- [ ] ENUM types DDL
- [ ] `users` table + indexes
- [ ] `cameras` table + indexes
- [ ] `stream_profiles` table
- [ ] `discovery_scans` table
- [ ] `storage_backends` table
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
- [ ] `system_config` table
- [ ] `camera_ip_history` table
- [ ] `system_upgrades` table
- [ ] `audio_levels` hypertable
- [ ] Migration down tested (`alembic downgrade -1` → `upgrade head`)

### 1.3 SQLAlchemy Models
- [ ] `app/core/database.py` — async engine + session factory
- [ ] `app/models/base.py` — declarative base
- [ ] `app/models/user.py`
- [ ] `app/models/camera.py`
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
- [ ] `app/models/system_config.py`
- [ ] `app/models/camera_ip_history.py`
- [ ] `app/models/system_upgrade.py`
- [ ] `app/models/audio_level.py`

### 1.4 FastAPI Skeleton
- [ ] `app/core/config.py` — Pydantic Settings (from env + DB)
- [ ] `app/core/security.py` — JWT create/verify, password hashing
- [ ] `app/core/redis.py` — Redis async client
- [ ] `app/middleware/auth.py` — JWT dependency + RBAC checker
- [ ] `app/middleware/cors.py` — CORS middleware
- [ ] `app/middleware/logging.py` — Request logging + trace ID
- [ ] `app/main.py` — FastAPI app factory, lifespan, exception handlers
- [ ] `app/schemas/auth.py` — LoginRequest, TokenResponse
- [ ] `app/schemas/user.py` — UserCreate, UserResponse, UserUpdate
- [ ] `app/schemas/camera.py` — CameraCreate, CameraResponse, CameraUpdate
- [ ] `app/schemas/common.py` — PaginatedResponse, ErrorResponse
- [ ] `app/api/v1/auth.py` — `/api/v1/auth/*` endpoints
- [ ] `app/api/v1/users.py` — `/api/v1/users/*` endpoints
- [ ] `app/api/v1/system.py` — `/api/v1/system/*` endpoints
- [ ] OpenAPI docs accessible at `/docs`

### 1.5 Auth & RBAC
- [ ] `POST /api/v1/auth/login` — JWT issue
- [ ] `POST /api/v1/auth/refresh` — token refresh
- [ ] `POST /api/v1/auth/logout` — token blacklist
- [ ] `POST /api/v1/auth/api-keys` — create API key
- [ ] `GET /api/v1/auth/api-keys` — list keys
- [ ] `DELETE /api/v1/auth/api-keys/{id}` — revoke key
- [ ] RBAC middleware: admin/operator/viewer role check
- [ ] Rate limiting (slowapi or custom)
- [ ] Camera password AES-256-GCM encrypt/decrypt service

### 1.6 Config Seed
- [ ] `scripts/seed_db.py` finalized
- [ ] Seed vendor_patterns.yml → `system_config` + vendor patterns cache
- [ ] Seed default.yml → `system_config`
- [ ] Create default admin user (admin/admin)

### 1.7 Web UI Skeleton
- [ ] `npx create vite@latest . --template react-ts` setup
- [ ] `npm install` dependencies: tailwindcss, radix-ui, tanstack-query, zustand, react-router, hls.js
- [ ] `src/App.tsx` — Router + AuthProvider
- [ ] `src/pages/Login.tsx`
- [ ] `src/components/layout/AppShell.tsx` — sidebar + topbar layout
- [ ] `src/components/layout/Sidebar.tsx`
- [ ] `src/components/layout/Topbar.tsx`
- [ ] `src/store/authStore.ts` — Zustand auth
- [ ] `src/api/client.ts` — Axios/fetch wrapper + interceptors
- [ ] `src/api/endpoints.ts` — API endpoint constants
- [ ] `src/hooks/useAuth.ts`
- [ ] Protected route wrapper component
- [ ] Empty placeholder pages for all 14 routes

### 1.8 CI/CD
- [ ] `.github/workflows/ci.yml` verified
- [ ] Linting step: `ruff check` passes on all code
- [ ] Testing step: `pytest` passes
- [ ] Docker build step: all images build

---

## Phase 2: Camera Integration (Week 3–4)

### 2.1 ONVIF Discovery
- [ ] `onvif_scanner.py` — WS-Discovery multicast probe implementation
- [ ] SOAP message construction / parsing
- [ ] `GetDeviceInformation` → manufacturer, model, firmware
- [ ] `GetCapabilities` → media, PTZ, events service URLs
- [ ] `GetProfiles` → stream URIs, codec, resolution
- [ ] `GetNetworkInterfaces` → IP, MAC
- [ ] ONVIF auth: WS-Security UsernameToken header
- [ ] Unit tests: mock ONVIF responses

### 2.2 RTSP Scanner
- [ ] `rtsp_scanner.py` — TCP port connect scan
- [ ] RTSP `OPTIONS` request → supported methods
- [ ] RTSP `DESCRIBE` → SDP parse (codec, resolution, audio tracks)
- [ ] Vendor detection from Server header
- [ ] Concurrent scan with `asyncio.Semaphore`
- [ ] Unit tests: mock RTSP server

### 2.3 HTTP Scanner
- [ ] `http_scanner.py` — HTTP GET on common ports
- [ ] Extract `Server` header
- [ ] Extract `<title>` tag
- [ ] Camera-specific path probing (`/cgi-bin/`, `/ISAPI/`, `/axis-cgi/`)
- [ ] Unit tests

### 2.4 ARP Scanner
- [ ] `arp_scanner.py` finalized (currently skeleton)
- [ ] Parse `/proc/net/arp`
- [ ] MAC OUI → vendor lookup via fingerprinter
- [ ] Unit tests

### 2.5 mDNS Scanner
- [ ] `mdns_scanner.py` — zeroconf library integration
- [ ] Browse `_onvif._tcp`, `_axis-video._tcp`, `_rtsp._tcp`
- [ ] Resolve hostname → IP
- [ ] Unit tests

### 2.6 Vendor Broadcast Scanner
- [ ] `vendor_scanner.py` — Hikvision UDP port 37020
- [ ] Dahua UDP port 37810
- [ ] Response parsing + vendor identification
- [ ] Unit tests

### 2.7 Discovery Engine Integration
- [ ] `engine.py` — 6-phase pipeline tested end-to-end
- [ ] `engine_merge.py` — merge + dedup tested
- [ ] Confidence scoring calibrated
- [ ] Background task via FastAPI `BackgroundTasks`
- [ ] `POST /api/v1/cameras/discover` endpoint
- [ ] `GET /api/v1/cameras/discover/{scan_id}/status` endpoint
- [ ] `GET /api/v1/cameras/discover/{scan_id}/results` endpoint
- [ ] Integration test: mock full network with fake cameras

### 2.8 Camera CRUD API
- [ ] `app/schemas/camera.py` — бүх request/response schemas
- [ ] `app/services/camera_service.py` — business logic
- [ ] `app/services/discovery_service.py` — discovery orchestration
- [ ] `GET /api/v1/cameras` — paginated, filtered, sorted list
- [ ] `POST /api/v1/cameras` — manual add
- [ ] `GET /api/v1/cameras/{id}` — detail with stream_profiles
- [ ] `PATCH /api/v1/cameras/{id}` — partial update
- [ ] `DELETE /api/v1/cameras/{id}` — with `keep_recordings` query param
- [ ] `POST /api/v1/cameras/{id}/test` — connection test
- [ ] Integration tests for all CRUD endpoints

### 2.9 Stream Manager
- [ ] `services/stream-manager/app/manager.py` — FFmpeg process lifecycle
- [ ] FFmpeg subprocess spawn per camera (main + sub)
- [ ] `_kill_ffmpeg()` — SIGTERM → 5s → SIGKILL
- [ ] `_monitor_ffmpeg()` — stderr parse, memory check
- [ ] `_reconnect_camera()` — exponential backoff with jitter
- [ ] Singleton enforcement (zombie prevention)
- [ ] Restart cooldown (10 min)
- [ ] Circuit breaker per camera (30s→300s cooldown)
- [ ] Redis heartbeat: `nvr:component:stream-manager` TTL 120s
- [ ] `nvr-mediamtx` integration (RTSP→WebRTC relay)
- [ ] Transport auto-fallback: tcp → udp → http
- [ ] Bandwidth monitor (FFmpeg progress bitrate read)
- [ ] Adaptive quality (auto-switch main↔sub stream)
- [ ] Multi-NIC binding support

### 2.10 Live View API
- [ ] `GET /api/v1/cameras/{id}/live` — WebSocket endpoint
- [ ] WebRTC signaling: offer/answer/ICE exchange
- [ ] HLS fallback: `GET /api/v1/streams/{id}/live.m3u8`
- [ ] `POST /api/v1/cameras/{id}/snapshot` — JPEG capture
- [ ] Camera status push: online/offline/fps/resolution

### 2.11 Web UI — Camera Pages
- [ ] `src/types/camera.ts` — TypeScript interfaces
- [ ] `src/hooks/useCamera.ts` — TanStack Query hooks
- [ ] `src/hooks/useCameraLive.ts` — WebSocket live stream hook
- [ ] `src/store/cameraStore.ts` — grid, layout, selection
- [ ] `src/pages/Cameras.tsx` — CRUD table
- [ ] `src/components/camera/CameraForm.tsx` — add/edit dialog
- [ ] `src/components/camera/DiscoveryDialog.tsx` — scan progress + results
- [ ] `src/pages/Dashboard.tsx` — multi-camera grid
- [ ] `src/components/camera/CameraGrid.tsx`
- [ ] `src/components/camera/CameraTile.tsx` — live player + status
- [ ] `src/components/live/LivePlayer.tsx` — WebRTC/HLS player
- [ ] `src/pages/LiveView.tsx` — fullscreen single camera
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
- [ ] `GET /api/v1/events` — paginated, filtered
- [ ] `GET /api/v1/events/{id}`
- [ ] `PATCH /api/v1/events/{id}/acknowledge`
- [ ] `WS /api/v1/events/stream` — real-time event push
- [ ] Event rules CRUD endpoints (`GET/POST/PATCH/DELETE /api/v1/event-rules`)

### 4.4 PTZ Control
- [ ] `app/services/camera_service_ptz.py`
- [ ] ONVIF PTZ: `AbsoluteMove`, `RelativeMove`, `ContinuousMove`, `Stop`
- [ ] Vendor-specific PTZ (Hikvision ISAPI, Dahua CGI, Axis VAPIX)
- [ ] PTZ preset save/recall
- [ ] `POST /api/v1/cameras/{id}/ptz`

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
- [ ] `src/types/event.ts`
- [ ] `src/hooks/useEvents.ts`
- [ ] `src/hooks/useEventStream.ts` — WebSocket real-time hook
- [ ] `src/store/eventStore.ts`
- [ ] `src/pages/Events.tsx` — event feed
- [ ] `src/components/events/EventCard.tsx` — thumbnail + details
- [ ] `src/components/events/EventFilter.tsx`
- [ ] `src/components/events/EventDetailDrawer.tsx`
- [ ] `src/components/ai/DetectionZoneEditor.tsx` — zone polygon editor
- [ ] `src/components/ai/FaceLibrary.tsx` — known faces management
- [ ] `src/components/camera/PTZControls.tsx` — directional pad + zoom
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
- [ ] Backup retention: daily × 7, weekly × 4, monthly × 12
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
- [ ] Mobile camera grid (responsive: 1×1 default, 2×2 max)

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
- [ ] `README.md` finalized — quick start, screenshots, features
- [ ] `CHANGELOG.md` — version history

### 5.11 Production Deploy
- [ ] `docker-compose.prod.yml` finalized
- [ ] Production `.env` generated (strong secrets)
- [ ] TLS certificates (Let's Encrypt certbot)
- [ ] Backup schedule configured (cron)
- [ ] Monitoring alerts configured
- [ ] Health check endpoint verified
- [ ] Production smoke test: all 8 cameras streaming + recording
- [ ] `docker compose -f docker-compose.prod.yml up -d`
- [ ] 24-hour burn-in: zero crashes, zero data loss

---

### Phase 6: Future (v1.1+)

- [ ] Horionztal scaling: multiple stream-manager instances
- [ ] GPU inference pool (load-balanced AI workers)
- [ ] Kubernetes migration (k3s single-node)
- [ ] Mobile native app (React Native)
- [ ] Cloud backup integration (AWS S3 Glacier, Backblaze B2)
- [ ] License plate recognition (LPR/ANPR)
- [ ] People counting + heatmap analytics
- [ ] Multi-site NVR federation (parent ↔ child NVR sync)

---

*Сүүлд шинэчилсэн: 2026-07-21*
*Total tasks: ~300+*
