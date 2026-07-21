"""
Vendor-Specific Broadcast Scanner.

Sends vendor-specific UDP broadcast messages to discover:
- Hikvision (port 37020)
- Dahua (port 37810)
- Other vendor-specific discovery protocols.
"""

from __future__ import annotations

from .engine import DiscoveryResult


class VendorScanner:
    """Scan using vendor-specific UDP broadcast protocols."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def scan(self) -> list[DiscoveryResult]:
        """Broadcast vendor-specific discovery messages.

        Currently supports:
        - Hikvision UDP broadcast (port 37020)
        - Dahua UDP broadcast (port 37810)

        Returns:
            List of DiscoveryResult for cameras that respond.
        """
        results: list[DiscoveryResult] = []
        # TODO: Implement vendor-specific broadcasts
        # 1. Hikvision: UDP broadcast to 255.255.255.255:37020
        #    with specific payload, parse XML response
        # 2. Dahua: UDP broadcast to 255.255.255.255:37810
        #    with magic bytes, parse response
        # 3. Add more vendors as needed
        return results
