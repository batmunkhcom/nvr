"""AI engine endpoints — snapshot analysis, motion detection, Ollama chat."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...middleware.auth import get_current_user, require_admin
from ...services.ai_service import (
    analyze_image,
    is_ai_enabled,
    ollama_chat,
    ollama_health,
    ollama_summarize,
)
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


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    camera_id: str | None = None


class SummarizeRequest(BaseModel):
    camera_id: str
    date: str  # YYYY-MM-DD


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


@router.post("/chat")
async def chat_with_ai(
    body: ChatRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Chat with Ollama about security events, optionally with a camera snapshot."""
    b64_image = None
    if body.camera_id:
        try:
            camera_uuid = uuid.UUID(body.camera_id)
            b64_image = await capture_snapshot_b64(camera_uuid)
        except Exception:
            pass

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    response = await ollama_chat(messages, b64_image)
    return {"data": {"response": response}}


@router.post("/summarize")
async def summarize_events(
    body: SummarizeRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Summarize events for a camera on a given date."""
    try:
        camera_uuid = uuid.UUID(body.camera_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid camera_id") from err

    summary = await ollama_summarize(camera_uuid, body.date)
    return {"data": {"summary": summary}}


@router.get("/health")
async def ollama_health_check():
    """Check if Ollama server is reachable."""
    ok = await ollama_health()
    return {"data": {"ollama_reachable": ok}}
