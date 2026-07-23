"""AI Engine — main entry point.

Orchestrates AI processing for all cameras:
- motion_source="server" → FrameSampler (YOLO ONNX + motion gate)
- motion_source="camera" → OnvifEventSubscriber (camera's built-in AI via ONVIF)
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../packages"))

from app.frame_sampler import FrameSampler
from app.ollama_client import OllamaClient

logger = structlog.get_logger()

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB", "nvr")
DB_USER = os.environ.get("POSTGRES_USER", "nvr")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "nvr")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
POLL_INTERVAL = 15

engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=5, echo=False)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SHUTDOWN = asyncio.Event()
_workers: dict[uuid.UUID, FrameSampler] = {}


async def main() -> None:
    logger.info("ai_engine_starting", version="0.2.0")

    ollama = OllamaClient()
    ollama_ok = await ollama.health()
    logger.info("ollama_status", reachable=ollama_ok)

    while not SHUTDOWN.is_set():
        try:
            await _reconcile_workers()
        except Exception:
            logger.warning("ai_reconcile_failed", exc_info=True)
        await _sleep(POLL_INTERVAL)

    for w in list(_workers.values()):
        await w.stop()
    logger.info("ai_engine_stopped")


async def _reconcile_workers() -> None:
    async with SessionFactory() as db:
        from app.models.camera import Camera

        result = await db.execute(
            select(Camera).where(
                Camera.is_active.is_(True),
                Camera.ai_enabled.is_(True),
            )
        )
        cameras = result.scalars().all()

        desired = {c.id for c in cameras}
        current = set(_workers.keys())

        for cid in current - desired:
            await _workers[cid].stop()
            del _workers[cid]
            logger.info("ai_worker_removed", camera_id=str(cid))

        for cam in cameras:
            if cam.id in _workers:
                continue

            if cam.motion_source == "camera":
                if not cam.onvif_events_service_url:
                    logger.warning("ai_no_onvif_url", camera=cam.name)
                    continue
                w = _build_onvif_worker(cam)
            else:
                if not cam.stream_sub_uri and not cam.stream_main_uri:
                    logger.warning("ai_no_stream_uri", camera=cam.name)
                    continue
                w = _build_server_worker(cam)

            if w is None:
                continue
            _workers[cam.id] = w
            await w.start()
            logger.info("ai_worker_added", camera=cam.name, id=str(cam.id))


def _build_server_worker(cam) -> FrameSampler:
    import contextlib

    password: str | None = None
    if cam.encrypted_password:
        with contextlib.suppress(Exception):
            from app.core.security import decrypt_password_aes
            password = decrypt_password_aes(cam.encrypted_password)

    stream_uri = cam.stream_sub_uri or cam.stream_main_uri
    if not stream_uri:
        return None

    return FrameSampler(
        camera_id=cam.id,
        camera_name=cam.name,
        stream_uri=stream_uri,
        username=cam.username,
        password=password,
        ai_objects=cam.ai_objects,
        ai_sensitivity=cam.ai_sensitivity,
        ai_min_confidence=cam.ai_min_confidence,
        db_session_factory=SessionFactory,
        event_callback=_broadcast_event,
    )


def _build_onvif_worker(cam):
    import contextlib

    password: str | None = None
    if cam.encrypted_password:
        with contextlib.suppress(Exception):
            from app.core.security import decrypt_password_aes
            password = decrypt_password_aes(cam.encrypted_password)

    from app.onvif_event_subscriber import OnvifEventSubscriber

    return OnvifEventSubscriber(
        camera_id=cam.id,
        camera_name=cam.name,
        events_service_url=cam.onvif_events_service_url,
        username=cam.username,
        password=password or "",
        db_session_factory=SessionFactory,
        event_callback=_broadcast_event,
    )


async def _broadcast_event(camera_id: uuid.UUID, objects: list, snapshot_path: str | None) -> None:
    try:
        import json

        import redis.asyncio as aioredis

        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))

        r = aioredis.from_url(f"redis://{redis_host}:{redis_port}/0")
        try:
            payload = json.dumps({
                "type": "ai_detection",
                "camera_id": str(camera_id),
                "objects": objects,
                "snapshot_path": snapshot_path,
            })
            await r.publish("nvr:events", payload)
        finally:
            await r.close()
    except Exception:
        pass


def _sleep(seconds: float) -> asyncio.Task:
    return asyncio.create_task(asyncio.sleep(seconds))


if __name__ == "__main__":
    asyncio.run(main())
