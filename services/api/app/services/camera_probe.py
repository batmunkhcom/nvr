"""Camera probe service — RTSP/HTTP detection for a single IP address.

Given an IP, probes common camera ports (RTSP 554, HTTP 80/8000/443),
sends RTSP OPTIONS and HTTP GET, parses Server headers and page titles
to identify manufacturer and model.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from typing import Any

import structlog

logger = structlog.get_logger()

DEFAULT_PORTS = [554, 80, 8000, 443, 8080, 8554, 8443, 88, 37777, 37778]
RTSP_PORTS = {554, 8554, 10554}
HTTP_PORTS = {80, 443, 8000, 8080, 8443, 88}

VENDOR_PATHS: dict[str, str] = {
    "hikvision": "/Streaming/Channels/101",
    "dahua": "/cam/realmonitor?channel=1&subtype=0",
    "axis": "/axis-media/media.amp",
    "reolink": "/h264Preview_01_main",
    "foscam": "/videoMain",
    "amcrest": "/cam/realmonitor?channel=1&subtype=0",
    "uniview": "/media/video1",
    "tp-link": "/stream1",
    "bosch": "/video",
    "samsung_hanwha": "/onvif/device_service",
}

# Server header → vendor name mapping (lowercase keys)
SERVER_TO_VENDOR: dict[str, str] = {
    "hikvision": "hikvision",
    "app-webs": "hikvision",
    "dahua": "dahua",
    "dss": "dahua",
    "web server": "dahua",
    "axis": "axis",
    "reolink": "reolink",
    "tp-link": "tp-link",
    "amcrest": "amcrest",
    "foscam": "foscam",
    "uniview": "uniview",
    "bosch": "bosch",
    "hanwha": "samsung_hanwha",
    "samsung": "samsung_hanwha",
    "wisenet": "samsung_hanwha",
}

# Title keywords → vendor
TITLE_TO_VENDOR: dict[str, str] = {
    "hikvision": "hikvision",
    "ivms": "hikvision",
    "dahua": "dahua",
    "dss": "dahua",
    "axis": "axis",
    "reolink": "reolink",
    "tp-link": "tp-link",
    "amcrest": "amcrest",
    "foscam": "foscam",
    "uniview": "uniview",
    "bosch": "bosch",
    "hanwha": "samsung_hanwha",
    "wisenet": "samsung_hanwha",
}


async def probe_ip(ip: str, timeout: float = 5.0) -> dict[str, Any]:
    """Probe an IP address for camera services.

    Returns a dict with detected camera info: manufacturer, model,
    stream URI, open ports, and capability flags (has_ptz, has_audio, etc.).
    """
    logger.info("camera_probe_start", ip=ip)

    open_ports = await _scan_ports(ip, DEFAULT_PORTS, timeout=1.5)
    if not open_ports:
        return _empty_result(ip)

    rtsp_info = await _probe_rtsp_ports(ip, open_ports, timeout=timeout)
    http_info = await _probe_http_ports(ip, open_ports, timeout=timeout)

    manufacturer = rtsp_info.get("manufacturer") or http_info.get("manufacturer")
    model = http_info.get("model") or rtsp_info.get("model")
    stream_uri = _build_stream_uri(ip, manufacturer)

    result: dict[str, Any] = {
        "reachable": rtsp_info.get("reachable", False) or http_info.get("reachable", False),
        "ip": ip,
        "open_ports": open_ports,
        "manufacturer": manufacturer,
        "model": model,
        "server_header": rtsp_info.get("server_header") or http_info.get("server_header"),
        "http_title": http_info.get("title"),
        "stream_main_uri": stream_uri,
        "has_rtsp": rtsp_info.get("reachable", False),
        "has_http": http_info.get("reachable", False),
        "has_audio": manufacturer in {"hikvision", "dahua", "axis", "reolink", "amcrest", "uniview"},
        "has_ptz": manufacturer in {"hikvision", "dahua", "axis", "foscam", "bosch", "samsung_hanwha"},
        "has_onvif": manufacturer in {
            "hikvision", "dahua", "axis", "bosch", "samsung_hanwha",
            "uniview", "reolink", "amcrest", "foscam",
        },
        "has_motion_detection": manufacturer in {"hikvision", "dahua", "axis"},
    }

    logger.info("camera_probe_done", ip=ip, reachable=result["reachable"],
                manufacturer=manufacturer, open_ports=len(open_ports))
    return result


# ── port scan ──────────────────────────────────────────────────────────────

async def _scan_ports(ip: str, ports: list[int], timeout: float) -> list[int]:
    results: list[tuple[int, bool]] = list(await asyncio.gather(
        *(_check_port(ip, p, timeout) for p in ports), return_exceptions=True,
    ))
    open_ports: list[int] = []
    for item in results:
        if isinstance(item, tuple):
            port, is_open = item
            if is_open:
                open_ports.append(port)
    return sorted(open_ports)


async def _check_port(ip: str, port: int, timeout: float) -> tuple[int, bool]:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout,
        )
        writer.close()
        with contextlib.suppress(TimeoutError, Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
        return port, True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return port, False


# ── RTSP probe ─────────────────────────────────────────────────────────────

async def _probe_rtsp_ports(ip: str, open_ports: list[int], timeout: float) -> dict[str, Any]:
    rtsp_ports = [p for p in open_ports if p in RTSP_PORTS]
    if not rtsp_ports:
        return {"reachable": False}
    for port in rtsp_ports:
        result = await _probe_rtsp(ip, port, timeout)
        if result.get("reachable"):
            return result
    return {"reachable": False}


async def _probe_rtsp(ip: str, port: int, timeout: float) -> dict[str, Any]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout,
        )
    except (TimeoutError, ConnectionRefusedError, OSError):
        return {"reachable": False}

    request = (
        f"OPTIONS rtsp://{ip}:{port} RTSP/1.0\r\n"
        f"CSeq: 1\r\n"
        f"User-Agent: NVR-Probe/1.0\r\n\r\n"
    )
    try:
        writer.write(request.encode())
        await asyncio.wait_for(writer.drain(), timeout=2.0)
        data = await asyncio.wait_for(reader.read(2048), timeout=2.0)
        text = data.decode("utf-8", errors="ignore")
    except (TimeoutError, ConnectionError):
        text = ""
    finally:
        writer.close()
        with contextlib.suppress(TimeoutError, Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=0.5)

    if not text or "RTSP" not in text:
        return {"reachable": False}

    result: dict[str, Any] = {"reachable": True}
    server = _extract_header(text, "Server")
    if server:
        result["server_header"] = server
        result["manufacturer"] = _match_vendor(server, SERVER_TO_VENDOR)
    return result


# ── HTTP probe ─────────────────────────────────────────────────────────────

async def _probe_http_ports(ip: str, open_ports: list[int], timeout: float) -> dict[str, Any]:
    http_ports = [p for p in open_ports if p in HTTP_PORTS]
    if not http_ports:
        return {"reachable": False}
    for port in http_ports:
        result = await _probe_http(ip, port, timeout)
        if result.get("reachable"):
            return result
    return {"reachable": False}


async def _probe_http(ip: str, port: int, timeout: float) -> dict[str, Any]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout,
        )
    except (TimeoutError, ConnectionRefusedError, OSError):
        return {"reachable": False}

    request = (
        f"GET / HTTP/1.0\r\n"
        f"Host: {ip}\r\n"
        f"User-Agent: NVR-Probe/1.0\r\n"
        f"Accept: text/html\r\n\r\n"
    )
    try:
        writer.write(request.encode())
        await asyncio.wait_for(writer.drain(), timeout=2.0)
        data = await asyncio.wait_for(reader.read(4096), timeout=3.0)
        text = data.decode("utf-8", errors="ignore")
    except (TimeoutError, ConnectionError):
        text = ""
    finally:
        writer.close()
        with contextlib.suppress(TimeoutError, Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=0.5)

    if not text:
        return {"reachable": False}

    result: dict[str, Any] = {"reachable": True}
    server = _extract_header(text, "Server")
    if server:
        result["server_header"] = server
        result["manufacturer"] = _match_vendor(server, SERVER_TO_VENDOR)

    title = _extract_html_title(text)
    if title:
        result["title"] = title
        if not result.get("manufacturer"):
            result["manufacturer"] = _match_vendor(title, TITLE_TO_VENDOR)
        if not result.get("model"):
            result["model"] = _extract_model_from_title(title)
    return result


# ── helpers ────────────────────────────────────────────────────────────────

def _extract_header(text: str, header_name: str) -> str | None:
    m = re.search(rf"{header_name}:\s*(.+?)\r?\n", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_html_title(html: str) -> str | None:
    m = re.search(r"<title>(.+?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip().replace("\n", " ")[:200] if m else None


def _extract_model_from_title(title: str) -> str | None:
    patterns = [
        r"([A-Z]+[-_]\d+[A-Z]*(?:[-_]\d+)*)",  # DS-2CD2042WD-I
        r"([A-Z]+\d+[-_][A-Z]+\d+)",              # IPC-HDW2431T
        r"([A-Z]+[-_][A-Z0-9]{4,})",              # Generic model-like
    ]
    for pat in patterns:
        m = re.search(pat, title, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _match_vendor(value: str, mapping: dict[str, str]) -> str | None:
    lower = value.lower()
    for keyword, vendor in mapping.items():
        if keyword in lower:
            return vendor
    return None


def _build_stream_uri(ip: str, manufacturer: str | None) -> str:
    path = VENDOR_PATHS.get(manufacturer or "", "/Streaming/Channels/101")
    return f"rtsp://{ip}:554{path}"


def _empty_result(ip: str) -> dict[str, Any]:
    return {
        "reachable": False, "ip": ip, "open_ports": [],
        "manufacturer": None, "model": None, "server_header": None,
        "http_title": None, "stream_main_uri": None,
        "has_rtsp": False, "has_http": False,
        "has_audio": False, "has_ptz": False, "has_onvif": False,
        "has_motion_detection": False,
    }
