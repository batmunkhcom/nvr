"""
ONVIF WS-Discovery Scanner — multicast probe for ONVIF-compliant cameras.

Sends WS-Discovery Probe SOAP messages over multicast UDP,
parses ProbeMatch responses, then queries device metadata via HTTP SOAP.
"""

from __future__ import annotations

import asyncio
import socket as socket_mod
import struct
import uuid
from ipaddress import IPv4Address
from xml.etree import ElementTree as ET

import aiohttp
import structlog

from .engine_data import DeviceVendor, DiscoveryMethod, DiscoveryResult, StreamProfile
from .fingerprint import VendorFingerprinter

logger = structlog.get_logger()

ONVIF_MULTICAST = "239.255.255.250"
ONVIF_PORT = 3702
DISCOVERY_TIMEOUT = 15

NS = {
    "wsd": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "wsdp": "http://schemas.xmlsoap.org/ws/2006/02/devprof",
    "dn": "http://www.onvif.org/ver10/network/wsdl",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "s": "http://www.w3.org/2003/05/soap-envelope",
}

WSDP_PROBE = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <s:Header>
    <a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>
    <a:MessageID>urn:uuid:${uuid}</a:MessageID>
    <a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>
  </s:Header>
  <s:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </s:Body>
</s:Envelope>"""


_GET_DEVICE_XML = """<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    <GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>
  </s:Body>
</s:Envelope>"""


_GET_PROFILES_XML = """<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    <GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>
  </s:Body>
</s:Envelope>"""


_GET_STREAM_URI_XML = """<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    <GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">
      <StreamSetup>
        <Stream xmlns="http://www.onvif.org/ver10/schema">RTP-Unicast</Stream>
        <Transport xmlns="http://www.onvif.org/ver10/schema">
          <Protocol>RTSP</Protocol>
        </Transport>
      </StreamSetup>
      <ProfileToken>{profile_token}</ProfileToken>
    </GetStreamUri>
  </s:Body>
