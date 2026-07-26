# mBm NVR AI Plugin Architecture

## Overview

The mBm NVR system uses a **plugin-based architecture** for AI-powered analytics. Plugins are modular, independent modules that can be enabled/disabled per camera without modifying the core AI engine code. This design enables:

- **Extensibility:** Add new features by creating a plugin in `services/ai-engine/app/plugins/`
- **Per-camera configuration:** Each camera independently chooses which plugins to run
- **Resource control:** Heavy plugins (LPR, facial recognition) only run on selected cameras
- **Global scalability:** Pattern-based LPR supports any country's license plate format

---

## Architecture

### Core Flow

```
RTSP Sub-stream → FrameSampler (0.5 FPS, motion-gated)
                        │
                        ▼
                AIDetector (YOLOv8 ONNX)
                        │
                        ▼ detections: [{class, confidence, box}]
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
    _persist() → DB + Redis   Plugins[i].on_detection()
              │                    │
              │              CounterPlugin, LPRPlugin, etc.
              │                    │
              └────┬─────────────┘
                   ▼
            event_callback → Redis pub (nvr:events)
```

### Plugin Interface

```python
class AIPlugin:
    """Base class for all AI engine plugins."""
    
    name: str = "base"           # Unique identifier
    enabled: bool = True         # Global toggle
    
    async def on_detection(
        self,
        camera_id: str,
        detections: list[dict],  # [{class, confidence, box}]
        frame: np.ndarray,       # Full BGR frame
        timestamp: datetime,     # Event time
    ) -> None:
        """Called after YOLO detection, before DB persistence."""
        pass
    
    async def start(self) -> None:
        """One-time init at engine startup (load models, connect DB)."""
        pass
    
    async def stop(self) -> None:
        """Cleanup on shutdown."""
        pass
```

### Camera Configuration

New field in `cameras` table:

```json
{
  "ai_enabled": true,
  "ai_objects": ["person", "car", "truck", "bus", "motorcycle", "bicycle"],
  "lpr_config": {
    "enabled": false,
    "pattern": "mongolia",
    "custom_regex": null,
    "min_confidence": 0.75
  },
  "ai_plugins": ["counter", "lpr"]   // Which plugins to run
}
```

### Database Schema

#### `lpr_config` JSONB column on `cameras` table

```sql
ALTER TABLE cameras ADD COLUMN lpr_config JSONB 
    DEFAULT '{"enabled": false, "pattern": "mongolia", "custom_regex": null, "min_confidence": 0.75}';
```

#### `license_plates` table

```sql
CREATE TABLE license_plates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id UUID NOT NULL REFERENCES cameras(id),
    plate_number VARCHAR(20) NOT NULL,
    country_code VARCHAR(3),           -- 'MN', 'EU', 'US', 'JP'
    pattern_name VARCHAR(50),          -- 'mongolia', 'europe', 'usa'
    confidence FLOAT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    snapshot_path TEXT,                -- Full frame with plate highlighted
    plate_image_path TEXT              -- Cropped plate image
);

CREATE INDEX idx_lpr_camera_time ON license_plates(camera_id, detected_at DESC);
CREATE INDEX idx_lpr_number ON license_plates(plate_number);
```

#### `object_counters` table

```sql
CREATE TABLE object_counters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id UUID NOT NULL REFERENCES cameras(id),
    object_category VARCHAR(32) NOT NULL,  -- 'person', 'vehicle', 'animal', 'livestock'
    counter_date DATE NOT NULL,
    hour INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
    count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(camera_id, object_category, counter_date, hour)
);

CREATE INDEX idx_counters_camera_time ON object_counters(camera_id, counter_date DESC);
```

#### `smart_alerts` table

```sql
CREATE TABLE smart_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id UUID NOT NULL REFERENCES cameras(id),
    rule_name VARCHAR(100) NOT NULL,
    rule_type VARCHAR(50) NOT NULL,        -- 'time_based', 'frequency', 'blacklist_lpr', 'zone_violation'
    severity VARCHAR(20) DEFAULT 'warning', -- 'info', 'warning', 'critical'
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    details JSONB,                         -- Rule-specific context
    acknowledged BOOLEAN DEFAULT FALSE,
    snapshot_path TEXT
);

CREATE INDEX idx_alerts_camera_time ON smart_alerts(camera_id, triggered_at DESC);
```

---

## Plugin Library

