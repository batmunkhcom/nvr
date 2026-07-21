"""Recording retention manager + corrupt segment recovery + tier migration."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from nvr_common.storage import StorageBackend

logger = structlog.get_logger()

FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
RETENTION_CHECK_INTERVAL = 3600  # 1 hour
EMERGENCY_THRESHOLD = 5
CRITICAL_THRESHOLD = 3


class RetentionManager:
    """Auto-delete old recordings based on retention policies."""

    async def cleanup(self, backend: StorageBackend, retention_days: int) -> dict:
        """Delete recordings older than retention_days from a storage backend."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        files = await backend.list_files("recordings/")

        deleted = 0
        freed_bytes = 0
        for path in files:
            if self._is_older_than(path, cutoff):
                await backend.delete(path)
                deleted += 1

        logger.info(
            "retention_cleanup",
            backend=backend.name,
            deleted=deleted,
            retention_days=retention_days,
        )
        return {"deleted": deleted, "freed_bytes": freed_bytes}

    @staticmethod
    def _is_older_than(path: str, cutoff: datetime) -> bool:
        parts = path.replace("recordings/", "").split("/")
        if len(parts) >= 3:
            date_str = f"{parts[0]}-{parts[1]}-{parts[2][:2]}"
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                return file_date < cutoff
            except ValueError:
                pass
        return False


class EmergencyCleanup:
    """Aggressive disk space cleanup protocol — 4 levels."""

    @staticmethod
    async def run(backend: StorageBackend) -> dict:
        """Execute emergency cleanup based on free space percentage."""
        free_pct = await backend.free_percent()
        if free_pct >= EMERGENCY_THRESHOLD:
            return {"action": "none", "free_pct": free_pct}

        logger.critical("emergency_cleanup_started", backend=backend.name, free_pct=free_pct)

        actions = []

        if free_pct < EMERGENCY_THRESHOLD:
            files = await backend.list_files("recordings/")
            old = sorted(files)[: max(1, len(files) // 3)]
            for f in old:
                await backend.delete(f)
            actions.append("deleted_oldest_third")

        if await backend.free_percent() < CRITICAL_THRESHOLD:
            all_files = await backend.list_files("recordings/")
            non_events = [f for f in all_files if "event" not in f.lower()]
            for f in non_events:
                await backend.delete(f)
            actions.append("deleted_non_event_recordings")

        logger.info("emergency_cleanup_complete", backend=backend.name, actions=actions)
        return {"action": "emergency", "free_pct": await backend.free_percent(), "steps": actions}


async def recover_corrupt_segment(filepath: str) -> str | None:
    """Attempt to recover a corrupt MP4 using ffmpeg -err_detect ignore_err."""
    if not os.path.exists(filepath):
        return None
    recovered = filepath.replace(".mp4", "_recovered.mp4")
    proc = await asyncio.create_subprocess_exec(
        FFMPEG_PATH,
        "-err_detect",
        "ignore_err",
        "-i",
        filepath,
        "-c",
        "copy",
        recovered,
        "-y",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    if proc.returncode == 0 and os.path.getsize(recovered) > 1024:
        logger.info("segment_recovered", original=filepath, recovered=recovered)
        return recovered
    if os.path.exists(recovered):
        os.unlink(recovered)
    return None


class TierMigrationManager:
    """Orchestrate storage tier migrations (hot → warm → cold)."""

    @staticmethod
    async def migrate_recording(
        recording_id: uuid.UUID,
        from_backend: StorageBackend,
        to_backend: StorageBackend,
        file_path: str,
    ) -> dict:
        """Migrate a recording from one backend to another with checksum verification."""
        logger.info("migration_started", recording_id=str(recording_id))

        source_checksum = await from_backend.checksum(file_path)

        await from_backend.copy_to(file_path, to_backend, file_path)

        dest_checksum = await to_backend.checksum(file_path)
        if dest_checksum != source_checksum:
            return {"status": "failed", "error": "Checksum mismatch"}

        await from_backend.delete(file_path)

        logger.info("migration_complete", recording_id=str(recording_id))
        return {"status": "complete", "checksum": dest_checksum}
