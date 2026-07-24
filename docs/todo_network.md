# mBm NVR System — Network Monitoring TODO (Сүлжээний урсгалын хяналт)

> **Status legend:** `[ ]` not started, `[~]` in progress, `[x]` done, `[-]` blocked/not applicable
> **Created:** 2026-07-23
> **Last updated:** 2026-07-23 (v4 — aligned with current codebase)

---

## Overview

Network monitoring dashboard showing real-time bandwidth, latency, packet loss per camera. Historical data stored for trend analysis. Linear charts with time-range selector. All cameras overview + location-based filtering.

**MVP scope:** Core metrics collection, dashboard UI, WebSocket real-time push, Telegram/webhook alert notifications, in-app alerts page.

---

## Architecture Notes (Current Codebase)

### Existing infrastructure to reuse:
- **WebSocket**: `ws_manager.py` + `ws.py` — camera_status + event broadcast already working
- **Notification service**: `notification_service.py` — Telegram + webhook delivery already built
- **Stream relay**: FFmpeg processes managed in `live_relay.py`, MediaMTX on port 9997
- **Dashboard pattern**: 5-card stat grid (`Dashboard.tsx`) + CameraGrid with drag-and-drop
- **i18n**: `LocaleContext.tsx` + `en.json`/`mn.json` — all UI text must use `t('key')`
- **Sidebar**: Already has Users, Schedules, Locations — just add Network menu item
- **AppShell routes**: All routes defined in `AppShell.tsx`

### Important integration points:
- `network_alerts` is independent from `alert_log` (alert_log tracks notification delivery)
- Camera status includes `online/offline/degraded/unknown` (degraded already in use)
- FFmpeg stats must come from MediaMTX REST API (`/v3/paths/{camera_id}`) or `/proc/{pid}/stat`
- Schedules page (`SchedulesPage.tsx`) should be merged into Recordings as a tab

---

## Phase 1: Database Schema (MVP — 3 Tables)

### 1.1 `network_metrics` — Time-series metrics storage

```sql
CREATE TABLE network_metrics (
    id              BIGSERIAL PRIMARY KEY,
    camera_id       UUID NOT NULL REFERENCES cameras(id),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
       -- Bandwidth (Mbps)
    inbound_mbps    NUMERIC(10,2),                   -- RTSP stream incoming bandwidth
    outbound_mbps   NUMERIC(10,2),                   -- FFmpeg relay outgoing bandwidth
    
       -- Latency (ms)
    rtt_ms          NUMERIC(8,2),                    -- Round-trip time to camera IP
    jitter_ms       NUMERIC(8,2),                    -- RTT variation
    rtsp_latency    NUMERIC(8,2),                    -- RTSP session setup latency
    
       -- Packet stats
    packets_sent    BIGINT,                          -- ICMP/RTSP packets sent
    packets_recv    BIGINT,                          -- Packets received
    packet_loss_pct NUMERIC(5,2),                    -- Percentage loss
    
       -- Connection quality
    fps_current     INTEGER,                         -- Current FPS from FFmpeg stderr
    bitrate_current NUMERIC(10,2),                   -- Current bitrate from FFmpeg stderr
    rtsp_reconnect_cnt INTEGER DEFAULT 0,            -- Session reconnection count
    
       -- FFmpeg process metrics
    ffmpeg_pid      INTEGER,                         -- FFmpeg process ID (if running)
    ffmpeg_cpu      NUMERIC(5,2),                    -- CPU usage of FFmpeg process
    ffmpeg_memory_mb NUMERIC(8,2),                   -- Memory usage of FFmpeg process
    
       -- Status
    status          VARCHAR(20) DEFAULT 'unknown',   -- online/offline/degraded
    error_message   TEXT
);

-- Hypertable if TimescaleDB available, otherwise regular table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('network_metrics', 'recorded_at', if_not_exists => TRUE);
    END IF;
END $$;

-- Indexes
CREATE INDEX idx_network_metrics_camera_time ON network_metrics (camera_id, recorded_at DESC);
CREATE INDEX idx_network_metrics_time ON network_metrics (recorded_at DESC);
CREATE INDEX idx_network_metrics_status ON network_metrics (status, recorded_at DESC) WHERE status != 'online';
```

### 1.2 `camera_network_config` — Per-camera monitoring config

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
    
       -- Alert thresholds
    bandwidth_warn_mbps NUMERIC(8,2) DEFAULT 10.0,
    bandwidth_crit_mbps NUMERIC(8,2) DEFAULT 5.0,
    latency_warn_ms     NUMERIC(8,2) DEFAULT 100,
    latency_crit_ms     NUMERIC(8,2) DEFAULT 300,
    packet_loss_warn_pct NUMERIC(5,2) DEFAULT 1.0,
    packet_loss_crit_pct NUMERIC(5,2) DEFAULT 5.0,
    
       -- Historical data retention (days)
    retention_days INTEGER NOT NULL DEFAULT 90,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed with all existing cameras
INSERT INTO camera_network_config (camera_id)
SELECT id FROM cameras ON CONFLICT (camera_id) DO NOTHING;
```

### 1.3 `network_alerts` — Alert history (independent from `alert_log`)

**Note:** Existing `alert_log` table tracks notification delivery (`event_id` → `notification_id`). `network_alerts` is a separate table for network-specific alerts, linked to `events.id` for correlation.

```sql
CREATE TABLE network_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id       UUID NOT NULL REFERENCES cameras(id),
    event_id        UUID REFERENCES events(id),      -- Correlate with existing events
    
       -- Alert details
    alert_type      VARCHAR(50) NOT NULL,            -- 'bandwidth_low', 'latency_high', 'packet_loss_high', 'camera_offline'
    severity        VARCHAR(10) NOT NULL,            -- 'warning', 'critical'
    message         TEXT NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES users(id),
    resolved_at     TIMESTAMPTZ,
    
       -- Alert context
    metadata        JSONB,                           -- { current_value: 4.2, threshold: 5.0, unit: 'mbps' }
    location        VARCHAR(255),                    -- Denormalized for quick filtering
    
    CONSTRAINT chk_network_alert_severity CHECK (severity IN ('warning', 'critical'))
);

