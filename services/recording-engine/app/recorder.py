"""Recording engine — per-camera FFmpeg supervisor with auto-restart.

Design:
- One supervisor task per camera; spawns FFmpeg segment muxer.
- Auto-restart on FFmpeg exit with circuit breaker backoff (5s -> 600s cap).
  The breaker resets only after a stable run (>= STABLE_RUNTIME_S), never on
  spawn — a spawned FFmpeg proves nothing about the connection succeeding.
- A progress watchdog stats the active segment: no mtime/size growth for
  STALL_LIMIT_S means a hung FFmpeg (dead RTSP over live TCP) and it is killed.
- Records directly from camera RTSP (sub-stream by default) with -c:v copy
  (no transcode CPU cost; one extra RTSP connection per camera).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
import urllib.parse
from collections.abc import Callable

import structlog
from nvr_common.circuit_breaker import CircuitBreaker

from . import config

logger = structlog.get_logger()

STDERR_TAIL_LINES = 20
STABLE_RUNTIME_S = 300  # FFmpeg ran this long -> session was healthy -> reset breaker
WATCHDOG_CHECK_S = 60   # progress check interval while FFmpeg runs
CODEC_CACHE_TTL_S = 3600

# Probed (video, audio) codecs per stream URL — avoids an ffprobe round-trip
# on every motion-recorder start.
_CODEC_CACHE: dict[str, tuple[float, str | None, str | None]] = {}


def _ensure_date_dirs(camera_dir: str) -> None:
    """Pre-create YYYY/MM/DD dirs for today and tomorrow (UTC).

    FFmpeg's segment muxer does not create strftime directories itself.
    """
    from datetime import UTC, datetime, timedelta

    for offset in (0, 1):
        day = datetime.now(UTC) + timedelta(days=offset)
        os.makedirs(
            os.path.join(camera_dir, day.strftime("%Y/%m/%d")),
            exist_ok=True,
        )


def _newest_segment_size(camera_dir: str) -> int | None:
    """Size of the most recently modified .mp4 under today's/yesterday's date dirs.

    Used by the stall watchdog; cheap (only two date dirs are checked).
    """
    from datetime import UTC, datetime, timedelta

    newest_mtime = 0.0
    newest_size: int | None = None
    for offset in (0, -1):
        day = datetime.now(UTC) + timedelta(days=offset)
        date_dir = os.path.join(camera_dir, day.strftime("%Y/%m/%d"))
        try:
            names = os.listdir(date_dir)
        except OSError:
            continue
        for name in names:
            if not name.endswith(".mp4"):
                continue
            try:
                st = os.stat(os.path.join(date_dir, name))
            except OSError:
                continue
            if st.st_mtime >= newest_mtime:
                newest_mtime = st.st_mtime
                newest_size = st.st_size
    return newest_size


def build_rtsp_url(stream_uri: str, username: str | None, password: str | None) -> str:
    """Embed credentials into the RTSP URL if not already present."""
    if not username or not password or not stream_uri.startswith("rtsp://"):
        return stream_uri
    parsed = urllib.parse.urlparse(stream_uri)
    if parsed.username:
        return stream_uri
    user = urllib.parse.quote(username, safe="")
    pw = urllib.parse.quote(password, safe="")
    netloc = f"{user}:{pw}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


CODEC_BSF_MAP: dict[str, str] = {
    "h264": "h264_metadata=video_full_range_flag=0",
}


def build_ffmpeg_args(stream_url: str, camera_dir: str, segment_seconds: int, *, video_codec: str | None = None, audio_codec: str | None = None) -> list[str]:
    """FFmpeg segment muxer command — MP4 segments named by UTC clock time.

    H.264 → passthrough with colour-range metadata fix (lowest CPU).
    HEVC  → transcoded to H.264 (Chrome has limited HEVC support).
    Other → passthrough, no filter.
    Audio → copied when already AAC (zero cost), transcoded otherwise."""
    output_pattern = os.path.join(camera_dir, "%Y/%m/%d/%Y%m%d_%H%M%S.mp4")

    input_flags = ["-rtsp_transport", "tcp", "-timeout", "15000000"]
    if video_codec == "hevc":
        input_flags += ["-fflags", "+genpts"]

    args = [
        config.FFMPEG_PATH,
        "-hide_banner",
        "-loglevel",
        "warning",
        *input_flags,
        "-i",
        stream_url,
    ]
    if video_codec == "hevc":
        args += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-color_range", "tv",
            "-colorspace", "bt709",
            "-color_trc", "bt709",
            "-color_primaries", "bt709",
            "-flags", "+global_header",
            # Force a keyframe at least every 30 frames so segment boundaries
            # align with the atclock target instead of drifting a full GOP.
            "-g", "30",
        ]
    else:
        args += ["-c:v", "copy"]
        bsf = CODEC_BSF_MAP.get(video_codec or "")
        if bsf:
            args += ["-bsf:v", bsf]
    if audio_codec == "aac":
        args += ["-c:a", "copy"]
    else:
        args += [
            "-c:a",
            "aac",
            "-b:a",
            "64k",
        ]
    args += [
        "-f",
        "segment",
        "-segment_format",
        "mp4",
        "-segment_format_options",
        "movflags=+faststart",
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
    return args


async def _probe_codecs(stream_url: str, timeout_s: int = 10) -> tuple[str | None, str | None]:
    """Probe (video, audio) codecs of an RTSP stream via ffprobe.

    Results are cached per URL for CODEC_CACHE_TTL_S so motion-mode recorders
    don't pay an ffprobe round-trip on every event.
    """
    cached = _CODEC_CACHE.get(stream_url)
    if cached and time.time() - cached[0] < CODEC_CACHE_TTL_S:
        return cached[1], cached[2]
    video: str | None = None
    audio: str | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            config.FFPROBE_PATH,
            "-v", "quiet",
            "-rtsp_transport", "tcp",
            "-timeout", str(timeout_s * 1_000_000),
            "-show_entries", "stream=codec_type,codec_name",
            "-of", "csv=p=0",
            stream_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        for line in stdout.decode(errors="replace").splitlines():
            parts = line.strip().lower().split(",")
            if len(parts) != 2:
                continue
            if parts[0] == "video" and video is None:
                video = parts[1]
            elif parts[0] == "audio" and audio is None:
                audio = parts[1]
    except Exception:
        logger.warning("recording_codec_probe_failed", stream_url=stream_url[:80], exc_info=True)
    _CODEC_CACHE[stream_url] = (time.time(), video, audio)
    return video, audio


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
        self._video_codec: str | None = None  # cached after first probe
        self._audio_codec: str | None = None
        # Short base cooldown: a camera reboot must cost seconds of footage,
        # not a flat 60s. Escalates 5→10→…→600s on persistent failure.
        self.breaker = CircuitBreaker(
            name=f"recording_{camera_id}", base_cooldown=5, max_cooldown=600
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
        _ensure_date_dirs(camera_dir)

        if self._video_codec is None:
            self._video_codec, self._audio_codec = await _probe_codecs(self.stream_url)
            if self._video_codec:
                logger.info(
                    "recording_codec_detected",
                    camera_id=self.camera_id,
                    video=self._video_codec,
                    audio=self._audio_codec,
                )

        args = build_ffmpeg_args(
            self.stream_url, camera_dir, self.segment_seconds,
            video_codec=self._video_codec, audio_codec=self._audio_codec,
        )

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        if self._stopping:
            # stop() raced with the spawn — don't leak the process.
            await self._kill_process()
            return
        logger.info(
            "recording_started",
            camera_id=self.camera_id,
            camera=self.camera_name,
            pid=self._process.pid,
        )
        start_ts = time.time()
        rc = await self._wait_with_watchdog(self._process, camera_dir)
        logger.warning("recording_ffmpeg_exited", camera_id=self.camera_id, returncode=rc)
        # Breaker history clears only after a stable session — spawn is not success.
        if time.time() - start_ts >= STABLE_RUNTIME_S:
            self.breaker.reset()

    async def _wait_with_watchdog(self, process: asyncio.subprocess.Process, camera_dir: str) -> int:
        """Wait for FFmpeg exit; kill it if the active segment stops growing.

        A hung FFmpeg (dead RTSP session over a live TCP connection, muxer
        stall) records nothing while looking alive — the watchdog turns the
        silent stall into a supervised restart.
        """
        stall_limit = max(2 * self.segment_seconds, 180)
        stderr_task = asyncio.create_task(self._wait_with_stderr_tail(process))
        last_size = -1
        last_growth = time.time()
        try:
            while True:
                done, _pending = await asyncio.wait(
                    {stderr_task}, timeout=WATCHDOG_CHECK_S,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if done:
                    return stderr_task.result()
                # Periodic progress check (+ keep tomorrow's date dir alive).
                _ensure_date_dirs(camera_dir)
                size = _newest_segment_size(camera_dir)
                now = time.time()
                if size is not None and size != last_size:
                    last_size = size
                    last_growth = now
                elif now - last_growth > stall_limit:
                    logger.warning(
                        "recording_stall_detected",
                        camera_id=self.camera_id,
                        stall_s=int(now - last_growth),
                    )
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                    return await stderr_task
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stderr_task

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
