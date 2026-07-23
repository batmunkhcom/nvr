"""Recording Engine — main entry point.

Polls cameras from the DB and spawns FFmpeg recording processes for
continuous, motion-triggered, and scheduled recording.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../packages"))

logger = structlog.get_logger()

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB", "nvr")
DB_USER = os.environ.get("POSTGRES_USER", "nvr")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "nvr")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

POLL_INTERVAL = 30
RETENTION_INTERVAL = 3600
SHUTDOWN = asyncio.Event()

engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=5)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_active: dict[str, dict] = {}


async def _load_cameras(session: AsyncSession) -> list[dict]:
    from app.models.camera import Camera

    result = await session.execute(
        select(Camera).where(Camera.is_active.is_(True), Camera.recording_mode != "disabled")
    )
    cameras = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "stream_uri": c.stream_sub_uri or c.stream_main_uri,
            "recording_mode": c.recording_mode,
            "storage_backend_id": str(c.storage_backend_id) if c.storage_backend_id else None,
            "username": c.username,
            "encrypted_password": c.encrypted_password,
        }
        for c in cameras
        if c.stream_sub_uri or c.stream_main_uri
    ]


async def _build_authed_uri(camera: dict) -> str:
    uri = camera["stream_uri"]
    if not camera.get("username") or not camera.get("encrypted_password"):
        return uri
    try:
        from cryptography.fernet import Fernet

        cipher = Fernet(os.environ.get("AES_KEY", "").encode() or Fernet.generate_key())
        try:
            password = cipher.decrypt(camera["encrypted_password"]).decode()
        except Exception:
            password = ""
        if password:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(uri)
            uri = urlunparse(
                parsed._replace(
                    netloc=f"{camera['username']}:{password}@{parsed.hostname}"
                    + (f":{parsed.port}" if parsed.port else "")
                )
            )
    except Exception:
        pass
    return uri


async def _get_output_dir(storage_backend_id: str | None, session: AsyncSession) -> str:
    base = os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings")
    if storage_backend_id:
        try:
            from app.models.storage_backend import StorageBackend

            result = await session.execute(
                select(StorageBackend).where(StorageBackend.id == uuid.UUID(storage_backend_id))
            )
            backend = result.scalar_one_or_none()
            if backend and backend.mount_point:
                return backend.mount_point
        except Exception:
            pass
    return base


async def _start_recording(camera: dict, session: AsyncSession) -> None:
    from app.recorder import RecordingEngine

    cam_id = camera["id"]
    if cam_id in _active:
        return

    uri = await _build_authed_uri(camera)
    output_dir = await _get_output_dir(camera.get("storage_backend_id"), session)
    logger.info("recording_launch", camera_id=cam_id, output_dir=output_dir)
    await RecordingEngine.start(cam_id, uri, output_dir)
    _active[cam_id] = camera


async def _stop_recording(camera_id: str) -> None:
    if camera_id in _active:
        del _active[camera_id]
        logger.info("recording_stop_scheduled", camera_id=camera_id)


async def _run_retention(session: AsyncSession) -> None:
    try:
        from app.retention import RetentionManager

        retention = RetentionManager(session)
        await retention.cleanup()
    except Exception as exc:
        logger.warning("retention_error", error=str(exc))


async def _poll() -> None:
    async with SessionFactory() as session:
        cameras = await _load_cameras(session)

        current_ids = {c["id"] for c in cameras}
        active_ids = set(_active.keys())

        for cam_id in active_ids - current_ids:
            await _stop_recording(cam_id)

        for camera in cameras:
            mode = camera["recording_mode"]
            if mode == "continuous":
                await _start_recording(camera, session)
            elif mode == "scheduled":
                try:
                    from app.scheduler import RecordingScheduler

                    sched = RecordingScheduler()
                    # Default: weekdays 24/7
                    should_record = await sched.evaluate(
                        camera["id"],
                        {
                            "days_of_week": [1, 2, 3, 4, 5, 6, 7],
                            "time_start": "00:00",
                            "time_end": "23:59",
                        },
                    )
                    if should_record:
                        await _start_recording(camera, session)
                    else:
                        await _stop_recording(camera["id"])
                except Exception:
                    await _start_recording(camera, session)


async def main() -> None:
    logger.info("recording_engine_starting")
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: SHUTDOWN.set())
    loop.add_signal_handler(signal.SIGINT, lambda: SHUTDOWN.set())

    last_retention = 0.0

    while not SHUTDOWN.is_set():
        try:
            await _poll()
        except Exception as exc:
            logger.error("poll_error", error=str(exc))

        now = datetime.now(UTC).timestamp()
        if now - last_retention >= RETENTION_INTERVAL:
            try:
                async with SessionFactory() as session:
                    await _run_retention(session)
            except Exception:
                pass
            last_retention = now

        await asyncio.wait_for(SHUTDOWN.wait(), timeout=POLL_INTERVAL)

    from app.recorder import RecordingEngine

    await RecordingEngine.stop()
    await engine.dispose()
    logger.info("recording_engine_stopped")


if __name__ == "__main__":
    asyncio.run(main())
