"""ONVIF PTZ service — real PTZ control via raw SOAP requests."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from ..core.security import decrypt_password_aes

if TYPE_CHECKING:
    from ..models.camera import Camera

logger = structlog.get_logger()

ONVIF_NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "ptz": "http://www.onvif.org/ver20/ptz/wsdl",
    "tptz": "http://www.onvif.org/ver10/ptz/wsdl",
}

WS_SEC_NS = (
    'xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"'
)
WS_UTIL_NS = (
    'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"'
)

# PTZ Profile Token (usually "profile_1" or first profile)
PROFILE_TOKEN = "profile_1"

# Vendor-specific PTZ HTTP API paths
VENDOR_PTZ_PATHS: dict[str, str] = {
    "hikvision": "/ISAPI/PTZCtrl/channels/1",
    "dahua": "/cgi-bin/ptz.cgi",
    "axis": "/axis-cgi/com/ptz.cgi",
    "foscam": "/cgi-bin/CGIProxy.fcgi",
}


async def ptz_action(
    camera_id: uuid.UUID,
    action: str = "move",
    direction: str | None = None,
    speed: float = 0.5,
    preset_id: int | None = None,
    zoom: str | None = None,
) -> dict[str, Any]:
    """Execute PTZ action on a camera.

    Tries ONVIF first, then falls back to vendor-specific HTTP API.
    """
    camera = await _get_camera(camera_id)

    if preset_id is not None:
        return await _onvif_goto_preset(camera, preset_id)

    if zoom:
        return await _ptz_zoom(camera, zoom, speed)

    if direction:
        return await _ptz_direction(camera, direction, speed)

    return {"status": "ok", "action": "none"}


async def _ptz_direction(camera: Camera, direction: str, speed: float) -> dict[str, Any]:
    """Move camera in a direction using ContinuousMove."""
    pan, tilt = _direction_to_pan_tilt(direction, speed)

    body = _soap_envelope(f"""
        <tptz:ContinuousMove>
            <tptz:ProfileToken>{PROFILE_TOKEN}</tptz:ProfileToken>
            <tptz:Velocity>
                <tptz:PanTilt x="{pan}" y="{tilt}" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"/>
                <tptz:Zoom x="0"/>
            </tptz:Velocity>
        </tptz:ContinuousMove>
    """)

    onvif_ok = await _send_onvif(camera, body)
    if onvif_ok:
        # Short move then stop
        await asyncio.sleep(0.5)
        await _onvif_stop(camera)
        return {"status": "ok", "action": "move", "direction": direction, "speed": speed}

    return await _vendor_ptz(camera, direction, "move", speed)


async def _ptz_zoom(camera: Camera, zoom: str, speed: float) -> dict[str, Any]:
    """Zoom in/out."""
    z = speed if zoom == "in" else -speed

    body = _soap_envelope(f"""
        <tptz:ContinuousMove>
            <tptz:ProfileToken>{PROFILE_TOKEN}</tptz:ProfileToken>
            <tptz:Velocity>
                <tptz:PanTilt x="0" y="0" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"/>
                <tptz:Zoom x="{z}"/>
            </tptz:Velocity>
        </tptz:ContinuousMove>
    """)

    onvif_ok = await _send_onvif(camera, body)
    if onvif_ok:
        await asyncio.sleep(0.5)
        await _onvif_stop(camera)
        return {"status": "ok", "action": "zoom", "zoom": zoom}

    return await _vendor_ptz(camera, zoom, "zoom", speed)


async def _onvif_goto_preset(camera: Camera, preset_id: int) -> dict[str, Any]:
    body = _soap_envelope(f"""
        <tptz:GotoPreset>
            <tptz:ProfileToken>{PROFILE_TOKEN}</tptz:ProfileToken>
            <tptz:PresetToken>{preset_id}</tptz:PresetToken>
        </tptz:GotoPreset>
    """)
    await _send_onvif(camera, body)
    return {"status": "ok", "action": "preset", "preset_id": preset_id}


async def _onvif_stop(camera: Camera):
    body = _soap_envelope(f"""
        <tptz:Stop>
            <tptz:ProfileToken>{PROFILE_TOKEN}</tptz:ProfileToken>
            <tptz:PanTilt>true</tptz:PanTilt>
            <tptz:Zoom>true</tptz:Zoom>
        </tptz:Stop>
    """)
    await _send_onvif(camera, body)


async def _send_onvif(camera: Camera, body: str) -> bool:
    url = camera.onvif_ptz_service_url
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                content=body,
                headers={
                    "Content-Type": 'application/soap+xml; charset=utf-8; action="http://www.onvif.org/ver20/ptz/wsdl/ContinuousMove"',
                },
            )
            return resp.status_code < 400
    except Exception as e:
        logger.warning("onvif_ptz_failed", url=url, error=str(e))
        return False


async def _vendor_ptz(
    camera: Camera, command: str, action: str, speed: float
) -> dict[str, Any]:
    """Fall back to vendor-specific HTTP PTZ API."""
    mfr = (camera.manufacturer or "").lower()
    path = VENDOR_PTZ_PATHS.get(mfr)
    if not path:
        logger.warning("no_vendor_ptz_path", manufacturer=mfr)
        return {"status": "error", "error": "No PTZ API available for this camera"}

    ip = str(camera.ip_address)
    pw = ""
    if camera.encrypted_password:
        with contextlib.suppress(Exception):
            pw = decrypt_password_aes(camera.encrypted_password)

    url = f"http://{ip}{path}"
    params = _build_vendor_params(mfr, command, action, speed)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if mfr == "hikvision":
                resp = await client.put(
                    url, json={"PTZCtrl": {"pan": params.get("pan", 0), "tilt": params.get("tilt", 0)}},
                    auth=(camera.username, pw) if camera.username else None,
                )
            elif mfr == "dahua":
                resp = await client.get(url, params=params, auth=(camera.username, pw) if camera.username else None)
            else:
                resp = await client.get(url, params=params)
            if resp.status_code < 400:
                return {"status": "ok", "action": action, "command": command, "via": "vendor_api"}
            logger.warning("vendor_ptz_failed", url=url, status=resp.status_code)
            return {"status": "error", "error": f"Vendor API returned {resp.status_code}"}
    except Exception as e:
        logger.error("vendor_ptz_exception", url=url, error=str(e), exc_info=True)
        return {"status": "error", "error": str(e)}


def _build_vendor_params(
    mfr: str, command: str, action: str, speed: float
) -> dict[str, Any]:
    """Build vendor-specific HTTP PTZ parameters."""
    if mfr == "dahua":
        dir_map = {"up": "Up", "down": "Down", "left": "Left", "right": "Right",
                   "zoomin": "ZoomInc", "zoomout": "ZoomDec"}
        return {"action": "start", "code": dir_map.get(command, "Up"),
                "arg1": 0, "arg2": int(speed * 10), "arg3": 0}
    if mfr == "axis":
        dir_map = {"up": "up", "down": "down", "left": "left", "right": "right",
                   "zoomin": "zoom_in", "zoomout": "zoom_out"}
        cmd = dir_map.get(command, "up")
        return {"move": cmd, "speed": int(speed * 100)}
    if mfr == "hikvision":
        dir_map = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0),
                   "zoomin": (0, 1), "zoomout": (0, -1)}
        pan, tilt = dir_map.get(command, (0, 0))
        return {"pan": int(pan * speed * 10), "tilt": int(tilt * speed * 10)}
    return {}


def _direction_to_pan_tilt(direction: str, speed: float) -> tuple[float, float]:
    dmap = {
        "up": (0.0, speed),
        "down": (0.0, -speed),
        "left": (-speed, 0.0),
        "right": (speed, 0.0),
        "up-left": (-speed * 0.7, speed * 0.7),
        "up-right": (speed * 0.7, speed * 0.7),
        "down-left": (-speed * 0.7, -speed * 0.7),
        "down-right": (speed * 0.7, -speed * 0.7),
        "zoomin": (0.0, 0.0),
        "zoomout": (0.0, 0.0),
    }
    return dmap.get(direction, (0.0, 0.0))


def _soap_envelope(body_inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
        f' {WS_SEC_NS} {WS_UTIL_NS}>'
        "<s:Header/>"
        f"<s:Body>{body_inner}</s:Body>"
        "</s:Envelope>"
    )


async def _get_camera(camera_id: uuid.UUID) -> Any:
    from sqlalchemy import select

    from ..core.database import async_session_factory
    from ..models.camera import Camera

    async with async_session_factory() as db:
        result = await db.execute(select(Camera).where(Camera.id == camera_id))
        camera = result.scalar_one_or_none()
        if not camera:
            from fastapi import HTTPException
            raise HTTPException(404, "Camera not found")
        return camera