</s:Envelope>"""


class ONVIFScanner:
    """Discover cameras using ONVIF WS-Discovery multicast + unicast SOAP queries."""

    def __init__(self, timeout: int = DISCOVERY_TIMEOUT):
        self.timeout = timeout
        self.fingerprinter = VendorFingerprinter()

    async def discover(self) -> list[DiscoveryResult]:
        """Run WS-Discovery multicast probe and return found devices."""
        discovered: dict[str, DiscoveryResult] = {}

        sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_DGRAM, socket_mod.IPPROTO_UDP)
        sock.setsockopt(socket_mod.SOL_SOCKET, socket_mod.SO_REUSEADDR, 1)
        sock.setsockopt(socket_mod.SOL_SOCKET, socket_mod.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 0))
        mreq = struct.pack("4sl", socket_mod.inet_aton(ONVIF_MULTICAST), socket_mod.INADDR_ANY)
        sock.setsockopt(socket_mod.IPPROTO_IP, socket_mod.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)

        msg_id = str(uuid.uuid4())
        probe_msg = WSDP_PROBE.replace("${uuid}", msg_id)
        sock.sendto(probe_msg.encode(), (ONVIF_MULTICAST, ONVIF_PORT))

        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.timeout

        while loop.time() < deadline:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 8192), timeout=remaining
                )
            except TimeoutError:
                break

            try:
                text = data.decode("utf-8", errors="replace")
                xaddrs = self._parse_xaddrs(text)
                if not xaddrs:
                    continue
                ip_str = addr[0]
                if ip_str in discovered:
                    continue

                result = await self._query_device(xaddrs, ip_str)
                if result:
                    discovered[ip_str] = result
            except Exception:
                logger.warning("onvif_parse_error", addr=addr[0], exc_info=True)

        sock.close()
        return list(discovered.values())

    async def _query_device(self, xaddrs: list[str], ip: str) -> DiscoveryResult | None:
        """Query device metadata via ONVIF SOAP HTTP requests."""
        base_url = xaddrs[0]
        device_url = base_url

        full_device_url = (
            device_url if device_url.startswith("http") else f"http://{ip}{device_url}"
        )
        base = full_device_url.rsplit("/", 1)[0] if "/" in full_device_url[8:] else full_device_url

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                # GetDeviceInformation
                manufacturer = None
                model = None
                firmware = None
                serial = None
                try:
                    async with session.post(
                        full_device_url,
                        data=_GET_DEVICE_XML,
                        headers={"Content-Type": "application/soap+xml", "SOAPAction": '""'},
                    ) as resp:
                        if resp.status == 200:
                            xml = await resp.text()
                            root = ET.fromstring(xml)
                            manufacturer = self._find_text(root, ".//tds:Manufacturer")
                            model = self._find_text(root, ".//tds:Model")
                            firmware = self._find_text(root, ".//tds:FirmwareVersion")
                            serial = self._find_text(root, ".//tds:SerialNumber")
                except Exception:
                    pass

                # GetProfiles
                streams: list[StreamProfile] = []
                main_uri = None
                sub_uri = None
                media_url = f"{base}/media"
                try:
                    async with session.post(
                        media_url,
                        data=_GET_PROFILES_XML,
                        headers={"Content-Type": "application/soap+xml", "SOAPAction": '""'},
                    ) as resp:
                        if resp.status == 200:
                            xml = await resp.text()
                            root = ET.fromstring(xml)
                            profiles = root.findall(".//trt:Profiles", NS)
                            for i, profile in enumerate(profiles[:3]):
                                token_el = profile.attrib.get("token")
                                name_el = self._find_text(
                                    profile, ".//trt:Name", default=f"profile_{i}"
                                )
                                profile_token = token_el or ""
                                if profile_token:
                                    stream_uri = await self._get_stream_uri(
                                        session, media_url, profile_token
                                    )
                                    if stream_uri:
                                        if i == 0:
                                            main_uri = stream_uri
                                        elif not sub_uri:
                                            sub_uri = stream_uri
                                        streams.append(
                                            StreamProfile(
                                                name=name_el or f"profile_{i}",
                                                uri=stream_uri,
                                                is_main=(i == 0),
                                            )
                                        )
                except Exception:
                    pass

            vendor = DeviceVendor.UNKNOWN
            if manufacturer:
                vendor = self.fingerprinter.identify_from_onvif_manufacturer(manufacturer)

            return DiscoveryResult(
                ip_address=IPv4Address(ip),
                method=DiscoveryMethod.ONVIF,
                vendor=vendor,
                manufacturer=manufacturer,
                model=model,
                firmware_version=firmware,
                serial_number=serial,
                stream_main_uri=main_uri,
                stream_sub_uri=sub_uri,
                streams=streams,
                onvif_device_service_url=device_url,
                onvif_media_service_url=f"{base}/media",
                confidence=85,
            )
        except Exception:
            logger.warning("onvif_query_error", ip=ip, exc_info=True)
            return None

    async def _get_stream_uri(
        self, session: aiohttp.ClientSession, media_url: str, profile_token: str
    ) -> str | None:
        try:
            body = _GET_STREAM_URI_XML.replace("{profile_token}", profile_token)
            async with session.post(
                media_url,
                data=body,
                headers={"Content-Type": "application/soap+xml", "SOAPAction": '""'},
            ) as resp:
                if resp.status == 200:
                    xml = await resp.text()
                    root = ET.fromstring(xml)
                    uri = root.find(".//trt:Uri", NS)
                    if uri is not None and uri.text:
                        return uri.text.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_xaddrs(data: str) -> list[str]:
        """Extract XAddrs URLs from WS-Discovery ProbeMatch."""
        results: list[str] = []
        tag_start = 0
        while True:
            tag_start = data.find("<d:XAddrs>", tag_start)
            if tag_start == -1:
                break
            tag_end = data.find("</d:XAddrs>", tag_start)
            if tag_end == -1:
                break
            content = data[tag_start + 10 : tag_end]
            results.extend(url.strip() for url in content.split() if url.strip())
            tag_start = tag_end + 11
        return results

    @staticmethod
    def _find_text(element: ET.Element, xpath: str, default: str | None = None) -> str | None:
        """Find text in XML element using namespaced xpath."""
        el = element.find(xpath, NS)
        return el.text.strip() if el is not None and el.text else default

    async def probe_single(self, ip: IPv4Address) -> DiscoveryResult | None:
        """Probe a single IP for ONVIF service via unicast HTTP."""
        result = await self._query_device([f"http://{ip}:80/onvif/device_service"], str(ip))
        if result:
            return result
        for port in (8080, 8000, 8899):
            result = await self._query_device([f"http://{ip}:{port}/onvif/device_service"], str(ip))
            if result:
                return result
        return None
