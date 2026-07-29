# AGENTS.md — mBm NVR System

## Agent Workflow: Comprehensive Verified Execution

As an autonomous developer agent working on the mBm NVR System, you must not simply generate a response and stop. You are required to follow a strict **Plan → Execute → Self-Reflect → Refine** cycle. Your final output must be verified, bug-free, and ready for production.

### Execution Cycle

1. **Understand & Plan:** 
   - Analyze the task against the domain rules in this document before writing any code.
   - Formulate a step-by-step plan internally.
2. **Execute:** 
   - Write clean, optimized code that strictly adheres to the architectural rules (Docker, FFmpeg, API conventions, etc.).
3. **Self-Correction & Edge-Case Analysis (Crucial):**
   - *Logic Check:* Does this solution handle edge cases correctly (e.g., stream reconnects, Safari vs. Chrome playback)?
   - *Compliance Check:* Did I use `libx264`? Did I use 4-space indentation? Am I using the `useStreamPlayer` hook correctly?
4. **Refine & Re-verify:** 
   - If your self-critique finds flaws or rule violations, fix them immediately before presenting the final answer.
5. **Final Delivery:** 
   - Only output the fully verified solution. Briefly explain what was changed and how it was validated.

### Strict Constraints
- **No incomplete work:** Never deliver untested, unverified, or broken code.
- **Think silently:** Perform your planning and self-correction internally, presenting only the final polished result.
- **Ask for clarity:** If a request is ambiguous or impossible given the system constraints, ask clarifying questions instead of guessing.

## Docker Networking

- All services use Docker compose networks (`nvr-net`), NOT `network_mode: host`.
- **Container hostnames** (not IPs or `host.docker.internal`) for inter-service communication:
  - `nvr-db` (PostgreSQL), `nvr-redis`, `nvr-minio`
  - `nvr-stream-manager:8001`, `nvr-mediamtx:8554/8888/9997`
   - `nvr-api:8000`, `nvr-web:3000`
- Port mappings required for host access: `8000`, `3000`, `8888`, `8554`, `9997`, `8001`, `8889` (WHEP), `8189/udp` (WebRTC ICE)

## Live Streaming — MediaMTX First

**MediaMTX is the center of the live path. Use it everywhere it can be used:**

1. **Sub streams: MediaMTX `sourceOnDemand` pull (default, `MEDIAMTX_PULL_MODE=sub`)** — the stream-manager creates a pull path via the MediaMTX API (`/v3/config/paths/add`) with the camera RTSP URI as `source`. MediaMTX fetches the camera itself while readers exist and closes 10s after the last reader leaves. **Zero FFmpeg transcode CPU** for sub streams.
2. **Main streams: FFmpeg `libx264` relay-push** (Dahua FU-A packet ordering breaks MediaMTX HLS with `-c:v copy` pushes) with `-preset ultrafast -tune zerolatency -g 15 -b:v 2500k -maxrate 2500k -bufsize 5000k -threads 1`. Sub fallback relay (if pull disabled): `-b:v 500k -bufsize 1000k`.
3. **Playback: WebRTC (WHEP) first, LL-HLS fallback** — `useStreamPlayer` tries WHEP at `/mtx/{path}/whep` (MediaMTX :8889), falls back to LL-HLS on any failure. LL-HLS requires BOTH server (`hlsVariant: lowLatency`) and client (`lowLatencyMode: true`) enabled.
4. **Recording: direct camera RTSP `-c:v copy`** (zero video CPU) — do NOT route through MediaMTX for continuous recording. Exception: motion-mode sub recording reads the relay path (`RECORD_VIA_RELAY=1`) because the AI sampler keeps that path warm anyway — ~100ms attach, ≤1s keyframe wait.
5. **AI sampling: reads the MediaMTX relay path** (`rtsp://nvr-mediamtx:8554/{cid}_sub`) — one camera connection serves AI + all viewers.
6. WebRTC through Docker NAT requires `MTX_WEBRTCADDITIONALHOSTS` = host LAN IP (`MEDIAMTX_ICE_HOST_IP` in .env) so ICE candidates are reachable from browsers.

## FFmpeg Transcoding

