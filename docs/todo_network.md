# NVR System — Network Monitoring TODO

> **Status legend:** `[ ]` not started, `[~]` in progress, `[x]` done, `[-]` blocked/not applicable
> **Created:** 2026-07-23
> **Last updated:** 2026-07-23 (v2 — final plan with all features)

---

## Overview

Network monitoring dashboard showing real-time bandwidth, latency, packet loss per camera. Historical data stored for trend analysis. Linear charts with time-range selector. All cameras overview + location-based filtering. WebSocket real-time push. Anomaly detection. Capacity planning. Export & reporting.

---

## Phase 1: Data Collection (Backend)

### 1.1 Database Schema — Network Metrics Storage

**Table:** `network_metrics` (TimescaleDB hypertable)

```sql
CREATE TABLE network_metrics (
    camera_id           UUID NOT NULL REFERENCES cameras(id),
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
     -- Bandwidth (Mbps)
    inbound_mbps        NUMERIC(10,2),    -- RTSP stream incoming bandwidth
    outbound_mbps       NUMERIC(10,2),    -- FFmpeg relay outgoing bandwidth
    theoretical_max_mbps NUMERIC(8,2),    -- Expected max based on resolution/profile
    
     -- Latency (ms)
    rtt_ms              NUMERIC(8,2),     -- Round-trip time to camera IP
    jitter_ms           NUMERIC(8,2),     -- RTT variation
    rtsp_latency        NUMERIC(8,2),     -- RTSP session setup latency
    hls_segment_delay_s NUMERIC(6,2),     -- MediaMTX HLS segment generation delay
    
     -- Packet stats
    packets_sent        BIGINT,           -- ICMP/RTSP packets sent
    packets_recv        BIGINT,           -- Packets received
    packet_loss_pct     NUMERIC(5,2),     -- Percentage loss
    retransmission_cnt  BIGINT DEFAULT 0, -- RTSP retransmissions
    
     -- Connection quality (NEW)
    fps_current         INTEGER,          -- Current FPS from FFmpeg stderr
    fps_expected        INTEGER,          -- Expected FPS from camera config
    fps_variance_pct    NUMERIC(6,2),     -- FPS fluctuation % (stability indicator)
    bitrate_current     NUMERIC(10,2),    -- Current bitrate from FFmpeg stderr
    bitrate_variance_pct NUMERIC(6,2),    -- Bitrate variance % (buffering indicator)
    rtsp_reconnect_cnt  INTEGER DEFAULT 0, -- Session reconnection count
    
     -- FFmpeg process metrics
    ffmpeg_pid          INTEGER,          -- FFmpeg process ID (if running)
    ffmpeg_cpu          NUMERIC(5,2),     -- CPU usage of FFmpeg process
    ffmpeg_memory_mb    NUMERIC(8,2),     -- Memory usage of FFmpeg process
    ffmpeg_threads      INTEGER,          -- Number of FFmpeg encoder threads
    
     -- Anomaly detection (NEW)
    anomaly_score       NUMERIC(4,2) DEFAULT 0.0,  -- 0-100 deviation from baseline
    anomaly_type        VARCHAR(50),                -- 'bandwidth_spike', 'latency_surge', 'fps_drop', etc.
    
     -- Status
    status              VARCHAR(20) DEFAULT 'unknown',   -- online/offline/degraded
    error_message       TEXT,
    
     -- Raw data for debugging
    ffmpeg_stderr_sample TEXT        -- Last 500 chars of FFmpeg stderr
);

-- Hypertable for time-series optimization
SELECT create_hypertable('network_metrics', 'recorded_at');

-- Indexes
CREATE INDEX idx_network_metrics_camera_time ON network_metrics (camera_id, recorded_at DESC);
CREATE INDEX idx_network_metrics_time ON network_metrics (recorded_at DESC);
CREATE INDEX idx_network_metrics_status ON network_metrics (status, recorded_at DESC);
CREATE INDEX idx_network_metrics_anomaly ON network_metrics (anomaly_score DESC, recorded_at DESC) WHERE anomaly_score > 0;
```

**Table:** `network_metrics_baseline` (per-camera baseline for anomaly detection)

```sql
CREATE TABLE network_metrics_baseline (
    camera_id         UUID PRIMARY KEY REFERENCES cameras(id),
    
     -- Baseline averages (calculated from first 7 days of data)
    avg_bandwidth_mbps NUMERIC(8,2),
    avg_latency_ms     NUMERIC(8,2),
    avg_fps            NUMERIC(6,2),
    avg_bitrate        NUMERIC(10,2),
    
     -- Standard deviations (for anomaly threshold)
    stddev_bandwidth   NUMERIC(8,2),
    stddev_latency     NUMERIC(8,2),
    stddev_fps         NUMERIC(6,2),
    
     -- Time-of-day patterns (hourly buckets for "same time comparison")
    hourly_pattern    JSONB,  -- { "00": {bw: 4.2, lat: 12}, "01": {...}, ... }
    
     -- Calculation metadata
    calculated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_points       INTEGER NOT NULL DEFAULT 0,
    valid_until       TIMESTAMPTZ
);
```

**Table:** `camera_network_config` (per-camera monitoring config)

```sql
CREATE TABLE camera_network_config (
    camera_id         UUID PRIMARY KEY REFERENCES cameras(id),
    
     -- Polling interval (seconds)
    poll_interval     INTEGER NOT NULL DEFAULT 30,
    
     -- ICMP ping config
    ping_enabled      BOOLEAN NOT NULL DEFAULT true,
    ping_count        INTEGER NOT NULL DEFAULT 3,
    ping_timeout      INTEGER NOT NULL DEFAULT 5,
    
     -- RTSP quality check
    rtsp_check_enabled BOOLEAN NOT NULL DEFAULT true,
    rtsp_sample_size   INTEGER NOT NULL DEFAULT 100,   -- frames to sample
    
     -- Alert thresholds
    bandwidth_warn_mbps NUMERIC(8,2) DEFAULT 10.0,
    bandwidth_crit_mbps NUMERIC(8,2) DEFAULT 5.0,
    latency_warn_ms     NUMERIC(8,2) DEFAULT 100,
    latency_crit_ms     NUMERIC(8,2) DEFAULT 300,
    packet_loss_warn_pct NUMERIC(5,2) DEFAULT 1.0,
    packet_loss_crit_pct NUMERIC(5,2) DEFAULT 5.0,
    
     -- Anomaly thresholds (NEW)
    anomaly_stddev_multiplier NUMERIC(4,2) DEFAULT 2.0,  -- X standard deviations = anomaly
    
     -- Historical data retention (days)
    retention_days INTEGER NOT NULL DEFAULT 90,
    
     -- WebSocket push enabled (NEW)
    ws_push_enabled BOOLEAN NOT NULL DEFAULT true,
    
     -- Baseline recalculation schedule (NEW)
    baseline_recalc_interval_days INTEGER NOT NULL DEFAULT 7,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed with all existing cameras
INSERT INTO camera_network_config (camera_id)
SELECT id FROM cameras;
```

