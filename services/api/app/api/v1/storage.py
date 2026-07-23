"""Storage API endpoints — manage storage backends and tiers."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user, require_admin
from ...services.recording_service import (
    create_storage_backend,
    delete_storage_backend,
    get_storage_backend,
    get_storage_usage,
    list_storage_backends,
    update_storage_backend,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


class BackendCreate(BaseModel):
    name: str
    backend_type: str
    mount_point: str | None = None
    config: dict | None = None
    total_bytes: int = 0
    available_bytes: int = 0
    priority: int = 10


class BackendUpdate(BaseModel):
    name: str | None = None
    mount_point: str | None = None
    config: dict | None = None
    total_bytes: int | None = None
    available_bytes: int | None = None
    priority: int | None = None
    is_active: bool | None = None


# ── list all ──
@router.get("/backends")
async def get_backends(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await list_storage_backends(db)


# ── create ──
@router.post("/backends", status_code=status.HTTP_201_CREATED)
async def add_backend(
    body: BackendCreate,
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    backend = await create_storage_backend(
        db,
        name=body.name,
        backend_type=body.backend_type,
        mount_point=body.mount_point,
        config=body.config,
        total_bytes=body.total_bytes,
        available_bytes=body.available_bytes,
        priority=body.priority,
    )
    return {"data": _backend_to_response(backend)}


# ── usage ──
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


# ── get / update / delete by id ──
@router.get("/backends/{backend_id}")
async def get_backend(
    backend_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    backend = await get_storage_backend(backend_id, db)
    return {"data": _backend_to_response(backend)}


@router.patch("/backends/{backend_id}")
async def edit_backend(
    backend_id: uuid.UUID,
    body: BackendUpdate,
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    backend = await update_storage_backend(
        backend_id,
        db,
        name=body.name,
        mount_point=body.mount_point,
        config=body.config,
        total_bytes=body.total_bytes,
        available_bytes=body.available_bytes,
        priority=body.priority,
        is_active=body.is_active,
    )
    return {"data": _backend_to_response(backend)}


@router.delete("/backends/{backend_id}")
async def remove_backend(
    backend_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await delete_storage_backend(backend_id, db)
    return {"data": {"deleted": str(backend_id)}}


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


def _backend_to_response(b) -> dict:
    return {
        "id": str(b.id),
        "name": b.name,
        "backend_type": b.backend_type,
        "mount_point": b.mount_point,
        "config": b.config,
        "total_bytes": b.total_bytes,
        "available_bytes": b.available_bytes,
        "priority": b.priority,
        "is_active": b.is_active,
        "health_status": b.health_status,
        "last_health_check": b.last_health_check.isoformat() if b.last_health_check else None,
    }
