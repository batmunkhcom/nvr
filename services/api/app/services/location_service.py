"""Location service — CRUD for camera locations."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.camera import Camera
from ..models.location import Location
from ..schemas.location import LocationCreate, LocationUpdate

logger = structlog.get_logger()


def location_to_dict(loc: Location, camera_count: int = 0) -> dict:
    return {
        "id": str(loc.id),
        "name": loc.name,
        "description": loc.description,
        "color": loc.color if hasattr(loc, "color") else "#3b82f6",
        "camera_count": camera_count,
        "created_at": loc.created_at.isoformat() if loc.created_at else None,
    }


async def list_locations(db: AsyncSession) -> dict:
    count_sq = (
        select(Camera.location_id, func.count().label("cnt"))
        .group_by(Camera.location_id)
        .subquery()
    )
    result = await db.execute(
        select(Location, func.coalesce(count_sq.c.cnt, 0))
        .outerjoin(count_sq, count_sq.c.location_id == Location.id)
        .order_by(Location.name)
    )
    return {"data": [location_to_dict(loc, cnt) for loc, cnt in result.all()]}


async def get_location(location_id: uuid.UUID, db: AsyncSession) -> Location:
    result = await db.execute(select(Location).where(Location.id == location_id))
    loc = result.scalar_one_or_none()
    if not loc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return loc


async def create_location(body: LocationCreate, db: AsyncSession) -> Location:
    existing = await db.execute(select(Location).where(Location.name == body.name.strip()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Location with this name already exists"
        )
    loc = Location(name=body.name.strip(), description=body.description, color=body.color)
    db.add(loc)
    await db.flush()
    logger.info("location_created", location_id=str(loc.id), name=loc.name)
    return loc


async def update_location(
    location_id: uuid.UUID, body: LocationUpdate, db: AsyncSession
) -> Location:
    loc = await get_location(location_id, db)
    if body.name is not None:
        name = body.name.strip()
        existing = await db.execute(
            select(Location).where(Location.name == name, Location.id != location_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Location with this name already exists",
            )
        loc.name = name
    if body.description is not None:
        loc.description = body.description
    if body.color is not None:
        loc.color = body.color
    await db.flush()
    logger.info("location_updated", location_id=str(loc.id))
    return loc


async def delete_location(location_id: uuid.UUID, db: AsyncSession) -> None:
    loc = await get_location(location_id, db)
    # cameras.location_id has ON DELETE SET NULL — cameras are unlinked, not deleted
    await db.delete(loc)
    await db.flush()
    logger.info("location_deleted", location_id=str(location_id))