**Table:** `network_alerts` (alert history, integrates with existing `alert_log`)

```sql
CREATE TABLE network_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id       UUID NOT NULL REFERENCES cameras(id),
    alert_type      VARCHAR(50) NOT NULL,  -- 'bandwidth_low', 'latency_high', 'packet_loss_high', 'camera_offline', 'fps_drop', 'anomaly_detected'
    severity        VARCHAR(10) NOT NULL,  -- 'warning', 'critical'
    message         TEXT NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES users(id),
    resolved_at     TIMESTAMPTZ,
    metadata        JSONB,  -- { current_value: 4.2, threshold: 5.0, unit: 'mbps' }
    
     -- Correlation (NEW)
    related_camera_ids UUID[],  -- Other cameras affected at same time
    location          VARCHAR(255),  -- Denormalized for quick filtering
    
    CONSTRAINT chk_network_alert_severity CHECK (severity IN ('warning', 'critical'))
);

CREATE INDEX idx_network_alerts_camera_time ON network_alerts (camera_id, triggered_at DESC);
CREATE INDEX idx_network_alerts_unack ON network_alerts (acknowledged_at IS NULL, triggered_at DESC);
CREATE INDEX idx_network_alerts_type ON network_alerts (alert_type, triggered_at DESC);
```

**Table:** `network_topology` (NEW — physical/logical network map)

```sql
CREATE TABLE network_topology (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,           -- 'Main Switch', 'Floor 2 AP', etc.
    type            VARCHAR(50) NOT NULL,             -- 'switch', 'access_point', 'router', 'nvr', 'camera'
    parent_id       UUID REFERENCES network_topology(id),  -- Hierarchical: switch → AP → camera
    ip_address      INET,
    mac_address     MACADDR,
    location_id     UUID REFERENCES locations(id),
    description     TEXT,
    
     -- Port/bandwidth capacity (NEW)
    total_bandwidth_mbps NUMERIC(8,2),                -- Switch port aggregate capacity
    used_bandwidth_mbps NUMERIC(8,2) DEFAULT 0.0,     -- Current utilization
    port_count      INTEGER,                           -- Total ports on switch
    active_ports    INTEGER DEFAULT 0,                 -- Ports in use
    
     -- Status
    status          VARCHAR(20) DEFAULT 'unknown',     -- online/offline/maintenance
    last_seen_at    TIMESTAMPTZ,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_network_topology_location ON network_topology (location_id);
CREATE INDEX idx_network_topology_type ON network_topology (type);
```

### 1.2 Network Metrics Collector Service

**File:** `services/api/app/services/network_monitor.py`

**Responsibilities:**
- Periodic RTSP stream sampling (get FFmpeg stderr stats)
- ICMP ping to camera IP (async subprocess or `scapy`)
- CPU/memory tracking for FFmpeg processes
- HLS segment delay measurement from MediaMTX
- FPS variance + bitrate variance calculation
- Anomaly detection (baseline comparison)
- Store metrics in `network_metrics` table
- Alert threshold evaluation → create `network_alerts` records
- Historical data cleanup (cron job / background task)
- WebSocket broadcast for real-time updates
- Baseline recalculation (weekly)

**Key methods:**

```python
class NetworkMonitor:
    async def collect_camera_metrics(self, camera_id: UUID) -> dict
    async def ping_camera(self, ip_address: str) -> PingResult
    async def parse_ffmpeg_stats(self, ffmpeg_output: str) -> FFmpegStats
    async def measure_hls_segment_delay(self, camera_id: UUID) -> float | None
    async def calculate_fps_variance(self, camera_id: UUID) -> float
    async def calculate_bitrate_variance(self, camera_id: UUID) -> float
    async def detect_anomaly(self, camera_id: UUID, metrics: dict) -> AnomalyResult | None
    async def store_metrics(self, metrics: dict) -> None
    async def evaluate_alerts(self, camera_id: UUID, metrics: dict) -> list[Alert]
    async def cleanup_old_data(self, retention_days: int) -> int
    async def recalculate_baseline(self, camera_id: UUID) -> BaselineResult
    async def broadcast_metric(self, camera_id: UUID, metrics: dict) -> None  # WebSocket push
    async def background_collector(self) -> None  # Main loop
```

**RTSP stream sampling approach:**
- Parse FFmpeg stderr for `frame=`, `fps=`, `bitrate=` stats
- Sample every N seconds (configurable per camera)
- Calculate bandwidth from bitrate
- Track FPS drops as quality indicator (`fps_variance_pct`)
- Track bitrate stability (`bitrate_variance_pct`) — high variance = potential buffering

**ICMP ping approach:**
- Use `asyncio.create_subprocess_exec("ping", ...)` or Python `scapy`
- Send 3 pings, calculate RTT, jitter, packet loss
- Non-blocking (run in executor)

**FFmpeg process tracking:**
- Query `/proc/[pid]/stat` for CPU %
- Query `/proc/[pid]/status` for VmRSS (memory)
- Cross-reference with `STREAM_DICT` from live_relay

**HLS segment delay measurement (NEW):**
- Query MediaMTX REST API: `GET /v3/paths/{camera_id}`
- Parse `playback` → `segment` timing info
- Calculate delay between `recorded_at` and segment generation time
- High delay = network congestion or encoding bottleneck

**FPS variance calculation (NEW):**
- Store last N FPS samples in memory ring buffer (per camera)
- Calculate standard deviation / mean = variance %
- >10% variance = unstable stream (frame drops)
- Used for `fps_variance_pct` field + anomaly detection

**Bitrate variance calculation (NEW):**
- Store last N bitrate samples in memory ring buffer (per camera)
- Calculate standard deviation / mean = variance %
- >15% variance = potential buffering / network instability
- Used for `bitrate_variance_pct` field + anomaly detection

**Anomaly detection (NEW):**
- Compare current metrics against `network_metrics_baseline`
- Use Z-score: `z = (current_value - baseline_avg) / baseline_stddev`
- If `|z| > anomaly_stddev_multiplier` → anomaly detected
- Classify anomaly type: 'bandwidth_spike', 'latency_surge', 'fps_drop', 'packet_loss_sudden'
- Store in `anomaly_score` (0-100) + `anomaly_type` fields

**Baseline recalculation (NEW):**
- Triggered weekly (configurable interval)
- Uses last 7 days of data
- Calculates hourly patterns (`hourly_pattern` JSONB)
- Updates `network_metrics_baseline` table
- Used for "same time comparison" feature in UI

**WebSocket broadcast (NEW):**
- When new metrics stored, broadcast to connected WebSocket clients
- Format: `{ type: 'metric_update', camera_id: 'uuid', metrics: {...} }`
- Clients subscribe per camera or all cameras
- Enables real-time dashboard updates without polling

### 1.3 API Endpoints — Network Metrics

