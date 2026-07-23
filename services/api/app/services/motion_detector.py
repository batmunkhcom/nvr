"""OpenCV motion detection background service — detects pixel changes and emits DB events."""

from __future__ import annotations

import asyncio
import contextlib
import uuid as _uuid
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()

_MOTION_TASK: asyncio.Task[None] | None = None
_MOTION_RUNNING = False
_BUFFER_SIZE = 10
_MIN_CONTOUR_AREA = 600
_CONSECUTIVE_FRAMES = 4
_FRAME_RESIZE = (320, 240)

_confidence_cache: float = 0.6


async def _load_confidence() -> float:
    global _confidence_cache
    try:
        from ..core.database import async_session_factory
        from ..models.system_config import SystemConfig

        async with async_session_factory() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(SystemConfig).where(SystemConfig.key == "ai.confidence_threshold")
            )
            row = result.scalar_one_or_none()
            if row is not None:
                _confidence_cache = float(row.value)
    except Exception:
        pass
    return _confidence_cache


async def _motion_loop() -> None:
    global _MOTION_RUNNING
    _MOTION_RUNNING = True
    logger.info("motion_detection_started")

    motion_buffers: dict[str, list[bool]] = {}

    while _MOTION_RUNNING:
        await _load_confidence()
        try:
            import cv2 as _cv2
        except ImportError:
            logger.warning("opencv_not_installed")
            await asyncio.sleep(60)
            continue

        try:
            from ..core.database import async_session_factory
            from ..core.security import decrypt_password_aes
            from ..models.camera import Camera

            async with async_session_factory() as session:
                from sqlalchemy import select

                result = await session.execute(select(Camera).where(Camera.status == "online"))
                cameras = result.scalars().all()

            for camera in cameras:
                if not _MOTION_RUNNING:
                    break
                cam_id = str(camera.id)
                rtsp_uri = camera.stream_sub_uri or camera.stream_main_uri
                if not rtsp_uri:
                    continue

                password = None
                if camera.username and camera.encrypted_password:
                    with contextlib.suppress(Exception):
                        password = decrypt_password_aes(camera.encrypted_password)

                from urllib.parse import urlparse, urlunparse

                authed_uri = rtsp_uri
                if camera.username and password:
                    parsed = urlparse(rtsp_uri)
                    authed_uri = urlunparse(
                        parsed._replace(
                            netloc=f"{camera.username}:{password}@{parsed.hostname}"
                            + (f":{parsed.port}" if parsed.port else "")
                        )
                    )

                cap = _cv2.VideoCapture(authed_uri)
                cap.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(_cv2.CAP_PROP_FPS, 5)

                if not cap.isOpened():
                    cap.release()
                    continue

                ret, prev_frame = cap.read()
                if not ret:
                    cap.release()
                    continue

                prev_gray = _cv2.cvtColor(prev_frame, _cv2.COLOR_BGR2GRAY)
                prev_gray = _cv2.GaussianBlur(prev_gray, (21, 21), 0)

                if cam_id not in motion_buffers:
                    motion_buffers[cam_id] = [False] * _BUFFER_SIZE

                for _ in range(10):
                    if not _MOTION_RUNNING:
                        break
                    ret, frame = cap.read()
                    if not ret:
                        break

                    gray = _cv2.cvtColor(frame, _cv2.COLOR_BGR2GRAY)
                    gray = _cv2.GaussianBlur(gray, (21, 21), 0)

                    diff = _cv2.absdiff(prev_gray, gray)
                    thresh = _cv2.threshold(diff, 25, 255, _cv2.THRESH_BINARY)[1]
                    thresh = _cv2.dilate(thresh, None, iterations=2)
                    contours, _ = _cv2.findContours(
                        thresh, _cv2.RETR_EXTERNAL, _cv2.CHAIN_APPROX_SIMPLE
                    )

                    has_motion = False
                    for c in contours:
                        if _cv2.contourArea(c) > _MIN_CONTOUR_AREA:
                            has_motion = True
                            break

                    motion_buffers[cam_id].append(has_motion)
                    if len(motion_buffers[cam_id]) > _BUFFER_SIZE:
                        motion_buffers[cam_id] = motion_buffers[cam_id][-_BUFFER_SIZE:]

                    prev_gray = gray

                    recent = motion_buffers[cam_id][-_CONSECUTIVE_FRAMES:]
                    if len(recent) >= _CONSECUTIVE_FRAMES and all(recent):
                        await _record_motion_event(
                            _uuid.UUID(cam_id),
                            camera.name or cam_id,
                            len(contours),
                        )
                        motion_buffers[cam_id] = [False] * _BUFFER_SIZE
                        break

                cap.release()

            await asyncio.sleep(3)

        except Exception as exc:
            logger.error("motion_loop_error", error=str(exc))
            await asyncio.sleep(5)


async def _record_motion_event(
    camera_id: _uuid.UUID,
    camera_name: str,
    num_contours: int,
) -> None:
    try:
        from ..core.database import async_session_factory
        from ..models.event import Event

        async with async_session_factory() as session:
            event = Event(
                camera_id=camera_id,
                event_type="motion_detected",
                severity="info",
                start_time=datetime.now(UTC),
                event_metadata={
                    "camera_name": camera_name,
                    "num_contours": num_contours,
                    "confidence": _confidence_cache,
                    "source": "opencv",
                },
            )
            session.add(event)
            await session.commit()
        logger.info("motion_event_recorded", camera_id=str(camera_id))
        try:
            from .ws_manager import ws_manager

            await ws_manager.broadcast_event(
                {
                    "id": str(event.id),
                    "camera_id": str(camera_id),
                    "event_type": "motion_detected",
                    "start_time": event.start_time.isoformat(),
                    "camera_name": camera_name,
                }
            )
        except Exception:
            pass
    except Exception as exc:
        logger.warning("motion_event_failed", camera_id=str(camera_id), error=str(exc))


async def start_motion_detection() -> None:
    global _MOTION_TASK, _MOTION_RUNNING
    if _MOTION_TASK and not _MOTION_TASK.done():
        return
    _MOTION_TASK = asyncio.create_task(_motion_loop())
    await asyncio.sleep(0.1)


async def stop_motion_detection() -> None:
    global _MOTION_TASK, _MOTION_RUNNING
    _MOTION_RUNNING = False
    if _MOTION_TASK and not _MOTION_TASK.done():
        _MOTION_TASK.cancel()
        _MOTION_TASK = None
    logger.info("motion_detection_stopped")


async def get_motion_status() -> dict:
    return {"running": _MOTION_RUNNING}
