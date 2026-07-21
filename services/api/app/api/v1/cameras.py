"""Camera API endpoints — CRUD + discovery + live + test."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...middleware.auth import get_current_user, require_operator
from ...schemas.camera import CameraCreate, CameraUpdate, DiscoveryRequest
from ...services.camera_service import (
    camera_to_dict,
    create_camera,
    delete_camera,
    get_camera_response,
    list_cameras,
    test_camera_connection,
    update_camera,
)
from ...services.camera_service_audio import start_talk_session, stop_talk_session
from ...services.camera_service_ptz import ptz_action
from ...services.discovery_service import (
    get_discovery_results,
    get_discovery_status,
    start_discovery,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"])


@router.get("")
async def get_cameras(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    manufacturer: str | None = None,
    status: str | None = None,
    search: str | None = None,
    has_ptz: bool | None = None,
    has_audio: bool | None = None,
    sort: str = "name",
    order: str = "asc",
):
    return await list_cameras(
        db,
        page=page,
        per_page=per_page,
        manufacturer=manufacturer,
        status=status,
        search=search,
        has_ptz=has_ptz,
        has_audio=has_audio,
        sort=sort,
        order=order,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_camera(
    body: CameraCreate,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    camera = await create_camera(body, db)
    return {"data": camera_to_dict(camera)}


@router.get("/{camera_id}")
async def get_camera_by_id(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_camera_response(camera_id, db)


@router.patch("/{camera_id}")
async def update_camera_by_id(
    camera_id: uuid.UUID,
    body: CameraUpdate,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    camera = await update_camera(camera_id, body, db)
    return {"data": camera_to_dict(camera)}


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera_by_id(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
    keep_recordings: bool = Query(False),
):
    await delete_camera(camera_id, keep_recordings, db)


@router.post("/{camera_id}/test")
async def test_camera(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await test_camera_connection(camera_id, db)
    return {"data": result}


@router.post("/discover", status_code=status.HTTP_202_ACCEPTED)
async def discover_cameras(
    body: DiscoveryRequest,
    current_user: Annotated[dict, Depends(require_operator)],
):
    result = await start_discovery(
        subnets=body.subnets,
        methods=body.methods,
        timeout=body.timeout,
    )
    return {"data": result}


@router.get("/discover/{scan_id}/status")
async def discover_status(
    scan_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
):
    result = await get_discovery_status(scan_id)
    return {"data": result}


@router.get("/discover/{scan_id}/results")
async def discover_results(
    scan_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
):
    result = await get_discovery_results(scan_id)
    return {"data": result}


@router.post("/{camera_id}/ptz")
async def camera_ptz(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
    action: str = "move",
    direction: str | None = None,
    speed: float = 0.5,
    preset_id: int | None = None,
    zoom: str | None = None,
):
    result = await ptz_action(
        camera_id, action=action, direction=direction, speed=speed, preset_id=preset_id, zoom=zoom
    )
    return {"data": result}


@router.post("/{camera_id}/talk/start")
async def start_talk(
    camera_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
):
    result = await start_talk_session(camera_id)
    return {"data": result}


@router.post("/{camera_id}/talk/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_talk(
    camera_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: Annotated[dict, Depends(require_operator)],
):
    await stop_talk_session(session_id)
