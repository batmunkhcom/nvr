"""Live stream relay — delegates to stream-manager service for ffmpeg relay."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

STREAM_DICT: dict[str, dict[str, Any]] = {}
MEDIAMTX_RTSP = os.environ.get("MEDIAMTX_RTSP", "rtsp://127.0.0.1:8554")
_STREAM_MANAGER_URL = os.environ.get("STREAM_MANAGER_URL", "http://host.docker.internal:8001")


async def _call_stream_manager(
    method: str, endpoint: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        if method == "POST":
            resp = await client.post(f"{_STREAM_MANAGER_URL}{endpoint}", json=payload)
        else:
            resp = await client.get(f"{_STREAM_MANAGER_URL}{endpoint}", params=payload)
        resp.raise_for_status()
        return resp.json()


async def start_relay(
    relay_key: str | uuid.UUID,
    rtsp_uri: str,
    rtsp_transport: str = "tcp",
    relay_target: str | None = None,
) -> dict[str, Any]:
    cid = str(relay_key)
    target = relay_target or MEDIAMTX_RTSP

    if cid in STREAM_DICT and STREAM_DICT[cid].get("running"):
        return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "already_running"}

    logger.info("relay_delegating", camera_id=cid, rtsp_uri=rtsp_uri)

    try:
        result = await _call_stream_manager("POST", "/relay/start", {
            "relay_key": cid,
            "rtsp_uri": rtsp_uri,
            "transport": rtsp_transport,
            "target": target,
        })
        STREAM_DICT[cid] = {"running": True, "delegated": True}
        return result
    except Exception as exc:
        logger.error("relay_delegate_failed", camera_id=cid, error=str(exc))
        return {"hls_url": None, "status": "error", "error": str(exc)}


async def stop_relay(relay_key: str | uuid.UUID) -> dict[str, Any]:
    cid = str(relay_key)
    STREAM_DICT.pop(cid, None)
    try:
        return await _call_stream_manager("POST", "/relay/stop", {"relay_key": cid})
    except Exception:
        return {"status": "stopped"}


async def relay_status(relay_key: str | uuid.UUID) -> dict[str, Any]:
    cid = str(relay_key)
    if cid in STREAM_DICT and STREAM_DICT[cid].get("running"):
        return {"running": True, "hls_url": f"/hls/{cid}/index.m3u8"}

    if await _check_mediamtx_path(cid):
        return {"running": True, "hls_url": f"/hls/{cid}/index.m3u8"}

    return {"running": False, "hls_url": None}


async def _check_mediamtx_path(cid: str) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://127.0.0.1:9997/v3/paths/get/{cid}", timeout=2)
            if resp.status_code == 200:
                return bool(resp.json().get("ready"))
    except Exception as exc:
        logger.warning("relay_status_mediamtx_failed", camera_id=cid, error=str(exc))
    return False
