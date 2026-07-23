"""Recording schedule CRUD — cron-like recording schedules per camera."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user, require_operator
from ...models.camera import Camera
from ...models.recording_schedule import RecordingSchedule

router = APIRouter(prefix="/api/v1/recording-schedules", tags=["recording-schedules"])


class ScheduleCreate(BaseModel):
    camera_id: str
    schedule_name: str
    schedule_type: str = "weekly"
    days_of_week: list[int] = [1, 2, 3, 4, 5, 6, 7]
    time_start: str = "00:00"
    time_end: str = "23:59"
    pre_record_seconds: int = 5
    post_record_seconds: int = 10
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    schedule_name: str | None = None
    days_of_week: list[int] | None = None
    time_start: str | None = None
    time_end: str | None = None
    pre_record_seconds: int | None = None
    post_record_seconds: int | None = None
    is_active: bool | None = None


def _schedule_to_dict(s: RecordingSchedule) -> dict:
    return {
        "id": str(s.id),
        "camera_id": str(s.camera_id),
        "schedule_name": s.schedule_name,
        "schedule_type": s.schedule_type,
        "days_of_week": s.days_of_week,
        "time_start": s.time_start.isoformat() if s.time_start else None,
        "time_end": s.time_end.isoformat() if s.time_end else None,
        "pre_record_seconds": s.pre_record_seconds,
        "post_record_seconds": s.post_record_seconds,
        "is_active": s.is_active,
    }


@router.get("")
async def list_schedules(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    camera_id: str | None = None,
):
    query = select(RecordingSchedule)
    if camera_id:
        try:
            cid = uuid.UUID(camera_id)
            query = query.where(RecordingSchedule.camera_id == cid)
        except ValueError:
            pass
    result = await db.execute(query.order_by(RecordingSchedule.schedule_name))
    return {"data": [_schedule_to_dict(s) for s in result.scalars().all()]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        cid = uuid.UUID(body.camera_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid camera_id"
        ) from None
    camera = await db.execute(select(Camera).where(Camera.id == cid))
    if not camera.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    try:
        h1, m1 = map(int, body.time_start.split(":"))
        h2, m2 = map(int, body.time_end.split(":"))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid time format (use HH:MM)"
        ) from None

    import datetime as dt

    schedule = RecordingSchedule(
        camera_id=cid,
        schedule_name=body.schedule_name,
        schedule_type=body.schedule_type,
        days_of_week=body.days_of_week,
        time_start=dt.time(h1, m1),
        time_end=dt.time(h2, m2),
        pre_record_seconds=body.pre_record_seconds,
        post_record_seconds=body.post_record_seconds,
        is_active=body.is_active,
    )
    db.add(schedule)
    await db.flush()
    return {"data": _schedule_to_dict(schedule)}


@router.patch("/{schedule_id}")
async def update_schedule(
    schedule_id: uuid.UUID,
    body: ScheduleUpdate,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(RecordingSchedule).where(RecordingSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    if body.schedule_name is not None:
        schedule.schedule_name = body.schedule_name
    if body.days_of_week is not None:
        schedule.days_of_week = body.days_of_week
    if body.time_start is not None:
        try:
            h, m = map(int, body.time_start.split(":"))
            import datetime as dt

            schedule.time_start = dt.time(h, m)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid time_start format (HH:MM)"
            ) from None
    if body.time_end is not None:
        try:
            h, m = map(int, body.time_end.split(":"))
            import datetime as dt

            schedule.time_end = dt.time(h, m)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid time_end format (HH:MM)"
            ) from None
    if body.pre_record_seconds is not None:
        schedule.pre_record_seconds = body.pre_record_seconds
    if body.post_record_seconds is not None:
        schedule.post_record_seconds = body.post_record_seconds
    if body.is_active is not None:
        schedule.is_active = body.is_active
    await db.flush()
    return {"data": _schedule_to_dict(schedule)}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(RecordingSchedule).where(RecordingSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    await db.delete(schedule)
    await db.flush()
    return {"data": {"deleted": str(schedule_id)}}
