# AI Detection

## Overview

YOLOv8n ONNX object detection on camera sub-streams with MOG2 motion gating, zone filtering, and IoU-based multi-object tracking with parked-object protection.

---

## Pipeline

```
RTSP Sub-stream (0.5 FPS, 640px width)
            │
            ▼
┌───────────────────┐
│  FrameSampler       │  OpenCV cap.read()
│  per camera         │  cv2.CAP_PROP_BUFFERSIZE=1 (minimal latency)
└────────┬──────────┘
            │
            ▼
┌───────────────────┐
│  MOG2 Motion Gate │  history=500, detectShadows=False
│   (OpenCV)           │  countNonZero > 500 pixels → motion
│                     │  Threshold: low=40, med=25, high=16
└────────┬──────────┘
            │ motion detected
            ▼
┌───────────────────┐
│  YOLOv8n ONNX       │  Shared singleton session
│   (ONNX Runtime)     │  Intra-op threads: 1
│  INPUT_SIZE=640     │  CPUExecutionProvider
└────────┬──────────┘
            │
            ▼
┌───────────────────┐
│  Post-processing    │  Transpose (1,84,8400) → per-class argmax
│                     │  NMS (IoU=0.45), confidence clamp [0.05, 0.95]
│  Letterbox unscale│
└────────┬──────────┘
            │
            ▼
┌───────────────────┐
│  Zone Filter        │  cv2.pointPolygonTest on bbox bottom-center
│  Confidence check │  Only objects inside zones pass
└────────┬──────────┘
            │
            ▼
┌───────────────────┐
│  Position Dedup     │  Static object: person 5min, vehicle 30min
│                     │  Parked after 5 stationary frames → survives timeouts
│  Min event gap: 2s  │  Moved (>0.10 normalized): 15s cooldown
└────────┬──────────┘
            │
       ┌────┴────┐
       ▼           ▼
   Events     JPEG
   Table    Snapshot
         (with bounding
          boxes + labels)
```

### Bounding Box Annotation (v0.01.41)

Before saving the JPEG snapshot, `frame_sampler._draw_boxes()` renders detection metadata directly onto the frame:

- `cv2.rectangle()` — colored bounding box (2px stroke), deterministic color per class via hash
- `cv2.putText()` — label with class name + confidence score (e.g. `car 0.85`), white text on filled rectangle background
- Font: `FONT_HERSHEY_SIMPLEX` at 0.5 scale with `LINE_AA` anti-aliasing
- Image saved at JPEG quality 85 via `cv2.imencode()`

This means event snapshots in the Events page now show annotated bounding boxes for all detected objects.


---

## Per-Camera Configuration

| Config | Type | Description |
|--------|------|-------------|
| `ai_enabled` | boolean | Enable/disable AI detection per camera |
| `ai_objects` | JSON array | COCO classes to detect: `["person", "car", "truck", "bus", "motorcycle", "bicycle", ...]` (80 total) |
| `ai_zones` | JSON array | Polygon zones: `[{"name": "...", "points": [[x,y], ...]}]` — empty zones = whole frame |
| `ai_sensitivity` | string | MOG2 threshold: `low` (40), `medium` (25), `high` (16) |
| `ai_min_confidence` | float | Confidence threshold, clamped 0.05–0.95 |

---

## Performance Optimization (v0.01.15)

| Change | Before | After | Impact |
|--------|--------|-------|--------|
| AI FPS | 2 FPS | 0.5 FPS | CPU: 166% → 74% |
| ONNX threads | 2 | 1 | Reduced contention |
| MOG2 sensitivity | medium | low | Fewer frames reach YOLO |
| Sub-stream bitrate | 2000k | 1000k | Lighter FFmpeg encode |
| AI engine CPU limit | 4 cores | 2 cores | cgroup enforcement |

**Result:** Load avg 41→21 (-48%), AI RAM 955MB→565MB (-41%)

---

## Motion-Only Mode

Cameras with `recording_mode='motion'` and `ai_enabled=False` get a **motion-only sampler**:
- MOG2 gate only (no YOLO inference)
- Publishes motion state to Redis `nvr:motion`
- Recording Engine's `MotionRecorderController` starts/stops FFmpeg based on motion state
- Motion active → start recorder; motion inactive 30s → stop recorder

---

## Worker Lifecycle

- **Reconcile interval:** 15s (`POLL_INTERVAL`)
- Config change detection: zones, objects, stream URI changes trigger worker recreation within 15s
- Model: `yolov8n.onnx` in `ai_models` volume at `/app/models` (exported on host via ultralytics)

---

## IoU-Based Multi-Object Tracking (v0.01.44 → v0.01.53)

Per-class dedup replaced with per-object Tracklet tracking. Each detected object gets a unique `track_id` and is tracked independently across frames.

v0.01.53 adds **parked-object protection** to prevent repeated detection of stationary cars/bikes that get re-detected every time MOG2 wakes up.

### Architecture

```
Detections (per frame, 0.5 FPS)
        │
        ▼
┌─────────────────────────────────┐
│  IoU Matching                    │
│  → for each existing Tracklet:   │
│    find best match by IoU>0.3    │
│  → unmatched: new Tracklet       │
│  → matched: update position      │
└──────────────┬──────────────────┘
               │
        ┌──────┴──────┐
        ▼              ▼
   Existing        New Object
   Tracklet        → Tracklet created
   → check move    → event fired immediately
   → check parked
   → check cooldown
        │
   ┌────┴────┐
   ▼         ▼
 Moved     Stationary
 15s gap   person: 5min / vehicle: 30min
           After 5 frames → parked → survives timeout
```

