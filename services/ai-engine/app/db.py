"""AI Engine — database access via plain SQL (no cross-service model imports)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

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
    """Active cameras with AI enabled."""
    result = await session.execute(
        text(
            """
            SELECT id, name, motion_source, stream_main_uri, stream_sub_uri,
                   username, encrypted_password, ai_objects, ai_sensitivity,
                   ai_min_confidence, onvif_events_service_url
            FROM cameras
            WHERE is_active AND ai_enabled
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
    objects: dict[str, float],
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


def decrypt_password(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        from nvr_common.security import decrypt_password_aes

        return decrypt_password_aes(encrypted)
    except Exception:
        logger.warning("camera_password_decrypt_failed")
        return None
