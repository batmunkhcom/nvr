"""System config service — DB-backed configuration with env fallback (Rule 1: no hardcode)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.system_config import SystemConfig


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
