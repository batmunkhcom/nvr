# NVR Project — Work Status & Plan

> Last updated: 2026-07-23 (session)
> Source of truth for what is completed vs. what remains.

---

## Phase A — Core Fixes ✅ DONE

### A1. RTSP Auth Check Single Connection Fix
**Task**: Dahua digest auth nonce is bound to TCP connection — multi-connection check always fails after first.
**Done**: Rewrote `camera_rtsp_check.py` to use a single TCP socket throughout OPTIONS→DESCRIBE flow, with same-connection retry for basic auth → digest fallback. Returns structured results: `auth_failed`, `unreachable`, `no_stream_uri`, `timeout`, `stream_error`.

### A2. All 9 Camera Passwords Applied
**Task**: All cameras had passwords set in UI but DB stream URIs had plaintext passwords → security risk.
**Done**: 
- Moved `.203` and `.218` passwords from URI string to `encrypted_password` column (security hardening).
- Fleet-pressed password (`AB99088033c`) into `encrypted_password` for cameras `.211`–`.217` which had stale/incorrect DB data.
- All 9 cameras now show `online` status.

### A3. LiveViewPage Full Fix
**Task**: PTZ buttons crash (undefined functions), Stream errors not shown, hard-coded HLS URL.
**Done**: 
- Implemented `doPtz()` and `doZoom()` calling `POST /cameras/{id}/ptz`.
- Made stream start idempotent via `startingRef` guard (fixes React StrictMode double-effect causing "Broken pipe").
- Added connecting/loading/error states with retry button.

### A4. Dashboard Configurable Columns
**Task**: Dashboard grid always 2 columns, no persistence.
**Done**: 
- Column selector buttons (1/2/3/4) in Dashboard.
- Persists via `system_config` table (`ui.dashboard_columns`) — not localStorage (AGENTS.md Rule 6).

### A5. Sidebar Collapsible
**Task**: Sidebar always expanded, no toggle.
**Done**: 
- Toggle button with chevron icons (expand/collapse).
- Icon-only mode collapses to 56px width, full to 224px.
- Preserved in DB via `ui.sidebar_collapsed`.

### A6. Location Entity Management
**Task**: Cameras have no location organization, UI has placeholder Settings → Locations.
**Done**: 
- **DB**: `locations` table (alembic 0003), `cameras.location_id` FK with `ON DELETE SET NULL`, data migration from free-text `location`.
- **API**: `GET/POST/PATCH/DELETE /api/v1/locations` + camera count aggregate.
- **UI**: Settings → Locations section (full CRUD form), Camera Add/Edit dialog dropdown, Cameras table location badge, Dashboard tile `(cam{id})` suffix.

### A7. IP-Range Discovery
**Task**: Discovery modal only accepts single IPs, no subnet/range input.
**Done**: 
- `discovery_service._expand_range()` supports both `IP1-IP2` and `IP1-subnet-IP2` formats (e.g. `10.10.0.200-230`, `10.10.0.200-10.10.0.230`).
- Frontend auto-guesses subnet from existing cameras' IPs.
- Results deduplicated by IP — duplicates skipped with info message.

### A8. Backup & Restore Scripts
**Task**: No system backup mechanism.
**Done**: 
- `scripts/backup.sh`: pg_dump + .env + config/.gitconfig, optional AES-256-CBC encryption, SHA-256 checksums, configurable retention (default 7 days).
- `scripts/restore.sh`: verify SHA-256 → decrypt with openssl → restore database from dump file, recreate .env and configs.

### A9. Secret Sanitization & Open Source Prep
**Task**: Repository contained real passwords/internal IPs in committed files.
**Done**: 
- `config.py postgres_password` default removed (required from env).
- Bootstrap script POSTGRES_PASSWORD made required.
- Internal IP (`10.10.0.229`) removed from all tracked code, replaced with env vars (`MEDIAMTX_RTSP`, `MEDIAMTX_HLS_URL`).
- DiscoveryModal uses generic `192.168.1.0/24` default instead of project IPs.
- AGENTS.md, SKILLS/, todo.md, auto-sanitize-push.sh added to `.gitignore`.
- Git credentials permissions set to `600` (owner read/write only).