- When transcoding is required (main-stream relay): always `libx264` with `-preset ultrafast -tune zerolatency -g 15`, bitrate per tier (sub 500k / main 2500k, bufsize 2×, overridable via `system_config` keys `stream.sub_bitrate_kbps`, `stream.main_bitrate_kbps`, `stream.threads`).
- Never push `-c:v copy` to MediaMTX — H.264 FU-A packet ordering issues from cameras cause MediaMTX HLS errors. (Recording to disk uses `-c:v copy` — different path, see Recording Lifecycle.)
- Output: `rtsp://nvr-mediamtx:8554/{camera_id}` or `{camera_id}_sub`.

## Frontend Stream Playback — useStreamPlayer Hook

**All video playback MUST use the shared `useStreamPlayer` hook** (`src/hooks/useStreamPlayer.ts`):

```ts
import { useStreamPlayer, type StreamType } from "../hooks/useStreamPlayer";
const { state, retrySec, attachVideo, startStream } = useStreamPlayer({
  cameraId,           // UUID string
  streamType,         // "main" | "sub"
  protocol,           // optional: "webrtc" (default, WHEP) or "hls" — WebRTC falls back to LL-HLS automatically
  pollAttempts,       // optional, default 60 (≈45s cold-start budget)
  retryIntervalMs,    // optional, default 60000
});
```

### Return values

| Value | Type | Description |
|-------|------|-------------|
| `state` | `"connecting" \| "loading" \| "playing" \| "retrying" \| "error"` | Current stream state |
| `retrySec` | `number` | Countdown seconds when in `retrying` state |
| `attachVideo` | `(el: HTMLVideoElement \| null) => void` | Ref callback for `<video>` element |
| `startStream` | `() => Promise<void>` | Manually retry/start |

### Usage pattern

```tsx
<video ref={attachVideo} muted autoPlay playsInline
  className={state === "playing" ? "opacity-80" : "opacity-0"} />

{state === "connecting" && <Spinner label="Connecting..." />}
{state === "loading" && <Spinner label="Buffering..." />}
{state === "retrying" && <button onClick={startStream}>Retry ({retrySec}s)</button>}
{state === "playing" && <StreamToggle streamType={streamType} onChange={setStreamType} />}
```

### Where it's used

- `src/components/camera/MiniLivePreview.tsx` — dashboard grid tiles
- `src/components/camera/CameraGrid.tsx:ExpandedView` — modal on single click
- `src/pages/LiveViewPage.tsx` — full live view

## API Response Convention

All API endpoints wrap responses in `{ "data": ... }`:
```json
{"data":{"hls_url":"/hls/{id}/index.m3u8","status":"started"}}
```

Frontend hooks must unwrap: `r.data.data` (axios), `json.data` (fetch).

## Router Prefix Convention

Each API v1 router uses full prefix in its own file (e.g., `prefix="/api/v1/cameras"`).
`__init__.py` includes without extra prefix:
```python
router.include_router(cameras_router)  # NO extra prefix
```

## Python Indentation

All Python files use 4-space indentation. Use `textwrap.dedent()` when writing via heredoc.

## Stream Relay Lifecycle

1. Frontend calls `POST /api/v1/cameras/{id}/live/start?stream=main|sub`
2. `live_relay.py` checks stream-manager status first, then delegates
3. **Sub (default)**: stream-manager creates a MediaMTX `sourceOnDemand` pull path — MediaMTX fetches the camera itself while readers exist. **Main**: FFmpeg libx264 relay-push to `rtsp://nvr-mediamtx:8554/{cid}`
4. `useStreamPlayer` tries WebRTC WHEP (`/mtx/{path}/whep`) first, falls back to LL-HLS (`/hls/{path}/index.m3u8`)
5. Circuit breaker prevents rapid restarts (15s→120s, reset only after a 60s stable run — never on spawn)
6. **Idle reaper** (FFmpeg relays only): stops relays with zero MediaMTX readers for 10 min (`STREAM_IDLE_TIMEOUT_S`). Pull paths are NOT reaped — MediaMTX `sourceOnDemandCloseAfter` (10s) manages them
7. Pull-path configs live in MediaMTX memory — after a MediaMTX restart they are re-created on the next `live/start` (relay/status verifies against the MediaMTX API)
8. MediaMTX has NO hot reload — SIGHUP terminates it; restart via compose

## Recording Lifecycle (recording-engine)

