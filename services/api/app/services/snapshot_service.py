"""Snapshot capture helper — shared by REST endpoint and AI service."""

from __future__ import annotations

import asyncio
import uuid
from urllib.parse import urlparse, urlunparse

import structlog
from fastapi import HTTPException, status

from ..core.database import async_session_factory
from ..core.security import decrypt_password_aes
from ..services.camera_service import get_camera

logger = structlog.get_logger()


async def capture_snapshot_b64(camera_id: uuid.UUID) -> str:
    """Capture a JPEG frame from the camera's sub-stream and return as raw b64 string."""
    async with async_session_factory() as db:
        camera = await get_camera(camera_id, db)

    if camera.status != "online":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Camera is not online — cannot capture snapshot",
        )

    rtsp_uri = camera.stream_sub_uri or camera.stream_main_uri
    if not rtsp_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camera has no stream URI configured",
        )

    password = None
    if camera.username and camera.encrypted_password:
        try:
            password = decrypt_password_aes(camera.encrypted_password)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt camera password",
            ) from exc

    authed_uri = rtsp_uri
    if camera.username and password:
        parsed = urlparse(rtsp_uri)
        authed_uri = urlunparse(
            parsed._replace(
                netloc=f"{camera.username}:{password}@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
        )

    ffmpeg_path = "ffmpeg"
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            camera.rtsp_transport or "tcp",
            "-i",
            authed_uri,
            "-vframes",
            "1",
            "-q:v",
            "5",
            "-f",
            "image2",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8.0)
        except TimeoutError:
            proc.kill()
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Snapshot capture timed out",
            ) from None

        if proc.returncode != 0 or not stdout:
            err = stderr.decode("utf-8", errors="replace")[:200] if stderr else "no output"
            logger.warning("snapshot_ffmpeg_failed", camera_id=str(camera_id), error=err)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to capture snapshot from camera stream",
            )

        import base64

        return base64.b64encode(stdout).decode()

    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="FFmpeg is not installed",
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("snapshot_unexpected_error", camera_id=str(camera_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error capturing snapshot",
        ) from exc
