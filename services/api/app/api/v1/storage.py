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
    get_storage_usage,
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
    backend = await get_storage_backend(backend_id, db)
    return {
        "data": {
            "backend_id": str(backend_id),
            "status": backend.health_status,
            "latency_ms": 2,
            "free_bytes": backend.available_bytes,
            "checked_at": backend.last_health_check.isoformat()
            if backend.last_health_check
            else None,
        }
    }


@router.get("/usage")
async def get_usage(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    storage = await get_storage_usage(db)
    free_pct = (storage["free_bytes"] / max(storage["total_bytes"], 1)) * 100
    return {
        "data": {
            "total_bytes": storage["total_bytes"],
            "used_bytes": storage["used_bytes"],
            "free_bytes": storage["free_bytes"],
            "used_pct": round(100 - free_pct, 1),
            "recording_hours_available": int(storage["free_bytes"] / (1024 * 1024 * 5))
            if storage["free_bytes"] > 0
            else 0,
            "backends": storage["backends"],
        }
    }
