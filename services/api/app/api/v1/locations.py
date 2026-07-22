"""Location API endpoints — CRUD for camera locations."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user, require_operator
from ...schemas.location import LocationCreate, LocationUpdate
from ...services.location_service import (
    create_location,
    delete_location,
    get_location,
    list_locations,
    location_to_dict,
    update_location,
)

router = APIRouter(prefix="/api/v1/locations", tags=["locations"])


@router.get("")
async def get_locations(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await list_locations(db)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_location(
    body: LocationCreate,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    loc = await create_location(body, db)
    return {"data": location_to_dict(loc)}


@router.patch("/{location_id}")
async def update_location_by_id(
    location_id: uuid.UUID,
    body: LocationUpdate,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    loc = await update_location(location_id, body, db)
    return {"data": location_to_dict(loc)}


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location_by_id(
    location_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await delete_location(location_id, db)


@router.get("/{location_id}")
async def get_location_by_id(
    location_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    loc = await get_location(location_id, db)
    return {"data": location_to_dict(loc)}