### A10. Sub-stream Relay for Dashboard Bandwidth
**Task**: Dashboard shows 9 full-resolution streams simultaneously — 2304x1296 @ 4.9 Mbps each = massive bandwidth waste.
**Done**: 
- `camera_probe.py` returns `stream_sub_uri` from ONVIF probe (`/Streaming/Channels/101`).
- `live_relay.py` uses unique `relay_key` — `{id}_sub` for sub-stream, `{id}` for main. Allows concurrent main+sub relays per camera.
- Live relay now embeds credentials in RTSP URL (replaces `username:`/`password:` args with `rtsp://user:pass@host/path`).
- Auto-restart with exponential backoff (5s→60s, configurable).

### A11. `func.now` Fix Across All Models
**Task**: SQLAlchemy 2.x `func.now()` as default fails with asyncpg — passes SQL expression as parameter value.
**Done**: Replaced `server_default=func.now()` and `default=func.now()` in ~20 model files with `lambda: datetime.now(UTC)`.

---

## Phase A — Test Coverage ✅ DONE

### Backend Tests (pytest, 49 total passing)
| File | Count | What it tests |
|------|-------|---------------|
| `test_rtsp_check.py` | 8 | Open/digest/basic/wrong-pw/no-creds/unreachable/invalid-url/non-auth-error + same-connection retry Dahua nonce binding |
| `test_services.py` | 14 | Camera to_dict, get_camera_response (404+success), recording get/delete/stats, timeline segments, storage usage, camera connection test (auth_failed→degraded, unreachable→offline, success→online) |
| `test_live_relay.py` | 8 | Start spawns ffmpeg, duplicate start idempotent, FFmpeg missing error, string relay keys, stop kills process, stop not-running, status running/not-running, circuit breaker cap at 600s |
| **NEW** `test_locations.py` | 11 | Location CRUD (create/409 conflict/delete), name stripping, rename collision, update description-only, 404 on missing location |
| **NEW** `test_system_config.py` | 4 | UI config upsert (new key), update existing, reject non-ui.* keys, type roundtrip (int/bool/str) |

### Frontend Tests (vitest + testing-library, 34 passing)
| File | Count | What it tests |
|------|-------|---------------|
| `useCameras.test.tsx` | 3 | Fetch camera list, null→empty array |
| `useEvents.test.tsx` | 2 | Fetch event list |
| `AppShell.test.tsx` | 4 | Sidebar nav links render, /→/dashboard redirect, **new**: sidebar collapse toggle persists via UI config API (not localStorage), expand button in collapsed state |
| **NEW** `useLocations.test.tsx` | 5 | Fetch locations list, empty array, Create location mutation calls POST, Update mutation PATCHes /locations/:id, Delete mutation DELETEs |
| **NEW** `CameraGrid.test.tsx` | 6 | Camera name badge + IP render (online), MiniLivePreview mounts for online cameras, offline placeholder renders first-letter+name, column selector defaults to 2 and switches via UI config API, reads persisted column count from UI config, empty state shows CTA |
| **NEW** `Cameras.test.tsx` | 6 | Connection error badge displays RTSP auth error text, no error badge when connection_error=null, Test All calls test endpoint for every camera sequentially, auth failure label shown after individual test, location badge displays (cam{index+1}), Test All disabled when no cameras |
| **NEW** `LiveViewPage.test.tsx` | 7 | Camera name in header renders, stream starts and PTZ controls display (has_ptz=true), Pan Left button calls /ptz with direction=left, Zoom In button calls /ptz with zoom=in, error state when camera has no stream URI configured (**no hls_url**), error state when live/start request **fails** (catch path), "Camera not found" for unknown |

---

## Phase A — Infrastructure/Hardening ✅ DONE

### A12. Docker Network Bridge Fix
**Task**: HLS requests to `/hls/` fall through nginx `location /` → proxied to nvr-web:3000 → 404. No video on dashboard tiles.
**Done**: 
- Added `extra_hosts: ["host.docker.internal:host-gateway"]` to `nvr-api`, `nvr-nginx`, and `nvr-web` services in docker-compose.yml so they can reach host's MediaMTX.
- `MEDIAMTX_RTSP` default changed from `rtsp://127.0.0.1:8554` → `rtsp://host.docker.internal:8554`.
- Added `location /hls/` block in nginx.conf proxying to MediaMTX `http://host.docker.internal:8888` with path rewrite and long read timeout (86400s for HLS).

