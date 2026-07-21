"""Recording service — business logic for recordings and storage."""

from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.recording import Recording
from ..models.storage_backend import StorageBackend

logger = structlog.get_logger()


async def list_recordings(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 25,
    camera_id: uuid.UUID | None = None,
    recording_type: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict:
    offset = (page - 1) * per_page
    query = select(Recording)

    if camera_id:
        query = query.where(Recording.camera_id == camera_id)
    if recording_type:
        query = query.where(Recording.recording_type == recording_type)
    if from_time:
        query = query.where(Recording.start_time >= from_time)
    if to_time:
        query = query.where(Recording.end_time <= to_time)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(Recording.start_time.desc()).offset(offset).limit(per_page)
    )
    recordings = result.scalars().all()

    return {
        "data": [_recording_to_dict(r) for r in recordings],
        "metadata": {"page": page, "per_page": per_page, "total": total},
    }


async def get_recording(recording_id: uuid.UUID, db: AsyncSession) -> Recording:
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    recording = result.scalar_one_or_none()
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return recording


async def delete_recording(recording_id: uuid.UUID, db: AsyncSession) -> None:
    recording = await get_recording(recording_id, db)
    await db.delete(recording)
    await db.flush()
    logger.info("recording_deleted", recording_id=str(recording_id))


async def list_storage_backends(db: AsyncSession) -> dict:
    result = await db.execute(select(StorageBackend).order_by(StorageBackend.priority))
    backends = result.scalars().all()
    return {"data": [_backend_to_dict(b) for b in backends]}


async def get_storage_backend(backend_id: uuid.UUID, db: AsyncSession) -> StorageBackend:
    result = await db.execute(select(StorageBackend).where(StorageBackend.id == backend_id))
    backend = result.scalar_one_or_none()
    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Storage backend not found"
        )
    return backend


def _recording_to_dict(r: Recording) -> dict:
    return {
        "id": str(r.id),
        "camera_id": str(r.camera_id),
        "file_path": r.file_path,
        "file_size_bytes": r.file_size_bytes,
        "duration_seconds": r.duration_seconds,
        "start_time": r.start_time.isoformat() if r.start_time else None,
        "end_time": r.end_time.isoformat() if r.end_time else None,
        "recording_type": r.recording_type,
        "has_audio": r.has_audio,
        "resolution": r.resolution,
        "codec": r.codec,
        "is_corrupt": r.is_corrupt,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _backend_to_dict(b: StorageBackend) -> dict:
    return {
        "id": str(b.id),
        "name": b.name,
        "backend_type": b.backend_type,
        "total_bytes": b.total_bytes,
        "available_bytes": b.available_bytes,
        "priority": b.priority,
        "is_active": b.is_active,
        "health_status": b.health_status,
        "last_health_check": b.last_health_check.isoformat() if b.last_health_check else None,
    }
