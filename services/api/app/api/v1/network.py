"""Network monitoring API endpoints — metrics, alerts, config, summary."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user
from ...services.network_monitor import network_monitor

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/network", tags=["network"])


@router.get("/monitor/status")
async def monitor_status(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Get monitor running state."""
    return {"data": {"running": network_monitor.running}}


@router.post("/monitor/start")
async def start_monitoring(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Start background network metrics collection."""
    if not network_monitor.running:
        await network_monitor.start()
    return {"data": {"running": True, "status": "started"}}


@router.post("/monitor/stop")
async def stop_monitoring(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Stop background network metrics collection."""
    if network_monitor.running:
        await network_monitor.stop()
    return {"data": {"running": False, "status": "stopped"}}


@router.post("/monitor/toggle")
async def toggle_monitoring(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Play/pause the background metrics collection."""
    if network_monitor.running:
        await network_monitor.stop()
        return {"data": {"running": False, "status": "paused"}}
    await network_monitor.start()
    return {"data": {"running": True, "status": "started"}}


@router.get("/metrics")
async def get_latest_metrics(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Latest metrics for all cameras."""
    result = await db.execute(
        text("""
        SELECT c.id, c.name, l.name AS location_name, l.color AS location_color,
               nm.status, nm.inbound_mbps, nm.outbound_mbps,
               nm.rtt_ms, nm.packet_loss_pct, nm.recorded_at
        FROM cameras c
        LEFT JOIN locations l ON l.id = c.location_id
        LEFT JOIN LATERAL (
            SELECT * FROM network_metrics nmc
            WHERE nmc.camera_id = c.id
            ORDER BY nmc.recorded_at DESC
            LIMIT 1
        ) nm ON true
        WHERE c.is_active = true
        ORDER BY c.display_order ASC
    """)
    )
    rows = result.fetchall()

    return {
        "data": [
            {
                "camera_id": str(row[0]),
                "camera_name": row[1],
                "location": row[2],
                "location_color": row[3],
                "status": row[4] or "unknown",
                "inbound_mbps": row[5],
                "outbound_mbps": row[6],
                "rtt_ms": row[7],
                "packet_loss_pct": row[8],
                "recorded_at": row[9].isoformat() if row[9] else None,
            }
            for row in rows
        ]
    }


@router.get("/metrics/all/history")
async def get_all_cameras_history(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    range: str = Query("24h", description="1h, 6h, 12h, 24h, 7d"),
):
    """Aggregated history across all cameras — summed per time bucket."""
    interval_map = {
        "1h": "1 hour",
        "6h": "6 hours",
        "12h": "12 hours",
        "24h": "24 hours",
        "7d": "7 days",
    }
    interval = interval_map.get(range, "24 hours")
    interval_sql = f"NOW() - INTERVAL '{interval}'"

    bucket = "minute" if range in ("1h", "6h", "12h") else "hour"
    if range == "7d":
        bucket = "hour"

    result = await db.execute(
        text(f"""
        SELECT date_trunc('{bucket}', recorded_at) AS bucket,
               COALESCE(SUM(inbound_mbps)::numeric(10,2), 0),
               COALESCE(SUM(outbound_mbps)::numeric(10,2), 0),
               AVG(rtt_ms)::numeric(8,2)
        FROM network_metrics
        WHERE recorded_at > {interval_sql}
        GROUP BY bucket
        ORDER BY bucket ASC
    """)
    )
    rows = result.fetchall()

    return {
        "data": {
            "camera_name": "All Cameras",
            "time_range": {"start": f"Now - {interval}", "end": "now"},
            "metrics": [
                {
                    "recorded_at": row[0].isoformat(),
                    "inbound_mbps": float(row[1]),
                    "outbound_mbps": float(row[2]),
                    "rtt_ms": float(row[3]) if row[3] else None,
                    "packet_loss_pct": None,
                    "status": None,
                }
                for row in rows
            ],
        }
    }


@router.get("/metrics/overlay")
async def get_overlay_history(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    range: str = Query("24h", description="1h, 6h, 12h, 24h, 7d"),
):
    """Per-camera time-bucketed history for multi-line overlay chart."""
    interval_map = {
        "1h": "1 hour",
        "6h": "6 hours",
        "12h": "12 hours",
        "24h": "24 hours",
        "7d": "7 days",
    }
    interval = interval_map.get(range, "24 hours")
    interval_sql = f"NOW() - INTERVAL '{interval}'"
    bucket = "minute" if range in ("1h", "6h", "12h") else "hour"
    if range == "7d":
        bucket = "hour"

    result = await db.execute(
        text(f"""
        SELECT c.id, c.name, l.name AS loc_name, l.color AS loc_color,
               date_trunc('{bucket}', nm.recorded_at) AS bucket,
               AVG(nm.inbound_mbps)::numeric(10,2),
               AVG(nm.outbound_mbps)::numeric(10,2)
        FROM cameras c
        LEFT JOIN locations l ON l.id = c.location_id
        JOIN network_metrics nm ON nm.camera_id = c.id
        WHERE c.is_active = true
          AND nm.recorded_at > {interval_sql}
        GROUP BY c.id, c.name, l.name, l.color, bucket
        ORDER BY bucket ASC, c.display_order ASC
    """)
    )
    rows = result.fetchall()

    series: dict[str, dict] = {}
    for cid, cname, loc, color, bucket, inbound, outbound in rows:
        cid_s = str(cid)
        if cid_s not in series:
            series[cid_s] = {
                "camera_id": cid_s,
                "camera_name": cname,
                "location": loc,
                "color": color or "#3b82f6",
                "points": [],
            }
        series[cid_s]["points"].append(
            {
                "recorded_at": bucket.isoformat(),
                "inbound_mbps": float(inbound) if inbound else 0,
                "outbound_mbps": float(outbound) if outbound else 0,
            }
        )

    return {"data": list(series.values())}


@router.get("/metrics/{camera_id}")
async def get_camera_metrics(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Latest metrics for single camera."""
    result = await db.execute(
        text("""
        SELECT c.name, l.name AS loc_name, nm.inbound_mbps, nm.outbound_mbps,
               nm.rtt_ms, nm.jitter_ms, nm.packet_loss_pct,
               nm.status, nm.recorded_at
        FROM cameras c
        LEFT JOIN locations l ON l.id = c.location_id
        LEFT JOIN LATERAL (
            SELECT * FROM network_metrics nmc
            WHERE nmc.camera_id = c.id
            ORDER BY nmc.recorded_at DESC
            LIMIT 1
        ) nm ON true
        WHERE c.id = :camera_id
    """),
        {"camera_id": camera_id},
    )
    row = result.fetchone()
    if not row:
        return {"data": None}
    return {
        "data": {
            "camera_name": row[0],
            "location": row[1],
            "camera_id": str(camera_id),
            "inbound_mbps": row[2],
            "outbound_mbps": row[3],
            "rtt_ms": row[4],
            "jitter_ms": row[5],
            "packet_loss_pct": row[6],
            "status": row[7] or "unknown",
            "recorded_at": row[8].isoformat() if row[8] else None,
        }
    }


@router.get("/metrics/{camera_id}/history")
async def get_camera_history(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    range: str = Query("24h", description="1h, 6h, 12h, 24h, 7d"),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
):
    """Historical metrics for single camera with time range."""
    interval_map = {
        "1h": "1 hour",
        "6h": "6 hours",
        "12h": "12 hours",
        "24h": "24 hours",
        "7d": "7 days",
    }
    interval = interval_map.get(range, "24 hours")

    cam_result = await db.execute(
        text("SELECT name, location FROM cameras WHERE id = :cid"), {"cid": camera_id}
    )
    cam_row = cam_result.fetchone()
    if not cam_row:
        return {"data": None}

    offset = (page - 1) * per_page
    interval_sql = f"NOW() - INTERVAL '{interval}'"
    result = await db.execute(
        text(f"""
        SELECT id, recorded_at, inbound_mbps, outbound_mbps, rtt_ms,
               packet_loss_pct, status
        FROM network_metrics
        WHERE camera_id = :camera_id
          AND recorded_at > {interval_sql}
        ORDER BY recorded_at DESC
        LIMIT :limit OFFSET :offset
    """),
        {"camera_id": camera_id, "limit": per_page, "offset": offset},
    )
    rows = result.fetchall()

    count_result = await db.execute(
        text(f"""
        SELECT COUNT(1) FROM network_metrics
        WHERE camera_id = :camera_id
          AND recorded_at > {interval_sql}
    """),
        {"camera_id": camera_id},
    )
    total_count = count_result.scalar() or 0

    return {
        "data": {
            "camera_id": str(camera_id),
            "camera_name": cam_row[0],
            "location": cam_row[1],
            "time_range": {"start": f"Now - {interval}", "end": "now"},
            "metrics": [
                {
                    "recorded_at": row[1].isoformat() if row[1] else None,
                    "inbound_mbps": row[2],
                    "outbound_mbps": row[3],
                    "rtt_ms": row[4],
                    "packet_loss_pct": row[5],
                    "status": row[6] or "unknown",
                }
                for row in rows
            ],
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
        }
    }


@router.get("/summary")
async def get_network_summary(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Summary: total online/offline, total bandwidth, active alerts."""
    cam_result = await db.execute(
        text("""
        SELECT nm.status, COUNT(*)::int
        FROM cameras c
        LEFT JOIN LATERAL (
            SELECT * FROM network_metrics nmc
            WHERE nmc.camera_id = c.id
            ORDER BY nmc.recorded_at DESC
            LIMIT 1
        ) nm ON true
        WHERE c.is_active = true
        GROUP BY nm.status
    """)
    )

    status_counts = {"online": 0, "offline": 0, "degraded": 0, "unknown": 0}
    for row in cam_result.fetchall():
        s = row[0] or "unknown"
        if s in status_counts:
            status_counts[s] = row[1]

    total_cameras = sum(status_counts.values())

    bw_result = await db.execute(
        text("""
        SELECT COALESCE(SUM(nm.inbound_mbps), 0)::numeric(10,2),
               COALESCE(SUM(nm.outbound_mbps), 0)::numeric(10,2),
               AVG(nm.rtt_ms)::numeric(8,2)
        FROM cameras c
        JOIN LATERAL (
            SELECT * FROM network_metrics nmc
            WHERE nmc.camera_id = c.id
            ORDER BY nmc.recorded_at DESC
            LIMIT 1
        ) nm ON true
        WHERE c.is_active = true
    """)
    )
    bw_row = bw_result.fetchone()

    alert_result = await db.execute(
        text("""
        SELECT COUNT(*)::int,
               SUM(CASE WHEN severity = 'warning' THEN 1 ELSE 0 END)::int,
               SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END)::int
        FROM network_alerts
        WHERE acknowledged_at IS NULL AND resolved_at IS NULL
    """)
    )
    alert_row = alert_result.fetchone()

    loc_result = await db.execute(
        text("""
        SELECT COALESCE(l.name, 'Unknown'), l.color,
               nm.status, COUNT(*)::int
        FROM cameras c
        LEFT JOIN locations l ON l.id = c.location_id
        LEFT JOIN LATERAL (
            SELECT * FROM network_metrics nmc
            WHERE nmc.camera_id = c.id
            ORDER BY nmc.recorded_at DESC
            LIMIT 1
        ) nm ON true
        WHERE c.is_active = true
        GROUP BY l.name, l.color, nm.status
        ORDER BY l.name, nm.status
    """)
    )

    cameras_by_location: dict[str, dict] = {}
    for row in loc_result.fetchall():
        loc = row[0]
        loc_color = row[1]
        if loc not in cameras_by_location:
            cameras_by_location[loc] = {
                "total": 0, "online": 0, "degraded": 0, "offline": 0,
                "avg_bw": None, "color": loc_color or "#3b82f6",
            }
        cameras_by_location[loc]["total"] += 1
        status_key = row[2] or "unknown"
        if status_key == "online":
            cameras_by_location[loc]["online"] += 1
        elif status_key == "degraded":
            cameras_by_location[loc]["degraded"] += 1
        elif status_key == "offline":
            cameras_by_location[loc]["offline"] += 1

    return {
        "data": {
            "total_cameras": total_cameras,
            "online_cameras": status_counts["online"],
            "degraded_cameras": status_counts["degraded"],
            "offline_cameras": status_counts["offline"],
            "total_inbound_mbps": float(bw_row[0]) if bw_row else 0.0,
            "total_outbound_mbps": float(bw_row[1]) if bw_row else 0.0,
            "avg_latency_ms": float(bw_row[2]) if bw_row and bw_row[2] else None,
            "active_alerts": alert_row[0] or 0,
            "alerts_by_severity": {"warning": alert_row[1] or 0, "critical": alert_row[2] or 0},
            "cameras_by_location": cameras_by_location,
        }
    }


@router.get("/alerts")
async def get_active_alerts(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Active (unacknowledged) alerts."""
    from ...services.network_alerts import network_alert_service

    if network_alert_service._engine:
        alerts = await network_alert_service.get_active_alerts(network_alert_service._engine)
    else:
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
        alerts = [
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

    return {"data": alerts}


@router.get("/alerts/all")
async def get_all_alerts(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    camera_id: str | None = Query(None),
    severity: str | None = Query(None),
    alert_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    """All alerts (paginated)."""
    offset = (page - 1) * per_page
    conditions = []
    params: dict = {"severity": severity, "alert_type": alert_type}
    if camera_id:
        conditions.append("na.camera_id = :camera_id")
        params["camera_id"] = camera_id
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    result = await db.execute(
        text(f"""
        SELECT na.id, na.camera_id, c.name as camera_name, l.name as location,
               l.color as location_color, na.alert_type, na.severity,
               na.message, na.triggered_at, na.acknowledged_at, na.metadata
        FROM network_alerts na
        JOIN cameras c ON na.camera_id = c.id
        LEFT JOIN locations l ON l.id = c.location_id
        WHERE {where_clause}
        ORDER BY na.triggered_at DESC
        LIMIT :limit OFFSET :offset
    """),
        {**params, "limit": per_page, "offset": offset},
    )
    rows = result.fetchall()

    count_result = await db.execute(
        text(f"""
        SELECT COUNT(1) FROM network_alerts na JOIN cameras c ON na.camera_id = c.id
        WHERE {where_clause}
    """),
        params,
    )
    total_count = count_result.scalar() or 0

    return {
        "data": [
            {
                "id": str(row[0]),
                "camera_id": str(row[1]),
                "camera_name": row[2],
                "location": row[3],
                "location_color": row[4],
                "alert_type": row[5],
                "severity": row[6],
                "message": row[7],
                "triggered_at": row[8].isoformat(),
                "acknowledged_at": row[9].isoformat() if row[9] else None,
                "metadata": dict(row[10]) if row[10] else None,
            }
            for row in rows
        ],
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Acknowledge a network alert."""
    from ...services.network_alerts import network_alert_service

    if network_alert_service._engine:
        result = await network_alert_service.acknowledge_alert(
            alert_id, current_user["id"], network_alert_service._engine
        )
    else:
        result_obj = await db.execute(
            text("""
            UPDATE network_alerts
            SET acknowledged_at = NOW(), acknowledged_by = :user_id
            WHERE id = :alert_id AND acknowledged_at IS NULL
            RETURNING id, acknowledged_at
        """),
            {"alert_id": alert_id, "user_id": current_user["id"]},
        )
        row = result_obj.fetchone()
        await db.commit()
        if row:
            result = {"id": str(row[0]), "acknowledged_at": row[1].isoformat()}
        else:
            result = {"error": "Alert not found or already acknowledged"}

    return {"data": result}


@router.get("/config/{camera_id}")
async def get_camera_config(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get per-camera monitoring config."""
    result = await db.execute(
        text("""
        SELECT poll_interval, ping_enabled, ping_count, ping_timeout, rtsp_check_enabled,
               bandwidth_warn_mbps, bandwidth_crit_mbps, latency_warn_ms, latency_crit_ms,
               packet_loss_warn_pct, packet_loss_crit_pct, retention_days
        FROM camera_network_config WHERE camera_id = :camera_id
    """),
        {"camera_id": camera_id},
    )
    row = result.fetchone()
    if not row:
        return {"data": None}
    return {
        "data": {
            "camera_id": str(camera_id),
            "poll_interval": row[0],
            "ping_enabled": row[1],
            "ping_count": row[2],
            "ping_timeout": row[3],
            "rtsp_check_enabled": row[4],
            "bandwidth_warn_mbps": float(row[5]),
            "bandwidth_crit_mbps": float(row[6]),
            "latency_warn_ms": float(row[7]),
            "latency_crit_ms": float(row[8]),
            "packet_loss_warn_pct": float(row[9]),
            "packet_loss_crit_pct": float(row[10]),
            "retention_days": row[11],
        }
    }


@router.patch("/config/{camera_id}")
async def update_camera_config(
    camera_id: uuid.UUID,
    body: dict,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update per-camera monitoring config."""
    allowed_fields = {
        "poll_interval",
        "ping_enabled",
        "ping_count",
        "ping_timeout",
        "rtsp_check_enabled",
        "bandwidth_warn_mbps",
        "bandwidth_crit_mbps",
        "latency_warn_ms",
        "latency_crit_ms",
        "packet_loss_warn_pct",
        "packet_loss_crit_pct",
        "retention_days",
    }
    updates = {k: v for k, v in body.items() if k in allowed_fields}
    if not updates:
        return {"data": {"status": "no_changes"}}

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["camera_id"] = camera_id

    await db.execute(
        text(f"""
        INSERT INTO camera_network_config (camera_id, {", ".join(updates.keys())})
        VALUES (:camera_id, {", ".join(f":{k}" for k in updates)})
        ON CONFLICT (camera_id) DO UPDATE SET {set_clause}
    """),
        updates,
    )
    await db.commit()
    return {"data": {"status": "updated", "fields": list(updates.keys())}}