```
POST    /api/v1/network/monitor/start         # Start monitoring for camera(s)
POST    /api/v1/network/monitor/stop          # Stop monitoring
GET     /api/v1/network/metrics               # Latest metrics for all cameras (paginated)
GET     /api/v1/network/metrics/{camera_id}   # Latest metrics for single camera
GET     /api/v1/network/metrics/{camera_id}/history   # Historical data (time range)
PATCH   /api/v1/network/config/{camera_id}    # Update per-camera monitoring config
GET     /api/v1/network/alerts                # Active alerts (unacknowledged)
GET     /api/v1/network/alerts/all            # All alerts (paginated, filterable)
GET     /api/v1/network/summary               # Summary: total online/offline, avg bandwidth, etc.
POST    /api/v1/network/alerts/{id}/acknowledge   # Acknowledge alert
WS      /api/v1/network/ws                    # WebSocket real-time metric stream
GET     /api/v1/network/baselines             # All baselines
GET     /api/v1/network/baselines/{camera_id} # Single baseline
POST    /api/v1/network/baselines/{camera_id}/recalculate  # Trigger manual recalculation
GET     /api/v1/network/baselines/{camera_id}/compare      # Compare current vs baseline
GET     /api/v1/network/topology              # Network topology tree
POST    /api/v1/network/topology              # Add network device
PATCH   /api/v1/network/topology/{id}         # Update network device
DELETE  /api/v1/network/topology/{id}         # Remove network device
GET     /api/v1/network/capacity              # Bandwidth capacity per location
POST    /api/v1/network/export                # Export metrics to CSV/PDF
GET     /api/v1/network/reports/scheduled     # Scheduled reports list
POST    /api/v1/network/reports/scheduled     # Create scheduled report
```

**Response format — `/api/v1/network/metrics/{camera_id}/history`:**

```json
{
   "data": {
     "camera_id": "uuid",
     "camera_name": "Camera 01",
     "location": "Entrance",
     "time_range": {
       "start": "2026-07-23T00:00:00Z",
       "end": "2026-07-23T23:59:59Z"
     },
     "metrics": [
       {
         "recorded_at": "2026-07-23T12:00:00Z",
         "inbound_mbps": 4.2,
         "outbound_mbps": 3.8,
         "rtt_ms": 12.5,
         "jitter_ms": 2.1,
         "packet_loss_pct": 0.0,
         "fps_current": 25,
         "fps_expected": 25,
         "fps_variance_pct": 2.3,
         "bitrate_current": 4200,
         "bitrate_variance_pct": 5.1,
         "hls_segment_delay_s": 1.2,
         "rtsp_reconnect_cnt": 0,
         "ffmpeg_cpu": 8.5,
         "ffmpeg_memory_mb": 85.3,
         "anomaly_score": 0.0,
         "anomaly_type": null,
         "status": "online"
       }
     ],
     "summary_stats": {
       "avg_bandwidth_mbps": 4.1,
       "max_bandwidth_mbps": 5.2,
       "min_bandwidth_mbps": 3.5,
       "avg_latency_ms": 13.2,
       "max_latency_ms": 45.0,
       "avg_fps": 24.8,
       "total_reconnects": 2,
       "total_anomalies": 0
     }
   }
}
```

**Response format — `/api/v1/network/summary`:**

```json
{
   "data": {
     "total_cameras": 10,
     "online_cameras": 8,
     "offline_cameras": 2,
     "avg_bandwidth_mbps": 4.5,
     "avg_latency_ms": 15.2,
     "avg_packet_loss_pct": 0.1,
     "total_anomalies_24h": 3,
     "active_alerts": 1,
     "cameras_by_location": {
       "Entrance": { "total": 3, "online": 3, "avg_bw": 4.8, "capacity_used_pct": 60 },
       "Parking": { "total": 4, "online": 2, "avg_bw": 3.9, "capacity_used_pct": 45 },
       "Office": { "total": 3, "online": 3, "avg_bw": 5.1, "capacity_used_pct": 72 }
     }
   }
}
```

**Response format — `/api/v1/network/baselines/{camera_id}/compare`:**

```json
{
   "data": {
     "camera_id": "uuid",
     "camera_name": "Camera 01",
     "comparison_period": {
       "baseline_date": "2026-07-16T00:00:00Z",
       "current_date": "2026-07-23T12:00:00Z"
     },
     "metrics": {
       "bandwidth": {
         "baseline_avg": 4.2,
         "current_avg": 3.8,
         "change_pct": -9.5,
         "status": "below_baseline"
       },
       "latency": {
         "baseline_avg": 12.0,
         "current_avg": 15.5,
         "change_pct": 29.2,
         "status": "above_baseline"
       },
       "fps": {
         "baseline_avg": 25.0,
         "current_avg": 24.5,
         "change_pct": -2.0,
         "status": "normal"
       }
     }
   }
}
```

**Response format — `/api/v1/network/capacity`:**

```json
{
   "data": {
     "locations": [
       {
         "location_id": "uuid",
         "location_name": "Entrance",
         "total_cameras": 3,
         "current_bandwidth_mbps": 14.4,
         "theoretical_max_mbps": 30.0,
         "capacity_used_pct": 48,
         "recommended_max_cameras": 6,
         "warning_threshold_reached": false
       }
     ],
     "system_total": {
       "total_cameras": 10,
       "total_bandwidth_mbps": 45.0,
       "network_capacity_mbps": 1000.0,
       "utilization_pct": 4.5
     }
   }
}
```

**Response format — `/api/v1/network/export` (CSV download):**

```
HTTP/1.1 200 OK
Content-Type: text/csv
Content-Disposition: attachment; filename="network_metrics_2026-07-23.csv"

camera_name,recorded_at,inbound_mbps,outbound_mbps,rtt_ms,jitter_ms,packet_loss_pct,fps_current,bitrate_current,status
Camera 01,2026-07-23T12:00:00Z,4.2,3.8,12.5,2.1,0.0,25,4200,online
Camera 01,2026-07-23T12:00:30Z,4.1,3.7,13.0,2.3,0.0,25,4100,online
...
```

### 1.4 Background Task — Metrics Collector

**File:** `services/api/app/services/network_monitor.py` → `NetworkMonitor.background_collector()`

- Runs every N seconds (default 30s, configurable per camera)
- Iterates over all cameras with `ping_enabled=true` or `rtsp_check_enabled=true`
- Collects metrics concurrently using `asyncio.gather()`
- Stores to database in batch (INSERT ... ON CONFLICT UPDATE for latest row per camera)
- Evaluates alert thresholds, creates alerts if breached
- Periodic cleanup of old data (> retention_days)
- Weekly baseline recalculation (scheduled task)
- WebSocket broadcast after each metrics store

**Scheduling:**
- Start on API lifespan (`app/main.py`)
- Stop on API shutdown
- Use `asyncio.create_task()` for background loop
- Graceful shutdown: finish current collection cycle before stopping

### 1.5 WebSocket Server — Real-time Push

