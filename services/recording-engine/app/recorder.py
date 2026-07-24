"""Recording engine — per-camera FFmpeg supervisor with auto-restart.

Design:
- One supervisor task per camera; spawns FFmpeg segment muxer.
- Auto-restart on FFmpeg exit with circuit breaker backoff (60s -> 600s cap).
- Records directly from camera RTSP (sub-stream by default) with -c:v copy
  (no transcode CPU cost; one extra RTSP connection per camera).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import urllib.parse
from collections.abc import Callable

import structlog
from nvr_common.circuit_breaker import CircuitBreaker

from . import config

logger = structlog.get_logger()

STDERR_TAIL_LINES = 20


def build_rtsp_url(stream_uri: str, username: str | None, password: str | None) -> str:
    """Embed credentials into the RTSP URL if not already present."""
    if not username or not password or not stream_uri.startswith("rtsp://"):
        return stream_uri
    parsed = urllib.parse.urlparse(stream_uri)
    if parsed.username:
        return stream_uri
    user = urllib.parse.quote(username, safe="")
    pw = urllib.parse.quote(password, safe="")
    port = f":{parsed.port}" if parsed.port else ""
    return f"rtsp://{user}:{pw}@{parsed.hostname}{port}{parsed.path}"


def build_ffmpeg_args(stream_url: str, camera_dir: str, segment_seconds: int) -> list[str]:
    """FFmpeg segment muxer command — MP4 segments named by UTC clock time."""
    output_pattern = os.path.join(camera_dir, "%Y/%m/%d/%Y%m%d_%H%M%S.mp4")
    return [
        config.FFMPEG_PATH,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-rw_timeout",
        "15000000",  # 15s IO timeout -> exit so supervisor restarts
        "-i",
        stream_url,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-f",
        "segment",
        "-segment_format",
        "mp4",
        "-segment_time",
        str(segment_seconds),
        "-segment_atclocktime",
        "1",
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        output_pattern,
    ]


class CameraRecorder:
    """Supervises the FFmpeg recording process for a single camera."""

    def __init__(
        self,
        camera_id: str,
        camera_name: str,
        stream_uri: str,
        username: str | None,
        password: str | None,
        output_base: str,
        segment_seconds: int,
        on_crash: Callable[[str, str], None] | None = None,
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.password = password
        self.output_base = output_base
        self.segment_seconds = segment_seconds
        self.on_crash = on_crash

        self.stream_url = build_rtsp_url(stream_uri, username, password)
        self.breaker = CircuitBreaker(
            name=f"recording_{camera_id}", base_cooldown=60, max_cooldown=600
        )
        self._task: asyncio.Task | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._stopping = False

    def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._supervise())

    async def stop(self) -> None:
        self._stopping = True
        await self._kill_process()
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("recording_stopped", camera_id=self.camera_id)

    async def _supervise(self) -> None:
        """Restart FFmpeg forever until stopped, with circuit breaker backoff."""
        while not self._stopping:
            if await self.breaker.is_open():
                await asyncio.sleep(min(self.breaker.cooldown_remaining() + 1, 60))
                continue
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("recording_spawn_failed", camera_id=self.camera_id, exc_info=True)
            if self._stopping:
                break
            self.breaker.trip()
            if self.on_crash:
                self.on_crash(self.camera_id, self.camera_name)
            logger.warning(
                "recording_restart_scheduled",
                camera_id=self.camera_id,
                cooldown_s=self.breaker.cooldown_remaining(),
            )

    async def _run_once(self) -> None:
        camera_dir = os.path.join(self.output_base, self.camera_id)
        os.makedirs(camera_dir, exist_ok=True)
        args = build_ffmpeg_args(self.stream_url, camera_dir, self.segment_seconds)

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(
            "recording_started",
            camera_id=self.camera_id,
            camera=self.camera_name,
            pid=self._process.pid,
        )
        self.breaker.reset()
        rc = await self._wait_with_stderr_tail(self._process)
        logger.warning("recording_ffmpeg_exited", camera_id=self.camera_id, returncode=rc)

    async def _wait_with_stderr_tail(self, process: asyncio.subprocess.Process) -> int:
        tail: list[bytes] = []
        assert process.stderr is not None
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            tail.append(line)
            if len(tail) > STDERR_TAIL_LINES:
                tail.pop(0)
        rc = await process.wait()
        if tail and rc != 0:
            logger.warning(
                "recording_ffmpeg_stderr",
                camera_id=self.camera_id,
                tail=b"".join(tail).decode("utf-8", errors="replace")[-1000:],
            )
        return rc

    async def _kill_process(self) -> None:
        process = self._process
        if not process or process.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
