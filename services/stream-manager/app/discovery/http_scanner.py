"""
HTTP Scanner — Probe HTTP/HTTPS ports for camera web interfaces.

Extracts Server header, page title, and vendor-specific paths
to identify camera manufacturers and models.
"""

from __future__ import annotations

import asyncio
import re
from ipaddress import IPv4Address, IPv4Network

import structlog

from .engine_data import DeviceVendor, DiscoveryMethod, DiscoveryResult
from .fingerprint import VendorFingerprinter

logger = structlog.get_logger()

HTTP_PORTS = [80, 443, 8080, 8443]
HTTP_TIMEOUT = 5
MAX_CONCURRENT = 50

VENDOR_PATHS = [
    "/cgi-bin/",
    "/ISAPI/",
    "/axis-cgi/",
    "/onvif/device_service",
    "/api/",
    "/goform/",
]

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE)


class HTTPScanner:
    """Scan IPs for HTTP camera interfaces and identify vendors."""

    def __init__(self, timeout: int = HTTP_TIMEOUT):
        self.timeout = timeout
        self.fingerprinter = VendorFingerprinter()

    async def probe(
        self, ip: IPv4Address, ports: list[int] | None = None
    ) -> DiscoveryResult | None:
        ports = ports or HTTP_PORTS
        for port in ports:
            result = await self._probe_port(ip, port)
            if result:
                return result
        return None

    async def _probe_port(self, ip: IPv4Address, port: int) -> DiscoveryResult | None:
        scheme = "https" if port in (443, 8443) else "http"
        base_url = f"{scheme}://{ip}:{port}"

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(str(ip), port), timeout=self.timeout
            )
        except (TimeoutError, OSError, ConnectionRefusedError):
            return None

        result = None
        try:
            request = f"GET / HTTP/1.0\r\nHost: {ip}\r\nUser-Agent: NVR-Discovery/1.0\r\nAccept: text/html\r\nConnection: close\r\n\r\n"
            writer.write(request.encode())
            await writer.drain()
            response = await asyncio.wait_for(reader.read(8192), timeout=self.timeout)
            text = response.decode("utf-8", errors="replace")

            server_header = self._extract_header(text, "Server")
            if not server_header:
                for line in text.split("\r\n"):
                    if line.lower().startswith("server:"):
                        server_header = line.split(":", 1)[1].strip()
                        break

            vendor = DeviceVendor.UNKNOWN
            if server_header:
                vendor = self.fingerprinter.identify_from_server_header(server_header)

            title = None
            title_match = TITLE_RE.search(text)
            if title_match:
                title = title_match.group(1).strip()
                if vendor == DeviceVendor.UNKNOWN:
                    vendor = self.fingerprinter.identify_from_title(title)

            if vendor != DeviceVendor.UNKNOWN or server_header:
                result = DiscoveryResult(
                    ip_address=ip,
                    method=DiscoveryMethod.HTTP,
                    vendor=vendor,
                    http_url=base_url,
                    https_url=base_url if scheme == "https" else None,
                    confidence=30 if vendor == DeviceVendor.UNKNOWN else 50,
                )
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        return result

    @staticmethod
    def _extract_header(response: str, header_name: str) -> str | None:
        pattern = re.compile(rf"^{header_name}:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
        match = pattern.search(response)
        return match.group(1).strip() if match else None

    async def scan_subnet(
        self, subnet_cidr: str, ports: list[int] | None = None
    ) -> list[DiscoveryResult]:
        network = IPv4Network(subnet_cidr, strict=False)
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def scan_ip(ip: IPv4Address) -> DiscoveryResult | None:
            async with sem:
                return await self.probe(ip, ports)

        tasks = [scan_ip(ip) for ip in network.hosts()]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]