### Tracklet Data Structure

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Unique id: `car_0_12345` |
| `cls` | str | COCO class name |
| `bbox` | (x1,y1,x2,y2) | Last known bounding box |
| `last_event_ts` | float | Last time an event was fired |
| `last_seen_ts` | float | Last time object was detected |
| `last_cx`, `last_cy` | float | Normalised centre for movement detection |
| `stationary_count` | int | Consecutive frames without movement |
| `is_parked` | bool | True after STATIONARY_HYSTERESIS (5) frames — exempt from timeout |

### Tracking Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `IOU_MATCH_THRESHOLD` | 0.30 | Minimum IoU to match same object |
| `TRACKLET_TIMEOUT_S` | 120.0 | Unseen objects expire after 2 min (was 5s) |
| `MOVING_COOLDOWN_S` | 15.0 | Moving objects: max 1 event/15s |
| `PERSON_STATIC_COOLDOWN_S` | 300.0 | Stationary people: max 1 event/5min |
| `VEHICLE_STATIC_COOLDOWN_S` | 1800.0 | Stationary vehicles: max 1 event/30min |
| `MIN_EVENT_GAP_S` | 2.0 | Absolute minimum between any events |
| `POSITION_TOLERANCE` | 0.10 | Normalised centre movement threshold |
| `STATIONARY_HYSTERESIS` | 5 | Consecutive frames before parked state |

### Parked-Object Protection (v0.01.53)

The root cause of repeated detections: when MOG2 settles (no motion), YOLO stops running. After the old 5s timeout, tracklets expired. When any motion triggered YOLO again, stationary objects were treated as NEW — firing events.

**Fix:** Three layers of protection:

1. **Timeout lengthened:** 5s → 120s — tracklet survives MOG2 silence
2. **Parked state:** After 5 consecutive stationary frames, `is_parked=True`. Parked tracklets are **exempt from timeout** — they survive indefinitely
3. **Per-class cooldowns:** Vehicles get 30-minute static cooldown vs 5-minute for people. A parked car fires at most 1 event per half hour

### Before vs After

| Scenario | Before (v0.01.44) | After (v0.01.53) |
|----------|-------------------|-------------------|
| Moving car | 1 event (15s cooldown) | Same |
| Two cars simultaneously | 2 separate events | Same |
| Parked car (MOG2 silence → motion triggers YOLO) | NEW event every time | Tracklet survives → NO new event |
| Parked car (30 min) | Could fire every 5 min | 1 event per 30 min max |
| Parked bike (2 hours) | Re-detected repeatedly | 1 event per 30 min if visible |
| Person exiting + re-entering | New tracklet → event | Same |

### Event Format Change

Events `metadata.objects` changed from `{class: confidence}` dict to list format:
```json
// Before
{"objects": {"car": 0.85, "person": 0.72}}

// After (v0.01.44+)
{"objects": [
  {"class": "car", "confidence": 0.85, "track_id": "car_0_45231", "box": [120, 80, 380, 260]},
  {"class": "person", "confidence": 0.72, "track_id": "person_1_45231", "box": [400, 50, 600, 350]}
]}
```

Frontend `Events.tsx` handles both formats for backward compatibility.

### Pause All Integration (v0.01.45)

When `nvr:recording:paused` is `true`, the AI engine:
- Skips `_persist()` — no events written to DB, no snapshots saved
- Skips plugin calls — object counter, smart alerts, LPR paused
- Keeps MOG2 motion detection and YOLO inference active (for motion heartbeat)
- Tracking continues internally but events are not fired

---

## AI Plugin System

### Object Counter Plugin

Real-time object counting plugin (`services/ai-engine/app/plugins/counter.py`):

| Category | COCO Classes |
|----------|-------------|
| **person** | person |
| **vehicle** | car, motorcycle, bus, truck, bicycle |
| **animal** | bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe |
| **livestock** | cow, horse, sheep |

- **Dedup:** 5 second cooldown between counting the same object class on the same camera
- **Flush:** Counts synced to `object_counters` table every 60 seconds
- **Hourly aggregation:** Per-camera, per-category hourly totals via counter service SQL queries
- **Per-camera breakdown:** `GET /api/v1/counters/per-camera` — returns per-camera totals with category mini-counts (shown on Statistics page)
- **Summary views:** `GET /api/v1/counters/summary` (?camera_id=&days=7), `GET /api/v1/counters/hourly` (?camera_id=&date=YYYY-MM-DD)
- Plugins receive ALL visible detections (pre-cooldown) via `plugin.on_detection()`, called before `_apply_cooldown()` in the FrameSampler pipeline

### License Plate Recognition (LPR)

EasyOCR-based plate detection with 8 country pattern library. Plates matched against regex patterns for Монгол, Европ, АНУ, Япон, Хятад, Орос, Солонгос + custom regex.

---

## Event Output

- **Events table:** Plain SQL insert with metadata JSON `{objects: [{class, confidence, box}], ...}`
- **JPEG snapshots:** Saved to `/data/recordings/snapshots/` with token auth, bounding boxes + labels drawn on image
- **Redis pub/sub:** `nvr:events` channel for real-time broadcast
