"""Recording Engine — main entry point.

Loops:
- reconcile: poll active cameras from DB, start/stop per-camera FFmpeg supervisors
- catalog: register closed MP4 segments into the recordings table
- retention: age-based + circular (overwrite-oldest) disk cleanup
- analytics: GB/day measurement + capacity projection into system_config

Self-contained: uses plain SQL (no cross-service model imports).

Pause All: checks Redis key `nvr:recording:paused` each reconcile cycle.
When active, stops ALL continuous + motion recorders and refuses to start new ones.
"""

from __future__ import annotations

import asyncio
import os
import signal

import redis.asyncio as aioredis
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from . import config
from .analytics import DiskAnalytics
from .catalog import SegmentCatalog
from .motion import MotionRecorderController, motion_listener_loop
from .recorder import CameraRecorder
from .retention import RetentionManager

logger = structlog.get_logger()

SHUTDOWN = asyncio.Event()

engine = create_async_engine(config.DATABASE_URL, pool_size=5, max_overflow=5)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_recorders: dict[str, CameraRecorder] = {}  # continuous-mode recorders (reconcile-managed)
_motion_controller = MotionRecorderController(SessionFactory)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
RECORDING_PAUSE_KEY = "nvr:recording:paused"


async def _check_paused() -> bool:
    """Check the global pause flag in Redis. Returns True if paused."""
    try:
        redis = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/0", decode_responses=True)
        val = await redis.get(RECORDING_PAUSE_KEY)
        await redis.aclose()
        return val == "true"
    except Exception:
        return False


async def _load_cameras() -> list[dict]:
    """Active, recording-enabled cameras with their stream URIs."""
    async with SessionFactory() as session:
        result = await session.execute(
            text(
                """
                SELECT id, name, recording_mode, recording_stream,
                       stream_main_uri, stream_sub_uri,
                       username, encrypted_password
                FROM cameras
                WHERE is_active
                  AND recording_mode NOT IN ('disabled', 'never', 'motion')
                  AND (stream_main_uri IS NOT NULL OR stream_sub_uri IS NOT NULL)
                """
            )
        )
        rows = result.fetchall()

        stream_pref_default = await config.get_config_str(session, "recording.stream") or "sub"

    cameras = []
    for row in rows:
        cam = dict(row._mapping)
        cam["id"] = str(cam["id"])
        stream_pref = cam.get("recording_stream") or stream_pref_default
        if stream_pref == "sub":
            cam["stream_uri"] = cam["stream_sub_uri"] or cam["stream_main_uri"]
        else:
            cam["stream_uri"] = cam["stream_main_uri"] or cam["stream_sub_uri"]
        cameras.append(cam)
    return cameras


def _decrypt(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        from nvr_common.security import decrypt_password_aes

        return decrypt_password_aes(encrypted)
    except Exception:
        logger.warning("camera_password_decrypt_failed")
        return None


async def _reconcile() -> None:
    if await _check_paused():
        for cam_id in list(_recorders):
            r = _recorders.pop(cam_id, None)
            if r:
                await r.stop()
                logger.info("recorder_stopped_paused", camera_id=cam_id)
        for cam_id in list(_motion_controller.recorders):
            r = _motion_controller.recorders.pop(cam_id, None)
            if r:
                await r.stop()
                logger.info("motion_recorder_stopped_paused", camera_id=cam_id)
        return

    try:
        cameras = await _load_cameras()
    except Exception:
        logger.error("camera_load_failed", exc_info=True)
        return

    desired = {c["id"] for c in cameras if c["stream_uri"]}

    for cam_id in set(_recorders) - desired:
        await _recorders.pop(cam_id).stop()

    async with SessionFactory() as session:
        segment_seconds = await config.get_config_int(session, "recording.segment_seconds")

    for cam in cameras:
        if cam["id"] in _recorders or not cam["stream_uri"]:
            continue
        recorder = CameraRecorder(
            camera_id=cam["id"],
            camera_name=cam["name"],
            stream_uri=cam["stream_uri"],
            username=cam["username"],
            password=_decrypt(cam["encrypted_password"]),
            output_base=config.STORAGE_LOCAL_PATH,
            segment_seconds=segment_seconds,
        )
        _recorders[cam["id"]] = recorder
        recorder.start()
        logger.info("recorder_added", camera=cam["name"], camera_id=cam["id"])


async def _reconcile_loop() -> None:
    while not SHUTDOWN.is_set():
        await _reconcile()
        await _interruptible_sleep(config.POLL_INTERVAL)


async def _catalog_loop() -> None:
    catalog = SegmentCatalog(SessionFactory)
    while not SHUTDOWN.is_set():
        try:
            await catalog.scan()
        except Exception:
            logger.warning("catalog_scan_failed", exc_info=True)
        await _interruptible_sleep(config.CATALOG_INTERVAL)


async def _retention_loop() -> None:
    retention = RetentionManager(SessionFactory)
    while not SHUTDOWN.is_set():
        try:
            await retention.run()
        except Exception:
            logger.warning("retention_run_failed", exc_info=True)
        await _interruptible_sleep(config.RETENTION_INTERVAL)


async def _analytics_loop() -> None:
    analytics = DiskAnalytics(SessionFactory)
    while not SHUTDOWN.is_set():
        try:
            await analytics.run()
        except Exception:
            logger.warning("analytics_run_failed", exc_info=True)
        await _interruptible_sleep(config.ANALYTICS_INTERVAL)


async def _interruptible_sleep(seconds: float) -> None:
    import contextlib

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(SHUTDOWN.wait(), timeout=seconds)


async def main() -> None:
    logger.info(
        "recording_engine_starting",
        version="1.0.0",
        storage=config.STORAGE_LOCAL_PATH,
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, SHUTDOWN.set)

    tasks = [
        asyncio.create_task(_reconcile_loop()),
        asyncio.create_task(_catalog_loop()),
        asyncio.create_task(_retention_loop()),
        asyncio.create_task(_analytics_loop()),
        asyncio.create_task(motion_listener_loop(_motion_controller, SHUTDOWN)),
    ]

    await SHUTDOWN.wait()

    await _motion_controller.shutdown()
    for recorder in list(_recorders.values()) + list(_motion_controller.recorders.values()):
        await recorder.stop()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await engine.dispose()
    logger.info("recording_engine_stopped")


if __name__ == "__main__":
    asyncio.run(main())
