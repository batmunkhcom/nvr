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


async def start_relay(
    relay_key: str | uuid.UUID, rtsp_uri: str, rtsp_transport: str = "tcp"
) -> dict[str, Any]:
    cid = str(relay_key)

    if cid in STREAM_DICT and STREAM_DICT[cid].get("running"):
        return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "already_running"}

    logger.info("relay_start", camera_id=cid, rtsp_uri=rtsp_uri)

    proc = await _spawn_ffmpeg(rtsp_uri, rtsp_transport, cid)
    if proc is None:
        return {"hls_url": None, "status": "error", "error": "ffmpeg not installed"}

    STREAM_DICT[cid] = {
        "running": True,
        "process": proc,
        "rtsp_uri": rtsp_uri,
        "rtsp_transport": rtsp_transport,
        "started_at": asyncio.get_event_loop().time(),
        "restart_count": 0,
    }

    t = asyncio.create_task(_monitor(cid, proc))
    _BG_TASKS.add(t)
    t.add_done_callback(_BG_TASKS.discard)

    return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "started"}


async def _spawn_ffmpeg(
    rtsp_uri: str, rtsp_transport: str, cid: str
) -> asyncio.subprocess.Process | None:
    try:
        return await asyncio.create_subprocess_exec(
            _ffmpeg_path,
            "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", rtsp_transport,
            "-i", rtsp_uri,
            "-c:v", "copy", "-an",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"{MEDIAMTX_RTSP}/{cid}",
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
    return {"running": False, "hls_url": None}


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
            backoff = min(BASE_BACKOFF * (2 ** restart_count), 60)
            logger.info(
                "relay_restarting",
                camera_id=camera_id,
                exit_code=exited,
                restart_in_s=backoff,
                attempt=restart_count + 1,
            )
            info["restart_count"] = restart_count + 1
            await asyncio.sleep(backoff)
            if camera_id not in STREAM_DICT or STREAM_DICT.get(camera_id, {}).get("_stopped_by_user"):
                return
            new_proc = await _spawn_ffmpeg(
                info["rtsp_uri"], info.get("rtsp_transport", "tcp"), camera_id
            )
            if new_proc:
                info["process"] = new_proc
                info["running"] = True
                t = asyncio.create_task(_monitor(camera_id, new_proc))
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
    except Exception:
        pass


def _kill_ffmpeg(proc: asyncio.subprocess.Process):
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    with contextlib.suppress(ProcessLookupError):
        proc.send_signal(signal.SIGTERM)
