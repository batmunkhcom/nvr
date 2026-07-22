"""Live stream relay — manages FFmpeg subprocess per camera to relay RTSP to MediaMTX."""

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


async def start_relay(camera_id: uuid.UUID, rtsp_uri: str, rtsp_transport: str = "tcp") -> dict[str, Any]:
    """Start FFmpeg relay: camera RTSP → MediaMTX (HLS).

    Returns dict with hls_url and status.
    """
    cid = str(camera_id)

    if cid in STREAM_DICT and STREAM_DICT[cid].get("running"):
        return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "already_running"}

    logger.info("relay_start", camera_id=cid, rtsp_uri=rtsp_uri)

    try:
        proc = await asyncio.create_subprocess_exec(
            _ffmpeg_path,
            "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", rtsp_transport,
            "-i", rtsp_uri,
            "-c:v", "copy", "-an",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"rtsp://127.0.0.1:8554/{cid}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("ffmpeg_not_found", path=_ffmpeg_path)
        return {"hls_url": None, "status": "error", "error": "ffmpeg not found"}

    STREAM_DICT[cid] = {
        "running": True,
        "process": proc,
        "rtsp_uri": rtsp_uri,
        "started_at": asyncio.get_event_loop().time(),
    }

    t = asyncio.create_task(_monitor(cid, proc))
    _BG_TASKS.add(t)
    t.add_done_callback(_BG_TASKS.discard)

    return {"hls_url": f"/hls/{cid}/index.m3u8", "status": "started"}


async def _monitor(camera_id: str, proc: asyncio.subprocess.Process):
    try:
        await proc.wait()
        exited = proc.returncode
        if proc.stderr:
            stderr_data = await proc.stderr.read()
            if stderr_data:
                logger.warning("relay_ffmpeg_stderr", camera_id=camera_id,
                               stderr=stderr_data.decode("utf-8", errors="replace")[:500])
        info = STREAM_DICT.get(camera_id)
        if info and info.get("process") is proc:
            info["running"] = False
        logger.info("relay_exited", camera_id=camera_id, exit_code=exited)
    except Exception:
        pass


def _kill_ffmpeg(proc: asyncio.subprocess.Process):
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    with contextlib.suppress(ProcessLookupError):
        proc.send_signal(signal.SIGTERM)
