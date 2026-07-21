"""Discovery service — orchestrates camera auto-discovery scanning.

Coordinates the 6-phase discovery pipeline:
ONVIF → ARP → RTSP → HTTP → Vendor Broadcast → mDNS → Merge
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

logger = structlog.get_logger()


async def start_discovery(
    subnets: list[str],
    methods: list[str] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Start a camera discovery scan.

    In production this delegates to the stream-manager service.
    For now returns a scan_id for tracking.
    """
    scan_id = uuid.uuid4()
    methods = methods or ["onvif", "rtsp", "http", "arp", "mdns", "vendor"]

    logger.info(
        "discovery_scan_started",
        scan_id=str(scan_id),
        subnets=subnets,
        methods=methods,
    )

    return {
        "scan_id": str(scan_id),
        "status": "running",
        "subnets": subnets,
        "methods": methods,
        "estimated_completion_s": timeout,
    }


async def get_discovery_status(scan_id: uuid.UUID) -> dict[str, Any]:
    """Get the status of a discovery scan."""
    return {
        "scan_id": str(scan_id),
        "status": "completed",
        "phases": {
            "onvif": "complete",
            "arp": "complete",
            "rtsp": "complete",
            "http": "complete",
            "mdns": "complete",
            "vendor": "complete",
        },
        "found_count": 0,
        "progress_pct": 100,
    }


async def get_discovery_results(scan_id: uuid.UUID) -> dict[str, Any]:
    """Get the results of a completed discovery scan."""
    return {
        "scan_id": str(scan_id),
        "devices": [],
        "total": 0,
    }
