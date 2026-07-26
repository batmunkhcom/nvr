# Latest Releases

> Auto-generated from CHANGELOG.md — updated on every docs/ push.

## v0.01.44-45 (2026-07-26)

- **IoU-based multi-object tracking** — per-class dedup replaced with Tracklet-based object tracking. Each object gets a unique `track_id`. IoU matching (threshold 0.3) links detections across frames. Moving objects: 15s cooldown. Stationary objects: 300s cooldown. Tracklet expiry: 5s unseen.
- **AI Pause** — AI engine respects `nvr:recording:paused` flag. When paused: no events written to DB, no snapshots saved, no counter plugin calls. MOG2 motion detection and YOLO inference continue (for heartbeat).
- **Events bulk delete** — `DELETE /api/v1/events/cleanup-by-date?before=YYYY-MM-DD&camera_id=uuid&dry_run=true`. Frontend modal with date picker, camera selector, preview count, and confirm delete. Snapshot files cleaned up.
- **Network alerts pagination** — Active alerts reduced from 50/page to 5/page.
- **Cross-Camera Tracking research** — `docs/wiki/Cross-Camera-Tracking.md` with Re-ID engine design, GPU (Tesla T4) plan, BGE-M3 analysis, 2D/3D options.

## v0.01.42 (2026-07-26)

- **Pause All** — global recording pause via round icon (green/red pulsating) in Topbar, admin password confirmation modal, stops ALL continuous + motion recorders. Stream viewing unaffected.
- **Per-camera recording toggle** — quick pause/resume button on each dashboard CameraTile. Remembers previous `recording_mode` via Redis, restores on unpause.
- **Recording engine pause check** — `_reconcile()` reads Redis `nvr:recording:paused` every 30s; `MotionRecorderController` checks before starting any motion recorder.
- **Dockerfile fixes** — `mqtt-bridge` COPY renames directory (hyphen→underscore), added PYTHONPATH. `recording-engine` and `ai-engine` Dockerfiles unified CMD to `app.main` + WORKDIR for standalone compatibility.

## v0.01.41 (2026-07-26)

- **Bounding box annotation on snapshots** — `frame_sampler._draw_boxes()` draws `cv2.rectangle` + `cv2.putText` labels on each detection before JPEG encode. Deterministic color per class (hash-based).
- **Cleanup command** — `python /app/cleanup.py --before YYYY-MM-DD [--dry-run]` deletes old events, `object_counters` rows, and associated snapshot files. Confirmation prompt before destructive action.

## v0.01.39-40 (2026-07-26)

- **Event snapshot fix** — `event.get("snapshot_path")` → `event.snapshot_path` (AttributeError was causing 500 → black square)
- **Event pagination** — 25 per page with prev/next navigation, page state management
- **Snapshot zoom** — thumbnail enlarged 96x56→160x96px, click-to-zoom fullscreen lightbox with Maximize2 icon, backdrop/Escape/X close, bottom caption

## v0.01.37-38 (2026-07-26)

- **Statistics page** — per-camera breakdown (`GET /counters/per-camera`), summary row with total objects + period, PerCameraGrid cards with per-category mini-counts
- **Counter SQL fix** — `params` dict was defined but never passed to `db.execute()` (all queries had empty params). Date arithmetic fixed by computing `start_date` in Python.
- **DB max_connections** — increased from 25 to 200 (was causing all services to fail when connection pool exhausted)

## v0.01.33-36 (2026-07-25–26)

