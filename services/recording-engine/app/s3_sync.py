"""S3 Post-Write Sync Worker.

Monitors recordings whose storage_backend_id is NULL (catalogued from local
disk but not yet uploaded to S3). For each camera assigned to an S3 backend,
uploads the closed segment, updates the DB row with the correct
storage_backend_id and S3 path, then removes the local file.

Runs on a 60s interval, independent of the catalog and retention loops.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger()

SYNC_INTERVAL = 60
MAX_UPLOADS_PER_RUN = 20


class S3SyncWorker:
    """Uploads locally written segments to their assigned S3 backends."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def run(self) -> dict:
        """One full sync pass. Returns summary."""
        stats = {"uploaded": 0, "deleted": 0, "errors": 0}

        camera_s3_map = await self._load_camera_s3_map()
        if not camera_s3_map:
            return stats

        rows = await self._load_pending_segments(camera_s3_map)
        if not rows:
            return stats

        for rec_id, file_path, camera_id, s3_config in rows:
            try:
                await self._upload_and_update(
                    rec_id, file_path, camera_id, s3_config
                )
                stats["uploaded"] += 1
                if await self._delete_local(file_path):
                    stats["deleted"] += 1
            except Exception:
                stats["errors"] += 1
                logger.warning("s3_sync_upload_failed", rec_id=str(rec_id), exc_info=True)

        if stats["uploaded"]:
            logger.info("s3_sync_pass", **stats)
        return stats

    async def _load_camera_s3_map(self) -> dict[str, dict]:
        """Returns {camera_id: s3_backend_config} for cameras with active S3 backends."""
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT c.id, sb.id AS backend_id, sb.config
                        FROM cameras c
                        JOIN storage_backends sb ON c.storage_backend_id = sb.id
                        WHERE sb.is_active AND sb.backend_type = 's3'
                        """
                    )
                )
                return {
                    str(row[0]): {"backend_id": str(row[1]), "config": row[2] or {}}
                    for row in result.fetchall()
                }
        except Exception:
            logger.warning("s3_camera_map_failed", exc_info=True)
            return {}

    async def _load_pending_segments(
        self, camera_s3_map: dict[str, dict]
    ) -> list[tuple]:
        """Returns rows: (rec_id, file_path, camera_id, s3_config) for pending uploads."""
        if not camera_s3_map:
            return []
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT id, file_path, camera_id
                        FROM recordings
                        WHERE storage_backend_id IS NULL
                          AND camera_id = ANY(:camera_ids)
                          AND end_time < :min_stable
                        ORDER BY start_time
                        LIMIT :limit
                        """
                    ),
                    {
                        "camera_ids": list(camera_s3_map),
                        "min_stable": datetime.now(UTC),
                        "limit": MAX_UPLOADS_PER_RUN,
                    },
                )
                rows = []
                for row in result.fetchall():
                    rec_id = row[0]
                    file_path = row[1]
                    camera_id = str(row[2])
                    s3_config = camera_s3_map.get(camera_id)
                    if s3_config and os.path.exists(file_path):
                        rows.append((rec_id, file_path, camera_id, s3_config))
                return rows
        except Exception:
            logger.warning("s3_pending_load_failed", exc_info=True)
            return []

    async def _upload_and_update(
        self,
        rec_id: str,
        local_path: str,
        camera_id: str,
        s3_config: dict,
    ) -> None:
        """Upload file to S3 and update the recording row."""
        from nvr_common.storage import S3Storage, LocalStorage

        local = LocalStorage("local", "local", {"path": os.path.dirname(local_path)})
        s3 = S3Storage(s3_config["backend_id"], "s3", s3_config["config"])

        rel_path = os.path.relpath(local_path, os.path.dirname(local_path))
        s3_key = f"{camera_id}/{rel_path}"

        await local.copy_to(
            local_path,
            s3,
            s3_key,
        )
        await s3._finish_chunked_upload(s3_key)

        async with self._session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE recordings
                    SET storage_backend_id = :backend_id,
                        file_path = :s3_path
                    WHERE id = :rec_id
                    """
                ),
                {
                    "backend_id": s3_config["backend_id"],
                    "s3_path": f"s3://{s3.bucket}/{s3_key}",
                    "rec_id": str(rec_id),
                },
            )
            await session.commit()

        logger.info(
            "s3_upload_complete",
            rec_id=str(rec_id),
            camera_id=camera_id,
            s3_key=s3_key,
        )

    @staticmethod
    async def _delete_local(file_path: str) -> bool:
        """Remove local segment + sidecar thumbnail. Returns True if deleted."""
        thumb = os.path.splitext(file_path)[0] + ".jpg"
        deleted = False
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                deleted = True
        except OSError:
            pass
        try:
            if os.path.exists(thumb):
                os.unlink(thumb)
        except OSError:
            pass
        return deleted
