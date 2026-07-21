"""Recording service — business logic for recordings and storage."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

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


async def get_timeline_segments(
    camera_id: uuid.UUID,
    date_str: str,
    db: AsyncSession,
) -> list[dict]:
    """Get recording segments for a camera on a specific date.

    Returns a list of timeline segments with start/end times.
    """
    day_start = datetime.fromisoformat(date_str)
    day_end = day_start + timedelta(days=1)

    result = await db.execute(
        select(Recording)
        .where(
            Recording.camera_id == camera_id,
            Recording.start_time >= day_start,
            Recording.start_time < day_end,
        )
        .order_by(Recording.start_time.asc())
    )
    recordings = result.scalars().all()

    segments = []
    for r in recordings:
        segments.append(
            {
                "camera_id": str(r.camera_id),
                "start_time": r.start_time.isoformat(),
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "recording_type": r.recording_type,
                "has_motion": r.recording_type in ("motion", "event"),
            }
        )
    return segments


async def get_storage_usage(db: AsyncSession) -> dict:
    """Aggregate storage usage across all backends."""
    result = await db.execute(select(StorageBackend).where(StorageBackend.is_active.is_(True)))
    backends = result.scalars().all()

    total = sum(b.total_bytes for b in backends)
    available = sum(b.available_bytes for b in backends)
    used = total - available

    return {
        "total_bytes": total,
        "used_bytes": max(used, 0),
        "free_bytes": max(available, 0),
        "backends": [_backend_to_dict(b) for b in backends],
    }


async def get_recording_stats(db: AsyncSession) -> dict:
    """Get recording statistics for the last 24 hours."""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(func.count()).select_from(
            select(Recording).where(Recording.start_time >= since).subquery()
        )
    )
    total_24h = result.scalar() or 0

    result = await db.execute(
        select(
            func.coalesce(func.sum(Recording.file_size_bytes), 0),
            func.coalesce(func.sum(Recording.duration_seconds), 0),
        ).where(Recording.start_time >= since)
    )
    total_bytes, total_duration = result.one()

    return {
        "recordings_24h": total_24h,
        "storage_bytes_24h": total_bytes,
        "recording_seconds_24h": int(total_duration),
    }
