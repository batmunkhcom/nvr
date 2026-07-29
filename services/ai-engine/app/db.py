"""AI Engine — database access via plain SQL (no cross-service model imports)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = structlog.get_logger()

DB_HOST = os.environ.get("POSTGRES_HOST") or os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("POSTGRES_PORT") or os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB") or os.environ.get("DB_NAME", "nvr")
DB_USER = os.environ.get("POSTGRES_USER") or os.environ.get("DB_USER", "nvr")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("DB_PASSWORD", "nvr")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=5)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def load_ai_cameras(session: AsyncSession) -> list[dict]:
    """Active cameras needing a sampler: AI enabled OR motion-mode recording."""
    result = await session.execute(
        text(
            """
            SELECT c.id, c.name, c.motion_source, c.stream_main_uri, c.stream_sub_uri,
                   c.username, c.encrypted_password, c.ai_objects, c.ai_sensitivity,
                   c.ai_min_confidence, c.ai_zones, c.ai_enabled, c.recording_mode,
                   c.onvif_events_service_url, c.ai_plugins, c.lpr_config,
                   sb.mount_point AS storage_mount_point
            FROM cameras c
            LEFT JOIN storage_backends sb
                ON c.storage_backend_id = sb.id AND sb.is_active
            WHERE c.is_active AND (c.ai_enabled OR c.recording_mode = 'motion')
            """
        )
    )
    cameras = []
    for row in result.fetchall():
        cam = dict(row._mapping)
        cam["id"] = str(cam["id"])
        cameras.append(cam)
    return cameras


async def read_config(session: AsyncSession, key: str) -> str | None:
    """Read a single value from system_config."""
    result = await session.execute(
        text("SELECT value FROM system_config WHERE key = :key"),
        {"key": key},
    )
    row = result.fetchone()
    return row[0] if row else None


async def read_config_float(key: str, default: float) -> float:
    """Read a numeric system_config value with a fallback default."""
    try:
        async with SessionFactory() as session:
            val = await read_config(session, key)
            if val is not None:
                return float(val)
    except Exception:
        logger.warning("config_read_failed", key=key)
    return default


async def read_config_str(key: str, default: str) -> str:
    """Read a string system_config value with a fallback default."""
    try:
        async with SessionFactory() as session:
            val = await read_config(session, key)
            if val is not None:
                return str(val)
    except Exception:
        logger.warning("config_read_failed", key=key)
    return default


async def read_timezone(default: str = "Asia/Ulaanbaatar") -> str:
    """Read the configured timezone string from system_config."""
    return await read_config_str("ui.timezone", default)


async def insert_detection_event(
    session: AsyncSession,
    camera_id: str,
    objects: list[dict],
    model_name: str,
    snapshot_path: str | None,
    start_time: datetime,
) -> None:
    """Persist an object_detected event."""
    await session.execute(
        text(
            """
            INSERT INTO events
                (id, camera_id, event_type, severity, start_time, metadata, snapshot_path)
            VALUES
                (:id, :camera_id, 'object_detected', 'info', :start_time,
                 CAST(:metadata AS json), :snapshot_path)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "start_time": start_time,
            "metadata": json.dumps({"objects": objects, "source": "nvr_ai", "model": model_name}),
            "snapshot_path": snapshot_path,
        },
    )
    await session.commit()


async def upsert_object_counter(
    session: AsyncSession,
    camera_id: str,
    object_category: str,
    counter_date: date,
    hour: int,
    count: int,
) -> None:
    """Upsert hourly object counter — increments existing count."""
    await session.execute(
        text(
            """
            INSERT INTO object_counters
                (id, camera_id, object_category, counter_date, hour, count)
            VALUES
                (gen_random_uuid(), CAST(:camera_id AS uuid), :object_category,
                 :counter_date, :hour, :count)
            ON CONFLICT (camera_id, object_category, counter_date, hour)
            DO UPDATE SET count = object_counters.count + EXCLUDED.count
            """
        ),
        {
            "camera_id": camera_id,
            "object_category": object_category,
            "counter_date": counter_date,
            "hour": hour,
            "count": count,
        },
    )
    await session.commit()


def decrypt_password(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        from nvr_common.security import decrypt_password_aes

        return decrypt_password_aes(encrypted)
    except Exception:
        logger.warning("camera_password_decrypt_failed")
        return None


async def insert_license_plate(
    session: AsyncSession,
    camera_id: str,
    plate_number: str,
    country_code: str,
    pattern_name: str,
    confidence: float,
    detected_at: datetime,
    plate_image_path: str | None = None,
    snapshot_path: str | None = None,
) -> None:
    """Persist a license plate reading."""
    await session.execute(
        text(
            """
            INSERT INTO license_plates
                (id, camera_id, plate_number, country_code, pattern_name,
                 confidence, detected_at, snapshot_path, plate_image_path)
            VALUES
                (gen_random_uuid(), CAST(:camera_id AS uuid), :plate_number,
                 :country_code, :pattern_name, :confidence, :detected_at,
                 :snapshot_path, :plate_image_path)
            """
        ),
        {
            "camera_id": camera_id,
            "plate_number": plate_number,
            "country_code": country_code,
            "pattern_name": pattern_name,
            "confidence": confidence,
            "detected_at": detected_at,
            "snapshot_path": snapshot_path,
            "plate_image_path": plate_image_path,
        },
    )
    await session.commit()


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


class RedisPublisher:
    """Lazy, shared Redis publisher for motion + detection channels."""

    _instance: RedisPublisher | None = None

    def __init__(self) -> None:
        self._redis = None

    @classmethod
    def shared(cls) -> RedisPublisher:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def publish(self, channel: str, payload: dict) -> None:
        import contextlib
        import json

        import redis.asyncio as aioredis

        try:
            if self._redis is None:
                host = os.environ.get("REDIS_HOST", "localhost")
                port = int(os.environ.get("REDIS_PORT", "6379"))
                self._redis = aioredis.from_url(
                    f"redis://{host}:{port}/0",
                    socket_connect_timeout=3,
                    retry_on_timeout=True,
                )
            await self._redis.publish(channel, json.dumps(payload))
        except Exception:
            # Drop the connection (closing it!) so next publish reconnects,
            # and retry once — pub/sub loss must not silently drop state.
            old, self._redis = self._redis, None
            if old is not None:
                with contextlib.suppress(Exception):
                    await old.aclose()
            logger.warning("redis_publish_failed", channel=channel)
            try:
                host = os.environ.get("REDIS_HOST", "localhost")
                port = int(os.environ.get("REDIS_PORT", "6379"))
                self._redis = aioredis.from_url(
                    f"redis://{host}:{port}/0",
                    socket_connect_timeout=3,
                    retry_on_timeout=True,
                )
                await self._redis.publish(channel, json.dumps(payload))
            except Exception:
                with contextlib.suppress(Exception):
                    await self._redis.aclose()
                self._redis = None
                logger.warning("redis_publish_retry_failed", channel=channel)
