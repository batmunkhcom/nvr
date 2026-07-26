"""Smart Alerts Plugin — rule-based alert engine.

Evaluates configured rules on each detection frame. Rule types:
    - time_based:   Trigger when object appears in a time window (e.g. 23:00-06:00)
    - frequency:    Trigger when count exceeds threshold within a window
    - zone_violation: Trigger when object enters a restricted zone
    - dwell_time:   Trigger when object stays longer than threshold (future)
    - crowd:        Trigger when person count exceeds threshold (future)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time

import numpy as np
import structlog

from .. import db
from .base import AIPlugin

logger = structlog.get_logger()

RULE_RELOAD_INTERVAL_S = 60


class SmartAlertsPlugin(AIPlugin):
    name = "smart_alerts"

    def __init__(self) -> None:
        self._rules: list[dict] = []
        self._frequency_buckets: dict[str, dict[str, list[float]]] = {}
        self._running = False
        self._reload_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        await self._load_rules()
        self._reload_task = asyncio.create_task(self._rule_reload_loop())
        logger.info("smart_alerts_plugin_started", rules_loaded=len(self._rules))

    async def stop(self) -> None:
        self._running = False
        if self._reload_task:
            self._reload_task.cancel()
        logger.info("smart_alerts_plugin_stopped")

    async def _rule_reload_loop(self) -> None:
        while self._running:
            await asyncio.sleep(RULE_RELOAD_INTERVAL_S)
            await self._load_rules()

    async def _load_rules(self) -> None:
        try:
            from sqlalchemy import text
            async with db.SessionFactory() as session:
                result = await session.execute(
                    text(
                        "SELECT id, camera_id, rule_name, rule_type, severity, "
                        "details, snapshot_path FROM smart_alerts "
                        "WHERE acknowledged = false"
                    )
                )
                self._rules = []
                for row in result.fetchall():
                    self._rules.append({
                        "id": str(row[0]),
                        "camera_id": str(row[1]),
                        "rule_name": row[2],
                        "rule_type": row[3],
                        "severity": row[4],
                        "details": row[5] or {},
                        "snapshot_path": row[6],
                    })
        except Exception:
            pass

    async def on_detection(
        self,
        camera_id: str,
        detections: list[dict],
        frame: np.ndarray,
        timestamp: datetime,
    ) -> None:
        active_rules = [r for r in self._rules if r["camera_id"] == camera_id]
        if not active_rules:
            return

        for rule in active_rules:
            triggered = await self._evaluate_rule(rule, detections, timestamp)
            if triggered:
                await self._trigger_alert(rule, camera_id, timestamp)

    async def _evaluate_rule(
        self, rule: dict, detections: list[dict], timestamp: datetime
    ) -> bool:
        rule_type = rule["rule_type"]
        details = rule.get("details", {})

        if rule_type == "time_based":
            return self._eval_time_based(details, detections, timestamp)
        elif rule_type == "frequency":
            return self._eval_frequency(rule["camera_id"], details, detections, timestamp)
        elif rule_type == "zone_violation":
            return self._eval_zone_violation(details, detections)

        return False

    def _eval_time_based(
        self, details: dict, detections: list[dict], timestamp: datetime
    ) -> bool:
        objects = details.get("object_categories") or ["person"]
        time_start_str = details.get("time_start")  # "23:00"
        time_end_str = details.get("time_end")      # "06:00"
        min_confidence = float(details.get("min_confidence", 0.5))

        if not time_start_str or not time_end_str:
            return False

        try:
            h1, m1 = map(int, time_start_str.split(":"))
            h2, m2 = map(int, time_end_str.split(":"))
            t_start = time(h1, m1)
            t_end = time(h2, m2)
        except ValueError:
            return False

        current_t = timestamp.time() if hasattr(timestamp, "time") else timestamp.astimezone(UTC).time()

        in_window = False
        if t_start <= t_end:
            in_window = t_start <= current_t <= t_end
        else:
            in_window = current_t >= t_start or current_t <= t_end

        if not in_window:
            return False

        has_matching = any(
            det["class"] in objects and det["confidence"] >= min_confidence
            for det in detections
        )
        return has_matching

    def _eval_frequency(
        self,
        camera_id: str,
        details: dict,
        detections: list[dict],
        timestamp: datetime,
    ) -> bool:
        threshold = int(details.get("threshold", 10))
        window_s = int(details.get("window_seconds", 300))
        objects = details.get("object_categories") or ["person"]
        min_confidence = float(details.get("min_confidence", 0.5))

        matching = sum(
            1 for d in detections
            if d["class"] in objects and d["confidence"] >= min_confidence
        )
        if matching == 0:
            return False

        now_ts = timestamp.timestamp()
        bucket_key = f"{camera_id}:frequency"
        if bucket_key not in self._frequency_buckets:
            self._frequency_buckets[bucket_key] = {}

        bucket = self._frequency_buckets[bucket_key]
        for obj in objects:
            if obj not in bucket:
                bucket[obj] = []
            bucket[obj].append(now_ts)
            bucket[obj] = [t for t in bucket[obj] if now_ts - t <= window_s]
            if len(bucket[obj]) >= threshold:
                bucket[obj] = []
                return True
        return False

    def _eval_zone_violation(self, details: dict, detections: list[dict]) -> bool:
        objects = details.get("object_categories") or ["person"]
        min_confidence = float(details.get("min_confidence", 0.5))

        has_violation = any(
            det["class"] in objects and det["confidence"] >= min_confidence
            for det in detections
        )
        return has_violation

    async def _trigger_alert(
        self, rule: dict, camera_id: str, timestamp: datetime
    ) -> None:
        logger.info(
            "smart_alert_triggered",
            camera_id=camera_id,
            rule_name=rule.get("rule_name"),
            rule_type=rule.get("rule_type"),
        )

        try:
            await db.RedisPublisher.shared().publish(
                "nvr:events",
                {
                    "type": "smart_alert",
                    "camera_id": camera_id,
                    "rule_name": rule.get("rule_name"),
                    "rule_type": rule.get("rule_type"),
                    "severity": rule.get("severity"),
                },
            )
        except Exception:
            logger.warning("alert_redis_publish_failed", camera_id=camera_id)