**File:** `services/api/app/services/network_ws.py` (new)

**Responsibilities:**
- Manage WebSocket connections
- Authenticate WS clients (JWT token)
- Subscribe/unsubscribe to camera metric streams
- Broadcast metric updates to subscribers
- Handle client disconnects
- Connection limit enforcement (per-user, global)

**WebSocket protocol:**

```
# Client → Server
{ "type": "subscribe", "camera_id": "uuid" }    # Subscribe to specific camera
{ "type": "subscribe_all" }                       # Subscribe to all cameras
{ "type": "unsubscribe", "camera_id": "uuid" }   # Unsubscribe from specific camera
{ "type": "ping" }                                 # Keep-alive

# Server → Client
{ "type": "metric_update", "camera_id": "uuid", "metrics": { ... } }
{ "type": "alert_triggered", "alert": { ... } }
{ "type": "pong" }
{ "type": "error", "message": "..." }
```

**Key methods:**

```python
class NetworkWebSocketManager:
    async def connect(self, websocket: WebSocket, token: str) -> None
    async def disconnect(self, websocket: WebSocket) -> None
    async def subscribe(self, websocket: WebSocket, camera_id: UUID | None) -> None
    async def broadcast_metric(self, camera_id: UUID, metrics: dict) -> None
    async def broadcast_alert(self, alert: dict) -> None
    
    async def worker(self) -> None  # Main message loop
```

### 1.6 Export & Reporting Service

**File:** `services/api/app/services/network_report.py` (new)

**Responsibilities:**
- CSV export (ad-hoc, time range filter)
- PDF report generation (daily/weekly summary)
- Scheduled report generation + email delivery
- Report template rendering

**Methods:**

```python
class NetworkReportService:
    async def export_csv(self, camera_ids: list[UUID], start: datetime, end: datetime) -> bytes
    async def generate_pdf_report(self, report_type: str, params: dict) -> bytes
    async def schedule_report(self, schedule: ReportSchedule) -> UUID
    async def send_report_email(self, report_id: UUID, recipients: list[str]) -> None
```

**Report types:**
- `daily_summary` — daily bandwidth/latency summary per camera
- `weekly_trend` — weekly trends with anomaly highlights
- `incident_report` — offline periods + root cause analysis
- `capacity_planning` — bandwidth utilization + recommendations

### 1.7 Alert Integration with Existing System

**Integration points:**
- `network_alerts` table links to existing `alert_log` via foreign key or shared `id`
- Alert severity mapping: network alerts → existing notification templates
- Email/push notifications reuse existing notification service
- Alert acknowledgment integrates with existing user system
- Correlation: related_camera_ids field helps identify switch/AP failures affecting multiple cameras

---

## Phase 2: Frontend — Network Dashboard

### 2.1 New Page — Network Dashboard

**File:** `services/web/src/pages/NetworkDashboard.tsx`

**Layout:**
```
┌───────────────────────────────────────────────────────────────────────┐
│  Network Dashboard                        [Live ●] [Export ▼] [Settings] │
├───────────────────────────────────────────────────────────────────────┤
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │
│   │ Total: 10   │ │ Online: 8   │ │ Alerts: 1   │ │ Anomalies: 3 │    │
│   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘    │
│                                                                       │
│   [All Cameras] [Entrance] [Parking] [Office]                         │
│                                                                       │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│   │ Camera 01│ │ Camera 02│ │ Camera 03│ │ Camera 04│ ...           │
│   │ Online ● │ │ Degraded ●│ │ Offline ● │ │ Online ● │               │
│   │ BW: 4.2  │ │ BW: 3.1  │ │ BW: --    │ │ BW: 5.1  │               │
│   │ Lat: 12ms│ │ Lat: 85ms│ │ Lat: --   │ │ Lat: 10ms│               │
│   │ FPS: 25  │ │ FPS: 18  │ │ FPS: --   │ │ FPS: 25  │               │
│   │ Loss: 0% │ │ Loss: 0.5%│ │ Loss: -- │ │ Loss: 0% │               │
│   │ ──▁▂▃▅▄▃──│ │ ──▅▄▃▂▁▂──│ │           │ │ ──▁▂▃▄▅▆──│               │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
│                                                                       │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │ Bandwidth History (24h) — Linear Chart              [▼ 1h/6h/12h/24h/7d] │
│   │ ────────────────────────────────────────────────────────────   │   │
│   │                                                               │   │
│   │    BW (Mbps)                                                  │   │
│   │    5.0 ┤     ╱╲         ╱╲                                   │   │
│   │    4.0 ┤   ╱╱  ╲──────╱  ╲──╲                                │   │
│   │    3.0 ┤ ╱╱      ╲    ╱    ╲  ╲                              │   │
│   │    2.0 ┤╱        ╲__/╱      ╲__╲                            │   │
│   │    1.0 ┤          ╲/         ╲___╲                          │   │
│   │    0.0 ┼──────────┴────────────┴───────────→ Time           │   │
│   │          00:00   06:00   12:00   18:00   24:00              │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │ Latency History (24h) — Linear Chart                [▼ 1h/6h/12h/24h/7d] │
│   │ ────────────────────────────────────────────────────────────   │   │
│   │                                                               │   │
│   │    Latency (ms)                                    Warning ─┤   │
│   │    300 ┤                                                    │   │
│   │    200 ┤                                                    │   │
│   │    100 ┤ ─────────────────────── Warning line               │   │
│   │     50 ┤        ╱╲       ╱╲                                 │   │
│   │     25 ┤      ╱╱  ╲────╱    ╲────                           │   │
│   │     10 ┤    ╱╱      ╲__/        ╲___                       │   │
│   │      0 ┼───╱────────────────────────────→ Time             │   │
│   │          00:00   06:00   12:00   18:00   24:00              │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │ Packet Loss History (24h) — Linear Chart            [▼ 1h/6h/12h/24h/7d] │
│   │ ────────────────────────────────────────────────────────────   │   │
│   │                                                               │   │
│   │    Loss (%)                                   Critical ─┤     │   │
│   │      5 ┤                                                    │   │
│   │      2 ┤ ───────────────────── Critical line               │   │
│   │      1 ┤ ───────────────────── Warning line                │   │
│   │      0 ┤ ─────────────────────────────────────────         │   │
│   │        ┼───────────────────────────────────→ Time          │   │
│   │          00:00   06:00   12:00   18:00   24:00              │   │
│   └───────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Grid view: all cameras with current metrics (bandwidth, latency, packet loss, FPS)
- Location filter tabs: All Cameras / Entrance / Parking / Office / etc.
- Per-camera mini sparkline chart (last 1h trend) — visual trend at a glance
- Full page linear charts (Recharts): bandwidth + latency + packet loss over time
- Time range selector: 1h / 6h / 12h / 24h / 7d / 30d (per chart, independent)
- Color coding: green (healthy), yellow (warning), red (critical)
- Live indicator: pulsing "●" when WebSocket connected, real-time updates active
- Export button: CSV/PDF export dropdown
- Settings gear: per-camera config modal

**Interactive features:**
- Click camera card → expand to show detailed chart + metrics panel (slide-over drawer)
- Hover on main chart → crosshair showing all cameras' values at that timestamp
- Click data point on main chart → highlight corresponding camera card
- Alert badge on camera card when active alert exists

### 2.2 Chart Component — NetworkChart

**File:** `services/web/src/components/network/NetworkChart.tsx`

**Library:** Recharts

```bash
npm install recharts
```

**Props:**

```typescript
interface NetworkChartProps {
  data: NetworkMetricPoint[];
  metrics: ('bandwidth' | 'latency' | 'packetLoss' | 'fps')[];
  timeRange: '1h' | '6h' | '12h' | '24h' | '7d' | '30d';
  height?: number;
  showLegend?: boolean;
  showGrid?: boolean;
  warningThresholds?: { bandwidth?: number; latency?: number; packetLoss?: number };
  onPointClick?: (point: NetworkMetricPoint, index: number) => void;
}

