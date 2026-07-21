"""
Vendor-Specific Broadcast Scanner.

Sends vendor-specific UDP broadcast/multicast packets to discover
cameras that support proprietary discovery protocols:
- Hikvision: UDP port 37020 (SADP protocol)
- Dahua: UDP port 37810 (config tool discovery)
"""

from __future__ import annotations

import asyncio
import socket as socket_mod
from ipaddress import IPv4Address

import structlog

from .engine_data import DeviceVendor, DiscoveryMethod, DiscoveryResult
from .fingerprint import VendorFingerprinter

logger = structlog.get_logger()

HIKVISION_PORT = 37020
DAHUA_PORT = 37810
BROADCAST_TIMEOUT = 5

HIKVISION_PROBE = (
    b"\x00\x01\x00\x00"  # message type
    b"\x00\x00\x00\x30"  # total length
    b"\x00\x00\x00\x01"  # session
    b"\x00\x00\x00\x00\x00\x00\x00\x00"  # reserved
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00"
)

DAHUA_PROBE = bytes.fromhex(
    "20000000"  # start code
    "00000000"  # session
    "00000000"  # sequence
    "9c00"  # msg type (query)
    "00000000"  # data size
    "00000000"  # reserved
    "fc000000"  # end
)


class VendorBroadcastScanner:
    """Discover cameras via vendor-specific UDP broadcast protocols."""

    def __init__(self, timeout: int = BROADCAST_TIMEOUT):
        self.timeout = timeout
        self.fingerprinter = VendorFingerprinter()

    async def scan(self) -> list[DiscoveryResult]:
        """Run vendor-specific broadcasts and return discovered devices."""
        discovered: dict[str, DiscoveryResult] = {}

        hikvision = await self._broadcast_hikvision()
        for ip, _data in hikvision.items():
            discovered[ip] = DiscoveryResult(
                ip_address=IPv4Address(ip),
                method=DiscoveryMethod.VENDOR_BROADCAST,
                vendor=DeviceVendor.HIKVISION,
                confidence=70,
            )

        dahua = await self._broadcast_dahua()
        for ip, _data in dahua.items():
            if ip not in discovered:
                discovered[ip] = DiscoveryResult(
                    ip_address=IPv4Address(ip),
                    method=DiscoveryMethod.VENDOR_BROADCAST,
                    vendor=DeviceVendor.DAHUA,
                    confidence=70,
                )

        return list(discovered.values())

    async def _broadcast_hikvision(self) -> dict[str, bytes]:
        """Send Hikvision SADP broadcast and parse responses."""
        results: dict[str, bytes] = {}

        sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_DGRAM)
        sock.setsockopt(socket_mod.SOL_SOCKET, socket_mod.SO_REUSEADDR, 1)
        sock.setsockopt(socket_mod.SOL_SOCKET, socket_mod.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", HIKVISION_PORT))
        sock.setblocking(False)

        try:
            sock.sendto(HIKVISION_PROBE, ("255.255.255.255", HIKVISION_PORT))

            loop = asyncio.get_event_loop()
            deadline = loop.time() + self.timeout

            while loop.time() < deadline:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 4096), timeout=remaining
                    )
                    ip = addr[0]
                    if ip not in results:
                        results[ip] = data
                except TimeoutError:
                    break
        except OSError:
            pass
        finally:
            sock.close()

        return results

    async def _broadcast_dahua(self) -> dict[str, bytes]:
        """Send Dahua config tool broadcast and parse responses."""
        results: dict[str, bytes] = {}

        sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_DGRAM)
        sock.setsockopt(socket_mod.SOL_SOCKET, socket_mod.SO_REUSEADDR, 1)
        sock.setsockopt(socket_mod.SOL_SOCKET, socket_mod.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", DAHUA_PORT))
        sock.setblocking(False)

        try:
            sock.sendto(DAHUA_PROBE, ("255.255.255.255", DAHUA_PORT))

            loop = asyncio.get_event_loop()
            deadline = loop.time() + self.timeout

            while loop.time() < deadline:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 4096), timeout=remaining
                    )
                    ip = addr[0]
                    if ip not in results:
                        results[ip] = data
                except TimeoutError:
                    break
        except OSError:
            logger.warning("dahua_broadcast_error", exc_info=True)
        finally:
            sock.close()

        return results