- **Camera edit full-page** — Edit button now navigates to `/cameras/:cameraId/edit` (full page with route), `?edit=` param handles redirects from old dialog
- **Stream stability 5 fixes** — circuit breaker trip AFTER reconnect loop, transport fallback tcp→udp→http, HLS buffer relaxed (mediamtx 1s→2s segments, HLS.js 5→10s buffer), dashboard lazy loading (IntersectionObserver), retry exponential backoff 2-4-8-15s
- **Reconnect flags removal** (v0.01.35) — removed `-reconnect*` flags from FFmpeg (RTSP doesn't support them, caused "Option reconnect not found" crash)
- **AI plugin UI** — `ai_plugins: string[]` in Camera/CameraCreatePayload/CameraUpdatePayload, counter/lpr/smart_alerts checkboxes in CameraEditPage

## v0.01.21 (2026-07-25)

- **CSP fix — remove hls.js from RecordingPlayer** — `hls.js` uses `new Function()` which triggers CSP `script-src` block in Chrome (Chrome strict, Safari lenient). RecordingPlayer now uses native `<video>` progressive MP4 only.
- **HEVC→H.264 transcode** in recording engine — ffprobe auto-detects codec; HEVC streams transcoded with `libx264 ultrafast crf20 pix_fmt yuv420p`
- **H.264 bitstream filter** — normalizes `yuvj420p color_range=pc` → `yuv420p tv` via `-bsf:v h264_metadata=video_full_range_flag=0`
- **HTTP Range handling fix** — returns `200 OK` for full-file requests, `206 Partial Content` only for partial ranges (fixes Chrome rejection of full-range 206 responses)
- **RecordingPlayer cleanup** — removed complex spinner/playBlocked overlay, restored working `controls={controls}`, fixed `video.playbackRate` useEffect for speed controls
- **Recordings.tsx** — added `key={activePlaybackId}` to force clean remount on recording switch
- **AGENTS.md** — comprehensive Recording Playback troubleshooting section added (CSP, codec, Range, browser differences)

## v0.01.15 (2026-07-25)

- **AI FPS 2→0.5** — YOLO inference rate reduced (CPU: 166%→74%)
- **ONNX threads 2→1** — reduced thread contention
- **MOG2 sensitivity medium→low** on all 11 cameras — fewer frames reach YOLO
- **Sub-stream bitrate 2000k→1000k** — lighter FFmpeg encode
- **AI engine Docker CPU limit 4→2** — cgroup enforcement
- **cam3 AI disabled** — `recording_mode=never` camera no longer runs YOLO

## v0.01.14 (2026-07-25)

- **Fixed FFmpeg `-stimeout` → `-timeout`** — FFmpeg 5.1.9 doesn't support `-stimeout`, causing startup crashes every few seconds
- **Removed `-reconnect` flags** — not supported for RTSP in FFmpeg 5.1.9
- **Monitor loop**: `returncode=0` clean exits bypass circuit breaker, 5 quick reconnect attempts
- **Monitor loop**: `returncode≠0` errors get 3 attempts with transport fallback
- **HLS.js `maxBufferHole: 0.5`** — tighter gap tolerance

## v0.01.13 (2026-07-25)

## v0.01.12 (2026-07-25)

## v0.01.11 (2026-07-24)

- **Low-latency HLS** — 10-15s → 1-3s glass-to-glass (hlsVariant: lowLatency)
- **Audio enabled** in stream-manager FFmpeg relay (was `-an`)
- **Audio controls** in live view (mute/unmute)
- **Digital zoom** — 2D CSS zoom+pan on any stream
- **ONVIF PTZ** in modal (ExpandedView)

## v0.01.10 (2026-07-24)

- **Download recordings** (`?download=true` query param)
- **Playback speed controls** — 0.125x, 0.25x, 0.5x, 0.75x, 1x, 1.5x, 2x, 4x, 8x
- **Recording thumbnails** — auto-generated sidecar JPEG per segment via ffmpeg
- **Thumbnail resilience** — `-ss 2` fallback to `-ss 0` for short segments
- **Bulk delete** — by ID list, all per camera, or before date
- **Timeline click-to-play** — click time bar to jump to segment

## v0.01.09 (2026-07-24)

- **Motion-only recording** — FFmpeg starts on motion, stops after 30s idle
- **AI zone editor** — draw polygon zones on camera snapshot, apply to detections
- **Position-aware dedup** — static object: 1 event/5min, moved: immediate

## v0.01.08 (2026-07-24)

- **Recording engine** — per-camera FFmpeg supervisors, `-c:v copy`, 300s segments
- **Circular retention** — disk ≥85% or <2GB free → delete oldest first
- **Segment Catalog** — 60s scan registers closed segments in `recordings` table
- **Disk Analytics** — hourly GB/day per camera, capacity projection
- **AI engine** — YOLOv8n ONNX, MOG2 motion gate, correct post-processing

## v0.01.07 (2026-07-24)

- **Idle stream reaper** — 10min zero-readers → stop FFmpeg relay
