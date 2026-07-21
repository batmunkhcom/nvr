"""Event service — business logic for event CRUD, rules engine, and real-time streaming."""

from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.event import Event
from ..models.event_rule import EventRule

logger = structlog.get_logger()


async def list_events(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 25,
    camera_id: uuid.UUID | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    acknowledged: bool | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
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

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(Event.created_at.desc()).offset(offset).limit(per_page)
    )
    events = result.scalars().all()

    return {
        "data": [_event_to_dict(e) for e in events],
        "metadata": {"page": page, "per_page": per_page, "total": total},
    }


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