CREATE INDEX idx_network_alerts_camera_time ON network_alerts (camera_id, triggered_at DESC);
CREATE INDEX idx_network_alerts_unack ON network_alerts (acknowledged_at IS NULL, triggered_at DESC);
CREATE INDEX idx_network_alerts_type ON network_alerts (alert_type, triggered_at DESC);
```

---

## Phase 2: Backend — Metrics Collector Service

### 2.1 File Structure

```
services/api/app/
├── services/
│    ├── network_monitor.py         # Main collector service + background task
│    ├── network_alerts.py          # Alert evaluation + creation logic
│    └── network_ws_bridge.py       # Bridge: broadcast metrics via existing ws_manager
├── api/v1/
│    └── network.py                 # Network API endpoints (new)
```

### 2.2 `network_monitor.py` — Core Collector

**Responsibilities:**
- Periodic ping to camera IP (ICMP)
- Collect FFmpeg/MediaMTX stats for FPS + bitrate
- Store metrics in `network_metrics` table
- Staggered polling: each camera polls at different offset to avoid simultaneous spikes

**Key design decisions:**

1. **Staggered polling** — Camera N starts at `(N * poll_interval / total_cameras) % poll_interval`. Prevents all 10 cameras from pinging simultaneously (2s sequential → ~0.5s effective).

2. **Concurrent limit** — `asyncio.Semaphore(5)` limits concurrent ping/parse operations. Prevents API thread starvation.

3. **FFmpeg stats source** — Use MediaMTX REST API (`GET /v3/paths/{camera_id}` on port 9997) for bitrate/fps data. Fallback to `/proc/{pid}/stat` if MediaMTX unavailable. Parse FFmpeg stderr from `live_relay.py` STREAM_DICT.

4. **Error resilience** — Failed ping/parse per camera does NOT stop other cameras. Each camera collection is wrapped in try/except, failures logged but collected separately.

5. **TimescaleDB fallback** — Migration checks for `timescaledb` extension. If unavailable, creates regular table. Queries work either way (indexes provide similar performance for small datasets).

```python
class NetworkMonitor:
    def __init__(self):
        self.running = False
        self._task: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(5)   # Concurrent limit
        self._camera_offsets: dict[UUID, float] = {}   # Stagger offsets
    
    async def start(self):
         """Start background collection loop. Called from app lifespan."""
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._collect_loop())
    
    async def stop(self):
         """Stop background collection. Called on app shutdown."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _collect_loop(self):
         """Main polling loop with staggered offsets."""
        while self.running:
            start_time = asyncio.get_event_loop().time()
            
             # Get all cameras with monitoring enabled
            cameras = await self._get_monitored_cameras()
            
             # Collect metrics for each camera (concurrent, semaphore-limited)
            tasks = [self._collect_single_camera(c, offset) 
                     for c, offset in self._camera_offsets.items()]
            await asyncio.gather(*tasks, return_exceptions=True)
            
             # Calculate next sleep: align to poll_interval boundaries
            elapsed = asyncio.get_event_loop().time() - start_time
            poll_interval = 30   # Default (can be per-camera avg)
            sleep_time = max(0, poll_interval - elapsed)
            await asyncio.sleep(sleep_time)
    
    async def _collect_single_camera(self, camera: Camera, offset_seconds: float):
         """Collect metrics for one camera. Independent error handling."""
         # Stagger start
        await asyncio.sleep(offset_seconds)
        
        async with self._semaphore:
            try:
                metrics = await self.collect_metrics(camera)
                if metrics:
                    await self.store_metrics(metrics)
                    alerts_created = await network_alert_service.evaluate_alerts(camera, metrics)
                    
                     # Send Telegram/webhook notifications for new alerts (MVP)
                    if alerts_created:
                        from .notification_service import notification_service
                        for alert in alerts_created:
                            await notification_service.send_network_alert(alert)
                    
                     # Broadcast via existing ws_manager (MVP)
                    from .ws_manager import ws_manager
                    await ws_manager.broadcast({
                        "type": "network_metric",
                        "camera_id": str(camera.id),
                        "metrics": metrics,
                    })
            except Exception as e:
                logger.error("network_collect_error", camera_id=str(camera.id), error=str(e))
    
    async def collect_metrics(self, camera: Camera) -> dict | None:
         """Collect all metrics for one camera. Returns None if collection failed."""
        results = {}
        
         # 1. ICMP ping
        if camera.config.ping_enabled:
            ping_result = await self.ping_camera(camera.ip_address)
            results.update(ping_result)
        
         # 2. MediaMTX stats (primary) or /proc/{pid}/stat (fallback)
        if camera.config.rtsp_check_enabled:
            mtmx_stats = await self.get_mediamtx_stats(camera.id)
            if mtmx_stats:
                results.update(mtmx_stats)
            else:
                proc_stats = await self.parse_proc_stats(camera.id)
                results.update(proc_stats)
        
         # Determine status
        results['status'] = self._determine_status(results)
        
        return results if results else None
    
    async def ping_camera(self, ip_address: str) -> dict:
         """ICMP ping via subprocess. Returns rtt_ms, jitter_ms, packet_loss_pct."""
         # Use "ping -c 3 -W 5 <ip>" in executor
         # Parse output for avg RTT, min/max RTT (for jitter), packet loss %
        pass
    
    async def get_mediamtx_stats(self, camera_id: UUID) -> dict | None:
         """Get bitrate/fps from MediaMTX REST API."""
         # GET http://127.0.0.1:9997/v3/paths/{camera_id}
         # Parse playback → segment timing, active readers/writers
        pass
    
    async def parse_proc_stats(self, camera_id: UUID) -> dict | None:
         """Fallback: read /proc/[pid]/stat + live_relay.py STREAM_DICT."""
         # 1. Find FFmpeg PID from STREAM_DICT (live_relay.py)
         # 2. Read /proc/{pid}/stat for CPU %
         # 3. Read /proc/{pid}/status for VmRSS (memory MB)
        pass
    
    def _determine_status(self, metrics: dict) -> str:
         """Determine camera status from collected metrics."""
        if not metrics.get('rtt_ms'):
            return 'offline'
        if metrics.get('packet_loss_pct', 0) > 5.0:
            return 'degraded'
        return 'online'
    
    async def store_metrics(self, metrics: dict) -> None:
         """Insert metrics into database."""
         # INSERT INTO network_metrics (camera_id, recorded_at, ...) VALUES (...)
        pass
    
    async def _get_monitored_cameras(self) -> list[Camera]:
         """Get all cameras with monitoring enabled + their configs."""
         # SELECT camera.*, camera_network_config.* FROM cameras
         # JOIN camera_network_config ON cameras.id = camera_network_config.camera_id
        pass
```

### 2.3 `network_alerts.py` — Alert Logic

**Responsibilities:**
- Evaluate threshold breaches
- Deduplicate alerts (same type within 5-minute cooldown)
- Auto-resolve when metrics return to normal
- Create `network_alerts` DB records
- Return created alerts for notification_service integration

**Key design decisions:**

1. **Alert cooldown** — Same alert type for same camera fires at most once per 5 minutes. Prevents alert storms.

2. **Auto-resolve** — When metrics return within thresholds, alert is marked resolved automatically. No manual intervention needed.

3. **Notification integration (MVP)** — When alerts are created, return them to caller. Caller invokes `notification_service.send_network_alert()` for Telegram/webhook delivery.

```python
class NetworkAlertService:
    ALERT_COOLDOWN_SECONDS = 300   # 5 minutes
    
    async def evaluate_alerts(self, camera: Camera, metrics: dict) -> list[dict]:
         """Check thresholds, create alerts if breached. Returns list of created alerts."""
        created = []
        
        checks = [
             ('bandwidth_low', metrics.get('outbound_mbps'), camera.config.bandwidth_crit_mbps, 'critical'),
             ('bandwidth_warn', metrics.get('outbound_mbps'), camera.config.bandwidth_warn_mbps, 'warning'),
             ('latency_high', metrics.get('rtt_ms'), camera.config.latency_crit_ms, 'critical'),
             ('latency_warn', metrics.get('rtt_ms'), camera.config.latency_warn_ms, 'warning'),
             ('packet_loss_high', metrics.get('packet_loss_pct'), camera.config.packet_loss_crit_pct, 'critical'),
             ('packet_loss_warn', metrics.get('packet_loss_pct'), camera.config.packet_loss_warn_pct, 'warning'),
         ]
        
        for alert_type, current_value, threshold, severity in checks:
            if current_value is None:
                continue
            
            breached = (
                 ('low' in alert_type and current_value < threshold) or
                 ('high' in alert_type and current_value > threshold)
             )
            
            if breached:
                 # Check cooldown — no same-type alert in last 5 min
                if await self._is_in_cooldown(camera.id, alert_type):
                    continue
                
                alert = await self._create_alert(camera, alert_type, severity, {
                     'current_value': current_value,
                     'threshold': threshold,
                 })
                created.append(alert)
                
                 # Also resolve any active alerts of opposite type (e.g., resolve warn when crit fires)
                await self._resolve_related_alerts(camera.id, alert_type)
        
         # Auto-resolve if metrics are back to normal
        await self._auto_resolve_if_ok(camera, metrics)
        
        return created
    
    async def _is_in_cooldown(self, camera_id: UUID, alert_type: str) -> bool:
         """Check if same alert type was fired within cooldown period."""
         # SELECT COUNT(1) FROM network_alerts 
         # WHERE camera_id = ? AND alert_type = ? 
         # AND triggered_at > NOW() - INTERVAL '5 minutes'
        pass
    
    async def _create_alert(self, camera: Camera, alert_type: str, severity: str, metadata: dict) -> dict:
         """Create new network alert record."""
         # INSERT INTO network_alerts (camera_id, alert_type, severity, message, metadata, location)
        pass
    
    async def _resolve_related_alerts(self, camera_id: UUID, new_alert_type: str):
         """Resolve warning alerts when critical fires (or vice versa)."""
        pass
    
    async def _auto_resolve_if_ok(self, camera: Camera, metrics: dict):
         """If all metrics within thresholds, resolve active alerts."""
         # Check if any active (unresolved) alerts exist for this camera
         # If current values are within warn thresholds → mark resolved
        pass
    
    async def get_active_alerts(self, db: AsyncSession) -> list[dict]:
         """Get all unacknowledged alerts for UI display."""
         # SELECT * FROM network_alerts WHERE acknowledged_at IS NULL ORDER BY triggered_at DESC
        pass
    
    async def acknowledge_alert(self, alert_id: UUID, user_id: UUID) -> dict:
         """Acknowledge a network alert."""
         # UPDATE network_alerts SET acknowledged_at = NOW(), acknowledged_by = ? WHERE id = ?
        pass
    
    async def get_all_alerts(self, db: AsyncSession, params: dict) -> dict:
         """Get paginated alerts with filters (camera_id, severity, alert_type)."""
         # SELECT * FROM network_alerts WHERE ... ORDER BY triggered_at DESC LIMIT ? OFFSET ?
        pass
```

### 2.4 `network_ws_bridge.py` — WebSocket Metric Broadcast Bridge

**Responsibilities:**
- Bridge between network_monitor and existing ws_manager
- Called after metrics stored to broadcast to connected clients
- Simple wrapper, no auth needed (ws_manager already handles connection lifecycle)

```python
from .ws_manager import ws_manager

async def broadcast_metric(camera_id: str, metrics: dict):
    """Broadcast network metric via existing ws_manager."""
    await ws_manager.broadcast({
        "type": "network_metric",
        "camera_id": camera_id,
        "metrics": metrics,
    })
```

### 2.5 API Endpoints (MVP)

**File:** `services/api/app/api/v1/network.py` (new)

```
POST     /api/v1/network/monitor/start           # Start background collection
POST     /api/v1/network/monitor/stop            # Stop background collection
GET      /api/v1/network/metrics                 # Latest metrics for all cameras (paginated)
GET      /api/v1/network/metrics/{camera_id}     # Latest metrics for single camera
GET      /api/v1/network/metrics/{camera_id}/history    # Historical data (time range, paginated)
PATCH    /api/v1/network/config/{camera_id}      # Update per-camera monitoring config
GET      /api/v1/network/alerts                  # Active (unacknowledged) alerts for current user
GET      /api/v1/network/alerts/all              # All alerts (paginated, filterable by camera/severity/type)
POST     /api/v1/network/alerts/{id}/acknowledge     # Acknowledge alert
GET      /api/v1/network/summary                 # Summary: total online/offline, avg bandwidth, etc.
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
          "bitrate_current": 4200,
          "ffmpeg_cpu": 8.5,
          "ffmpeg_memory_mb": 85.3,
          "status": "online"
        }
      ],
      "total_count": 2880,
      "page": 1,
      "per_page": 100
    }
}
```

**Response format — `/api/v1/network/summary`:**

```json
{
    "data": {
      "total_cameras": 10,
      "online_cameras": 8,
      "degraded_cameras": 1,
      "offline_cameras": 1,
      "avg_bandwidth_mbps": 4.5,
      "avg_latency_ms": 15.2,
      "avg_packet_loss_pct": 0.1,
      "active_alerts": 1,
      "alerts_by_severity": { "warning": 1, "critical": 0 },
      "cameras_by_location": {
        "Entrance": { "total": 3, "online": 3, "avg_bw": 4.8 },
        "Parking": { "total": 4, "online": 2, "degraded": 1, "offline": 1, "avg_bw": 3.9 },
        "Office": { "total": 3, "online": 3, "avg_bw": 5.1 }
      }
    }
}
```

**Response format — `/api/v1/network/alerts`:**

```json
{
    "data": [
      {
        "id": "uuid",
        "camera_id": "uuid",
        "camera_name": "Camera 03",
        "location": "Parking",
        "alert_type": "latency_high",
        "severity": "critical",
        "message": "RTT 450ms exceeds critical threshold of 300ms",
        "triggered_at": "2026-07-23T12:05:00Z",
        "acknowledged_at": null,
        "metadata": { "current_value": 450, "threshold": 300, "unit": "ms" }
      }
    ]
}
```

### 2.6 Background Task Integration

**File:** `services/api/app/main.py` (modify lifespan)

Current lifespan:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_starting", version="0.1.0", env=settings.api_log_level)
    await get_redis()
    yield
    await close_redis()
    await engine.dispose()
    logger.info("app_stopped")
```

Add network monitor start/stop:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_starting", version="0.1.0", env=settings.api_log_level)
    await get_redis()
    
     # Start network monitor (non-blocking)
    from .services.network_monitor import network_monitor
    await network_monitor.start()
    
    yield
    
     # Cleanup
    await network_monitor.stop()
    await close_redis()
    await engine.dispose()
    logger.info("app_stopped")
```

### 2.7 Register API router

**File:** `services/api/app/api/v1/__init__.py` (modify)

Add:
```python
from .network import router as network_router

router = APIRouter()
router.include_router(network_router, prefix="/network", tags=["network"])
# ... other routers
```

---

## Phase 3: Frontend — Dashboard & Components (MVP)

### 3.1 File Structure

```
services/web/src/
├── pages/
│    └── NetworkDashboard.tsx            # Main dashboard page
├── components/
│    ├── network/
│    │    ├── NetworkSummaryBar.tsx      # Top summary stats (5-card grid)
│    │    ├── LocationFilter.tsx         # Location tab filter
│    │    ├── CameraMetricCard.tsx       # Per-camera metric card with sparkline
│    │    └── NetworkChart.tsx           # Full-page linear chart component
│    └── ui/                             # Existing (EmptyState, Toast, ConfirmDialog)
├── hooks/
│    └── useNetwork.ts                   # All TanStack Query hooks
├── types/
│    └── network.ts                      # TypeScript interfaces
├── api/
│    └── network.ts                      # API client methods
└── i18n/
     ├── translations/en.json            # Add network keys
     └── translations/mn.json            # Add network keys
```

### 3.2 `NetworkDashboard.tsx` — Main Page Layout

**Pattern:** Follow existing `Dashboard.tsx` layout (5-card stat grid + content below).

```
┌───────────────────────────────────────────────────────────────────────┐
│  Network Dashboard                                     [Start ▶] [Stop ■] │
├───────────────────────────────────────────────────────────────────────┤
│     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │
│     │ Total: 10     │ │ Online: 8     │ │ Degraded: 1    │ │ Offline: 1 │ │
│     └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ │
│     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │
│     │ Alerts: 1      │ │ Avg BW: 4.5  │ │ Avg Lat: 15ms │                 │
│     └──────────────┘ └──────────────┘ └──────────────┘                 │
│                                                                         │
│     [All Cameras] [Entrance] [Parking] [Office]                          │
│                                                                         │
│     ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│     │ Camera 01│ │ Camera 02│ │ Camera 03│ │ Camera 04│ ...             │
│     │ Online ● │ │ Degraded ●│ │ Offline ○ │ │ Online ● │                 │
│     │ BW: 4.2    │ │ BW: 3.1    │ │ BW: --      │ │ BW: 5.1    │                 │
│     │ Lat: 12ms│ │ Lat: 85ms│ │ Lat: --     │ │ Lat: 10ms│                 │
│     │ FPS: 25    │ │ FPS: 18    │ │ FPS: --     │ │ FPS: 25    │                 │
│     │ Loss: 0% │ │ Loss: 0.5%│ │ Loss: -- │ │ Loss: 0% │                 │
│     │ ──▁▂▃▅▄▃──│ │ ──▅▄▃▂▁▂──│ │             │ │ ──▁▂▃▄▅▆──│                 │
│     └──────────┘ └──────────┘ └──────────┘ └──────────┘                 │
│                                                                         │
│     ┌───────────────────────────────────────────────────────────────┐     │
│     │ Bandwidth (Mbps) — Last 24h                         [▼ 1h/6h/12h/24h/7d]│
│     │ ────────────────────────────────────────────────────────────     │     │
│     │                                                                │     │
│     │    5.0 ┤       ╱╲           ╱╲                                   │     │
│     │    4.0 ┤     ╱╱    ╲──────╱    ╲──╲                              │     │
│     │    3.0 ┤ ╱╱        ╲      ╱      ╲    ╲                           │     │
│     │    2.0 ┤╱          ╲__/╱        ╲__╲                           │     │
│     │    1.0 ┤            ╲/           ╲___╲                         │     │
│     │    0.0 ┼────────────┴────────────┴───────────→ Time            │     │
│     │           00:00      06:00      12:00      18:00      24:00         │     │
│     └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│     ┌───────────────────────────────────────────────────────────────┐     │
│     │ Latency (ms) — Last 24h                         [▼ 1h/6h/12h/24h/7d]│
│     │ ────────────────────────────────────────────────────────────     │     │
│     │                                                                │     │
│     │    300 ┤ ───────────── Warning (100ms)                           │     │
│     │    200 ┤                                                         │     │
│     │    100 ┤          ╱╲         ╱╲                                   │     │
│     │     50 ┤        ╱╱    ╲────╱      ╲────                           │     │
│     │     25 ┤      ╱╱        ╲__/          ╲___                        │     │
│     │      10 ┤    ╱                                                           │     │
│     │       0 ┼──╱────────────────────────────→ Time                    │     │
│     │           00:00      06:00      12:00      18:00      24:00             │     │
│     └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│     ┌───────────────────────────────────────────────────────────────┐     │
│     │ Active Alerts (1)                                             │     │
│     │ ────────────────────────────────────────────────────────────     │     │
│     │ Camera 03 • Parking • Latency: 450ms > 300ms (critical)        │     │
│     │ [Acknowledge]                                                  │     │
│     └───────────────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────┘
```

**Features (MVP):**
- 7-card stat grid (total/online/degraded/offline/alerts/avg_bw/avg_lat) — matches Dashboard.tsx pattern
- Location filter tabs: All Cameras / Entrance / Parking / Office (uses existing `/api/v1/locations`)
- Camera grid: cards with current metrics + sparkline trend (last 30 min)
- Bandwidth chart: linear chart, all cameras color-coded, time range selector
- Latency chart: linear chart with warning threshold reference line
- Active alerts section at bottom
- Start/Stop buttons: control background collection
- Auto-refresh every 30s via polling (WebSocket push also active in MVP)

**Interactive features:**
- Click camera card → expand to show full history for that camera (inline expansion, not drawer — simpler for MVP)
- Hover on chart → tooltip with all cameras' values at that timestamp
- Alert badge on camera card when active alert exists
- Acknowledge alert inline from dashboard

### 3.3 `NetworkChart.tsx` — Linear Chart Component

**Library:** Recharts

```bash
npm install recharts
```

**Props (MVP):**

```typescript
interface NetworkChartProps {
  data: NetworkMetricPoint[];
  metric: 'bandwidth' | 'latency';
  timeRange: '1h' | '6h' | '12h' | '24h' | '7d';
  height?: number;
  showThresholdLine?: boolean;
  thresholdValue?: number;
  thresholdLabel?: string;
}
```

**Features (MVP):**
- Linear line chart (`Recharts.LineChart` + `Recharts.Line`)
- Multiple cameras on same chart (color-coded lines, one per camera)
- Time axis with auto-formatted labels (respects timeRange)
- Hover tooltip with exact values for all cameras at cursor position
- Warning/critical threshold reference line (dashed red)
- Responsive sizing
- Area fill option (translucent gradient under line)

### 3.4 `CameraMetricCard.tsx` — Per-Camera Card

**Pattern:** Follow existing CameraTile from `CameraGrid.tsx` (status indicator, name, IP, location badge).

**Shows per camera (MVP):**
- Camera name + status indicator (green dot = online, yellow = degraded, gray = offline)
- Current bandwidth (Mbps)
- Current latency (ms)
- FPS (current)
- Packet loss (%)
- Mini sparkline chart (last 30 min, 60 points at 30s interval) — Recharts `AreaChart` mini
- Alert badge (red dot with number) if active alert exists

**Sparkline behavior:**
- Shows last 60 data points (30 min at 30s interval)
- Compressed horizontally, ~120px wide
- Color matches status (green/yellow/red)
- Hover shows exact value at that point

### 3.5 `NetworkSummaryBar.tsx` — Top Summary Stats

**Pattern:** Follow existing Dashboard.tsx stat cards (icon + label + value + subtext).

Shows at top of dashboard:
- Total cameras / online / degraded / offline count (separate cards)
- Active alert count (clickable → scrolls to alerts section)
- Average bandwidth across all cameras
- Average latency across all cameras
- Last updated timestamp (e.g., "Updated 15s ago")

### 3.6 `LocationFilter.tsx` — Location Tabs

**Pattern:** Follow existing tab patterns in the codebase.

- Tab bar with locations from API
- "All Cameras" tab shows everything
- Selected location tab filters grid + charts
- Uses existing `/api/v1/locations` endpoint for location list
- Active tab highlighted (blue bg, white text — same pattern as Sidebar NavLink)

### 3.7 Inline Camera Expansion

**Instead of a slide-over drawer (deferred), MVP uses inline expansion:**

When clicking a camera card:
- Card expands downward (CSS max-height transition)
- Shows full history chart for that single camera (bandwidth + latency)
- Shows detailed metrics table (all fields)
- Shows recent alert history for this camera (last 7 days, last 5 entries)
- Click again or click elsewhere → collapses

This avoids needing a drawer component and is simpler to implement.

### 3.8 Sidebar Navigation Item

**File:** `services/web/src/components/layout/Sidebar.tsx` (modify)

Current navItems:
```typescript
const navItems = [
    { to: "/dashboard", icon: LayoutDashboard, key: "nav.dashboard" },
    { to: "/cameras", icon: Video, key: "nav.cameras" },
    { to: "/recordings", icon: Film, key: "nav.recordings" },
    { to: "/events", icon: Bell, key: "nav.events" },
    { to: "/storage", icon: HardDrive, key: "nav.storage" },
    { to: "/locations", icon: MapPin, label: "Locations", admin: true },
    { to: "/schedules", icon: Clock, label: "Schedules", admin: true },  // ← Merge into Recordings
    { to: "/settings/users", icon: Users, label: "Users", admin: true },
    { to: "/settings", icon: Settings, key: "nav.settings" },
];
```

Add Network between Events and Storage:
```typescript
const navItems = [
    { to: "/dashboard", icon: LayoutDashboard, key: "nav.dashboard" },
    { to: "/cameras", icon: Video, key: "nav.cameras" },
    { to: "/recordings", icon: Film, key: "nav.recordings" },
    { to: "/events", icon: Bell, key: "nav.events" },
    { to: "/network", icon: Activity, key: "nav.network" },     // <-- NEW (between Events and Storage)
    { to: "/storage", icon: HardDrive, key: "nav.storage" },
    { to: "/locations", icon: MapPin, label: "Locations", admin: true },
    { to: "/settings/users", icon: Users, label: "Users", admin: true },
    { to: "/settings", icon: Settings, key: "nav.settings" },
];
```

**Icon:** `Activity` from `lucide-react` (pulse/heartbeat icon)

Remove `/schedules` route (merge into Recordings page as tab).

### 3.9 Route Configuration

**File:** `services/web/src/components/layout/AppShell.tsx` (modify)

Add `/network` route, remove `/schedules` route:

Current:
```typescript
<Route path="/recordings" element={<Recordings />} />
<Route path="/events" element={<Events />} />
<Route path="/storage" element={<Storage />} />
<Route path="/locations" element={<LocationsPage />} />
<Route path="/schedules" element={<SchedulesPage />} />
```

New:
```typescript
<Route path="/recordings" element={<Recordings />} />
<Route path="/events" element={<Events />} />
<Route path="/network" element={<NetworkDashboard />} />     {/* <-- NEW */}
<Route path="/storage" element={<Storage />} />
<Route path="/locations" element={<LocationsPage />} />
{/* /schedules removed — merged into Recordings page */}
```

---

## Phase 4: Frontend — Hooks, Types & API Client

### 4.1 TypeScript Types

**File:** `services/web/src/types/network.ts` (new)

```typescript
export interface NetworkMetricPoint {
  recorded_at: string;
  
     // Bandwidth
  inbound_mbps: number | null;
  outbound_mbps: number | null;
  
     // Latency
  rtt_ms: number | null;
  jitter_ms: number | null;
  rtsp_latency: number | null;
  
     // Packet stats
  packets_sent: number | null;
  packets_recv: number | null;
  packet_loss_pct: number | null;
  
     // Connection quality
  fps_current: number | null;
  bitrate_current: number | null;
  rtsp_reconnect_cnt: number | null;
  
     // FFmpeg process metrics
  ffmpeg_pid: number | null;
  ffmpeg_cpu: number | null;
  ffmpeg_memory_mb: number | null;
  
     // Status
  status: 'online' | 'offline' | 'degraded' | 'unknown';
  error_message: string | null;
}

export interface MetricPageResponse {
  camera_id: string;
  camera_name: string;
  location: string | null;
  time_range: { start: string; end: string };
  metrics: NetworkMetricPoint[];
  total_count: number;
  page: number;
  per_page: number;
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
  bandwidth_warn_mbps: number;
  bandwidth_crit_mbps: number;
  latency_warn_ms: number;
  latency_crit_ms: number;
  packet_loss_warn_pct: number;
  packet_loss_crit_pct: number;
  retention_days: number;
}

export interface NetworkDashboardSummary {
  total_cameras: number;
  online_cameras: number;
  degraded_cameras: number;
  offline_cameras: number;
  avg_bandwidth_mbps: number | null;
  avg_latency_ms: number | null;
  avg_packet_loss_pct: number | null;
  active_alerts: number;
  alerts_by_severity: { warning: number; critical: number };
  cameras_by_location: Record<string, LocationSummary>;
}

export interface LocationSummary {
  total: number;
  online: number;
  degraded: number;
  offline: number;
  avg_bw: number | null;
}

export interface NetworkAlert {
  id: string;
  camera_id: string;
  camera_name: string;
  location: string | null;
  alert_type: 'bandwidth_low' | 'latency_high' | 'packet_loss_high' | 'camera_offline';
  severity: 'warning' | 'critical';
  message: string;
  triggered_at: string;
  acknowledged_at: string | null;
  metadata: Record<string, any> | null;
}

export interface NetworkConfigUpdate {
  poll_interval?: number;
  ping_enabled?: boolean;
  ping_count?: number;
  ping_timeout?: number;
  rtsp_check_enabled?: boolean;
  bandwidth_warn_mbps?: number;
  bandwidth_crit_mbps?: number;
  latency_warn_ms?: number;
  latency_crit_ms?: number;
  packet_loss_warn_pct?: number;
  packet_loss_crit_pct?: number;
  retention_days?: number;
}
```

### 4.2 API Client Methods

**File:** `services/web/src/api/network.ts` (new)

```typescript
import apiClient from './client';

export const networkApi = {
     // Metrics
  getMetrics: () => apiClient.get('/network/metrics'),
  getCameraMetrics: (cameraId: string) => 
    apiClient.get(`/network/metrics/${cameraId}`),
  getCameraHistory: (cameraId: string, params: { start?: string; end?: string; range?: string; page?: number; per_page?: number }) => 
    apiClient.get(`/network/metrics/${cameraId}/history`, { params }),
  
     // Summary & Alerts
  getSummary: () => apiClient.get('/network/summary'),
  getActiveAlerts: () => apiClient.get('/network/alerts'),
  getAllAlerts: (params?: { camera_id?: string; severity?: string; alert_type?: string; page?: number; per_page?: number }) => 
    apiClient.get('/network/alerts/all', { params }),
  acknowledgeAlert: (alertId: string) => 
    apiClient.post(`/network/alerts/${alertId}/acknowledge`),
  
     // Monitoring control
  startMonitoring: () => apiClient.post('/network/monitor/start'),
  stopMonitoring: () => apiClient.post('/network/monitor/stop'),
  
     // Config
  getCameraConfig: (cameraId: string) => 
    apiClient.get(`/network/config/${cameraId}`),
  updateConfig: (cameraId: string, config: NetworkConfigUpdate) => 
    apiClient.patch(`/network/config/${cameraId}`, config),
};
```

### 4.3 React Hooks

**File:** `services/web/src/hooks/useNetwork.ts` (new)

Existing hooks pattern from `useCameras.ts`, `useRecordings.ts`:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { networkApi } from '../api/network';
import type { NetworkMetricPoint, NetworkDashboardSummary, NetworkAlert, NetworkConfigUpdate } from '../types/network';

// useNetworkMetrics — latest metrics for all cameras
export function useNetworkMetrics() {
  return useQuery({ queryKey: ['network', 'metrics'], queryFn: networkApi.getMetrics });
}

// useCameraMetrics — latest metrics for single camera
export function useCameraMetrics(cameraId: string) {
  return useQuery({ 
    queryKey: ['network', 'metrics', cameraId], 
    queryFn: () => networkApi.getCameraMetrics(cameraId),
    enabled: !!cameraId,
  });
}

// useCameraHistory — historical data with time range
export function useCameraHistory(
  cameraId: string,
  timeRange: '1h' | '6h' | '12h' | '24h' | '7d' = '24h'
) {
  return useQuery({
    queryKey: ['network', 'history', cameraId, timeRange],
    queryFn: () => networkApi.getCameraHistory(cameraId, { range: timeRange }),
    enabled: !!cameraId,
  });
}

// useNetworkSummary — dashboard summary stats
export function useNetworkSummary() {
  return useQuery({ 
    queryKey: ['network', 'summary'], 
    queryFn: networkApi.getSummary,
    refetchInterval: 30_000,   // Auto-refresh every 30s (matches polling interval)
  });
}

// useActiveAlerts — active (unacknowledged) alerts
export function useActiveAlerts() {
  return useQuery({ 
    queryKey: ['network', 'alerts'], 
    queryFn: networkApi.getActiveAlerts,
    refetchInterval: 15_000,   // More frequent for alerts
  });
}

// useAllAlerts — all alerts with pagination/filters
export function useAllAlerts(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['network', 'alerts', 'all', params],
    queryFn: () => networkApi.getAllAlerts(params),
  });
}

// useNetworkConfig — per-camera config CRUD
export function useNetworkConfig(cameraId: string) {
  const qc = useQueryClient();
  return {
    query: useQuery({
      queryKey: ['network', 'config', cameraId],
      queryFn: () => networkApi.getCameraConfig(cameraId),
      enabled: !!cameraId,
    }),
    update: useMutation({
      mutationFn: (config: NetworkConfigUpdate) => networkApi.updateConfig(cameraId, config),
      onSuccess: () => qc.invalidateQueries({ queryKey: ['network', 'config', cameraId] }),
    }),
  };
}

// useMonitoringControl — start/stop background collection
export function useMonitoringControl() { 
  const qc = useQueryClient();
  return {
    start: useMutation({ mutationFn: networkApi.startMonitoring, onSuccess: () => qc.invalidateQueries({ queryKey: ['network', 'summary'] }) }),
    stop: useMutation({ mutationFn: networkApi.stopMonitoring, onSuccess: () => qc.invalidateQueries({ queryKey: ['network', 'summary'] }) }),
  };
}

// useAcknowledgeAlert — acknowledge a network alert
export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) => networkApi.acknowledgeAlert(alertId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['network', 'alerts'] });
      qc.invalidateQueries({ queryKey: ['network', 'summary'] });
    },
  });
}
```

### 4.4 WebSocket Metric Update Hook Extension

**IMPORTANT:** Existing `useNvrWebSocket` hook in `useWebSocket.ts` already handles camera_status and event messages. We need to extend it for network_metric messages.

**File:** `services/web/src/hooks/useWebSocket.ts` (modify)

Current message type:
```typescript
type WsMessage = {
  type: "camera_status" | "event";
  camera_id?: string;
  status?: string;
  connection_error?: string | null;
  event?: Record<string, unknown>;
};
```

Add `network_metric` type:
```typescript
type WsMessage = {
  type: "camera_status" | "event" | "network_metric";   // <-- NEW
  camera_id?: string;
  status?: string;
  connection_error?: string | null;
  event?: Record<string, unknown>;
  metrics?: Record<string, unknown>;   // <-- NEW (for network_metric)
};
```

Hook signature extension:
```typescript
export function useNvrWebSocket(
  onCameraStatus?: (cameraId: string, status: string, error: string | null) => void,
  onEvent?: (event: Record<string, unknown>) => void,
  onNetworkMetric?: (cameraId: string, metrics: Record<string, unknown>) => void,   // <-- NEW
) {
  // ... existing code ...
  
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data) as WsMessage;
      if (msg.type === "camera_status" && msg.camera_id && callbacksRef.current.onCameraStatus) {
        callbacksRef.current.onCameraStatus(msg.camera_id, msg.status || "", msg.connection_error || null);
       } else if (msg.type === "event" && msg.event && callbacksRef.current.onEvent) {
        callbacksRef.current.onEvent(msg.event);
       } else if (msg.type === "network_metric" && msg.camera_id && msg.metrics && callbacksRef.current.onNetworkMetric) {   // <-- NEW
        callbacksRef.current.onNetworkMetric(msg.camera_id, msg.metrics);
       }
    } catch { /* ignore malformed */ }
  };
  
  return wsRef;
}
```

Dashboard integration pattern (existing Dashboard.tsx already uses `useNvrWebSocket`):
```typescript
const onNetworkMetric = useCallback(
  (cameraId: string, metrics: Record<string, unknown>) => {
     // Invalidate network queries when new metric arrives
    qc.invalidateQueries({ queryKey: ['network', 'metrics'] });
    qc.invalidateQueries({ queryKey: ['network', 'summary'] });
   },
  [qc],
);
useNvrWebSocket(onCameraStatus, onEvent, onNetworkMetric);
```

---

## Phase 5: Database Migration

### 5.1 Alembic Migration

**File:** `services/api/alembic/versions/XXXX_add_network_monitoring.py` (new)

Steps:
1. Create `network_metrics` table (with TimescaleDB hypertable if extension available)
2. Create `camera_network_config` table
3. Seed `camera_network_config` for all existing cameras (`ON CONFLICT DO NOTHING`)
4. Create `network_alerts` table with constraints
5. Create indexes for time-series queries
6. Down migration: drop tables in reverse order (alerts → config → metrics)

**TimescaleDB fallback:** Migration checks `pg_extension` for `timescaledb`. If not present, creates regular table. All queries use standard PostgreSQL syntax that works on both.

---

## Phase 6: Testing

### 6.1 API Tests

**File:** `services/api/tests/test_network_monitor.py`

- Mock FFmpeg output parsing (test regex on sample stderr lines)
- Mock ICMP ping responses (mock subprocess output)
- Test metrics storage and retrieval (use test DB session)
- Test alert threshold evaluation (breach + cooldown + auto-resolve)
- Test historical data time-range queries
- Test staggered polling logic (offset calculation)

**File:** `services/api/tests/test_network_alerts.py`

- Test alert cooldown (same type within 5 min → no duplicate)
- Test auto-resolve (metrics return to normal → alert resolved)
- Test severity escalation (warn → critical → resolve warn automatically)

### 6.2 Frontend Tests

**File:** `services/web/src/test/network.test.tsx`

- NetworkChart component rendering with sample data
- CameraMetricCard with various states (online/offline/degraded)
- Location filtering logic (filter by location name)
- Time range selector behavior (change timeRange → fetch new data)
- Sparkline chart rendering (60 points, compressed width)
- Inline camera expansion (click card → expand/collapse)
- useCameraHistory data fetching and error handling

### 6.3 Manual Testing Checklist

**Backend:**
- [ ] Start network monitoring → verify metrics appear in DB
- [ ] Verify FFmpeg stderr parsing captures fps/bitrate correctly
- [ ] Verify ICMP ping returns accurate RTT/jitter/packet_loss
- [ ] Verify alert thresholds trigger correctly (manually set low thresholds)
- [ ] Verify alert cooldown works (same type doesn't fire within 5 min)
- [ ] Verify auto-resolve works (metrics return to normal → alert resolved)
- [ ] Verify staggered polling (cameras don't all ping simultaneously)
- [ ] Verify hardware load → monitoring doesn't overwhelm system
- [ ] Verify WebSocket broadcast delivers metrics to connected clients
- [ ] Verify Telegram webhook delivers network alerts

**Frontend:**
- [ ] View dashboard → verify all cameras show correct metrics
- [ ] Click location filter → verify grid + charts update
- [ ] Change time range (1h/6h/12h/24h/7d) → verify chart data updates
- [ ] Offline camera → verify gray status + no chart data
- [ ] Degraded camera → verify yellow status + warning indicators
- [ ] Alert thresholds → verify alert badge appears on camera card
- [ ] Auto-refresh → verify metrics update every 30s
- [ ] Click camera card → verify inline expansion with full chart
- [ ] Start/Stop monitoring → verify background collection starts/stops
- [ ] WebSocket live → verify real-time metric updates (no manual refresh needed)
- [ ] Responsive layout → verify on mobile/tablet sizes
- [ ] Sidebar Network link → navigate to dashboard correctly

---

## Implementation Order (Recommended)

### Sprint 1: Backend Foundation (~2-3 days)
1. Database migration (3 tables + seed data)
2. `network_monitor.py` — collector service with ping + MediaMTX stats
3. `network_alerts.py` — alert evaluation + cooldown + auto-resolve
4. `network_ws_bridge.py` — WebSocket metric broadcast
5. API endpoints (`api/v1/network.py`)
6. Register router in `api/v1/__init__.py`
7. Background task integration in `app/main.py` lifespan
8. Unit tests (collector, alerts, thresholds)

### Sprint 2: Frontend Dashboard (~2-3 days)
9. TypeScript types (`types/network.ts`)
10. API client (`api/network.ts`)
11. Hooks (`hooks/useNetwork.ts`) — data fetching + WebSocket integration
12. Extend `useWebSocket.ts` for network_metric type
13. `NetworkChart.tsx` — linear chart component with Recharts
14. `CameraMetricCard.tsx` — per-camera card with sparkline
15. `NetworkSummaryBar.tsx` — top summary stats
16. `LocationFilter.tsx` — location tab filter
17. `NetworkDashboard.tsx` — main page layout (follow Dashboard.tsx pattern)
18. Add Network to Sidebar (`Sidebar.tsx`)
19. Add `/network` route in AppShell, remove `/schedules` route
20. i18n translation keys (`en.json`, `mn.json`)
21. Frontend tests

### Sprint 3: Polish & QA (~1-2 days)
22. Manual testing checklist
23. Performance tuning (query optimization, chart rendering)
24. Error handling improvements
25. Responsive layout fixes
26. Merge SchedulesPage into Recordings page (tab UI)

**Total estimated: ~5-8 days for MVP**

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Chart library | Recharts | Lightweight, React-native, good linear chart support |
| Data granularity | 30-second intervals | Balance between detail and storage size |
| Historical retention | 90 days default | Configurable per camera |
| Ping method | `asyncio.create_subprocess_exec("ping")` | No extra dependencies, reliable |
| FFmpeg stats source | MediaMTX REST API (`/v3/paths/{camera_id}`) primary, `/proc/{pid}/stat` fallback | Already have MediaMTX running on port 9997 |
| Alert evaluation | On-store (triggered when metrics written) | Real-time, no extra polling |
| Auto-refresh | 30s polling via `refetchInterval` in TanStack Query + WebSocket push (MVP) | Dual approach: WS for real-time, polling as fallback |
| WebSocket auth | Existing JWT query param in `useWebSocket.ts` | Reuse existing ws_manager infrastructure |
| Staggered polling | Offset = `(camera_index * poll_interval / total_cameras)` | Prevents simultaneous ping spikes |
| Concurrent limit | `asyncio.Semaphore(5)` | Prevents API thread starvation |
| TimescaleDB | Optional (fallback to regular table) | Works with or without extension |
| Alert cooldown | 5 minutes per camera per type | Prevents alert storms |
| Inline expansion | Card expands downward (MVP) | Simpler than slide-over drawer |
| Error handling | Per-camera try/except in gather | One camera failure doesn't affect others |
| Notification delivery | `notification_service.send_network_alert()` on alert creation | Reuse existing Telegram + webhook infrastructure |

---

## Storage Estimation

**Per camera per day (30s intervals = 2880 points):**
- ~2880 rows × ~250 bytes/row ≈ 720 KB/day
- 90 days retention ≈ 65 MB/camera
- 10 cameras ≈ 650 MB total

**Per camera config:**
- ~500 bytes/camera (negligible)

**Network alerts:**
- Estimated 5 alerts/camera/month × 10 cameras × 90 days ≈ 1350 rows ≈ 500 KB (negligible)

**Total MVP storage: ~650 MB for 10 cameras over 90 days**

---

## Performance Considerations

**Backend:**
- Staggered polling: cameras poll at different offsets, effective collection time ~0.5s instead of 22s sequential
- Concurrent limit: `asyncio.Semaphore(5)` prevents thread starvation
- Batch DB inserts: accumulate metrics per cycle, single INSERT ... VALUES (...), (...), (...) query
- FFmpeg parsing: MediaMTX REST API call is instant (~10ms), no subprocess needed
- WebSocket broadcast: async fan-out to subscribers, doesn't block collector

**Frontend:**
- Chart data loading: TanStack Query caching + stale-while-revalidate (auto 30s refetch)
- Sparkline optimization: only render last 60 points, not full history
- Large dataset rendering: Recharts handles ~1000 points fine (24h at 30s = 2880 points, may need sampling for 7d views)
- WebSocket push: real-time updates bypass polling entirely when connected

**Database:**
- Indexes on (camera_id, recorded_at DESC) for efficient per-camera history queries
- Index on (recorded_at DESC) for summary aggregations
- Partial index on status where status != 'online' for quick degraded/offline detection

---

## Security Considerations

- Network metrics endpoint: same auth as other API endpoints (JWT required)
- WebSocket connection: already handled by existing ws_manager (JWT query param validation)
- Rate limit metric collection: prevent misconfiguration from excessive polling (< 10s interval rejected by backend)

---

## Monitoring the Monitor

**Self-health checks (MVP):**
- Background collector task status: running/stopped/errored (exposed via `/api/v1/network/summary` → `monitoring_status` field)
- Last collection timestamp per camera (stale data detection — if >2× poll_interval since last metric, show "data stale" warning)

---

*Last updated: 2026-07-23*
*Plan version: v4 (aligned with current codebase, WebSocket + notifications in MVP)*
