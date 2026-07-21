"""Two-way audio talkback service."""

from __future__ import annotations

import uuid

import structlog

logger = structlog.get_logger()


async def start_talk_session(camera_id: uuid.UUID) -> dict:
    """Start a two-way audio talkback session with camera."""
    session_id = uuid.uuid4()
    logger.info("talk_session_started", camera_id=str(camera_id), session_id=str(session_id))
    return {"session_id": str(session_id), "status": "active"}


async def stop_talk_session(session_id: uuid.UUID) -> None:
    """Stop an active talkback session."""
    logger.info("talk_session_stopped", session_id=str(session_id))
