"""Motion-triggered recording controller.

Listens to the `nvr:motion` Redis channel (published by the AI engine's
frame samplers and ONVIF subscribers) and starts/stops per-camera recorders
for cameras with recording_mode='motion'.

Stop is delayed by `recording.motion_stop_delay_s` (default 30s) so brief
motion gaps don't split the recording; each new motion event cancels the
pending stop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import config
from .recorder import CameraRecorder

logger = structlog.get_logger()

DEFAULT_STOP_DELAY_S = 30


class MotionRecorderController:
    """Starts/stops CameraRecorder instances based on motion events.

    Keeps its own recorder registry (separate from the continuous-mode
    recorders managed by the reconcile loop) so the two never fight.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self.recorders: dict[str, CameraRecorder] = {}
        self._stop_timers: dict[str, asyncio.Task] = {}

    async def handle_event(self, camera_id: str, active: bool) -> None:
        if active:
            timer = self._stop_timers.pop(camera_id, None)
            if timer and not timer.done():
                timer.cancel()
            if camera_id not in self.recorders:
                await self._start(camera_id)
        else:
            if camera_id in self.recorders and camera_id not in self._stop_timers:
                delay = await self._stop_delay()
                self._stop_timers[camera_id] = asyncio.create_task(
                    self._stop_after(camera_id, delay)
                )
                logger.info("motion_stop_scheduled", camera_id=camera_id, delay_s=delay)

    async def _start(self, camera_id: str) -> None:
        cam = await self._load_camera(camera_id)
        if not cam or not cam["stream_uri"]:
            return
        async with self._session_factory() as session:
            segment_seconds = await config.get_config_int(session, "recording.segment_seconds")
        recorder = CameraRecorder(
            camera_id=cam["id"],
            camera_name=cam["name"],
            stream_uri=cam["stream_uri"],
            username=cam["username"],
            password=_decrypt(cam["encrypted_password"]),
            output_base=config.STORAGE_LOCAL_PATH,
            segment_seconds=segment_seconds,
        )
        self.recorders[camera_id] = recorder
        recorder.start()
        logger.info("motion_recording_started", camera=cam["name"], camera_id=camera_id)

    async def _stop_after(self, camera_id: str, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            recorder = self.recorders.pop(camera_id, None)
            if recorder:
                await recorder.stop()
                logger.info("motion_recording_stopped", camera_id=camera_id)
        finally:
            self._stop_timers.pop(camera_id, None)

    async def _stop_delay(self) -> float:
        try:
            async with self._session_factory() as session:
                value = await config.get_config_int(session, "recording.motion_stop_delay_s")
                return float(value or DEFAULT_STOP_DELAY_S)
        except Exception:
            return float(DEFAULT_STOP_DELAY_S)

    async def _load_camera(self, camera_id: str) -> dict | None:
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT id, name, stream_main_uri, stream_sub_uri,
                               username, encrypted_password
                        FROM cameras
                        WHERE id = :id AND is_active AND recording_mode = 'motion'
                        """
                    ),
                    {"id": camera_id},
                )
                row = result.fetchone()
                if not row:
                    return None
                cam = dict(row._mapping)
                cam["id"] = str(cam["id"])
                stream_pref = await config.get_config_str(session, "recording.stream")
                if stream_pref == "sub":
                    cam["stream_uri"] = cam["stream_sub_uri"] or cam["stream_main_uri"]
                else:
                    cam["stream_uri"] = cam["stream_main_uri"] or cam["stream_sub_uri"]
                return cam
        except Exception:
            logger.warning("motion_camera_load_failed", camera_id=camera_id, exc_info=True)
            return None

    async def shutdown(self) -> None:
        for timer in self._stop_timers.values():
            timer.cancel()


async def motion_listener_loop(
    controller: MotionRecorderController, shutdown: asyncio.Event
) -> None:
    """Subscribe to nvr:motion and feed the controller. Reconnects on failure."""
    import os

    import redis.asyncio as aioredis

    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))

    while not shutdown.is_set():
        try:
            redis = aioredis.from_url(f"redis://{host}:{port}/0")
            pubsub = redis.pubsub()
            await pubsub.subscribe("nvr:motion")
            logger.info("motion_listener_subscribed")
            async for message in pubsub.listen():
                if shutdown.is_set():
                    break
                if message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    camera_id = payload.get("camera_id")
                    if camera_id:
                        await controller.handle_event(str(camera_id), bool(payload.get("active")))
                except (ValueError, KeyError, AttributeError):
                    logger.warning("motion_event_invalid", data=str(message.get("data"))[:200])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("motion_listener_error", exc_info=True)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(shutdown.wait(), timeout=5)


def _decrypt(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        from nvr_common.security import decrypt_password_aes

        return decrypt_password_aes(encrypted)
    except Exception:
        logger.warning("camera_password_decrypt_failed")
        return None
