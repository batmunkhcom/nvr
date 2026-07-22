"""Discovery service — orchestrates camera auto-discovery scanning.

Runs real subnet scans using TCP port probes + RTSP/HTTP identification.
Stores scan state in-memory (keyed by scan_id), with background asyncio tasks.
"""

from __future__ import annotations

import asyncio
import ipaddress
import time
import uuid
from typing import Any

import structlog

from .camera_probe import probe_ip

logger = structlog.get_logger()

# In-memory scan storage: {scan_id: {status, phases, devices, start_time, ...}}
_scans: dict[str, dict[str, Any]] = {}
_SCAN_TTL = 600  # auto-clean scans older than 10 min
_tasks: set[asyncio.Task[Any]] = set()


async def start_discovery(
    subnets: list[str],
    methods: list[str] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    methods = methods or ["rtsp", "http"]
    scan_id = uuid.uuid4()

    total_ips = _count_ips(subnets)
    _scans[str(scan_id)] = {
        "scan_id": str(scan_id),
        "status": "running",
        "subnets": subnets,
        "methods": methods,
        "timeout": min(timeout, 120),
        "total_ips": total_ips,
        "scanned_ips": 0,
        "found_count": 0,
        "phases": dict.fromkeys(methods, "pending"),
        "devices": [],
        "started_at": time.time(),
        "errors": [],
    }
    logger.info("discovery_started", scan_id=str(scan_id), subnets=subnets,
                methods=methods, total_ips=total_ips)

    t = asyncio.create_task(_run_scan(scan_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)

    return {
        "scan_id": str(scan_id),
        "status": "running",
        "subnets": subnets,
        "methods": methods,
        "estimated_completion_s": min(timeout, 120),
        "total_ips": total_ips,
    }


async def get_discovery_status(scan_id: uuid.UUID) -> dict[str, Any]:
    sid = str(scan_id)
    if sid not in _scans:
        return {"scan_id": sid, "status": "not_found", "phases": {},
                "found_count": 0, "progress_pct": 0}
    scan = _scans[sid]
    total = max(scan.get("total_ips", 0), 1)
    pct = min(100, int(scan["scanned_ips"] / total * 100)) if total > 0 else 0
    return {
        "scan_id": sid,
        "status": scan["status"],
        "phases": scan["phases"],
        "found_count": scan["found_count"],
        "progress_pct": pct,
        "scanned_ips": scan["scanned_ips"],
        "total_ips": total,
    }


async def get_discovery_results(scan_id: uuid.UUID) -> dict[str, Any]:
    sid = str(scan_id)
    if sid not in _scans:
        return {"scan_id": sid, "devices": [], "total": 0}
    scan = _scans[sid]
    return {
        "scan_id": sid,
        "devices": scan.get("devices", []),
        "total": scan.get("found_count", 0),
    }


# ── background scan ────────────────────────────────────────────────────────

async def _run_scan(scan_id: uuid.UUID):
    sid = str(scan_id)
    scan = _scans.get(sid)
    if not scan:
        return

    try:
        subnets = scan["subnets"]
        ips = _expand_subnets(subnets)
        scan["total_ips"] = len(ips)
        methods = scan["methods"]

        semaphore = asyncio.Semaphore(30)

        async def _probe_and_record(ip: str):
            try:
                async with semaphore:
                    info = await probe_ip(ip, timeout=3.0)
            except Exception:
                return
            scan["scanned_ips"] += 1
            if info.get("reachable"):
                if any(d["ip_address"] == ip for d in scan["devices"]):
                    return
                scan["found_count"] += 1
                scan["devices"].append({
                    "ip_address": ip,
                    "manufacturer": info.get("manufacturer"),
                    "model": info.get("model"),
                    "http_title": info.get("http_title"),
                    "stream_main_uri": info.get("stream_main_uri"),
                    "stream_sub_uri": info.get("stream_sub_uri"),
                    "open_ports": info.get("open_ports"),
                    "has_rtsp": info.get("has_rtsp"),
                    "has_http": info.get("has_http"),
                    "has_audio": info.get("has_audio"),
                    "has_ptz": info.get("has_ptz"),
                    "has_onvif": info.get("has_onvif"),
                    "has_motion_detection": info.get("has_motion_detection"),
                    "confidence": _calc_confidence(info),
                })

        for method in methods:
            scan["phases"][method] = "running"
            await asyncio.gather(*[_probe_and_record(ip) for ip in ips])
            scan["phases"][method] = "complete"

        scan["status"] = "completed"
        logger.info("discovery_completed", scan_id=sid, found=scan["found_count"],
                    scanned=scan["total_ips"])

    except Exception as e:
        logger.error("discovery_scan_failed", scan_id=sid, error=str(e),
                     exc_info=True)
        scan["status"] = "failed"
        scan["errors"].append(str(e))
    finally:
        _schedule_cleanup(sid)


# ── helpers ────────────────────────────────────────────────────────────────

def _expand_range(spec: str) -> list[str]:
    """Expand '192.168.1.100-192.168.1.150' or '192.168.1.100-150' into IPs."""
    spec = spec.strip()
    if "-" not in spec:
        return []
    start_s, end_s = spec.split("-", 1)
    try:
        start = ipaddress.ip_address(start_s.strip())
    except ValueError:
        return []
    end_s = end_s.strip()
    if "." not in end_s:
        # short form: '192.168.1.100-150' — last octet only
        parts = start_s.strip().split(".")
        if len(parts) != 4 or not end_s.isdigit():
            return []
        end_s = ".".join(parts[:3] + [end_s])
    try:
        end = ipaddress.ip_address(end_s)
    except ValueError:
        return []
    if end < start:
        start, end = end, start
    ips: list[str] = []
    cur = int(start)
    while cur <= int(end) and len(ips) < 1024:
        ips.append(str(ipaddress.ip_address(cur)))
        cur += 1
    return ips


def _count_ips(subnets: list[str]) -> int:
    total = 0
    for s in subnets:
        if "-" in s:
            total += len(_expand_range(s))
            continue
        try:
            net = ipaddress.ip_network(s, strict=False)
            total += min(net.num_addresses, 256)
        except ValueError:
            logger.warning("invalid_subnet", subnet=s)
    return total


def _expand_subnets(subnets: list[str]) -> list[str]:
    ips: list[str] = []
    for s in subnets:
        if "-" in s:
            ips.extend(_expand_range(s))
            if len(ips) >= 1024:
                break
            continue
        try:
            net = ipaddress.ip_network(s, strict=False)
            for addr in net.hosts():
                ips.append(str(addr))
                if len(ips) >= 1024:
                    break
        except ValueError:
            continue
    return ips


def _calc_confidence(info: dict[str, Any]) -> int:
    """Calculate a confidence score (0-100) for a discovered device."""
    score = 20  # base for being reachable
    if info.get("manufacturer"):
        score += 30
    if info.get("model"):
        score += 15
    if info.get("has_rtsp"):
        score += 15
    if info.get("has_http"):
        score += 10
    if info.get("has_onvif"):
        score += 10
    return min(score, 100)


def _schedule_cleanup(scan_id: str):
    async def _cleanup():
        await asyncio.sleep(_SCAN_TTL)
        _scans.pop(scan_id, None)

    t = asyncio.create_task(_cleanup())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
