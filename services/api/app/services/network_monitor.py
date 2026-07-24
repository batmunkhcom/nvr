"""Network metrics collector - background task that polls cameras for bandwidth, latency, packet loss."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = structlog.get_logger()


class NetworkMonitor:
    def __init__(self):
        self.running = False
        self._task: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(5)
        self._camera_offsets: dict[UUID, float] = {}
        self._engine = None

    def init(self, db_url: str):
        """Initialize with database URL. Called from app lifespan."""
        self._engine = create_async_engine(db_url)

    async def start(self):
        """Start background collection loop. Called from app lifespan."""
        if self.running or not self._engine:
            return
        self.running = True
        logger.info("network_monitor_starting")
        self._task = asyncio.create_task(self._collect_loop())

    async def stop(self):
        """Stop background collection. Called on app shutdown."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("network_monitor_stopped")

    async def _collect_loop(self):
        """Main polling loop with staggered offsets."""
        while self.running:
            start_time = asyncio.get_event_loop().time()

            try:
                cameras = await self._get_monitored_cameras()

                if not cameras:
                    await asyncio.sleep(30)
                    continue

                poll_interval = 30
                total = len(cameras)
                for i, cam in enumerate(cameras):
                    self._camera_offsets[cam['id']] = (i * poll_interval / total) if total > 1 else 0

                tasks = [self._collect_single_camera(cam, offset) for cam, offset in self._camera_offsets.items()]
                await asyncio.gather(*tasks, return_exceptions=True)

            except Exception:
                logger.error("network_monitor_loop_error", exc_info=True)

            elapsed = asyncio.get_event_loop().time() - start_time
            sleep_time = max(0, 30 - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _get_monitored_cameras(self) -> list[dict[str, Any]]:
        """Get all active cameras with monitoring enabled + their configs."""
        async with AsyncSession(self._engine) as db:
            result = await db.execute(text("""
                SELECT c.id, c.name, c.ip_address, c.location, c.stream_main_uri, c.stream_sub_uri,
                       cnc.poll_interval, cnc.ping_enabled, cnc.rtsp_check_enabled
                FROM cameras c
                JOIN camera_network_config cnc ON c.id = cnc.camera_id
                WHERE c.is_active = true
                ORDER BY c.display_order ASC
            """))
            rows = result.fetchall()

            return [
                {
                    'id': row[0],
                    'name': row[1],
                    'ip_address': row[2],
                    'location': row[3],
                    'stream_main_uri': row[4],
                    'stream_sub_uri': row[5],
                    'poll_interval': row[6],
                    'ping_enabled': row[7],
                    'rtsp_check_enabled': row[8],
                }
                for row in rows
            ]

    async def _collect_single_camera(self, camera: dict[str, Any], offset_seconds: float):
        """Collect metrics for one camera. Independent error handling."""
        if offset_seconds > 0:
            await asyncio.sleep(offset_seconds)

        async with self._semaphore:
            try:
                metrics = await self.collect_metrics(camera)
                if metrics:
                    await self.store_metrics(metrics)

                    try:
                        from .ws_manager import ws_manager
                        await ws_manager.broadcast({
                            "type": "network_metric",
                            "camera_id": str(camera['id']),
                            "metrics": metrics,
                        })
                    except Exception as ws_err:
                        logger.warning("network_ws_broadcast_failed", error=str(ws_err))

                    try:
                        from .network_alerts import network_alert_service
                        if network_alert_service:
                            await network_alert_service.evaluate(
                                camera['id'], metrics, self._engine
                            )
                    except Exception as alert_err:
                        logger.warning("network_alert_eval_failed", error=str(alert_err))

            except Exception as e:
                logger.error(
                    "network_collect_error",
                    camera_id=str(camera.get('id', 'unknown')),
                    camera_name=camera.get('name', 'unknown'),
                    error=str(e),
                )

    async def collect_metrics(self, camera: dict[str, Any]) -> dict[str, Any] | None:
        """Collect all metrics for one camera. Returns None if collection failed."""
        results: dict[str, Any] = {
            'camera_id': str(camera['id']),
        }

        if camera.get('ping_enabled', True):
            try:
                ping_result = await self.ping_camera(camera['ip_address'])
                results.update(ping_result)
            except Exception as e:
                logger.debug("ping_failed", camera_id=str(camera['id']), error=str(e))
                results['rtt_ms'] = None
                results['jitter_ms'] = None
                results['packet_loss_pct'] = 100.0
        else:
            results['rtt_ms'] = None
            results['jitter_ms'] = None
            results['packet_loss_pct'] = None

        if camera.get('rtsp_check_enabled', True):
            try:
                mtmx_stats = await self.get_mediamtx_stats(camera['id'])
                if mtmx_stats:
                    results.update(mtmx_stats)
                else:
                    proc_stats = await self.parse_proc_stats(camera['id'])
                    if proc_stats:
                        results.update(proc_stats)
            except Exception as e:
                logger.debug("stats_fetch_failed", camera_id=str(camera['id']), error=str(e))

        results['status'] = self._determine_status(results)

        return results if results else None

    async def ping_camera(self, ip_address: str) -> dict[str, Any]:
        """ICMP ping via subprocess. Returns rtt_ms, jitter_ms, packet_loss_pct."""
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "3", "-W", "5", ip_address,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")

        rtt_match = re.search(r"rtt\s+min/avg/max/mdev\s+=\s+([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", output)

        if rtt_match:
            avg_rtt = float(rtt_match.group(2))
            mdev = float(rtt_match.group(4))

            return {
                "rtt_ms": round(avg_rtt, 2),
                "jitter_ms": round(mdev, 2),
                "packet_loss_pct": 0.0,
            }

        loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet\s+loss", output)
        if loss_match:
            loss_pct = float(loss_match.group(1))
            return {
                "rtt_ms": None,
                "jitter_ms": None,
                "packet_loss_pct": loss_pct,
            }

        return {
            "rtt_ms": None,
            "jitter_ms": None,
            "packet_loss_pct": 100.0,
        }

    async def get_mediamtx_stats(self, camera_id: UUID) -> dict[str, Any] | None:
        """Get bitrate/fps from MediaMTX REST API."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"http://127.0.0.1:9997/v3/paths/{camera_id}")
                if resp.status_code != 200:
                    return None

                data = resp.json()
                stats: dict[str, Any] = {}

                runners = data.get("runners", [])
                total_bitrate_mbps = 0.0
                fps_values = []
                pids = []

                for runner in runners:
                    for reader in runner.get("readers", []):
                        stats_info = reader.get("stats", {})
                        bitrate_bps = stats_info.get("averageBitrateBps", 0)
                        total_bitrate_mbps += bitrate_bps / 1_000_000
                        fps = stats_info.get("currentFps", 0)
                        if fps > 0:
                            fps_values.append(fps)

                    for writer in runner.get("writers", []):
                        stats_info = writer.get("stats", {})
                        bitrate_bps = stats_info.get("currentBitrateBps", 0)
                        total_bitrate_mbps += bitrate_bps / 1_000_000
                        fps = stats_info.get("currentFps", 0)
                        if fps > 0:
                            fps_values.append(fps)

                    pid = runner.get("pid")
                    if pid:
                        pids.append(pid)

                if total_bitrate_mbps > 0:
                    stats["outbound_mbps"] = round(total_bitrate_mbps, 2)
                    stats["fps_current"] = round(sum(fps_values) / len(fps_values), 1) if fps_values else None

                    for pid in pids:
                        proc_stats = await self._read_proc_stats(pid)
                        if proc_stats:
                            stats["ffmpeg_pid"] = pid
                            stats["ffmpeg_cpu"] = proc_stats.get("cpu_percent")
                            stats["ffmpeg_memory_mb"] = proc_stats.get("memory_mb")

                return stats if stats else None

        except Exception as e:
            logger.debug("mediamtx_api_failed", camera_id=str(camera_id), error=str(e))
            return None

    async def parse_proc_stats(self, camera_id: UUID) -> dict[str, Any] | None:
        """Fallback: find FFmpeg PID from running processes, then read /proc/[pid]/stat."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pgrep", "-f", f"ffmpeg.*{camera_id}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            pids = stdout.decode("utf-8", errors="replace").strip().split("\n")

            if not pids or pids == [""]:
                return None

            pid = int(pids[0])
            stats = await self._read_proc_stats(pid)
            if stats:
                stats["ffmpeg_pid"] = pid
            return stats

        except Exception as e:
            logger.debug("proc_stats_failed", camera_id=str(camera_id), error=str(e))
            return None

    async def _read_proc_stats(self, pid: int) -> dict[str, Any] | None:
        """Read /proc/{pid}/stat and /proc/{pid}/status for CPU + memory."""
        try:
            with open(f"/proc/{pid}/stat", "r") as f:
                stat_fields = f.read().split()

            utime = int(stat_fields[13])
            stime = int(stat_fields[14])
            total_ticks = utime + stime

            with open(f"/proc/{pid}/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        memory_kb = int(line.split()[1])
                        return {
                            "ffmpeg_cpu": round(total_ticks / 10.0, 2),
                            "ffmpeg_memory_mb": round(memory_kb / 1024, 2),
                        }

            return {"ffmpeg_cpu": 0.0, "ffmpeg_memory_mb": 0.0}

        except (FileNotFoundError, IndexError, ValueError):
            return None

    def _determine_status(self, metrics: dict[str, Any]) -> str:
        """Determine camera status from collected metrics."""
        if not metrics.get('rtt_ms') and metrics.get('packet_loss_pct', 0) >= 100:
            return 'offline'
        if metrics.get('packet_loss_pct', 0) > 5.0:
            return 'degraded'
        return 'online'

    async def store_metrics(self, metrics: dict[str, Any]) -> None:
        """Insert metrics into database."""
        camera_id = metrics.pop('camera_id', None)
        if not camera_id:
            return

        async with AsyncSession(self._engine) as db:
            try:
                await db.execute(text("""
                    INSERT INTO network_metrics
                       (camera_id, recorded_at, inbound_mbps, outbound_mbps, rtt_ms, jitter_ms,
                        rtsp_latency, packets_sent, packets_recv, packet_loss_pct,
                        fps_current, bitrate_current, rtsp_reconnect_cnt,
                        ffmpeg_pid, ffmpeg_cpu, ffmpeg_memory_mb, status, error_message)
                    VALUES (:camera_id, NOW(), :inbound_mbps, :outbound_mbps, :rtt_ms, :jitter_ms,
                              :rtsp_latency, :packets_sent, :packets_recv, :packet_loss_pct,
                              :fps_current, :bitrate_current, :rtsp_reconnect_cnt,
                              :ffmpeg_pid, :ffmpeg_cpu, :ffmpeg_memory_mb, :status, :error_message)
                """), {
                    "camera_id": camera_id,
                    "inbound_mbps": metrics.get("inbound_mbps"),
                    "outbound_mbps": metrics.get("outbound_mbps"),
                    "rtt_ms": metrics.get("rtt_ms"),
                    "jitter_ms": metrics.get("jitter_ms"),
                    "rtsp_latency": metrics.get("rtsp_latency"),
                    "packets_sent": metrics.get("packets_sent"),
                    "packets_recv": metrics.get("packets_recv"),
                    "packet_loss_pct": metrics.get("packet_loss_pct"),
                    "fps_current": metrics.get("fps_current"),
                    "bitrate_current": metrics.get("bitrate_current"),
                    "rtsp_reconnect_cnt": metrics.get("rtsp_reconnect_cnt"),
                    "ffmpeg_pid": metrics.get("ffmpeg_pid"),
                    "ffmpeg_cpu": metrics.get("ffmpeg_cpu"),
                    "ffmpeg_memory_mb": metrics.get("ffmpeg_memory_mb"),
                    "status": metrics.get("status", "unknown"),
                    "error_message": metrics.get("error_message"),
                })
                await db.commit()
            except Exception:
                await db.rollback()
                raise


network_monitor = NetworkMonitor()
