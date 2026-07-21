"""Recordings API endpoints — browse, stream, export recordings."""

from __future__ import annotations

import os
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user, require_admin
from ...services.recording_service import (
    delete_recording,
    get_recording,
    get_recording_stats,
    get_timeline_segments,
    list_recordings,
)

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
        db,
        page=page,
        per_page=per_page,
        camera_id=camera_id,
        recording_type=recording_type,
        from_time=from_time,
        to_time=to_time,
    )


@router.get("/timeline")
async def get_timeline(
    camera_id: uuid.UUID,
    date: str,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    segments = await get_timeline_segments(camera_id, date, db)
    return {"data": segments}


@router.get("/stats")
async def get_stats(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return {"data": await get_recording_stats(db)}


@router.get("/{recording_id}")
async def get_recording_by_id(
    recording_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    recording = await get_recording(recording_id, db)
    return {"data": recording}


@router.get("/{recording_id}/stream")
async def stream_recording(
    recording_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    recording = await get_recording(recording_id, db)
    file_path = recording.file_path
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Recording file not found on disk")

    file_size = os.path.getsize(file_path)

    def file_iterator(path: str, chunk_size: int = 1024 * 1024):
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    return StreamingResponse(
        file_iterator(file_path),
        media_type="video/mp4",
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="recording_{recording_id}.mp4"',
        },
    )


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recording_by_id(
    recording_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await delete_recording(recording_id, db)
