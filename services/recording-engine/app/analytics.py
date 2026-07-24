"""Disk usage analytics — measures real GB/day per camera and projects capacity.

Runs hourly. Reads the recordings table (last 24h window) to compute actual
bytes/day per camera, then stores the analysis in system_config as
`storage.analysis` (JSON) so the API/UI can display:

  - per-camera and total GB/day
  - disk total/used/free
  - estimated days of recording that fit in the remaining space
"""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import config

logger = structlog.get_logger()

WINDOW_HOURS = 24


class DiskAnalytics:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def run(self) -> dict:
        """Compute and persist the storage analysis. Returns the analysis dict."""
        usage = await asyncio.to_thread(shutil.disk_usage, config.STORAGE_LOCAL_PATH)
        since = datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)

        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT c.name, r.camera_id,
                           SUM(r.file_size_bytes) AS bytes,
                           COUNT(*) AS segments
                    FROM recordings r
                    JOIN cameras c ON c.id = r.camera_id
                    WHERE r.start_time >= :since
                    GROUP BY r.camera_id, c.name
                    ORDER BY bytes DESC
                    """
                ),
                {"since": since},
            )
            rows = result.fetchall()

            # current stored totals per camera (all time) — shown as "stored now"
            stored_result = await session.execute(
                text(
                    """
                    SELECT c.name, r.camera_id,
                           SUM(r.file_size_bytes) AS bytes,
                           COUNT(*) AS segments
                    FROM recordings r
                    JOIN cameras c ON c.id = r.camera_id
                    GROUP BY r.camera_id, c.name
                    """
                )
            )
            stored_rows = stored_result.fetchall()

            # coverage: how many distinct hours have data (for partial-day scaling)
            coverage = await session.execute(
                text(
                    "SELECT COUNT(DISTINCT date_trunc('hour', start_time)) "
                    "FROM recordings WHERE start_time >= :since"
                ),
                {"since": since},
            )
            hours_covered = max(1, coverage.scalar() or 1)

        scale = WINDOW_HOURS / min(hours_covered, WINDOW_HOURS)
        window_by_cam: dict[str, dict] = {}
        total_bytes_day = 0.0
        for name, camera_id, total_b, segments in rows:
            gb_day = round(float(total_b or 0) / (1024**3) * scale, 2)
            total_bytes_day += gb_day
            window_by_cam[str(camera_id)] = {
                "camera": name,
                "gb_per_day": gb_day,
                "segments_24h": segments,
            }

        per_camera = []
        total_stored_gb = 0.0
        for name, camera_id, total_b, segments in stored_rows:
            stored_gb = round(float(total_b or 0) / (1024**3), 2)
            total_stored_gb += stored_gb
            win = window_by_cam.pop(str(camera_id), {})
            per_camera.append(
                {
                    "camera_id": str(camera_id),
                    "camera": name,
                    "stored_gb": stored_gb,
                    "stored_segments": segments,
                    "gb_per_day": win.get("gb_per_day", 0.0),
                    "segments_24h": win.get("segments_24h", 0),
                }
            )
        # cameras with recent writes but no stored rows (edge case)
        for camera_id, win in window_by_cam.items():
            per_camera.append(
                {
                    "camera_id": camera_id,
                    "camera": win["camera"],
                    "stored_gb": 0.0,
                    "stored_segments": 0,
                    "gb_per_day": win["gb_per_day"],
                    "segments_24h": win["segments_24h"],
                }
            )
        per_camera.sort(key=lambda c: c["stored_gb"], reverse=True)

        free_bytes = usage.free
        days_fit = round(free_bytes / (total_bytes_day * 1024**3), 1) if total_bytes_day else None

        analysis = {
            "computed_at": datetime.now(UTC).isoformat(),
            "window_hours": WINDOW_HOURS,
            "per_camera": per_camera,
            "total_gb_per_day": round(total_bytes_day, 2),
            "total_stored_gb": round(total_stored_gb, 2),
            "disk": {
                "path": config.STORAGE_LOCAL_PATH,
                "total_gb": round(usage.total / (1024**3), 1),
                "used_gb": round(usage.used / (1024**3), 1),
                "free_gb": round(free_bytes / (1024**3), 1),
                "used_percent": round(usage.used / usage.total * 100, 1) if usage.total else 0,
            },
            "days_fit": days_fit,
        }

        async with self._session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO system_config (key, value, description)
                    VALUES ('storage.analysis', :value,
                            'Автомат дискийн анализ — recording engine цаг тутам тооцдог')
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                        updated_at = now()
                    """
                ),
                {"value": json.dumps(analysis)},
            )
            await session.commit()

        logger.info(
            "storage_analysis",
            total_gb_day=analysis["total_gb_per_day"],
            days_fit=days_fit,
            free_gb=analysis["disk"]["free_gb"],
        )
        return analysis