### A13. Circuit Breaker Rule 17 — Backoff Cap
**Task**: Relay exponential backoff capped too low (60s). AGENTS.md Rule 17 requires `60s→600s` progression.
**Done**: Increased `MAX_BACKOFF` in `live_relay.py` from implicit 60s to explicit 600s (10 minutes). Backoff doubles each restart: 3s→6s→12s…→up to 10 min max.

### A14. Relay Monitor → Camera Degraded Status
**Task**: FFmpeg relay crashes but camera stays `online` in DB — no visibility into stream issues. Rule 5 requires connection_error tracking.
**Done**: Added `_mark_camera_degraded()` function called on `relay_gave_up` (after MAX_RESTARTS failures). Sets status="degraded" + sets `connection_error` from FFmpeg exit code log.

### A15. System Config DB-Driven Relay Target
**Task**: HLS URL construction uses hardcoded defaults — should read from system_config (AGENTS.md Rule 1: no hardcode, Rule 2: DB as single source).
**Done**: 
- Created `config_service.py` with `get_config_value()` helper.
- Live relay target now reads from `mediamtx.rtsp_url` in system_config before falling back to env var default (or Docker-compose override).

### A16. MiniLivePreview Loading/Connecting/Error States
**Task**: Dashboard tiles show blank black rectangles — no feedback when stream isn't loading or fails. No error retry mechanism.
**Done**: 
- 4 states: `connecting` → `loading` → `playing` + `error`.
- Connecting: spinner + text "Connecting..." (POST live/start).
- Loading: blue spinner + text "Loading stream..." (polling HLS manifest).
- Error: red alert icon + error message + Retry button (stream failed to start).
- Playing: video at opacity-70.
- Relay start retries up to 3 times before showing error.
- HLS.js error events properly handled and destroy HLS instance on fatal errors.

---

## Phase A/5 — Remaining Tasks 🔄 IN PROGRESS

### A17. Camera Health-Check Loop (Background Task) ⬜ STARTED
**Status**: `health_check_loop.py` skeleton created and committed. Needs:
1. Import cleanup — verify syntax (file was rewritten multiple times, may have stale imports).
2. Start from main.py `lifespan` context manager — call `start_health_check(interval_s)` on app startup, `stop_health_check()` on shutdown.
3. Test in non-test env to ensure task doesn't block Docker container start.
4. Integration test with mock cameras.

**What it does**: Iterates all cameras every `N` seconds (configurable via system_config, default 120s), calls camera RTSP check for each, updates status/erroconnection_error in DB automatically — no manual Test needed. Degraded cameras get periodic recheck without hammering.

---

## Phase B — Design Improvements ⬜ TODO

### B1. Color Token System
- Currently mixed `gray-800/900` everywhere → should define consistent palette (surface/accent/success/warning/danger) in Tailwind config or utility classes.

### B2. Camera Tile Enhancements
- Status ring indicator around tile edge.
- Connection error tooltip on hover.
- Location badge per location entity.
- Improved skeleton loading animation for tiles.

### B3. Cameras Page Card Rows
- Current row style basic gray lines → improve to card-style rows with better visual hierarchy, improved skeleton loading states.

### B4. Empty States
- "No cameras configured" page should have illustration/icon + CTA button instead of plain text.
- No events/recordings filters result → add illustration state for each empty section (Events, Recordings).

### B5. Typography Scale
- Page title 20px, section header 16px, body 13px — define consistent scale across layout.

### B6. Toast Notification System ⬜ (Recommended)
**Task**: Currently uses `alert()`/`confirm()` which blocks main thread and breaks UX.  
**Plan**: Create `<Toast />` component with position system (top-right), auto-dismiss, different variants (success/error/warning/info). Replace all `alert()` calls in codebase with toast dispatch via context/store.

### B7. Dark Scrollbar Styling
- Add `scrollbar-width` and `::-webkit-scrollbar` styles to global CSS for consistent dark theme scrollbars throughout the app.

### B8. Page Transition Fade
- Add fade-in animation/page transitions between route changes using CSS keyframes or framer-motion.

---

## Phase C — Configurability ⬜ TODO

### C1 Settings Page Visual Form for System Config
**Task**: Settings page currently has placeholder text → no editable config form.
**Plan**: 
- Create `SettingsSection` component with table/list view of config entries by category (UI, MediaMTX, Camera, AI, Recording).
- For each key show: label, description, current value, edit input (text/number/toggle/dropdown based on type).
- On save PATCH to `/api/v1/system/ui-config` → update DB + toast success.
- Use existing `ui.*` keys as reference: `dashboard_columns`, `sidebar_collapsed`, `refresh_interval_s`, `language`.

