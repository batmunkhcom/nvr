"""Frame sampler — RTSP sub-stream reader with motion gate + YOLO detection.

A dedicated drainer thread continuously reads the RTSP stream and keeps only
the freshest frame — sampling never lags behind real time, and a half-dead
TCP connection is detected via frame staleness (STALE_FRAME_S).

Frames are gated on MOG2 motion, the shared ONNX detector runs off the event
loop, two-stage tracking (strict IoU+distance, then relaxed centre-distance
fallback for fast-moving objects) applies moving/stationary cooldowns with a
per-class event-gap backstop, events + JPEG snapshots are persisted, and
state is broadcast over Redis.

Tracking (v4): two-stage IoU + centre-distance matching. Moving objects fire
events every MOVING_COOLDOWN_S (15s); stationary objects: persons every 5 min,
vehicles every 20 min. After 5 consecutive stationary frames the tracklet is
'parked' and survives timeouts indefinitely, preventing re-detection of
parked cars/bikes. Tracklets expire after TRACKLET_TIMEOUT_S (300s) if not
parked. New tracklets always fire — throttled only by CLASS_EVENT_GAP_S.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlparse, urlunparse
from zoneinfo import ZoneInfo

import numpy as np
import structlog

from . import db
from .detector import AIDetector, MotionDetector

logger = structlog.get_logger()

# Sample rate per camera. Configurable via system_config ai.target_fps (3.0 default),
# per-camera override via FrameSampler constructor. Inference cost scales linearly.
RECONNECT_BASE_S = 5
RECONNECT_MAX_S = 120
DEFAULT_OBJECTS = ["person", "car", "truck", "bus", "motorcycle", "bicycle", "dog", "cat", "bird"]
MOTION_CHANNEL = "nvr:motion"
MOTION_OFF_S = 30.0
MOTION_HEARTBEAT_S = 30.0
MOTION_COOLDOWN_S = 10.0   # re-arm delay — MUST stay below the recorder stop delay (30s)
MOTION_ARM_FRAMES = 1      # consecutive motion frames before going active
MOTION_WARMUP_FRAMES = 1   # frames suppressed after (re)connect while MOG2 learns
STALE_FRAME_S = 15.0       # no fresh frame this long => capture is half-dead => reconnect

# Detection frame width. High-resolution sub-streams are downscaled to this
# width before inference. 1280 keeps far more detail than the old 640 default,
# which severely hurt small / distant object recall. Can be lowered on CPU-bound
# hosts via AI_FRAME_WIDTH.
FRAME_WIDTH = int(os.environ.get("AI_FRAME_WIDTH", "1280") or "1280")

# ── IoU tracking constants ──
IOU_MATCH_THRESHOLD = 0.30          # IoU > this → same tracked object
FALLBACK_CENTRE_DISTANCE = 0.12     # centre-distance match for fast movers; tight enough to avoid cross-traffic mismatches at 1 FPS
TRACKLET_TIMEOUT_S = 300.0          # unseen this long → remove tracklet (5 min)
MOVING_COOLDOWN_S = 15.0            # moving object: at most 1 event per N seconds
PERSON_STATIC_COOLDOWN_S = 300.0    # stationary person/animal: 5 min
VEHICLE_STATIC_COOLDOWN_S = 300.0   # stationary vehicle: 5 min
MIN_EVENT_GAP_S = 2.0                # absolute minimum gap between any two events
CLASS_EVENT_GAP_S = 5.0              # global per-class event throttle (anti-spam backstop)
POSITION_TOLERANCE = 0.05            # normalized centre movement threshold (speed-bump traffic is slow; 0.02 marked slow cars as stationary)
STATIONARY_HYSTERESIS = 999999       # parked-tracklet logic disabled per user request — passing cars must keep firing
PARKED_MOVED_EXPIRY_S = 10.0         # kept for compatibility; no tracklets become parked
MAX_CENTRE_DISTANCE = 0.15           # IoU + centre distance diff → treat as same object
MAX_TRACKLETS = int(os.environ.get("AI_MAX_TRACKLETS", "64") or "64")  # hard cap per camera (bounds the match loop)

# ── Object category mapping (used by both counter and event metadata) ──
MIN_COUNTER_GAP_S = 2.0              # max 1 counter upsert per category every N seconds
CATEGORY_MAP: dict[str, list[str]] = {
     "person": ["person"],
     "vehicle": ["car", "truck", "bus", "motorcycle", "bicycle"],
     "animal": ["cat", "dog", "bird"],
     "livestock": ["horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"],
}


def _classify_object(cls: str) -> str | None:
    for category, classes in CATEGORY_MAP.items():
        if cls in classes:
            return category
    return None

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle"}


def _same_detection_category(cls_a: str, cls_b: str) -> bool:
    """Return True if two YOLO class labels belong in the same category
    for purposes of cross-class parked-tracklet inheritance (e.g. a
    parked 'bus' hand-over to a 'car' detection at the same position).
    Cross-category inheritance ('person' → 'car') is NOT allowed — a
    false-positive parked person must not block vehicle detections."""
    return cls_a == cls_b or (cls_a in VEHICLE_CLASSES and cls_b in VEHICLE_CLASSES)


@dataclass
class Tracklet:
    """A tracked object instance (per camera).

    Matched across frames via IoU.  One camera can hold multiple tracklets
    of the same class (e.g. two cars visible simultaneously).
    """

    id: str
    cls: str
    bbox: tuple[int, int, int, int]
    last_event_ts: float
    last_seen_ts: float
    last_cx: float = 0.0
    last_cy: float = 0.0
    stationary_count: int = 0
    is_parked: bool = False
    moved_from_parked_at: float = 0.0


def compute_iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    """Intersection-over-Union between two bounding boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


