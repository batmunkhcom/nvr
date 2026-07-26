# NVR AI Plugin System — Implementation TODO

> Last updated: 2026-07-26
> Status legend: `[ ]` not started, `[~]` in progress, `[x]` done
> Per-camera enable: `cameras.ai_plugins` JSONB array + `cameras.lpr_config` JSONB

---

## Phase 1 — Core Plugin Infrastructure

### 1.1 Plugin Interface & Registry
- [ ] `services/ai-engine/app/plugins/__init__.py` — plugin registry, load order, `get_plugins_for_camera()`
- [ ] `services/ai-engine/app/plugins/base.py` — `AIPlugin` ABC: `name`, `on_detection()`, `start()`, `stop()`
- [ ] `services/ai-engine/app/main.py:_build_worker()` — pass `ai_plugins` list to FrameSampler
- [ ] `services/ai-engine/app/frame_sampler.py:FrameSampler.__init__()` — accept `plugins: list[AIPlugin]`
- [ ] `services/ai-engine/app/frame_sampler.py:_consume()` — call `plugins[i].on_detection()` after YOLO, before `_persist()`
- [ ] `services/ai-engine/app/frame_sampler.py:start()/stop()` — start/stop each plugin

### 1.2 DB Migration
- [ ] `services/api/alembic/versions/0009_ai_plugins.py` — add `ai_plugins` JSONB to `cameras`
- [ ] `services/api/alembic/versions/0009_ai_plugins.py` — add `lpr_config` JSONB to `cameras`
- [ ] `services/api/alembic/versions/0009_ai_plugins.py` — create `object_counters` table
- [ ] `services/api/alembic/versions/0009_ai_plugins.py` — create `license_plates` table
- [ ] `services/api/alembic/versions/0009_ai_plugins.py` — create `smart_alerts` table
- [ ] `services/api/alembic/versions/0009_ai_plugins.py` — run migration & verify in DB

### 1.3 Camera Schema Update
- [ ] `services/api/app/schemas/camera.py:CameraCreate` — add `ai_plugins: list[str] | None`, `lpr_config: dict | None`
- [ ] `services/api/app/schemas/camera.py:CameraUpdate` — add same fields
- [ ] `services/api/app/schemas/camera.py:CameraResponse` — add `ai_plugins`, `lpr_config`
- [ ] `services/api/app/models/camera.py` — add `ai_plugins` Column(JSONB), `lpr_config` Column(JSONB)
- [ ] `services/api/app/services/camera_service.py` — save new fields on create/update
- [ ] `services/ai-engine/app/db.py:load_ai_cameras()` — include `ai_plugins`, `lpr_config` in SELECT

### 1.4 Plugin Config Verification
- [ ] `services/ai-engine/app/main.py` — validate `ai_plugins` values against known plugin names
- [ ] Warning log when unknown plugin name in config → skip (no crash)
- [ ] Test: per-camera plugin enable/disable works correctly

---

## Phase 2 — Counter Plugin

### 2.1 Plugin Implementation
- [ ] `services/ai-engine/app/plugins/counter.py` — `CounterPlugin(AIPlugin)` class
- [ ] `counter.py` — `CATEGORY_MAP`: `person→person`, `vehicle→[car,truck,bus,motorcycle,bicycle]`, `animal→[cat,dog,bird]`, `livestock→[horse,sheep,cow,elephant,bear,zebra,giraffe]`
- [ ] `counter.py` — `_counts: dict[str, dict[str, int]]` in-memory counters `{camera_id: {category: count}}`
- [ ] `counter.py` — `_last_event_ts: dict[str, dict[str, float]]` dedup per category per camera
- [ ] `counter.py` — `on_detection()` — increment counters, per-category dedup (5s MIN_EVENT_GAP_S)
- [ ] `counter.py` — `_flush_loop()` — async loop every 60s upsert to `object_counters` via `db.SessionFactory`
- [ ] `counter.py` — `start()` / `stop()` — start/stop flush loop

