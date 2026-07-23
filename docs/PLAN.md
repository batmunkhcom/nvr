# mBm NVR System — Бүрэн архитектур төлөвлөгөө

**Хамрах хүрээ:** Database schema, API specification, streaming architecture, AI pipeline,
security design, recording engine, storage lifecycle, deployment, vendor analysis, frontend architecture.

---

## 1. Технологийн Стек

| Бүрэлдэхүүн         | Технологи                                  | Хувилбар |
|---------------------|--------------------------------------------|----------|
| API сервер          | Python FastAPI + uvicorn                   | 3.13 / 0.115 |
| ORM                 | SQLAlchemy (async)                         | 2.0 |
| Migration           | Alembic                                    | 1.14 |
| Database            | PostgreSQL                                 | 16 |
| Time-series         | TimescaleDB (extension)                    | 2.16 |
| Cache / PubSub      | Redis                                      | 7.4 |
| Media processing    | FFmpeg                                     | 7.0 |
| AI runtime          | ONNX Runtime                               | 1.20 |
| AI models           | YOLOv8n, RetinaFace, ArcFace, YAMNet       | — |
| Computer vision     | OpenCV (headless)                          | 4.10 |
| Object storage      | MinIO (S3-compatible)                      | latest |
| Frontend framework  | React + TypeScript                         | 19 / 5.7 |
| State management    | Zustand                                    | 5.x |
| HTTP client         | TanStack Query (React Query)               | 5.x |
| Build tool          | Vite                                       | 6.x |
| UI components       | Radix UI + Tailwind CSS                    | latest |
| Streaming protocol  | WebRTC + HLS fallback                      | — |
| Infra               | Docker Compose v2                          | latest |
| TLS termination     | NGINX                                      | 1.27 |
| CI/CD               | GitHub Actions                             | — |

---

## 2. Өгөгдлийн Сангийн Бүрэн Схем (DDL)

### 2.1 Extension Setup

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### 2.2 ENUM Types

```sql
CREATE TYPE user_role AS ENUM ('admin', 'operator', 'viewer');
CREATE TYPE recording_mode AS ENUM ('continuous', 'motion', 'scheduled');
-- recording_type = actual trigger that created the recording:
--   continuous=always-on, motion=motion_detected event, manual=user clicked record,
--   event=AI/audio/system event
-- Mapping: 'scheduled' mode → 'continuous' type during active schedule window
CREATE TYPE recording_type AS ENUM ('continuous', 'motion', 'manual', 'event');
CREATE TYPE event_severity AS ENUM ('info', 'warning', 'critical');
CREATE TYPE storage_backend_type AS ENUM ('local', 'nfs', 'smb', 's3');
CREATE TYPE stream_transport AS ENUM ('tcp', 'udp', 'http', 'multicast');
CREATE TYPE auth_type AS ENUM ('basic', 'digest', 'onvif_token');
CREATE TYPE camera_status AS ENUM ('online', 'offline', 'degraded', 'unknown');
CREATE TYPE scan_status AS ENUM ('running', 'completed', 'failed', 'cancelled');
CREATE TYPE discovery_phase AS ENUM ('onvif', 'arp', 'rtsp', 'http', 'vendor', 'mdns', 'merge');
```

### 2.3 Үндсэн хүснэгтүүд

#### system_config — Системийн глобал тохиргоо

```sql
CREATE TABLE system_config (
    key         VARCHAR(255) PRIMARY KEY,
    value       JSONB NOT NULL DEFAULT '{}',
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE system_config IS
'Бүх системийн runtime тохиргоо. Файлд hardcode юм байхгүй.';
```

#### users — Хэрэглэгч & RBAC

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(64) NOT NULL UNIQUE,
    email           VARCHAR(255),
    hashed_password VARCHAR(255) NOT NULL,
    role            user_role NOT NULL DEFAULT 'viewer',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);
