"""Recording scheduler — cron-based recording schedule enforcement."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()


class RecordingScheduler:
    """Evaluate recording schedules and start/stop recording per cameras."""

    def __init__(self):
        self._active_schedules: dict[str, dict] = {}

    async def evaluate(self, camera_id: str, schedule: dict) -> bool:
        """Check if recording should be active for a camera based on schedule.

        Args:
            camera_id: Camera UUID string.
            schedule: Schedule dict with days_of_week, time_start, time_end.

        Returns:
            True if recording should be active now.
        """
        now = datetime.now(UTC)
        weekday = now.isoweekday()
        current_time = now.time()

        days = schedule.get("days_of_week", [1, 2, 3, 4, 5, 6, 7])
        if weekday not in days:
            return False

        time_start_str = schedule.get("time_start", "00:00")
        time_end_str = schedule.get("time_end", "23:59")

        try:
            h1, m1 = map(int, time_start_str.split(":"))
            h2, m2 = map(int, time_end_str.split(":"))
            start = datetime.now(UTC).replace(hour=h1, minute=m1, second=0).time()
            end = datetime.now(UTC).replace(hour=h2, minute=m2, second=0).time()
            return start <= current_time <= end
        except (ValueError, AttributeError):
            return True

    def should_switch(self, camera_id: str, was_active: bool, schedule: dict) -> bool | None:
        """Determine if recording state should change.

        Returns:
            True to start, False to stop, None to keep current state.
        """
        should_be = asyncio.run(self.evaluate(camera_id, schedule))
        if should_be and not was_active:
            return True
        if not should_be and was_active:
            return False
        return None
