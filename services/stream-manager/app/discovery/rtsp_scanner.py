"""
RTSP Scanner — Port probe, OPTIONS/DESCRIBE, SDP parsing, vendor detection.

Performs full RTSP handshake to identify camera streams and capabilities.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from ipaddress import IPv4Address, IPv4Network

import structlog

from .engine_data import DeviceVendor, DiscoveryMethod, DiscoveryResult, StreamProfile
from .fingerprint import VendorFingerprinter

logger = structlog.get_logger()

RTSP_PORTS = [554, 8554, 10554]
MAX_CONCURRENT = 50

SDP_CODEC_MAP = {96: "h264", 97: "h265", 98: "h264", 99: "h265", 8: "pcm", 0: "pcm", 3: "g711"}


def _parse_sdp(sdp: str) -> list[StreamProfile]:
    """Parse SDP response into stream profiles."""
    profiles: list[StreamProfile] = []
    current_media: dict[str, str] = {}
    session_resolution: str | None = None
    resolution_re = re.compile(r"width=(\d+).*height=(\d+)")

    for line in sdp.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("a=x-dimensions:"):
            dim = line.split(":")[1] if ":" in line else ""
            parts = dim.split(",")
            if len(parts) >= 2:
                session_resolution = f"{parts[0]}x{parts[1]}"
        elif res_match := resolution_re.search(line):
            session_resolution = f"{res_match.group(1)}x{res_match.group(2)}"

        if line.startswith("m="):
            if current_media:
                profiles.append(_build_profile(current_media, session_resolution, len(profiles)))
            parts = line[2:].split()
            current_media = {
                "media_type": parts[0],
                "port": parts[1],
                "transport": parts[2],
                "fmt_list": parts[3:],
            }
        elif line.startswith("a=rtpmap:") and current_media:
            content = line[9:]
            pt, rest = content.split(" ", 1) if " " in content else (content.split("/")[0], content)
            codec_name = rest.split("/")[0] if "/" in rest else rest
            pt_num = int(pt)
            current_media.setdefault("codecs", {})[pt_num] = codec_name
        elif line.startswith("a=framerate:") and current_media:
            with contextlib.suppress(ValueError, IndexError):
                current_media["fps"] = str(int(float(line.split(":")[1])))

    if current_media:
        profiles.append(_build_profile(current_media, session_resolution, len(profiles)))
    return profiles


def _build_profile(media: dict, resolution: str | None, index: int) -> StreamProfile:
    fmt_list = media.get("fmt_list", [])
    codec_map = media.get("codecs", {})

    codec = None
    if fmt_list and codec_map:
        pt = int(fmt_list[0])
        raw_codec = codec_map.get(pt, "")
        codec = SDP_CODEC_MAP.get(pt, raw_codec.lower() if raw_codec else None)

    return StreamProfile(
        name="main" if index == 0 else f"sub_{index}",
        uri="",
        codec=codec or (codec_map.get(int(fmt_list[0]), "") if fmt_list and codec_map else None),
        resolution=resolution,
        fps=int(media["fps"]) if media.get("fps") else None,
        is_main=(index == 0),
    )


class RTSPscanner:
    """Scan IP addresses for RTSP camera services with full handshake."""

    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.fingerprinter = VendorFingerprinter()

    async def probe(
        self, ip: IPv4Address, ports: list[int] | None = None
    ) -> DiscoveryResult | None:
        ports = ports or RTSP_PORTS
        for port in ports:
            result = await self._probe_port(ip, port)
            if result:
                return result
        return None

    async def _probe_port(self, ip: IPv4Address, port: int) -> DiscoveryResult | None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(str(ip), port), timeout=self.timeout
            )
        except (TimeoutError, OSError, ConnectionRefusedError):
            return None

        try:
            options_resp = await self._send_rtsp_request(
                reader, writer, f"OPTIONS rtsp://{ip}:{port} RTSP/1.0\r\nCSeq: 1\r\n\r\n", "RTSP"
            )
            if not options_resp:
                return None

            server_header = self._extract_header(options_resp, "Server")
            vendor = (
                self.fingerprinter.identify_from_server_header(server_header)
                if server_header
                else DeviceVendor.UNKNOWN
            )

            describe_resp = await self._send_rtsp_request(
                reader,
                writer,
                f"DESCRIBE rtsp://{ip}:{port} RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\n\r\n",
                "SDP",
            )
            streams: list[StreamProfile] = []
            if describe_resp and "v=0" in describe_resp:
                streams = _parse_sdp(describe_resp)

            main_uri = None
            sub_uri = None
            for s in streams:
                if s.is_main:
                    main_uri = f"rtsp://{ip}:{port}/" + (s.uri if s.uri else "")
                elif not sub_uri:
                    sub_uri = f"rtsp://{ip}:{port}/" + (s.uri if s.uri else "")

            if not main_uri and not streams:
                main_uri = f"rtsp://{ip}:{port}"

            return DiscoveryResult(
                ip_address=ip,
                method=DiscoveryMethod.RTSP,
                vendor=vendor,
                stream_main_uri=main_uri,
                stream_sub_uri=sub_uri,
                streams=streams,
                confidence=55,
            )
        except Exception:
            logger.warning("rtsp_probe_error", ip=str(ip), port=port, exc_info=True)
            return None
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _send_rtsp_request(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, request: str, expect: str
    ) -> str | None:
        try:
            writer.write(request.encode())
            await writer.drain()
            response = await asyncio.wait_for(reader.read(4096), timeout=self.timeout)
            text = response.decode("utf-8", errors="replace")
            if expect in text:
                return text
            return None
        except Exception:
            return None

    def _extract_header(self, response: str, header_name: str) -> str | None:
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
