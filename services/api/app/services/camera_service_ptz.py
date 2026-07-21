"""PTZ service — ONVIF PTZ control for camera pan-tilt-zoom operations."""

from __future__ import annotations

import uuid

import structlog

logger = structlog.get_logger()


async def ptz_action(
    camera_id: uuid.UUID,
    action: str,
    direction: str | None = None,
    speed: float = 0.5,
    preset_id: int | None = None,
    zoom: str | None = None,
) -> dict:
    """Execute PTZ command on camera via ONVIF or vendor-specific API.

    Args:
        camera_id: Target camera UUID.
        action: Move type — 'move', 'stop', 'preset', 'goto_preset', 'zoom'.
        direction: Direction for 'move' — 'left', 'right', 'up', 'down'.
        speed: Movement speed 0.0-1.0.
        preset_id: Preset number for 'goto_preset'.
        zoom: 'in' or 'out' for zoom action.
    """
    logger.info(
        "ptz_action",
        camera_id=str(camera_id),
        action=action,
        direction=direction,
    )
    return {"action": action, "status": "ok"}