1. Per-camera FFmpeg supervisor: sub-stream RTSP → `-c:v copy` → 300s MP4 segments at `{storage_path}/{cid}/YYYY/MM/DD/`
2. Storage path resolved at startup: reads active local `storage_backends.mount_point` from DB (admin panel config), falls back to `STORAGE_LOCAL_PATH` env var
3. Docker bind mount: host `${STORAGE_HOST_PATH}` → container `${STORAGE_LOCAL_PATH}` (`/data` → `/data/recordings`)
4. `SegmentCatalog` (60s): registers closed segments in `recordings` table (ffprobe duration; unreadable segments registered `is_corrupt=true`, duration never fabricated). `s3://` rows are never purged by the local filesystem walk. Thumbnails retry at most once/day (`.thumb_failed` marker)
5. **Circular retention** (5 min loop): when disk ≥ `storage.max_usage_percent` (85%) or free < `storage.min_free_gb` (2GB) → oldest segments **of that root** deleted first in batches — disk can never fill up. Age limit: `retention.default_days` (7). Files < 10 min old protected. S3 objects deleted via the storage backend, orphan camera dirs cleaned after the age grace
6. `DiskAnalytics` (hourly): GB/day per camera + days-fit projection → `system_config` key `storage.analysis` → shown on Storage page
7. Env: uses `POSTGRES_*` vars + `NVR_ENCRYPTION_KEY` (AES-256-GCM via `nvr_common.security`)
8. `recording_mode`: continuous/motion record; `never`/`disabled` skip
9. **Circuit breaker**: 5s→600s escalating; resets only after a 300s stable session (a camera reboot costs seconds, not a flat 60s)
10. **Progress watchdog**: if the active segment's size doesn't grow for `max(2×segment_seconds, 180s)`, the hung FFmpeg is killed and restarted — process alive ≠ recording
11. Recorder config signature: stream URI/credentials/storage/segment length changes rebuild the recorder within 30s (no stale RTSP URLs)
12. Codec probing (video+audio) is cached per stream URL for 1h — motion recorders don't pay an ffprobe round-trip per event

## AI Detection Lifecycle (ai-engine)

