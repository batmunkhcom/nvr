"""Storage Tier Migration Worker.

Moves recordings between storage backends based on tier retention policies.
Each tier specifies:
  - backend_id: target storage backend
  - retention_days: recordings older than this get moved to the NEXT tier
  - priority_level: processing order (1=hot, 2=warm, 3=cold)

A recording is eligible for migration when:
  1. Its age (now - start_time) exceeds its current tier's retention_days
  2. A lower-priority (colder) tier exists as the target
  3. Its storage_backend_id matches the source tier's backend

Migration uses the StorageBackend.copy_to() method and populates the
storage_migrations table for tracking.

Runs on a 1-hour interval.
"""

from __future__ import annotations

import asyncio
import uuid as uuid_lib
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger()

MIGRATE_INTERVAL = 3600
MAX_MIGRATIONS_PER_RUN = 50
MIN_SEGMENT_AGE_S = 600  # don't migrate segments still being written


class TierMigrationWorker:
    """Moves old recordings to colder storage tiers based on retention policies."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def run(self) -> dict:
        """One migration pass. Returns summary."""
        stats = {"migrated": 0, "skipped": 0, "errors": 0}

        tiers = await self._load_active_tiers()
        if len(tiers) < 2:
            return stats

        for i in range(len(tiers) - 1):
            source_tier = tiers[i]
            target_tier = tiers[i + 1]
            batch_stats = await self._migrate_batch(source_tier, target_tier)
            stats["migrated"] += batch_stats["migrated"]
            stats["skipped"] += batch_stats["skipped"]
            stats["errors"] += batch_stats["errors"]

        if stats["migrated"]:
            logger.info("tier_migration_pass", **stats)
        return stats

    async def _load_active_tiers(self) -> list[dict]:
        """Returns tiers ordered by priority_level (hot→cold)."""
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT st.id, st.name, st.backend_id, st.priority_level,
                               st.retention_days, st.min_free_bytes, st.max_used_percent,
                               sb.mount_point, sb.backend_type, sb.config
                        FROM storage_tiers st
                        JOIN storage_backends sb ON st.backend_id = sb.id
                        WHERE st.is_active
                        ORDER BY st.priority_level
                        """
                    )
                )
                return [
                    {
                        "tier_id": str(row[0]),
                        "name": row[1],
                        "backend_id": str(row[2]),
                        "priority_level": row[3],
                        "retention_days": row[4],
                        "min_free_bytes": row[5],
                        "max_used_percent": row[6],
                        "mount_point": row[7],
                        "backend_type": row[8],
                        "config": row[9] or {},
                    }
                    for row in result.fetchall()
                ]
        except Exception:
            logger.warning("tier_load_failed", exc_info=True)
            return []

    async def _migrate_batch(
        self, source: dict, target: dict
    ) -> dict:
        """Migrate recordings from source tier to target tier."""
        stats = {"migrated": 0, "skipped": 0, "errors": 0}
        if source["retention_days"] <= 0:
            return stats

        cutoff = datetime.now(UTC).timestamp() - (source["retention_days"] * 86400)
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=UTC)

        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, file_path, camera_id
                    FROM recordings
                    WHERE storage_backend_id = :backend_id
                      AND start_time < :cutoff
                    ORDER BY start_time
                    LIMIT :limit
                    """
                ),
                {
                    "backend_id": source["backend_id"],
                    "cutoff": cutoff_dt,
                    "limit": MAX_MIGRATIONS_PER_RUN,
                },
            )
            rows = result.fetchall()

        for row in rows:
            rec_id = str(row[0])
            file_path = row[1]
            camera_id = str(row[2])

            if not await self._is_migratable(file_path):
                stats["skipped"] += 1
                continue

            try:
                await self._copy_between_backends(
                    rec_id, file_path, camera_id, source, target
                )
                stats["migrated"] += 1
            except Exception:
                stats["errors"] += 1
                logger.warning(
                    "tier_migration_failed",
                    rec_id=rec_id,
                    source=source["name"],
                    target=target["name"],
                    exc_info=True,
                )

        return stats

    @staticmethod
    async def _is_migratable(file_path: str) -> bool:
        import os
        import time

        try:
            return time.time() - os.path.getmtime(file_path) >= MIN_SEGMENT_AGE_S
        except OSError:
            return False

    async def _copy_between_backends(
        self,
        rec_id: str,
        file_path: str,
        camera_id: str,
        source: dict,
        target: dict,
    ) -> None:
        """Copy recording from source backend to target, update DB."""
        from nvr_common.storage import LocalStorage

        if target["backend_type"] == "s3":
            from nvr_common.storage import S3Storage

            dest = S3Storage(target["backend_id"], target["name"], target["config"])
            dest_path = f"{camera_id}/{os.path.basename(file_path)}"
        else:
            dest = LocalStorage(
                target["backend_id"],
                target["name"],
                {"path": target["mount_point"]},
            )
            dest_path = f"{camera_id}/{os.path.basename(file_path)}"

        src = LocalStorage(source["backend_id"], source["name"], {"path": source["mount_point"]})

        rel_path = os.path.relpath(file_path, source["mount_point"])
        await src.copy_to(rel_path, dest, dest_path)
        await dest._finish_chunked_upload(dest_path)

        new_path = (
            f"s3://{dest.bucket}/{dest_path}"
            if target["backend_type"] == "s3"
            else os.path.join(target["mount_point"], dest_path)
        )

        migration_id = str(uuid_lib.uuid4())
        async with self._session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO storage_migrations
                        (id, recording_id, from_backend_id, to_backend_id,
                         status, source_path, dest_path, started_at, completed_at)
                    VALUES
                        (:id, :rec_id, :from_id, :to_id,
                         'completed', :src_path, :dst_path, now(), now())
                    """
                ),
                {
                    "id": migration_id,
                    "rec_id": rec_id,
                    "from_id": source["backend_id"],
                    "to_id": target["backend_id"],
                    "src_path": file_path,
                    "dst_path": new_path,
                },
            )
            await session.execute(
                text(
                    "UPDATE recordings SET storage_backend_id = :to_id, file_path = :new_path "
                    "WHERE id = :rec_id"
                ),
                {"to_id": target["backend_id"], "new_path": new_path, "rec_id": rec_id},
            )
            await session.commit()

        logger.info(
            "tier_migration_complete",
            rec_id=rec_id,
            from_tier=source["name"],
            to_tier=target["name"],
        )
