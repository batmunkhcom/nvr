"""
ONVIF WS-Discovery Scanner.

Uses WS-Discovery multicast protocol to find ONVIF-compliant cameras on the network.
"""

from __future__ import annotations

from ipaddress import IPv4Address

from .engine import DiscoveryResult

ONVIF_MULTICAST = "239.255.255.250"
ONVIF_PORT = 3702


class ONVIFScanner:
    """Discover cameras using ONVIF WS-Discovery (multicast)."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def discover(self) -> list[DiscoveryResult]:
        """Run ONVIF WS-Discovery and return found devices.

        Sends WS-Discovery Probe message on multicast address
        and parses ProbeMatch responses.
        """
        results: list[DiscoveryResult] = []

        # TODO: Implement WS-Discovery using asyncio sockets
        # 1. Create UDP socket, join multicast group
        # 2. Send WS-Discovery Probe SOAP message
        # 3. Listen for ProbeMatch responses
        # 4. For each response, call GetDeviceInformation
        # 5. Call GetCapabilities, GetProfiles for stream URIs
        # 6. Return DiscoveryResult list

        return results

    async def probe_single(self, ip: IPv4Address) -> DiscoveryResult | None:
        """Probe a single IP for ONVIF service."""
        # TODO: Send WS-Discovery unicast Probe to specific IP
        return None
