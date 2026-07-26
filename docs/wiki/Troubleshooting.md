# Troubleshooting

## 1. CSP Blocks hls.js in RecordingPlayer (Chrome)

**Symptom:** Recordings page shows spinner forever, no errors in console (Chrome). Works in Safari.

**Root cause:** `hls.js` uses `new Function()` internally. CSP `script-src` blocks `unsafe-eval`. Chrome enforces CSP strictly; Safari doesn't.

**Fix:** RecordingPlayer only plays MP4 (progressive download via `/api/v1/recordings/{id}/stream`), NOT HLS. No hls.js in RecordingPlayer. Do NOT add hls.js to RecordingPlayer.

---

## 2. Chrome vs Safari Video Playback Differences

Chrome is strict about:
- `Range: bytes=0-` → MUST return `206 Partial Content` (Safari accepts `200 OK`)
- `pix_fmt=yuvj420p` full-range color → rejects (Safari handles)
- CSP `unsafe-eval` → blocks (Safari ignores)

---

## 3. Recording Codec Normalization

**Problem:** Cameras may output HEVC or H.264 with `pix_fmt=yuvj420p color_range=pc`. Both cause Chrome playback failure.

**Fix in recording engine:**
- HEVC → transcode to H.264: `-c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p`
- H.264 → apply bitstream filter: `-bsf:v h264_metadata=video_full_range_flag=0`
- Codec detected via ffprobe before FFmpeg command is built

---

## 4. HTTP Range Request Handling

**Problem:** Chrome sends `Range: bytes=0-` for video pre-flight. Returning `200 OK` causes Chrome to reject/drop the stream.

**Fix in recordings endpoint:**
- Parse `Range` header via `_parse_range()`
- Check `is_full_range` (start==0, end==file_size-1)
- Full range → `200 OK` (progressive download, browser buffers as it streams)
- Partial range → `206 Partial Content` + `Content-Range` (seeking)

---

## 5. Stream Endpoint Content-Disposition

`Content-Disposition: inline` on video responses interferes with browser playback. Only use `attachment` for `?download=true`.

---

## 6. FFmpeg Startup Crashes (HLS Stability)

**Problem:** FFmpeg crashes every few seconds on stream relay startup.

