"""Recordings API endpoints — browse, stream, export recordings."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user, require_admin
from ...services.recording_service import delete_recording, get_recording, list_recordings

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/recordings", tags=["recordings"])


@router.get("")
async def get_recordings(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    camera_id: uuid.UUID | None = None,
    recording_type: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
):
    return await list_recordings(
        db, page=page, per_page=per_page,
        camera_id=camera_id, recording_type=recording_type,
        from_time=from_time, to_time=to_time,
    )


@router.get("/{recording_id}")
async def get_recording_by_id(
    recording_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    recording = await get_recording(recording_id, db)
    return {"data": recording}


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recording_by_id(
    recording_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await delete_recording(recording_id, db)


@router.get("/timeline")
async def get_timeline(
    camera_id: uuid.UUID,
    date: str,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return {
        "data": {
            "camera_id": str(camera_id),
            "date": date,
            "segments": [],
        }
    }