### 2.2 Counter API Endpoints
- [ ] `services/api/app/api/v1/counters.py` — router `prefix="/api/v1/counters"`
- [ ] `counters.py:GET /summary` — `?camera_id=` `&days=7` → `{person, vehicle, animal, livestock}`
- [ ] `counters.py:GET /hourly` — `?camera_id=` `&date=2025-07-26` → `[{hour, person, vehicle, ...}]`
- [ ] `counters.py:GET /comparison` — `?camera_id_a=xxx&camera_id_b=yyy&date=` → side-by-side
- [ ] `services/api/app/services/counter_service.py` — DB aggregation queries
- [ ] `services/api/app/api/v1/__init__.py` — include counters router

### 2.3 Counter Frontend
- [ ] `services/web/src/hooks/useCounters.ts` — `useCounterSummary()`, `useCounterHourly()`
- [ ] `services/web/src/pages/Statistics.tsx` — new page with hourly/daily graphs (Recharts)
- [ ] `services/web/src/components/statistics/CounterCards.tsx` — 4 stat cards (person/vehicle/animal/livestock)
- [ ] `services/web/src/components/statistics/HourlyChart.tsx` — bar/line chart per category
- [ ] `services/web/src/pages/Dashboard.tsx` — add CounterCards row below camera grid
- [ ] WebSocket invalidate `["counters", "summary"]` on detection event

---

## Phase 3 — LPR Plugin (License Plate Recognition)

### 3.1 Pattern Library
- [ ] `services/ai-engine/app/plugins/lpr_patterns.py` — `LPR_PATTERNS` dict with 8+ countries
- [ ] `lpr_patterns.py` — Mongolia: `[А-Я]{3}\s?\d{4}` + `\d{4}\s?[А-Я]{3}`
- [ ] `lpr_patterns.py` — Europe: `[A-Z]{2,3}\s?\d{2,4}\s?[A-Z]{0,3}`
- [ ] `lpr_patterns.py` — USA: `[A-Z]{1,3}[-\s]?\d{4,7}`
- [ ] `lpr_patterns.py` — Japan: `[^\W_]+[\s-]?\d{1,4}[\s-]?[^\W_]+[\s-]?\d{1,4}`
- [ ] `lpr_patterns.py` — China: `[А-Я]{1,2}[A-Z]\s?[·]?\d{5}`
- [ ] `lpr_patterns.py` — Russia: `[А-Я]{1,3}\d{3,4}[А-Я]{2,3}\s?\d{2,3}`
- [ ] `lpr_patterns.py` — South Korea: `[^\W_]+[\s-]?\d{1,2}[^\W_][\s-]?\d{4}`
- [ ] `lpr_patterns.py` — Custom: user-defined regex support

### 3.2 PaddleOCR Setup
- [ ] Add paddlepaddle + paddleocr to `services/ai-engine/requirements.txt` or Dockerfile
- [ ] Test PaddleOCR inference on sample car images (Cyrillic accuracy check)
- [ ] If PaddleOCR too heavy: fallback to EasyOCR or Tesseract via env var `OCR_ENGINE`
- [ ] Download PaddleOCR models to `/app/models/paddleocr/` (persistent volume)

### 3.3 LPR Plugin Implementation
- [ ] `services/ai-engine/app/plugins/lpr.py` — `LPRPlugin(AIPlugin)` class
- [ ] `lpr.py` — `on_detection()` — filter vehicle detections only (car/truck/bus/motorcycle)
- [ ] `lpr.py` — `_crop_plate()` — crop lower 30% of vehicle bbox from frame
- [ ] `lpr.py` — `_ocr_read()` — run PaddleOCR on cropped region → raw text
- [ ] `lpr.py` — `_match_pattern()` — regex match against selected country pattern
- [ ] `lpr.py` — `_validate_confidence()` — OCR confidence ≥ `lpr_config.min_confidence`
- [ ] `lpr.py` — `_persist_plate()` — insert into `license_plates` table
- [ ] `lpr.py` — Dedup: same plate_number + same camera → skip if within 120s
- [ ] `lpr.py` — Check blacklist/whitelist on match → trigger smart alert if needed

