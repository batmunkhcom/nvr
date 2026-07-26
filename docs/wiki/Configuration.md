# Configuration

## System Config Keys

All values editable via Settings page UI. Stored in `system_config` table as JSONB.

### Storage

| Key | Default | Description |
|-----|---------|-------------|
| `storage.max_usage_percent` | `85` | Disk % at which circular cleanup triggers |
| `storage.min_free_gb` | `2` | Free GB floor for circular cleanup |
| `storage.analysis` | (computed) | Hourly GB/day + days-fit analytics |

### Recording

| Key | Default | Description |
|-----|---------|-------------|
| `recording.segment_seconds` | `300` | MP4 segment duration |
| `recording.stream` | `sub` | Which stream to record (sub/main) |
| `recording.motion_stop_delay_s` | `30` | Idle seconds before stopping motion recorder |

### Retention

| Key | Default | Description |
|-----|---------|-------------|
| `retention.default_days` | `7` | Age-based deletion threshold (days) |

### AI

| Key | Default | Description |
|-----|---------|-------------|
| `ai.enabled` | `false` | Global AI toggle |
| `ai.confidence_threshold` | `0.5` | Per-camera default (overridden by `ai_min_confidence`) |

### UI

| Key | Default | Description |
|-----|---------|-------------|
| `ui.dashboard_columns` | `2` | Grid column count (persisted per user) |
| `ui.sidebar_collapsed` | `false` | Sidebar state |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password | (required) |
| `JWT_SECRET_KEY` | JWT signing secret | (required) |
| `NVR_ENCRYPTION_KEY` | AES-256-GCM key for camera passwords | (required) |
| `STORAGE_LOCAL_PATH` | Container path for recordings | `/data/recordings` |
| `STORAGE_HOST_PATH` | Host path bind-mounted to container `STORAGE_LOCAL_PATH` | `/data` |
| `MEDIAMTX_RTSP` | MediaMTX RTSP endpoint | `rtsp://nvr-mediamtx:8554` |
| `MEDIAMTX_HLS_URL` | MediaMTX HLS origin | (configure in .env) |
| `STREAM_MANAGER_URL` | Stream manager HTTP | `http://nvr-stream-manager:8001` |
| `STREAM_IDLE_TIMEOUT_S` | Idle reaper timeout | `600` (10 min) |
| `AI_MODEL_PATH` | ONNX model directory | `/app/models` |
| `AI_YOLO_MODEL` | ONNX model filename | `yolov8n.onnx` |
| `AI_DEVICE` | ONNX provider | `cpu` |

---

## Per-Camera AI Config

| Field | Type | Description |
|-------|------|-------------|
| `ai_enabled` | boolean | Enable/disable AI detection |
| `ai_objects` | JSON array | COCO classes: `["person", "car", ...]` (80 total) |
| `ai_zones` | JSON array | Polygon zones: `[{"name": "...", "points": [[x,y], ...]}]` |
| `ai_sensitivity` | string | MOG2 threshold: `low` (40), `medium` (25), `high` (16) |
| `ai_min_confidence` | float | Confidence threshold, clamped 0.05–0.95 |

---

## Tuning Recommendations

### High Performance (Current — v0.01.15)
- AI FPS: 0.5 (was 2)
- Sub-stream bitrate: 1000k (was 2000k)
- MOG2 sensitivity: low (was medium)
- ONNX threads: 1 (was 2)
- AI engine CPU limit: 2 cores (was 4)

### Storage Planning
- Motion recording: ~5-8 GB/day per camera
- Continuous recording: ~26 GB/day per camera (main stream)
- 7-day retention at 85% disk triggers circular cleanup
- DiskAnalytics projects days-fit based on current rate
