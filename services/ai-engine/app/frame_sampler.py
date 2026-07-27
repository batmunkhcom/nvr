"""Frame sampler — RTSP sub-stream reader with motion gate + YOLO detection.

Reads frames directly as numpy arrays (no JPEG round-trip), gates on MOG2
motion, runs the shared ONNX detector off the event loop, applies IoU-based
per-object tracking with moving/stationary cooldowns, persists events + JPEG
snapshots, and broadcasts over Redis.

Tracking (v3): IoU-based multi-object tracklet tracking. Each object gets a
unique track_id. Moving objects fire events every MOVING_COOLDOWN_S (15s);
stationary objects: persons every 5 min, vehicles every 30 min. After 5
consecutive stationary frames the tracklet is 'parked' and survives timeouts
indefinitely, preventing re-detection of parked cars/bikes.
Tracklets expire after TRACKLET_TIMEOUT_S (120s) if not parked.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlparse, urlunparse

import numpy as np
import structlog

from . import db
from .detector import AIDetector, MotionDetector

logger = structlog.get_logger()

TARGET_FPS = 0.5
RECONNECT_BASE_S = 5
RECONNECT_MAX_S = 120
FRAME_WIDTH = 640
DEFAULT_OBJECTS = ["person", "car", "truck", "bus", "motorcycle", "bicycle", "dog", "cat", "bird"]
MOTION_CHANNEL = "nvr:motion"
MOTION_OFF_S = 30.0
MOTION_HEARTBEAT_S = 30.0
MOTION_COOLDOWN_S = 60.0
FORCED_INFERENCE_INTERVAL_S = 30.0

# ── IoU tracking constants ──
IOU_MATCH_THRESHOLD = 0.30          # IoU > this → same tracked object
TRACKLET_TIMEOUT_S = 300.0          # unseen this long → remove tracklet (5 min)
MOVING_COOLDOWN_S = 15.0            # moving object: at most 1 event per N seconds
PERSON_STATIC_COOLDOWN_S = 300.0    # stationary person/animal: 5 min
VEHICLE_STATIC_COOLDOWN_S = 1200.0  # stationary vehicle: 20 min
MIN_EVENT_GAP_S = 2.0                # absolute minimum gap between any two events
POSITION_TOLERANCE = 0.10            # normalized centre movement threshold
STATIONARY_HYSTERESIS = 5            # consecutive stationary frames → parked
PARKED_MOVED_EXPIRY_S = 10.0         # parked object moved → tracklet expires after this
MAX_CENTRE_DISTANCE = 0.15           # IoU + centre distance diff → treat as same object

# ── Object category mapping (used by both counter and event metadata) ──
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
    import redis.asyncio as aioredis

    try:
        host = os.environ.get("REDIS_HOST", "localhost")
        port = int(os.environ.get("REDIS_PORT", "6379"))
        redis = aioredis.from_url(f"redis://{host}:{port}/0", decode_responses=True)
        val = await redis.get(RECORDING_PAUSE_KEY)
        await redis.aclose()
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
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.stream_url = build_rtsp_url(stream_uri, username, password)
        self.ai_objects = set(ai_objects or DEFAULT_OBJECTS)
        self.ai_min_confidence = ai_min_confidence or 0.5
        if self.ai_min_confidence > 1:
            self.ai_min_confidence = 0.5
        self.ai_zones = [z for z in (ai_zones or []) if len(z.get("points", [])) >= 3]
        self.motion_only = motion_only
        self.plugins = plugins or []
        self.storage_path = storage_path or os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings")

        self._detector = AIDetector.shared()
        self._motion = MotionDetector(sensitivity=ai_sensitivity or "medium")
        self._event_callback = event_callback
        self._running = False
        self._tracklets: list[Tracklet] = []
        self._task: asyncio.Task | None = None
        self._motion_active = False
        self._last_motion_ts = 0.0
        self._last_motion_pub_ts = 0.0
        self._motion_consecutive = 0
        self._motion_last_stop_ts = 0.0
        self._last_forced_inference_ts = 0.0
        self._last_counter_ts: dict[str, float] = {}

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

        backoff = RECONNECT_BASE_S
        while self._running:
            cap = await asyncio.to_thread(self._open_capture, cv2)
            if cap is None:
                logger.warning(
                    "frame_sampler_open_failed",
                    camera=self.camera_name,
                    retry_s=backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX_S)
                continue

            backoff = RECONNECT_BASE_S
            logger.info("frame_sampler_connected", camera=self.camera_name)
            try:
                await self._consume(cap, cv2)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("frame_sampler_error", camera=self.camera_name, exc_info=True)
            finally:
                await asyncio.to_thread(cap.release)

    def _open_capture(self, cv2):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            cap.release()
            return None
        return cap

    async def _consume(self, cap, cv2) -> None:
        frame_interval = 1.0 / TARGET_FPS
        failures = 0
        while self._running:
            started = asyncio.get_running_loop().time()
            ret, frame = await asyncio.to_thread(cap.read)
            if not ret or frame is None:
                failures += 1
                if failures >= 10:
                    logger.warning("frame_sampler_stream_lost", camera=self.camera_name)
                    return  # trigger reconnect
                await asyncio.sleep(0.5)
                continue
            failures = 0

            frame = cv2.resize(
                frame, (FRAME_WIDTH, int(frame.shape[0] * FRAME_WIDTH / frame.shape[1]))
            )
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
            has_motion = self._motion.detect(gray)
            await self._track_motion(has_motion)

            force_inference = False
            if not has_motion:
                now_ts = datetime.now(UTC).timestamp()
                if now_ts - self._last_forced_inference_ts >= FORCED_INFERENCE_INTERVAL_S:
                    force_inference = True
                else:
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
            detections = self._filter_zones(detections, frame.shape[1], frame.shape[0])

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

            if force_inference:
                self._last_forced_inference_ts = datetime.now(UTC).timestamp()

            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.05, frame_interval - elapsed))

    def _apply_tracking(self, detections: list[dict], frame_w: int, frame_h: int) -> list[dict]:
        """IoU-based multi-object tracking with moving/stationary cooldowns.

        Each detection is matched to an existing Tracklet by IoU + centre distance.
        New objects create a tracklet and always fire an event on first sight.
        Existing objects check movement and cooldown before re-firing.

        Moving objects fire at most once per MOVING_COOLDOWN_S (15s).
        Stationary objects: persons 5 min, vehicles 20 min.
        After STATIONARY_HYSTERESIS (5) consecutive stationary frames, the
        tracklet is marked 'parked' and survives TRACKLET_TIMEOUT_S expiry.
        When a parked object moves away, its tracklet is expired quickly
        (PARKED_MOVED_EXPIRY_S) so a new object in the same spot fires fresh.
        """
        now_ts = datetime.now(UTC).timestamp()

        # Purge expired tracklets (keep parked ones unless recently moved away)
        alive: list[Tracklet] = []
        for t in self._tracklets:
            age = now_ts - t.last_seen_ts
            if t.moved_from_parked_at > 0:
                moved_age = now_ts - t.moved_from_parked_at
                if moved_age > PARKED_MOVED_EXPIRY_S:
                    continue  # drop: parked object moved away, tracklet expired
            if t.is_parked or age < TRACKLET_TIMEOUT_S:
                alive.append(t)
        self._tracklets = alive

        fresh: list[dict] = []
        unmatched = list(range(len(detections)))

        # Try to match each existing tracklet to a detection
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
                det_cx = (box[0] + box[2]) / 2 / max(frame_w, 1)
                det_cy = (box[1] + box[3]) / 2 / max(frame_h, 1)
                dist = abs(det_cx - t.last_cx) + abs(det_cy - t.last_cy)
                if dist > MAX_CENTRE_DISTANCE:
                    continue
                score = iou - dist * 0.5
                if score > best_score:
                    best_score = score
                    best_idx = i

            if best_idx >= 0:
                det = detections[best_idx]
                box = det["box"]
                cx = (box[0] + box[2]) / 2 / max(frame_w, 1)
                cy = (box[1] + box[3]) / 2 / max(frame_h, 1)

                t.bbox = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
                t.last_seen_ts = now_ts

                moved = abs(cx - t.last_cx) + abs(cy - t.last_cy) > POSITION_TOLERANCE
                if not moved:
                    t.stationary_count += 1
                    if t.stationary_count >= STATIONARY_HYSTERESIS:
                        t.is_parked = True
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
                    if moved:
                        if gap >= MOVING_COOLDOWN_S:
                            t.last_event_ts = now_ts
                            det["track_id"] = t.id
                            fresh.append(det)
                    else:
                        if gap >= static_cooldown:
                            t.last_event_ts = now_ts
                            det["track_id"] = t.id
                            fresh.append(det)

                unmatched.remove(best_idx)

        # Remaining detections → new tracklets (always fire a first event)
        for i in unmatched:
            det = detections[i]
            box = det.get("box") or [0, 0, 0, 0]
            tid = f"{det['class']}_{len(self._tracklets)}_{int(now_ts * 1000) % 100000}"
            cx = (box[0] + box[2]) / 2 / max(frame_w, 1)
            cy = (box[1] + box[3]) / 2 / max(frame_h, 1)
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
        for det in detections:
            box = det.get("box") or [0, 0, 0, 0]
            px = (box[0] + box[2]) / 2
            py = box[3]  # bottom edge = ground contact point
            if any(cv2.pointPolygonTest(poly, (px, py), False) >= 0 for poly in polygons):
                kept.append(det)
        return kept

    async def _track_motion(self, has_motion: bool) -> None:
        """Publish motion state changes (+ heartbeat) for the recording engine."""
        now_ts = datetime.now(UTC).timestamp()
        if has_motion:
            self._last_motion_ts = now_ts
            self._motion_consecutive += 1
            cooldown_remaining = self._motion_last_stop_ts + MOTION_COOLDOWN_S - now_ts
            if not self._motion_active and self._motion_consecutive >= 5 and cooldown_remaining <= 0:
                self._motion_active = True
                await self._publish_motion(True)
            elif self._motion_active and now_ts - self._last_motion_pub_ts >= MOTION_HEARTBEAT_S:
                await self._publish_motion(True)      # heartbeat while active
        else:
            self._motion_consecutive = 0
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
            logger.warning("snapshot_encode_failed", camera=self.camera_name)

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
                 # Upsert object counters (consolidated with events)
                ts = now.timestamp()
                for det in detections:
                    category = _classify_object(det["class"])
                    if category is None:
                        continue
                    last_ts = self._last_counter_ts.get(category, 0)
                    if ts - last_ts < MIN_COUNTER_GAP_S:
                        continue
                    self._last_counter_ts[category] = ts
                    await db.upsert_object_counter(
                        session,
                        camera_id=self.camera_id,
                        object_category=category,
                        counter_date=now.date(),
                        hour=now.hour,
                        count=1,
                      )
        except Exception:
            logger.warning("ai_persist_failed", camera=self.camera_name, exc_info=True)
            return

        if self._event_callback:
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

        for det in detections:
            box = det.get("box")
            if not box or len(box) != 4:
                continue
            x1, y1, x2, y2 = map(int, box)
            label = f"{det['class']} {det['confidence']:.2f}"
            # deterministic color per class
            random.seed(hash(det["class"]) % (2**31))
            color = (random.randint(80, 255), random.randint(80, 255), random.randint(80, 255))
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
        os.makedirs(snap_dir, exist_ok=True)
        path = os.path.join(snap_dir, f"{self.camera_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.jpg")
        await asyncio.to_thread(_write_file, path, data)
        return path


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)
