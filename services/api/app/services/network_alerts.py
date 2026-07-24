"""Network alert evaluation - threshold checking, cooldown, auto-resolve."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = structlog.get_logger()


class NetworkAlertService:
    ALERT_COOLDOWN_SECONDS = 300

    def __init__(self):
        self._engine = None

    def init(self, db_url: str):
        """Initialize with database URL. Called from app lifespan."""
        self._engine = create_async_engine(db_url)

    async def evaluate(self, camera_id: UUID, metrics: dict[str, Any], engine=None):
        """Check thresholds, create alerts if breached. Returns list of created alert dicts."""
        target_engine = engine or self._engine
        if not target_engine:
            return []

        config = await self._get_camera_config(camera_id, target_engine)
        if not config:
            return []

        created = []

        checks = [
            (
                "bandwidth_low",
                metrics.get("outbound_mbps"),
                float(config["bandwidth_crit_mbps"]),
                "critical",
                "Mbps",
            ),
            (
                "bandwidth_warn",
                metrics.get("outbound_mbps"),
                float(config["bandwidth_warn_mbps"]),
                "warning",
                "Mbps",
            ),
            (
                "latency_high",
                metrics.get("rtt_ms"),
                float(config["latency_crit_ms"]),
                "critical",
                "ms",
            ),
            (
                "latency_warn",
                metrics.get("rtt_ms"),
                float(config["latency_warn_ms"]),
                "warning",
                "ms",
            ),
            (
                "packet_loss_high",
                metrics.get("packet_loss_pct"),
                float(config["packet_loss_crit_pct"]),
                "critical",
                "%",
            ),
            (
                "packet_loss_warn",
                metrics.get("packet_loss_pct"),
                float(config["packet_loss_warn_pct"]),
                "warning",
                "%",
            ),
        ]

        for alert_type, current_value, threshold, severity, unit in checks:
            if current_value is None:
                continue

            breached = ("low" in alert_type and current_value < threshold) or (
                "high" in alert_type and current_value > threshold
            )

            if not breached:
                continue

            if await self._is_in_cooldown(camera_id, alert_type, target_engine):
                continue

            msg = self._build_message(alert_type, current_value, threshold, unit)

            alert = await self._create_alert(
                camera_id,
                alert_type,
                severity,
                msg,
                {"current_value": current_value, "threshold": threshold, "unit": unit},
                target_engine,
            )
            created.append(alert)

            await self._resolve_related_alerts(camera_id, alert_type, target_engine)

        return created

    async def _get_camera_config(self, camera_id: UUID, engine) -> dict[str, Any] | None:
        """Get camera network config from DB."""
        async with AsyncSession(engine) as db:
            result = await db.execute(
                text("""
                SELECT poll_interval, ping_enabled, ping_count, ping_timeout, rtsp_check_enabled,
                       bandwidth_warn_mbps, bandwidth_crit_mbps, latency_warn_ms, latency_crit_ms,
                       packet_loss_warn_pct, packet_loss_crit_pct, retention_days
                FROM camera_network_config
                WHERE camera_id = :camera_id
              """),
                {"camera_id": camera_id},
            )
            row = result.fetchone()
            if row:
                return {
                    "poll_interval": row[0],
                    "ping_enabled": row[1],
                    "ping_count": row[2],
                    "ping_timeout": row[3],
                    "rtsp_check_enabled": row[4],
                    "bandwidth_warn_mbps": row[5],
                    "bandwidth_crit_mbps": row[6],
                    "latency_warn_ms": row[7],
                    "latency_crit_ms": row[8],
                    "packet_loss_warn_pct": row[9],
                    "packet_loss_crit_pct": row[10],
                    "retention_days": row[11],
                }
            return None

    async def _is_in_cooldown(self, camera_id: UUID, alert_type: str, engine) -> bool:
        """Check if same alert type was fired within cooldown period."""
        async with AsyncSession(engine) as db:
            result = await db.execute(
                text("""
                SELECT COUNT(1) FROM network_alerts
                WHERE camera_id = :camera_id
                  AND alert_type = :alert_type
                  AND triggered_at > NOW() - INTERVAL '5 minutes'
              """),
                {"camera_id": camera_id, "alert_type": alert_type},
            )
            count = result.scalar()
            return count is not None and count > 0

    def _build_message(
        self, alert_type: str, current_value: float, threshold: float, unit: str
    ) -> str:
        """Build human-readable alert message."""
        if "bandwidth_low" in alert_type:
            return f"Bandwidth {current_value:.1f} {unit} below threshold {threshold:.1f} {unit}"
        elif "latency_high" in alert_type:
            sev = "critical" if "crit" in alert_type else "warning"
            return f"Latency {current_value:.0f} {unit} exceeds {sev} threshold of {threshold:.0f} {unit}"
        elif "packet_loss_high" in alert_type:
            sev = "critical" if "crit" in alert_type else "warning"
            return f"Packet loss {current_value:.1f}% exceeds {sev} threshold of {threshold:.1f}%"
        return f"{alert_type}: {current_value} {unit}"

    async def _create_alert(
        self, camera_id: UUID, alert_type: str, severity: str, message: str, metadata: dict, engine
    ) -> dict:
        """Create new network alert record."""
        async with AsyncSession(engine) as db:
            result = await db.execute(
                text("""
                INSERT INTO network_alerts (camera_id, alert_type, severity, message, metadata)
                VALUES (:camera_id, :alert_type, :severity, :message, :metadata)
                RETURNING id, camera_id, alert_type, severity, message, triggered_at, metadata
              """),
                {
                    "camera_id": camera_id,
                    "alert_type": alert_type,
                    "severity": severity,
                    "message": message,
                    "metadata": metadata,
                },
            )
            row = result.fetchone()
            await db.commit()

            return {
                "id": str(row[0]),
                "camera_id": str(row[1]),
                "alert_type": row[2],
                "severity": row[3],
                "message": row[4],
                "triggered_at": row[5].isoformat(),
                "metadata": dict(row[6]) if row[6] else None,
            }

    async def _resolve_related_alerts(self, camera_id: UUID, new_alert_type: str, engine):
        """Resolve warning alerts when critical fires (or vice versa)."""
        async with AsyncSession(engine) as db:
            if "crit" in new_alert_type:
                warn_type = new_alert_type.replace("_crit", "_warn")
                await db.execute(
                    text("""
                    UPDATE network_alerts
                    SET resolved_at = NOW()
                    WHERE camera_id = :camera_id
                      AND alert_type = :warn_type
                      AND acknowledged_at IS NULL
                      AND resolved_at IS NULL
                  """),
                    {"camera_id": camera_id, "warn_type": warn_type},
                )
            await db.commit()

    async def get_active_alerts(self, engine) -> list[dict]:
        """Get all unacknowledged alerts for UI display."""
        async with AsyncSession(engine) as db:
            result = await db.execute(
                text("""
                SELECT na.id, na.camera_id, c.name as camera_name, na.alert_type, na.severity,
                       na.message, na.triggered_at, na.acknowledged_at, na.metadata
                FROM network_alerts na
                JOIN cameras c ON na.camera_id = c.id
                WHERE na.acknowledged_at IS NULL
                ORDER BY na.triggered_at DESC
              """)
            )
            rows = result.fetchall()

            return [
                {
                    "id": str(row[0]),
                    "camera_id": str(row[1]),
                    "camera_name": row[2],
                    "alert_type": row[3],
                    "severity": row[4],
                    "message": row[5],
                    "triggered_at": row[6].isoformat(),
                    "acknowledged_at": row[7].isoformat() if row[7] else None,
                    "metadata": dict(row[8]) if row[8] else None,
                }
                for row in rows
            ]

    async def acknowledge_alert(self, alert_id: UUID, user_id: UUID, engine) -> dict:
        """Acknowledge a network alert."""
        async with AsyncSession(engine) as db:
            result = await db.execute(
                text("""
                UPDATE network_alerts
                SET acknowledged_at = NOW(), acknowledged_by = :user_id
                WHERE id = :alert_id AND acknowledged_at IS NULL
                RETURNING id, acknowledged_at
              """),
                {"alert_id": alert_id, "user_id": user_id},
            )
            row = result.fetchone()
            await db.commit()

            if row:
                return {"id": str(row[0]), "acknowledged_at": row[1].isoformat()}
            return {"error": "Alert not found or already acknowledged"}


network_alert_service = NetworkAlertService()
