"""Storage API endpoints — manage storage backends and tiers."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user
from ...services.recording_service import (
    get_storage_backend,
    list_storage_backends,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


@router.get("/backends")
async def get_backends(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await list_storage_backends(db)


@router.get("/backends/{backend_id}")
async def get_backend(
    backend_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    backend = await get_storage_backend(backend_id, db)
    return {"data": backend}


@router.get("/backends/{backend_id}/health")
async def get_backend_health(
    backend_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return {
        "data": {
            "backend_id": str(backend_id),
            "status": "healthy",
            "latency_ms": 0,
            "free_bytes": 0,
            "checked_at": None,
        }
    }


@router.get("/usage")
async def get_storage_usage(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    return {
        "data": {
            "total_bytes": 0,
            "used_bytes": 0,
            "free_bytes": 0,
            "used_pct": 0,
            "recording_hours_available": 0,
        }
    }
