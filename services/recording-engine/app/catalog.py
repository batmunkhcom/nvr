"""Segment catalog — reconciles on-disk MP4 segments with the recordings table.

Scans STORAGE_LOCAL_PATH/<camera_id>/YYYY/MM/DD/*.mp4:
- New closed segments (mtime older than STABLE_SECONDS) get a DB row so the
  API/Recordings page can list and stream them.
- DB rows whose files disappeared (deleted by retention) are removed.
Idempotent — safe to run repeatedly and after crashes.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import config

logger = structlog.get_logger()

STABLE_SECONDS = 15  # file untouched this long => segment is closed
FILENAME_RE = re.compile(r"(\d{8})_(\d{6})\.mp4$")


async def _probe_duration(path: str) -> float | None:
    """Get segment duration via ffprobe (None on failure)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            config.FFPROBE_PATH,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return round(float(out.decode().strip()), 1)
    except Exception:
        return None


def _parse_start_time(filename: str) -> datetime | None:
    match = FILENAME_RE.search(filename)
    if not match:
        return None
    try:
        return datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None


class SegmentCatalog:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def scan(self) -> dict:
        """One full reconciliation pass over the recordings directory."""
        stats = {"registered": 0, "purged_rows": 0, "errors": 0}
        base = config.STORAGE_LOCAL_PATH
        if not os.path.isdir(base):
            return stats

        async with self._session_factory() as session:
            known_paths = await self._load_known_paths(session)
            disk_files = self._walk_segments(base)

            for path in sorted(disk_files):
                if path in known_paths:
                    continue
                try:
                    if await self._register(session, path, base):
                        stats["registered"] += 1
                except Exception:
                    stats["errors"] += 1
                    logger.warning("catalog_register_failed", path=path, exc_info=True)

            stats["purged_rows"] = await self._purge_missing(session, known_paths, disk_files)
            await session.commit()

        if stats["registered"] or stats["purged_rows"]:
            logger.info("catalog_scan_complete", **stats)
        return stats

    async def _load_known_paths(self, session: AsyncSession) -> set[str]:
        result = await session.execute(text("SELECT file_path FROM recordings"))
        return {row[0] for row in result.fetchall()}

    def _walk_segments(self, base: str) -> set[str]:
        """All .mp4 segment paths on disk (absolute)."""
        found: set[str] = set()
        for camera_dir in os.listdir(base):
            cam_path = os.path.join(base, camera_dir)
            if camera_dir == "snapshots" or not os.path.isdir(cam_path):
                continue
            for root, _dirs, files in os.walk(cam_path):
                for name in files:
                    if name.endswith(".mp4"):
                        found.add(os.path.join(root, name))
        return found

    async def _register(self, session: AsyncSession, path: str, base: str) -> bool:
        """Insert a recordings row for a closed segment. Returns True if inserted."""
        start_time = _parse_start_time(os.path.basename(path))
        if start_time is None:
            return False
        try:
            stat = os.stat(path)
        except OSError:
            return False
        if datetime.now(UTC).timestamp() - stat.st_mtime < STABLE_SECONDS:
            return False  # still being written

        duration = await _probe_duration(path)
        if duration is None or duration <= 0:
            mtime_age = max(1.0, datetime.now(UTC).timestamp() - stat.st_mtime)
            duration = min(mtime_age, 600.0)
        end_time = start_time + timedelta(seconds=duration)

        # camera id is the first path component under the base dir
        rel = os.path.relpath(path, base)
        camera_id = rel.split(os.sep)[0]
        try:
            uuid.UUID(camera_id)
        except ValueError:
            return False

        await session.execute(
            text(
                """
                INSERT INTO recordings
                    (id, camera_id, file_path, file_size_bytes, duration_seconds,
                     start_time, end_time, recording_type)
                VALUES (:id, :camera_id, :file_path, :size, :duration,
                        :start_time, :end_time, 'continuous')
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "camera_id": camera_id,
                "file_path": path,
                "size": stat.st_size,
                "duration": duration,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        return True

    async def _purge_missing(
        self, session: AsyncSession, known_paths: set[str], disk_files: set[str]
    ) -> int:
        """Remove DB rows whose files no longer exist (e.g. deleted by retention)."""
        missing = [p for p in known_paths if p not in disk_files]
        if not missing:
            return 0
        await session.execute(
            text("DELETE FROM recordings WHERE file_path = ANY(:paths)"),
            {"paths": missing},
        )
        return len(missing)
