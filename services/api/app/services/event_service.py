"""Event service — business logic for event CRUD, rules engine, and real-time streaming."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.event import Event
from ..models.event_rule import EventRule

from .config_service import get_timezone, local_date

logger = structlog.get_logger()

# Object category mapping for AI-detected events. Must match the categories used
# by the AI engine (COCO classes + synthetic categories).
OBJECT_CATEGORIES: dict[str, list[str]] = {
    "person": ["person"],
    "animal": ["cat", "dog", "bird"],
    "vehicle": ["car", "truck", "bus", "motorcycle", "bicycle"],
    "livestock": ["horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"],
}

# All supported object classes that can appear in the metadata.objects array.
OBJECT_CLASSES: set[str] = set().union(*OBJECT_CATEGORIES.values())


def _expand_object_filters(
    object_classes: list[str] | None,
    object_categories: list[str] | None,
) -> list[str]:
    """Return concrete COCO class names from class names and/or category names."""
    classes: set[str] = set()
    for cls in object_classes or []:
        classes.add(cls.lower())
    for category in object_categories or []:
        classes.update(OBJECT_CATEGORIES.get(category.lower(), []))
    return sorted(classes)


def _object_class_filter_clause(classes: list[str]) -> str:
    """SQL EXISTS clause: event metadata.objects contains at least one class."""
    placeholders = ", ".join([f":class_{i}" for i in range(len(classes))])
    return (
        "EXISTS ("
        "SELECT 1 FROM jsonb_array_elements(metadata::jsonb->'objects') AS obj "
        f"WHERE obj->>'class' IN ({placeholders})"
        ")"
    )


def _object_count_clause(classes: list[str] | None) -> str:
    """SQL scalar subquery: count matching objects in metadata."""
    if classes:
        placeholders = ", ".join([f":class_{i}" for i in range(len(classes))])
        where_clause = f"WHERE obj->>'class' IN ({placeholders})"
    else:
        where_clause = ""
    return (
        "SELECT COUNT(*) FROM jsonb_array_elements(metadata::jsonb->'objects') AS obj "
        f"{where_clause}"
    )


async def list_events(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 10,
    camera_id: uuid.UUID | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    acknowledged: bool | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    object_classes: list[str] | None = None,
    object_categories: list[str] | None = None,
    min_objects: int | None = None,
) -> dict:
    offset = (page - 1) * per_page
    query = select(Event)

    if camera_id:
        query = query.where(Event.camera_id == camera_id)
    if event_type:
        query = query.where(Event.event_type == event_type)
    if severity:
        query = query.where(Event.severity == severity)
    if acknowledged is not None:
        query = query.where(Event.is_acknowledged == acknowledged)
    if from_time:
        query = query.where(Event.created_at >= from_time)
    if to_time:
        query = query.where(Event.created_at <= to_time)

    classes = _expand_object_filters(object_classes, object_categories)
    if classes:
        clause = _object_class_filter_clause(classes)
        params = {f"class_{i}": cls for i, cls in enumerate(classes)}
        query = query.where(text(clause).bindparams(**params))

    if min_objects is not None and min_objects > 0:
        clause = _object_count_clause(classes if classes else None)
        params = {f"class_{i}": cls for i, cls in enumerate(classes)} if classes else {}
        params["min_objects"] = min_objects
        query = query.where(text(f"({clause}) >= :min_objects").bindparams(**params))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # per_page=0 means "all" — no LIMIT clause.
    limit = per_page if per_page and per_page > 0 else None
    result = await db.execute(
        query.order_by(Event.created_at.desc()).offset(offset).limit(limit)
    )
    events = result.scalars().all()

    return {
        "data": [_event_to_dict(e) for e in events],
        "metadata": {"page": page, "per_page": per_page, "total": total},
    }


async def get_event_daily(
    db: AsyncSession,
    camera_id: uuid.UUID | None = None,
    days: int = 7,
) -> list[dict]:
    """Daily event/detection counts in the local timezone, zero-filled."""
    tz = await get_timezone(db)
    today = local_date(tz)
    start_local = datetime.combine(today - timedelta(days=days - 1), time.min, tzinfo=tz)

    params: dict = {"start": start_local, "tz_name": str(tz)}
    camera_clause = ""
    if camera_id:
        camera_clause = " AND camera_id = CAST(:camera_id AS uuid)"
        params["camera_id"] = camera_id

    result = await db.execute(
        text(f"""
            SELECT (created_at AT TIME ZONE :tz_name)::date AS d,
                   COUNT(*)::int AS detections,
                   COUNT(*) FILTER (WHERE is_acknowledged)::int AS acknowledged
            FROM events
            WHERE created_at >= :start{camera_clause}
            GROUP BY d
            ORDER BY d
        """),
        params,
    )
    by_date: dict[date, dict] = {}
    for row in result.fetchall():
        by_date[row[0]] = {"detections": row[1], "acknowledged": row[2]}

    series = []
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).isoformat()
        row = by_date.get(date.fromisoformat(d), {})
        series.append(
            {
                "date": d,
                "detections": row.get("detections", 0),
                "acknowledged": row.get("acknowledged", 0),
            }
        )
    return series


async def get_event(event_id: uuid.UUID, db: AsyncSession) -> Event:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


async def acknowledge_event(event_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> dict:
    event = await get_event(event_id, db)
    event.is_acknowledged = True
    event.acknowledged_by = user_id
    await db.flush()
    return {"id": str(event.id), "is_acknowledged": True}


async def list_event_rules(db: AsyncSession, camera_id: uuid.UUID | None = None) -> dict:
    query = select(EventRule)
    if camera_id:
        query = query.where(EventRule.camera_id == camera_id)
    result = await db.execute(query.order_by(EventRule.created_at.desc()))
    rules = result.scalars().all()
    return {"data": [_rule_to_dict(r) for r in rules]}


async def create_event_rule(db: AsyncSession, data: dict) -> dict:
    rule = EventRule(
        camera_id=data.get("camera_id"),
        rule_name=data["rule_name"],
        event_type=data.get("event_type", "motion_detected"),
        conditions=data.get("conditions", {}),
        actions=data.get("actions", {"record": True}),
        cooldown_seconds=data.get("cooldown_seconds", 60),
    )
    db.add(rule)
    await db.flush()
    return _rule_to_dict(rule)


async def update_event_rule(rule_id: uuid.UUID, data: dict, db: AsyncSession) -> dict:
    result = await db.execute(select(EventRule).where(EventRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event rule not found")
    for field, value in data.items():
        if hasattr(rule, field) and value is not None:
            setattr(rule, field, value)
    await db.flush()
    return _rule_to_dict(rule)


async def delete_event_rule(rule_id: uuid.UUID, db: AsyncSession) -> None:
    result = await db.execute(select(EventRule).where(EventRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event rule not found")
    await db.delete(rule)
    await db.flush()


def _event_to_dict(e: Event) -> dict:
    return {
        "id": str(e.id),
        "camera_id": str(e.camera_id),
        "event_type": e.event_type,
        "severity": e.severity,
        "start_time": e.start_time.isoformat() if e.start_time else None,
        "end_time": e.end_time.isoformat() if e.end_time else None,
        "metadata": e.event_metadata,
        "snapshot_path": e.snapshot_path,
        "is_acknowledged": e.is_acknowledged,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _rule_to_dict(r: EventRule) -> dict:
    return {
        "id": str(r.id),
        "camera_id": str(r.camera_id) if r.camera_id else None,
        "rule_name": r.rule_name,
        "event_type": r.event_type,
        "conditions": r.conditions,
        "actions": r.actions,
        "cooldown_seconds": r.cooldown_seconds,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
