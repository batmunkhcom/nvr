"""RTSP stream authentication check.

Performs a minimal RTSP handshake (OPTIONS → DESCRIBE) against a camera
stream URL over a SINGLE TCP connection. When the server answers 401,
retries DESCRIBE with Basic or Digest auth on the same connection —
Dahua-style cameras bind the digest nonce to the connection, so a fresh
socket would always be rejected with 401 even with valid credentials.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()

DEFAULT_TIMEOUT = 6.0


@dataclass
class RtspCheckResult:
    """Outcome of an RTSP auth/stream check."""

    ok: bool
    error_code: str | None = None  # auth_failed | unreachable | timeout | protocol_error
    error_message: str | None = None
    latency_ms: int | None = None
    server: str | None = None
    auth_methods: list[str] = field(default_factory=list)


async def check_rtsp_stream(
    url: str,
    username: str | None = None,
    password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> RtspCheckResult:
    """Check an RTSP stream URL, authenticating when required.

    Args:
        url: Full rtsp:// URL (credentials in URL are stripped and ignored;
             pass them via username/password instead).
        username: Camera username.
        password: Decrypted camera password.
        timeout: Socket timeout in seconds.

    Returns:
        RtspCheckResult with ok=True when DESCRIBE succeeds (2xx),
        error_code="auth_failed" when credentials are rejected or missing.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return RtspCheckResult(ok=False, error_code="invalid_url", error_message="Invalid RTSP URL")
    port = parsed.port or 554
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    clean_uri = f"rtsp://{host}:{port}{path}"

    started = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except TimeoutError:
        return RtspCheckResult(ok=False, error_code="timeout", error_message="Connection timed out")
    except (ConnectionRefusedError, OSError) as e:
        return RtspCheckResult(
            ok=False,
            error_code="unreachable",
            error_message=f"Cannot connect to {host}:{port} ({e})",
        )

    try:
        session = _RtspSession(reader, writer, timeout)
        resp = await session.request("DESCRIBE", clean_uri, {"Accept": "application/sdp"})
        latency_ms = int((time.monotonic() - started) * 1000)
        status_line = resp.split("\r\n", 1)[0] if resp else ""
        server = _extract_header(resp, "Server")

        if not status_line.startswith("RTSP/"):
            return RtspCheckResult(
                ok=False,
                error_code="protocol_error",
                error_message=f"Unexpected response: {status_line or 'empty'}",
            )
        code = _status_code(status_line)
        if 200 <= code < 300:
            return RtspCheckResult(ok=True, latency_ms=latency_ms, server=server)
        if code not in (401, 403):
            return RtspCheckResult(
                ok=False,
                error_code="stream_error",
                error_message=f"Stream request failed: {status_line}",
                latency_ms=latency_ms,
                server=server,
            )

        # 401/403 — authentication required
        auth_header = _extract_header(resp, "WWW-Authenticate") or ""
        methods = [m.strip().split(" ")[0] for m in auth_header.split(",") if m.strip()]
        if not username or password is None:
            return RtspCheckResult(
                ok=False,
                error_code="auth_failed",
                error_message="Camera requires authentication but no credentials are configured",
                latency_ms=latency_ms,
                server=server,
                auth_methods=methods,
            )

        auth_value = _build_authorization(auth_header, username, password, "DESCRIBE", clean_uri)
        resp = await session.request(
            "DESCRIBE",
            clean_uri,
            {"Accept": "application/sdp", "Authorization": auth_value},
        )
        status_line = resp.split("\r\n", 1)[0] if resp else ""
        code = _status_code(status_line)
        if code in (401, 403):
            logger.warning("rtsp_auth_failed", host=host, port=port, username=username)
            return RtspCheckResult(
                ok=False,
                error_code="auth_failed",
                error_message=f"Wrong username or password (RTSP {status_line[9:].strip()})",
                latency_ms=latency_ms,
                server=server,
                auth_methods=methods,
            )
        if 200 <= code < 300:
            return RtspCheckResult(
                ok=True, latency_ms=latency_ms, server=server, auth_methods=methods
            )
        return RtspCheckResult(
            ok=False,
            error_code="stream_error",
            error_message=f"Stream request failed: {status_line}",
            latency_ms=latency_ms,
            server=server,
        )
    except (TimeoutError, ConnectionError) as e:
        return RtspCheckResult(
            ok=False,
            error_code="unreachable",
            error_message=f"Connection lost ({type(e).__name__})",
        )
    finally:
        writer.close()
        with contextlib.suppress(TimeoutError, Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=0.5)


# ── wire helpers ───────────────────────────────────────────────────────────


class _RtspSession:
    """Minimal RTSP request/response exchange over one open connection."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, timeout: float):
        self._reader = reader
        self._writer = writer
        self._timeout = timeout
        self._cseq = 0

    async def request(self, method: str, uri: str, headers: dict[str, str]) -> str:
        self._cseq += 1
        lines = [
            f"{method} {uri} RTSP/1.0",
            f"CSeq: {self._cseq}",
            "User-Agent: NVR-HealthCheck/1.0",
            *[f"{k}: {v}" for k, v in headers.items()],
        ]
        self._writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
        await asyncio.wait_for(self._writer.drain(), self._timeout)
        data = await asyncio.wait_for(self._reader.read(8192), self._timeout)
        return data.decode("utf-8", errors="ignore")


def _extract_header(text: str, name: str) -> str | None:
    m = re.search(rf"{name}:\s*(.+?)\r?\n", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _status_code(status_line: str) -> int:
    """Parse numeric status code from an RTSP status line."""
    parts = status_line.split(" ", 2)
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return 0


def _build_authorization(
    auth_header: str, username: str, password: str, method: str, uri: str
) -> str:
    if auth_header.lower().startswith("digest"):
        realm = _digest_param(auth_header, "realm")
        nonce = _digest_param(auth_header, "nonce")
        ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
        return (
            f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{uri}", response="{response}"'
        )
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def _digest_param(header: str, name: str) -> str:
    m = re.search(rf'{name}="([^"]*)"', header, re.IGNORECASE)
    return m.group(1) if m else ""
