# AGENTS.md — mBm NVR System

## Docker Networking

- All services use Docker compose networks (`nvr-net`), NOT `network_mode: host`.
- **Container hostnames** (not IPs or `host.docker.internal`) for inter-service communication:
  - `nvr-db` (PostgreSQL), `nvr-redis`, `nvr-minio`
  - `nvr-stream-manager:8001`, `nvr-mediamtx:8554/8888/9997`
  - `nvr-api:8000`, `nvr-web:3000`
- Port mappings required for host access: `8000`, `3000`, `8888`, `8554`, `9997`, `8001`

## FFmpeg Transcoding

- Always use `libx264` with `-preset ultrafast -tune zerolatency -g 15 -b:v 2000k -maxrate 2000k -bufsize 4000k`.
- Never use `-c:v copy` — H.264 FU-A packet ordering issues from cameras cause MediaMTX HLS errors.
- Output: `rtsp://nvr-mediamtx:8554/{camera_id}` or `{camera_id}_sub`.

## Frontend Stream Playback — useStreamPlayer Hook

**All video playback MUST use the shared `useStreamPlayer` hook** (`src/hooks/useStreamPlayer.ts`):

```ts
import { useStreamPlayer, type StreamType } from "../hooks/useStreamPlayer";
const { state, retrySec, attachVideo, startStream } = useStreamPlayer({
  cameraId,           // UUID string
  streamType,         // "main" | "sub"
  pollAttempts,       // optional, default 30
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
3. Stream-manager starts FFmpeg with libx264 transcode → pushes to MediaMTX
4. MediaMTX creates HLS at `rtsp://nvr-mediamtx:8554/{cid}`
5. Frontend polls `/hls/{cid}/index.m3u8` then initializes HLS.js
6. Circuit breaker prevents rapid restarts (30-60s cooldown)
7. **Idle reaper**: stream-manager stops relays with zero MediaMTX readers for 10 min (`STREAM_IDLE_TIMEOUT_S`) — saves CPU when nobody watches
8. MediaMTX has NO hot reload — SIGHUP terminates it; restart via compose

## Recording Lifecycle (recording-engine)

1. Per-camera FFmpeg supervisor: sub-stream RTSP → `-c:v copy` → 300s MP4 segments at `/data/recordings/{cid}/YYYY/MM/DD/`
2. `SegmentCatalog` (60s): registers closed segments in `recordings` table (ffprobe duration)
3. **Circular retention** (5 min loop): when disk ≥ `storage.max_usage_percent` (85%) or free < `storage.min_free_gb` (2GB) → oldest segments deleted first — disk can never fill up. Age limit: `retention.default_days` (7). Files < 10 min old protected.
4. `DiskAnalytics` (hourly): GB/day per camera + days-fit projection → `system_config` key `storage.analysis` → shown on Storage page
5. Env: uses `POSTGRES_*` vars + `NVR_ENCRYPTION_KEY` (AES-256-GCM via `nvr_common.security`)
6. `recording_mode`: continuous/motion record; `never`/`disabled` skip

## AI Detection Lifecycle (ai-engine)

1. `FrameSampler` per camera: RTSP sub-stream at 2fps → MOG2 motion gate → shared YOLOv8n ONNX session
2. Detections filtered by `ai_objects`, `ai_min_confidence` (clamped 0.05–0.95), and `ai_zones` polygons (bottom-center of bbox must be inside a zone; empty zones = whole frame)
3. **Position-aware dedup**: static object = 1 event per 5 min; moved object = immediate event
4. Events → `events` table (plain SQL) + JPEG snapshot at `/data/recordings/snapshots/` + Redis pub
5. Model: `yolov8n.onnx` in `ai_models` volume at `/app/models` (exported on host via ultralytics, not in image)
6. Media auth: `<img>/<video>` use `?token=` query param (get_current_user accepts it)
7. **Motion publishing**: every sampler publishes motion state to Redis `nvr:motion` (on change + 30s heartbeat). Workers are also created for `recording_mode='motion'` cameras with AI disabled (motion-only mode, no YOLO)
8. Worker config signature: any camera config change (zones/objects/stream) recreates the worker within 15s

## Motion-Only Recording (recording_mode='motion')

1. AI engine publishes `{camera_id, active}` to Redis `nvr:motion`
2. `MotionRecorderController` (recording-engine): motion active → start `CameraRecorder`; motion inactive → stop after `recording.motion_stop_delay_s` (30s); new motion cancels the pending stop
3. Motion recorders live in a separate registry from continuous recorders (no reconcile conflicts)
4. Segments are marked `recording_type='motion'` by the catalog based on camera mode

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