1. `FrameSampler` per camera: a **drainer thread** reads the MediaMTX relay sub-stream continuously and keeps only the freshest frame (no stale-frame lag; half-dead sessions detected via 15s staleness). Samples at `AI_TARGET_FPS` (default 1.0) → MOG2 motion gate → shared YOLOv8n ONNX session
2. Detections filtered by `ai_objects`, `ai_min_confidence` (clamped 0.05–0.95), and `ai_zones` polygons (bottom-center of bbox must be inside a zone; empty zones = whole frame)
3. **Two-stage tracking**: stage 1 strict (IoU ≥ 0.3 AND centre distance ≤ 0.15), stage 2 relaxed centre-distance fallback (≤ 0.30) — at 1 FPS a moving object has zero frame-overlap, so stage 1 alone would fire a new event every frame. New objects fire immediately, throttled by a 5s per-class global gap (anti-spam backstop). Moving: 1 event/15s. Stationary: persons 5 min, vehicles 20 min. Parked objects (5+ stationary frames) exempt from the 300s timeout; a parked tracklet that moves expires only after 10s UNSEEN (no double-fire)
4. Events → `events` table (plain SQL) + JPEG snapshot at `{STORAGE_LOCAL_PATH}/snapshots/` + Redis pub. Snapshot is written BEFORE the DB insert; counter upserts are independent of the event insert (a counter failure never loses the event/broadcast)
5. Model: `yolov8n.onnx` in `ai_models` volume at `/app/models` (exported on host via ultralytics, not in image). A missing model never disables motion-only/ONVIF workers — detection no-ops until it loads
6. Media auth: `<img>/<video>` use `?token=` query param (get_current_user accepts it)
7. **Motion publishing**: every sampler publishes motion state to Redis `nvr:motion` — on change + 30s heartbeat in BOTH states (active and inactive, so consumers can detect a dead publisher). Workers are also created for `recording_mode='motion'` cameras with AI disabled (motion-only mode, no YOLO). Relay start is re-POSTed whenever capture fails (the relay is the sampler's lifeline)
8. Worker config signature (incl. credentials + storage path): any camera config change recreates the worker within 15s

## Motion-Only Recording (recording_mode='motion')

1. AI engine publishes `{camera_id, active}` to Redis `nvr:motion` (ONVIF subscribers publish the REAL event value — `Value="false"` ends motion)
2. `MotionRecorderController` (recording-engine): motion active → start `CameraRecorder`; motion inactive → stop after `recording.motion_stop_delay_s` (30s); new motion cancels the pending stop. Every True is a keepalive (refreshes last-active timestamp)
3. **Staleness sweep** (30s): recorders with no keepalive for 90s (publisher dead / lost False) or whose camera left motion-mode are stopped — motion recorders can never run forever
4. Motion recorders live in a separate registry from continuous recorders (no reconcile conflicts)
5. Motion recorders read the MediaMTX relay path (`RECORD_VIA_RELAY=1`, server-side motion only) — ~100ms attach, ≤1s keyframe wait, one shared camera connection
6. Segments are marked `recording_type='motion'` by the catalog based on camera mode

## Engineering Rules (learned from production incidents — follow strictly)

1. **CancelledError rule**: after `except asyncio.CancelledError`, NEVER fall through into reconnect/continue logic — re-raise (or check a `_stopping` flag). A swallowed cancel turned every intentional stream stop into an automatic restart and defeated the idle reaper completely.
2. **Circuit breaker rule**: `reset()` only after a proven stable run (300s recording / 60s stream), never on spawn — a spawned FFmpeg proves nothing. Don't trip before your own retry attempts; trip once on exhaustion.
3. **Concurrency rule**: every check-then-act on a shared registry (processes, recorders, paths) must hold a per-key `asyncio.Lock` across the whole check→spawn→register sequence.
4. **S3 path rule**: any code walking the local filesystem (catalog, retention, cleanup) must skip `s3://` paths; deletion of remote objects goes through the storage backend abstraction, never `os.unlink`.
5. **Motion state rule**: heartbeat BOTH states (active + inactive) so consumers can detect a dead publisher; consumers must have a staleness watchdog (90s) because Redis pub/sub is fire-and-forget. Publisher-side retries a failed publish once.
6. **Event pipeline rule**: snapshot → DB event insert → broadcast. Counters/notifications are independent transactions — their failure must never lose the event or its broadcast.
7. **FFmpeg watchdog rule**: process alive ≠ work happening. Supervisors must stat output growth (recording) or frame freshness (sampling) and kill hung processes.
8. **Tracking-FPS coupling rule**: IoU thresholds are only valid for a given sample rate — at 1 FPS movers have zero frame overlap, so a distance-based fallback match + a per-class global event gap are mandatory. Re-validate tracking constants when `AI_TARGET_FPS` changes.
9. **MediaMTX usage rule**: live path = MediaMTX (sourceOnDemand pull, LL-HLS, WebRTC WHEP). Continuous recording = direct camera `-c:v copy` (lowest CPU, independent). AI sampling + motion recording = the shared relay path. Server config (LL-HLS variant) is useless without the matching client flags (`lowLatencyMode: true`).
10. **OpenCV options rule**: `OPENCV_FFMPEG_CAPTURE_OPTIONS` entries are separated by `|` (not `;`): `"rtsp_transport;tcp|timeout;15000000"`.

## Key Files

| File | Purpose |
|------|---------|
| `services/stream-manager/app/manager.py` | FFmpeg process lifecycle, circuit breaker, idle reaper |
| `services/stream-manager/app/relay_api.py` | HTTP API for relay start/stop/status |
| `services/api/app/services/live_relay.py` | Stream relay delegation to stream-manager |
| `services/api/app/api/v1/cameras.py` | Camera endpoints including live/start |
| `services/recording-engine/app/main.py` | Recording loops (reconcile/catalog/retention/analytics) |
| `services/recording-engine/app/recorder.py` | Per-camera FFmpeg supervisor with auto-restart |
| `services/recording-engine/app/catalog.py` | Segment→DB registration + sync |
| `services/recording-engine/app/retention.py` | Circular + age-based cleanup |
| `services/recording-engine/app/analytics.py` | GB/day + capacity projection |
| `packages/common/nvr_common/storage.py` | Storage backend ABC + Local + S3 implementations |
| `services/api/app/services/recording_service.py` | Storage backend CRUD + usage aggregation |
| `services/api/app/api/v1/storage.py` | Storage API endpoints |
| `services/ai-engine/app/main.py` | AI worker reconcile loop |
| `services/ai-engine/app/detector.py` | YOLOv8 ONNX (1,84,8400) post-processing + NMS |
| `services/ai-engine/app/frame_sampler.py` | Motion gate + dedup + event persist |
| `services/ai-engine/app/db.py` | Plain-SQL DB access (no cross-service imports) |
| `packages/common/nvr_common/security.py` | Shared AES-256-GCM password decrypt |
| `services/web/src/hooks/useStreamPlayer.ts` | Shared HLS player hook |
| `services/web/src/components/camera/MiniLivePreview.tsx` | Dashboard tile preview |
| `services/web/src/components/camera/CameraGrid.tsx` | Dashboard grid + ExpandedView modal |
| `services/web/src/pages/LiveViewPage.tsx` | Full live view with PTZ |

## Recording Playback — Troubleshooting

### 1. CSP blocks hls.js in RecordingPlayer

**Symptom:** Recordings page shows spinner forever, no errors in console (Chrome). Works in Safari.

**Root cause:** `hls.js` uses `new Function()` internally. CSP `script-src` blocks `unsafe-eval`. Chrome enforces CSP strictly; Safari doesn't.

**Fix:** `RecordingPlayer.tsx` only plays MP4 (progressive download via `/api/v1/recordings/{id}/stream`), NOT HLS. Remove `import Hls from "hls.js"` and the `if (src.endsWith(".m3u8") && Hls.isSupported())` block. Do NOT add hls.js to RecordingPlayer.

**Files affected:** `services/web/src/components/recording/RecordingPlayer.tsx`

### 2. Chrome vs Safari video playback differences

Chrome is strict about:
- `Range: bytes=0-` → MUST return `206 Partial Content` (Safari accepts `200 OK`)
- `pix_fmt=yuvj420p` full-range color → rejects (Safari handles)
- CSP `unsafe-eval` → blocks (Safari ignores)

### 3. Recording codec normalization

**Problem:** Cameras may output HEVC or H.264 with `pix_fmt=yuvj420p color_range=pc`. Both cause Chrome playback failure.

**Fix in `services/recording-engine/app/recorder.py`:**
- HEVC → transcode to H.264: `-c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p`
- H.264 → apply bitstream filter: `-bsf:v h264_metadata=video_full_range_flag=0`
- Codec detected via ffprobe before FFmpeg command is built

### 4. HTTP Range request handling

**Problem:** Chrome sends `Range: bytes=0-` for video pre-flight. Returning `200 OK` causes Chrome to reject/drop the stream.

**Fix in `services/api/app/api/v1/recordings.py`:**
- Parse `Range` header via `_parse_range()`
- Check `is_full_range` (start==0, end==file_size-1)
- Full range → `200 OK` (progressive download, browser buffers as it streams)
- Partial range → `206 Partial Content` + `Content-Range` (seeking)

### 5. Stream endpoint must NOT use `Content-Disposition: inline`

`Content-Disposition: inline` on video responses interferes with browser playback. Only use `attachment` for `?download=true`.

### 6. `scalar_one_or_none()` returns a scalar — do NOT index it

**Symptom:** `resolve_storage_path()` returned `/` instead of `/data/recordings`. Recording engine logs show `storage_path_from_backend mount_point=/`.

**Root cause:** SQLAlchemy's `result.scalar_one_or_none()` returns the raw scalar value (e.g. the string `/data/recordings`). Code that does `row[0]` on that string gets the **first character** (`/`), not the whole value. This differs from `result.fetchall()` / `result.fetchone()` which return `Row` objects where `row[0]` is correct column access.

**Fix:** After `scalar_one_or_none()`, use the return value directly — no `[0]` indexing:
```python
row = result.scalar_one_or_none()
if row:
    return row  # NOT row[0]
```

**Files affected:** `services/recording-engine/app/config.py:82-84`

### 7. `_walk_segments` must handle non-camera directories

**Symptom:** Catalog loop crashes with `OSError` when `base` is `/` (root filesystem) or contains non-camera directories like `/proc`, `/sys`.

**Fix:** Wrap `os.makedirs` calls in try/except OSError. The catalog should gracefully skip directories where it cannot create date subdirectories.

**Files affected:** `services/recording-engine/app/catalog.py:215`

### 8. Missing `import os` in analytics.py

**Symptom:** `NameError: name 'os' is not defined` in analytics loop.

**Fix:** Add `import os` to imports.

**Files affected:** `services/recording-engine/app/analytics.py:16`
