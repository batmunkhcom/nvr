"""Live stream relay — delegates to stream-manager service for ffmpeg relay."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

STREAM_DICT: dict[str, dict[str, Any]] = {}
MEDIAMTX_RTSP = os.environ.get("MEDIAMTX_RTSP", "rtsp://nvr-mediamtx:8554")
_MEDIAMTX_API = os.environ.get("MEDIAMTX_API", "http://nvr-mediamtx:9997")
_STREAM_MANAGER_URL = os.environ.get("STREAM_MANAGER_URL", "http://host.docker.internal:8001")


async def _call_stream_manager(
    method: str, endpoint: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        if method == "POST":
            resp = await client.post(f"{_STREAM_MANAGER_URL}{endpoint}", json=payload)
        else:
            resp = await client.get(f"{_STREAM_MANAGER_URL}{endpoint}", params=payload)
        data = resp.json()
        return data


async def start_relay(
    relay_key: str | uuid.UUID,
    rtsp_uri: str,
    rtsp_transport: str = "tcp",
    relay_target: str | None = None,
    force: bool = False,
    bitrate: int | None = None,
    threads: int | None = None,
) -> dict[str, Any]:
    cid = str(relay_key)
    target = relay_target or MEDIAMTX_RTSP

    if not force:
        try:
            status_resp = await _call_stream_manager("GET", "/relay/status", {"relay_key": cid})
            if status_resp.get("running"):
                STREAM_DICT[cid] = {"running": True, "delegated": True}
                return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "already_running"}
        except Exception:
            pass

    logger.info("relay_delegating", camera_id=cid, rtsp_uri=rtsp_uri)

    payload: dict[str, Any] = {
        "relay_key": cid,
        "rtsp_uri": rtsp_uri,
        "transport": rtsp_transport,
        "target": target,
    }
    if bitrate is not None:
        payload["bitrate"] = bitrate
    if threads is not None:
        payload["threads"] = threads

    try:
        result = await _call_stream_manager("POST", "/relay/start", payload)
        status = result.get("status", "")
        if status == "cooldown":
            STREAM_DICT.pop(cid, None)
            return {
                "hls_url": None,
                "status": "cooldown",
                "cooldown_remaining_s": result.get("cooldown_remaining_s", 0),
            }
        if status in ("started", "pending", "already_running"):
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
    # Verify against stream-manager first — STREAM_DICT is only a local cache
    # and can go stale-positive (e.g. relay killed by idle reaper).
    try:
        status_resp = await _call_stream_manager("GET", "/relay/status", {"relay_key": cid})
        if status_resp.get("running"):
            STREAM_DICT[cid] = {"running": True, "delegated": True}
            return {"running": True, "hls_url": f"/hls/{cid}/index.m3u8"}
        STREAM_DICT.pop(cid, None)
    except Exception:
        pass

    if await _check_mediamtx_path(cid):
        return {"running": True, "hls_url": f"/hls/{cid}/index.m3u8"}

    return {"running": False, "hls_url": None}


async def _check_mediamtx_path(cid: str) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_MEDIAMTX_API}/v3/paths/get/{cid}", timeout=2)
            if resp.status_code == 200:
                return bool(resp.json().get("ready"))
    except Exception as exc:
        logger.warning("relay_status_mediamtx_failed", camera_id=cid, error=str(exc))
    return False
