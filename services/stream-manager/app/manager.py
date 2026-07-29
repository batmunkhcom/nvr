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
# An FFmpeg that ran at least this long before exiting is considered to have
# had a stable session — its circuit-breaker trip history is cleared.
STABLE_RUNTIME_S = 60
# MediaMTX pull mode: "sub" | "all" | "" (off). Pull-mode relays let MediaMTX
# fetch the camera itself (sourceOnDemand) instead of an FFmpeg libx264
# relay-push — zero transcode CPU, and MediaMTX opens/closes the camera
# connection based on reader presence (the idle reaper is not involved).
PULL_MODE = os.environ.get("MEDIAMTX_PULL_MODE", "sub").lower()

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
    _stream_params: dict[str, dict] = {}  # noqa: RUF012  # bitrate, threads, transport per stream
    _locks: dict[str, asyncio.Lock] = {}  # noqa: RUF012  # per-relay-key lifecycle locks
    _pull_paths: set[str] = set()  # noqa: RUF012  # relay keys served via MediaMTX sourceOnDemand

    @classmethod
    def _get_breaker(cls, camera_id: str) -> CircuitBreaker:
        if camera_id not in cls._breakers:
            cls._breakers[camera_id] = CircuitBreaker(
                name=f"stream_{camera_id}", base_cooldown=15, max_cooldown=120
            )
        return cls._breakers[camera_id]

    @classmethod
    def _get_lock(cls, camera_id: str) -> asyncio.Lock:
        """Per-relay-key lock guarding the connect/disconnect check-then-act."""
        lock = cls._locks.get(camera_id)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks[camera_id] = lock
        return lock

    @classmethod
    def _use_pull(cls, cid: str) -> bool:
        """Whether this relay key is served via MediaMTX sourceOnDemand pull."""
        if PULL_MODE == "all":
            return True
        return PULL_MODE == "sub" and cid.endswith("_sub")

    @classmethod
    async def _connect_pull(cls, cid: str, stream_uri: str) -> bool:
        """Create/update a MediaMTX on-demand pull path instead of an FFmpeg relay.

        MediaMTX fetches the camera itself while readers (HLS/WHEP/RTSP) are
        attached and closes the connection sourceOnDemandCloseAfter after the
        last reader leaves — zero transcode CPU and no reaper involvement.
        """
        import httpx

        body = {
            "source": stream_uri,
            "sourceOnDemand": True,
            # Dahua cameras can take >10s for the first handshake+keyframe —
            # give cold starts enough room or every first reader gets a 400.
            "sourceOnDemandStartTimeout": "20s",
            "sourceOnDemandCloseAfter": "10s",
            "rtspTransport": "tcp",
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.patch(f"{MEDIAMTX_API_URL}/v3/config/paths/patch/{cid}", json=body)
                if resp.status_code == 404:
                    resp = await client.post(f"{MEDIAMTX_API_URL}/v3/config/paths/add/{cid}", json=body)
                if resp.status_code >= 400:
                    logger.error(
                        "pull_path_create_failed",
                        camera_id=cid,
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                    return False
        except Exception:
            logger.error("pull_path_create_error", camera_id=cid, exc_info=True)
            return False
        cls._pull_paths.add(cid)
        cls._last_reader_seen[cid] = time.time()
        logger.info("pull_path_created", camera_id=cid)
        return True

    @classmethod
    async def _disconnect_pull(cls, cid: str) -> None:
        """Stop tracking a pull path — but keep it configured in MediaMTX.

        Pull paths cost nothing while unread (sourceOnDemandCloseAfter closes
        the camera connection 10s after the last reader). Deleting the config
        on live/stop would kill the AI sampler's session mid-read and leave it
        dark until its next reconnect+relay-POST cycle. The next connect()
        PATCHes the config anyway, so stale entries self-heal.
        """
        cls._pull_paths.discard(cid)
        logger.info("pull_path_untracked", camera_id=cid)

    @classmethod
    async def connect(cls, camera_id: UUID | str, stream_uri: str, transport: str = "tcp", force: bool = False, bitrate: int | None = None, threads: int | None = None) -> bool:
        """Start FFmpeg process for a camera stream. Returns True if connected/already-running."""
        cid = str(camera_id)
        async with cls._get_lock(cid):
            if cls._use_pull(cid):
                return await cls._connect_pull(cid, stream_uri)
            if cid in cls._processes and cls._processes[cid].returncode is None:
                logger.info("stream_already_active", camera_id=cid)
                return True

            breaker = cls._get_breaker(cid)
            if await breaker.is_open():
                if force:
                    logger.info("circuit_force_reset", camera_id=cid)
                    breaker.reset()
                else:
                    remaining = breaker.cooldown_remaining()
                    logger.warning("circuit_open_skip", camera_id=cid, cooldown_remaining=remaining)
                    return False

            is_sub = cid.endswith("_sub")
            default_bitrate = 500 if is_sub else 2500
            bv = bitrate if bitrate is not None else default_bitrate
            threads_val = threads if threads is not None else 1
            bv_str = f"{bv}k"
            bufsize = f"{bv * 2}k"

            args = [
                FFMPEG_PATH,
                "-hide_banner",
                "-loglevel",
                "error",
                "-threads",
                str(threads_val),
                "-rtsp_transport",
                transport,
                "-timeout",
                "5000000",
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
                bv_str,
                "-maxrate",
                bv_str,
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

            cls._stream_params[cid] = {"bitrate": bv, "threads": threads_val, "transport": transport}

            try:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                cls._processes[cid] = process
                cls._last_reader_seen[cid] = time.time()  # grace period for viewers to attach

                monitor = asyncio.create_task(cls._monitor(cid, process, stream_uri))
                cls._monitors[cid] = monitor

                logger.info("stream_connected", camera_id=cid, pid=process.pid, transport=transport)
                logger.debug("ffmpeg_args", camera_id=cid, args=[*args[:2], "...", *args[-3:]])
                return True
            except Exception:
                logger.error("stream_connect_failed", camera_id=cid, exc_info=True)
                breaker.trip()
                return False

    @classmethod
    async def disconnect(cls, camera_id: UUID | str) -> None:
        """Gracefully stop FFmpeg (or delete the pull path) for a camera."""
        cid = str(camera_id)
        async with cls._get_lock(cid):
            if cid in cls._pull_paths:
                await cls._disconnect_pull(cid)
                return
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
    ) -> bool:
        """Monitor FFmpeg stderr and auto-reconnect on unexpected exit.

        Cancellation (live/stop, idle reaper, shutdown) is an intentional stop:
        the task MUST NOT fall through into the reconnect block — otherwise every
        deliberate disconnect respawns the stream ~1s later.
        """
        breaker = cls._get_breaker(camera_id)
        start_ts = time.time()

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
                    # Do NOT trip the breaker here — give our own reconnect
                    # attempts below a chance first; trip once on exhaustion.
                    logger.warning("stream_error", camera_id=camera_id, line=text.strip())
                    break
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            raise
        except Exception:
            logger.error("monitor_error", camera_id=camera_id, exc_info=True)

        # FFmpeg exited on its own (EOF or fatal stderr error).
        await cls._kill_ffmpeg(process)
        rc = process.returncode
        logger.warning("ffmpeg_exited", camera_id=camera_id, pid=process.pid, returncode=rc)

        # A long stable run proves the camera/URI is healthy — clear trip history.
        if time.time() - start_ts >= STABLE_RUNTIME_S:
            breaker.reset()

        if not cls._running:
            return False

        jitter = asyncio.get_event_loop().time() % 1.0
        await asyncio.sleep(1.0 + jitter)

        max_attempts = 3 if rc == 0 else 2
        params = cls._stream_params.get(camera_id, {})
        last_transport = params.get("transport", "tcp")
        transport_idx = TRANSPORT_ORDER.index(last_transport) if last_transport in TRANSPORT_ORDER else 0
        reconnected = False
        for attempt in range(max_attempts):
            transport = TRANSPORT_ORDER[(transport_idx + attempt) % len(TRANSPORT_ORDER)]
            ok = False
            try:
                ok = await cls.connect(
                    camera_id, stream_uri, transport,
                    bitrate=params.get("bitrate"),
                    threads=params.get("threads"),
                )
            except Exception as exc:
                logger.warning("monitor_reconnect_failed", camera_id=camera_id, attempt=attempt + 1, error=str(exc))
            if ok:
                logger.info("stream_reconnected", camera_id=camera_id, transport=transport)
                reconnected = True
                break
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
        """Stop stream manager, all FFmpeg processes, and all pull paths."""
        cls._running = False
        for cid in list(cls._processes) + list(cls._pull_paths):
            await cls.disconnect(cid)

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
            if cid in cls._pull_paths:
                continue  # MediaMTX sourceOnDemand manages its own lifecycle
            if active_readers.get(cid, 0) > 0:
                cls._last_reader_seen[cid] = now
                continue
            idle_for = now - cls._last_reader_seen.get(cid, now)
            if idle_for > IDLE_TIMEOUT_S:
                logger.info("stream_idle_stop", camera_id=cid, idle_s=int(idle_for))
                await cls.disconnect(cid)
                cls._last_reader_seen.pop(cid, None)
