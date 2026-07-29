"""System config service — DB-backed configuration with env fallback (Rule 1: no hardcode)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.system_config import SystemConfig

logger = structlog.get_logger()

_DEFAULT_TZ = "Asia/Ulaanbaatar"


async def get_config_value(db: AsyncSession, key: str, default: Any = None) -> Any:
    """Read a single key from system_config; return default when unset."""
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    row = result.scalar_one_or_none()
    return row.value if row is not None else default


async def get_config_int(db: AsyncSession, key: str, default: int) -> int:
    """Read a config key coerced to int (guards against bad stored values)."""
    value = await get_config_value(db, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def get_timezone(db: AsyncSession) -> ZoneInfo:
    """Return the configured system timezone (ZoneInfo), defaulting to Asia/Ulaanbaatar."""
    tz_str = str(await get_config_value(db, "ui.timezone", _DEFAULT_TZ))
    try:
        return ZoneInfo(tz_str)
    except ZoneInfoNotFoundError:
        logger.warning("timezone_not_found", configured=tz_str, falling_back=_DEFAULT_TZ)
        return ZoneInfo(_DEFAULT_TZ)


def local_date(tz: ZoneInfo) -> date:
    """Today's date in the given timezone."""
    return datetime.now(tz).date()