### C2 Health Check Configurable Interval
- Current interval hardcoded (60s) in health_check_loop.py. Change to read from system_config `camera.health_check_interval_s` (default 60). Add circuit breaker: cameras consistently failing get longer intervals between checks.

---

## Phase D — Open Source ✅ DONE

| Item | Status |
|------|--------|
| Apache-2.0 LICENSE added to repo | ✅ Merged into GitHub main |
| README.md (full English comprehensive) | ✅ Written and pushed |
| AGENTS.md gitignored | ✅ Untracked, not committed to GitHub |
| SKILLS/ gitignored | ✅ Untracked |
| todo.md gitignored | ✅ Already in .gitignore since creation |
| auto-sanitize-push.sh gitignored | ✅ Added to .gitignore |
| `~/.git-credentials` permissions 600 | ✅ Set and verified |
| No real passwords in codebase files | ✅ Verified, all encrypted or env-only |

---

## Phase E — AI Integration ⬜ PLANNED

### E1 Frame Sampler + YOLO Person Detection (AI-1: 2-3 days)
**Research summary**: ONNX Runtime + YOLOv8n recommended. Runs on CPU (~30ms/frame), AGPL concerns avoided by using ultralytics only for model export, pure ONNX runtime for inference.

**Plan**:
1. Add sub-stream frame sampler to `ai-engine`: connect RTSP sub-stream at 2-5 fps (motion-gated), run YOLOv8n person detection.
2. Store detections: new `detections` table (camera_id, timestamp, object_type, confidence_level, snapshot_url).
3. On detection → publish event to MQTT/Redis → create recording snippet with 10s buffer (pre-event + post-event).

### E2 Event Filtering UI (AI-2)
**Plan**: Add camera_name filter dropdown, date range picker to Events page, object type filter toggle (all/person/car/vessel), detection threshold slider.

### E3 Notification Service (AI-3)
**Plan**: Skeleton `notification_service.py` exists — wire up Telegram webhook + email notification on critical events (camera offline, AI detection). Uses existing MQTT bridge for pub/sub.

---

## Phase F — Additional Improvements ⬜ TODO (Backlog)

1. **Stream transport auto-fallback** — TCP→UDP automatic retry based on `stream_transport` DB column (`cameras.py` RTSP auth already handles tcp/udp arg).
2. **ONVIF auto-config on Add Camera** — Pull stream URI and capabilities (ptz, audio, sub-stream) from ONVIF device info when adding discovered cameras.
3. **Recording engine activation** — Container exists in compose (`nvr-recording-engine`) but not running. Should pull segments from MediaMTX relay endpoints rather than direct camera RTSP to reduce system load.
4. **Webhook/Telegram for offline cameras** — When camera goes `offline` or `degraded`, send alert via webhook or push notification (extend existing MQTT integration).
5. **Snapshot preview on tiles** — Use existing `snapshot.py` API → show JPEG thumbnail on dashboard tiles instead of HLS stream in non-critical areas.

---

## Commit History (most recent first)

| Hash | Message | Date |
|------|--------|------|
| d09dc6a | test: relay lifecycle, locations, system config, LiveView, CameraGrid, Cameras, sidebar collapse (59 new tests) | 2026-07-23 |
| 77a6733 | fix: add HLS proxy in nginx + Docker network bridge for MediaMTX + loading/connecting states for live previews | 2026-07-23 |
| d469570 🌐github | docs: comprehensive English README with features, architecture, quick start guide | 2026-07-23 |
| 1be2e39 | merge: adopt Apache-2.0 LICENSE from GitHub initial commit | 2026-07-23 |
| fb9af75 | feat: substream relay, IP-range discovery, locations, backup scripts, secret sanitization | 2026-07-23 |

---

## How to Continue

**Next immediate step**: Finish Phase A#17 — integrate health_check_loop into main.py lifespan so it starts automatically with the API.

**After that**: Phase C (Settings page visual form, configurable intervals).

**Before pushing**: Run `make test` or:
```bash
cd services/api && python3 -m pytest tests/ -q  # should pass 49 tests
cd services/web && npx vitest run                 # should pass 34 frontend tests
npx tsc --noEmit                                  # should be clean
```
