"""Motion-triggered recording controller.

Listens to the `nvr:motion` Redis channel (published by the AI engine's
frame samplers and ONVIF subscribers) and starts/stops per-camera recorders
for cameras with recording_mode='motion'.

Stop is delayed by `recording.motion_stop_delay_s` (default 30s) so brief
motion gaps don't split the recording; each new motion event cancels the
pending stop.

Reliability model (pub/sub is fire-and-forget, messages can be lost):
- every `active: True` is a keepalive that refreshes the camera's last-active
  timestamp (fixes ONVIF publishers that never send False),
- a periodic sweep stops recorders whose heartbeat went stale OR whose
  camera is no longer motion-mode (covers lost False, dead AI engine,
  mode flips) — recorders can never run forever.

Respects global pause: when `nvr:recording:paused` is true, no motion
recorder will be started.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import config
from .recorder import CameraRecorder

logger = structlog.get_logger()

DEFAULT_STOP_DELAY_S = 30
RECORDING_PAUSE_KEY = "nvr:recording:paused"
SWEEP_INTERVAL_S = 30
# No active keepalive for this long => publisher is gone => stop recording.
# AI engine heartbeats every 30s (both states), so 90s = 3 missed beats.
STALE_AFTER_S = 90
# Record motion from the MediaMTX relay instead of a direct camera session.
MEDIAMTX_RTSP_HOST = os.environ.get("MEDIAMTX_RTSP_HOST", "nvr-mediamtx")
RECORD_VIA_RELAY = os.environ.get("RECORD_VIA_RELAY", "1") == "1"


async def _check_paused() -> bool:
    try:
        redis = await config.get_redis()
        val = await redis.get(RECORDING_PAUSE_KEY)
        return val == "true"
    except Exception:
        return False


class MotionRecorderController:
    """Starts/stops CameraRecorder instances based on motion events.

    Keeps its own recorder registry (separate from the continuous-mode
    recorders managed by the reconcile loop) so the two never fight.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self.recorders: dict[str, CameraRecorder] = {}
        self._stop_timers: dict[str, asyncio.Task] = {}
        self._last_active_ts: dict[str, float] = {}
        self._sweep_task: asyncio.Task | None = None

    async def handle_event(self, camera_id: str, active: bool) -> None:
        if active:
            # Keepalive semantics: any True refreshes the timestamp, even from
            # publishers that never send False (ONVIF motion events).
            self._last_active_ts[camera_id] = time.time()
        if await _check_paused():
            return
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

    def start_sweep(self) -> None:
        """Start the periodic staleness/mode sweep (idempotent)."""
        if self._sweep_task is None or self._sweep_task.done():
            self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_S)
            try:
                await self._sweep()
            except Exception:
                logger.warning("motion_sweep_failed", exc_info=True)

    async def _sweep(self) -> None:
        """Stop recorders with a stale heartbeat or a non-motion-mode camera."""
        if not self.recorders:
            return
        camera_ids = list(self.recorders)
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id FROM cameras "
                    "WHERE id = ANY(:ids) AND is_active AND recording_mode = 'motion'"
                ),
                {"ids": camera_ids},
            )
            motion_ok = {str(row[0]) for row in result.fetchall()}

        now = time.time()
        for camera_id in camera_ids:
            if camera_id not in motion_ok:
                logger.info("motion_recorder_mode_changed", camera_id=camera_id)
                await self._stop_now(camera_id)
                continue
            last = self._last_active_ts.get(camera_id, 0.0)
            if now - last > STALE_AFTER_S:
                logger.warning(
                    "motion_recorder_stale_heartbeat",
                    camera_id=camera_id,
                    stale_s=int(now - last),
                )
                await self._stop_now(camera_id)

    async def _stop_now(self, camera_id: str) -> None:
        timer = self._stop_timers.pop(camera_id, None)
        if timer and not timer.done():
            timer.cancel()
        recorder = self.recorders.pop(camera_id, None)
        self._last_active_ts.pop(camera_id, None)
        if recorder:
            await recorder.stop()
            logger.info("motion_recording_stopped", camera_id=camera_id)

    async def _start(self, camera_id: str) -> None:
        cam = await self._load_camera(camera_id)
        if not cam or not cam["stream_uri"]:
            return
        async with self._session_factory() as session:
            segment_seconds = await config.get_config_int(session, "recording.segment_seconds")
        output_base = cam.get("output_base", config.STORAGE_LOCAL_PATH)
        recorder = CameraRecorder(
            camera_id=cam["id"],
            camera_name=cam["name"],
            stream_uri=cam["stream_uri"],
            username=cam["username"],
            password=_decrypt(cam["encrypted_password"]),
            output_base=output_base,
            segment_seconds=segment_seconds,
        )
        self.recorders[camera_id] = recorder
        recorder.start()
        logger.info("motion_recording_started", camera=cam["name"], camera_id=camera_id)

    async def _stop_after(self, camera_id: str, delay: float) -> None:
        task = asyncio.current_task()
        try:
            await asyncio.sleep(delay)
            recorder = self.recorders.pop(camera_id, None)
            self._last_active_ts.pop(camera_id, None)
            if recorder:
                await recorder.stop()
                logger.info("motion_recording_stopped", camera_id=camera_id)
        finally:
            # Only evict our own entry — a newer timer may already be registered.
            if self._stop_timers.get(camera_id) is task:
                self._stop_timers.pop(camera_id, None)

    async def _stop_delay(self) -> float:
        try:
            async with self._session_factory() as session:
                value = await config.get_config_int(session, "recording.motion_stop_delay_s")
                return float(value if value is not None else DEFAULT_STOP_DELAY_S)
        except Exception:
            return float(DEFAULT_STOP_DELAY_S)

    async def _load_camera(self, camera_id: str) -> dict | None:
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT c.id, c.name, c.recording_stream, c.motion_source,
                               c.stream_main_uri, c.stream_sub_uri,
                               c.username, c.encrypted_password,
                               sb.mount_point AS storage_mount_point
                        FROM cameras c
                        LEFT JOIN storage_backends sb
                            ON c.storage_backend_id = sb.id AND sb.is_active
                        WHERE c.id = :id AND c.is_active AND c.recording_mode = 'motion'
                        """
                    ),
                    {"id": camera_id},
                )
                row = result.fetchone()
                if not row:
                    return None
                cam = dict(row._mapping)
                cam["id"] = str(cam["id"])
                stream_pref = cam.get("recording_stream") or await config.get_config_str(session, "recording.stream") or "sub"
                if stream_pref == "sub":
                    cam["stream_uri"] = cam["stream_sub_uri"] or cam["stream_main_uri"]
                else:
                    cam["stream_uri"] = cam["stream_main_uri"] or cam["stream_sub_uri"]
                cam["output_base"] = cam.get("storage_mount_point") or config.STORAGE_LOCAL_PATH
                if not cam.get("storage_mount_point"):
                    logger.warning(
                        "motion_camera_no_storage_backend",
                        camera_id=camera_id,
                        camera_name=cam.get("name"),
                        fallback=config.STORAGE_LOCAL_PATH,
                    )
                # Record via the MediaMTX relay when the AI sampler keeps it
                # warm anyway: the relay is already connected with a 1s GOP,
                # so the recorder attaches in ~100ms and the muxer waits <=1s
                # for a keyframe (vs ~2-4s camera handshake + GOP wait direct).
                # Only for server-side motion (ONVIF cameras have no relay).
                if (
                    RECORD_VIA_RELAY
                    and stream_pref == "sub"
                    and cam.get("username")
                    and cam.get("motion_source") != "camera"
                ):
                    cam["stream_uri"] = f"rtsp://{MEDIAMTX_RTSP_HOST}:8554/{camera_id}_sub"
                    cam["username"] = None
                    cam["encrypted_password"] = None
                return cam
        except Exception:
            logger.warning("motion_camera_load_failed", camera_id=camera_id, exc_info=True)
            return None

    async def shutdown(self) -> None:
        if self._sweep_task and not self._sweep_task.done():
            self._sweep_task.cancel()
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
