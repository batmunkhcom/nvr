"""Counter Plugin — object counting by category with periodic DB flush."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import numpy as np
import structlog

from .. import db
from .base import AIPlugin

logger = structlog.get_logger()

CATEGORY_MAP: dict[str, list[str]] = {
    "person": ["person"],
    "vehicle": ["car", "truck", "bus", "motorcycle", "bicycle"],
    "animal": ["cat", "dog", "bird"],
    "livestock": ["horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"],
}
MIN_EVENT_GAP_S = 5
FLUSH_INTERVAL_S = 60


class CounterPlugin(AIPlugin):
    name = "counter"

    def __init__(self) -> None:
        self._counts: dict[str, dict[str, int]] = {}
        self._last_event_ts: dict[str, dict[str, float]] = {}
        self._running = False
        self._flush_task: asyncio.Task | None = None

    async def on_detection(
        self,
        camera_id: str,
        detections: list[dict],
        frame: np.ndarray,
        timestamp: datetime,
    ) -> None:
        now_ts = timestamp.timestamp()
        if camera_id not in self._counts:
            self._counts[camera_id] = {}
        if camera_id not in self._last_event_ts:
            self._last_event_ts[camera_id] = {}

        seen_categories: set[str] = set()
        for det in detections:
            cls = det["class"]
            category = self._classify(cls)
            if category is None:
                continue
            seen_categories.add(category)

        for category in seen_categories:
            last_ts = self._last_event_ts[camera_id].get(category, 0)
            if now_ts - last_ts < MIN_EVENT_GAP_S:
                continue
            self._last_event_ts[camera_id][category] = now_ts
            self._counts[camera_id][category] = self._counts[camera_id].get(category, 0) + 1

    @staticmethod
    def _classify(className: str) -> str | None:
        for category, classes in CATEGORY_MAP.items():
            if className in classes:
                return category
        return None

    async def start(self) -> None:
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("counter_plugin_started")

    async def stop(self) -> None:
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush_to_db()
        logger.info("counter_plugin_stopped")

    async def _flush_loop(self) -> None:
        while self._running:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            await self._flush_to_db()

    async def _flush_to_db(self) -> None:
        if not self._counts:
            return
        snapshot: dict[str, dict[str, int]] = {}
        for camera_id, cats in self._counts.items():
            snapshot[camera_id] = dict(cats)
        self._counts.clear()

        now = datetime.now(UTC)
        try:
            async with db.SessionFactory() as session:
                for camera_id, cats in snapshot.items():
                    for category, count in cats.items():
                        if count <= 0:
                            continue
                        await db.upsert_object_counter(
                            session,
                            camera_id=camera_id,
                            object_category=category,
                            counter_date=now.date(),
                            hour=now.hour,
                            count=count,
                        )
        except Exception:
            logger.warning("counter_flush_failed", exc_info=True)