```

#### cameras — Камерын бүртгэл

```sql
CREATE TABLE cameras (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name             VARCHAR(255) NOT NULL,
    ip_address       INET NOT NULL,
    mac_address      MACADDR,
    manufacturer     VARCHAR(100),
    model            VARCHAR(255),
    firmware_version VARCHAR(50),
    serial_number    VARCHAR(100),

    -- RTSP stream URLs (хэд хэдэн профайл)
    stream_main_uri  VARCHAR(1024),
    stream_sub_uri   VARCHAR(1024),
    stream_audio_uri VARCHAR(1024),

    -- Authentication
    auth_type           auth_type NOT NULL DEFAULT 'basic',
    username            VARCHAR(100) NOT NULL DEFAULT 'admin',
    encrypted_password  TEXT,                    -- AES-256-GCM encrypted

    -- Capabilities (auto-detected)
    has_audio             BOOLEAN NOT NULL DEFAULT FALSE,
    has_talkback          BOOLEAN NOT NULL DEFAULT FALSE,
    has_ptz               BOOLEAN NOT NULL DEFAULT FALSE,
    has_onvif             BOOLEAN NOT NULL DEFAULT FALSE,
    has_motion_detection  BOOLEAN NOT NULL DEFAULT FALSE,
    has_io_ports          BOOLEAN NOT NULL DEFAULT FALSE,
    onvif_motion_supported BOOLEAN NOT NULL DEFAULT FALSE,
    motion_source         VARCHAR(20) DEFAULT 'server',  -- 'onvif', 'server', 'both'
    max_resolution        VARCHAR(20),           -- "3840x2160"

    -- ONVIF service URLs
    onvif_device_service_url  VARCHAR(1024),
    onvif_media_service_url   VARCHAR(1024),
    onvif_ptz_service_url     VARCHAR(1024),
    onvif_events_service_url  VARCHAR(1024),

    -- Stream configuration
    recording_mode    recording_mode NOT NULL DEFAULT 'continuous',
    stream_transport  stream_transport NOT NULL DEFAULT 'tcp',
    pre_record_seconds   SMALLINT NOT NULL DEFAULT 5,
    post_record_seconds  SMALLINT NOT NULL DEFAULT 10,

    -- Network binding (multi-NIC, DHCP resilience)
    preferred_ip      INET,
    ip_binding        VARCHAR(20) DEFAULT 'dynamic',  -- 'dynamic','static','dhcp_reserved'
    network_interface VARCHAR(50),                     -- Docker network name

    -- Privacy (GDPR)
    privacy_mode      VARCHAR(20) DEFAULT 'none',      -- 'none','mask_zones','blur_faces'

    -- PTZ presets (JSON array of {name, pan, tilt, zoom})
    ptz_presets       JSONB DEFAULT '[]',

    -- Status
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    status               camera_status NOT NULL DEFAULT 'unknown',
    last_seen_at         TIMESTAMPTZ,
    last_discovery_at    TIMESTAMPTZ,
    time_synced_at       TIMESTAMPTZ,
    discovery_source     VARCHAR(50),
    discovery_confidence SMALLINT DEFAULT 0 CHECK (discovery_confidence BETWEEN 0 AND 100),

    -- Tags / notes
    tags      TEXT[],
    location  VARCHAR(255),
    notes     TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX idx_cameras_ip         ON cameras(ip_address);
CREATE INDEX idx_cameras_mac        ON cameras(mac_address);
CREATE INDEX idx_cameras_status     ON cameras(status);
CREATE INDEX idx_cameras_name       ON cameras(name);
CREATE INDEX idx_cameras_location   ON cameras USING GIN (location gin_trgm_ops);
CREATE INDEX idx_cameras_manufacturer ON cameras(manufacturer);
CREATE INDEX idx_cameras_recording   ON cameras(recording_mode) WHERE status = 'online';
```

#### stream_profiles — Камерын stream профайл

```sql
CREATE TABLE stream_profiles (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id    UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    profile_name VARCHAR(50) NOT NULL,           -- 'main', 'sub', 'third', 'audio_only'
    profile_type VARCHAR(20) NOT NULL DEFAULT 'video',  -- 'video','audio','data'
    codec        VARCHAR(20),                    -- 'h264','h265','mjpeg','aac','pcm'
    resolution   VARCHAR(20),                    -- '1920x1080'
    fps          SMALLINT,
    bitrate_kbps INTEGER,
    rtsp_uri     VARCHAR(1024),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(camera_id, profile_name)
);
CREATE INDEX idx_stream_profiles_camera ON stream_profiles(camera_id);
```

#### recording_schedules — Бичлэгийн хуваарь

```sql
CREATE TABLE recording_schedules (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id        UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    schedule_name    VARCHAR(100) NOT NULL,
    schedule_type    recording_mode NOT NULL,
    days_of_week     SMALLINT[] NOT NULL DEFAULT '{1,2,3,4,5,6,7}',  -- 1=Mon, 7=Sun
    time_start       TIME NOT NULL DEFAULT '00:00:00',
    time_end         TIME NOT NULL DEFAULT '23:59:59',
    pre_record_seconds  SMALLINT NOT NULL DEFAULT 5,
    post_record_seconds SMALLINT NOT NULL DEFAULT 10,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_schedules_camera ON recording_schedules(camera_id);
CREATE INDEX idx_schedules_active ON recording_schedules(is_active) WHERE is_active = TRUE;
```

#### discovery_scans — Discovery scan sessions

```sql
CREATE TABLE discovery_scans (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    status          scan_status NOT NULL DEFAULT 'running',
    subnets         INET[] NOT NULL,
    methods         TEXT[] NOT NULL DEFAULT '{onvif,rtsp,http,arp,mdns,vendor}',
    progress_pct    SMALLINT DEFAULT 0,
    phases          JSONB NOT NULL DEFAULT '{}',
    -- {"onvif":"complete","arp":"complete","rtsp":"running","http":"pending",...}
    found_count     INTEGER DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_discovery_scans_status ON discovery_scans(status);
```

#### storage_backends — Storage backend тохиргоо

```sql
CREATE TABLE storage_backends (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name           VARCHAR(100) NOT NULL UNIQUE,
    backend_type   storage_backend_type NOT NULL,
    config         JSONB NOT NULL DEFAULT '{}',
    -- local:  {"path":"/data/recordings"}
    -- nfs:    {"server":"192.168.1.100","path":"/volume1/nvr","mount_options":"nfsvers=4"}
    -- smb:    {"server":"192.168.1.101","share":"nvr","username":"user","password_encrypted":"..."}
    -- s3:     {"endpoint":"minio:9000","bucket":"nvr-recordings","access_key":"...","secret_key_enc":"...","secure":false}

    mount_point       VARCHAR(512),
    total_bytes       BIGINT NOT NULL DEFAULT 0,
    available_bytes   BIGINT NOT NULL DEFAULT 0,
    priority          SMALLINT NOT NULL DEFAULT 10,     -- lower = бүртгэл эхлээд энд бичигдэнэ
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    health_status     VARCHAR(20) NOT NULL DEFAULT 'unknown',
    last_health_check TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_storage_type   ON storage_backends(backend_type);
CREATE INDEX idx_storage_active ON storage_backends(is_active, priority);
```

#### recordings — Бичлэгийн мета-өгөгдөл (TimescaleDB hypertable)

```sql
CREATE TABLE recordings (
    id                  UUID NOT NULL DEFAULT uuid_generate_v4(),
    camera_id           UUID NOT NULL REFERENCES cameras(id),
    storage_backend_id  UUID REFERENCES storage_backends(id),
    file_path           VARCHAR(2048) NOT NULL,
    file_size_bytes     BIGINT NOT NULL DEFAULT 0,
    duration_seconds    REAL NOT NULL DEFAULT 0,
    start_time          TIMESTAMPTZ NOT NULL,
    end_time            TIMESTAMPTZ NOT NULL,
    recording_type      recording_type NOT NULL DEFAULT 'continuous',
    has_audio           BOOLEAN NOT NULL DEFAULT FALSE,
    resolution          VARCHAR(20),
    codec               VARCHAR(20),
    bitrate_kbps        INTEGER,
    event_id            UUID,
    retention_override_days INTEGER,
    checksum_sha256     VARCHAR(64),
    is_corrupt          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, start_time)
);
CREATE UNIQUE INDEX idx_recordings_id_unique ON recordings(id);

SELECT create_hypertable('recordings', 'start_time',
    chunk_time_interval => INTERVAL '1 day'
);

CREATE INDEX idx_recordings_camera_time ON recordings(camera_id, start_time DESC);
CREATE INDEX idx_recordings_type          ON recordings(recording_type, start_time DESC);
CREATE INDEX idx_recordings_event         ON recordings(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX idx_recordings_storage       ON recordings(storage_backend_id);
CREATE INDEX idx_recordings_created       ON recordings(created_at DESC);
```

#### events — Motion, detection, system event-үүд

```sql
CREATE TABLE events (
    id              UUID NOT NULL DEFAULT uuid_generate_v4(),
    camera_id       UUID NOT NULL REFERENCES cameras(id),
    event_type      VARCHAR(50) NOT NULL,
    -- motion_detected, object_detected, person_detected, face_detected, face_recognized,
    -- audio_detected, camera_offline, camera_online, recording_error,
    -- storage_full, storage_error, system_startup, system_shutdown

    severity        event_severity NOT NULL DEFAULT 'info',
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}',
    -- {
    --   "bounding_boxes": [{"label":"person","confidence":0.92,"x":100,"y":200,"w":80,"h":180}],
    --   "zone_id": "entrance", "snapshot_path": "s3://...", "face_id": "..."
    -- }

    snapshot_path   VARCHAR(2048),
    is_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_by UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, created_at)
);
CREATE UNIQUE INDEX idx_events_id_unique ON events(id);

SELECT create_hypertable('events', 'created_at',
    chunk_time_interval => INTERVAL '1 day'
);

CREATE INDEX idx_events_camera_time ON events(camera_id, created_at DESC);
CREATE INDEX idx_events_type         ON events(event_type, created_at DESC);
CREATE INDEX idx_events_severity     ON events(severity, created_at DESC);
CREATE INDEX idx_events_start_time   ON events(start_time DESC);
```

#### event_rules — Хөдөлгөөн/detection дүрэм

```sql
CREATE TABLE event_rules (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id        UUID REFERENCES cameras(id) ON DELETE CASCADE,  -- NULL = global
    rule_name        VARCHAR(100) NOT NULL,
    description      TEXT,
    event_type       VARCHAR(50) NOT NULL,           -- 'motion_detected', 'object_detected', ...
    conditions       JSONB NOT NULL DEFAULT '{}',
    -- {
    --   "min_confidence": 0.7,
    --   "object_classes": ["person","car"],
    --   "zones": [{"name":"entrance","points":[[0,0],[100,0],[100,100],[0,100]]}],
    --   "schedule": {"days":[1,2,3,4,5],"start":"08:00","end":"20:00"}
    -- }

    actions          JSONB NOT NULL DEFAULT '{}',
    -- {"record": true, "notify": ["email","webhook"], "snapshot": true, "trigger_alarm": false}

    cooldown_seconds INTEGER NOT NULL DEFAULT 60,
    audio_config     JSONB DEFAULT '{"min_db":80,"duration_seconds":3}',
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_event_rules_camera ON event_rules(camera_id);
CREATE INDEX idx_event_rules_active ON event_rules(is_active) WHERE is_active = TRUE;
```

#### storage_tiers — Tiered хадгалалтын бодлого

```sql
CREATE TABLE storage_tiers (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                  VARCHAR(50) NOT NULL UNIQUE,
    backend_id            UUID NOT NULL REFERENCES storage_backends(id),
    priority_level        SMALLINT NOT NULL,             -- 1=hot, 2=warm, 3=cold
    retention_days        INTEGER NOT NULL,
    applies_to_types      recording_type[] NOT NULL DEFAULT '{continuous}',
    min_free_bytes        BIGINT NOT NULL DEFAULT 10737418240,  -- 10GB
    max_used_percent      SMALLINT NOT NULL DEFAULT 90,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(backend_id, priority_level)
);
```

#### storage_migrations — Tier migrations tracking

```sql
CREATE TABLE storage_migrations (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recording_id     UUID NOT NULL REFERENCES recordings(id),
    from_backend_id  UUID NOT NULL REFERENCES storage_backends(id),
    to_backend_id    UUID NOT NULL REFERENCES storage_backends(id),
    status           VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending,copying,verifying,complete,failed
    source_path      VARCHAR(2048) NOT NULL,
    dest_path        VARCHAR(2048) NOT NULL,
    checksum_source  VARCHAR(64),
    checksum_dest    VARCHAR(64),
    error_message    TEXT,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_storage_migrations_status ON storage_migrations(status);
CREATE INDEX idx_storage_migrations_recording ON storage_migrations(recording_id);
CREATE INDEX idx_storage_migrations_from ON storage_migrations(from_backend_id);
CREATE INDEX idx_storage_migrations_to ON storage_migrations(to_backend_id);
```

#### discovery_log — Discovery лог

```sql
CREATE TABLE discovery_log (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id              UUID NOT NULL REFERENCES discovery_scans(id),
    ip_address           INET NOT NULL,
    mac_address          MACADDR,
    discovery_method     VARCHAR(50) NOT NULL,
    result_status        VARCHAR(20) NOT NULL,
    manufacturer_detected VARCHAR(100),
    raw_response         JSONB,
    confidence           SMALLINT DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_discovery_log_scan ON discovery_log(scan_id);
```

#### notifications — Notification сувгууд

```sql
CREATE TABLE notifications (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          VARCHAR(100) NOT NULL,
    channel_type  VARCHAR(20) NOT NULL CHECK (channel_type IN ('email','webhook','push')),
    config        JSONB NOT NULL DEFAULT '{}',
    -- email: {"smtp_host":"","smtp_port":587,"username":"","password_enc":"","to":[""]}
    -- webhook: {"url":"","method":"POST","headers":{"Authorization":"Bearer ..."}}
    -- push: {"fcm_key":"...","topics":["alerts"]}

    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### notification_templates — Notification хэв маяг

```sql
CREATE TABLE notification_templates (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    event_type    VARCHAR(50) NOT NULL,              -- '*', 'motion_detected', ...
    subject_tpl   VARCHAR(500) NOT NULL DEFAULT 'NVR Alert: {{event_type}}',
    body_tpl      TEXT NOT NULL DEFAULT 'Event: {{event_type}} at {{camera_name}} ({{timestamp}})',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### alert_log — Notification илгээлтийн бүртгэл

```sql
CREATE TABLE alert_log (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id         UUID NOT NULL REFERENCES events(id),
    notification_id  UUID NOT NULL REFERENCES notifications(id),
    sent_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivery_status  VARCHAR(20) NOT NULL DEFAULT 'sent',   -- sent, failed, retrying
    error_message    TEXT,
    retry_count      SMALLINT NOT NULL DEFAULT 0
);
CREATE INDEX idx_alert_log_event ON alert_log(event_id);
CREATE INDEX idx_alert_log_notification ON alert_log(notification_id);
```

#### api_keys — External API integration keys

```sql
CREATE TABLE api_keys (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         VARCHAR(100) NOT NULL,               -- "Home Assistant", "Mobile App"
    key_hash     VARCHAR(255) NOT NULL,                -- bcrypt hash
    key_prefix   VARCHAR(12) NOT NULL,                 -- First 8 chars for UI: "nvr_a3f2..."
    permissions  TEXT[] NOT NULL DEFAULT '{read}',
    expires_at   TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE UNIQUE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
```

#### audit_log — Audit trail

```sql
CREATE TABLE audit_log (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID REFERENCES users(id),
    action        VARCHAR(100) NOT NULL,               -- 'camera.created', 'recording.deleted', ...
    resource_type VARCHAR(50) NOT NULL,
    resource_id   UUID,
    details       JSONB,
    ip_address    INET,
    user_agent    VARCHAR(500),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('audit_log', 'created_at',
    chunk_time_interval => INTERVAL '1 day'
);

CREATE INDEX idx_audit_user   ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);
```

---

## 3. API Бүрэн Спецификаци

### 3.1 Common Patterns

**Response Wrapper:**
```json
{
  "data": { ... },
  "metadata": { "page": 1, "per_page": 25, "total": 142 }
}
```

**Error Response:**
```json
{
  "data": null,
  "error": {
    "code": "CAMERA_NOT_FOUND",
    "message": "Camera with id 550e8400-... not found",
    "trace_id": "a1b2c3d4-e5f6-..."
  }
}
```

**Pagination:** `?page=1&per_page=25` (max 100)
**Sorting:** `?sort=name&order=asc`
**Filtering:** `?manufacturer=hikvision&status=online&search=front`
**Date range:** `?from=2026-07-01T00:00:00Z&to=2026-07-21T23:59:59Z`

**HTTP Status Codes:**
| Code | Meaning |
|------|---------|
| 200  | Success  |
| 201  | Created  |
| 204  | No Content (delete) |
| 206  | Partial Content (range-based streaming) |
| 400  | Validation Error |
| 401  | Unauthorized / Token expired |
| 403  | Forbidden (RBAC) |
| 404  | Not Found |
| 409  | Conflict (duplicate name/IP) |
| 422  | Unprocessable Entity |
| 429  | Rate Limit Exceeded |
| 500  | Internal Server Error |
| 503  | Service Unavailable (DB down, etc.) |

**Error Codes:**
| Code | Meaning |
|------|---------|
| `CAMERA_NOT_FOUND` | Camera ID not found |
| `RECORDING_NOT_FOUND` | Recording ID not found |
| `EVENT_NOT_FOUND` | Event ID not found |
| `USER_NOT_FOUND` | User ID not found |
| `STORAGE_BACKEND_NOT_FOUND` | Storage backend ID not found |
| `SCAN_NOT_FOUND` | Discovery scan ID not found |
| `INVALID_CREDENTIALS` | Wrong username/password |
| `TOKEN_EXPIRED` | JWT access token expired |
| `TOKEN_REVOKED` | Token has been revoked |
| `RATE_LIMIT_EXCEEDED` | Too many requests |
| `DUPLICATE_IP` | Camera with this IP already exists |
| `DUPLICATE_NAME` | Name already used |
| `CAMERA_OFFLINE` | Camera is not reachable |
| `CAMERA_UNREACHABLE` | Cannot connect to camera |
| `STREAM_ERROR` | Failed to get stream from camera |
| `EXPORT_FAILED` | Recording export failed |
| `DISCOVERY_IN_PROGRESS` | Another scan is running |
| `DISCOVERY_FAILED` | Discovery scan failed |
| `STORAGE_FULL` | Storage has no free space |
| `MIGRATION_FAILED` | Storage migration failed |
| `FORBIDDEN` | Insufficient RBAC permissions |

### 3.2 Authentication

#### POST /api/v1/auth/login

```json
// Request
{
  "username": "admin",
  "password": "secure_password"
}

// Response 200
{
  "data": {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "id": "uuid",
      "username": "admin",
      "role": "admin",
      "email": "admin@example.com"
    }
  }
}
```

#### POST /api/v1/auth/refresh

```json
// Request
{ "refresh_token": "eyJhbGciOi..." }

// Response 200
{
  "data": {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "eyJhbGciOi...",
    "expires_in": 86400
  }
}
```

#### POST /api/v1/auth/logout

```json
// Request
{ "refresh_token": "eyJhbGciOi..." }

// Response 204 (no content)
```

#### POST /api/v1/auth/api-keys

```json
// Request (admin only)
{ "name": "Home Assistant", "permissions": ["read", "write"] }

// Response 201
{
  "data": {
    "id": "uuid",
    "name": "Home Assistant",
    "key": "nvr_a3f2c1b8d9e0f1a2b3c4d5e6f7a8b9c0",   // ЗӨВХӨН энэ удаа!
    "key_prefix": "nvr_a3f2",
    "permissions": ["read", "write"],
    "expires_at": null,
    "created_at": "2026-07-21T..."
  }
}
```

### 3.3 Cameras API

#### GET /api/v1/cameras

```
Query params: ?page=1&per_page=25&sort=name&order=asc
              &manufacturer=hikvision&status=online&search=front_door
              &has_ptz=true&has_audio=true
```

```json
// Response 200
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Front Door Cam",
      "ip_address": "192.168.1.100",
      "mac_address": "C4:2F:90:AB:CD:EF",
      "manufacturer": "hikvision",
      "model": "DS-2CD2143G2-I",
      "firmware_version": "V5.7.15",
      "serial_number": "DS-2CD2143G2-I20240615AAWR...",
      "stream_main_uri": "rtsp://192.168.1.100:554/Streaming/Channels/101",
      "stream_sub_uri": "rtsp://192.168.1.100:554/Streaming/Channels/102",
      "stream_audio_uri": null,
      "auth_type": "basic",
      "username": "admin",
      "has_audio": true,
      "has_talkback": false,
      "has_ptz": false,
      "has_onvif": true,
      "has_motion_detection": true,
      "has_io_ports": true,
      "max_resolution": "2688x1520",
      "recording_mode": "continuous",
      "stream_transport": "tcp",
      "ptz_presets": [],
      "status": "online",
      "last_seen_at": "2026-07-21T14:30:00Z",
      "tags": ["outdoor", "entrance"],
      "location": "Main Building, East Entrance",
      "created_at": "2026-06-01T08:00:00Z",
      "updated_at": "2026-07-20T12:00:00Z"
    }
  ],
  "metadata": { "page": 1, "per_page": 25, "total": 8 }
}
```

#### POST /api/v1/cameras

```json
// Request
{
  "name": "New Camera",
  "ip_address": "192.168.1.200",
  "username": "admin",
  "password": "camera_password",
  "auth_type": "basic",
  "stream_main_uri": "rtsp://192.168.1.200:554/Streaming/Channels/101",
  "recording_mode": "continuous",
  "stream_transport": "tcp",
  "tags": ["indoor", "office"],
  "location": "3rd Floor"
}

// Response 201: { "data": { ... full camera object } }
```

#### GET /api/v1/cameras/{id}

```json
// Response 200: { "data": { ... full camera object with stream_profiles[] } }
// Response 404: { "error": { "code": "CAMERA_NOT_FOUND", "message": "..." } }
```

#### PATCH /api/v1/cameras/{id}

```json
// Request (хэсэгчилсэн шинэчлэл)
{
  "name": "Renamed Camera",
  "recording_mode": "motion",
  "password": "new_password",
  "tags": ["indoor", "conference_room"]
}
```

#### DELETE /api/v1/cameras/{id}

```json
// Query: ?keep_recordings=true|false  (default: false)
// Response 204
```

#### POST /api/v1/cameras/discover

```json
// Request
{
  "subnets": ["192.168.1.0/24", "192.168.2.0/24"],
  "methods": ["onvif", "rtsp", "http", "arp", "mdns", "vendor"],
  "timeout": 120
}

// Response 202
{
  "data": {
    "scan_id": "uuid",
    "status": "running",
    "estimated_completion_s": 90
  }
}
```

#### GET /api/v1/cameras/discover/{scan_id}/status

```json
// Response 200
{
  "data": {
    "scan_id": "uuid",
    "status": "running",       // running | completed | failed
    "phases": {
      "onvif": "complete", "arp": "complete", "rtsp": "running",
      "http": "pending", "mdns": "pending", "vendor": "pending"
    },
    "found_count": 5,
    "progress_pct": 45
  }
}
```

#### GET /api/v1/cameras/discover/{scan_id}/results

```json
// Response 200 (сүүлийн 2 scan-ы result хадгалагдана)
{
  "data": {
    "scan_id": "uuid",
    "devices": [
      {
        "id": "temp-uuid",
        "primary_ip": "192.168.1.100",
        "vendor": "hikvision",
        "manufacturer": "Hikvision",
        "model": "DS-2CD2143G2-I",
        "overall_confidence": 98,
        "stream_main_uri": "rtsp://192.168.1.100:554/Streaming/Channels/101",
        "has_audio": true, "has_ptz": false, "has_onvif": true,
        "default_username": "admin",
        "discovery_methods": ["onvif", "rtsp", "arp"]
      }
    ],
    "total": 5
  }
}
```

#### POST /api/v1/cameras/{id}/test

```json
// Response 200
{
  "data": {
    "reachable": true,
    "rtsp_ok": true,
    "latency_ms": 12,
    "stream_resolution": "2688x1520",
    "stream_codec": "h264"
  }
}
```

#### POST /api/v1/cameras/{id}/ptz

```json
// Request
{
  "action": "move",        // move | stop | preset | goto_preset | zoom
  "direction": "left",     // left | right | up | down (move үед)
  "speed": 0.5,            // 0.0 - 1.0 (move үед)
  "preset_id": 1,          // goto_preset үед
  "zoom": "in"             // in | out (zoom үед)
}

// Response 200: { "data": { "ok": true } }
```

#### POST /api/v1/cameras/{id}/talk

```json
// Request (multipart/form-data) или WebSocket stream
// WebSocket: ws://host/api/v1/cameras/{id}/talk

// Response 200: { "data": { "session_id": "uuid", "status": "active" } }
```

#### POST /api/v1/cameras/{id}/snapshot

```json
// Response 200 (image/jpeg binary) or
{
  "data": {
    "snapshot_url": "https://nvr.mbm.mn/api/v1/files/snapshots/{id}.jpg",
    "taken_at": "2026-07-21T14:30:00Z",
    "resolution": "2688x1520"
  }
}
```

#### GET /api/v1/cameras/{id}/live

```
WebSocket: ws://host/api/v1/cameras/{id}/live
Protocol: JSON signaling + WebRTC

Client → Server: { "type": "offer", "sdp": "v=0\r\no=..." }
Server → Client: { "type": "answer", "sdp": "v=0\r\no=..." }

// ICE candidates
Client → Server: { "type": "ice", "candidate": "candidate:..." }
Server → Client: { "type": "ice", "candidate": "candidate:..." }

// HLS mode fallback
Client → Server: { "type": "hls" }
Server → Client: { "type": "hls_url", "url": "/api/v1/streams/{id}/live.m3u8" }

// Status updates
Server → Client: { "type": "status", "online": true, "recording": true, "resolution": "2688x1520", "fps": 25 }

// Errors
Server → Client: { "type": "error", "code": "STREAM_UNAVAILABLE", "message": "Camera is offline" }
Server → Client: { "type": "error", "code": "AUTH_REQUIRED", "message": "Invalid or expired token" }
```

### 3.4 Recordings API

#### GET /api/v1/recordings

```
Query: ?page=1&per_page=25&camera_id=uuid
       &from=2026-07-20T00:00:00Z&to=2026-07-21T23:59:59Z
       &type=continuous,motion,event
       &sort=start_time&order=desc
```

```json
// Response 200
{
  "data": [
    {
      "id": "uuid",
      "camera_id": "uuid",
      "camera_name": "Front Door Cam",
      "file_path": "s3://nvr-recordings/2026/07/21/front_door_20260721_143000.mp4",
      "file_size_bytes": 157286400,
      "duration_seconds": 900.5,
      "start_time": "2026-07-21T14:30:00Z",
      "end_time": "2026-07-21T14:45:00Z",
      "recording_type": "continuous",
      "has_audio": true,
      "resolution": "2688x1520",
      "codec": "h264",
      "bitrate_kbps": 1400,
      "is_corrupt": false,
      "event_id": null,
      "created_at": "2026-07-21T14:45:05Z"
    }
  ],
  "metadata": { "page": 1, "per_page": 25, "total": 96 }
}
```

#### GET /api/v1/recordings/{id}

```json
// Response 200: { "data": { ... single recording object } }
// Response 404: { "error": { "code": "RECORDING_NOT_FOUND" } }
```

#### GET /api/v1/recordings/{id}/stream

```
HTTP Range-based streaming (Accept-Ranges: bytes)
Онлайн playback: GET /api/v1/recordings/{id}/stream
                 Header: Range: bytes=0-1048575
HLS fallback:    GET /api/v1/recordings/{id}/stream?format=hls
                 → { "data": { "hls_url": "/api/v1/streams/recording/{id}.m3u8" } }

Response 206 (Partial Content):
Content-Type: video/mp4
Content-Range: bytes 0-1048575/157286400
Accept-Ranges: bytes
```

#### DELETE /api/v1/recordings/{id}

```json
// Response 204
```

#### POST /api/v1/recordings/export

```json
// Request
{
  "camera_id": "uuid",
  "from": "2026-07-21T14:30:00Z",
  "to": "2026-07-21T14:45:00Z",
  "format": "mp4",
  "include_audio": true
}

// Response 202
{
  "data": {
    "export_id": "uuid",
    "status": "processing",
    "estimated_size_bytes": 52428800
  }
}

// GET /api/v1/recordings/export/{export_id}/status
// Response 200: { "data": { "status": "complete", "download_url": "..." } }
```

#### GET /api/v1/recordings/timeline

```json
// Query: ?camera_id=uuid&date=2026-07-21
// Response 200
{
  "data": {
    "camera_id": "uuid",
    "date": "2026-07-21",
    "segments": [
      {
        "start_time": "2026-07-21T00:00:00Z",
        "end_time": "2026-07-21T06:30:00Z",
        "type": "continuous",
        "color": "#4CAF50"
      },
      {
        "start_time": "2026-07-21T07:15:00Z",
        "end_time": "2026-07-21T07:16:30Z",
        "type": "motion",
        "color": "#FF9800",
        "event_id": "uuid",
        "event_type": "person_detected"
      }
    ]
  }
}
```

### 3.5 Events API

#### GET /api/v1/events

```
Query: ?page=1&per_page=25&camera_id=uuid
       &event_type=motion_detected,object_detected
       &severity=warning,critical
       &from=2026-07-20T00:00:00Z&to=2026-07-21T23:59:59Z
       &acknowledged=false
       &sort=created_at&order=desc
```

```json
// Response 200
{
  "data": [
    {
      "id": "uuid",
      "camera_id": "uuid",
      "camera_name": "Front Door Cam",
      "event_type": "object_detected",
      "severity": "warning",
      "start_time": "2026-07-21T14:31:05Z",
      "end_time": "2026-07-21T14:31:12Z",
      "metadata": {
        "objects": [
          {"label": "person", "confidence": 0.94, "box": [320, 180, 400, 520]},
          {"label": "car", "confidence": 0.88, "box": [100, 200, 500, 400]}
        ],
        "snapshot_path": "s3://nvr-recordings/snapshots/2026/07/21/...jpg"
      },
      "snapshot_url": "/api/v1/files/snapshots/...jpg",
      "is_acknowledged": false,
      "created_at": "2026-07-21T14:31:05Z"
    }
  ],
  "metadata": { "page": 1, "per_page": 50, "total": 230 }
}
```

#### GET /api/v1/events/{id}

```json
// Response 200: { "data": { ... single event with full metadata } }
```

#### PATCH /api/v1/events/{id}/acknowledge

```json
// Response 200: { "data": { "id": "uuid", "is_acknowledged": true } }
```

#### WS /api/v1/events/stream

```
WebSocket: ws://host/api/v1/events/stream
Query: ?camera_id=uuid&event_types=motion_detected,object_detected&min_severity=warning

Server → Client messages:
{
  "type": "event.new",
  "data": { ... event object }
}
{
  "type": "event.updated",    // (acknowledged, severity changed)
  "data": { ... event object }
}
{
  "type": "camera.status",
  "data": { "camera_id": "uuid", "status": "online" }
}
{
  "type": "storage.alert",
  "data": { "backend_id": "uuid", "free_pct": 4.2, "severity": "critical" }
}
```

### 3.6 Storage API

#### GET /api/v1/storage/backends

```json
// Response 200
{
  "data": [
    {
      "id": "uuid",
      "name": "local_primary",
      "backend_type": "local",
      "total_bytes": 1000000000000,
      "available_bytes": 350000000000,
      "used_pct": 65.0,
      "priority": 1,
      "is_active": true,
      "health_status": "healthy",
      "last_health_check": "2026-07-21T14:30:00Z"
    }
  ]
}
```

#### POST /api/v1/storage/backends

```json
// Request
{
  "name": "nas_archive",
  "backend_type": "nfs",
  "config": {
    "server": "192.168.1.100",
    "path": "/volume1/nvr",
    "mount_options": "nfsvers=4,rsize=1048576"
  },
  "priority": 2
}

// Response 201: { "data": { ... backend object } }
```

#### GET /api/v1/storage/backends/{id}

```json
// Response 200: { "data": { ... full backend object with config } }
```

#### PATCH /api/v1/storage/backends/{id}

```json
// Request (хэсэгчилсэн)
{ "is_active": false, "priority": 3 }
```

#### DELETE /api/v1/storage/backends/{id}

```json
// Query: ?migrate_to=uuid   (бичлэгүүдийг өөр backend руу зөөх)
// Response 202: { "data": { "migration_id": "uuid", "status": "started" } }
```

#### GET /api/v1/storage/backends/{id}/health

```json
// Response 200
{
  "data": {
    "backend_id": "uuid",
    "status": "healthy",
    "latency_ms": 5,
    "free_bytes": 350000000000,
    "io_error_count_24h": 0,
    "checked_at": "2026-07-21T14:30:00Z"
  }
}
```

#### GET /api/v1/storage/usage

```json
// Response 200
{
  "data": {
    "total_bytes": 3000000000000,
    "used_bytes": 1800000000000,
    "free_bytes": 1200000000000,
    "used_pct": 60.0,
    "recording_hours_available": 720,
    "earliest_recording": "2026-06-21T00:00:00Z",
    "latest_recording": "2026-07-21T14:45:00Z",
    "breakdown": {
      "continuous_bytes": 1200000000000,
      "motion_bytes": 400000000000,
      "event_bytes": 200000000000
    },
    "per_backend": [
      { "backend_id": "uuid", "name": "local_primary", "used_pct": 85.0, "status": "warning" },
      { "backend_id": "uuid", "name": "nas_archive", "used_pct": 40.0, "status": "healthy" }
    ]
  }
}
```

#### GET /api/v1/storage/tiers && POST /api/v1/storage/tiers

```json
// GET Response 200
{
  "data": [
    {
      "id": "uuid", "name": "hot", "backend_name": "local_primary",
      "priority_level": 1, "retention_days": 7,
      "applies_to_types": ["continuous", "motion", "event"],
      "is_active": true
    },
    {
      "id": "uuid", "name": "warm", "backend_name": "nas_archive",
      "priority_level": 2, "retention_days": 30,
      "applies_to_types": ["continuous", "motion"],
      "is_active": true
    },
    {
      "id": "uuid", "name": "cold", "backend_name": "s3_minio",
      "priority_level": 3, "retention_days": 365,
      "applies_to_types": ["continuous"],
      "is_active": true
    }
  ]
}

// POST Request
{
  "name": "archive_deep",
  "backend_id": "uuid",
  "priority_level": 4,
  "retention_days": 730,
  "applies_to_types": ["continuous"]
}
```

### 3.7 Users API (Admin only)

```
GET    /api/v1/users                      # Хэрэглэгчдийн жагсаалт
POST   /api/v1/users                      # Хэрэглэгч үүсгэх
       { "username": "operator1", "password": "...", "role": "operator", "email": "..." }
GET    /api/v1/users/{id}
PATCH  /api/v1/users/{id}                 # role, is_active, password өөрчлөх
DELETE /api/v1/users/{id}
```

### 3.8 System API

#### GET /api/v1/system/health

```json
// Response 200
{
  "data": {
    "status": "healthy",       // healthy | degraded | down
    "uptime_seconds": 864000,
    "version": "0.1.0",
    "checks": {
      "database": "ok",
      "redis": "ok",
      "minio": "ok",
      "ffmpeg": "ok (version 7.0)"
    },
    "cameras": { "total": 8, "online": 7, "offline": 1 },
    "storage": { "total_pct": 60, "status": "ok" },
    "recording": { "active_recordings": 8, "errors_24h": 0 }
  }
}
```

#### GET /api/v1/system/metrics

```
Prometheus /metrics endpoint (requires API key with 'read' scope or admin JWT)
Scrape config: Authorization: Bearer <api-key>
Metrics: camera_count, recording_count, ffmpeg_processes,
         storage_bytes_total/used/free, event_count_24h,
         api_request_count/duration, ai_inference_duration
```

#### GET /api/v1/system/config

```json
// Response 200 (admin only, бүх system_config key-value)
{
  "data": {
    "system.name": "mBm NVR System",
    "system.timezone": "Asia/Ulaanbaatar",
    "recording.default_mode": "continuous",
    "storage.default_retention_days": 30
  }
}
```

#### PATCH /api/v1/system/config

```json
// Request
{ "key": "recording.default_mode", "value": "motion" }
```

#### GET /api/v1/system/logs

```
Query: ?page=1&per_page=50&level=error,warning
       &component=stream-manager,recording-engine
       &from=2026-07-21T00:00:00Z&to=2026-07-21T23:59:59Z
       &search=connection_timeout

// Response 200: { "data": [ { "timestamp":"...", "level":"error", "component":"...", "message":"...", "trace_id":"..." } ], "metadata": { ... } }
```

---

## 4. Stream / Live View Architecture

### 4.1 WebRTC Pipeline (primary, low-latency)

```
┌──────────┐    RTSP over TCP/UDP    ┌──────────────┐
│ IP Camera │────────────────────────→│ Stream Mgr   │
│ (H.264)   │                         │ (FFmpeg)     │
└──────────┘                         │              │
                                     │ RTP → fMP4   │
                                     │ segments     │
                                     └──────┬───────┘
                                            │ WebRTC peer
                                            │ (aiortc / mediamtx)
                                            ▼
┌──────────────┐    SDP Offer/Answer    ┌──────────────┐
│  Web Client  │←──── WebSocket ───────→│  API Gateway  │
│  (React)     │    ICE Candidates      │  (FastAPI)    │
└──────────────┘                        └──────────────┘
```

**Signaling Flow:**
1. Client opens WebSocket `ws://host/api/v1/cameras/{id}/live`
2. Server starts FFmpeg: `ffmpeg -rtsp_transport tcp -i rtsp://... -c copy -an -f rtsp rtsp://127.0.0.1:8554/{camera_id}`
3. MediaMTX (RTSP→WebRTC bridge) picks up stream
4. Server creates `RTCPeerConnection`, adds track, creates SDP offer
5. Server sends `{ "type": "offer", "sdp": "..." }` to client
6. Client sets remote description, creates answer
7. Client sends `{ "type": "answer", "sdp": "..." }` to server
8. ICE candidates exchanged bidirectionally
9. Video flows via WebRTC (UDP, <500ms latency)

**HLS Fallback (high latency, reliable):**
- If WebRTC fails (NAT/firewall), client requests `{ "type": "hls" }`
- Server returns HLS playlist URL
- Client uses `<video>` element with `hls.js`
- FFmpeg generates HLS: `ffmpeg -i rtsp://... -c copy -f hls -hls_time 2 -hls_list_size 5 /tmp/hls/{camera_id}.m3u8`

### 4.2 FFmpeg Pipeline per Camera

```bash
# Main stream: continuous recording + WebRTC source
ffmpeg \
  -rtsp_transport tcp \
  -i "rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/101" \
  -c:v copy -c:a aac -b:a 128k \
  -f segment -segment_format mp4 -segment_time 900 \
  -segment_wrap 999 -reset_timestamps 1 \
  -strftime 1 "/data/recordings/%Y/%m/%d/%H_%M_%S.mp4" \
  -c:v copy -an -f rtsp rtsp://127.0.0.1:8554/camera_{id}_main

# Sub stream: AI detection (lower resolution, 5 FPS)
# Frame delivery via Redis Streams (cross-container, NOT shell pipe)
ffmpeg \
  -rtsp_transport tcp \
  -i "rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/102" \
  -vf "fps=5,scale=640:480" -f image2pipe -vcodec bmp - \
  | redis-cli -x PUBLISH nvr:frames:camera_{id} "$(base64)"

# The AI Engine runs in a separate container and consumes from:
# nvr:frames:camera_{id} Redis channel
# Each frame is base64-encoded BMP binary pushed via Redis pub/sub
```

**Transport fallback order:**
```python
TRANSPORT_ORDER = ["tcp", "udp", "http"]
# Try TCP first (most cameras support it), then UDP, then HTTP tunnel
```

### 4.3 Multi-View Grid

```
Client-side: multiple WebSocket connections (1 per camera grid tile)
Max concurrent WebRTC: 4 (browser limit)
For 16-camera grid: WebRTC for 4 visible + snapshots for rest
Snapshot refresh: 1 FPS via HTTP GET /api/v1/cameras/{id}/snapshot
```

---

## 5. AI Engine Pipeline

### 5.1 Frame Processing Pipeline

```
RTSP Sub-stream (640x480, 5 FPS)
        │
        ▼
┌───────────────────┐
│  FFmpeg Decoder   │  rawvideo (BGR24) → stdout pipe
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Frame Queue      │  asyncio.Queue(maxsize=30)
│  (per camera)     │  overflow → drop oldest
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Preprocessing    │  Resize (640x640), normalize (0-1),
│  (OpenCV)         │  BGR→RGB, to tensor
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Batch Inference  │  Accumulate N frames → ONNX Runtime
│  (ONNX Runtime)   │  Run YOLOv8n → bounding boxes + classes
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Post-processing  │  NMS (IoU=0.45), confidence filter
│                   │  Face detection trigger → ArcFace recognition
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Event Emitter    │  Compare with event_rules
│                   │  Emit to Redis pub/sub channel "nvr:events"
└────────┬──────────┘
         │
    ┌────┴────┐
    ▼         ▼
 Recording  Notification
 Trigger    Service
```

### 5.2 Model Configuration

| Model           | ONNX File        | Input Size | Output                     | CPU (ms) | GPU (ms) |
|-----------------|------------------|------------|----------------------------|----------|----------|
| YOLOv8n         | yolov8n.onnx     | 640×640    | boxes (80 classes)         | 80-120   | 8-15     |
| YOLOv8s         | yolov8s.onnx     | 640×640    | boxes (80 classes)         | 180-250  | 15-25    |
| RetinaFace      | retinaface.onnx  | 640×640    | face boxes + landmarks     | 40-60    | 5-10     |
| ArcFace (R100)  | arcface.onnx     | 112×112    | 512-dim embedding          | 15-25    | 3-5      |
| YAMNet          | yamnet.onnx      | 15600 (0.975s audio) | audio classes     | 10-20    | 2-5      |

### 5.3 Inference Scheduling

```
Round-robin across cameras, 5 FPS each:
  Camera 1: frame 1 → inference (120ms) → wait 80ms
  Camera 2: frame 1 → inference (120ms) → wait 80ms
  ...
  Camera 8: frame 1 → inference (120ms) → wait 80ms

Max cameras on single CPU: ~1–2 (at 5 FPS, YOLOv8n 80-120ms/frame)
GPU available → batch 8+ cameras together → 30+ cameras
CPU with model quantization (INT8) → ~4 cameras
Note: Reduce to 1-2 FPS for motion detection-only → 8+ cameras on CPU
```

```python
# Latency-aware queue
class AIModelManager:
    def __init__(self, model_path: str, device: str = "cpu"):
        self.session = ort.InferenceSession(model_path, providers=[...])
        self.batch_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.results: dict[str, list[Detection]] = {}

    async def inference_loop(self):
        """Collect frames, batch, run ONNX, distribute results."""
        while True:
            batch = await self._collect_batch(timeout=0.05, max_batch=8)
            if not batch:
                continue
            inputs = self._preprocess_batch(batch)
            outputs = await asyncio.to_thread(self.session.run, None, inputs)
            self._distribute_results(batch, outputs)
```

### 5.4 Face Recognition Flow

```
1. YOLOv8 detects "person" class
2. If confidence > 0.7 → crop person ROI
3. RetinaFace detects face within person ROI
4. ArcFace extracts 512-dim embedding
5. Compare with known faces DB (cosine similarity > 0.5 → match)
6. Emit event: { "type": "face_recognized", "person_id": "...", "confidence": 0.89 }
```

### 5.5 Audio Detection

```
1. FFmpeg extracts audio: ffmpeg -i rtsp://... -ac 1 -ar 16000 -f s16le pipe:1
2. Buffer 975ms (15600 samples) → YAMNet inference
3. Detect: speech, dog_bark, glass_breaking, gunshot, siren, baby_cry
4. Emit event if confidence > 0.3
```

---

## 6. Security Design

### 6.1 RBAC Matrix

| Action                    | Admin | Operator | Viewer  |
|---------------------------|-------|----------|---------|
| View cameras              | ✅    | ✅       | ✅      |
| Add/edit/delete cameras   | ✅    | ✅¹      | ❌      |
| View live streams         | ✅    | ✅       | ✅      |
| PTZ control               | ✅    | ✅       | ❌      |
| Two-way talk              | ✅    | ✅       | ❌      |
| View recordings           | ✅    | ✅       | ✅      |
| Delete recordings         | ✅    | ❌       | ❌      |
| Export recordings         | ✅    | ✅       | ❌      |
| View events               | ✅    | ✅       | ✅      |
| Acknowledge events        | ✅    | ✅       | ❌      |
| Manage event rules        | ✅    | ✅       | ❌      |
| Manage storage            | ✅    | ❌       | ❌      |
| Manage users              | ✅    | ❌       | ❌      |
| System config             | ✅    | ❌       | ❌      |
| View system logs          | ✅    | ✅       | ❌      |
| Create API keys           | ✅    | ❌       | ❌      |
| System health/metrics     | ✅    | ✅       | ❌      |

¹ Operator камер устгах үед `keep_recordings=true` байх ёстой (default). `false` нь бичлэг устгах тул зөвхөн Admin хийх боломжтой.

### 6.2 JWT Token Structure

```json
{
  "sub": "user-uuid",
  "username": "admin",
  "role": "admin",
  "iat": 1689945600,
  "exp": 1690032000,
  "jti": "unique-token-id",
  "type": "access"    // "access" or "refresh"
}
```

**Token lifecycle:**
- Access token: 24 hours, stored in memory (React state)
- Refresh token: 7 days, stored in httpOnly cookie
- Auto-refresh: 5 min before expiry → silent refresh
- Revocation: Redis blacklist `nvr:token:blacklist:{jti}` with TTL

### 6.3 Camera Password Encryption

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os, base64

MASTER_KEY = os.environ["NVR_ENCRYPTION_KEY"]  # 32 bytes, base64

def encrypt_password(plaintext: str) -> str:
    nonce = os.urandom(12)
    cipher = AESGCM(base64.b64decode(MASTER_KEY))
    ct = cipher.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()

def decrypt_password(ciphertext: str) -> str:
    raw = base64.b64decode(ciphertext)
    nonce, ct = raw[:12], raw[12:]
    cipher = AESGCM(base64.b64decode(MASTER_KEY))
    return cipher.decrypt(nonce, ct, None).decode()
```

### 6.4 API Key Authentication

```python
# Header: X-API-Key: nvr_a3f2c1b8d9e0f1a2b3c4d5e6f7a8b9c0
# Verify: 
key_hash = bcrypt.hashpw(raw_key.encode(), stored_salt)
if key_hash == stored_hash:
    # Check permissions, expiry
```

### 6.5 Rate Limiting

```
/api/v1/auth/login:         5 req/min per IP     (brute force protection)
/api/v1/cameras/discover:   2 req/min per user    (network scan limit)
/api/v1/recordings/export:  10 req/min per user
Default:                    100 req/min per user
```

### 6.6 CORS & Headers

```python
# Production CORS
origins = ["https://nvr.mbm.mn", "https://admin.nvr.mbm.mn"]

# Security headers (via NGINX)
add_header X-Content-Type-Options nosniff;
add_header X-Frame-Options DENY;
add_header X-XSS-Protection "1; mode=block";
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; media-src 'self' blob:; connect-src 'self' ws: wss:;";
```

---

## 7. Recording Engine State Machine

### 7.1 FFmpeg Responsibility Division

**Чухал:** FFmpeg процессыг хоёр үйлчилгээ тусдаа удирдана:

| Үйлчилгээ | FFmpeg үүрэг |
|---|---|
| **nvr-stream-manager** | RTSP холболт тогтоох, WebRTC/HLS дамжуулалт, main→sub stream transcoding, snapshot авах. **Бичлэг хадгалахгүй.** |
| **nvr-recording-engine** | Stream Manager-аас stream хуулбарлах, segment файл үүсгэх, storage backend руу бичих, motion detection trigger, retention удирдах |

Recording Engine нь Stream Manager-аас WebRTC/HLS дамжуулж буй stream руу холбогдож бичлэг хийнэ
(stream duplication), эсвэл тусдаа RTSP холболт үүсгэж шууд бичнэ (per configuration).

### 7.2 Per-Camera States

```
                    ┌──────────┐
                    │  IDLE    │  Camera not being recorded
                    └────┬─────┘
                         │ start_recording()
                         ▼
              ┌─────────────────────┐
              │  WAITING_CONNECT    │  FFmpeg connecting to RTSP
              └────────┬────────────┘
                       │ RTSP OK / timeout (30s)
              ┌────────┴────────┐
              ▼                 ▼
    ┌─────────────────┐   ┌──────────────┐
    │   RECORDING     │   │   ERROR      │  Circuit breaker trip
    │ (continuous/    │   │ (retry       │
    │  motion/        │   │  backoff)    │
    │  scheduled)     │   └──────┬───────┘
    └────────┬────────┘          │
             │ stream lost       │ cooldown expired
             ▼                   ▼
    ┌─────────────────┐   ┌──────────────┐
    │  RECONNECTING   │◄──│   IDLE       │
    │  (exponential   │   └──────────────┘
    │   backoff)      │
    └────────┬────────┘
             │ reconnected
             ▼
    ┌─────────────────┐
    │   RECORDING     │
    └─────────────────┘
```

### 7.3 Continuous Recording

```python
class ContinuousRecorder:
    """FFmpeg -f segment based continuous recording."""

    async def start(self, camera: Camera) -> None:
        args = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", camera.stream_transport,
            "-i", camera.stream_main_uri,
            "-c:v", "copy",           # Passthrough video (no re-encode)
            "-c:a", "aac", "-b:a", "128k",
            "-f", "segment",
            "-segment_format", "mp4",
            "-segment_time", "900",    # 15-minute segments
            "-segment_atclocktime", "1",
            "-reset_timestamps", "1",
            "-strftime", "1",
            str(self.output_dir / "%Y/%m/%d/%Y%m%d_%H%M%S.mp4"),
        ]
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._monitor_task = asyncio.create_task(self._monitor_ffmpeg())

    async def _monitor_ffmpeg(self) -> None:
        """Monitor stderr for errors, check memory usage."""
        while self._running:
            line = await self.process.stderr.readline()
            if not line:
                break
            if b"Connection refused" in line or b"404 Not Found" in line:
                await self._handle_disconnect()
            if b"error" in line.lower():
                logger.error("ffmpeg_error", camera=self.camera_id, line=line.decode())
        # Process exited → reconnect
        if self._running:
            await self._handle_disconnect()
```

### 7.4 Motion-Triggered Recording

```python
class MotionRecorder:
    """Records only when motion is detected."""

    def __init__(self, pre_record_s: int = 5, post_record_s: int = 10):
        self.pre_record_s = pre_record_s
        self.post_record_s = post_record_s
        self.buffer: deque[bytes] = deque(maxlen=pre_record_s * 25)  # 25 FPS buffer
        self.is_recording = False
        self.motion_end_timer: asyncio.Task | None = None

    async def on_motion_event(self, camera_id: UUID):
        if not self.is_recording:
            self.is_recording = True
            await self._start_writing()
            await self._flush_buffer()  # Write pre-record buffer

        # Reset/start post-record timer
        if self.motion_end_timer:
            self.motion_end_timer.cancel()
        self.motion_end_timer = asyncio.create_task(self._delayed_stop())

    async def _delayed_stop(self):
        await asyncio.sleep(self.post_record_s)
        self.is_recording = False
        await self._finalize_segment()
```

### 7.5 Corrupt Segment Recovery

```python
async def recover_corrupt_segment(filepath: str) -> str | None:
    """Recover corrupted MP4 by copying valid data with ffmpeg."""
    recovered = filepath.replace(".mp4", "_recovered.mp4")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-err_detect", "ignore_err",
        "-i", filepath, "-c", "copy", recovered,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode == 0 and os.path.getsize(recovered) > 1024:
        return recovered
    return None
```

---

## 8. Storage Tiering Lifecycle

### 8.1 Tier Migration Flow

```
┌─────────┐  age>7d  ┌─────────┐  age>30d  ┌─────────┐
│  HOT    │──────────→│  WARM   │──────────→│  COLD   │
│ Local   │           │ NAS/NFS │           │ S3/MinIO│
│ SSD     │           │ HDD     │           │ Object  │
└─────────┘           └─────────┘           └─────────┘
  1-2 TB               10-50 TB              ∞ TB
```

### 8.2 Migration Procedure

```python
async def migrate_recording(recording_id: UUID, from_backend: StorageBackend, to_backend: StorageBackend):
    migration_id = await db.insert_migration(recording_id, "copying")

    # 1. Read from source using streaming (NOT full in-memory for large files)
    sha = hashlib.sha256()
    chunk_count = 0
    async for chunk in from_backend.read_stream(recording.file_path, chunk_size=1_048_576):
        sha.update(chunk)
        chunk_count += 1

    source_checksum = sha.hexdigest()
    if source_checksum != recording.checksum_sha256:
        await db.mark_corrupt(recording_id)
        return

    # 3. Write to destination (stream from source to dest in chunks)
    async for chunk in from_backend.read_stream(recording.file_path, chunk_size=1_048_576):
        await to_backend.write_chunk(recording.file_path, chunk)

    # 4. Verify destination
    dest_checksum = await to_backend.checksum(recording.file_path)
    if dest_checksum != source_checksum:
        await db.update_migration(migration_id, "failed", error="Destination checksum mismatch")
        await to_backend.delete(recording.file_path)
        return

    # 5. Delete source
    await from_backend.delete(recording.file_path)

    # 6. Update database
    await db.update_migration(migration_id, "complete")
    await db.update_recording_storage(recording_id, to_backend.id)
```

### 8.3 Disk Space Emergency Protocol

```python
EMERGENCY_THRESHOLD = 5  # percent free
CRITICAL_THRESHOLD = 3

async def emergency_cleanup(backend_id: UUID):
    free_pct = await db.get_backend_free_pct(backend_id)
    if free_pct >= EMERGENCY_THRESHOLD:
        return

    logger.critical("emergency_cleanup_started", backend_id=backend_id, free_pct=free_pct)

    # Step 1: Delete oldest continuous recordings (keep 24h minimum)
    await delete_recordings_by_type("continuous", keep_hours=24, backend_id=backend_id)

    # Step 2: Delete old snapshots (keep 7 days)
    await delete_files_by_pattern("snapshots/", keep_days=7, backend_id=backend_id)

    # Step 3: Still critical — move all continuous to next tier
    if await db.get_backend_free_pct(backend_id) < CRITICAL_THRESHOLD:
        await force_migrate_all_continuous(backend_id)

    # Step 4: Last resort — delete non-event recordings
    if await db.get_backend_free_pct(backend_id) < CRITICAL_THRESHOLD:
        await delete_all_non_event_recordings(backend_id)
```

---

## 9. Vendor-Specific Connection Analysis

### 9.1 Hikvision

```
Default IP:     192.168.1.64
Default creds:  admin / admin12345 (camera), admin / 12345 (NVR)
RTSP paths:     /Streaming/Channels/101 (main), /102 (sub), /201 (3rd)
Auth:           Basic Auth (RTSP), Digest (ONVIF), ISAPI (HTTP)
ONVIF port:     80 (same as HTTP)
API:            /ISAPI/System/deviceInfo, /ISAPI/PTZCtrl/channels/{id}
Audio:          Channel 1 only, AAC or G.711 μ-law
Talkback:       /ISAPI/System/TwoWayAudio/channels/1 (needs POST with audio data)
Quirks:
  - Some firmware versions require "admin:" (empty password) for RTSP even with ONVIF auth
  - PELCO-D over ONVIF PTZ sometimes off-by-1 degree
  - Motion detection events via ISAPI /Event/notification/alertStream (HTTP long-poll)
```

### 9.2 Dahua

```
Default IP:     192.168.1.108
Default creds:  admin / admin123
RTSP paths:     /cam/realmonitor?channel=1&subtype=0 (main), &subtype=1 (sub)
Auth:           Digest (preferred), Basic fallback
ONVIF port:     80
UDP discovery:  Port 37810 (magic packet)
API:            /cgi-bin/magicBox.cgi?action=getSystemInfo
Talkback:       /cgi-bin/audio.cgi?action=postAudioData (need HTTP session cookie)
Quirks:
  - RTSP requires Digest auth for most models; Basic auth returns 401
  - stream decoding needs extra parameter: ?proto=Onvif for ONVIF streams
  - Some models use H.265 exclusively on main stream (need transcoding)
```

### 9.3 Axis

```
Default IP:     DHCP (Bonjour: axis-<mac>.local)
Default creds:  root / pass
RTSP paths:     /axis-media/media.amp?videocodec=h264
Auth:           Basic (over HTTPS recommended)
ONVIF port:     80
mDNS service:   _axis-video._tcp.local.
API:            /axis-cgi/ (VAPIX API)
PTZ:            /axis-cgi/com/ptz.cgi?camera=1&move=left
Quirks:
  - Best ONVIF compat — Profile S, G, T all supported
  - Motion detection via ONVIF Rules engine
  - Two-way audio via /axis-cgi/audio/transmit.cgi
  - Requires HTTPS + self-signed cert (most deployments)
```

### 9.4 Reolink

```
Default IP:     DHCP
Default creds:  admin / (blank — set on first login)
RTSP paths:     /h264Preview_01_main, /h264Preview_01_sub
Auth:           Basic
ONVIF:          Profile S only (no PTZ via ONVIF for non-PTZ models)
API:            /cgi-bin/api.cgi?cmd=DevInfo
Quirks:
  - RTSP stream drops when ONVIF service is called (mutual exclusion bug)
  - H.265 main stream needs specific client support
  - Two-way talk only via proprietary app, not ONVIF
  - Firmware updates required for stable ONVIF
```

### 9.5 TP-Link / Tapo

```
Default IP:     DHCP
Default creds:  admin / admin (user-created via Tapo app first)
RTSP paths:     /stream1 (main), /stream2 (sub)
Auth:           Basic (username/password from Tapo app)
ONVIF:          Partial — Profile S, no PTZ via ONVIF
API:            /cgi-bin/getinfo
Quirks:
  - RTSP must be manually enabled via Tapo app first
  - Camera account ≠ Tapo cloud account (separate RTSP credentials)
  - No ONVIF discovery (must add manually if ONVIF doesn't respond)
```

### 9.6 Generic ONVIF

```
RTSP paths to try:
  /onvif1, /live, /media/video1, /media/video2,
  /profile1/media.smp, /stream, /Streaming/Channels/1,
  /ch01.264, /ch1/main, /video, /h264

ONVIF ports to try:
  80, 8080, 8000, 8899, 5000, 8554

Auth to try (in order):
  1. ONVIF token (WS-Security UsernameToken)
  2. HTTP Digest
  3. HTTP Basic
```

---

## 10. Frontend Architecture

### 10.1 Route Design

```
/                       → Redirect to /dashboard
/login                  → Login page
/dashboard              → Multi-camera grid (default 2×2)
/live/:cameraId         → Single camera fullscreen live view
/recordings             → Recording browser (filterable list)
/recordings/:id         → Recording playback
/timeline               → Multi-camera timeline view
/events                 → Event feed (filterable, real-time)
/cameras                → Camera management (CRUD table)
/cameras/:id            → Camera detail + live preview + settings
/storage                → Storage usage dashboard + backend management
/settings               → System settings (admin only)
/settings/users         → User management (admin only)
/settings/notifications → Notification channel config
```

### 10.2 Component Tree

```
App
├── AuthProvider
│   ├── LoginPage
│   └── AppShell
│       ├── Sidebar
│       │   ├── NavItems (Dashboard, Live, Recordings, etc.)
│       │   └── CameraStatusIndicator (online count)
│       ├── TopBar
│       │   ├── SearchBar
│       │   ├── NotificationBell (event count badge)
│       │   └── UserMenu (profile, logout)
│       └── MainContent
│           ├── DashboardPage
│           │   ├── CameraGrid
│           │   │   └── CameraTile (×N)
│           │   │       ├── LivePlayer (WebRTC/HLS)
│           │   │       ├── CameraLabel + StatusBadge
│           │   │       └── QuickActions (snapshot, PTZ overlay)
│           │   └── EventFeed (recent events sidebar)
│           ├── LiveViewPage
│           │   ├── FullscreenPlayer
│           │   ├── PTZControls (if has_ptz)
│           │   ├── TalkButton (if has_talkback)
│           │   └── RecordingIndicator
│           ├── RecordingsPage
│           │   ├── RecordingFilters (date, camera, type)
│           │   ├── RecordingList (DataTable)
│           │   └── ExportDialog
│           ├── RecordingPlayerPage
│           │   ├── VideoPlayer (hls.js)
│           │   ├── Timeline (seekable segments)
│           │   └── EventMarkers (on timeline)
│           ├── TimelinePage
│           │   ├── CameraSelector (multi-select)
│           │   ├── TimelineView (24h horizontal scroll)
│           │   └── EventOverlay
│           ├── EventsPage
│           │   ├── EventFilters
│           │   ├── EventCard (thumbnail, type, camera, time)
│           │   └── EventDetailDrawer
│           ├── CamerasPage
│           │   ├── CameraTable (sortable, filterable)
│           │   ├── CameraForm (add/edit dialog)
│           │   └── DiscoveryDialog (scan progress + results)
│           ├── CameraDetailPage
│           │   ├── LivePreview
│           │   ├── CameraInfoCard
│           │   ├── StreamConfig
│           │   ├── PTZPresetManager
│           │   └── EventRulesList
│           ├── StoragePage
│           │   ├── StorageOverview (pie chart: used/free)
│           │   ├── BackendList (health status)
│           │   └── TierConfig
│           └── SettingsPage
│               ├── SystemConfig
│               ├── UserManagement
│               └── NotificationConfig
```

### 10.3 State Management (Zustand Stores)

```typescript
// authStore.ts
interface AuthStore {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

// cameraStore.ts
interface CameraStore {
  cameras: Camera[];
  selectedIds: Set<string>;
  filters: CameraFilters;
  isLiveGrid: boolean;
  gridLayout: [number, number];  // [2,2] = 2×2
  fetchCameras: () => Promise<void>;
  selectCamera: (id: string) => void;
  setFilters: (f: Partial<CameraFilters>) => void;
  setGridLayout: (cols: number, rows: number) => void;
}

// eventStore.ts
interface EventStore {
  events: Event[];
  unacknowledgedCount: number;
  filters: EventFilters;
  realtimeConnected: boolean;
  connectRealtime: () => void;
  disconnectRealtime: () => void;
  acknowledgeEvent: (id: string) => Promise<void>;
}

// recordingStore.ts
interface RecordingStore {
  recordings: Recording[];
  filters: RecordingFilters;
  timelineData: TimelineSegment[] | null;
  fetchRecordings: () => Promise<void>;
  fetchTimeline: (cameraId: string, date: string) => Promise<void>;
  exportClip: (params: ExportParams) => Promise<string>;
}

// storageStore.ts
interface StorageStore {
  backends: StorageBackend[];
  usageSummary: StorageUsage | null;
  fetchBackends: () => Promise<void>;
  fetchUsage: () => Promise<void>;
}
```

### 10.4 Real-Time Update Flow

```
WebSocket: ws://host/api/v1/events/stream

On message:
  → eventStore.addEvent(data)        [update events list]
  → If camera offline: cameraStore.updateStatus(id, 'offline')
  → If motion_detected: trigger toast + play sound
  → If storage_full: show critical alert banner

Auto-refetch (TanStack Query):
  - Camera list: refetchOnWindowFocus, staleTime: 30s
  - Recording list: staleTime: 60s
  - Storage usage: refetchInterval: 60000 (1 min)
  - System health: refetchInterval: 30000 (30 sec)

Live stream status (per camera):
  - WebSocket: { type: "status", online: true, fps: 25, resolution: "..." }
  - Fallback: HTTP GET /api/v1/cameras/{id} every 30s
```

---

## 11. Deployment Architecture

### 11.1 Docker Compose Services

```yaml
# docker-compose.yml (development)
services:
  nvr-api:              # FastAPI + uvicorn
    build: ./docker/api
    ports: ["8000:8000"]
    environment: *api_env
    depends_on: [nvr-db, nvr-redis]
    volumes:
      - ./services/api:/app
      - ./config:/app/config

  nvr-stream-manager:   # RTSP connections + WebRTC/HLS relay (NO storage writes)
    build: ./docker/stream-manager
    network_mode: host    # Need multicast for ONVIF discovery
    environment:
      DB_HOST: localhost  # host mode — use localhost for services
      REDIS_HOST: localhost
      API_URL: http://localhost:8000
    depends_on: [nvr-db, nvr-redis]

  nvr-mediamtx:          # RTSP→WebRTC bridge (MediaMTX)
    image: bluenviron/mediamtx:latest
    ports: ["8554:8554", "8889:8889", "8189:8189"]
    volumes:
      - ./config/mediamtx.yml:/mediamtx.yml
    network_mode: host    # Same network as stream-manager for local RTSP relay

  nvr-recording-engine:  # FFmpeg segment writer + storage routing
    build: ./docker/recording-engine
    volumes:
      - recordings:/data/recordings
    depends_on: [nvr-db, nvr-redis, nvr-stream-manager]

  nvr-ai-engine:         # AI inference (separate container)
    build: ./docker/ai-engine
    volumes:
      - ai_models:/app/models
    depends_on: [nvr-redis, nvr-stream-manager]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]    # Comment out for CPU-only mode

  nvr-mqtt-bridge:       # NVR events → MQTT (Home Assistant)
    build: ./docker/mqtt-bridge
    depends_on: [nvr-redis, nvr-mosquitto]

  nvr-chrony:            # NTP server for camera time sync
    image: cturra/ntp:latest
    ports: ["123:123/udp"]
    environment:
      NTP_SERVERS: "pool.ntp.org"
    cap_add: [SYS_TIME]

  nvr-db:               # PostgreSQL 16 + TimescaleDB
    image: timescale/timescaledb:2.16-pg16
    ports: ["5432:5432"]
    volumes:
      - pg_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: nvr
      POSTGRES_USER: nvr_user

  nvr-redis:            # Redis 7
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redis_data:/data

  nvr-minio:            # MinIO S3-compatible storage
    image: minio/minio:latest
    ports: ["9000:9000", "9001:9001"]
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"

  nvr-mosquitto:        # MQTT broker (Home Assistant integration)
    image: eclipse-mosquitto:2
    ports: ["1883:1883"]
    volumes:
      - ./config/mosquitto.conf:/mosquitto/config/mosquitto.conf

  nvr-nginx:            # Reverse proxy
    build: ./docker/nginx
    ports: ["80:80", "443:443"]
    depends_on: [nvr-api]

  # Web frontend is served by nginx in production, or dev server in development
  nvr-web:              # React dev server (development only)
    build: ./docker/web
    ports: ["3000:3000"]
    volumes:
      - ./services/web/src:/app/src
    command: npm run dev -- --host 0.0.0.0

volumes:
  pg_data:
  redis_data:
  minio_data:
  recordings:
  ai_models:
```

### 11.2 Docker Network

```
Networks:
  nvr-backend:    { api, stream-manager, recording-engine, ai-engine, db, redis, minio }
  nvr-frontend:   { nginx, api, web }
  nvr-bridge:     host network bridge (for ONVIF multicast)

CIDR allocation:
  nvr-backend:   172.20.0.0/16
  nvr-frontend:  172.21.0.0/16

NGINX routes:
  /api/*         → nvr-api:8000
  /ws/*          → nvr-api:8000 (WebSocket upgrade)
  /              → nvr-web:3000 (dev) or /usr/share/nginx/html (prod)
```

### 11.3 Resource Limits

```yaml
services:
  nvr-api:
    deploy:
      resources:
        limits:   { cpus: "2", memory: "1G" }
        reservations: { cpus: "0.5", memory: "512M" }

  nvr-stream-manager:
    deploy:
      resources:
        limits:   { cpus: "4", memory: "4G" }     # FFmpeg per camera needs ~200MB
        reservations: { cpus: "1", memory: "1G" }

  nvr-ai-engine:
    deploy:
      resources:
        limits:   { cpus: "4", memory: "4G" }

  nvr-db:
    deploy:
      resources:
        limits:   { cpus: "2", memory: "2G" }

  nvr-recording-engine:
    deploy:
      resources:
        limits:   { cpus: "2", memory: "2G" }
```

### 11.4 Scaling Strategy

```
Vertical scaling first:
  - CPU++ for AI Engine (more cameras → more models running)
  - RAM++ for Stream Manager (more FFmpeg instances)
  - Disk I/O (NVMe for recordings hot tier)

Horizontal scaling (future, Phase 5+):
  - Stream Manager: scale out by camera count (max ~16 cameras per instance)
  - AI Engine: scale out + GPU pool per N cameras
  - API: scale out behind load balancer (stateless, session in Redis)
  - Recording Engine: NOT horizontally scalable (FFmpeg per camera → pin to single instance)

Hard limits:
  - 1 FFmpeg process per camera stream (main + sub = 2 per camera)
  - Max ~32 cameras on single Stream Manager (64 FFmpeg processes, 8-12GB RAM)
  - AI Engine: ~8 cameras on CPU, ~50+ on GPU (batch processing)
```

---

## 12. Сүлжээний Найдвартай байдал & Цагийн Синхрон

### 12.1 Камерын Цагийн Синхрон (NTP)

8 камер өөр өөр цагтай бол timeline playback, motion event-ийн цаг буруу бичигдэнэ.
NVR өөрөө NTP server болж камеруудаа синхрончилно:

```python
# NVR → NTP server (stratum 3) for cameras
async def sync_camera_time(camera_id: UUID):
    """Force camera NTP sync via ONVIF SetSystemDateAndTime."""
    # ONVIF: SetSystemDateAndTime(DateTimeType=NTP, NTP=Manual, NTPManual=[{IPv4Address: nvr_ip}])
    # Fallback: HTTP API per vendor
    # Hikvision: PUT /ISAPI/System/time?format=json {"timeMode":"NTP","NTPServer":"nvr_ip"}
    # Dahua: GET /cgi-bin/configManager.cgi?action=setConfig&...NTP.Server=nvr_ip
```

**Стратеги:**
- NVR container `chrony` NTP server ажиллуулна (stratum 2→3)
- Discovery хийх үед камерын цагийг шалгаж, 5 секундээс зөрвөл алерт
- Бичлэг хийхээс өмнө камерын цагийг синхрончилно
- `cameras` хүснэгтэд `time_synced_at TIMESTAMPTZ` талбар нэмнэ

### 12.2 DHCP Камерын IP Өөрчлөгдөх Асуудал (MAC-based Identity)

Камер DHCP-тэй, IP нь өөрчлөгдвөл бичлэг тасарна. `cameras` хүснэгтэд `preferred_ip`, `ip_binding`, `network_interface` талбарууд энэ асуудлыг шийднэ.

-- IP өөрчлөлтийн түүх:
CREATE TABLE camera_ip_history (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id    UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    old_ip       INET NOT NULL,
    new_ip       INET NOT NULL,
    detected_by  VARCHAR(50) NOT NULL,  -- 'arp', 'rtsp_probe', 'onvif', 'manual'
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ip_history_camera ON camera_ip_history(camera_id, changed_at DESC);
```

**MAC-based persistent identity алгоритм:**
1. Камер бүртгэх үед MAC address заавал хадгална
2. 60 секунд тутамд ARP table / ONVIF GetNetworkInterfaces шалгана
3. MAC-тэй IP зөрвөл → `camera_ip_history` бичнэ, `cameras.ip_address` шинэчилнэ
4. RTSP/ONVIF холболт тасарвал → MAC-аар ARP scan хийж шинэ IP хайна
5. DHCP reservation хийхийг зөвлөх UI notification

### 12.3 Multi-NIC Сервер Дэмжлэг

Нэг NIC камерын сүлжээнд, нөгөө NIC хэрэглэгчийн сүлжээнд:

```yaml
# docker-compose.yml network config
services:
  nvr-api:
    networks:
      camera_net:        # 192.168.1.0/24 — камерын сүлжээ
        ipv4_address: 192.168.1.2
      user_net:          # 10.0.0.0/24 — хэрэглэгчийн сүлжээ
        ipv4_address: 10.0.0.2
```

**Камерын сүлжээний тохиргоо (DB-д):**
`cameras.network_interface` талбар нь камер холбогдох NIC-ийг заана: `'camera_net'`, `'user_net'`, `'both'`. Stream Manager энэ тохиргоог харж зөв NIC-ээр холбогдоно.

### 12.4 IPv6 Дэмжлэг

Зарим орчин үеийн камер IPv6-аар ирдэг (Reolink, Axis):

```sql
-- INET төрөл IPv4+IPv6 хоёрыг дэмждэг тул одоогийн схем бэлэн
-- Discovery engine-д IPv6 multicast (ff02::c) нэмэх:
ALTER TYPE discovery_method ADD VALUE 'onvif_ipv6';
-- mDNS: IPv6-д зориулж ff02::fb multicast ашиглах
```

### 12.5 Сүлжээний Bandwidth Monitoring & Adaptive Quality

```python
class BandwidthMonitor:
    """Камер бүрийн bandwidth хэрэглээг хэмжиж, тохируулна."""

    async def monitor(self):
        # FFmpeg progress-оос bitrate унших: progress=continue|bitrate=4200.0kbits/s
        # Хэрэглэгч: browser API NetworkInformation.downlink
        pass

    async def auto_degrade(self, camera_id: UUID):
        """Bandwidth хангалтгүй үед sub-stream руу автомат унах:
        - Multi-view grid: 4+ камер → sub-stream
        - Single view: main stream байх
        - Mobile / PWA: sub-stream default
        """
```

**Bandwidth Calculator (UI):**
```
8 cameras × 4K H.265 = 8 × 8 Mbps = 64 Mbps (бичлэг)
4 cameras live view = 4 × 8 Mbps = 32 Mbps (хэрэглэгч)
─────────────────────────────────────────────
Total required: 96 Mbps (Gigabit Ethernet → OK)
100 Mbps network: 2 камер л main stream үзэх боломжтой
```

---

## 13. Үйл ажиллагаа & Тасралтгүй байдал

### 13.1 Backup & Сэргээх Төлөвлөгөө

| Зүйл | Хэрхэн | Хэзээ | Хаана |
|------|--------|-------|-------|
| **PostgreSQL** | `pg_dump -Fc` (custom format) | Өдөр бүр 03:00 | S3/MinIO cold tier |
| **TimescaleDB chunks** | WAL-G / pgBackRest | Continuous WAL archive | S3/MinIO |
| **System config** | DB backup-д багтана | Өдөр бүр 03:00 | — |
| **Бичлэгүүд** | Storage tier migration → S3 | Tier бодлогоор | S3 (байнга) |
| **AI models** | Docker volume backup | Эхний deploy + model update үед | S3 |

**RPO (Recovery Point Objective):** 24 цаг (өдрийн backup), TimescaleDB WAL → 0 алдагдал
**RTO (Recovery Time Objective):** 2 цаг

```bash
# scripts/backup.sh
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME -Fc -f "/tmp/nvr_backup_${TIMESTAMP}.dump"
aws s3 cp "/tmp/nvr_backup_${TIMESTAMP}.dump" "s3://nvr-backups/db/"
aws s3 ls "s3://nvr-backups/db/" | sort | head -n -7 | awk '{print $4}' | \
  while read f; do aws s3 rm "s3://nvr-backups/db/$f"; done  # keep last 7 days
```

**Сэргээх алхамууд:**
1. `docker compose up -d nvr-db` (хоосон PostgreSQL эхлүүлэх)
2. `pg_restore -d nvr nvr_backup_20260721_030000.dump`
3. TimescaleDB chunks: `timescaledb-restore` (WAL-G)
4. `docker compose up -d` (бусад бүх үйлчилгээ)

### 13.2 Upgrade & Rollback Стратеги

```sql
-- Upgrade tracking table:
CREATE TABLE system_upgrades (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_version    VARCHAR(20) NOT NULL,
    to_version      VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending → pre_check → backing_up → migrating → verifying → complete | failed → rolling_back

    pre_check_ok    BOOLEAN,
    backup_path     VARCHAR(1024),
    migration_applied INTEGER DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Rollback стратеги:**
1. DB migration `alembic downgrade -1` (down migration байхгүй бол хийхгүй)
2. Өмнөх Docker image tag руу буцах: `IMAGE_TAG=v0.01.01 docker compose up -d`
3. Хамгийн сүүлийн backup restore хийх

**Бичлэг тасралтгүй байх стратеги:**
- NVR-api + NVR-web → 30 сек downtime (Docker restart)
- nvr-stream-manager → бичлэг тасрах (FFmpeg дахин холбогдоно, ~5 сек gap)
- Шинэчлэлийг recording gap багатай цагаар хийх (шөнийн 03:00)

### 13.3 Камер Firmware Update Үед Авто-Pause

```python
class FirmwareUpdateHandler:
    """Камер firmware update хийх үед бичлэгийг түр зогсоож, update дууссаны дараа үргэлжлүүлнэ."""

    async def on_camera_unreachable(self, camera_id: UUID):
        # 5 минут бол "maybe updating" гэж тэмдэглэ
        # 15 минутаас дээш → жинхэнэ offline алерт
        pass

    async def on_camera_reachable(self, camera_id: UUID):
        # Онлайн болсон → бичлэгийг автоматаар үргэлжлүүлэх
        # Firmware version өөрчлөгдсөн эсэхийг шалгаж audit_log бичих
        pass
```

### 13.4 Daylight Saving Time (DST)

```sql
-- Бүх recording schedule UTC-д хадгалагдана, хэрэглэгчийн timezone-р харуулна.
-- DB: TIMESTAMPTZ (UTC)
-- UI: convert to user timezone (system_config 'system.timezone')
--
-- DST шилжилтийн үед:
-- Spring forward (02:00→03:00): 1 цагийн бичлэг байхгүй (норм)
-- Fall back (03:00→02:00): давхар цагийн бичлэг → recording schedule сэрэмжлүүлэг
```

---

## 14. Compliance, Интеграци & Үр ашиг

### 14.1 GDPR / Хууль Эрх Зүйн Compliance

**Privacy тохиргоо (DB-д):**
`cameras.privacy_mode = 'none' | 'mask_zones' | 'blur_faces'`
`recordings.retention_override_days` → хэрэглэгч гараар "энэ бичлэгийг Х хоног хадгал" гэж тохируулж болно.

Хандалтын бүртгэл: `audit_log` хүснэгтээр `recording.viewed`, `recording.exported`, `live_stream.viewed` бүртгэгдэнэ.

**Автомат Privacy функц:**
- Хүний нүүр автомат blur (AI engine-д нэмэх)
- Privacy zone masking (draw zones in UI, pixelate during recording)
- Retention policy: GDPR "recordings not older than X days" дүрэм
- Right to access: audit_log-оос өөрийн бичлэгүүдийг экспортлох API
- Data deletion request: `POST /api/v1/compliance/delete-person-data` (admin)

### 14.2 External Integration Points

#### Home Assistant Integration

```yaml
# Home Assistant configuration.yaml
mqtt:
  broker: nvr.mbm.mn
  port: 1883

camera:
  - platform: mqtt
    name: "NVR Front Door"
    topic: "nvr/cameras/front_door/snapshot"

binary_sensor:
  - platform: mqtt
    name: "NVR Motion Front Door"
    state_topic: "nvr/cameras/front_door/motion"
    payload_on: "ON"
    payload_off: "OFF"
```

**MQTT Event Bridge (nvr-mqtt-bridge service):**
```python
# nvr → MQTT topic map:
# nvr/cameras/{camera_name}/motion      → motion_detected events (ON/OFF)
# nvr/cameras/{camera_name}/snapshot    → latest snapshot (JPEG binary)
# nvr/cameras/{camera_name}/online      → online status (ON/OFF)
# nvr/cameras/{camera_name}/detection   → person/car/... detected
# nvr/storage/status                    → {"total":..., "free":..., "pct":...}
# nvr/system/health                     → {"status":"healthy",...}
```

#### REST API Integration

```python
# API key scope-тойгоор external системээс хандах:
# GET  /api/v1/cameras                    → камерын жагсаалт
# GET  /api/v1/cameras/{id}/snapshot      → агшин зураг
# GET  /api/v1/events?event_type=motion   → motion event-үүд
# WS   /api/v1/events/stream              → realtime event stream
```

#### Webhook Outgoing

```python
# Event → Webhook config (DB-д notification_svc хүснэгтээр):
# { "url": "https://hooks.slack.com/...", "method": "POST",
#   "headers": {"Content-Type": "application/json"},
#   "body_template": "{\"text\": \"ALERT: {{event_type}} at {{camera_name}}\"}" }
```

### 14.3 ONVIF Native Motion Detection (CPU Хэмнэх)

```python
class ONVIFMotionHandler:
    """Камерын өөрийн motion detection-ийг ашиглах (ONVIF RuleEngine):
    - Camera-side motion detection → CPU/GPU хэрэглэхгүй
    - ONVIF event subscription → motion event
    - Fallback: server-side OpenCV MOG2 (ONVIF motion байхгүй камерт)
    """

    async def subscribe_motion(self, camera_id: UUID):
        # ONVIF CreatePullPointSubscription → PullMessages loop
        # Motion event ирэхэд → event emitted → recording trigger
        pass

    # camera_capabilities.fields:
    # onvif_motion_supported: bool     # ONVIF RuleEngine дэмждэг эсэх
    # motion_source: 'onvif' | 'server' | 'both'
```

### 14.4 Audio Level Monitoring & Alert

```sql
-- Audio event threshold тохиргоо (event_rules.audio_config):
-- { "min_db": 80, "duration_seconds": 3, "class_filter": ["speech","dog_bark"] }

-- Audio level history (TimescaleDB):
CREATE TABLE audio_levels (
    id          UUID NOT NULL DEFAULT uuid_generate_v4(),
    camera_id   UUID NOT NULL REFERENCES cameras(id),
    level_db    REAL NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, measured_at)
);
SELECT create_hypertable('audio_levels', 'measured_at', chunk_time_interval => INTERVAL '1 hour');
CREATE INDEX idx_audio_levels_camera ON audio_levels(camera_id, measured_at DESC);
```

```python
class AudioLevelMonitor:
    """FFmpeg-ээс audio level уншиж, дүн шинжилгээ хийх:
    ffmpeg -i rtsp://... -af "volumedetect" -f null /dev/null
    → mean_volume: -23.5 dB, max_volume: -3.2 dB
    """

    async def monitor(self, camera_id: UUID):
        # 10 секунд тутамд audio level шалгах
        # Threshold (configurable) давсан → event үүсгэх
        pass
```

---

## 15. Хөгжүүлэлтийн Орчин & Хэрэгслүүд

### 15.1 Камер Симуляци (Testing Without Real Cameras)

```bash
# RTSP test stream generator (FFmpeg):
ffmpeg -re -f lavfi -i "testsrc=duration=3600:size=1920x1080:rate=25" \
       -f lavfi -i "sine=frequency=440:duration=3600" \
       -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
       -c:a aac -b:a 128k \
       -f rtsp rtsp://localhost:8554/test_cam_1

# Multi-camera simulation script:
for i in $(seq 1 8); do
  ffmpeg -re -f lavfi -i "testsrc=size=1920x1080:rate=25[out0];color=red:size=1920x1080[bg];[bg][out0]overlay=0:0:enable='between(t,${i},${i}+1)'" \
         -c:v libx264 -preset ultrafast -f rtsp rtsp://localhost:8554/cam_${i} &
done
```

```python
class CameraSimulator:
    """Программаар камер симуляци хийх:

    Features:
      - Multi-camera (хүссэн тоогоор)
      - Motion events injection (тодорхой хугацаанд хөдөлгөөн оруулах)
      - Object overlay (persons, cars зурган дээр нэмэх)
      - Camera offline/online simulation
      - Audio stream (sine wave эсвэл файл)
      - ONVIF response simulation (mock ONVIF server)
      - Bandwidth throttling simulation
    """
```

### 15.2 Камер Тохируулах Wizard (Guided UI)

```
Wizard Steps:
┌─────────────────────────────────────────────────────────┐
│ Step 1: Welcome                                          │
│   "NVR тавтай морил! Камераа хэрхэн холбох вэ?"          │
│   [Auto-Discovery] [Manual Add] [Import Config]          │
├─────────────────────────────────────────────────────────┤
│ Step 2: Auto-Discovery                                   │
│   Scanning your network...                               │
│   ┌──────────────────────────────────────────────────┐  │
│   │ ✅ ONVIF WS-Discovery    → 2 devices found        │  │
│   │ 🔄 RTSP Port Scan         → scanning... (45%)     │  │
│   │ ⏳ HTTP Web Scan           → pending               │  │
│   └──────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│ Step 3: Review Discovered Cameras                        │
│   ┌────────┬──────────┬─────────┬───────┬────────────┐  │
│   │ Select │ Name     │ Vendor  │ IP    │ Confidence │  │
│   ├────────┼──────────┼─────────┼───────┼────────────┤  │
│   │  ☑    │ Front    │ Hikvis. │ .100  │ 98% ✓      │  │
│   │  ☑    │ Garage   │ Dahua   │ .105  │ 92% ✓      │  │
│   │  ☐    │ Unknown  │ ???     │ .200  │ 35% ⚠      │  │
│   └────────┴──────────┴─────────┴───────┴────────────┘  │
├─────────────────────────────────────────────────────────┤
│ Step 4: Credentials                                     │
│   Camera: Front Door (Hikvision)                         │
│   Username: [admin               ]                       │
│   Password: [••••••••            ]  [Test Connection]    │
│   💡 Default: admin / admin12345                         │
├─────────────────────────────────────────────────────────┤
│ Step 5: Recording Settings                               │
│   Recording Mode: [Continuous ▾]                         │
│   Storage: [local_primary ▾]                             │
│   Retention: [30 days           ]                        │
├─────────────────────────────────────────────────────────┤
│ Step 6: Ready!                                           │
│   ✅ 5 cameras added                                     │
│   📹 Recording started                                   │
│   [Go to Dashboard]                                      │
└─────────────────────────────────────────────────────────┘
```

### 15.3 Системийн Өөрөө Тестлэх (Built-in Self Test)

```python
# POST /api/v1/system/self-test
# Response:
{
  "data": {
    "database": {"status": "ok", "latency_ms": 2},
    "redis": {"status": "ok", "latency_ms": 1},
    "minio": {"status": "ok", "latency_ms": 5},
    "ffmpeg": {"status": "ok", "version": "7.0"},
    "disk_space": {"status": "ok", "free_pct": 65},
    "camera_streams": [
      {"camera": "Front Door", "status": "ok", "fps": 25, "bitrate_kbps": 4200},
      {"camera": "Garage", "status": "degraded", "error": "High packet loss: 15%"}
    ]
  }
}
```

---

## 16. Хөгжүүлэх үе шатууд (Шинэчилсэн)

### Phase 1 — Foundation (Эхний 2 долоо хоног)
- [x] Project structure + AGENTS.md + PLAN.md
- [ ] Docker Compose орчин (db, redis, minio, api, nginx, mosquitto)
- [ ] FastAPI skeleton + full project structure
- [ ] SQLAlchemy models (бүх хүснэгтүүд + шинэ: camera_ip_history, system_upgrades, audio_levels)
- [ ] Alembic migration (DDL бүрэн)
- [ ] Config seed script (`scripts/seed_db.py`)
- [ ] JWT auth + RBAC middleware
- [ ] API documentation (auto OpenAPI)
- [ ] CI/CD pipeline
- [ ] Web UI skeleton (React Router + auth gate + wizard framework)
- [ ] Camera simulator (FFmpeg RTSP test streams)
- [ ] NTP server container (chrony)

### Phase 2 — Camera Integration (2 долоо хоног)
- [ ] ONVIF WS-Discovery engine implementation
- [ ] RTSP/HTTP/ARP/mDNS/Vendor scanner implementations
- [ ] Vendor fingerprint engine + vendor_patterns.yml → DB
- [ ] MAC-based identity + DHCP IP tracking (camera_ip_history)
- [ ] Camera CRUD API (full) + test/health API
- [ ] Stream Manager — FFmpeg subprocess manager
- [ ] WebRTC signaling server (WebSocket + aiortc)
- [ ] HLS fallback streaming
- [ ] Bandwidth monitor + adaptive quality (main/sub auto-switch)
- [ ] Multi-NIC network binding support
- [ ] Web UI: Camera grid + live view page + Camera Setup Wizard

### Phase 3 — Recording (2 долоо хоног)
- [ ] Recording Engine — continuous/motion/scheduled
- [ ] FFmpeg segment writer with atomic rotation
- [ ] Motion detection (frame differencing + MOG2/KNN)
- [ ] ONVIF native motion subscription (CPU хэмнэх)
- [ ] Recording schedule engine (cron + timezone + DST handling)
- [ ] Storage backend implementations (Local, NFS, SMB, S3)
- [ ] Storage tiering auto-migration
- [ ] Retention policy + emergency cleanup
- [ ] Corrupt segment recovery
- [ ] Firmware update auto-pause/resume handler
- [ ] Web UI: Recording browser + playback + timeline

### Phase 4 — AI & Advanced (2 долоо хоног)
- [ ] YOLOv8n ONNX object detection pipeline
- [ ] Face detection + recognition (RetinaFace + ArcFace)
- [ ] Audio capture + YAMNet event detection
- [ ] Audio level monitoring & threshold alert
- [ ] Event rules engine (zone-based, schedule, confidence)
- [ ] Two-way audio talkback (ONVIF + FFmpeg)
- [ ] PTZ control (ONVIF + vendor API)
- [ ] Notification service (Email + Webhook + Push)
- [ ] Realtime WebSocket event push
- [ ] MQTT event bridge (Home Assistant integration)
- [ ] Privacy mode: face blur + zone masking
- [ ] Web UI: Event feed + Detection zone editor + Face library + Privacy zones

### Phase 5 — Production (2 долоо хоног)
- [ ] Performance profiling & optimization
- [ ] Security hardening (HTTPS, rate limiting, audit, GDPR compliance)
- [ ] Prometheus metrics + Grafana dashboards
- [ ] Database backup/restore automation (pg_dump + WAL-G)
- [ ] Upgrade/rollback mechanism (system_upgrades table)
- [ ] Self-test / diagnostics endpoint
- [ ] IPv6 full support
- [ ] PWA mobile support (offline, push notifications)
- [ ] Load testing (artillery/k6, 32 cameras simulation)
- [ ] Test coverage ≥80% (unit + integration + E2E)
- [ ] Production deployment guide + docker-compose.prod.yml
- [ ] Monitoring + alerts (uptime, disk space, camera offline, time drift)

---

*Сүүлд шинэчилсэн: 2026-07-21*
*Хувилбар: v0.00.02*
