"""Frame sampler — RTSP sub-stream reader with motion gate + YOLO detection."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
import structlog

from .detector import AIDetector, MotionDetector

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

TARGET_FPS = 2
COOLDOWN_SECONDS = 10


class FrameSampler:
    def __init__(
        self,
        camera_id: uuid.UUID,
        camera_name: str,
        stream_uri: str,
        username: str,
        password: str | None,
        ai_objects: list[str] | None,
        ai_sensitivity: str,
        ai_min_confidence: float,
        db_session_factory,
        event_callback,
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.stream_uri = stream_uri
        self.username = username
        self.password = password
        self.ai_objects = ai_objects or ["person", "car", "truck", "bus", "motorcycle", "bicycle"]
        self.ai_sensitivity = ai_sensitivity
        self.ai_min_confidence = ai_min_confidence

        self._db_factory = db_session_factory
        self._event_callback = event_callback

        self._detector = AIDetector()
        self._motion = MotionDetector(sensitivity=ai_sensitivity)
        self._running = False
        self._last_detection_at: dict[str, float] = {}

    async def start(self) -> None:
        self._running = True
        await self._detector.initialize()
        logger.info("frame_sampler_started", camera_id=str(self.camera_id))
        asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        logger.info("frame_sampler_stopped", camera_id=str(self.camera_id))

    async def _loop(self) -> None:
        import cv2

        rtsp_url = self._build_rtsp_url()
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            logger.warning("frame_sampler_open_failed", camera=self.camera_name, url=self.stream_uri)
            return

        frame_interval = 1.0 / TARGET_FPS
        last_grab = 0.0

        while self._running:
            await asyncio.sleep(max(0, frame_interval - (asyncio.get_event_loop().time() - last_grab)))
            last_grab = asyncio.get_event_loop().time()

            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                await asyncio.sleep(1)
                continue

            frame = cv2.resize(frame, (640, 360))

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            image_bytes = buf.tobytes()

            if not self._motion.detect(image_bytes):
                continue

            detections = await self._detector.detect(image_bytes)
            detections = [d for d in detections if d["class"] in self.ai_objects and d["confidence"] >= self.ai_min_confidence]

            if not detections:
                continue

            now_ts = datetime.now(UTC).timestamp()
            for det in detections:
                cls = det["class"]
                last_ts = self._last_detection_at.get(cls, 0)
                if now_ts - last_ts < COOLDOWN_SECONDS:
                    continue
                self._last_detection_at[cls] = now_ts

            await self._persist_events(detections, image_bytes)

        cap.release()

    def _build_rtsp_url(self) -> str:
        if self.username and self.password:
            uri = self.stream_uri
            if uri and uri.startswith("rtsp://"):
                parts = uri.split("://", 1)
                return f"rtsp://{self.username}:{self.password}@{parts[1]}"
        return self.stream_uri or ""

    async def _persist_events(self, detections: list[dict], snapshot_bytes: bytes) -> None:
        try:
            from app.models.event import Event

            async with self._db_factory() as db:

                now = datetime.now(UTC)
                objects = {d["class"]: round(d["confidence"], 2) for d in detections}
                object_list = list(objects.keys())

                snapshot_path = None
                try:
                    snapshot_path = await self._save_snapshot(snapshot_bytes, now)
                except Exception:
                    pass

                event = Event(
                    id=uuid.uuid4(),
                    camera_id=self.camera_id,
                    event_type="object_detected",
                    severity="info",
                    start_time=now,
                    event_metadata={
                        "objects": objects,
                        "source": "nvr_ai",
                        "model": self._detector.model_name,
                    },
                    snapshot_path=snapshot_path,
                )
                db.add(event)
                await db.commit()

                if self._event_callback:
                    await self._event_callback(self.camera_id, object_list, snapshot_path)

                logger.info(
                    "ai_detection", camera=self.camera_name,
                    objects=object_list, camera_id=str(self.camera_id),
                )
        except Exception:
            logger.warning("ai_persist_failed", camera_id=str(self.camera_id), exc_info=True)

    async def _save_snapshot(self, data: bytes, ts: datetime) -> str:
        try:
            import os
            snap_dir = os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings") + "/snapshots"
            os.makedirs(snap_dir, exist_ok=True)
            filename = f"{self.camera_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            path = os.path.join(snap_dir, filename)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _write_file, path, data)
            return path
        except Exception:
            return ""

    def describe(self) -> str:
        return (
            f"FrameSampler(camera={self.camera_name}, objects={self.ai_objects}, "
            f"fps={TARGET_FPS}, sensitivity={self.ai_sensitivity})"
        )


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)
