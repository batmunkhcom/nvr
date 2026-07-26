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
            SELECT id, name, motion_source, stream_main_uri, stream_sub_uri,
                   username, encrypted_password, ai_objects, ai_sensitivity,
                   ai_min_confidence, ai_zones, ai_enabled, recording_mode,
                   onvif_events_service_url, ai_plugins, lpr_config
            FROM cameras
            WHERE is_active AND (ai_enabled OR recording_mode = 'motion')
            """
        )
    )
    cameras = []
    for row in result.fetchall():
        cam = dict(row._mapping)
        cam["id"] = str(cam["id"])
        cameras.append(cam)
    return cameras


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
        try:
            import json

            import redis.asyncio as aioredis

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
            # drop the connection so next publish reconnects
            self._redis = None
            logger.warning("redis_publish_failed", channel=channel)
