# Recording Engine

## Overview

Per-camera FFmpeg supervisors with `-c:v copy` (zero video CPU), circular retention, segment catalog, and disk analytics.

---

## Components

### CameraRecorder (Per-Camera FFmpeg Supervisor)

- Spawns FFmpeg to record RTSP sub-stream → 300s MP4 segments
- Auto-restart on failure with circuit breaker (60s→600s cooldown)
- Codec normalization via ffprobe before FFmpeg spawns:
    - HEVC → `-c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p`
    - H.264 → `-bsf:v h264_metadata=video_full_range_flag=0` (normalizes `yuvj420p color_range=pc` → `yuv420p tv`)
- Motion-only mode: FFmpeg starts/stops based on Redis `nvr:motion` state

### SegmentCatalog (60s interval)

- Scans `/data/recordings/{camera_id}/YYYY/MM/DD/` for closed segments
- Runs ffprobe to get duration, codec, resolution
- Registers segments in `recordings` table
- Segments marked `recording_type='motion'` or `'continuous'` based on camera mode

### CircularRetention (5 min interval)

**Triggers:**
- Disk usage ≥ `storage.max_usage_percent` (85%)
- Free space < `storage.min_free_gb` (2GB)

**Behavior:**
- Delete oldest segments first (files < 10 min old protected)
- Max 500 deletions per run (I/O storm prevention)
- DB rows for deleted files cleaned up
- Disk can never fill up

### DiskAnalytics (hourly)

- Calculates GB/day per camera
- Projects days-fit based on current rate
- Stores in `system_config` key `storage.analysis`
- Shown on Storage page UI

---

## Recording Modes

| Mode | Behavior |
|------|----------|
| `continuous` | FFmpeg runs 24/7, 300s segments |
| `motion` | FFmpeg starts on motion, stops after 30s idle (`recording.motion_stop_delay_s`) |
| `never` / `disabled` | Skip recording entirely |

### Pause All (v0.01.42)

Global recording pause via Redis-backed flag that stops ALL recording (continuous + motion) while leaving live streaming unaffected.

**State storage:** Redis key `nvr:recording:paused` — set to `"true"` (paused) or `"false"` (active) by the API.

**Reconcile check** (`_reconcile()` in `main.py`):
- Reads Redis `nvr:recording:paused` at start of every reconcile cycle (30s interval)
- When paused: stops all `_recorders` (continuous) and `_motion_controller.recorders` (motion), then returns early (no new recorders started)
- When unpaused: normal reconcile logic resumes, recorders created on next cycle

**Motion controller guard** (`MotionRecorderController.handle_event()` in `motion.py`):
- Checks Redis `nvr:recording:paused` before processing any motion events
- When paused: all motion events are silently ignored — no new recorders spawn
- When unpaused: normal motion-triggered start/stop behavior resumes

**API endpoints:**
- `POST /api/v1/system/recording/pause` — sets Redis key, requires admin password confirmation
- `POST /api/v1/system/recording/resume` — clears Redis key, requires admin password confirmation
- `GET /api/v1/system/recording/status` — returns `{paused: bool}`, no auth needed

**Per-camera toggle** (`POST /api/v1/cameras/{id}/recording/toggle`):
- Current mode → saved to Redis `camera:pause:{camera_id}`, then set to `disabled`
- On unpause → previous mode restored from Redis (defaults to `continuous` if no saved state)
- Operator+ access, no password needed

---

## Configuration Keys

| Key | Default | Description |
|-----|---------|-------------|
| `recording.segment_seconds` | `300` | MP4 segment duration |
| `recording.stream` | `sub` | Which stream to record (sub/main) |
| `recording.motion_stop_delay_s` | `30` | Idle seconds before stopping motion recorder |
| `retention.default_days` | `7` | Age-based deletion threshold |
| `storage.max_usage_percent` | `85` | Disk % at which circular cleanup triggers |
| `storage.min_free_gb` | `2` | Free GB floor for circular cleanup |

---

## File Structure

```
/data/recordings/
├── {camera_id}/
│    ├── YYYY/
│    │    └── MM/
│    │         └── DD/
│    │              └── YYYYMMDD_HHMMSS.mp4   # 300s segments
│    ├── snapshots/                            # AI detection JPEGs
│    └── {camera_id}_YYYYMMDD_HHMMSS.jpg       # Thumbnails (sidecar)
```

---

## Key Technical Notes

1. **`-c:v copy`** — no video transcode (very low CPU) since recording writes to disk directly
2. **`+faststart`** — enables seeking before download complete
3. **`-strftime 1`** — segments named with timestamps for easy cataloging
4. **Circuit breaker** — 60s→600s cooldown (`min(60 × 2^trips, 600)`)
5. **`returncode=0`** (clean exit) → breaker NOT tripped, immediate reconnect up to 5 attempts