### 1. Counter Plugin (`counter`)

Counts detected objects by category and persists hourly aggregates.

#### Object Categories (from COCO classes)

| Category | COCO Classes |
|----------|-------------|
| `person` | `person` |
| `vehicle` | `car`, `truck`, `bus`, `motorcycle`, `bicycle` |
| `animal` | `cat`, `dog`, `bird` |
| `livestock` | `horse`, `sheep`, `cow`, `elephant`, `bear`, `zebra`, `giraffe` |

#### Flush Strategy

- In-memory counters: `_counts[camera_id][category] = int`
- Flush interval: Every 60 seconds
- Dedup: Same as FrameSampler cooldown (5s MIN_EVENT_GAP_S)
- Upsert into `object_counters` table with `ON CONFLICT ... DO UPDATE`

#### API Endpoints

```
GET /api/v1/counters/summary?camera_id=xxx&days=7
→ {"data": {
     "person": 142,
     "vehicle": 89,
     "animal": 5,
     "livestock": 2
   }}

GET /api/v1/counters/hourly?camera_id=xxx&date=2025-07-26
→ {"data": [
     {"hour": 8, "person": 12, "vehicle": 3},
     {"hour": 9, "person": 18, "vehicle": 7}
   ]}

GET /api/v1/counters/comparison?camera_id_a=xxx&camera_id_b=yyy&date=2025-07-26
→ {"data": {
     "camera_a": {...},
     "camera_b": {...}
   }}
```

#### Frontend Components

- **Dashboard stat cards:** Live counters updated via WebSocket
- **Statistics page:** Recharts line/bar graphs (hourly, daily, weekly)
- **Export CSV/PDF:** Download reports

---

### 2. LPR Plugin (`lpr`)

License Plate Recognition with pattern-based regex matching for international support.

#### Pattern Library (`lpr_patterns.py`)

| Country | Code | Format Examples | Regex Pattern |
|---------|------|-----------------|---------------|
| **Монгол** | MN | `УБЛ9999`, `9999УБЛ`, `УБЛ 9999` | `[А-Я]{3}\s?\d{4}|\d{4}\s?[А-Я]{3}` |
| **Европ** | EU | `AB 12 CD`, `ABC 1234` | `[A-Z]{2,3}\s?\d{2,4}\s?[A-Z]{0,3}` |
| **АНУ** | US | `ABC-1234`, `12-ABC-34567` | `[A-Z]{1,3}[-\s]?\d{4,7}` |
| **Япон** | JP | `品川 500 あ 12-34` | `[^\W_]+[\s-]?\d{1,4}[\s-]?[^\W_]+[\s-]?\d{1,4}` |
| **Хятад** | CN | `京A·12345` | `[А-Я]{1,2}[A-Z]\s?[·]?\d{5}` |
| **Орос** | RU | `А123БВ 123` | `[А-Я]{1,3}\d{3,4}[А-Я]{2,3}\s?\d{2,3}` |
| **Өмнөд Солонгос** | KR | `강남 52가 1234` | `[^\W_]+[\s-]?\d{1,2}[^\W_][\s-]?\d{4}` |
| **Custom** | XX | User-provided regex | (manual input) |

#### Processing Flow

```
1. YOLO detects vehicle (car/truck/bus/motorcycle)
        │
        ▼
2. Crop license plate region (lower 30% of vehicle bbox)
        │
        ▼
3. OCR engine (PaddleOCR / Tesseract) → raw text
        │
        ▼
4. Regex match against selected pattern
        │
        ▼ Match ✓ ──→ Validate confidence ≥ min_confidence
        │                    │
        │                    ▼
        │              Insert to license_plates table
        │                    │
        │                    ▼
        │              Check blacklist/whitelist (smart_alerts)
        │
        ▼ Match ✗ ──→ Log as low-confidence, no insert
```

#### OCR Engine Options

| Engine | Accuracy | Speed | Mongolian Support | Recommendation |
|--------|----------|-------|-------------------|---------------|
| **PaddleOCR** | 90-95% | Fast | Good (Cyrillic) | **Primary choice** |
| **Tesseract** | 60-75% | Medium | Fair | Fallback |
| **YOLOv8-Plate** | 95%+ | Very fast | Needs training | Future upgrade |

#### API Endpoints