### 3.4 LPR API Endpoints
- [ ] `services/api/app/api/v1/lpr.py` — router `prefix="/api/v1/lpr"`
- [ ] `lpr.py:GET /patterns` — return all country patterns
- [ ] `lpr.py:POST /cameras/{id}/lpr` — update `lpr_config` on camera
- [ ] `lpr.py:GET /readings` — `?camera_id=` `&days=7` `&plate_number=` → readings list
- [ ] `lpr.py:GET /blacklist` — `?active=true` → blacklist entries
- [ ] `lpr.py:POST /blacklist` — add plate to blacklist `{plate_number, reason}`
- [ ] `lpr.py:DELETE /blacklist/{id}` — remove from blacklist
- [ ] `services/api/app/services/lpr_service.py` — DB operations + blacklist management
- [ ] `services/api/app/api/v1/__init__.py` — include LPR router

### 3.5 LPR Frontend
- [ ] Camera settings dialog — add LPR section (enable toggle, pattern dropdown, confidence slider, custom regex input)
- [ ] `services/web/src/hooks/useLPR.ts` — `useLPRReadings()`, `useLPRPatterns()`, `useLPRBlacklist()`
- [ ] `services/web/src/pages/LPRReadings.tsx` — table: plate_number, camera, time, confidence, snapshot
- [ ] `services/web/src/components/lpr/BlacklistManager.tsx` — CRUD for blacklisted plates
- [ ] Real-time LPR alert: WebSocket `nvr:lpr` channel → toast notification for blacklist match

---

## Phase 4 — Smart Alerts Plugin

### 4.1 Rule Engine
- [ ] `services/ai-engine/app/plugins/smart_alerts.py` — `SmartAlertsPlugin(AIPlugin)` class
- [ ] `smart_alerts.py` — `_load_rules()` — load active rules from DB at start + every 60s
- [ ] `smart_alerts.py` — `on_detection()` — evaluate each rule against detection result
- [ ] `smart_alerts.py` — Rule types: `time_based`, `frequency`, `blacklist_lpr`, `zone_violation`, `dwell_time`, `crowd_detection`
- [ ] `smart_alerts.py` — `_eval_time_based()` — time window check (e.g. 23:00-06:00)
- [ ] `smart_alerts.py` — `_eval_frequency()` — rolling window counter (e.g. >10 vehicles in 5 min)
- [ ] `smart_alerts.py` — `_eval_blacklist_lpr()` — plate match against blacklist (called from LPR plugin)
- [ ] `smart_alerts.py` — `_eval_zone_violation()` — zone polygon logic (reuse FrameSampler._filter_zones)
- [ ] `smart_alerts.py` — `_eval_dwell_time()` — object stationary > threshold (reuse position dedup)
- [ ] `smart_alerts.py` — `_eval_crowd()` — unique person count in last N seconds > threshold
- [ ] `smart_alerts.py` — `_trigger_alert()` — insert into `smart_alerts` table + notify channels

### 4.2 Notification Channels
- [ ] `services/api/app/services/notifications/__init__.py` — `send_notification(channel, payload)` dispatcher
- [ ] `services/api/app/services/notifications/telegram.py` — HTTP POST to Telegram Bot API
- [ ] `services/api/app/services/notifications/slack.py` — Slack incoming webhook
- [ ] `services/api/app/services/notifications/email.py` — SMTP with snapshot attachment
- [ ] `services/api/app/services/notifications/sms.py` — Twilio or local SMS gateway
- [ ] Configuration via `system_config` table (webhook URLs, API keys)