RECORDING_PAUSE_KEY = "nvr:recording:paused"


async def _check_paused() -> bool:
    """Check the global recording pause flag in Redis."""
    try:
        redis = await db.get_redis()
        val = await redis.get(RECORDING_PAUSE_KEY)
        return val == "true"
    except Exception:
        return False


def build_rtsp_url(stream_uri: str, username: str | None, password: str | None) -> str:
    if not username or not password or not stream_uri.startswith("rtsp://"):
        return stream_uri
    parsed = urlparse(stream_uri)
    if parsed.username:
        return stream_uri
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


class _LatestFrameReader:
    """Background thread that drains an RTSP capture, keeping the freshest frame.

    OpenCV's FFmpeg backend buffers frames internally, so a 1 FPS consumer of
    a 5-15 FPS stream would otherwise read increasingly stale frames until
    the server kicks the slow reader. The drainer also converts a silently
    hung TCP session into a detectable failure (stale timestamp / read EOF).
    """

    def __init__(self, url: str, cv2) -> None:
        self._url = url
        self._cv2 = cv2
        self._cap = None
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_frame_ts = 0.0
        self.failed = False

    def start(self) -> bool:
        cap = self._cv2.VideoCapture(self._url, self._cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            return False
        self._cap = cap
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ret, frame = self._cap.read()
            except Exception:
                ret, frame = False, None
            if not ret or frame is None:
                self.failed = True
                return
            with self._lock:
                self._frame = frame
                self.last_frame_ts = time.time()

    def read(self) -> np.ndarray | None:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def release(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._cap is not None:
            self._cap.release()


class FrameSampler:
    def __init__(
        self,
        camera_id: str,
        camera_name: str,
        stream_uri: str,
        username: str | None,
        password: str | None,
        ai_objects: list[str] | None,
        ai_sensitivity: str | None,
        ai_min_confidence: float | None,
        ai_zones: list | None = None,
        motion_only: bool = False,
        event_callback=None,
        plugins: list | None = None,
        storage_path: str | None = None,
        on_capture_failed=None,
        target_fps: float = 3.0,
        tz: ZoneInfo | None = None,
    ):
        self._tz = tz or ZoneInfo("Asia/Ulaanbaatar")
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.stream_url = build_rtsp_url(stream_uri, username, password)
        self.ai_objects = set(ai_objects or DEFAULT_OBJECTS)
        # Default confidence: per-camera DB value first, then AI_CONFIDENCE_THRESHOLD
        # env var, then a lower 0.3 fallback so small / distant objects are kept.
        # Lower bound 0.05 prevents runaway false positives if the value is missing.
        default_conf = float(os.environ.get("AI_CONFIDENCE_THRESHOLD", "0.25") or "0.25")
        self.ai_min_confidence = min(max(ai_min_confidence or default_conf, 0.05), 0.95)
        self.ai_zones = [z for z in (ai_zones or []) if len(z.get("points", [])) >= 3]
        self.motion_only = motion_only
        self.plugins = plugins or []
        self.storage_path = storage_path or os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings")

        self._detector = AIDetector.shared()
        self._motion = MotionDetector(sensitivity=ai_sensitivity or "medium")
        self._event_callback = event_callback
        self._on_capture_failed = on_capture_failed
        self.target_fps = float(target_fps)
        self._running = False
        self._tracklets: list[Tracklet] = []
        self._task: asyncio.Task | None = None
        self._motion_active = False
        self._last_motion_ts = 0.0
        self._last_motion_pub_ts = 0.0
        self._motion_consecutive = 0
        self._motion_last_stop_ts = 0.0
        self._frames_since_connect = 0
        self._last_counter_ts: dict[str, float] = {}
        # Image-based dedup: compare consecutive snapshots to detect
        # parked/stationary objects that haven't moved.  A near-identical
        # frame means the same scene → suppress the event.
        self._last_thumb: np.ndarray | None = None
        self._last_event_thumb_ts: float = 0.0
        self._dup_suppress_count: int = 0

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("frame_sampler_started", camera=self.camera_name)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("frame_sampler_stopped", camera=self.camera_name)

    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        import cv2

        # Socket-level read timeout so a half-dead RTSP session fails instead
        # of blocking cap.read() forever. Set once at startup. 15s covers
        # MediaMTX on-demand cold pulls (camera handshake can exceed 10s).
        # NOTE: OpenCV separates capture options with '|' (not ';').
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;15000000"

        backoff = RECONNECT_BASE_S
        while self._running:
            reader = await asyncio.to_thread(self._open_reader, cv2)
            if reader is None:
                logger.warning(
                    "frame_sampler_open_failed",
                    camera=self.camera_name,
                    retry_s=backoff,
                )
                if self._on_capture_failed:
                    await self._on_capture_failed()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX_S)
                continue

            backoff = RECONNECT_BASE_S
            self._frames_since_connect = 0
            self._last_thumb = None  # reset snapshot dedup on reconnect
            self._dup_suppress_count = 0
            logger.info("frame_sampler_connected", camera=self.camera_name)
            try:
                await self._consume(reader, cv2)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("frame_sampler_error", camera=self.camera_name, exc_info=True)
            finally:
                await asyncio.to_thread(reader.release)

    def _open_reader(self, cv2) -> _LatestFrameReader | None:
        reader = _LatestFrameReader(self.stream_url, cv2)
        return reader if reader.start() else None

    async def _consume(self, reader: _LatestFrameReader, cv2) -> None:
        frame_interval = 1.0 / self.target_fps
        while self._running:
            started = asyncio.get_running_loop().time()
            if reader.failed or (
                reader.last_frame_ts > 0
                and time.time() - reader.last_frame_ts > STALE_FRAME_S
            ):
                logger.warning("frame_sampler_stream_lost", camera=self.camera_name)
                if self._on_capture_failed:
                    await self._on_capture_failed()
                return  # trigger reconnect
            frame = await asyncio.to_thread(reader.read)
            if frame is None:
                # reader thread hasn't delivered the first frame yet
                await asyncio.sleep(0.2)
                continue

            self._frames_since_connect += 1
            frame = cv2.resize(
                frame, (FRAME_WIDTH, int(frame.shape[0] * FRAME_WIDTH / frame.shape[1]))
            )
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
            has_motion = self._motion.detect(gray)
            await self._track_motion(has_motion)

            # Periodic motion-gate stats (every ~60 frames ≈ 20s at 3 FPS)
            # so we can see MOG2 pass/reject rates and foreground pixel counts
            # for this specific camera view.  Logs regardless of has_motion.
            fc = self._frames_since_connect
            if fc % 60 == 0:
                logger.info(
                    "motion_gate_stats",
                    camera=self.camera_name,
                    fg_pixels=self._motion.last_fg_pixels,
                    fg_ratio=round(self._motion.last_fg_ratio, 4),
                    has_motion=has_motion,
                    frame_size=f"{frame.shape[1]}x{frame.shape[0]}",
                    frame_num=fc,
                )

            if not has_motion:
                await asyncio.sleep(frame_interval)
                continue

            if self.motion_only:
                await asyncio.sleep(frame_interval)
                continue

            detections = await asyncio.to_thread(
                self._detector.detect, frame, self.ai_min_confidence
            )
            detections = [
                d
                for d in detections
                if d["class"] in self.ai_objects and d["confidence"] >= self.ai_min_confidence
            ]
            before_zones = len(detections)
            detections = self._filter_zones(detections, frame.shape[1], frame.shape[0])
            if before_zones:
                logger.debug(
                    "detections_per_frame",
                    camera_id=self.camera_id,
                    before_zones=before_zones,
                    after_zones=len(detections),
                    classes=[d.get("class", d.get("class_name")) for d in detections],
                )

            # call plugins with all visible detections (pre-cooldown)
            if detections and self.plugins and not await _check_paused():
                now = datetime.now(UTC)
                for plugin in self.plugins:
                    try:
                        await plugin.on_detection(self.camera_id, detections, frame, now)
                    except Exception:
                        logger.warning(
                            "plugin_on_detection_failed",
                            camera=self.camera_name,
                            plugin=plugin.name if hasattr(plugin, "name") else "unknown",
                        )

            detections = self._apply_tracking(detections, frame.shape[1], frame.shape[0])
            if detections and not await _check_paused():
                await self._persist(detections, frame, cv2)

            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.05, frame_interval - elapsed))

    def _apply_tracking(self, detections: list[dict], frame_w: int, frame_h: int) -> list[dict]:
        """Two-stage multi-object tracking with moving/stationary cooldowns.

        Stage 1: strict match (IoU >= IOU_MATCH_THRESHOLD and centre distance
        <= MAX_CENTRE_DISTANCE). Stage 2: relaxed fallback — at 1 FPS a moving
        object leaves zero overlap between frames, so unmatched tracklets get a
        second chance via class + centre distance <= FALLBACK_CENTRE_DISTANCE.
        Without stage 2 every moving object spawned a new tracklet (and an
        event) every single frame.

        New objects fire immediately, throttled only by a global per-class gap
        (CLASS_EVENT_GAP_S) as an anti-spam backstop. Moving objects then fire
        at most once per MOVING_COOLDOWN_S; stationary objects: persons 5 min,
        vehicles 20 min. After STATIONARY_HYSTERESIS consecutive stationary
        frames the tracklet is 'parked' and survives TRACKLET_TIMEOUT_S expiry.
        A parked tracklet that starts moving expires only after being UNSEEN
        for PARKED_MOVED_EXPIRY_S (a matching moved object must not double-fire).
        """
        now_ts = datetime.now(UTC).timestamp()

        # Purge expired tracklets (keep parked ones; drop moved-away only when unseen)
        alive: list[Tracklet] = []
        for t in self._tracklets:
            age = now_ts - t.last_seen_ts
            if t.moved_from_parked_at > 0 and age > PARKED_MOVED_EXPIRY_S:
                continue  # moved away and not seen since → drop
            if t.is_parked or age < TRACKLET_TIMEOUT_S:
                alive.append(t)
        # Parked-first: keep parked tracklets, evict oldest non-parked by LRU
        alive.sort(key=lambda t: (0 if t.is_parked else 1, -t.last_seen_ts))
        self._tracklets = alive[:MAX_TRACKLETS]

        fresh: list[dict] = []
        unmatched = list(range(len(detections)))
        matched_tracklets: set[str] = set()

        def _norm_centre(box: list) -> tuple[float, float]:
            return (
                (box[0] + box[2]) / 2 / max(frame_w, 1),
                (box[1] + box[3]) / 2 / max(frame_h, 1),
            )

        def _apply_match(t: Tracklet, det: dict) -> None:
            box = det["box"]
            cx, cy = _norm_centre(box)
            t.bbox = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
            t.last_seen_ts = now_ts

            moved = abs(cx - t.last_cx) + abs(cy - t.last_cy) > POSITION_TOLERANCE
            if not moved:
                t.stationary_count += 1
                # Parked logic disabled per user request; no tracklet becomes parked.
                # if t.stationary_count >= STATIONARY_HYSTERESIS:
                #     t.is_parked = True
                t.moved_from_parked_at = 0.0
            else:
                if t.is_parked:
                    t.is_parked = False
                    t.moved_from_parked_at = now_ts
                t.stationary_count = 0

            t.last_cx = cx
            t.last_cy = cy

            static_cooldown = (
                VEHICLE_STATIC_COOLDOWN_S if t.cls in VEHICLE_CLASSES
                else PERSON_STATIC_COOLDOWN_S
            )
            gap = now_ts - t.last_event_ts
            if gap >= MIN_EVENT_GAP_S:
                cooldown = MOVING_COOLDOWN_S if moved else static_cooldown
                if gap >= cooldown and not t.is_parked:
                    t.last_event_ts = now_ts
                    det["track_id"] = t.id
                    fresh.append(det)

        # ── Stage 1: strict IoU + centre distance ──
        # Parked tracklets participate BUT do NOT consume detections
        # unless the object moved (became unparked).  A parked false-positive
        # (e.g. background tree misclassified as "car") must not steal
        # detections of real vehicles passing through the same area.
        for t in self._tracklets:
            best_idx = -1
            best_score = -1.0
            for i in unmatched:
                det = detections[i]
                if det["class"] != t.cls:
                    continue
                box = det.get("box")
                if not box or len(box) != 4:
                    continue
                iou = compute_iou(t.bbox, (int(box[0]), int(box[1]), int(box[2]), int(box[3])))
                if iou < IOU_MATCH_THRESHOLD:
                    continue
                det_cx, det_cy = _norm_centre(box)
                dist = abs(det_cx - t.last_cx) + abs(det_cy - t.last_cy)
                if dist > MAX_CENTRE_DISTANCE:
                    continue
                score = iou - dist * 0.5
                if score > best_score:
                    best_score = score
                    best_idx = i
            if best_idx >= 0:
                was_parked = t.is_parked
                matched_tracklets.add(t.id)
                _apply_match(t, detections[best_idx])
                # Parked objects that did NOT move must not consume the
                # detection — a real vehicle passing through the same area
                # must be able to fire its own event.
                if not (was_parked and t.is_parked):
                    unmatched.remove(best_idx)

        # ── Stage 2: relaxed centre-distance fallback for unmatched tracklets ──
        # At 1 FPS a walking person moves ~50-70px while their box is ~25-40px
        # wide → consecutive-frame IoU ≈ 0 → stage 1 can never match movers.
        # Parked tracklets are skipped here: a stationary vehicle sitting in the
        # same lane position must not steal brand-new detections from passing
        # traffic. The parked tracklet is already matched via stage-1 IoU.
        for t in self._tracklets:
            if t.id in matched_tracklets or not unmatched:
                continue
            if t.is_parked:
                continue
            best_idx = -1
            best_dist = FALLBACK_CENTRE_DISTANCE
            for i in unmatched:
                det = detections[i]
                if det["class"] != t.cls:
                    continue
                box = det.get("box")
                if not box or len(box) != 4:
                    continue
                det_cx, det_cy = _norm_centre(box)
                dist = abs(det_cx - t.last_cx) + abs(det_cy - t.last_cy)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
            if best_idx >= 0:
                matched_tracklets.add(t.id)
                _apply_match(t, detections[best_idx])
                unmatched.remove(best_idx)

        # ── Remaining detections → new tracklets (fire immediately, spatial anti-spam) ──
        for i in unmatched:
            det = detections[i]
            box = det.get("box") or [0, 0, 0, 0]
            tid = f"{det['class']}_{len(self._tracklets)}_{int(now_ts * 1000) % 100000}"
            cx, cy = _norm_centre(box)
            t = Tracklet(
                id=tid,
                cls=det["class"],
                bbox=(int(box[0]), int(box[1]), int(box[2]), int(box[3])),
                last_event_ts=now_ts,
                last_seen_ts=now_ts,
                last_cx=cx,
                last_cy=cy,
            )
            self._tracklets.append(t)
            candidate_bbox = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))

            # Parked-tracklet inheritance is disabled: the user requested that
            # passing/slow vehicles on the speed bump keep firing events. A
            # new detection always becomes a fresh tracklet and is throttled
            # only by the normal moving/stationary cooldowns.

            # Tracklet-based anti-spam: suppress the event only when the
            # candidate overlaps (IoU > IOU_MATCH_THRESHOLD) an *active*
            # tracklet of the SAME class that already fired recently.
            # Genuinely different objects (e.g. two cars in adjacent lanes)
            # have low IoU and pass through unscathed.
            cls = det["class"]
            overlapped = False
            for ot in self._tracklets:
                if ot is t:
                    continue
                if ot.cls != cls:
                    continue
                if now_ts - ot.last_event_ts > CLASS_EVENT_GAP_S:
                    continue
                if compute_iou(candidate_bbox, ot.bbox) > IOU_MATCH_THRESHOLD:
                    overlapped = True
                    break

            if not overlapped:
                det["track_id"] = tid
                fresh.append(det)

        return fresh

    def _filter_zones(self, detections: list[dict], frame_w: int, frame_h: int) -> list[dict]:
        """Keep detections whose bottom-center (ground point) is inside a zone.

        Zones are normalized (0-1) polygons; empty zone list = whole frame.
        """
        if not self.ai_zones:
            return detections
        import cv2

        polygons = [
            (np.array(z["points"], dtype=np.float32) * [frame_w, frame_h]).astype(np.int32)
            for z in self.ai_zones
        ]
        kept = []
        dropped: list[str] = []
        for det in detections:
            box = det.get("box") or [0, 0, 0, 0]
            px = (box[0] + box[2]) / 2
            py = box[3]  # bottom edge = ground contact point
            if any(cv2.pointPolygonTest(poly, (px, py), False) >= 0 for poly in polygons):
                kept.append(det)
            else:
                dropped.append(f"{det.get('class_name', '?')}({det.get('confidence', 0):.2f} @ {px:.0f},{py:.0f})")
        if dropped:
            logger.info(
                "zone_filter_dropped",
                camera_id=self.camera_id,
                dropped=dropped,
                kept=len(kept),
            )
        return kept

    async def _track_motion(self, has_motion: bool) -> None:
        """Publish motion state changes (+ heartbeat) for the recording engine.

        Heartbeats are published in BOTH states — an inactive heartbeat lets
        the recording engine distinguish "no motion" from "publisher dead".
        The first frames after a (re)connect are suppressed: MOG2 sees an
        all-new scene and would otherwise fire a spurious motion burst.
        """
        now_ts = datetime.now(UTC).timestamp()
        if has_motion:
            self._last_motion_ts = now_ts
            self._motion_consecutive += 1
            cooldown_remaining = self._motion_last_stop_ts + MOTION_COOLDOWN_S - now_ts
            warmup_done = self._frames_since_connect > MOTION_WARMUP_FRAMES
            if (
                not self._motion_active
                and warmup_done
                and self._motion_consecutive >= MOTION_ARM_FRAMES
                and cooldown_remaining <= 0
            ):
                self._motion_active = True
                await self._publish_motion(True)
            elif self._motion_active and now_ts - self._last_motion_pub_ts >= MOTION_HEARTBEAT_S:
                await self._publish_motion(True)      # heartbeat while active
        else:
            self._motion_consecutive = 0
            if not self._motion_active and now_ts - self._last_motion_pub_ts >= MOTION_HEARTBEAT_S:
                await self._publish_motion(False)     # inactive heartbeat
        if self._motion_active and now_ts - self._last_motion_ts >= MOTION_OFF_S:
            self._motion_active = False
            self._motion_last_stop_ts = now_ts
            await self._publish_motion(False)

    async def _publish_motion(self, active: bool) -> None:
        self._last_motion_pub_ts = datetime.now(UTC).timestamp()
        await db.RedisPublisher.shared().publish(
            MOTION_CHANNEL,
            {"camera_id": self.camera_id, "active": active},
        )
        logger.info("motion_state", camera=self.camera_name, active=active)

    async def _persist(self, detections: list[dict], frame: np.ndarray, cv2) -> None:
        now = datetime.now(UTC)
        now_local = datetime.now(self._tz)
        objects = [
             {
                 "class": d["class"],
                 "confidence": d["confidence"],
                 "track_id": d.get("track_id", ""),
                 "box": d.get("box", []),
                }
            for d in detections
         ]

        snapshot_path = None
        try:
            annotated = self._draw_boxes(frame.copy(), detections, cv2)
            ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                snapshot_path = await self._save_snapshot(buf.tobytes(), now)
        except Exception:
            logger.warning("snapshot_encode_failed", camera=self.camera_name, exc_info=True)

        # Event insert and counter upserts are independent — a counter failure
        # must never take the event (and its broadcast) down with it.
        event_saved = False
        try:
            async with db.SessionFactory() as session:
                await db.insert_detection_event(
                    session,
                    camera_id=self.camera_id,
                    objects=objects,
                    model_name=self._detector.model_name,
                    snapshot_path=snapshot_path,
                    start_time=now,
                )
            event_saved = True
        except Exception:
            logger.warning("ai_persist_failed", camera=self.camera_name, exc_info=True)

        ts = now.timestamp()
        for det in detections:
            category = _classify_object(det["class"])
            if category is None:
                continue
            if ts - self._last_counter_ts.get(category, 0) < MIN_COUNTER_GAP_S:
                continue
            try:
                async with db.SessionFactory() as session:
                    await db.upsert_object_counter(
                        session,
                        camera_id=self.camera_id,
                        object_category=category,
                        counter_date=now_local.date(),
                        hour=now_local.hour,
                        count=1,
                    )
                # Advance the gap timer only after a successful upsert.
                self._last_counter_ts[category] = ts
            except Exception:
                logger.warning("ai_counter_upsert_failed", camera=self.camera_name, category=category)

        if event_saved and self._event_callback:
            await self._event_callback(self.camera_id, [o["class"] for o in objects], snapshot_path)
        logger.info(
            "ai_detection",
            camera=self.camera_name,
            objects=[o["class"] for o in objects],
        )

    @staticmethod
    def _draw_boxes(frame: np.ndarray, detections: list[dict], cv2) -> np.ndarray:
        """Draw bounding boxes and labels on a copy of the detection frame."""
        import random

        rng = random.Random()
        for det in detections:
            box = det.get("box")
            if not box or len(box) != 4:
                continue
            x1, y1, x2, y2 = map(int, box)
            label = f"{det['class']} {det['confidence']:.2f}"
            rng.seed(hash(det["class"]) % (2**31))
            color = (rng.randint(80, 255), rng.randint(80, 255), rng.randint(80, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 4), (x1 + tw + 4, y1), color, -1)
            cv2.putText(
                frame, label, (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
            )

        return frame

    async def _save_snapshot(self, data: bytes, ts: datetime) -> str | None:
        snap_dir = os.path.join(self.storage_path, "snapshots")
        path = os.path.join(snap_dir, f"{self.camera_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.jpg")
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_write_file, path, data),
                timeout=5.0,
            )
            return path
        except Exception:
            logger.warning(
                "snapshot_storage_failed",
                camera=self.camera_name,
                storage_path=self.storage_path,
            )
        # Fallback to local temp so a hung NFS mount does not block detection events.
        fallback_dir = "/tmp/ai_snapshots"
        os.makedirs(fallback_dir, exist_ok=True)
        fallback_path = os.path.join(
            fallback_dir, f"{self.camera_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        )
        await asyncio.to_thread(_write_file, fallback_path, data)
        logger.info("snapshot_saved_to_fallback", camera=self.camera_name, path=fallback_path)
        return fallback_path


def _write_file(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