```
GET /api/v1/lpr/patterns
→ {"data": [
     {"code": "MN", "name": "Монгол Улс", "patterns": [...]},
     {"code": "EU", "name": "Европ (EU)", "patterns": [...]}
   ]}

POST /api/v1/cameras/{id}/lpr
→ {"data": {"lpr_config": {"enabled": true, "pattern": "mongolia"}}}

GET /api/v1/lpr/readings?camera_id=xxx&days=7&plate_number=УБЛ9999
→ {"data": [
     {"plate_number": "УБЛ9999", "confidence": 0.92, "detected_at": "...", "snapshot_path": "..."}
   ]}

GET /api/v1/lpr/blacklist?active=true
→ {"data": [...]}

POST /api/v1/lpr/blacklist
→ {"data": {"id": "...", "plate_number": "ABC1234", "reason": "Stolen vehicle"}}
```

#### Frontend Components

- **Camera settings dialog:** LPR enable/disable, pattern dropdown, confidence slider, custom regex input
- **LPR readings page:** Table with plate number, timestamp, snapshot thumbnail, camera name
- **Blacklist management:** CRUD for blacklisted/whitelisted plates
- **Real-time alerts:** WebSocket notification when blacklisted plate detected

---

### 3. Smart Alerts Plugin (`smart_alerts`)

Rule-based alerting system triggered by AI detection events.

#### Rule Types

| Type | Description | Example |
|------|-------------|---------|
| `time_based` | Trigger during specific time windows | "Alert if person detected between 23:00-06:00" |
| `frequency` | Trigger when count exceeds threshold in time window | "Alert if >10 vehicles in 5 minutes (traffic jam)" |
| `blacklist_lpr` | Trigger when blacklisted plate detected | "Alert for stolen vehicle plates" |
| `zone_violation` | Trigger when object enters restricted zone | "Alert if car enters pedestrian zone" |
| `dwell_time` | Trigger when object stays too long | "Alert if vehicle parked >30 min" |
| `crowd_detection` | Trigger when too many people gather | "Alert if >20 people in frame" |

#### Rule Configuration

```json
{
  "name": "Night intrusion alert",
  "rule_type": "time_based",
  "conditions": {
    "object_categories": ["person"],
    "time_start": "23:00",
    "time_end": "06:00",
    "min_confidence": 0.7
  },
  "severity": "critical",
  "notifications": ["websocket", "telegram", "email"],
  "enabled": true
}
```

#### Notification Channels

| Channel | Implementation |
|---------|---------------|
| **WebSocket** | Push to frontend in real-time |
| **Telegram** | HTTP webhook to Telegram Bot API |
| **Slack** | Incoming webhook URL |
| **Email** | SMTP send with snapshot attachment |
| **SMS** | Twilio or local SMS gateway ( Mongolia: Unitel, G-Mobile) |
| **MQTT** | Publish to topic for IoT integration |

#### API Endpoints

```
GET /api/v1/smart-alerts/rules?camera_id=xxx
→ {"data": [...]}

POST /api/v1/smart-alerts/rules
→ {"data": {...}}

PATCH /api/v1/smart-alerts/rules/{id}
→ {"data": {...}}

DELETE /api/v1/smart-alerts/rules/{id}

GET /api/v1/smart-alerts/triggers?camera_id=xxx&days=7&severity=critical
→ {"data": [...]}

POST /api/v1/smart-alerts/test-notification
→ {"data": {"sent": true}}
```

---

### 4. Heat Map Plugin (`heat_map`)

Visual analytics showing where people/vehicles move most frequently.

#### Features

- Accumulate detection positions normalized to frame coordinates (0-1)
- Blur and composite into heatmap overlay (red = high density, blue = low)
- Store as timestamped image + aggregate stats
- Display on camera live view as toggleable overlay

#### Data Model

```sql
CREATE TABLE heat_map_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id UUID NOT NULL REFERENCES cameras(id),
    heatmap_date DATE NOT NULL,
    heatmap_image_path TEXT,
    hotspots JSONB  -- [{"x": 0.5, "y": 0.7, "density": 42}]
);
```

#### API Endpoints

```
GET /api/v1/heatmaps/{camera_id}?date=2025-07-26
→ {"data": {"heatmap_image_path": "...", "hotspots": [...]}}
```

---

### 5. People Analytics Plugin (`people_analytics`)

Advanced human behavior and crowd analysis.

#### Features

