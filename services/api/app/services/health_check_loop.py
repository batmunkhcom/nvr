"""Background camera health-check loop — periodically pings all cameras and updates DB status."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import async_session_factory
from ..models.camera import Camera
from ..services.camera_probe import probe_ip

logger = structlog.get_logger()


async def _check_single(camera: Camera) -> dict[str, Any]:
    cam_id = str(camera.id)
    rtsp_uri = camera.stream_main_uri or camera.stream_sub_uri
    prev_status = (camera.status or "unknown").lower()

    async def _notify_if_changed(new_status: str, error_msg: str | None = None):
        if new_status != prev_status and prev_status != "online":
            try:
                from .notification_service import send_camera_alert
                await send_camera_alert(
                    camera_id=cam_id,
                    camera_name=camera.name or cam_id,
                    status=new_status,
                    error_message=error_msg,
                )
            except Exception:
                pass
        elif new_status == "online" and prev_status != "online":
            try:
                from .notification_service import send_camera_alert
                await send_camera_alert(
                    camera_id=cam_id,
                    camera_name=camera.name or cam_id,
                    status=new_status,
                )
            except Exception:
                pass

    try:
        probe_result = await probe_ip(
            camera.ip_address or "", port=554, timeout=3.0
        )
        if not probe_result.get("reachable") or 554 not in probe_result.get("open_ports", []):
            err = "Camera unreachable on port 554"
            async with async_session_factory() as session:
                await session.execute(
                    update(Camera)
                        .where(Camera.id == camera.id)
                        .values(status="offline", connection_error=err)
                )
                await session.commit()
            await _notify_if_changed("offline", err)
            return {"status": "offline", "error_code": "unreachable"}

        if not rtsp_uri:
            err = "No stream URI configured"
            async with async_session_factory() as session:
                await session.execute(
                    update(Camera)
                        .where(Camera.id == camera.id)
                        .values(status="offline", connection_error=err)
                )
                await session.commit()
            await _notify_if_changed("offline", err)
            return {"status": "offline", "error_code": "no_stream_uri"}

        from ..services.camera_rtsp_check import check_rtsp_stream
        from ..core.security import decrypt_password_aes

        password = None
        if camera.encrypted_password:
            password = decrypt_password_aes(camera.encrypted_password)
        check_result = await check_rtsp_stream(
            rtsp_uri, username=camera.username, password=password, timeout=6.0
        )
        auth_ok = getattr(check_result, "authorized", True)
        error_msg = str(check_result.error_message) if not auth_ok else None
        error_code = getattr(check_result, "error_code", None) if not auth_ok else None

        async with async_session_factory() as session:
            if not auth_ok:
                await session.execute(
                    update(Camera)
                        .where(Camera.id == camera.id)
                        .values(status="degraded", connection_error=error_msg[:500])
                )
                await session.commit()
                await _notify_if_changed("degraded", error_msg)
                return {"status": "degraded", "error_code": error_code}

            await session.execute(
                update(Camera)
                    .where(Camera.id == camera.id)
                    .values(status="online", connection_error=None)
            )
            await session.commit()
            await _notify_if_changed("online")
            return {"status": "online"}

    except Exception as exc:
        logger.error("health_check_error", camera_id=cam_id, error=str(exc))
        return {"status": "unknown"}


_health_check_task: asyncio.Task[None] | None = None


async def health_check_loop(interval_s: int) -> None:
    logger.info("health_check_loop_starting", interval_seconds=interval_s)
    while True:
        start = asyncio.get_event_loop().time()
        try:
            query = select(Camera).where(
                Camera.status.in_(["online", "offline", "degraded", "unknown"])
            )
            async with async_session_factory() as session:
                result_query = await session.execute(query)
                cameras = result_query.scalars().all()

            if cameras:
                results = await asyncio.gather(
                    *[_check_single(cam) for cam in cameras],
                    return_exceptions=True,
                )
                degraded = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "degraded")
                offline = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "offline")
                logger.info(
                    "health_check_loop_iteration",
                    cameras_checked=len(cameras),
                    degraded=degraded,
                    offline=offline,
                )
        except Exception as exc:
            logger.error("health_check_loop_error", error=str(exc))

        elapsed = asyncio.get_event_loop().time() - start
        delay = max(interval_s - elapsed, 0.5)
        await asyncio.sleep(delay)


def start_health_check(interval_s: int | None = None) -> None:
    global _health_check_task
    if _health_check_task and not _health_check_task.done():
        logger.info("health_check_loop_already_running")
        return

    async def _wrapper() -> None:
        try:
            effective = interval_s or 120
            try:
                from .config_service import get_config_int
                async with async_session_factory() as session:
                    db_interval = await get_config_int(session, "camera.health_check_interval_s", 0)
                if db_interval and db_interval >= 30:
                    effective = db_interval
            except Exception:
                pass
            await health_check_loop(effective)
        except asyncio.CancelledError:
            logger.info("health_check_loop_stopped")

    _health_check_task = asyncio.create_task(_wrapper())
    logger.info("health_check_loop_started", interval=interval_s or 120)


def stop_health_check() -> None:
    global _health_check_task
    if _health_check_task and not _health_check_task.done():
        _health_check_task.cancel()
        logger.info("health_check_loop_cancelled")
    _health_check_task = None
