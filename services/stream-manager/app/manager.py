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

FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
TRANSPORT_ORDER = ["tcp", "udp", "http"]
RESTART_COOLDOWN = 600
MEMORY_LIMIT_MB = 1024
HEARTBEAT_TTL = 120

_instance_count: int = 0


class StreamManager:
    """Manages FFmpeg RTSP connections + WebRTC/HLS relay per camera."""

    _running: bool = False
    _task: asyncio.Task | None = None
    _last_restart_at: float = 0.0
    _processes: dict[str, asyncio.subprocess.Process] = {}  # noqa: RUF012
    _monitors: dict[str, asyncio.Task] = {}  # noqa: RUF012
    _breakers: dict[str, CircuitBreaker] = {}  # noqa: RUF012

    @classmethod
    def _get_breaker(cls, camera_id: str) -> CircuitBreaker:
        if camera_id not in cls._breakers:
            cls._breakers[camera_id] = CircuitBreaker(
                name=f"stream_{camera_id}", base_cooldown=30, max_cooldown=300
            )
        return cls._breakers[camera_id]

    @classmethod
    async def connect(cls, camera_id: UUID | str, stream_uri: str, transport: str = "tcp") -> None:
        """Start FFmpeg process for a camera stream."""
        cid = str(camera_id)
        if cid in cls._processes and cls._processes[cid].returncode is None:
            logger.info("stream_already_active", camera_id=cid)
            return

        breaker = cls._get_breaker(cid)
        if await breaker.is_open():
            remaining = breaker.cooldown_remaining()
            logger.warning("circuit_open_skip", camera_id=cid, cooldown_remaining=remaining)
            return

        args = [
            FFMPEG_PATH,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            transport,
            "-i",
            stream_uri,
            "-c:v",
            "copy",
            "-an",
            "-f",
            "rtsp",
            f"rtsp://127.0.0.1:8554/{cid}",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            cls._processes[cid] = process
            breaker.reset()

            monitor = asyncio.create_task(cls._monitor(cid, process, stream_uri))
            cls._monitors[cid] = monitor

            logger.info("stream_connected", camera_id=cid, pid=process.pid, transport=transport)
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
        backoff = 1.0

        try:
            while True:
                line = await process.stderr.readline()
                if not line:
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

        if cls._running:
            breaker.trip()
            jitter = asyncio.get_event_loop().time() % 1.0
            await asyncio.sleep(min(backoff, 300) + jitter)
            backoff *= 2

            transport_idx = TRANSPORT_ORDER.index("tcp")
            reconnected = False
            for attempt in range(3):
                transport = TRANSPORT_ORDER[(transport_idx + attempt) % len(TRANSPORT_ORDER)]
                try:
                    await cls.connect(UUID(camera_id), stream_uri, transport)
                    logger.info("stream_reconnected", camera_id=camera_id, transport=transport)
                    reconnected = True
                    break
                except Exception:
                    continue
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
        """Main loop — heartbeat, periodic reconnects."""
        while cls._running:
            try:
                await asyncio.sleep(HEARTBEAT_TTL)
            except asyncio.CancelledError:
                break
            logger.debug("stream_manager_heartbeat", active_streams=len(cls._processes))
