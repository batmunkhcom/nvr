"""Live stream relay — uses MediaMTX HTTP API to pull RTSP and serve HLS (no ffmpeg needed)."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

MEDIAMTX_API = os.environ.get("MEDIAMTX_API", "http://10.10.0.229:9997")
MEDIAMTX_HLS = os.environ.get("MEDIAMTX_HLS", "http://10.10.0.229:8888")
STREAM_DICT: dict[str, dict[str, Any]] = {}
MEDIAMTX_AUTH = ("admin", "nvr123")


async def start_relay(camera_id: uuid.UUID, rtsp_uri: str, rtsp_transport: str = "tcp") -> dict[str, Any]:
    """Start streaming via MediaMTX: configure path to pull RTSP source.

    Returns dict with hls_url and status.
    """
    cid = str(camera_id)

    if cid in STREAM_DICT and STREAM_DICT[cid].get("running"):
        return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "already_running"}

    logger.info("relay_start_via_api", camera_id=cid, rtsp_uri=rtsp_uri)

    try:
        async with httpx.AsyncClient(timeout=5.0, auth=MEDIAMTX_AUTH) as client:
            resp = await client.post(
                f"{MEDIAMTX_API}/v3/config/paths/add/{cid}",
                json={"source": rtsp_uri, "runOnDemand": True, "runOnDemandCloseAfter": 30},
            )
            if resp.status_code >= 400:
                logger.error("mediamtx_api_error", status=resp.status_code, body=resp.text[:200])
                return {"hls_url": None, "status": "error", "error": f"MediaMTX API error {resp.status_code}"}

        STREAM_DICT[cid] = {"running": True, "rtsp_uri": rtsp_uri}
        return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "started"}

    except Exception as e:
        logger.error("mediamtx_connection_failed", error=str(e), exc_info=True)
        return {"hls_url": None, "status": "error", "error": "Cannot reach MediaMTX"}


async def stop_relay(camera_id: uuid.UUID) -> dict[str, Any]:
    """Remove path from MediaMTX."""
    cid = str(camera_id)
    if cid not in STREAM_DICT:
        return {"status": "not_running"}

    try:
        async with httpx.AsyncClient(timeout=5.0, auth=MEDIAMTX_AUTH) as client:
            await client.delete(f"{MEDIAMTX_API}/v3/config/paths/delete/{cid}")
        STREAM_DICT.pop(cid, None)
        logger.info("relay_stopped", camera_id=cid)
        return {"status": "stopped"}
    except Exception as e:
        logger.error("mediamtx_stop_failed", camera_id=cid, error=str(e))
        return {"status": "error", "error": str(e)}


async def relay_status(camera_id: uuid.UUID) -> dict[str, Any]:
    cid = str(camera_id)
    if cid in STREAM_DICT and STREAM_DICT[cid].get("running"):
        return {"running": True, "hls_url": f"/hls/{cid}/index.m3u8"}
    return {"running": False, "hls_url": None}
