"""Recording engine — continuous and motion-triggered recording handlers."""

from __future__ import annotations

import asyncio
import os
from collections import deque

import structlog
from nvr_common.circuit_breaker import CircuitBreaker

logger = structlog.get_logger()

_engine_instance: RecordingEngine | None = None
FFMPEG_CMD = os.environ.get("FFMPEG_PATH", "ffmpeg")
RESTART_COOLDOWN = 600


class RecordingEngine:
    """Manages FFmpeg recording per camera with circuit breaker and retry."""

    circuit_breakers: dict[str, CircuitBreaker] = {}  # noqa: RUF012
    _running: bool = False
    _subtasks: list[asyncio.Task] = []  # noqa: RUF012

    @classmethod
    def get_breaker(cls, camera_id: str) -> CircuitBreaker:
        if camera_id not in cls.circuit_breakers:
            cls.circuit_breakers[camera_id] = CircuitBreaker(
                name=f"recording_{camera_id}",
                base_cooldown=60,
                max_cooldown=600,
            )
        return cls.circuit_breakers[camera_id]

    @classmethod
    async def start(cls, camera_id: str, stream_uri: str, output_dir: str) -> None:
        """Start recording for a camera."""
        breaker = cls.get_breaker(camera_id)
        if await breaker.is_open():
            logger.warning("circuit_open_skip", camera_id=camera_id)
            return

        import os

        output_path = os.path.join(output_dir, str(camera_id), "%Y/%m/%d/%Y%m%d_%H%M%S.mp4")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        args = [
            FFMPEG_CMD,
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            stream_uri,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "segment",
            "-segment_format",
            "mp4",
            "-segment_time",
            "900",
            "-segment_atclocktime",
            "1",
            "-reset_timestamps",
            "1",
            "-strftime",
            "1",
            output_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info("recording_started", camera_id=camera_id, pid=process.pid)

            monitor_task = asyncio.create_task(
                cls._monitor(camera_id, process, stream_uri, output_dir)
            )
            cls._subtasks.append(monitor_task)
        except Exception:
            logger.error("recording_start_failed", camera_id=camera_id, exc_info=True)
            breaker.trip()

    @classmethod
    async def _monitor(
        cls, camera_id: str, process: asyncio.subprocess.Process, stream_uri: str, output_dir: str
    ) -> None:
        """Monitor FFmpeg stderr for errors and handle process death."""
        breaker = cls.get_breaker(camera_id)
        try:
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").lower()
                if "connection refused" in text or "404" in text or "unauthorized" in text:
                    logger.warning("recording_stream_error", camera_id=camera_id, line=text.strip())
                    breaker.trip()
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error("monitor_error", camera_id=camera_id, exc_info=True)
        finally:
            await cls._kill_ffmpeg(process)
            breaker.trip()
            logger.info("recording_stopped", camera_id=camera_id)

    @classmethod
    async def _kill_ffmpeg(cls, process: asyncio.subprocess.Process) -> None:
        """Graceful shutdown: SIGTERM → 5s wait → SIGKILL."""
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
    async def stop(cls) -> None:
        """Stop all recordings and clean up subtasks."""
        cls._running = False
        for task in cls._subtasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*cls._subtasks, return_exceptions=True)
        cls._subtasks.clear()
        logger.info("recording_engine_stopped")


class MotionBuffer:
    """Pre-record buffer for motion-triggered recording."""

    def __init__(self, pre_record_s: int = 5, fps: int = 25):
        self.pre_record_s = pre_record_s
        self.buffer: deque[bytes] = deque(maxlen=pre_record_s * fps)

    def push(self, frame: bytes) -> None:
        self.buffer.append(frame)

    def flush(self) -> list[bytes]:
        frames = list(self.buffer)
        self.buffer.clear()
        return frames