| Feature | Description |
|---------|-------------|
| **Dwell time** | Track how long a person stays in frame (position-aware dedup) |
| **Crowd detection** | Count unique persons; alert if exceeds threshold |
| **Time-of-day analysis** | Peak hours identification |
| **Direction tracking** | Line-crossing detection for entry/exit counting |
| **Loitering detection** | Alert if person stays in sensitive area > X seconds |

#### API Endpoints

```
GET /api/v1/people-analytics/dwell?camera_id=xxx&date=2025-07-26
→ {"data": {"avg_dwell_s": 45, "max_dwell_s": 320, "total_events": 28}}

GET /api/v1/people-analytics/peak-hours?camera_id=xxx&days=7
→ {"data": [{"hour": 9, "count": 42}, {"hour": 14, "count": 38}]}
```

---

### 6. Vehicle Analytics Plugin (`vehicle_analytics`)

Specialized vehicle tracking and traffic analysis.

#### Features

| Feature | Description |
|---------|-------------|
| **Vehicle type breakdown** | Separate counts for car, truck, bus, motorcycle |
| **Direction tracking** | Line-crossing detection (left→right, right→left) |
| **Speed estimation** | Two cameras with known distance + timestamp diff |
| **Parking detection** | Vehicle stationary > X minutes → alert |
| **Traffic flow rate** | Vehicles per hour/minute |

#### API Endpoints

```
GET /api/v1/vehicle-analytics/breakdown?camera_id=xxx&date=2025-07-26
→ {"data": {"car": 85, "truck": 12, "bus": 3, "motorcycle": 22}}

GET /api/v1/vehicle-analytics/flow-rate?camera_id=xxx&hours=24
→ {"data": [{"hour": 8, "rate": 45}, {"hour": 14, "rate": 32}]}
```

---

### 7. Animal Detection Plugin (`animal_detection`)

Wildlife and livestock monitoring.

#### Features

| Feature | Description |
|---------|-------------|
| **Species classification** | Distinguish cat, dog, bird, horse, sheep, cow |
| **Livestock herd size** | Count animals in same frame as a group |
| **Stray animal alert** | Night-time stray animal detection → security notification |
| **Activity patterns** | Diurnal/nocturnal behavior analysis |

#### API Endpoints

```
GET /api/v1/animal-detection/species?camera_id=xxx&days=7
→ {"data": {"cat": 15, "dog": 8, "bird": 42, "horse": 3}}
```

---

### 8. Multi-Camera Tracking Plugin (`multi_camera_tracking`)

Cross-camera object re-identification and route tracking.

#### Features

| Feature | Description |
|---------|-------------|
| **Re-identification (ReID)** | Match same person/vehicle across cameras using visual features |
| **Route tracking** | Build timeline of camera appearances for detected objects |
| **Cross-camera counting** | Total unique objects across multiple cameras (avoid double-counting) |
| **Gateway counting** | Border checkpoint / toll booth total throughputs |

#### Technical Approach

- Use lightweight embedding model (MobileNetV2 or OSNet) for ReID
- Store embeddings in Redis with TTL (real-time only, no persistence)
- Match threshold: cosine similarity > 0.75

#### API Endpoints

```
GET /api/v1/tracking/route?object_id=xxx&camera_ids=[c1,c2,c3]
→ {"data": [
     {"camera_id": "c1", "timestamp": "...", "bbox": [...]},
     {"camera_id": "c2", "timestamp": "...", "bbox": [...]}
   ]}

GET /api/v1/tracking/gateway-count?camera_ids=[c1,c2,c3]&date=2025-07-26
→ {"data": {"unique_objects": 156, "total_appearances": 289}}
```

---

### 9. Export & Reports Plugin (`export_reports`)

Generate and download analytics reports.

#### Features

| Feature | Description |
|---------|-------------|
| **CSV export** | Counter data, LPR readings, event logs |
| **PDF report** | Formatted daily/weekly/monthly summary with charts |
| **Scheduled reports** | Email report on cron schedule |
| **Custom date range** | User-selectable start/end dates |

#### API Endpoints

```
GET /api/v1/reports/export?type=counters&camera_id=xxx&format=csv&from=2025-07-01&to=2025-07-26
→ File download

GET /api/v1/reports/scheduled
→ {"data": [...]}

POST /api/v1/reports/scheduled
→ {"data": {"email": "admin@example.com", "frequency": "daily", "format": "pdf"}}
```

---

