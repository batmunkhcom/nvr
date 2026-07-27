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
ACTIVE_STORAGE_ROOTS: set[str] = set()
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
    """Read highest-priority active filesystem backend mount_point, fall back to env."""
    try:
        result = await session.execute(
            text(
                "SELECT mount_point FROM storage_backends "
                "WHERE is_active AND backend_type IN ('local', 'nfs', 'smb') "
                "ORDER BY priority LIMIT 1"
            )
        )
        row = result.scalar_one_or_none()
        if row:
            logger.info("storage_path_from_backend", mount_point=row)
            return row
    except Exception:
        logger.warning("storage_backend_read_failed", exc_info=True)

    fallback = os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings")
    logger.info("storage_path_from_env", path=fallback)
    return fallback


def get_storage_roots() -> set[str]:
    """All unique storage roots to scan for catalog/retention/analytics."""
    return ACTIVE_STORAGE_ROOTS or {STORAGE_LOCAL_PATH}


async def load_all_backend_mounts(session: AsyncSession) -> dict[str, str]:
    """Returns {mount_point: backend_id} for all active filesystem backends."""
    try:
        result = await session.execute(
            text(
                "SELECT mount_point, id FROM storage_backends "
                "WHERE is_active AND backend_type IN ('local', 'nfs', 'smb')"
            )
        )
        return {row[0]: str(row[1]) for row in result.fetchall() if row[0]}
    except Exception:
        return {}


async def build_camera_storage_map(session: AsyncSession) -> dict[str, str]:
    """Returns {camera_id: output_base} for cameras with assigned backends."""
    try:
        result = await session.execute(
            text(
                "SELECT c.id, sb.mount_point FROM cameras c "
                "JOIN storage_backends sb ON c.storage_backend_id = sb.id "
                "WHERE sb.is_active AND sb.backend_type IN ('local', 'nfs', 'smb')"
            )
        )
        return {str(row[0]): row[1] for row in result.fetchall()}
    except Exception:
        logger.warning("camera_storage_map_failed", exc_info=True)
        return {}
