"""Recording engine configuration — env vars + system_config readers."""

from __future__ import annotations

import json
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

_redis_client = None


async def get_redis():
    """Shared lazy Redis client (avoids per-call connection churn)."""
    global _redis_client
    import redis.asyncio as aioredis

    if _redis_client is None:
        host = os.environ.get("REDIS_HOST", "localhost")
        port = int(os.environ.get("REDIS_PORT", "6379"))
        _redis_client = aioredis.from_url(
            f"redis://{host}:{port}/0",
            decode_responses=True,
            socket_connect_timeout=3,
        )
    return _redis_client

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


# Cache of the last successfully built camera → storage mount map.
# Used as fallback when the DB query fails — prevents silent routing
# of NFS-assigned cameras back to default-local.
_camera_storage_map_cache: dict[str, str] = {}


async def build_camera_storage_map(session: AsyncSession) -> dict[str, str]:
    """Returns {camera_id: output_base} for cameras with assigned backends.

    On DB failure, returns the last-known-good map if available, otherwise
    an empty map (which lets _reconcile fall back per-camera to STORAGE_LOCAL_PATH).
    A Redis key is published so the UI can surface the degradation.
    """
    try:
        result = await session.execute(
            text(
                "SELECT c.id, sb.mount_point FROM cameras c "
                "JOIN storage_backends sb ON c.storage_backend_id = sb.id "
                "WHERE sb.is_active AND sb.backend_type IN ('local', 'nfs', 'smb')"
            )
        )
        fresh = {str(row[0]): row[1] for row in result.fetchall()}
        _camera_storage_map_cache.clear()
        _camera_storage_map_cache.update(fresh)
        return fresh
    except Exception:
        logger.critical("camera_storage_map_failed", exc_info=True)
        try:
            redis = await get_redis()
            await redis.set("nvr:storage:db_error", "1", ex=120)
        except Exception:
            pass
        if _camera_storage_map_cache:
            logger.warning(
                "camera_storage_map_using_cache",
                cache_size=len(_camera_storage_map_cache),
            )
            return dict(_camera_storage_map_cache)
        return {}


async def publish_storage_health(
    session: AsyncSession | None = None,
) -> None:
    """Check every active filesystem backend mount_point is accessible and
    publish a JSON summary to Redis ``nvr:storage:health`` for the frontend."""
    import contextlib

    try:
        redis = await get_redis()
    except Exception:
        return

    backends: list[dict] = []
    if session is not None:
        with contextlib.suppress(Exception):
            result = await session.execute(
                text(
                    "SELECT id, name, mount_point, backend_type FROM storage_backends "
                    "WHERE is_active AND backend_type IN ('local', 'nfs', 'smb')"
                )
            )
            backends = [dict(row._mapping) for row in result.fetchall()]

    items = []
    for be in backends:
        mp = be.get("mount_point")
        ok = False
        if mp:
            try:
                ok = os.path.isdir(mp)
            except OSError:
                ok = False
        items.append(
            {
                "id": str(be["id"]),
                "name": be.get("name", ""),
                "mount_point": mp,
                "accessible": ok,
            }
        )

    payload = json.dumps({"backends": items, "db_error": False})
    try:
        await redis.set("nvr:storage:health", payload, ex=120)
    except Exception:
        pass
