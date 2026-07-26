"""AI Engine — main entry point.

Reconciles per-camera AI workers from the DB:
- motion_source="server" -> FrameSampler (RTSP frame sampling + ONNX YOLO)
- motion_source="camera" -> OnvifEventSubscriber (camera's built-in analytics)

Self-contained: plain SQL via app.db (no cross-service model imports).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os

import structlog

from . import db
from .detector import AIDetector
from .frame_sampler import FrameSampler
from .plugins import get_plugins_for_camera, start_all, stop_all

logger = structlog.get_logger()

POLL_INTERVAL = 15
SHUTDOWN = asyncio.Event()

_workers: dict[str, object] = {}
_signatures: dict[str, tuple] = {}


def _signature(cam: dict) -> tuple:
    """Config fingerprint — worker is recreated when this changes."""
    return (
        cam["stream_sub_uri"],
        cam["stream_main_uri"],
        json.dumps(cam["ai_objects"], sort_keys=True),
        cam["ai_sensitivity"],
        cam["ai_min_confidence"],
        json.dumps(cam["ai_zones"]),
        cam["motion_source"],
        cam["onvif_events_service_url"],
        cam["ai_enabled"],
        cam.get("recording_mode"),
        json.dumps(cam.get("ai_plugins"), sort_keys=True),
    )


async def _reconcile() -> None:
    try:
        async with db.SessionFactory() as session:
            cameras = await db.load_ai_cameras(session)
    except Exception:
        logger.error("ai_camera_load_failed", exc_info=True)
        return

    desired = {c["id"] for c in cameras}
    for cam_id in set(_workers) - desired:
        worker = _workers.pop(cam_id)
        _signatures.pop(cam_id, None)
        await worker.stop()
        logger.info("ai_worker_removed", camera_id=cam_id)

    for cam in cameras:
        sig = _signature(cam)
        if cam["id"] in _workers:
            if _signatures.get(cam["id"]) == sig:
                continue
            # config changed (zones, objects, stream...) -> recreate worker
            await _workers.pop(cam["id"]).stop()
            _signatures.pop(cam["id"], None)
            logger.info("ai_worker_reloading", camera=cam["name"])
        worker = _build_worker(cam)
        if worker is None:
            continue
        _workers[cam["id"]] = worker
        _signatures[cam["id"]] = sig
        await worker.start()
        logger.info("ai_worker_added", camera=cam["name"], camera_id=cam["id"])


def _build_worker(cam: dict):
    password = db.decrypt_password(cam["encrypted_password"])

    if cam["motion_source"] == "camera":
        if not cam["onvif_events_service_url"]:
            logger.warning("ai_no_onvif_url", camera=cam["name"])
            return None
        from .onvif_event_subscriber import OnvifEventSubscriber

        return OnvifEventSubscriber(
            camera_id=cam["id"],
            camera_name=cam["name"],
            events_service_url=cam["onvif_events_service_url"],
            username=cam["username"],
            password=password or "",
            event_callback=_broadcast_event,
        )

    stream_uri = cam["stream_sub_uri"] or cam["stream_main_uri"]
    if not stream_uri:
        logger.warning("ai_no_stream_uri", camera=cam["name"])
        return None

    # motion-only worker: publishes motion state for motion-mode recording
    # (no YOLO) when AI detection is disabled for this camera
    motion_only = not cam["ai_enabled"] and cam.get("recording_mode") == "motion"

    plugins = get_plugins_for_camera(cam.get("ai_plugins"))

    return FrameSampler(
        camera_id=cam["id"],
        camera_name=cam["name"],
        stream_uri=stream_uri,
        username=cam["username"],
        password=password,
        ai_objects=cam["ai_objects"],
        ai_sensitivity=cam["ai_sensitivity"],
        ai_min_confidence=cam["ai_min_confidence"],
        ai_zones=cam["ai_zones"],
        motion_only=motion_only,
        event_callback=_broadcast_event,
        plugins=plugins,
        storage_path=cam.get("storage_mount_point"),
    )


async def _broadcast_event(camera_id: str, objects: list, snapshot_path: str | None) -> None:
    """Publish detection events to Redis for the API websocket bridge."""
    try:
        import redis.asyncio as aioredis

        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        r = aioredis.from_url(f"redis://{redis_host}:{redis_port}/0")
        try:
            await r.publish(
                "nvr:events",
                json.dumps(
                    {
                        "type": "ai_detection",
                        "camera_id": camera_id,
                        "objects": objects,
                        "snapshot_path": snapshot_path,
                    }
                ),
            )
        finally:
            await r.close()
    except Exception:
        pass


async def main() -> None:
    logger.info("ai_engine_starting", version="1.0.0")

    await start_all()

    detector = AIDetector.shared()
    model_ok = await detector.initialize()
    if not model_ok:
        logger.error(
            "ai_model_unavailable",
            path=detector.model_path,
            hint="mount yolov8n.onnx into the ai_models volume",
        )

    while not SHUTDOWN.is_set():
        if not detector.ready:
            model_ok = await detector.initialize()
        if model_ok:
            with contextlib.suppress(Exception):
                await _reconcile()
        await asyncio.sleep(POLL_INTERVAL)

    for worker in list(_workers.values()):
        await worker.stop()
    await stop_all()
    await db.engine.dispose()
    logger.info("ai_engine_stopped")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
