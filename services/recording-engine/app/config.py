"""Recording engine configuration — env vars + system_config readers."""

from __future__ import annotations

import os

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# --- Environment ---
DB_HOST = os.environ.get("POSTGRES_HOST") or os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("POSTGRES_PORT") or os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB") or os.environ.get("DB_NAME", "nvr")
DB_USER = os.environ.get("POSTGRES_USER") or os.environ.get("DB_USER", "nvr")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("DB_PASSWORD", "nvr")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

STORAGE_LOCAL_PATH = os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings")
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.environ.get("FFPROBE_PATH", "ffprobe")

POLL_INTERVAL = 30  # camera reconcile loop
CATALOG_INTERVAL = 60  # segment scanner
RETENTION_INTERVAL = 300  # circular cleanup check
ANALYTICS_INTERVAL = 3600  # disk usage analysis

# --- system_config defaults (overridable from DB) ---
DEFAULTS = {
    "retention.default_days": 7,
    "storage.max_usage_percent": 85,
    "storage.min_free_gb": 2,
    "recording.segment_seconds": 300,
    "recording.stream": "sub",
}

_config_cache: dict[str, object] = {}


async def get_config(session: AsyncSession, key: str) -> object:
    """Read a system_config value, falling back to DEFAULTS. Cached per call site."""
    try:
        result = await session.execute(
            text("SELECT value FROM system_config WHERE key = :key"), {"key": key}
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
    except Exception:
        logger.warning("config_read_failed", key=key)
    return DEFAULTS.get(key)


async def get_config_int(session: AsyncSession, key: str) -> int:
    value = await get_config(session, key)
    try:
        return int(str(value).strip('"'))
    except (TypeError, ValueError):
        return int(DEFAULTS.get(key, 0))


async def get_config_str(session: AsyncSession, key: str) -> str:
    value = await get_config(session, key)
    return str(value).strip('"')


async def resolve_storage_path(session: AsyncSession) -> str:
    """Read active local storage backend mount_point from DB, fall back to env var.

    This connects the admin panel storage configuration to the actual recording
    engine — when a user creates a storage backend from the UI, the recording
    engine will use its mount_point as the output directory.
    """
    try:
        result = await session.execute(
            text(
                "SELECT mount_point FROM storage_backends "
                "WHERE is_active AND backend_type = 'local' "
                "ORDER BY priority LIMIT 1"
            )
        )
        row = result.scalar_one_or_none()
        if row and row[0]:
            logger.info("storage_path_from_backend", mount_point=row[0])
            return row[0]
    except Exception:
        logger.warning("storage_backend_read_failed", exc_info=True)

    fallback = os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings")
    logger.info("storage_path_from_env", path=fallback)
    return fallback