interface MultiCameraChartProps {
  cameras: { id: string; name: string; data: NetworkMetricPoint[]; color: string }[];
  metric: 'bandwidth' | 'latency' | 'packetLoss' | 'fps';
  timeRange: '1h' | '6h' | '12h' | '24h' | '7d' | '30d';
  height?: number;
}
```

**Features:**
- Linear line chart (Recharts `LineChart` + `Line`)
- Multiple metric lines on same chart (bandwidth, latency)
- Multiple cameras on same chart (color-coded lines)
- Time axis with auto-formatted labels (respects timeRange)
- Hover tooltip with exact values
- Crosshair on hover (shows all cameras' values at cursor position)
- Warning/critical threshold reference lines
- Responsive sizing
- Color coding per metric type
- Smooth animation on data update
- Area fill option (translucent gradient under line)

### 2.3 Camera Metric Card Component

**File:** `services/web/src/components/network/CameraMetricCard.tsx`

**Shows per camera:**
- Camera name + status indicator (green/yellow/red dot)
- Current bandwidth (Mbps) — with sparkline trend
- Current latency (ms) — with sparkline trend
- FPS (current/expected) — with variance %
- Packet loss (%)
- Mini sparkline chart (last 1h trend) — Recharts `AreaChart` mini
- Alert badge (red dot with number) if active alert exists
- Click → expand to full chart view (slide-over drawer)

**Sparkline behavior:**
- Shows last 60 data points (30min at 30s interval)
- Compressed horizontally, ~120px wide
- Color matches status (green/yellow/red)
- Hover shows exact value at that point

### 2.4 Network Summary Bar

**File:** `services/web/src/components/network/NetworkSummaryBar.tsx`

Shows at top of dashboard:
- Total cameras / online / offline count
- Average bandwidth across all cameras
- Average latency
- Active alert count (clickable → alerts list)
- 24h anomaly count
- Last updated timestamp
- Live indicator (pulsing dot when WebSocket connected)

### 2.5 Location-based Filtering

**File:** `services/web/src/components/network/LocationFilter.tsx`

- Tab bar with locations from API
- "All Cameras" tab shows everything
- Selected location tab filters grid + charts
- Uses existing `/api/v1/locations` endpoint for location list
- Location badge on each camera card
- Capacity usage indicator per location (color-coded bar)

### 2.6 Camera Detail Drawer

**File:** `services/web/src/components/network/CameraDetailDrawer.tsx` (NEW)

Slide-over panel when clicking a camera card:
- Full history chart for selected metric (bandwidth/latency/FPS/packet loss)
- Time range selector (1h/6h/12h/24h/7d/30d)
- Current metrics table (all fields)
- Alert history for this camera (last 7 days)
- Anomaly events list with timestamps
- Compare vs baseline button → opens comparison view
- FFmpeg process info (PID, CPU, memory, threads)
- RTSP connection info (reconnect count, session latency)
- HLS segment delay trend

### 2.7 Comparison View Modal

**File:** `services/web/src/components/network/ComparisonView.tsx` (NEW)

Modal showing current vs baseline comparison:
- Side-by-side metrics table with change %
- Overlapping line chart (baseline = dashed, current = solid)
- Hourly pattern comparison (heatmap grid)
- "Same time yesterday" comparison row
- Recommendations based on deviations

### 2.8 Network Topology View

**File:** `services/web/src/components/network/TopologyView.tsx` (NEW)

Visual network topology map:
- Hierarchical tree: NVR → Switch → AP → Cameras
- Nodes colored by status (green/yellow/red)
- Connection lines show bandwidth utilization (thickness/color)
- Click node → show details + metrics
- Zoom/pan support
- Export as SVG/PNG

**Library:** React Flow or D3.js for graph rendering

```bash
npm install @xyflow/react   # React Flow (simpler, good for tree layouts)
```

### 2.9 Export & Report Modal

**File:** `services/web/src/components/network/ExportModal.tsx` (NEW)

Modal for exporting data:
- Date range picker (start/end)
- Camera selection (all / specific cameras)
- Format selector (CSV / PDF)
- Report type (for PDF): daily summary / weekly trend / incident report / capacity planning
- Scheduled report setup (frequency, recipients, time)
- Generate button → shows progress → download link

### 2.10 Settings/Config Modal

**File:** `services/web/src/components/network/NetworkSettingsModal.tsx` (NEW)

Per-camera monitoring configuration:
- Poll interval (10s / 30s / 60s / custom)
- Ping enabled/disabled toggle
- RTSP check enabled/disabled toggle
- Alert thresholds (bandwidth warn/crit, latency warn/crit, packet loss warn/crit)
- Anomaly detection sensitivity (stddev multiplier: 1.5 / 2.0 / 3.0)
- WebSocket push enabled/disabled toggle
- Retention period (30d / 60d / 90d / custom)
- Save button → PATCH request to API

### 2.11 Sidebar Navigation Item

**File:** `services/web/src/components/layout/Sidebar.tsx` (modify)

Add network monitoring icon:

```typescript
const navItems = [
   { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
   { to: "/cameras", icon: Video, label: "Cameras" },
   { to: "/network", icon: Activity, label: "Network" },   // <-- NEW
   { to: "/recordings", icon: Film, label: "Recordings" },
   { to: "/events", icon: Bell, label: "Events" },
   { to: "/storage", icon: HardDrive, label: "Storage" },
   { to: "/settings", icon: Settings, label: "Settings" },
];
```

**Icon:** `Activity` from `lucide-react` (pulse/heartbeat icon)

### 2.12 Route Configuration

**File:** `services/web/src/App.tsx` (modify)

Add route for network dashboard page.

**File:** `services/web/src/components/layout/AppShell.tsx` (modify)

Add `/network` route pointing to `NetworkDashboard`.

---

## Phase 3: Frontend — Hooks & Types

### 3.1 Network API Client Methods

**File:** `services/web/src/api/network.ts` (new)

```typescript
import apiClient from './client';

export const networkApi = {
   // Metrics
  getMetrics: () => apiClient.get('/network/metrics'),
  getCameraMetrics: (cameraId: string) => 
    apiClient.get(`/network/metrics/${cameraId}`),
  getCameraHistory: (cameraId: string, params: { start?: string; end?: string; range?: string }) => 
    apiClient.get(`/network/metrics/${cameraId}/history`, { params }),
  
  // Summary & Capacity
  getSummary: () => apiClient.get('/network/summary'),
  getCapacity: () => apiClient.get('/network/capacity'),
  
  // Alerts
  getAlerts: () => apiClient.get('/network/alerts'),
  getAllAlerts: (params?: { camera_id?: string; severity?: string; limit?: number }) => 
    apiClient.get('/network/alerts/all', { params }),
  acknowledgeAlert: (alertId: string) => 
    apiClient.post(`/network/alerts/${alertId}/acknowledge`),
  
  // Monitoring control
  startMonitoring: (cameraIds?: string[]) => 
    apiClient.post('/network/monitor/start', { camera_ids: cameraIds }),
  stopMonitoring: (cameraIds?: string[]) => 
    apiClient.post('/network/monitor/stop', { camera_ids: cameraIds }),
  
  // Config
  updateConfig: (cameraId: string, config: Partial<NetworkConfig>) => 
    apiClient.patch(`/network/config/${cameraId}`, config),
  getCameraConfig: (cameraId: string) => 
    apiClient.get(`/network/config/${cameraId}`),
  
  // Baselines
  getBaselines: () => apiClient.get('/network/baselines'),
  getBaseline: (cameraId: string) => apiClient.get(`/network/baselines/${cameraId}`),
  recalculateBaseline: (cameraId: string) => 
    apiClient.post(`/network/baselines/${cameraId}/recalculate`),
  compareBaseline: (cameraId: string) => 
    apiClient.get(`/network/baselines/${cameraId}/compare`),
  
  // Topology
  getTopology: () => apiClient.get('/network/topology'),
  createTopologyNode: (data: TopologyNodeCreate) => 
    apiClient.post('/network/topology', data),
  updateTopologyNode: (id: string, data: Partial<TopologyNodeUpdate>) => 
    apiClient.patch(`/network/topology/${id}`, data),
  deleteTopologyNode: (id: string) => 
    apiClient.delete(`/network/topology/${id}`),
  
  // Export & Reports
  exportCSV: (params: ExportParams) => 
    apiClient.post('/network/export', params, { responseType: 'blob' }),
  generatePDFReport: (params: ReportParams) => 
    apiClient.post('/network/reports/generate', params, { responseType: 'blob' }),
  getScheduledReports: () => apiClient.get('/network/reports/scheduled'),
  createScheduledReport: (schedule: ReportSchedule) => 
    apiClient.post('/network/reports/scheduled', schedule),
  
  // WebSocket URL builder
  getWSUrl: () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/v1/network/ws`;
  },
};
```

### 3.2 TypeScript Types

**File:** `services/web/src/types/network.ts` (new)

```typescript
export interface NetworkMetricPoint {
  recorded_at: string;
  
   // Bandwidth
  inbound_mbps: number | null;
  outbound_mbps: number | null;
  theoretical_max_mbps: number | null;
  
   // Latency
  rtt_ms: number | null;
  jitter_ms: number | null;
  rtsp_latency: number | null;
  hls_segment_delay_s: number | null;
  
   // Packet stats
  packets_sent: number | null;
  packets_recv: number | null;
  packet_loss_pct: number | null;
  retransmission_cnt: number | null;
  
   // Connection quality
  fps_current: number | null;
  fps_expected: number | null;
  fps_variance_pct: number | null;
  bitrate_current: number | null;
  bitrate_variance_pct: number | null;
  rtsp_reconnect_cnt: number | null;
  
   // FFmpeg process metrics
  ffmpeg_pid: number | null;
  ffmpeg_cpu: number | null;
  ffmpeg_memory_mb: number | null;
  ffmpeg_threads: number | null;
  
   // Anomaly detection
  anomaly_score: number | null;
  anomaly_type: string | null;
  
   // Status
  status: 'online' | 'offline' | 'degraded' | 'unknown';
  error_message: string | null;
}

export interface MetricSummary {
  avg_bandwidth_mbps: number | null;
  max_bandwidth_mbps: number | null;
  min_bandwidth_mbps: number | null;
  avg_latency_ms: number | null;
  max_latency_ms: number | null;
  avg_fps: number | null;
  total_reconnects: number;
  total_anomalies: number;
}

export interface CameraNetworkSummary {
  camera_id: string;
  camera_name: string;
  location: string | null;
  ip_address: string;
  latest_metric: NetworkMetricPoint;
  avg_bandwidth_mbps: number | null;
  avg_latency_ms: number | null;
  alert_count: number;
}

export interface NetworkConfig {
  poll_interval: number;
  ping_enabled: boolean;
  ping_count: number;
  ping_timeout: number;
  rtsp_check_enabled: boolean;
  rtsp_sample_size: number;
  bandwidth_warn_mbps: number;
  bandwidth_crit_mbps: number;
  latency_warn_ms: number;
  latency_crit_ms: number;
  packet_loss_warn_pct: number;
  packet_loss_crit_pct: number;
  anomaly_stddev_multiplier: number;
  retention_days: number;
  ws_push_enabled: boolean;
  baseline_recalc_interval_days: number;
}

export interface NetworkSummary {
  total_cameras: number;
  online_cameras: number;
  offline_cameras: number;
  avg_bandwidth_mbps: number | null;
  avg_latency_ms: number | null;
  avg_packet_loss_pct: number | null;
  total_anomalies_24h: number;
  active_alerts: number;
  cameras_by_location: Record<string, LocationSummary>;
}

export interface LocationSummary {
  total: number;
  online: number;
  offline: number;
  avg_bw: number | null;
  capacity_used_pct: number | null;
}

export interface NetworkAlert {
  id: string;
  camera_id: string;
  camera_name: string;
  location: string | null;
  alert_type: 'bandwidth_low' | 'latency_high' | 'packet_loss_high' | 'camera_offline' | 'fps_drop' | 'anomaly_detected';
  severity: 'warning' | 'critical';
  message: string;
  triggered_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  metadata: Record<string, any> | null;
  related_camera_ids: string[];
}

export interface BaselineData {
  camera_id: string;
  avg_bandwidth_mbps: number | null;
  avg_latency_ms: number | null;
  avg_fps: number | null;
  avg_bitrate: number | null;
  stddev_bandwidth: number | null;
  stddev_latency: number | null;
  stddev_fps: number | null;
  hourly_pattern: Record<string, HourlyPattern> | null;
  calculated_at: string;
  data_points: number;
}

export interface HourlyPattern {
  bw: number | null;
  lat: number | null;
  fps: number | null;
}

export interface BaselineComparison {
  camera_id: string;
  camera_name: string;
  comparison_period: {
    baseline_date: string;
    current_date: string;
  };
  metrics: {
    bandwidth: ComparisonResult;
    latency: ComparisonResult;
    fps: ComparisonResult;
    bitrate: ComparisonResult;
  };
}

export interface ComparisonResult {
  baseline_avg: number | null;
  current_avg: number | null;
  change_pct: number | null;
  status: 'normal' | 'above_baseline' | 'below_baseline';
}

export interface CapacityInfo {
  location_id: string;
  location_name: string;
  total_cameras: number;
  current_bandwidth_mbps: number;
  theoretical_max_mbps: number;
  capacity_used_pct: number;
  recommended_max_cameras: number;
  warning_threshold_reached: boolean;
}

export interface TopologyNode {
  id: string;
  name: string;
  type: 'switch' | 'access_point' | 'router' | 'nvr' | 'camera';
  parent_id: string | null;
  ip_address: string | null;
  mac_address: string | null;
  location_id: string | null;
  total_bandwidth_mbps: number | null;
  used_bandwidth_mbps: number | null;
  port_count: number | null;
  active_ports: number;
  status: 'online' | 'offline' | 'maintenance';
  children?: TopologyNode[];
}

export interface ExportParams {
  camera_ids?: string[];
  start: string;
  end: string;
  format: 'csv' | 'pdf';
  report_type?: 'daily_summary' | 'weekly_trend' | 'incident_report' | 'capacity_planning';
}

export interface ReportSchedule {
  name: string;
  report_type: string;
  frequency: 'daily' | 'weekly' | 'monthly';
  time_of_day: string;  // HH:MM
  recipients: string[];
  camera_ids?: string[];
  enabled: boolean;
}

export interface WSMessage {
  type: 'metric_update' | 'alert_triggered' | 'pong' | 'error' | 'subscribe_ack' | 'unsubscribe_ack';
  camera_id?: string;
  metrics?: NetworkMetricPoint;
  alert?: NetworkAlert;
  message?: string;
}

export interface WSSubscription {
  type: 'subscribe' | 'subscribe_all' | 'unsubscribe';
  camera_id?: string;
}
```

### 3.3 React Hooks

**File:** `services/web/src/hooks/useNetwork.ts` (new)

```typescript
// useNetworkMetrics — latest metrics for all cameras
export function useNetworkMetrics() { ... }

// useCameraMetrics — latest metrics for single camera
export function useCameraMetrics(cameraId: string) { ... }

// useCameraHistory — historical data with time range
export function useCameraHistory(
  cameraId: string,
  timeRange: '1h' | '6h' | '12h' | '24h' | '7d' | '30d'
) { ... }

// useNetworkSummary — dashboard summary stats
export function useNetworkSummary() { ... }

// useNetworkAlerts — active alerts (unacknowledged)
export function useNetworkAlerts() { ... }

// useAllNetworkAlerts — all alerts with pagination/filters
export function useAllNetworkAlerts(params?: AlertFilterParams) { ... }

// useNetworkConfig — per-camera config CRUD
export function useNetworkConfig(cameraId: string) { ... }

// useStartMonitoring — start/stop background collection
export function useStartMonitoring() { ... }

// useBaseline — baseline data for a camera
export function useBaseline(cameraId: string) { ... }

// useBaselineComparison — current vs baseline comparison
export function useBaselineComparison(cameraId: string) { ... }

// useCapacity — bandwidth capacity per location
export function useCapacity() { ... }

// useTopology — network topology tree
export function useTopology() { ... }

// useExport — CSV/PDF export
export function useExport() { ... }

// useWebSocketMetrics — WebSocket real-time metric stream
export function useWebSocketMetrics(
  cameraId: string | null,         // null = all cameras
  onMetricUpdate?: (metrics: NetworkMetricPoint) => void,
  onAlert?: (alert: NetworkAlert) => void
) { ... }

// useScheduledReports — scheduled report management
export function useScheduledReports() { ... }
```

**useWebSocketMetrics implementation notes:**
- Manages WebSocket connection lifecycle (connect/reconnect/disconnect)
- JWT token in URL query parameter or subprotocol
- Auto-reconnect with exponential backoff (1s → 2s → 4s → max 30s)
- Heartbeat: client sends ping every 25s, server responds with pong
- Subscription management: subscribe on mount, unsubscribe on unmount
- Message routing: dispatch to appropriate callbacks based on message type
- Connection status exposed: `isConnected`, `lastError`

---

## Phase 4: Database Migration

### 4.1 Alembic Migration

**File:** `services/api/alembic/versions/XXXX_add_network_monitoring.py` (new)

Steps:
1. Create `network_metrics` table (TimescaleDB hypertable)
2. Create `network_metrics_baseline` table
3. Create `camera_network_config` table
4. Seed `camera_network_config` for all existing cameras
5. Create `network_alerts` table
6. Create `network_topology` table
7. Create indexes for time-series queries
8. Down migration: drop tables in reverse order (topology → alerts → config → baseline → metrics)

---

## Phase 5: Integration & Testing

### 5.1 API Tests

**File:** `services/api/tests/test_network_monitor.py`

- Mock FFmpeg output parsing
- Mock ICMP ping responses
- Test metrics storage and retrieval
- Test alert threshold evaluation
- Test historical data time-range queries
- Test anomaly detection logic (Z-score calculation)
- Test baseline recalculation
- Test WebSocket message broadcasting
- Test CSV export generation
- Test FPS variance calculation
- Test bitrate variance calculation

**File:** `services/api/tests/test_network_ws.py`

- Mock WebSocket connection
- Test subscribe/unsubscribe
- Test metric broadcast to subscribers
- Test reconnection logic

**File:** `services/api/tests/test_network_report.py`

- Test CSV export with various date ranges
- Test PDF report generation
- Test scheduled report creation

### 5.2 Frontend Tests

**File:** `services/web/src/test/network.test.tsx`

- NetworkChart component rendering with sample data
- CameraMetricCard with various states (online/offline/degraded)
- Location filtering logic
- Time range selector behavior
- Sparkline chart rendering
- Comparison view modal rendering
- Topology view rendering (basic)
- Export modal form validation
- WebSocket hook connection/reconnection logic
- useCameraHistory data fetching and error handling

### 5.3 Manual Testing Checklist

**Backend:**
- [ ] Start network monitoring → verify metrics appear in DB
- [ ] Verify FFmpeg stderr parsing captures fps/bitrate correctly
- [ ] Verify ICMP ping returns accurate RTT/jitter/packet_loss
- [ ] Verify alert thresholds trigger correctly (manually set low thresholds)
- [ ] Verify anomaly detection identifies known anomalies
- [ ] Verify baseline recalculation produces reasonable values
- [ ] Verify WebSocket broadcast delivers metrics to connected clients
- [ ] Verify CSV export contains correct data
- [ ] Verify historical cleanup removes old data (> retention_days)
- [ ] Verify hardware load → monitoring doesn't overwhelm system

**Frontend:**
- [ ] View dashboard → verify all cameras show correct metrics
- [ ] Click location filter → verify grid + charts update
- [ ] Change time range (1h/6h/12h/24h/7d) → verify chart data updates
- [ ] Offline camera → verify red status + no chart data
- [ ] Alert thresholds → verify warning/critical indicators
- [ ] Auto-refresh → verify metrics update every 30s
- [ ] Click camera card → verify detail drawer opens with full chart
- [ ] Compare vs baseline → verify comparison view shows correct deltas
- [ ] Topology view → verify tree renders correctly
- [ ] Export CSV → verify file downloads and contains correct data
- [ ] WebSocket live mode → verify pulsing indicator + real-time updates
- [ ] Responsive layout → verify on mobile/tablet sizes

---

## Implementation Order (Recommended)

### Sprint 1: Foundation
1. **Database schema** — migrations for all new tables
2. **Backend collector core** — `NetworkMonitor` with ping + FFmpeg parsing
3. **Backend API basic** — metrics endpoints (list, history, summary)
4. **Frontend types** — TypeScript interfaces in `types/network.ts`
5. **Frontend hooks basic** — data fetching hooks (`useNetworkMetrics`, `useCameraHistory`)

### Sprint 2: Dashboard & Charts
6. **Frontend components** — `NetworkChart`, `CameraMetricCard`, `NetworkSummaryBar`
7. **Frontend page** — `NetworkDashboard.tsx` with grid + charts
8. **Location filtering** — `LocationFilter` component + integration
9. **Sidebar + routes** — add to navigation

### Sprint 3: Advanced Features
10. **WebSocket real-time** — `NetworkWebSocketManager` + `useWebSocketMetrics`
11. **Anomaly detection** — Z-score calculation + baseline comparison
12. **Camera detail drawer** — full chart + metrics + alert history
13. **Comparison view** — current vs baseline modal

### Sprint 4: Polish & Extras
14. **Network topology** — `TopologyView` with React Flow
15. **Export & reports** — CSV/PDF export + scheduled reports
16. **Settings modal** — per-camera config UI
17. **Testing** — unit tests + integration tests + manual verification
18. **Performance tuning** — query optimization, chart rendering optimization

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Chart library | Recharts | Lightweight, React-native, good linear chart support |
| Topology library | React Flow (@xyflow/react) | Tree layout support, zoom/pan, simpler than D3 |
| Data granularity | 30-second intervals | Balance between detail and storage size |
| Historical retention | 90 days default | Configurable per camera |
| Ping method | `asyncio.create_subprocess_exec("ping")` | No extra dependencies, reliable |
| FFmpeg parsing | stderr regex on `frame=`, `fps=`, `bitrate=` | Standard FFmpeg output format |
| Alert evaluation | On-store (triggered when metrics written) | Real-time, no extra polling |
| Auto-refresh | 30s interval via `setInterval` in hook | Matches collection interval |
| WebSocket auth | JWT in URL query param | Simple, works with existing auth |
| WS reconnection | Exponential backoff (1s→30s max) | Prevents reconnect storms |
| Anomaly detection | Z-score vs baseline (configurable stddev multiplier) | Statistically sound, tunable |
| FPS variance | Ring buffer (last 60 samples) → std dev / mean | Low overhead, accurate |
| Bitrate variance | Ring buffer (last 60 samples) → std dev / mean | Low overhead, accurate |
| Export format | CSV (text/csv), PDF (application/pdf) | Universal compatibility |
| Baseline recalculation | Weekly, uses last 7 days of data | Captures normal patterns, avoids seasonal bias |

---

## Storage Estimation

**Per camera per day (30s intervals = 2880 points):**
- ~2880 rows × ~300 bytes/row ≈ 864 KB/day (increased due to new fields)
- 90 days retention ≈ 78 MB/camera
- 10 cameras ≈ 780 MB total

**Per camera baseline:**
- ~168 hourly buckets × ~100 bytes ≈ 17 KB (negligible)

**Network alerts:**
- Estimated 5 alerts/camera/month × 10 cameras × 90 days ≈ 1350 rows ≈ 500 KB (negligible)

**Topology nodes:**
- Estimated 20 nodes (switches/APs/cameras) × ~500 bytes ≈ 10 KB (negligible)

**Optimization strategy:**
- Downsample old data automatically: hourly avg for >7d, daily avg for >30d
- Store downsampled data in separate `network_metrics_hourly` / `network_metrics_daily` tables
- Original 30s data retained for 7d, then replaced by hourly aggregates
- Reduces 90-day storage from 780 MB to ~150 MB

---

## Performance Considerations

**Backend:**
- Concurrent metric collection: `asyncio.gather()` for all cameras in parallel
- Batch DB inserts: accumulate metrics, insert in batches of 50
- Connection pooling: ensure PostgreSQL pool has enough connections (20 base + monitoring)
- FFmpeg stderr parsing: regex compiled once at module level, not per-parse
- WebSocket broadcast: fan-out to subscribers asynchronously, don't block collector

**Frontend:**
- Chart data loading: TanStack Query caching + stale-while-revalidate
- Sparkline optimization: only render last 60 points, not full history
- Large dataset rendering: use Recharts `dataKey` sampling for >1000 points
- WebSocket message throttling: debounce metric updates to 1s max render frequency
- Component lazy loading: toplogy view + export modal loaded on demand (React.lazy)

**Database:**
- TimescaleDB hypertable: automatic chunking by time (1 week per chunk)
- Indexes on frequently queried columns (camera_id, recorded_at, status)
- Partial indexes for active alerts (`acknowledged_at IS NULL`)
- Query optimization: use `latest()` or `first()` for current metrics to avoid full table scan

---

## Security Considerations

- Network metrics endpoint: same auth as other API endpoints (JWT required)
- WebSocket connection: validate JWT before accepting connection
- Export data: respect user permissions (viewer can only see cameras they have access to)
- CSV export: sanitize camera names/IPs in output (no SQL injection risk, but good practice)
- Rate limit metric collection: prevent misconfiguration from excessive polling (< 10s interval rejected)

---

## Monitoring the Monitor

**Self-health checks:**
- Background collector task status: running/stopped/errored
- Last collection timestamp per camera (stale data detection)
- WebSocket connection count + error rate
- DB write latency for metrics table (slow writes = performance issue)
- Memory usage of collector process (memory leak detection)

**Metrics about network monitoring:**
- `network_metrics_collected_total` — total metrics stored (Prometheus counter)
- `network_metrics_collection_duration_seconds` — time to collect all cameras (Prometheus histogram)
- `network_websocket_connections_active` — currently connected WS clients (Prometheus gauge)
- `network_alerts_triggered_total` — alerts triggered by type (Prometheus counter)

---

*Last updated: 2026-07-23*
*Plan version: v2 (final)*
