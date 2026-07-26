"""Stream Manager — FFmpeg process lifecycle, WebRTC signaling, transport fallback.

Manages RTSP connections per camera. NO storage writes (Recording Engine handles that).
Enforces singleton enforcement, zombie prevention, restart cooldown per AGENTS.md §18.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from uuid import UUID

import structlog
from nvr_common.circuit_breaker import CircuitBreaker

logger = structlog.get_logger()

MEDIAMTX_RTSP_HOST = os.environ.get("MEDIAMTX_RTSP_HOST", "nvr-mediamtx")
MEDIAMTX_API_URL = os.environ.get("MEDIAMTX_API_URL", "http://nvr-mediamtx:9997")
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
TRANSPORT_ORDER = ["tcp", "udp", "http"]
RESTART_COOLDOWN = 600
MEMORY_LIMIT_MB = 1024
HEARTBEAT_TTL = 120
IDLE_TIMEOUT_S = int(os.environ.get("STREAM_IDLE_TIMEOUT_S", "600"))

_instance_count: int = 0


class StreamManager:
    """Manages FFmpeg RTSP connections + WebRTC/HLS relay per camera."""

    _running: bool = False
    _task: asyncio.Task | None = None
    _last_restart_at: float = 0.0
    _processes: dict[str, asyncio.subprocess.Process] = {}  # noqa: RUF012
    _monitors: dict[str, asyncio.Task] = {}  # noqa: RUF012
    _breakers: dict[str, CircuitBreaker] = {}  # noqa: RUF012
    _last_reader_seen: dict[str, float] = {}  # noqa: RUF012

    @classmethod
    def _get_breaker(cls, camera_id: str) -> CircuitBreaker:
        if camera_id not in cls._breakers:
            cls._breakers[camera_id] = CircuitBreaker(
                name=f"stream_{camera_id}", base_cooldown=15, max_cooldown=120
            )
        return cls._breakers[camera_id]

    @classmethod
    async def connect(cls, camera_id: UUID | str, stream_uri: str, transport: str = "tcp", force: bool = False) -> None:
        """Start FFmpeg process for a camera stream."""
        cid = str(camera_id)
        if cid in cls._processes and cls._processes[cid].returncode is None:
            logger.info("stream_already_active", camera_id=cid)
            return

        breaker = cls._get_breaker(cid)
        if await breaker.is_open():
            if force:
                logger.info("circuit_force_reset", camera_id=cid)
                breaker.reset()
            else:
                remaining = breaker.cooldown_remaining()
                logger.warning("circuit_open_skip", camera_id=cid, cooldown_remaining=remaining)
                return

        is_sub = cid.endswith("_sub")
        bitrate = "1000k" if is_sub else "4000k"
        maxrate = "1000k" if is_sub else "4000k"
        bufsize = "2000k" if is_sub else "8000k"

        args = [
            FFMPEG_PATH,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            transport,
            "-timeout",
            "10000000",
            "-i",
            stream_uri,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-g",
            "15",
            "-b:v",
            bitrate,
            "-maxrate",
            maxrate,
            "-bufsize",
            bufsize,
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-ac",
            "1",
            "-pkt_size",
            "1200",
            "-f",
            "rtsp",
            "-rtsp_transport",
            "tcp",
            f"rtsp://{MEDIAMTX_RTSP_HOST}:8554/{cid}",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            cls._processes[cid] = process
            breaker.reset()
            cls._last_reader_seen[cid] = time.time()  # grace period for viewers to attach

            monitor = asyncio.create_task(cls._monitor(cid, process, stream_uri))
            cls._monitors[cid] = monitor

            logger.info("stream_connected", camera_id=cid, pid=process.pid, transport=transport)
            logger.debug("ffmpeg_args", camera_id=cid, args=[*args[:2], "...", *args[-3:]])
        except Exception:
            logger.error("stream_connect_failed", camera_id=cid, exc_info=True)
            breaker.trip()

    @classmethod
    async def disconnect(cls, camera_id: UUID | str) -> None:
        """Gracefully stop FFmpeg for a camera."""
        cid = str(camera_id)
        if cid in cls._monitors:
            cls._monitors[cid].cancel()
            del cls._monitors[cid]
        if cid in cls._processes:
            await cls._kill_ffmpeg(cls._processes[cid])
            del cls._processes[cid]
            logger.info("stream_disconnected", camera_id=cid)

    @classmethod
    async def _monitor(
        cls, camera_id: str, process: asyncio.subprocess.Process, stream_uri: str
    ) -> None:
        """Monitor FFmpeg stderr, memory usage, and auto-reconnect."""
        breaker = cls._get_breaker(camera_id)

        try:
            while True:
                line = await process.stderr.readline()
                if not line:
                    logger.warning("monitor_eof", camera_id=camera_id, pid=process.pid)
                    break
                text = line.decode("utf-8", errors="replace").lower()
                if any(
                    e in text
                    for e in ("connection refused", "404", "unauthorized", "invalid data found")
                ):
                    logger.warning("stream_error", camera_id=camera_id, line=text.strip())
                    breaker.trip()
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error("monitor_error", camera_id=camera_id, exc_info=True)
        finally:
            await cls._kill_ffmpeg(process)
            rc = process.returncode
            if rc is not None:
                logger.warning("ffmpeg_exited", camera_id=camera_id, pid=process.pid, returncode=rc)

        if cls._running:
            jitter = asyncio.get_event_loop().time() % 1.0
            await asyncio.sleep(1.0 + jitter)

            max_attempts = 5 if rc == 0 else 3
            transport_idx = TRANSPORT_ORDER.index("tcp")
            reconnected = False
            for attempt in range(max_attempts):
                transport = TRANSPORT_ORDER[(transport_idx + attempt) % len(TRANSPORT_ORDER)]
                try:
                    await cls.connect(camera_id, stream_uri, transport)
                    logger.info("stream_reconnected", camera_id=camera_id, transport=transport)
                    reconnected = True
                    break
                except Exception as exc:
                    logger.warning("monitor_reconnect_failed", camera_id=camera_id, attempt=attempt+1, error=str(exc))
                    await asyncio.sleep(2)
            if not reconnected:
                breaker.trip()
                logger.warning("monitor_reconnect_exhausted", camera_id=camera_id)
            return reconnected

    @classmethod
    async def _kill_ffmpeg(cls, process: asyncio.subprocess.Process) -> None:
        """SIGTERM → 5s → SIGKILL."""
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                process.kill()
                await process.wait()
        except ProcessLookupError:
            pass

    @classmethod
    async def start(cls) -> None:
        """Start stream manager singleton."""
        global _instance_count
        if _instance_count > 0:
            logger.warning("stream_manager_already_running", count=_instance_count)
            return
        if time.time() - cls._last_restart_at < RESTART_COOLDOWN:
            logger.warning("restart_cooldown_active")
            return

        _instance_count += 1
        cls._last_restart_at = time.time()
        cls._running = True
        cls._task = asyncio.create_task(cls._run())
        logger.info("stream_manager_started")

    @classmethod
    async def stop(cls) -> None:
        """Stop stream manager and all FFmpeg processes."""
        cls._running = False
        for cid in list(cls._processes):
            await cls.disconnect(UUID(cid))

        if cls._task:
            cls._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cls._task

        global _instance_count
        _instance_count = max(0, _instance_count - 1)
        logger.info("stream_manager_stopped")

    @classmethod
    async def _run(cls) -> None:
        """Main loop — heartbeat, idle stream reaping."""
        while cls._running:
            try:
                await asyncio.sleep(HEARTBEAT_TTL)
            except asyncio.CancelledError:
                break
            logger.debug("stream_manager_heartbeat", active_streams=len(cls._processes))
            try:
                await cls._reap_idle_streams()
            except Exception:
                logger.warning("idle_reaper_error", exc_info=True)

    @classmethod
    async def _reap_idle_streams(cls) -> None:
        """Stop relays with zero MediaMTX readers for longer than IDLE_TIMEOUT_S.

        Streams only consume CPU (transcode) while someone watches. Viewers
        re-trigger start via the API when they return.
        """
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{MEDIAMTX_API_URL}/v3/paths/list")
            if resp.status_code != 200:
                return
            items = resp.json().get("items") or []

        now = time.time()
        active_readers: dict[str, int] = {}
        for item in items:
            readers = item.get("readers") or []
            active_readers[item.get("name", "")] = len(readers)

        for cid in list(cls._processes):
            if active_readers.get(cid, 0) > 0:
                cls._last_reader_seen[cid] = now
                continue
            idle_for = now - cls._last_reader_seen.get(cid, now)
            if idle_for > IDLE_TIMEOUT_S:
                logger.info("stream_idle_stop", camera_id=cid, idle_s=int(idle_for))
                await cls.disconnect(cid)
                cls._last_reader_seen.pop(cid, None)