### 10. Facial Recognition Plugin (`facial_recognition`)

Person identification (optional, privacy-sensitive).

#### Features

| Feature | Description |
|---------|-------------|
| **Face detection** | Detect faces in frame (dlib / RetinaFace) |
| **Face embedding** | Generate 128-dim vector (ArcFace model) |
| **Gallery matching** | Compare against known persons database |
| **Access control** | Alert for unrecognized persons in restricted areas |

#### Privacy Considerations

- Requires explicit opt-in per camera
- Face gallery managed separately (GDPR/compliance)
- Option to disable at any time
- All face data encrypted at rest

#### Data Model

```sql
CREATE TABLE face_gallery (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_name VARCHAR(100) NOT NULL,
    embedding vector(128),  -- Use pgvector extension
    photo_path TEXT,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE face_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id UUID NOT NULL REFERENCES cameras(id),
    gallery_id UUID REFERENCES face_gallery(id),
    match_confidence FLOAT,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    snapshot_path TEXT
);
```

---

### 11. Behavior Analysis Plugin (`behavior_analysis`)

Suspicious activity detection.

#### Features

| Feature | Description |
|---------|-------------|
| **Running detection** | Rapid position change between frames |
| **Falling detection** | Sudden appearance of horizontal person bbox |
| **Loitering** | Person stationary in sensitive area > X seconds |
| **Left object** | Object appears then disappears (theft detection) |
| **Taken object** | Object disappears from known location |

#### API Endpoints

```
GET /api/v1/behavior/events?camera_id=xxx&type=loitering&days=7
→ {"data": [...]}
```

---

### 12. Uniform Detection Plugin (`uniform_detection`)

Identify uniformed personnel (security guards, workers).

#### Features

| Feature | Description |
|---------|-------------|
| **Uniform classification** | Detect security uniforms, construction vests |
| **Badge/logo recognition** | Optional: recognize organization logos |
| **Presence tracking** | Track which shifts personnel are on-site |

---

### 13. Safety Compliance Plugin (`safety_compliance`)

Workplace safety monitoring (construction sites, factories).

#### Features

| Feature | Description |
|---------|-------------|
| **Helmet detection** | Detect hard hats on workers |
| **Vest detection** | Detect high-visibility vests |
| **PPE compliance** | Combined helmet + vest check |
| **Restricted area alerts** | Unauthorized persons in hazardous zones |

---

### 14. Plugin Manager (`plugin_manager`)

UI and API for managing plugins system-wide.

#### Features

| Feature | Description |
|---------|-------------|
| **Plugin list** | Show all available plugins with status |
| **Enable/Disable** | Toggle plugins globally or per-camera |
| **Configuration UI** | Plugin-specific settings (e.g., LPR pattern, alert rules) |
| **Resource monitoring** | CPU/RAM usage per plugin |
| **Health checks** | Auto-restart crashed plugins |
| **Usage analytics** | How often each plugin triggers events |

#### API Endpoints

