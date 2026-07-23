"""Live stream relay — launches FFmpeg subprocess to relay camera RTSP → MediaMTX."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import uuid
from typing import Any

import structlog

logger = structlog.get_logger()

STREAM_DICT: dict[str, dict[str, Any]] = {}
_BG_TASKS: set[asyncio.Task[Any]] = set()
_ffmpeg_path = os.environ.get("FFMPEG_PATH", "ffmpeg")
MEDIAMTX_RTSP = os.environ.get("MEDIAMTX_RTSP", "rtsp://127.0.0.1:8554")

MAX_RESTARTS = 10
BASE_BACKOFF = 3
MAX_BACKOFF = 600  # Rule 17: circuit breaker caps exponential backoff at 10 min


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

    logger.info("relay_start", camera_id=cid, rtsp_uri=rtsp_uri)

    proc = await _spawn_ffmpeg(rtsp_uri, rtsp_transport, cid, target)
    if proc is None:
        return {"hls_url": None, "status": "error", "error": "ffmpeg not installed"}

    STREAM_DICT[cid] = {
        "running": True,
        "process": proc,
        "rtsp_uri": rtsp_uri,
        "rtsp_transport": rtsp_transport,
        "relay_target": target,
        "started_at": asyncio.get_event_loop().time(),
        "restart_count": 0,
    }

    t = asyncio.create_task(_monitor(cid, proc))
    _BG_TASKS.add(t)
    t.add_done_callback(_BG_TASKS.discard)

    return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "started"}


async def _spawn_ffmpeg(
    rtsp_uri: str, rtsp_transport: str, cid: str, relay_target: str | None = None
) -> asyncio.subprocess.Process | None:
    # Always transcode to H264 for universal browser compatibility.
    # -preset ultrafast keeps CPU overhead minimal for live monitoring.
    codec_args = ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency"]
    target = relay_target or MEDIAMTX_RTSP

    try:
        return await asyncio.create_subprocess_exec(
            _ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            rtsp_transport,
            "-i",
            rtsp_uri,
            *codec_args,
            "-an",
            "-f",
            "rtsp",
            "-rtsp_transport",
            "tcp",
            f"{target}/{cid}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("ffmpeg_not_found", path=_ffmpeg_path)
        return None


async def stop_relay(relay_key: str | uuid.UUID) -> dict[str, Any]:
    cid = str(relay_key)
    info = STREAM_DICT.pop(cid, None)
    if not info:
        return {"status": "not_running"}
    info["_stopped_by_user"] = True
    proc = info.get("process")
    if proc and proc.returncode is None:
        _kill_ffmpeg(proc)
    logger.info("relay_stopped", camera_id=cid)
    return {"status": "stopped"}


async def relay_status(relay_key: str | uuid.UUID) -> dict[str, Any]:
    cid = str(relay_key)
    if cid in STREAM_DICT and STREAM_DICT[cid].get("running"):
        return {"running": True, "hls_url": f"/hls/{cid}/index.m3u8"}

    # STREAM_DICT may be stale — check MediaMTX if the path is actually alive
    if await _check_mediamtx_path(cid):
        return {"running": True, "hls_url": f"/hls/{cid}/index.m3u8"}

    return {"running": False, "hls_url": None}


async def _check_mediamtx_path(cid: str) -> bool:
    """Ask MediaMTX control API whether the relay path is alive."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://127.0.0.1:9997/v3/paths/get/{cid}", timeout=2)
            if resp.status_code == 200:
                return bool(resp.json().get("ready"))
    except Exception as exc:
        logger.warning("relay_status_mediamtx_failed", camera_id=cid, error=str(exc))
    return False


async def _monitor(camera_id: str, proc: asyncio.subprocess.Process):
    try:
        await proc.wait()
        exited = proc.returncode
        if proc.stderr:
            stderr_data = await proc.stderr.read()
            if stderr_data:
                logger.warning(
                    "relay_ffmpeg_stderr",
                    camera_id=camera_id,
                    stderr=stderr_data.decode("utf-8", errors="replace")[:500],
                )
        info = STREAM_DICT.get(camera_id)
        if not info or info.get("process") is not proc:
            return
        if info.get("_stopped_by_user"):
            info["running"] = False
            logger.info("relay_exited", camera_id=camera_id, exit_code=exited)
            return

        restart_count = info.get("restart_count", 0)
        if restart_count < MAX_RESTARTS:
            backoff = min(BASE_BACKOFF * (2**restart_count), MAX_BACKOFF)
            logger.info(
                "relay_restarting",
                camera_id=camera_id,
                exit_code=exited,
                restart_in_s=backoff,
                attempt=restart_count + 1,
            )
            info["restart_count"] = restart_count + 1
            await asyncio.sleep(backoff)
            if camera_id not in STREAM_DICT or STREAM_DICT.get(camera_id, {}).get(
                "_stopped_by_user"
            ):
                return

            current_transport = info.get("rtsp_transport", "tcp")
            alternate = "udp" if current_transport == "tcp" else "tcp"
            new_proc = await _spawn_ffmpeg(
                info["rtsp_uri"],
                current_transport,
                camera_id,
                info.get("relay_target"),
            )
            if new_proc:
                info["process"] = new_proc
                info["running"] = True
                t = asyncio.create_task(_monitor(camera_id, new_proc))
                _BG_TASKS.add(t)
                t.add_done_callback(_BG_TASKS.discard)
                return

            # Try alternate transport as fallback (Rule 20: tcp↔udp auto)
            logger.info(
                "relay_transport_fallback",
                camera_id=camera_id,
                from_transport=current_transport,
                to_transport=alternate,
            )
            fallback_proc = await _spawn_ffmpeg(
                info["rtsp_uri"],
                alternate,
                camera_id,
                info.get("relay_target"),
            )
            if fallback_proc:
                info["process"] = fallback_proc
                info["rtsp_transport"] = alternate
                info["running"] = True
                logger.info(
                    "relay_transport_switched",
                    camera_id=camera_id,
                    new_transport=alternate,
                )
                t = asyncio.create_task(_monitor(camera_id, fallback_proc))
                _BG_TASKS.add(t)
                t.add_done_callback(_BG_TASKS.discard)
                return

        info["running"] = False
        logger.error(
            "relay_gave_up",
            camera_id=camera_id,
            exit_code=exited,
            restarts=restart_count,
        )
        await _mark_camera_degraded(camera_id, f"relay gave up (exit {exited})")
    except Exception:
        pass


async def _mark_camera_degraded(camera_id: str, reason: str) -> None:
    """Set camera status to degraded when the relay permanently fails."""
    try:
        import uuid as _uuid

        from sqlalchemy import update

        from ..core.database import async_session_factory
        from ..models.camera import Camera

        cam_uuid = _uuid.UUID(camera_id.split("_")[0])  # strip _sub suffix
        async with async_session_factory() as session:
            await session.execute(
                update(Camera)
                .where(Camera.id == cam_uuid)
                .values(status="degraded", connection_error=reason)
            )
            await session.commit()
        logger.info("relay_marked_degraded", camera_id=camera_id)
    except Exception as exc:
        logger.warning("relay_mark_degraded_failed", camera_id=camera_id, error=str(exc))


def _kill_ffmpeg(proc: asyncio.subprocess.Process):
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    with contextlib.suppress(ProcessLookupError):
        proc.send_signal(signal.SIGTERM)
