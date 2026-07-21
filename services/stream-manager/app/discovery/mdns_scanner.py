"""
mDNS / Avahi Scanner — Zero-configuration service discovery for cameras.

Queries mDNS for camera-related services:
_onvif._tcp, _axis-video._tcp, _rtsp._tcp, _http._tcp
"""

from __future__ import annotations

import asyncio
import re
from ipaddress import IPv4Address

import structlog

from .engine_data import DeviceVendor, DiscoveryMethod, DiscoveryResult

logger = structlog.get_logger()

SERVICE_TYPES = [
    ("_onvif._tcp.local.", DeviceVendor.GENERIC_ONVIF),
    ("_axis-video._tcp.local.", DeviceVendor.AXIS),
    ("_rtsp._tcp.local.", DeviceVendor.UNKNOWN),
    ("_http._tcp.local.", DeviceVendor.UNKNOWN),
]

MDNS_MULTICAST = "224.0.0.251"
MDNS_PORT = 5353
SCAN_TIMEOUT = 8

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
NAME_RE = re.compile(r"NAME=([^\s]+)")


class MDNSScanner:
    """Discover cameras using mDNS/Bonjour/Avahi service queries."""

    def __init__(self, timeout: int = SCAN_TIMEOUT):
        self.timeout = timeout

    async def scan(self) -> list[DiscoveryResult]:
        """Browse mDNS for camera services."""
        discovered: dict[str, DiscoveryResult] = {}

        for service_type, vendor in SERVICE_TYPES:
            try:
                results = await self._query_mdns(service_type)
                for ip_str, _hostname in results.items():
                    if ip_str not in discovered:
                        discovered[ip_str] = DiscoveryResult(
                            ip_address=IPv4Address(ip_str),
                            method=DiscoveryMethod.MDNS,
                            vendor=vendor,
                            confidence=60,
                        )
            except Exception:
                logger.debug("mdns_scan_skip", service=service_type, exc_info=True)

        return list(discovered.values())

    async def _query_mdns(self, service_type: str) -> dict[str, str]:
        """Query mDNS for a specific service type."""
        import socket as socket_mod

        found: dict[str, str] = {}

        # Build mDNS query
        query = self._build_query(service_type)

        sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_DGRAM, socket_mod.IPPROTO_UDP)
        sock.setsockopt(socket_mod.SOL_SOCKET, socket_mod.SO_REUSEADDR, 1)
        sock.setsockopt(socket_mod.IPPROTO_IP, socket_mod.IP_MULTICAST_TTL, 255)

        try:
            sock.bind(("0.0.0.0", 0))
            sock.sendto(query, (MDNS_MULTICAST, MDNS_PORT))

            sock.settimeout(self.timeout)
            deadline = asyncio.get_event_loop().time() + self.timeout

            while asyncio.get_event_loop().time() < deadline:
                try:
                    sock.settimeout(max(0.1, deadline - asyncio.get_event_loop().time()))
                    data, addr = sock.recvfrom(4096)
                    ip = addr[0]
                    hostname = self._extract_hostname(data)
                    if ip not in found and not ip.startswith("127."):
                        found[ip] = hostname or f"mdns-{ip}"
                except TimeoutError:
                    break
                except OSError:
                    break
        except OSError:
            pass
        finally:
            sock.close()

        return found

    @staticmethod
    def _build_query(service_type: str) -> bytes:
        """Build a minimal mDNS query packet."""
        parts = service_type.rstrip(".").split(".")
        msg = bytearray()
        msg += b"\x00\x00"  # transaction ID
        msg += b"\x00\x00"  # flags: standard query
        msg += b"\x00\x01"  # 1 question
        msg += b"\x00\x00"  # 0 answers
        msg += b"\x00\x00"  # 0 authority
        msg += b"\x00\x00"  # 0 additional

        for part in parts:
            msg.append(len(part))
            msg += part.encode()
        msg.append(0)  # null terminator
        msg += b"\x00\x0c"  # type PTR
        msg += b"\x00\x01"  # class IN

        return bytes(msg)

    @staticmethod
    def _extract_hostname(data: bytes) -> str | None:
        """Extract hostname from mDNS response data."""
        text = data.decode("utf-8", errors="replace")
        match = NAME_RE.search(text)
        if match:
            return match.group(1)
        return None
