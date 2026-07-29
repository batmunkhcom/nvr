"""AI detection diagnostics — inspect why a camera may not produce events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.camera import Camera
from ..models.event import Event
from ..models.storage_backend import StorageBackend

logger = structlog.get_logger()

DEFAULT_OBJECTS = ["person", "car", "truck", "bus", "motorcycle", "bicycle", "dog", "cat", "bird"]


async def get_camera_ai_diagnostics(camera_id: uuid.UUID, db: AsyncSession) -> dict:
    """Return a diagnostic report for a camera's AI/object-detection pipeline.

    Checks configuration, storage backend, and recent events. Does NOT talk to
    the AI engine directly — it reads the same DB the AI engine reads.
    """
    result = await db.execute(
        select(
            Camera.id,
            Camera.name,
            Camera.is_active,
            Camera.status,
            Camera.stream_main_uri,
            Camera.stream_sub_uri,
            Camera.username,
            Camera.ai_enabled,
            Camera.ai_objects,
            Camera.ai_min_confidence,
            Camera.ai_zones,
            Camera.ai_sensitivity,
            Camera.motion_source,
            Camera.recording_mode,
            Camera.onvif_events_service_url,
            Camera.location_id,
            Camera.storage_backend_id,
            StorageBackend.id.label("sb_id"),
            StorageBackend.name.label("sb_name"),
            StorageBackend.backend_type.label("sb_type"),
            StorageBackend.mount_point.label("sb_mount_point"),
            StorageBackend.is_active.label("sb_is_active"),
        )
        .outerjoin(StorageBackend, Camera.storage_backend_id == StorageBackend.id)
        .where(Camera.id == camera_id)
    )
    row = result.one_or_none()
    if row is None:
        return {"error": "Camera not found"}

    cam = row._mapping
    issues: list[str] = []
    checks: dict[str, any] = {}

    checks["camera_active"] = bool(cam["is_active"])
    if not cam["is_active"]:
        issues.append("Camera is inactive (is_active=false).")

    checks["ai_enabled"] = bool(cam["ai_enabled"])
    checks["recording_mode"] = cam["recording_mode"]
    if not cam["ai_enabled"] and cam["recording_mode"] != "motion":
        issues.append(
            "AI detection is disabled and recording_mode is not 'motion'. "
            "Enable AI or set recording_mode to motion to start a sampler worker."
        )

    stream_uri = cam["stream_sub_uri"] or cam["stream_main_uri"]
    checks["stream_uri_present"] = bool(stream_uri)
    if not stream_uri:
        issues.append("No stream URI configured (stream_main_uri or stream_sub_uri).")

    checks["motion_source"] = cam["motion_source"]
    if cam["motion_source"] == "camera":
        checks["onvif_events_url_present"] = bool(cam["onvif_events_service_url"])
        if not cam["onvif_events_service_url"]:
            issues.append("motion_source='camera' but onvif_events_service_url is empty.")
    else:
        # server-side motion/AI needs a username so the AI engine uses the relay
        checks["username_present"] = bool(cam["username"])
        if not cam["username"]:
            issues.append(
                "Username is empty. AI engine will fall back to direct RTSP instead of the MediaMTX relay."
            )

    checks["ai_objects"] = cam["ai_objects"] or DEFAULT_OBJECTS
    ai_objects = set(cam["ai_objects"] or DEFAULT_OBJECTS)
    vehicle_objects = {"car", "truck", "bus", "motorcycle", "bicycle"}
    checks["vehicles_in_ai_objects"] = bool(ai_objects & vehicle_objects)
    if not (ai_objects & vehicle_objects):
        issues.append(f"No vehicle classes in ai_objects: {sorted(ai_objects)}. Cars/trucks will not be detected.")

    checks["ai_min_confidence"] = cam["ai_min_confidence"] or 0.5
    if (cam["ai_min_confidence"] or 0.5) > 0.8:
        issues.append(f"ai_min_confidence is very high ({cam['ai_min_confidence']}). Try lowering it to 0.4-0.6.")

    checks["ai_zones_count"] = len([z for z in (cam["ai_zones"] or []) if len(z.get("points", [])) >= 3])
    if checks["ai_zones_count"] > 0:
        issues.append(
            f"{checks['ai_zones_count']} AI zone(s) configured. Detections outside zones are ignored."
        )

    # Storage backend checks
    storage_ok = True
    if cam["storage_backend_id"]:
        checks["storage_backend"] = {
            "id": str(cam["sb_id"]),
            "name": cam["sb_name"],
            "type": cam["sb_type"],
            "mount_point": cam["sb_mount_point"],
            "is_active": bool(cam["sb_is_active"]),
        }
        if not cam["sb_is_active"]:
            storage_ok = False
            issues.append("Selected storage backend is inactive.")
        if cam["sb_type"] == "nfs":
            issues.append(
                "Storage backend type is 'nfs'. A hung/unreachable NFS mount can block snapshot writes; "
                "the AI engine now falls back to /tmp/ai_snapshots after 5s, but verify the mount is healthy."
            )
    else:
        checks["storage_backend"] = None

    # Recent events
    since = datetime.now(UTC) - timedelta(hours=24)
    events_result = await db.execute(
        select(
            func.count(Event.id).label("event_count"),
            func.max(Event.start_time).label("last_event_at"),
        )
        .where(
            Event.camera_id == camera_id,
            Event.event_type == "object_detected",
            Event.start_time >= since,
        )
    )
    events_row = events_result.one()
    checks["object_detected_events_24h"] = events_row.event_count or 0
    checks["last_object_detected_at"] = events_row.last_event_at.isoformat() if events_row.last_event_at else None

    # Recent motion events (if any) give a hint the stream is alive
    motion_result = await db.execute(
        select(func.count(Event.id).label("event_count"))
        .where(
            Event.camera_id == camera_id,
            Event.event_type == "motion",
            Event.start_time >= since,
        )
    )
    checks["motion_events_24h"] = motion_result.scalar() or 0

    # Live stream path that AI engine would use
    if stream_uri and cam["motion_source"] != "camera":
        checks["ai_engine_stream_uri"] = f"rtsp://nvr-mediamtx:8554/{camera_id}_sub"

    return {
        "camera_id": str(camera_id),
        "camera_name": cam["name"],
        "checks": checks,
        "issues": issues,
        "healthy": len(issues) == 0,
    }
