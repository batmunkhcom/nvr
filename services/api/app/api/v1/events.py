"""Events API endpoints — event feed, acknowledge, event rules CRUD."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user, require_operator
from ...services.event_service import (
    acknowledge_event,
    create_event_rule,
    delete_event_rule,
    get_event,
    list_event_rules,
    list_events,
    update_event_rule,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("")
async def get_events(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    camera_id: uuid.UUID | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    acknowledged: bool | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
):
    return await list_events(
        db,
        page=page,
        per_page=per_page,
        camera_id=camera_id,
        event_type=event_type,
        severity=severity,
        acknowledged=acknowledged,
        from_time=from_time,
        to_time=to_time,
    )


@router.get("/{event_id}")
async def get_event_by_id(
    event_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    event = await get_event(event_id, db)
    return {"data": event}


@router.patch("/{event_id}/acknowledge")
async def ack_event(
    event_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await acknowledge_event(event_id, uuid.UUID(current_user["sub"]), db)
    return {"data": result}


@router.get("/rules/list")
async def get_event_rules(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    camera_id: uuid.UUID | None = None,
):
    return await list_event_rules(db, camera_id)


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def add_event_rule(
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: dict | None = None,
):
    if body is None:
        body = {}
    result = await create_event_rule(db, body)
    return {"data": result}


@router.patch("/rules/{rule_id}")
async def update_event_rule_by_id(
    rule_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: dict | None = None,
):
    if body is None:
        body = {}
    result = await update_event_rule(rule_id, body, db)
    return {"data": result}


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_rule_by_id(
    rule_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await delete_event_rule(rule_id, db)
