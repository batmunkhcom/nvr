"""Camera service — business logic for camera CRUD, discovery orchestration, connection testing."""

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import encrypt_password_aes
from ..models.camera import Camera
from ..schemas.camera import CameraCreate, CameraUpdate

logger = structlog.get_logger()


async def list_cameras(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 25,
    manufacturer: str | None = None,
    status: str | None = None,
    search: str | None = None,
    has_ptz: bool | None = None,
    has_audio: bool | None = None,
    sort: str = "name",
    order: str = "asc",
) -> dict:
    offset = (page - 1) * per_page
    query = select(Camera)

    if manufacturer:
        query = query.where(Camera.manufacturer == manufacturer)
    if status:
        query = query.where(Camera.status == status)
    if search:
        query = query.where(Camera.name.ilike(f"%{search}%"))
    if has_ptz is not None:
        query = query.where(Camera.has_ptz == has_ptz)
    if has_audio is not None:
        query = query.where(Camera.has_audio == has_audio)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    sort_col = getattr(Camera, sort, Camera.name)
    query = query.order_by(sort_col.desc()) if order == "desc" else query.order_by(sort_col.asc())

    result = await db.execute(query.offset(offset).limit(per_page))
    cameras = result.scalars().all()

    return {
        "data": [_camera_to_response(c) for c in cameras],
        "metadata": {"page": page, "per_page": per_page, "total": total},
    }


def camera_to_dict(camera: Camera) -> dict:
    return _camera_to_response(camera)


async def get_camera(camera_id: uuid.UUID, db: AsyncSession) -> Camera:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera


async def get_camera_response(camera_id: uuid.UUID, db: AsyncSession) -> dict:
    camera = await get_camera(camera_id, db)
    return _camera_to_response(camera)


async def create_camera(body: CameraCreate, db: AsyncSession) -> Camera:
    existing = await db.execute(select(Camera).where(Camera.ip_address == body.ip_address))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Camera with this IP already exists"
        )

    encrypted_pw = None
    if body.password:
        encrypted_pw = encrypt_password_aes(body.password)

    now = datetime.now(UTC)
    camera = Camera(
        name=body.name,
        ip_address=body.ip_address,
        username=body.username,
        encrypted_password=encrypted_pw,
        auth_type=body.auth_type,
        stream_main_uri=body.stream_main_uri,
        stream_sub_uri=body.stream_sub_uri,
        stream_audio_uri=body.stream_audio_uri,
        recording_mode=body.recording_mode,
        stream_transport=body.stream_transport,
        tags=body.tags,
        location=body.location,
        notes=body.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(camera)
    await db.flush()
    logger.info("camera_created", camera_id=str(camera.id), name=camera.name)

    try:
        from .camera_probe import probe_ip
        ip_str = str(camera.ip_address)
        result = await probe_ip(ip_str)
        camera.status = "online" if result["reachable"] else "offline"
        camera.last_seen_at = datetime.now(UTC)
        await db.flush()
        logger.info("camera_auto_tested", camera_id=str(camera.id), status=camera.status)
    except Exception:
        logger.warning("camera_auto_test_failed", camera_id=str(camera.id), exc_info=True)

    return camera


async def update_camera(camera_id: uuid.UUID, body: CameraUpdate, db: AsyncSession) -> Camera:
    camera = await get_camera(camera_id, db)
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)
    camera.updated_at = datetime.now(UTC)
    await db.flush()
    logger.info("camera_updated", camera_id=str(camera.id))
    return camera


async def delete_camera(camera_id: uuid.UUID, keep_recordings: bool, db: AsyncSession) -> None:
    camera = await get_camera(camera_id, db)
    await db.delete(camera)
    await db.flush()
    logger.info("camera_deleted", camera_id=str(camera_id), keep_recordings=keep_recordings)


async def test_camera_connection(camera_id: uuid.UUID, db: AsyncSession) -> dict:
    camera = await get_camera(camera_id, db)
    from .camera_probe import probe_ip
    ip_str = str(camera.ip_address)
    result = await probe_ip(ip_str)
    camera.status = "online" if result["reachable"] else "offline"
    camera.last_seen_at = datetime.now(UTC)
    await db.flush()
    return {
        "reachable": result["reachable"],
        "rtsp_ok": result.get("has_rtsp", False),
        "latency_ms": None,
        "stream_resolution": None,
        "stream_codec": None,
        "manufacturer": result.get("manufacturer"),
        "open_ports": result.get("open_ports", []),
    }


def _camera_to_response(camera: Camera) -> dict:
    return {
        "id": str(camera.id),
        "name": camera.name,
        "ip_address": str(camera.ip_address) if camera.ip_address else None,
        "mac_address": str(camera.mac_address) if camera.mac_address else None,
        "manufacturer": camera.manufacturer,
        "model": camera.model,
        "firmware_version": camera.firmware_version,
        "serial_number": camera.serial_number,
        "stream_main_uri": camera.stream_main_uri,
        "stream_sub_uri": camera.stream_sub_uri,
        "stream_audio_uri": camera.stream_audio_uri,
        "auth_type": camera.auth_type,
        "username": camera.username,
        "has_audio": camera.has_audio,
        "has_talkback": camera.has_talkback,
        "has_ptz": camera.has_ptz,
        "has_onvif": camera.has_onvif,
        "has_motion_detection": camera.has_motion_detection,
        "has_io_ports": camera.has_io_ports,
        "motion_source": camera.motion_source,
        "max_resolution": camera.max_resolution,
        "recording_mode": camera.recording_mode,
        "stream_transport": camera.stream_transport,
        "ptz_presets": camera.ptz_presets,
        "status": camera.status,
        "last_seen_at": camera.last_seen_at.isoformat() if camera.last_seen_at else None,
        "tags": camera.tags,
        "location": camera.location,
        "notes": camera.notes,
        "privacy_mode": camera.privacy_mode,
        "created_at": camera.created_at.isoformat() if camera.created_at else None,
        "updated_at": camera.updated_at.isoformat() if camera.updated_at else None,
    }
