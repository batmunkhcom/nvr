"""Unit tests for the RTSP stream auth check (camera_rtsp_check)."""

from __future__ import annotations

import asyncio
import base64
import hashlib

import pytest
from app.services.camera_rtsp_check import check_rtsp_stream

REALM = "TestRealm"
NONCE = "abc123nonce"
USERNAME = "admin"
PASSWORD = "secret123"


def _digest_ok(auth_value: str, method: str, uri: str) -> bool:
    if not auth_value.startswith("Digest "):
        return False
    params = {}
    for part in auth_value[7:].split(", "):
        k, _, v = part.partition("=")
        params[k.strip()] = v.strip().strip('"')
    ha1 = hashlib.md5(f"{USERNAME}:{REALM}:{PASSWORD}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    expected = hashlib.md5(f"{ha1}:{NONCE}:{ha2}".encode()).hexdigest()
    return params.get("username") == USERNAME and params.get("response") == expected


class FakeRtspServer:
    """Minimal fake RTSP server for auth testing."""

    def __init__(self, mode: str):
        self.mode = mode  # open | digest | basic | bad_status
        self.server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            buffer = b""
            while True:  # multiple requests per connection (Dahua-style nonce binding)
                try:
                    data = await asyncio.wait_for(reader.read(4096), timeout=3)
                except (TimeoutError, ConnectionError):
                    break
                if not data:
                    break
                buffer += data
                if b"\r\n\r\n" not in buffer:
                    continue
                req, buffer = buffer.split(b"\r\n\r\n", 1)
                resp = self._respond(req.decode("utf-8", errors="ignore"))
                writer.write(resp.encode())
                await writer.drain()
        finally:
            writer.close()

    def _respond(self, req: str) -> str:
        first_line = req.split("\r\n", 1)[0]
        parts = first_line.split(" ")
        method, uri = parts[0], parts[1]
        auth = ""
        cseq = "1"
        for line in req.split("\r\n"):
            if line.lower().startswith("authorization:"):
                auth = line.split(":", 1)[1].strip()
            if line.lower().startswith("cseq:"):
                cseq = line.split(":", 1)[1].strip()

        if self.mode == "open":
            return f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\n\r\n"
        if self.mode == "bad_status":
            return f"RTSP/1.0 454 Session Not Found\r\nCSeq: {cseq}\r\n\r\n"
        if self.mode == "digest":
            if auth and _digest_ok(auth, method, uri):
                return f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\n\r\n"
            return (
                f"RTSP/1.0 401 Unauthorized\r\nCSeq: {cseq}\r\n"
                f'WWW-Authenticate: Digest realm="{REALM}", nonce="{NONCE}"\r\n\r\n'
            )
        if self.mode == "basic":
            expected = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
            if auth == f"Basic {expected}":
                return f"RTSP/1.0 200 OK\r\nCSeq: {cseq}\r\n\r\n"
            return (
                f"RTSP/1.0 401 Unauthorized\r\nCSeq: {cseq}\r\n"
                'WWW-Authenticate: Basic realm="cam"\r\n\r\n'
            )
        return "RTSP/1.0 500 Internal Server Error\r\n\r\n"


@pytest.fixture
async def rtsp_server():
    servers: list[FakeRtspServer] = []

    async def _make(mode: str) -> FakeRtspServer:
        srv = FakeRtspServer(mode)
        await srv.start()
        servers.append(srv)
        return srv

    yield _make
    for srv in servers:
        await srv.stop()


class TestCheckRtspStream:
    async def test_open_stream_ok(self, rtsp_server):
        srv = await rtsp_server("open")
        result = await check_rtsp_stream(f"rtsp://127.0.0.1:{srv.port}/stream1")
        assert result.ok is True
        assert result.error_code is None
        assert result.latency_ms is not None

    async def test_digest_auth_success(self, rtsp_server):
        srv = await rtsp_server("digest")
        result = await check_rtsp_stream(
            f"rtsp://127.0.0.1:{srv.port}/stream1", username=USERNAME, password=PASSWORD
        )
        assert result.ok is True
        assert result.error_code is None

    async def test_digest_auth_wrong_password(self, rtsp_server):
        srv = await rtsp_server("digest")
        result = await check_rtsp_stream(
            f"rtsp://127.0.0.1:{srv.port}/stream1", username=USERNAME, password="wrong"
        )
        assert result.ok is False
        assert result.error_code == "auth_failed"
        assert "Wrong username or password" in (result.error_message or "")

    async def test_auth_required_but_no_credentials(self, rtsp_server):
        srv = await rtsp_server("digest")
        result = await check_rtsp_stream(f"rtsp://127.0.0.1:{srv.port}/stream1")
        assert result.ok is False
        assert result.error_code == "auth_failed"
        assert "no credentials" in (result.error_message or "")

    async def test_basic_auth_success(self, rtsp_server):
        srv = await rtsp_server("basic")
        result = await check_rtsp_stream(
            f"rtsp://127.0.0.1:{srv.port}/stream1", username=USERNAME, password=PASSWORD
        )
        assert result.ok is True

    async def test_unreachable(self):
        # Port 1 on localhost is virtually always closed
        result = await check_rtsp_stream("rtsp://127.0.0.1:1/stream1", timeout=1.0)
        assert result.ok is False
        assert result.error_code == "unreachable"

    async def test_invalid_url(self):
        result = await check_rtsp_stream("not-a-url")
        assert result.ok is False
        assert result.error_code == "invalid_url"

    async def test_non_auth_error_status(self, rtsp_server):
        srv = await rtsp_server("bad_status")
        result = await check_rtsp_stream(f"rtsp://127.0.0.1:{srv.port}/stream1")
        assert result.ok is False
        assert result.error_code == "stream_error"