### 4.3 Smart Alerts API
- [ ] `services/api/app/api/v1/smart_alerts.py` — router `prefix="/api/v1/smart-alerts"`
- [ ] `smart_alerts.py:GET /rules` — list rules `?camera_id=`
- [ ] `smart_alerts.py:POST /rules` — create rule
- [ ] `smart_alerts.py:PATCH /rules/{id}` — update rule
- [ ] `smart_alerts.py:DELETE /rules/{id}` — delete rule
- [ ] `smart_alerts.py:GET /triggers` — `?camera_id=` `&days=7` `&severity=`
- [ ] `smart_alerts.py:POST /test-notification` — test notification delivery
- [ ] `services/api/app/services/alert_service.py` — rule CRUD + trigger queries

### 4.4 Smart Alerts Frontend
- [ ] `services/web/src/pages/AlertRules.tsx` — rule list + create/edit form
- [ ] `services/web/src/components/alerts/RuleForm.tsx` — rule type selector, conditions builder
- [ ] `services/web/src/components/alerts/AlertFeed.tsx` — real-time alert feed (toast + sidebar)
- [ ] `services/web/src/hooks/useSmartAlerts.ts` — `useAlertRules()`, `useAlertTriggers()`

---

## Phase 5 — Dashboard & Statistics UI

### 5.1 Statistics Page
- [ ] `services/web/src/pages/Statistics.tsx` — new page: date picker, camera filter, category filter
- [ ] `services/web/src/pages/Statistics.tsx` — hourly bar chart (Recharts BarChart)
- [ ] `services/web/src/pages/Statistics.tsx` — daily trend line chart (Recharts LineChart)
- [ ] `services/web/src/pages/Statistics.tsx` — summary cards row
- [ ] `services/web/src/pages/Statistics.tsx` — export CSV button
- [ ] Add route in `App.tsx` → `/statistics`
- [ ] Add sidebar link in `Sidebar.tsx` → Statistics (icon: BarChart3)

### 5.2 Dashboard Enrichment
- [ ] `services/web/src/pages/Dashboard.tsx` — add 4 CounterCards row below existing stat cards
- [ ] WebSocket invalidate `["counters", "summary"]` on `nvr:events` detection events
- [ ] `services/web/src/components/statistics/CounterCards.tsx` — animated stat cards (person/vehicle/animal/livestock)

### 5.3 Sidebar & Navigation
- [ ] Add "Statistics" menu item in `Sidebar.tsx`
- [ ] Add "LPR Readings" menu item (icon: CarFront)
- [ ] Add "Alert Rules" menu item (icon: BellRing)
- [ ] Add "Plugins" menu item under Settings (icon: Puzzle)
- [ ] Conditional visibility: LPR/Plugins only visible if any camera has them enabled

---

## Phase 6 — Advanced Plugins

### 6.1 Heat Map Plugin
- [ ] `services/ai-engine/app/plugins/heat_map.py` — `HeatMapPlugin`
- [ ] Accumulate detection positions → normalized heatmap array per camera
- [ ] Flush to `heat_map_data` table hourly (composite image + hotspots JSON)
- [ ] `services/api/app/api/v1/heatmaps.py` — `GET /{camera_id}?date=`
- [ ] Frontend: heatmap overlay on camera live view (toggle button)

### 6.2 People Analytics Plugin
- [ ] `services/ai-engine/app/plugins/people_analytics.py` — `PeopleAnalyticsPlugin`
- [ ] Dwell time tracking (person in same position > X seconds)
- [ ] Crowd detection (unique person count > threshold)
- [ ] Peak hours identification
- [ ] Direction tracking (line-crossing entry/exit)
- [ ] `services/api/app/api/v1/people_analytics.py` — dwell, peak-hours, crowd endpoints

### 6.3 Vehicle Analytics Plugin
- [ ] `services/ai-engine/app/plugins/vehicle_analytics.py` — `VehicleAnalyticsPlugin`
- [ ] Vehicle type breakdown counts (car/truck/bus/motorcycle)
- [ ] Direction tracking (line-crossing left→right, right→left)
- [ ] Flow rate (vehicles per hour)
- [ ] `services/api/app/api/v1/vehicle_analytics.py` — breakdown, flow-rate endpoints

