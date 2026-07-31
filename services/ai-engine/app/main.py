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
from zoneinfo import ZoneInfo

import structlog

from . import db
from .detector import AIDetector
from .frame_sampler import FrameSampler
from .onvif_callback_server import OnvifCallbackServer
from .plugins import get_plugins_for_camera, start_all, stop_all

logger = structlog.get_logger()

_STREAM_MANAGER_URL = os.environ.get(
    "STREAM_MANAGER_URL", "http://nvr-stream-manager:8001"
)

POLL_INTERVAL = 15
SHUTDOWN = asyncio.Event()

_workers: dict[str, object] = {}
_signatures: dict[str, tuple] = {}


def _signature(cam: dict) -> tuple:
    """Config fingerprint — worker is recreated when this changes."""
    return (
        cam["stream_sub_uri"],
        cam["stream_main_uri"],
        cam["username"],
        cam["encrypted_password"],
        json.dumps(cam["ai_objects"], sort_keys=True),
        cam["ai_sensitivity"],
        cam["ai_min_confidence"],
        json.dumps(cam["ai_zones"]),
        cam["motion_source"],
        cam["onvif_events_service_url"],
        cam["ai_enabled"],
        cam.get("recording_mode"),
        cam.get("recording_stream"),
        cam.get("storage_mount_point"),
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
        worker = await _build_worker(cam)
        if worker is None:
            continue
        _workers[cam["id"]] = worker
        _signatures[cam["id"]] = sig
        await worker.start()
        logger.info("ai_worker_added", camera=cam["name"], camera_id=cam["id"])


def _resolve_ai_stream(cam: dict) -> tuple[bool, str | None, str]:
    """Pick the stream URI and MediaMTX relay key for AI sampling.

    Uses the camera's `recording_stream` setting to keep recording and AI on
    the same stream by default. Falls back to the other stream if the chosen
    one is not configured.

    Returns:
        (use_main, stream_uri, relay_key)
    """
    cid = str(cam["id"])
    use_main = (cam.get("recording_stream") or "").lower() == "main"
    if use_main:
        stream_uri = cam["stream_main_uri"] or cam["stream_sub_uri"]
        relay_key = cid
    else:
        stream_uri = cam["stream_sub_uri"] or cam["stream_main_uri"]
        relay_key = f"{cid}_sub"
    return use_main, stream_uri, relay_key


async def _build_worker(cam: dict):
    password = db.decrypt_password(cam["encrypted_password"])

    if cam["motion_source"] == "camera":
        if not cam["onvif_events_service_url"]:
            logger.warning("ai_no_onvif_url", camera=cam["name"])
            return None
        from .onvif_base_subscriber import OnvifBaseSubscriber

        return OnvifBaseSubscriber(
            camera_id=cam["id"],
            camera_name=cam["name"],
            events_service_url=cam["onvif_events_service_url"],
            username=cam["username"],
            password=password or "",
            event_callback=_broadcast_event,
        )

    use_main, stream_uri, relay_key = _resolve_ai_stream(cam)
    if not stream_uri:
        logger.warning("ai_no_stream_uri", camera=cam["name"])
        return None
    logger.info(
        "ai_stream_selected",
        camera=cam["name"],
        recording_stream=cam.get("recording_stream"),
        use_main=use_main,
        stream_uri=stream_uri,
        relay_key=relay_key,
    )

    # Prefer MediaMTX relay over direct camera RTSP to avoid session conflicts.
    # The stream-manager already maintains one RTSP session per camera; sharing
    # eliminates the second session that cameras often reject.
    mediamtx_rtsp = os.environ.get("MEDIAMTX_RTSP_HOST", "nvr-mediamtx")
    relay_uri = f"rtsp://{mediamtx_rtsp}:8554/{relay_key}"
    # Use relay if camera auth is set (implies stream-manager handles it),
    # otherwise fall back to direct RTSP.
    use_relay = bool(cam.get("username"))
    final_uri = relay_uri if use_relay else stream_uri

    def _ensure_relay() -> None:
        """(Re)start the stream-manager relay — the sampler's lifeline.

        Called at worker build AND whenever capture fails: the idle reaper can
        stop the relay during a long sampler reconnect gap, and a single
        one-shot attempt would leave the camera dark forever. The URI must
        carry credentials — MediaMTX pull and FFmpeg relay both authenticate
        against the camera with them.
        """
        from .frame_sampler import build_rtsp_url

        authed_uri = build_rtsp_url(stream_uri, cam["username"], password)
        try:
            import httpx
            httpx.post(
                f"{_STREAM_MANAGER_URL}/relay/start",
                json={"relay_key": relay_key, "rtsp_uri": authed_uri, "transport": "tcp"},
                timeout=5,
            )
            logger.debug("ai_relay_started", camera=cam["name"], relay_key=relay_key)
        except Exception:
            logger.warning("ai_relay_start_failed", camera=cam["name"])

    on_capture_failed = None
    if use_relay:
        _ensure_relay()
        relay_retry_ts = 0.0

        async def on_capture_failed() -> None:
            nonlocal relay_retry_ts
            now = asyncio.get_running_loop().time()
            if now - relay_retry_ts < 15:
                return
            relay_retry_ts = now
            await asyncio.to_thread(_ensure_relay)

    # motion-only worker: publishes motion state for motion-mode recording
    # (no YOLO) when AI detection is disabled for this camera
    motion_only = not cam["ai_enabled"] and cam.get("recording_mode") == "motion"

    plugins = get_plugins_for_camera(cam.get("ai_plugins"))

    target_fps = await db.read_config_float("ai.target_fps", 3.0)
    tz_str = await db.read_timezone()
    tz = ZoneInfo(tz_str)

    return FrameSampler(
        camera_id=cam["id"],
        camera_name=cam["name"],
        stream_uri=final_uri,
        username=None if use_relay else cam["username"],
        password=None if use_relay else password,
        ai_objects=cam["ai_objects"],
        ai_sensitivity=cam["ai_sensitivity"],
        ai_min_confidence=cam["ai_min_confidence"],
        ai_zones=cam["ai_zones"],
        motion_only=motion_only,
        event_callback=_broadcast_event,
        plugins=plugins,
        storage_path=cam.get("storage_mount_point"),
        on_capture_failed=on_capture_failed,
        target_fps=target_fps,
        tz=tz,
    )


async def _broadcast_event(camera_id: str, objects: list, snapshot_path: str | None) -> None:
    """Publish detection events to Redis for the API websocket bridge."""
    await db.RedisPublisher.shared().publish(
        "nvr:events",
        {
            "type": "ai_detection",
            "camera_id": camera_id,
            "objects": objects,
            "snapshot_path": snapshot_path,
        },
    )


async def _log_onvif_health() -> None:
    """Emit a periodic summary of ONVIF callback registrations and last events."""
    while not SHUTDOWN.is_set():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        server = OnvifCallbackServer()
        if server.handler_count():
            logger.info(
                "onvif_callback_health",
                handlers=server.handler_count(),
                last_events={
                    cid: server.last_event_time(cid)
                    for cid in list(server._handlers.keys())[:10]
                },
            )


async def main() -> None:
    import signal
    from concurrent.futures import ThreadPoolExecutor

    logger.info("ai_engine_starting", version="1.0.0")

    loop = asyncio.get_running_loop()
    # Bound the blocking-work executor: the default sizes off HOST cpu count
    # (min(32, cpu+4)) while the container is capped at 2 — oversubscription
    # queues inference behind cap.read() calls on many-camera hosts.
    loop.set_default_executor(ThreadPoolExecutor(max_workers=6, thread_name_prefix="ai-io"))
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, SHUTDOWN.set)

    await start_all()

    # Start the shared ONVIF callback server once.  Camera subscribers
    # register their per-camera paths with this server instead of each
    # trying to bind port 8091 independently.
    onvif_server = OnvifCallbackServer()
    await onvif_server.start()
    health_task = asyncio.create_task(_log_onvif_health())

    # Per-camera detection model override via system_config, fallback to env
    detection_model = await db.read_config_str("ai.detection_model", "")
    if detection_model:
        os.environ["AI_YOLO_MODEL"] = detection_model
        logger.info("ai_detection_model_configured", model=detection_model)

    detector = AIDetector.shared()
    model_ok = await detector.initialize()
    if not model_ok:
        logger.error(
            "ai_model_unavailable",
            path=detector.model_path,
            hint="mount ONNX models into the ai_models volume",
        )

    try:
        while not SHUTDOWN.is_set():
            if not detector.ready:
                # Keep retrying in the background; detection no-ops until ready,
                # but motion-only and ONVIF workers must run regardless.
                model_ok = await detector.initialize()
            # Always reconcile — a missing YOLO model must not disable
            # motion-mode recording or ONVIF subscriptions.
            with contextlib.suppress(Exception):
                await _reconcile()
            await asyncio.sleep(POLL_INTERVAL)
    finally:
        health_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await health_task
        for worker in list(_workers.values()):
            await worker.stop()
        await onvif_server.stop()
        await stop_all()
        await db.engine.dispose()
        logger.info("ai_engine_stopped")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
