"""LPR API endpoints — license plate readings and pattern library."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user
from ...services.lpr_service import get_lpr_readings

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/lpr", tags=["lpr"])


@router.get("/patterns")
async def lpr_patterns(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    from nvr_common.lpr_patterns import LPR_PATTERNS

    return {"data": LPR_PATTERNS}


@router.get("/readings")
async def lpr_readings(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    camera_id: uuid.UUID | None = None,
    plate_number: str | None = None,
    days: int = Query(7, ge=1, le=90),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    return await get_lpr_readings(
        db,
        camera_id=str(camera_id) if camera_id else None,
        plate_number=plate_number,
        days=days,
        page=page,
        per_page=per_page,
    )