### 6.4 Animal Detection Plugin
- [ ] `services/ai-engine/app/plugins/animal_detection.py` — `AnimalDetectionPlugin`
- [ ] Species classification (cat/dog/bird/horse/sheep/cow)
- [ ] Stray animal alert (night-time detection)
- [ ] `services/api/app/api/v1/animal_detection.py` — species breakdown endpoint

### 6.5 Multi-Camera Tracking Plugin
- [ ] `services/ai-engine/app/plugins/multi_camera_tracking.py`
- [ ] Re-identification (ReID) — extract visual embeddings per detection
- [ ] Store embeddings in Redis with TTL (60s)
- [ ] Cosine similarity matching across cameras (>0.75 threshold)
- [ ] Route tracking — timeline of camera IDs for same object
- [ ] `services/api/app/api/v1/tracking.py` — route, gateway-count endpoints

### 6.6 Facial Recognition Plugin (Opt-In)
- [ ] `services/ai-engine/app/plugins/facial_recognition.py` — `FacialRecognitionPlugin`
- [ ] Face detection (RetinaFace / dlib)
- [ ] Face embedding (ArcFace 128-dim vector)
- [ ] Gallery matching against `face_gallery` table via pgvector
- [ ] Migration: `face_gallery` + `face_matches` tables
- [ ] Privacy: explicit opt-in per camera, encrypted data at rest
- [ ] `services/api/app/api/v1/facial_recognition.py` — gallery CRUD, match list

### 6.7 Behavior Analysis Plugin
- [ ] `services/ai-engine/app/plugins/behavior_analysis.py` — `BehaviorAnalysisPlugin`
- [ ] Running detection (rapid position change between frames)
- [ ] Falling detection (horizontal person bbox detection)
- [ ] Loitering detection (person stationary in zone > X seconds)
- [ ] Theft detection (object disappears from known location)
- [ ] `services/api/app/api/v1/behavior.py` — events endpoint

### 6.8 Safety Compliance Plugin
- [ ] `services/ai-engine/app/plugins/safety_compliance.py` — `SafetyCompliancePlugin`
- [ ] Helmet detection (fine-tuned model or YOLO transfer learning)
- [ ] Vest detection (high-visibility color detection)
- [ ] PPE compliance (helmet + vest AND)
- [ ] `services/api/app/api/v1/safety.py` — compliance stats endpoint

---

## Phase 7 — Export & Reports

### 7.1 Export Service
- [ ] `services/api/app/services/report_service.py` — CSV generation (counters, LPR, events)
- [ ] `services/api/app/services/report_service.py` — PDF generation (WeasyPrint / ReportLab)
- [ ] `services/api/app/api/v1/reports.py:GET /export` — `?type=counters&camera_id=$1&format=csv&from=$2&to=$3`
- [ ] `services/api/app/api/v1/reports.py:GET /scheduled` — list scheduled reports
- [ ] `services/api/app/api/v1/reports.py:POST /scheduled` — create scheduled report (email, freq, format)
- [ ] `services/api/app/api/v1/reports.py:DELETE /scheduled/{id}` — delete schedule

### 7.2 Report Frontend
- [ ] `services/web/src/pages/Reports.tsx` — export form: type, camera, date range, format
- [ ] Download button triggers file download
- [ ] Scheduled reports management table

---

## Phase 8 — Plugin Manager

### 8.1 Plugin Health & Monitoring
- [ ] `services/ai-engine/app/plugins/health.py` — `PluginHealth` tracker
- [ ] CPU/RAM usage per plugin (psutil or cgroups)
- [ ] Uptime, event count, error count per plugin
- [ ] Auto-restart crashed plugins
- [ ] `services/ai-engine/app/main.py` — health check loop (30s interval)

