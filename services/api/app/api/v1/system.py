"""System endpoints — health, metrics, config, logs."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user, require_admin
from ...models.camera import Camera
from ...models.system_config import SystemConfig
from ...services.recording_service import get_recording_stats
from ...services.self_test import run_self_test

router = APIRouter(prefix="/api/v1/system", tags=["system"])

UI_CONFIG_PREFIX = "ui."


class UiConfigUpdate(BaseModel):
    key: str
    value: Any


@router.get("/health")
async def health(db: Annotated[AsyncSession, Depends(get_db)]):
    total_result = await db.execute(select(func.count()).select_from(Camera))
    total = total_result.scalar() or 0
    online_result = await db.execute(
        select(func.count()).select_from(Camera).where(Camera.status == "online")
    )
    online = online_result.scalar() or 0
    offline_result = await db.execute(
        select(func.count()).select_from(Camera).where(Camera.status == "offline")
    )
    offline = offline_result.scalar() or 0

    return {
        "data": {
            "status": "healthy",
            "uptime_seconds": 0,
            "version": "0.1.0",
            "checks": {
                "database": "ok",
                "redis": "ok",
                "minio": "ok",
                "ffmpeg": "ok",
            },
            "cameras": {"total": total, "online": online, "offline": offline},
            "storage": {"total_pct": 0, "status": "ok"},
            "recording": {"active_recordings": 0, "errors_24h": 0},
        }
    }


@router.get("/config")
async def get_system_config(
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()
    return {"data": {c.key: c.value for c in configs}}


@router.patch("/config")
async def update_system_config(
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    key: str = "",
    value: str = "",
):
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()
    if config:
        config.value = value
    else:
        config = SystemConfig(key=key, value=value)
        db.add(config)
    await db.flush()
    return {"data": {"key": key, "value": value}}


@router.get("/ui-config")
async def get_ui_config(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return ui.* preferences — readable by any authenticated user."""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key.startswith(UI_CONFIG_PREFIX))
    )
    return {"data": {c.key: c.value for c in result.scalars().all()}}


@router.patch("/ui-config")
async def update_ui_config(
    body: UiConfigUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Upsert a ui.* preference — any authenticated user, ui.* keys only."""
    if not body.key.startswith(UI_CONFIG_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only '{UI_CONFIG_PREFIX}*' keys are allowed here",
        )
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == body.key))
    config = result.scalar_one_or_none()
    if config:
        config.value = body.value
        config.updated_at = datetime.now(UTC)
    else:
        config = SystemConfig(key=body.key, value=body.value)
        db.add(config)
    await db.flush()
    return {"data": {"key": body.key, "value": body.value}}


@router.get("/logs")
async def get_system_logs(
    current_user: Annotated[dict, Depends(require_admin)],
    page: int = 1,
    per_page: int = 50,
    level: str | None = None,
    component: str | None = None,
):
    return {
        "data": [],
        "metadata": {"page": page, "per_page": per_page, "total": 0},
    }


@router.get("/metrics")
async def get_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stats = await get_recording_stats(db)
    return {"data": stats}


@router.post("/self-test")
async def system_self_test(
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await run_self_test(db)
    return {"data": result}


@router.post("/notification/test")
async def test_notification(
    current_user: Annotated[dict, Depends(require_admin)],
):
    """Send a test notification through all enabled channels."""
    from ...services.notification_service import send_test_notification
    result = await send_test_notification()
    return {"data": result}
