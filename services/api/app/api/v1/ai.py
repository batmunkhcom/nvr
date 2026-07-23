"""AI engine endpoints — snapshot analysis, motion detection control."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...middleware.auth import get_current_user, require_admin
from ...services.ai_service import analyze_image, is_ai_enabled
from ...services.motion_detector import (
    get_motion_status,
    start_motion_detection,
    stop_motion_detection,
)
from ...services.snapshot_service import capture_snapshot_b64

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class AnalyzeRequest(BaseModel):
    camera_id: str
    prompt: str = "Describe what you see in this security camera image. Focus on people, vehicles, animals, or unusual activity."


class MotionControlRequest(BaseModel):
    enabled: bool


@router.post("/analyze")
async def analyze_camera_snapshot(
    body: AnalyzeRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Take a snapshot and send it to the configured AI for analysis."""
    if not await is_ai_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI engine is not configured or disabled",
        )

    try:
        camera_uuid = uuid.UUID(body.camera_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid camera ID format",
        ) from err

    try:
        b64_image = await capture_snapshot_b64(camera_uuid)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ai_snapshot_failed", camera_id=body.camera_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to capture camera snapshot",
        ) from exc

    result = await analyze_image(b64_image, body.prompt)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "AI analysis failed"),
        )

    return {"data": {"response": result["response"], "model": result.get("model")}}


@router.get("/status")
async def ai_status(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Return whether the AI engine is configured and enabled."""
    enabled = await is_ai_enabled()
    motion = await get_motion_status()
    return {"data": {"enabled": enabled, "motion_detection": motion}}


@router.post("/motion")
async def control_motion(
    body: MotionControlRequest,
    current_user: Annotated[dict, Depends(require_admin)],
):
    """Enable or disable OpenCV motion detection."""
    if body.enabled:
        await start_motion_detection()
        return {"data": {"motion_detection": True}}
    await stop_motion_detection()
    return {"data": {"motion_detection": False}}
