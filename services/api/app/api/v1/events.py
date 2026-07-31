"""Events API endpoints — event feed, acknowledge, event rules CRUD, bulk delete."""

import os
import uuid
from datetime import date
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import text
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
from ...services.snapshot_service import capture_snapshot_bytes

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
    objects: list[str] | None = Query(None, description="Filter by object class names (e.g. car,person,dog)"),
    object_categories: list[str] | None = Query(None, description="Filter by object category (e.g. animal,vehicle,person)"),
    min_objects: int | None = Query(None, ge=1, description="Minimum number of detected objects"),
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
        object_classes=objects,
        object_categories=object_categories,
        min_objects=min_objects,
    )


@router.get("/{event_id}")
async def get_event_by_id(
    event_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    event = await get_event(event_id, db)
    return {"data": event}


@router.get("/{event_id}/snapshot")
async def get_event_snapshot(
    event_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Serve the AI detection snapshot JPEG (supports ?token= for <img> tags).

    If the saved snapshot file is missing (e.g. written to a container-only /tmp
    fallback or deleted), capture a fresh frame from the camera on demand.
    """
    event = await get_event(event_id, db)
    snapshot_path = event.snapshot_path
    if snapshot_path and os.path.exists(snapshot_path):
        return FileResponse(snapshot_path, media_type="image/jpeg")

    logger.warning(
        "event_snapshot_missing",
        event_id=str(event_id),
        camera_id=str(event.camera_id),
        snapshot_path=snapshot_path,
    )
    try:
        jpeg = await capture_snapshot_bytes(event.camera_id)
        return Response(jpeg, media_type="image/jpeg")
    except HTTPException as exc:
        # Preserve the original HTTP status but surface a clearer message.
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"Snapshot file missing and on-demand capture failed: {exc.detail}",
        ) from exc


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


@router.delete("/cleanup-by-date")
async def cleanup_events_by_date(
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
    before: str = Query(..., description="YYYY-MM-DD — delete events before this date"),
    camera_id: uuid.UUID | None = Query(None),
    dry_run: bool = Query(False),
):
    """Delete events (and their snapshot files) older than the given date.

    ?before=2026-06-01&camera_id=uuid&dry_run=true
    dry_run returns count without deleting.
    """
    try:
        cutoff = date.fromisoformat(before)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.") from exc

    # Get snapshot paths before deleting
    path_query = text(
        "SELECT snapshot_path FROM events WHERE created_at < :cutoff AND snapshot_path IS NOT NULL"
        + (" AND camera_id = :camera_id" if camera_id else "")
    )
    path_params: dict = {"cutoff": cutoff}
    if camera_id:
        path_params["camera_id"] = camera_id
    path_result = await db.execute(path_query, path_params)
    snapshot_paths = [r[0] for r in path_result.fetchall() if r[0]]

    # Count query
    count_query = text(
        "SELECT COUNT(*) FROM events WHERE created_at < :cutoff"
        + (" AND camera_id = :camera_id" if camera_id else "")
    )
    count_result = await db.execute(count_query, path_params)
    event_count = count_result.scalar() or 0

    if dry_run:
        return {"data": {"event_count": event_count, "snapshot_count": len(snapshot_paths), "dry_run": True}}

    # Delete events
    delete_query = text(
        "DELETE FROM events WHERE created_at < :cutoff"
        + (" AND camera_id = :camera_id" if camera_id else "")
    )
    del_result = await db.execute(delete_query, path_params)
    await db.commit()

    # Remove snapshot files
    removed_files = 0
    for sp in snapshot_paths:
        try:
            if os.path.exists(sp):
                os.unlink(sp)
                removed_files += 1
        except OSError:
            pass

    return {
        "data": {
            "deleted_events": del_result.rowcount or 0,
            "deleted_snapshots": removed_files,
            "dry_run": False,
        }
    }
