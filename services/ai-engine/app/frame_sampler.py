"""Frame sampler — RTSP sub-stream reader with motion gate + YOLO detection.

Reads frames directly as numpy arrays (no JPEG round-trip), gates on MOG2
motion, runs the shared ONNX detector off the event loop, applies per-class
cooldowns, persists events + JPEG snapshots, and broadcasts over Redis.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from urllib.parse import quote, urlparse, urlunparse

import numpy as np
import structlog

from . import db
from .detector import AIDetector, MotionDetector

logger = structlog.get_logger()

TARGET_FPS = 0.5
STATIC_COOLDOWN_S = 300  # same object in same place -> 1 event per 5 min
MIN_EVENT_GAP_S = 5  # never more than 1 event per class per 5s
POSITION_TOLERANCE = 0.10  # normalized box-center movement = new object
RECONNECT_BASE_S = 5
RECONNECT_MAX_S = 120
FRAME_WIDTH = 640
DEFAULT_OBJECTS = ["person", "car", "truck", "bus", "motorcycle", "bicycle"]
MOTION_CHANNEL = "nvr:motion"
MOTION_OFF_S = 30.0   # silence this long -> motion inactive
MOTION_HEARTBEAT_S = 30.0   # re-publish active state (recording engine recovery)
MOTION_COOLDOWN_S = 60.0   # min gap between recording starts after motion stops


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
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.stream_url = build_rtsp_url(stream_uri, username, password)
        self.ai_objects = set(ai_objects or DEFAULT_OBJECTS)
        self.ai_min_confidence = ai_min_confidence or 0.5
        # clamp misconfigured values (e.g. "2" from system_config)
        if self.ai_min_confidence > 1:
            self.ai_min_confidence = 0.5
        self.ai_zones = [z for z in (ai_zones or []) if len(z.get("points", [])) >= 3]
        self.motion_only = motion_only

        self._detector = AIDetector.shared()
        self._motion = MotionDetector(sensitivity=ai_sensitivity or "medium")
        self._event_callback = event_callback
        self._running = False
        # class -> (last_event_ts, center_x_norm, center_y_norm)
        self._last_events: dict[str, tuple[float, float, float]] = {}
        self._task: asyncio.Task | None = None
        # motion recording trigger state
        self._motion_active = False
        self._last_motion_ts = 0.0
        self._last_motion_pub_ts = 0.0
        self._motion_consecutive = 0
        self._motion_last_stop_ts = 0.0

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
            detections = self._filter_zones(detections, frame.shape[1], frame.shape[0])
            detections = self._apply_cooldown(detections, frame.shape[1], frame.shape[0])
            if detections:
                await self._persist(detections, frame, cv2)

            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.05, frame_interval - elapsed))

    def _apply_cooldown(self, detections: list[dict], frame_w: int, frame_h: int) -> list[dict]:
        """Position-aware event dedup.

        A detection is a NEW event when:
        - the class has no recent event, or
        - the object moved significantly (new arrival / object in motion).

        A static object (parked car, standing person) re-fires at most once
        per STATIC_COOLDOWN_S so events are not spammed.
        """
        now_ts = datetime.now(UTC).timestamp()
        fresh = []
        for det in detections:
            cls = det["class"]
            box = det.get("box") or [0, 0, 0, 0]
            cx = ((box[0] + box[2]) / 2) / max(frame_w, 1)
            cy = ((box[1] + box[3]) / 2) / max(frame_h, 1)

            last = self._last_events.get(cls)
            if last is not None:
                last_ts, last_cx, last_cy = last
                gap = now_ts - last_ts
                moved = abs(cx - last_cx) + abs(cy - last_cy) > POSITION_TOLERANCE
                if gap < MIN_EVENT_GAP_S:
                    continue
                if not moved and gap < STATIC_COOLDOWN_S:
                    continue

            self._last_events[cls] = (now_ts, cx, cy)
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
        objects = {d["class"]: d["confidence"] for d in detections}

        snapshot_path = None
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
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
        except Exception:
            logger.warning("ai_persist_failed", camera=self.camera_name, exc_info=True)
            return

        if self._event_callback:
            await self._event_callback(self.camera_id, list(objects.keys()), snapshot_path)
        logger.info(
            "ai_detection",
            camera=self.camera_name,
            objects=list(objects.keys()),
        )

    async def _save_snapshot(self, data: bytes, ts: datetime) -> str | None:
        snap_dir = os.path.join(
            os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings"), "snapshots"
        )
        os.makedirs(snap_dir, exist_ok=True)
        path = os.path.join(snap_dir, f"{self.camera_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.jpg")
        await asyncio.to_thread(_write_file, path, data)
        return path


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)
