"""Network metrics collector — polls cameras for bandwidth, latency, packet loss.

Runs as a background asyncio loop (started from app lifespan). Collects:
  - ping (RTT / jitter / packet loss) — requires NET_RAW cap
  - MediaMTX path stats (inbound/outbound bytes → Mbps delta)
  - Status determination (online / degraded / offline)

Auto-start on app boot; play/pause via API.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = structlog.get_logger()

MEDIAMTX_HOST = "http://nvr-mediamtx:9997"
DEFAULT_RETENTION_DAYS = 30
POLL_INTERVAL_S = 30


class NetworkMonitor:
    def __init__(self):
        self.running = False
        self._task: asyncio.Task | None = None
        self._engine = None
        self._byte_tracker: dict[
            str, tuple[float, int, int]
        ] = {}  # cam_id -> (ts, bytes_rcv, bytes_sent)

    def init(self, db_url: str):
        self._engine = create_async_engine(db_url)

    async def start(self):
        if self.running or not self._engine:
            return
        self.running = True
        logger.info("network_monitor_starting")
        self._task = asyncio.create_task(self._collect_loop())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("network_monitor_stopped")

    async def _collect_loop(self):
        while self.running:
            t_start = time.monotonic()

            try:
                cameras = await self._get_monitored_cameras()
                if not cameras:
                    await asyncio.sleep(POLL_INTERVAL_S)
                    continue

                mediamtx_data = await self._fetch_mediamtx_paths()

                tasks = [self._collect_single_camera(c, mediamtx_data) for c in cameras]
                await asyncio.gather(*tasks, return_exceptions=True)

                await self._cleanup_old_metrics()

            except Exception:
                logger.error("network_monitor_loop_error", exc_info=True)

            elapsed = time.monotonic() - t_start
            if (sleep_sec := POLL_INTERVAL_S - elapsed) > 0:
                await asyncio.sleep(sleep_sec)

    async def _get_monitored_cameras(self) -> list[dict[str, Any]]:
        async with AsyncSession(self._engine) as db:
            result = await db.execute(
                text("""
                SELECT c.id, c.name, c.ip_address, c.location,
                       cnc.poll_interval, cnc.ping_enabled, cnc.retention_days
                FROM cameras c
                JOIN camera_network_config cnc ON c.id = cnc.camera_id
                WHERE c.is_active = true
                ORDER BY c.display_order ASC
            """)
            )
            rows = result.fetchall()
            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "ip_address": row[2],
                    "location": row[3],
                    "poll_interval": row[4] or POLL_INTERVAL_S,
                    "ping_enabled": row[5] if row[5] is not None else True,
                    "retention_days": row[6] or DEFAULT_RETENTION_DAYS,
                }
                for row in rows
            ]

    async def _fetch_mediamtx_paths(self) -> dict[str, dict[str, int]]:
        """Fetch path-level byte counters from MediaMTX.

        Returns: {camera_id: {"bytesReceived": N, "bytesSent": N}, ...}
        The _sub suffix is stripped from path names.
        """
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{MEDIAMTX_HOST}/v3/paths/list")
                if resp.status_code != 200:
                    return {}
                page = resp.json()
        except Exception:
            logger.debug("mediamtx_api_failed")
            return {}

        result: dict[str, dict[str, int]] = {}
        for p in page.get("items", []):
            name = p.get("name", "")
            if name.endswith("_sub"):
                cid = name[:-4]
                result[cid] = {
                    "bytes_received": p.get("bytesReceived", 0),
                    "bytes_sent": p.get("bytesSent", 0),
                }
        return result

    def _compute_mbps(
        self, cam_id: str, bytes_rcv: int, bytes_sent: int
    ) -> tuple[float | None, float | None]:
        """Compute inbound/outbound Mbps from byte deltas since last sample."""
        now = time.monotonic()
        inbound_mbps = outbound_mbps = None

        if prev := self._byte_tracker.get(cam_id):
            prev_ts, prev_rcv, prev_sent = prev
            elapsed = now - prev_ts
            if elapsed >= 1.0:
                d_rcv = bytes_rcv - prev_rcv
                d_sent = bytes_sent - prev_sent
                if d_rcv >= 0:
                    inbound_mbps = round(d_rcv / elapsed * 8 / 1_000_000, 2)
                if d_sent >= 0:
                    outbound_mbps = round(d_sent / elapsed * 8 / 1_000_000, 2)

        self._byte_tracker[cam_id] = (now, bytes_rcv, bytes_sent)
        return inbound_mbps, outbound_mbps

    async def _collect_single_camera(self, camera: dict[str, Any], mmtx: dict[str, dict[str, int]]):
        try:
            metrics = await self.collect_metrics(camera, mmtx)
            if metrics:
                await self.store_metrics(metrics)

                from .ws_manager import ws_manager

                await ws_manager.broadcast(
                    {"type": "network_metric", "camera_id": str(camera["id"]), "metrics": metrics}
                )

                from .network_alerts import network_alert_service

                await network_alert_service.evaluate(camera["id"], metrics, self._engine)

        except Exception as e:
            logger.error(
                "network_collect_error",
                camera_id=str(camera.get("id", "unknown")),
                error=str(e),
            )

    async def collect_metrics(
        self, camera: dict[str, Any], mmtx: dict[str, dict[str, int]]
    ) -> dict[str, Any] | None:
        cid = str(camera["id"])
        results: dict[str, Any] = {"camera_id": cid}

        # --- ping ---
        if camera.get("ping_enabled", True) and camera.get("ip_address"):
            try:
                ping = await self._ping(camera["ip_address"])
                results.update(ping)
            except Exception:
                # ping failure is non-fatal — leave metrics unset
                pass
        results.setdefault("rtt_ms", None)
        results.setdefault("jitter_ms", None)
        results.setdefault("packet_loss_pct", None)

        # --- MediaMTX bytes → bandwidth ---
        path = mmtx.get(cid, {})
        bytes_rcv = path.get("bytes_received", 0)
        bytes_sent = path.get("bytes_sent", 0)
        inbound, outbound = self._compute_mbps(cid, bytes_rcv, bytes_sent)
        results["inbound_mbps"] = inbound
        results["outbound_mbps"] = outbound

        results["status"] = self._determine_status(results)
        return results

    async def _ping(self, ip_address: str) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            "3",
            "-W",
            "5",
            ip_address,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        output = stdout.decode(errors="replace")

        m = re.search(r"rtt\s+min/avg/max/mdev\s+=\s+([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", output)
        if m:
            return {
                "rtt_ms": round(float(m.group(2)), 2),
                "jitter_ms": round(float(m.group(4)), 2),
                "packet_loss_pct": 0.0,
            }

        m = re.search(r"(\d+(?:\.\d+)?)%\s+packet\s+loss", output)
        if m:
            return {
                "rtt_ms": None,
                "jitter_ms": None,
                "packet_loss_pct": float(m.group(1)),
            }

        return {"rtt_ms": None, "jitter_ms": None, "packet_loss_pct": None}

    def _determine_status(self, metrics: dict[str, Any]) -> str:
        loss = metrics.get("packet_loss_pct")
        rtt = metrics.get("rtt_ms")
        inbound = metrics.get("inbound_mbps")
        outbound = metrics.get("outbound_mbps")

        has_bandwidth = (inbound is not None and inbound > 0) or (
            outbound is not None and outbound > 0
        )

        if loss is not None and loss >= 100 and not has_bandwidth:
            return "offline"
        if loss is not None and loss > 5.0:
            return "degraded"
        if rtt is None and loss is None and not has_bandwidth:
            return "unknown"
        return "online"

    async def _cleanup_old_metrics(self):
        """Delete metrics rows older than the configured retention (default 30 days)."""
        try:
            async with AsyncSession(self._engine) as db:
                await db.execute(
                    text(
                        "DELETE FROM network_metrics WHERE recorded_at < NOW() - INTERVAL '30 days'"
                    )
                )
                await db.commit()
        except Exception:
            await db.rollback()

    async def store_metrics(self, metrics: dict[str, Any]) -> None:
        camera_id = metrics.pop("camera_id", None)
        if not camera_id:
            return

        async with AsyncSession(self._engine) as db:
            try:
                await db.execute(
                    text(
                        """
                        INSERT INTO network_metrics
                           (camera_id, recorded_at,
                            inbound_mbps, outbound_mbps,
                            rtt_ms, jitter_ms, packet_loss_pct,
                            status)
                        VALUES (:camera_id, NOW(),
                                :inbound_mbps, :outbound_mbps,
                                :rtt_ms, :jitter_ms, :packet_loss_pct,
                                :status)
                        """
                    ),
                    {
                        "camera_id": camera_id,
                        "inbound_mbps": metrics.get("inbound_mbps"),
                        "outbound_mbps": metrics.get("outbound_mbps"),
                        "rtt_ms": metrics.get("rtt_ms"),
                        "jitter_ms": metrics.get("jitter_ms"),
                        "packet_loss_pct": metrics.get("packet_loss_pct"),
                        "status": metrics.get("status", "unknown"),
                    },
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise


network_monitor = NetworkMonitor()
