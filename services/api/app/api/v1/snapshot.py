"""Camera snapshot capture — grabs a JPEG frame via FFmpeg and returns a data URL."""

from __future__ import annotations

import asyncio
import base64
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from ...core.database import get_db
from ...middleware.auth import get_current_user

logger = structlog.get_logger()

router = APIRouter()


@router.post("/api/v1/cameras/{camera_id}/snapshot")
async def capture_snapshot(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Capture a JPEG snapshot from the camera's sub-stream via FFmpeg and return as base64."""
    from ...services.camera_service import get_camera
    from ...core.security import decrypt_password_aes

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
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt camera password",
            )

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

    ffmpeg_path = "ffmpeg"
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", camera.rtsp_transport or "tcp",
            "-i", authed_uri,
            "-vframes", "1",
            "-q:v", "5",
            "-f", "image2",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=8.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Snapshot capture timed out",
            )

        if proc.returncode != 0 or not stdout:
            err = stderr.decode("utf-8", errors="replace")[:200] if stderr else "no output"
            logger.warning("snapshot_ffmpeg_failed", camera_id=str(camera_id), error=err)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to capture snapshot from camera stream",
            )

        b64 = base64.b64encode(stdout).decode()
        return {
            "data": {
                "snapshot_url": f"data:image/jpeg;base64,{b64}",
                "taken_at": None,
                "resolution": "auto",
            }
        }

    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="FFmpeg is not installed",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("snapshot_unexpected_error", camera_id=str(camera_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error capturing snapshot",
        )