```
GET /api/v1/plugins
→ {"data": [
     {"name": "counter", "enabled": true, "cameras": 12, "cpu_pct": 2.3},
     {"name": "lpr", "enabled": false, "cameras": 0, "cpu_pct": 0}
   ]}

PATCH /api/v1/plugins/{name}/config
→ {"data": {...}}

GET /api/v1/plugins/{name}/health
→ {"data": {"status": "healthy", "uptime_s": 86400}}
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1-2)

| Task | File(s) | Description |
|------|---------|-------------|
| Plugin interface | `services/ai-engine/app/plugins/base.py` | Abstract base class |
| Plugin registry | `services/ai-engine/app/plugins/__init__.py` | Load order, initialization |
| FrameSampler integration | `services/ai-engine/app/frame_sampler.py` | Call plugins in `_consume()` |
| DB migrations | `alembic/versions/0009_ai_plugins.py` | `lpr_config`, `object_counters`, `license_plates`, `smart_alerts` |
| Camera schema update | `services/api/app/schemas/camera.py` | Add `lpr_config`, `ai_plugins` fields |

### Phase 2: Counter Plugin (Week 2-3)

| Task | File(s) | Description |
|------|---------|-------------|
| Counter plugin | `services/ai-engine/app/plugins/counter.py` | Category mapping, flush logic |
| Counter API | `services/api/app/api/v1/counters.py` | Summary, hourly, comparison endpoints |
| Counter service | `services/api/app/services/counter_service.py` | DB queries, aggregations |
| Frontend: Dashboard cards | `services/web/src/pages/Dashboard.tsx` | Live stat cards with WebSocket update |
| Frontend: Statistics page | `services/web/src/pages/Statistics.tsx` | Recharts graphs (hourly/daily) |

### Phase 3: LPR Plugin (Week 3-5)

| Task | File(s) | Description |
|------|---------|-------------|
| LPR patterns | `services/ai-engine/app/plugins/lpr_patterns.py` | Country pattern library |
| LPR plugin | `services/ai-engine/app/plugins/lpr.py` | OCR + regex matching |
| PaddleOCR setup | Dockerfile / requirements | Add PaddleOCR dependency |
| LPR API | `services/api/app/api/v1/lpr.py` | Patterns, readings, blacklist endpoints |
| LPR service | `services/api/app/services/lpr_service.py` | DB operations, blacklist management |
| Frontend: Camera settings | `services/web/src/components/camera/CameraEditDialog.tsx` | LPR config section |
| Frontend: LPR page | `services/web/src/pages/LPRReadings.tsx` | Readings table + search |
| Frontend: Blacklist UI | `services/web/src/components/lpr/BlacklistManager.tsx` | CRUD for blacklisted plates |

### Phase 4: Smart Alerts (Week 5-6)

| Task | File(s) | Description |
|------|---------|-------------|
| Alerts plugin | `services/ai-engine/app/plugins/smart_alerts.py` | Rule evaluation engine |
| Alerts API | `services/api/app/api/v1/smart_alerts.py` | Rules CRUD, triggers list |
| Alerts service | `services/api/app/services/alert_service.py` | Rule management, notification dispatch |
| Notification channels | `services/api/app/services/notifications/` | Telegram, Slack, Email, SMS |
| Frontend: Alert rules | `services/web/src/pages/AlertRules.tsx` | Rule builder UI |
| Frontend: Alert feed | `services/web/src/components/alerts/AlertFeed.tsx` | Real-time alert notifications |

### Phase 5: Advanced Plugins (Week 6-10)

| Plugin | Priority | Complexity |
|--------|----------|-----------|
| Heat Map | Medium | Medium |
| People Analytics | High | Medium |
| Vehicle Analytics | High | Low |
| Animal Detection | Low | Low |
| Export & Reports | High | Medium |
| Multi-Camera Tracking | Medium | High |
| Facial Recognition | Low | High (privacy) |
| Behavior Analysis | Medium | High |
| Uniform Detection | Low | Medium |
| Safety Compliance | Medium | Medium |

### Phase 6: Plugin Manager & Polish (Week 10-12)

| Task | File(s) | Description |
|------|---------|-------------|
| Plugin manager API | `services/api/app/api/v1/plugins.py` | List, config, health endpoints |
| Plugin manager UI | `services/web/src/pages/Plugins.tsx` | System-wide plugin management |
| Resource monitoring | `services/ai-engine/app/plugins/health.py` | CPU/RAM tracking per plugin |
| Documentation | `docs/` | User guides, API docs |

---

## API Response Convention

All endpoints wrap responses in `{ "data": ... }`:

```json
{"data": {"plate_number": "УБЛ9999", "confidence": 0.92, "detected_at": "..."}}
```

Frontend unwraps: `r.data.data` (axios), `json.data` (fetch).

---

## Frontend Integration Patterns

### WebSocket Updates for Live Counters

```typescript
// In Dashboard.tsx or StatisticsPage.tsx
useNvrWebSocket(
  onCameraStatus,
  useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["counters", "summary"] });
  }, [queryClient])
);
```

### Counter Card Component

```tsx
<div className="bg-gray-900 rounded border border-gray-800 p-3">
  <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
    <Car size={14} className="text-blue-400" /> Vehicles
  </div>
  <div className="text-lg font-bold">{summary.vehicle ?? "—"}</div>
  <div className="text-[10px] text-gray-500 mt-0.5">today</div>
</div>
```

### LPR Readings Table

```tsx
<table>
  <thead>
    <tr>
      <th>Plate Number</th>
      <th>Camera</th>
      <th>Time</th>
      <th>Confidence</th>
      <th>Snap</th>
    </tr>
  </thead>
  <tbody>
    {readings.map(r => (
      <tr key={r.id}>
        <td className="font-mono">{r.plate_number}</td>
        <td>{cameraNames[r.camera_id]}</td>
        <td>{new Date(r.detected_at).toLocaleString()}</td>
        <td>{Math.round(r.confidence * 100)}%</td>
        <td><img src={eventSnapshotUrl(r.id)} /></td>
      </tr>
    ))}
  </tbody>
