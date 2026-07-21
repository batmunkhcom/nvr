"""
RTSP Scanner — Port probe and stream capability detection.

Scans IPs for RTSP services and identifies camera capabilities
via OPTIONS/DESCRIBE requests.
"""

from __future__ import annotations

from ipaddress import IPv4Address

from .engine import DiscoveryResult
from .fingerprint import VendorFingerprinter

RTSP_PORTS = [554, 8554, 10554]


class RTSPscanner:
    """Scan IP addresses for RTSP camera services."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.fingerprinter = VendorFingerprinter()

    async def probe(self, ip: IPv4Address, ports: list[int] | None = None) -> DiscoveryResult | None:
        """Probe an IP for RTSP service on common ports.

        Args:
            ip: Target IP address.
            ports: List of ports to scan. Defaults to [554, 8554, 10554].

        Returns:
            DiscoveryResult on success, None if no RTSP service found.
        """
        ports = ports or RTSP_PORTS
        # TODO: Implement RTSP port scanning + OPTIONS/DESCRIBE
        # 1. TCP connect to each port
        # 2. Send RTSP OPTIONS request
        # 3. Parse Server header for vendor identification
        # 4. Send RTSP DESCRIBE to get media profiles
        # 5. Extract stream URIs from SDP
        # 6. Return DiscoveryResult
        return None

    async def scan_subnet(
        self, subnet_cidr: str, ports: list[int] | None = None
    ) -> list[DiscoveryResult]:
        """Scan an entire subnet for RTSP cameras."""
        results: list[DiscoveryResult] = []
        # TODO: Concurrent scan of all IPs in subnet
        return results
