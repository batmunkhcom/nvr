"""Counter API endpoints — object count statistics."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user
from ...services.counter_service import get_counter_hourly, get_counter_summary, get_counter_per_camera

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/counters", tags=["counters"])


@router.get("/summary")
async def counter_summary(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    camera_id: uuid.UUID | None = Query(None),
    days: int = Query(7, ge=1, le=90),
):
    summary = await get_counter_summary(db, str(camera_id) if camera_id else None, days)
    return {"data": summary}


@router.get("/hourly")
async def counter_hourly(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    camera_id: uuid.UUID = Query(...),
    target_date: str = Query(..., description="YYYY-MM-DD"),
):
    try:
        parsed_date = date.fromisoformat(target_date)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")
    data = await get_counter_hourly(db, str(camera_id), parsed_date)
    return {"data": data}


@router.get("/per-camera")
async def counter_per_camera(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(7, ge=1, le=90),
):
    data = await get_counter_per_camera(db, days)
    return {"data": data}