</table>
```

---

## Resource Management

### CPU Budget per Plugin

| Plugin | Estimated CPU (per camera) | Notes |
|--------|---------------------------|-------|
| Counter | ~0.5% | Minimal — just counting |
| LPR | ~8-15% | OCR inference per vehicle detection |
| Heat Map | ~2% | Image compositing |
| People Analytics | ~3% | Dwell time calculations |
| Vehicle Analytics | ~2% | Direction/speed math |
| Multi-Camera Tracking | ~5% | ReID embeddings + matching |
| Facial Recognition | ~10-20% | Face detection + embedding |
| Behavior Analysis | ~5% | Frame differencing + tracking |

### Configuration Controls

```yaml
# Per-camera plugin config
cameras:
  - id: "xxx"
    ai_plugins: ["counter", "lpr"]   # Only run these plugins
    lpr_config:
      enabled: true
      pattern: "mongolia"
    
# Global resource limits (future)
ai_engine:
  max_cpu_percent: 80
  plugin_priority:
    - "lpr"
    - "counter"
    - "smart_alerts"
```

---

## Internationalization (i18n)

Plugin UI labels should support multiple languages:

| Language | Code | Priority |
|----------|------|----------|
| Mongolian | mn | Primary |
| English | en | Secondary |
| Russian | ru | Tertiary |

Example:
```typescript
const labels = {
  mn: { vehicleCount: "Машин тоо", personCount: "Хүн тоо" },
  en: { vehicleCount: "Vehicle Count", personCount: "Person Count" },
  ru: { vehicleCount: "Транспорт", personCount: "Люди" }
};
```

---

## Security & Privacy

### Data Protection

- All snapshots encrypted at rest (AES-256-GCM via `nvr_common.security`)
- Face gallery data requires explicit consent (GDPR compliance)
- LPR data retention policy configurable (30/90/365 days)
- Audit log for all plugin configuration changes

### Access Control

| Role | Counter | LPR | Smart Alerts | Facial Recognition |
|------|---------|-----|--------------|-------------------|
| Viewer | Read-only | Read-only | Read-only | No access |
| Operator | Read/Write | Read-only | Read/Write | No access |
| Admin | Full | Full | Full | Full (if enabled) |

---

## Future Roadmap

### Quarter 1 (MVP)
- [x] Plugin architecture foundation
- [x] Counter plugin
- [x] LPR plugin (pattern-based)
- [x] Dashboard statistics page
- [x] Smart alerts (basic rules)

### Quarter 2
- [ ] Export & Reports (CSV/PDF)
- [ ] People Analytics (dwell time, peak hours)
- [ ] Vehicle Analytics (direction, flow rate)
- [ ] Plugin Manager UI
- [ ] Telegram/Slack notifications

### Quarter 3
- [ ] Multi-camera tracking (ReID)
- [ ] Heat Map visualization
- [ ] Behavior Analysis (loitering, running)
- [ ] SMS notifications
- [ ] Scheduled reports

### Quarter 4
- [ ] Facial Recognition (opt-in)
- [ ] Uniform Detection
- [ ] Safety Compliance (helmet/vest)
- [ ] Speed estimation (multi-camera)
- [ ] MQTT IoT integration

---

## File Structure

```
services/ai-engine/app/
├── plugins/
│   ├── __init__.py              # Plugin registry, load order
│   ├── base.py                  # AIPlugin abstract base class
│   ├── counter.py               # Object counting plugin
│   ├── lpr.py                   # License plate recognition
│   ├── lpr_patterns.py          # Country pattern library
│   ├── smart_alerts.py          # Rule-based alerting
│   ├── heat_map.py              # Heat map generation
│   ├── people_analytics.py      # Dwell time, crowd detection
│   ├── vehicle_analytics.py     # Traffic flow, direction tracking
│   ├── animal_detection.py      # Wildlife/livestock monitoring
│   ├── multi_camera_tracking.py # ReID, route tracking
│   ├── facial_recognition.py    # Face detection + matching
│   ├── behavior_analysis.py     # Suspicious activity detection
│   ├── export_reports.py        # CSV/PDF report generation
│   └── health.py                # CPU/RAM monitoring per plugin

