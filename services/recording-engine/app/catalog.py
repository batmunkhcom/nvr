"""Segment catalog — reconciles on-disk MP4 segments with the recordings table.

Scans all active storage roots (from config.get_storage_roots()) for new
closed segments. Each root is a mount_point from a storage_backend.

- New closed segments (mtime older than STABLE_SECONDS) get a DB row so the
  API/Recordings page can list and stream them.
- DB rows whose files disappeared (deleted by retention) are removed.
- storage_backend_id is populated based on which mount_point the file lives under.
Idempotent — safe to run repeatedly and after crashes.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
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


async def _make_thumbnail(segment_path: str) -> str | None:
    """Extract a frame at ~2s as a sidecar JPEG next to the segment.

    Falls back to -ss 0 for very short segments (< 2s).
    """
    thumb_path = os.path.splitext(segment_path)[0] + ".jpg"
    if os.path.exists(thumb_path):
        return thumb_path
    try:
        proc = await asyncio.create_subprocess_exec(
            config.FFMPEG_PATH,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "2",
            "-i",
            segment_path,
            "-vframes",
            "1",
            "-vf",
            "scale=320:-1",
            "-q:v",
            "5",
            "-y",
            thumb_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
        if proc.returncode == 0 and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return thumb_path
        if os.path.exists(thumb_path):
            os.unlink(thumb_path)
    except Exception:
        pass
    try:
        proc = await asyncio.create_subprocess_exec(
            config.FFMPEG_PATH,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "0",
            "-i",
            segment_path,
            "-vframes",
            "1",
            "-vf",
            "scale=320:-1",
            "-q:v",
            "5",
            "-y",
            thumb_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
        if proc.returncode == 0 and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return thumb_path
    except Exception:
        pass
    if os.path.exists(thumb_path):
        os.unlink(thumb_path)
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
        """One full reconciliation pass over all storage roots."""
        stats = {"registered": 0, "purged_rows": 0, "errors": 0}
        roots = config.get_storage_roots()

        async with self._session_factory() as session:
            known_paths = await self._load_known_paths(session)
            camera_modes = await self._load_camera_modes(session)
            backend_map = await self._load_backend_map(session)

            all_disk_files: set[str] = set()
            thumb_budget = 200

            for base in roots:
                if not os.path.isdir(base):
                    continue
                disk_files = self._walk_segments(base)
                all_disk_files.update(disk_files)

                for path in sorted(disk_files):
                    if path in known_paths:
                        if (
                            thumb_budget > 0
                            and self._needs_thumbnail(path)
                            and await _make_thumbnail(path)
                        ):
                            thumb_budget -= 1
                        continue
                    try:
                        if await self._register(session, path, base, camera_modes, backend_map):
                            stats["registered"] += 1
                    except Exception:
                        stats["errors"] += 1
                        logger.warning("catalog_register_failed", path=path, exc_info=True)

            stats["purged_rows"] = await self._purge_missing(session, known_paths, all_disk_files)
            await session.commit()

        if stats["registered"] or stats["purged_rows"]:
            logger.info("catalog_scan_complete", **stats)
        return stats

    async def _load_known_paths(self, session: AsyncSession) -> set[str]:
        result = await session.execute(text("SELECT file_path FROM recordings"))
        return {row[0] for row in result.fetchall()}

    async def _load_camera_modes(self, session: AsyncSession) -> dict[str, str]:
        result = await session.execute(text("SELECT id, recording_mode FROM cameras"))
        return {str(row[0]): row[1] for row in result.fetchall()}

    async def _load_backend_map(self, session: AsyncSession) -> dict[str, str]:
        """Returns {mount_point: backend_id} for all active filesystem backends."""
        return await config.load_all_backend_mounts(session)

    @staticmethod
    def _needs_thumbnail(segment_path: str) -> bool:
        """Segment is closed but has no sidecar thumbnail yet."""
        thumb = os.path.splitext(segment_path)[0] + ".jpg"
        if os.path.exists(thumb):
            return False
        try:
            return time.time() - os.path.getmtime(segment_path) >= STABLE_SECONDS
        except OSError:
            return False

    def _walk_segments(self, base: str) -> set[str]:
        """All .mp4 segment paths on disk (absolute)."""
        from datetime import timedelta

        found: set[str] = set()
        for camera_dir in os.listdir(base):
            cam_path = os.path.join(base, camera_dir)
            if camera_dir == "snapshots" or not os.path.isdir(cam_path):
                continue
            # keep date dirs available for long-running ffmpeg processes
            for offset in (0, 1):
                day = datetime.now(UTC) + timedelta(days=offset)
                os.makedirs(os.path.join(cam_path, day.strftime("%Y/%m/%d")), exist_ok=True)
            for root, _dirs, files in os.walk(cam_path):
                for name in files:
                    if name.endswith(".mp4"):
                        found.add(os.path.join(root, name))
        return found

    async def _register(
        self, session: AsyncSession, path: str, base: str, camera_modes: dict[str, str],
        backend_map: dict[str, str],
    ) -> bool:
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

        rel = os.path.relpath(path, base)
        camera_id = rel.split(os.sep)[0]
        try:
            uuid.UUID(camera_id)
        except ValueError:
            return False

        storage_backend_id = self._resolve_backend_id(path, backend_map)
        recording_type = "motion" if camera_modes.get(camera_id) == "motion" else "continuous"
        if await _make_thumbnail(path) is None:
            logger.warning("thumbnail_generation_failed", path=path)
        await session.execute(
            text(
                """
                INSERT INTO recordings
                    (id, camera_id, file_path, file_size_bytes, duration_seconds,
                     start_time, end_time, recording_type, storage_backend_id)
                VALUES (:id, :camera_id, :file_path, :size, :duration,
                        :start_time, :end_time, :recording_type, :storage_backend_id)
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
                "recording_type": recording_type,
                "storage_backend_id": storage_backend_id,
            },
        )
        return True

    @staticmethod
    def _resolve_backend_id(path: str, backend_map: dict[str, str]) -> str | None:
        """Find which backend this file belongs to by matching mount_point prefix."""
        for mount_point, backend_id in sorted(backend_map.items(), key=lambda x: -len(x[0])):
            if path.startswith(mount_point):
                return backend_id
        return None

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
