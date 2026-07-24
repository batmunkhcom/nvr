"""Recording retention — age-based + circular (overwrite-oldest) cleanup.

Policy:
1. Age-based: segments older than retention.default_days are deleted.
2. Circular: when disk usage exceeds storage.max_usage_percent OR free space
   drops below storage.min_free_gb, the OLDEST segments are deleted first
   until the watermark is satisfied — the disk can never fill up.
3. Files younger than PROTECT_SECONDS (still being written) are never deleted.
4. Every file delete also removes the recordings DB row (kept in sync).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import config

logger = structlog.get_logger()

PROTECT_SECONDS = 600  # never delete segments newer than 10 minutes
MAX_DELETES_PER_RUN = 500


class RetentionManager:
    """Keeps recordings within age and disk-space watermarks."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def run(self) -> dict:
        """One retention pass. Returns a summary dict."""
        async with self._session_factory() as session:
            retention_days = await config.get_config_int(session, "retention.default_days")
            max_usage_pct = await config.get_config_int(session, "storage.max_usage_percent")
            min_free_gb = await config.get_config_int(session, "storage.min_free_gb")

        summary = {"age_deleted": 0, "circular_deleted": 0, "freed_bytes": 0}

        deleted, freed = await self._enforce_age_limit(retention_days)
        summary["age_deleted"] += deleted
        summary["freed_bytes"] += freed

        deleted, freed = await self._enforce_disk_watermarks(max_usage_pct, min_free_gb)
        summary["circular_deleted"] += deleted
        summary["freed_bytes"] += freed

        if deleted or summary["age_deleted"]:
            logger.info("retention_pass_complete", **summary)
        return summary

    # ------------------------------------------------------------------
    # Age-based cleanup
    # ------------------------------------------------------------------

    async def _enforce_age_limit(self, retention_days: int) -> tuple[int, int]:
        if retention_days <= 0:
            return 0, 0
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, file_path FROM recordings "
                    "WHERE start_time < :cutoff ORDER BY start_time LIMIT :limit"
                ),
                {"cutoff": cutoff, "limit": MAX_DELETES_PER_RUN},
            )
            rows = result.fetchall()
        return await self._delete_rows(rows)

    # ------------------------------------------------------------------
    # Circular (disk watermark) cleanup
    # ------------------------------------------------------------------

    async def _enforce_disk_watermarks(
        self, max_usage_pct: int, min_free_gb: int
    ) -> tuple[int, int]:
        deleted = 0
        freed = 0
        for _ in range(MAX_DELETES_PER_RUN):
            usage = await asyncio.to_thread(shutil.disk_usage, config.STORAGE_LOCAL_PATH)
            usage_pct = usage.used / usage.total * 100 if usage.total else 0
            free_gb = usage.free / (1024**3)
            if usage_pct < max_usage_pct and free_gb >= min_free_gb:
                break

            row = await self._oldest_recording()
            if row is None:
                logger.critical(
                    "retention_nothing_to_delete",
                    usage_pct=round(usage_pct, 1),
                    free_gb=round(free_gb, 2),
                )
                break
            d, f = await self._delete_rows([row])
            deleted += d
            freed += f
            if d == 0:
                # Oldest segment is protected or undeletable — cannot make progress
                break

        if deleted:
            logger.warning("retention_circular_cleanup", deleted=deleted, freed_bytes=freed)
        return deleted, freed

    async def _oldest_recording(self) -> tuple | None:
        """Oldest deletable recording row (id, file_path), or None."""
        protect_after = datetime.now(UTC) - timedelta(seconds=PROTECT_SECONDS)
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, file_path FROM recordings "
                    "WHERE start_time < :protect ORDER BY start_time LIMIT 1"
                ),
                {"protect": protect_after},
            )
            return result.fetchone()

    # ------------------------------------------------------------------
    # Delete helpers (file + DB row, kept in sync)
    # ------------------------------------------------------------------

    async def _delete_rows(self, rows: list[tuple]) -> tuple[int, int]:
        deleted = 0
        freed = 0
        for row_id, file_path in rows:
            if not self._is_deletable(file_path):
                continue
            size = 0
            try:
                size = os.path.getsize(file_path)
                os.unlink(file_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("retention_delete_failed", path=file_path, exc_info=True)
                continue
            if await self._delete_row_only(row_id):
                deleted += 1
                freed += size
        self._prune_empty_dirs()
        return deleted, freed

    async def _delete_row_only(self, row_id) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(
                    text("DELETE FROM recordings WHERE id = :id"), {"id": str(row_id)}
                )
                await session.commit()
            return True
        except Exception:
            logger.warning("retention_row_delete_failed", id=str(row_id), exc_info=True)
            return False

    @staticmethod
    def _is_deletable(file_path: str) -> bool:
        try:
            age = time.time() - os.path.getmtime(file_path)
            return age >= PROTECT_SECONDS
        except OSError:
            return True  # missing file -> row should be purged anyway

    @staticmethod
    def _prune_empty_dirs() -> None:
        """Remove empty Y/M/D directories left behind after deletes."""
        base = config.STORAGE_LOCAL_PATH
        for camera_dir in os.listdir(base):
            cam_path = os.path.join(base, camera_dir)
            if not os.path.isdir(cam_path):
                continue
            for root, dirs, _files in os.walk(cam_path, topdown=False):
                for d in dirs:
                    full = os.path.join(root, d)
                    try:
                        if not os.listdir(full):
                            os.rmdir(full)
                    except OSError:
                        pass