### 8.2 Plugin Manager API
- [ ] `services/api/app/api/v1/plugins.py` — router `prefix="/api/v1/plugins"`
- [ ] `plugins.py:GET /` — list all plugins: name, enabled, camera_count, cpu_pct, status
- [ ] `plugins.py:PATCH /{name}/config` — update plugin settings
- [ ] `plugins.py:GET /{name}/health` — detailed health metrics
- [ ] `plugins.py:POST /{name}/restart` — manual restart

### 8.3 Plugin Manager Frontend
- [ ] `services/web/src/pages/Plugins.tsx` — plugin list with status badges (green/yellow/red)
- [ ] Enable/disable toggle per plugin system-wide
- [ ] Per-camera plugin config sub-section
- [ ] Resource usage display (CPU %, RAM MB)
- [ ] Restart button per plugin

---

## Quality & Testing

### Unit Tests
- [ ] `services/api/tests/test_counter_plugin.py` — category mapping, flush, dedup
- [ ] `services/api/tests/test_lpr_plugin.py` — pattern matching, OCR mock, dedup
- [ ] `services/api/tests/test_smart_alerts.py` — rule evaluation, time windows, thresholds
- [ ] `services/api/tests/test_counter_api.py` — summary/hourly/comparison endpoints
- [ ] `services/api/tests/test_lpr_api.py` — readings, blacklist CRUD

### Integration Tests
- [ ] End-to-end: camera detection → counter plugin → DB → API → frontend
- [ ] End-to-end: camera detection → LPR plugin → OCR → match → API → frontend
- [ ] WebSocket: counter + alert updates pushed to frontend
- [ ] Notification delivery: Telegram, Slack, Email test

### Performance
- [ ] CPU: Counter only → <1% per camera
- [ ] CPU: Counter + LPR → <12% per camera
- [ ] CPU: All plugins → <25% per camera (capped via `ai_plugins`)
- [ ] Memory: <50MB overhead for all plugins combined
- [ ] DB: aggregation queries under 100ms for 30-day range

---

## Documentation

- [ ] `docs/ai-plugin-architecture.md` — done (full architecture)
- [ ] `docs/ai-plugin-api.md` — API reference for all plugin endpoints
- [ ] `docs/ai-plugin-development.md` — how to create a new plugin (developer guide)
- [ ] `docs/ai-lpr-patterns.md` — pattern library reference + how to add a country
- [ ] `AGENTS.md` — update with plugin architecture section
- [ ] `README.md` — add plugin system feature highlight

---

## Deployment Checklist

- [ ] Dockerfile: add PaddleOCR + paddlepaddle dependencies
- [ ] Dockerfile: increase AI engine memory limit from 2G → 4G (optional, per plugin load)
- [ ] `docker-compose.yml`: add `AI_PLUGINS=counter,lpr,smart_alerts` env to `nvr-ai-engine`
- [ ] `docker-compose.yml`: volume mount `paddleocr_models:/app/models/paddleocr`
- [ ] Run migrations: `alembic upgrade head`
- [ ] Seed default plugin config for existing cameras (empty `ai_plugins` = backward compatible)
- [ ] Health check: verify AI engine starts with plugins enabled
- [ ] Log check: `docker logs nvr-ai-engine` → no plugin-related errors

---

## Summary Counts

| Phase | Tasks | Plugins Covered |
|-------|-------|----------------|
| Phase 1 (Core) | 18 | Infrastructure |
| Phase 2 (Counter) | 16 | counter |
| Phase 3 (LPR) | 29 | lpr |
| Phase 4 (Smart Alerts) | 25 | smart_alerts |
| Phase 5 (Dashboard) | 10 | UI |
| Phase 6 (Advanced) | 20 | heat_map, people_analytics, vehicle_analytics, animal_detection, multi_camera_tracking, facial_recognition, behavior_analysis, safety_compliance |
| Phase 7 (Export) | 7 | export_reports |
| Phase 8 (Manager) | 12 | plugin_manager |
| Testing | 9 | All |
| Docs | 6 | N/A |
| Deploy | 8 | N/A |
| **Total** | **160** | **14 plugins** |
