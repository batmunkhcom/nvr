"""System endpoints — health, metrics, config, logs."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import require_admin
from ...models.system_config import SystemConfig
from ...services.recording_service import get_recording_stats
from ...services.self_test import run_self_test

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health")
async def health():
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
            "cameras": {"total": 0, "online": 0, "offline": 0},
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