**Fix (v0.01.14):**
- `-stimeout` → `-timeout` (FFmpeg 5.1.9 doesn't support `-stimeout`)
- Removed `-reconnect` flags (not supported for RTSP in FFmpeg 5.1.9)
- Monitor loop: `returncode=0` clean exits bypass circuit breaker, 5 quick reconnect attempts
- Monitor loop: `returncode≠0` errors get 3 attempts with transport fallback

---

## 7. Stream Relay Lifecycle

1. Frontend calls `POST /api/v1/cameras/{id}/live/start?stream=main|sub`
2. `live_relay.py` checks stream-manager status first, then delegates
3. Stream-manager starts FFmpeg with libx264 transcode → pushes to MediaMTX
4. MediaMTX creates HLS at `rtsp://nvr-mediamtx:8554/{camera_id}`
5. Frontend polls `/hls/{cid}/index.m3u8` then initializes HLS.js
6. Circuit breaker prevents rapid restarts (15s→120s cooldown for stream relay)
7. **Idle reaper**: stream-manager stops relays with zero MediaMTX readers for 10 min (`STREAM_IDLE_TIMEOUT_S`)

---

## 8. High CPU / Load Issues

**Symptom:** Server load avg > 30, AI RAM > 900MB

**Fix (v0.01.15):**
- Reduce AI FPS from 2 to 0.5
- Reduce ONNX threads from 2 to 1
- Lower MOG2 sensitivity from medium to low
- Reduce sub-stream bitrate from 2000k to 1000k
- Limit AI engine Docker CPU to 2 cores

**Result:** Load avg 41→21 (-48%), AI RAM 955MB→565MB (-41%)

---

## Quick Reference: Key Files

| File | Purpose |
|------|---------|
| `services/stream-manager/app/manager.py` | FFmpeg process lifecycle, circuit breaker, idle reaper |
| `services/stream-manager/app/relay_api.py` | HTTP API for relay start/stop/status |
| `services/api/app/services/live_relay.py` | Stream relay delegation to stream-manager |
| `services/recording-engine/app/main.py` | Recording loops (reconcile/catalog/retention/analytics) |
| `services/recording-engine/app/recorder.py` | Per-camera FFmpeg supervisor with auto-restart |
| `services/recording-engine/app/catalog.py` | Segment→DB registration + sync |
| `services/recording-engine/app/retention.py` | Circular + age-based cleanup |
| `services/ai-engine/app/main.py` | AI worker reconcile loop |
| `services/ai-engine/app/detector.py` | YOLOv8 ONNX post-processing + NMS |
| `services/ai-engine/app/frame_sampler.py` | Motion gate + dedup + event persist |

---

## 9. mqtt-bridge Crash on Startup

**Symptom:** `nvr-mqtt-bridge` container exits immediately with `ModuleNotFoundError: No module named 'services.mqtt_bridge'`.

**Root cause:** Dockerfile copies host directory `services/mqtt-bridge/` (with hyphen) but Python module import expects `services.mqtt_bridge` (with underscore). Hyphen is not a valid Python identifier for module names.

**Fix (v0.01.42):**
- Dockerfile `COPY` renames directory: `services/mqtt-bridge/ → ./services/mqtt_bridge/`
- Added `ENV PYTHONPATH=/app:/app/packages/common`
- Same fix applied to `recording-engine` and `ai-engine` Dockerfiles (unified CMD to `app.main` + explicit WORKDIR/PYTHONPATH)

---

## 10. Recording Not Resuming After Pause

**Symptom:** After using Pause All or per-camera pause, recordings don't resume when unpausing.

**Checklist:**
1. Verify Redis key: `docker compose exec nvr-redis redis-cli GET nvr:recording:paused` — should return `"false"` or `(nil)`
2. Check recording engine logs: `docker compose logs nvr-recording-engine --tail 50` — look for `recorder_added` messages (continuous) or `motion_recording_started` (motion)
3. The reconcile loop runs every 30 seconds — wait at least 35s after unpausing
4. For per-camera pause: verify `recording_mode` in DB: `SELECT recording_mode FROM cameras WHERE id='...'` — should NOT be `'disabled'`
5. Verify Redis stores previous mode for per-camera: `docker compose exec nvr-redis redis-cli GET camera:pause:{camera_id}`

---

## 11. Event Snapshot Shows Blank/Black

**Symptom:** Events page shows black rectangles instead of snapshot images.

**Possible causes:**
1. `camera_id` or `snapshot_path` mismatch in DB — verify `SELECT camera_id, snapshot_path FROM events WHERE ...`
2. File not found on disk — check `/data/recordings/snapshots/` in the API container
3. Token/auth issue — snapshots use `?token=` query param; verify JWT is valid

**Fix history (v0.01.39):** Was using `event.get("snapshot_path")` (dict access) instead of `event.snapshot_path` (attribute access) — returned None → 500 error → black square. Fixed to use attribute access.

---

## 12. Per-Camera Pause Not Working

**Symptom:** Clicking the per-camera pause button on a dashboard tile doesn't stop recording.

**Checklist:**
1. Verify the request succeeded: check browser DevTools → Network → look for `POST /api/v1/cameras/{id}/recording/toggle` → response should have `recording_mode: "disabled"`
2. Check DB: `SELECT id, name, recording_mode FROM cameras WHERE id='...'` — should show `disabled`
3. Wait for recording engine reconcile (30s max) — continuous recorders stop on next reconcile cycle
4. For motion cameras: recent motion events may still trigger recording — check `nvr-redis redis-cli GET nvr:recording:paused` isn't blocking the toggle
5. Verify operator+ role: endpoint requires `require_operator` (admin or operator role)
