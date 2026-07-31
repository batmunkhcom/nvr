"""Recording retention — age-based + circular (overwrite-oldest) cleanup.

Policy:
1. Age-based: segments older than retention.default_days are deleted.
2. Circular: when disk usage exceeds storage.max_usage_percent OR free space
   drops below storage.min_free_gb across any storage root, the OLDEST
   segments are deleted first until the watermark is satisfied — the disk
   can never fill up.
3. Files younger than PROTECT_SECONDS (still being written) are never deleted.
4. Every file delete also removes the recordings DB row (kept in sync).
5. Multi-root: each storage root is checked independently for watermarks.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from datetime import UTC, datetime, timedelta

import structlog
from nvr_common.quota import apply_disk_quota, directory_size_bytes
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import config

logger = structlog.get_logger()

PROTECT_SECONDS = 600  # never delete segments newer than 10 minutes
MAX_DELETES_PER_RUN = 500
DELETE_BATCH = 50  # rows deleted per watermark re-check in circular cleanup


def _delete_sidecar(segment_path: str) -> None:
    """Remove the thumbnail JPEG belonging to a segment (if any)."""
    thumb = os.path.splitext(segment_path)[0] + ".jpg"
    try:
        if os.path.exists(thumb):
            os.unlink(thumb)
    except OSError:
        pass


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

        summary = {"age_deleted": 0, "circular_deleted": 0, "orphan_deleted": 0, "freed_bytes": 0}

        deleted, freed = await self._enforce_age_limit(retention_days)
        summary["age_deleted"] += deleted
        summary["freed_bytes"] += freed

        deleted, freed = await self._enforce_disk_watermarks(max_usage_pct, min_free_gb)
        summary["circular_deleted"] += deleted
        summary["freed_bytes"] += freed

        summary["orphan_deleted"] = await self._cleanup_orphan_dirs(retention_days)

        # Prune empty date dirs once per run (not per deleted file).
        self._prune_empty_dirs()

        if deleted or summary["age_deleted"] or summary["orphan_deleted"]:
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
        roots = config.get_storage_roots()
        quotas = await self._load_mount_quotas(roots)
        for root in roots:
            if not os.path.isdir(root):
                continue
            quota = quotas.get(root)
            usage = await asyncio.to_thread(shutil.disk_usage, root)
            # Quota backends (e.g. SeaweedFS/NFS) report cluster-wide used/free
            # rather than the slice consumed by this mount. Walk the directory
            # to get a realistic used number.
            if quota:
                actual_used = await asyncio.to_thread(directory_size_bytes, root)
            else:
                actual_used = usage.used
            total, used, free = apply_disk_quota(
                usage.total, actual_used, usage.free, quota
            )
            # Delete in batches between watermark checks.
            for _ in range(MAX_DELETES_PER_RUN // DELETE_BATCH):
                usage_pct = used / total * 100 if total else 0
                free_gb = free / (1024**3)
                if usage_pct < max_usage_pct and free_gb >= min_free_gb:
                    break

                # Oldest recordings ON THIS ROOT only — freeing space on root A
                # must not delete footage that lives on root B.
                rows = await self._oldest_recordings(root, DELETE_BATCH)
                if not rows:
                    logger.critical(
                        "retention_nothing_to_delete",
                        root=root,
                        usage_pct=round(usage_pct, 1),
                        free_gb=round(free_gb, 2),
                    )
                    break
                d, f = await self._delete_rows(rows)
                deleted += d
                freed += f
                if d == 0:
                    break
                used = max(0, used - f)
                free = total - used

        if deleted:
            logger.warning("retention_circular_cleanup", deleted=deleted, freed_bytes=freed)
        return deleted, freed

    async def _load_mount_quotas(self, roots: set[str]) -> dict[str, int | None]:
        """Return {mount_point: quota_bytes|None} for active filesystem backends."""
        quotas: dict[str, int | None] = {}
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        "SELECT mount_point, config FROM storage_backends "
                        "WHERE is_active AND backend_type IN ('local', 'nfs', 'smb')"
                    )
                )
                rows = result.fetchall()
        except Exception:
            return quotas
        for mp, cfg in rows:
            if not mp:
                continue
            cfg = cfg or {}
            quota = cfg.get("quota_bytes")
            quotas[mp] = quota if quota and quota > 0 else None
        # Match roots that are under a configured mount_point.
        out: dict[str, int | None] = {}
        for root in roots:
            out[root] = next(
                (
                    quotas[mp]
                    for mp in sorted(quotas, key=len, reverse=True)
                    if root.startswith(mp.rstrip("/") + "/") or root == mp.rstrip("/")
                ),
                None,
            )
        return out

    async def _oldest_recordings(self, root: str, limit: int) -> list[tuple]:
        """Oldest deletable recording rows (id, file_path) under a storage root."""
        protect_after = datetime.now(UTC) - timedelta(seconds=PROTECT_SECONDS)
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, file_path FROM recordings "
                    "WHERE start_time < :protect AND file_path LIKE :prefix "
                    "ORDER BY start_time LIMIT :limit"
                ),
                {"protect": protect_after, "prefix": f"{root.rstrip('/')}/%", "limit": limit},
            )
            return result.fetchall()

    # ------------------------------------------------------------------
    # Orphan cleanup (files of deleted cameras)
    # ------------------------------------------------------------------

    async def _cleanup_orphan_dirs(self, retention_days: int) -> int:
        """Remove camera dirs whose UUID no longer exists in the cameras table.

        delete_camera leaves files behind and retention only touches DB-backed
        files, so orphan dirs would leak forever. Grace period: every file in
        the dir must be older than the retention age before removal.
        """
        removed = 0
        grace_s = max(retention_days, 1) * 86400
        async with self._session_factory() as session:
            result = await session.execute(text("SELECT id FROM cameras"))
            live_ids = {str(row[0]) for row in result.fetchall()}

        now = time.time()
        for base in config.get_storage_roots():
            if not os.path.isdir(base):
                continue
            for camera_dir in os.listdir(base):
                cam_path = os.path.join(base, camera_dir)
                if camera_dir == "snapshots" or not os.path.isdir(cam_path):
                    continue
                try:
                    import uuid as uuid_mod
                    uuid_mod.UUID(camera_dir)
                except ValueError:
                    continue
                if camera_dir in live_ids:
                    continue
                # Only delete when every file inside is past the grace period.
                try:
                    mtimes = [
                        os.path.getmtime(os.path.join(root, name))
                        for root, _dirs, files in os.walk(cam_path)
                        for name in files
                    ]
                except OSError:
                    continue
                if mtimes and all(now - m > grace_s for m in mtimes):
                    shutil.rmtree(cam_path, ignore_errors=True)
                    removed += 1
                    logger.warning("retention_orphan_dir_removed", path=cam_path)
        return removed

    # ------------------------------------------------------------------
    # Delete helpers (file + DB row, kept in sync)
    # ------------------------------------------------------------------

    async def _delete_rows(self, rows: list[tuple]) -> tuple[int, int]:
        deleted = 0
        freed = 0
        for row_id, file_path in rows:
            if file_path.startswith("s3://"):
                # Object lives in object storage — deleting the DB row without
                # deleting the object leaks it forever.
                size = await self._delete_s3_object(file_path)
                if size is None:
                    continue
                if await self._delete_row_only(row_id):
                    deleted += 1
                    freed += size
                continue
            if not self._is_deletable(file_path):
                continue
            size = 0
            try:
                size = os.path.getsize(file_path)
                os.unlink(file_path)
                _delete_sidecar(file_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("retention_delete_failed", path=file_path, exc_info=True)
                continue
            if await self._delete_row_only(row_id):
                deleted += 1
                freed += size
        return deleted, freed

    async def _delete_s3_object(self, file_path: str) -> int | None:
        """Delete an s3://bucket/key recording object. Returns freed bytes (0 if unknown), None on failure."""
        from nvr_common.storage import S3Storage

        bucket, _, key = file_path[5:].partition("/")
        if not bucket or not key:
            return 0
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        "SELECT id, name, config FROM storage_backends "
                        "WHERE backend_type = 's3' AND is_active"
                    )
                )
                backends = result.fetchall()
            for backend_id, name, cfg in backends:
                if (cfg or {}).get("bucket") == bucket:
                    s3 = S3Storage(str(backend_id), name, cfg)
                    await s3.delete(key)
                    return 0
            logger.warning("retention_s3_backend_not_found", bucket=bucket)
            return 0
        except Exception:
            logger.warning("retention_s3_delete_failed", path=file_path, exc_info=True)
            return None

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
        """Remove empty Y/M/D directories left behind after deletes.

        Today/tomorrow date dirs are kept even when empty — a live FFmpeg
        segment muxer needs them at the roll boundary.
        """
        from datetime import timedelta as td

        keep = {
            (datetime.now(UTC) + td(days=o)).strftime("%Y/%m/%d")
            for o in (0, 1)
        }
        for base in config.get_storage_roots():
            if not os.path.isdir(base):
                continue
            for camera_dir in os.listdir(base):
                cam_path = os.path.join(base, camera_dir)
                if not os.path.isdir(cam_path):
                    continue
                for root, dirs, _files in os.walk(cam_path, topdown=False):
                    for d in dirs:
                        full = os.path.join(root, d)
                        rel_full = os.path.relpath(full, cam_path).replace(os.sep, "/")
                        if rel_full in keep:
                            continue
                        try:
                            if not os.listdir(full):
                                os.rmdir(full)
                        except OSError:
                            pass