services/api/app/
├── api/v1/
│   ├── counters.py              # Counter statistics endpoints
│   ├── lpr.py                   # LPR readings, blacklist endpoints
│   ├── smart_alerts.py          # Alert rules + triggers
│   └── plugins.py               # Plugin manager endpoints
├── services/
│   ├── counter_service.py       # Counter DB operations
│   ├── lpr_service.py           # LPR DB operations
│   ├── alert_service.py         # Alert rule management
│   └── notifications/
│       ├── telegram.py
│       ├── slack.py
│       ├── email.py
│       └── sms.py

services/web/src/
├── pages/
│   ├── Statistics.tsx           # Counter graphs & analytics
│   ├── LPRReadings.tsx          # License plate readings list
│   ├── AlertRules.tsx           # Smart alert rules management
│   ├── Plugins.tsx              # Plugin manager UI
│   └── ...
├── components/
│   ├── camera/
│   │   └── CameraEditDialog.tsx  # LPR config section
│   ├── lpr/
│   │   └── BlacklistManager.tsx  # Plate blacklist CRUD
│   ├── alerts/
│   │   └── AlertFeed.tsx        # Real-time notification feed
│   └── statistics/
│       ├── CounterCards.tsx     # Dashboard stat cards
│       └── HourlyChart.tsx      # Recharts time-series graph
└── hooks/
    ├── useCounters.ts           # Counter data fetching
    ├── useLPR.ts                # LPR data fetching
    └── useSmartAlerts.ts        # Alert rules management
```

---

## Testing Strategy

### Unit Tests

- Plugin interface compliance (all plugins implement `on_detection`, `start`, `stop`)
- Pattern matching accuracy (each country regex tested against sample plates)
- Counter flush logic (verify hourly aggregation correctness)
- Smart alert rule evaluation (time windows, thresholds)

### Integration Tests

- End-to-end: Camera detection → plugin processing → DB persistence → API retrieval
- WebSocket real-time updates (counter increments, alert triggers)
- LPR OCR accuracy on sample images
- Notification delivery (Telegram webhook mock, email mock)

### Performance Tests

- CPU usage per plugin at 30-camera load
- Memory leak detection (long-running plugin processes)
- DB query performance for time-range aggregations
- WebSocket message throughput

---

## Deployment Considerations

### Docker Compose Changes

```yaml
services:
  nvr-ai-engine:
    volumes:
      - ai_models:/app/models          # YOLO + PaddleOCR models
    environment:
      - AI_PLUGINS=counter,lpr,smart_alerts   # Enabled plugins
      - PADDLEOCR_MODEL=en_PP-OCRv4     # OCR model variant
    deploy:
      resources:
        limits:
          cpus: '4.0'                  # CPU budget for all plugins
```

### Model Storage

| Model | Path | Size | Purpose |
|-------|------|------|---------|
| YOLOv8n.onnx | `/app/models/yolov8n.onnx` | ~7 MB | Object detection (shared) |
| PaddleOCR det | `/app/models/paddleocr_det.pb` | ~5 MB | Text detection |
| PaddleOCR cls | `/app/models/paddleocr_cls.pb` | ~2 MB | Text rotation classification |
| PaddleOCR rec | `/app/models/paddleocr_rec.pb` | ~10 MB | Text recognition |

### Hardware Requirements

| Cameras | CPU (cores) | RAM | Notes |
|---------|-------------|-----|-------|
| 1-10 | 2 | 4 GB | Counter + LPR only |
| 11-30 | 4 | 8 GB | All plugins except facial recognition |
| 31-60 | 8 | 16 GB | Selective plugin enablement recommended |
| 60+ | 16+ | 32+ | Consider distributed AI processing |

---

## Summary

The mBm NVR AI Plugin Architecture provides a **modular, extensible foundation** for video analytics:

- **14 planned plugins** covering counting, LPR, alerts, analytics, and more
- **Pattern-based LPR** supports any country's license plate format
- **Per-camera configuration** enables selective deployment
- **Resource-aware design** prevents CPU/RAM overload
- **Phased implementation** delivers MVP in 6 weeks, full feature set in 12 weeks

This architecture positions the mBm NVR system as a **globally deployable AI video analytics platform** suitable for security, traffic management, retail analytics, and industrial monitoring.
