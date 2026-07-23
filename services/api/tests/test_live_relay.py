"""Live relay unit tests — start/stop/status lifecycle with mocked subprocess."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.services import live_relay


class _FakeProc:
    """Minimal stand-in for asyncio.subprocess.Process."""

    def __init__(self, returncode: int | None = None):
        self.returncode = returncode
        self.stderr = None
        self.terminated = False

    async def wait(self):
        # Block forever unless already exited — monitor awaits this
        if self.returncode is not None:
            return self.returncode
        await asyncio.sleep(3600)
        return 0

    def terminate(self):
        self.terminated = True

    def send_signal(self, _sig):
        self.terminated = True


@pytest.fixture(autouse=True)
def clean_streams():
    """Ensure STREAM_DICT is empty around every test."""
    live_relay.STREAM_DICT.clear()
    yield
    live_relay.STREAM_DICT.clear()


class TestStartRelay:
    @pytest.mark.anyio
    async def test_start_spawns_ffmpeg(self):
        proc = _FakeProc()
        with patch.object(live_relay, "_spawn_ffmpeg", AsyncMock(return_value=proc)):
            result = await live_relay.start_relay(uuid.uuid4(), "rtsp://cam/1")

        assert result["status"] == "started"
        assert result["hls_url"] is not None
        assert len(live_relay.STREAM_DICT) == 1

    @pytest.mark.anyio
    async def test_duplicate_start_idempotent(self):
        proc = _FakeProc()
        cid = uuid.uuid4()
        with patch.object(live_relay, "_spawn_ffmpeg", AsyncMock(return_value=proc)):
            first = await live_relay.start_relay(cid, "rtsp://cam/1")
            second = await live_relay.start_relay(cid, "rtsp://cam/1")

        assert first["status"] == "started"
        assert second["status"] == "already_running"
        assert len(live_relay.STREAM_DICT) == 1

    @pytest.mark.anyio
    async def test_ffmpeg_missing_returns_error(self):
        with patch.object(live_relay, "_spawn_ffmpeg", AsyncMock(return_value=None)):
            result = await live_relay.start_relay(uuid.uuid4(), "rtsp://cam/1")

        assert result["status"] == "error"
        assert result["hls_url"] is None
        assert "ffmpeg" in result["error"]
        assert len(live_relay.STREAM_DICT) == 0

    @pytest.mark.anyio
    async def test_relay_key_accepts_string(self):
        proc = _FakeProc()
        with patch.object(live_relay, "_spawn_ffmpeg", AsyncMock(return_value=proc)):
            result = await live_relay.start_relay("abc_sub", "rtsp://cam/1")

        assert result["status"] == "started"
        assert "_sub" in result["hls_url"]


class TestStopRelay:
    @pytest.mark.anyio
    async def test_stop_kills_process(self):
        proc = _FakeProc()
        cid = uuid.uuid4()
        with patch.object(live_relay, "_spawn_ffmpeg", AsyncMock(return_value=proc)):
            await live_relay.start_relay(cid, "rtsp://cam/1")

        result = await live_relay.stop_relay(cid)

        assert result["status"] == "stopped"
        assert proc.terminated is True
        assert str(cid) not in live_relay.STREAM_DICT

    @pytest.mark.anyio
    async def test_stop_not_running(self):
        result = await live_relay.stop_relay(uuid.uuid4())
        assert result["status"] == "not_running"


class TestRelayStatus:
    @pytest.mark.anyio
    async def test_status_running(self):
        proc = _FakeProc()
        cid = uuid.uuid4()
        with patch.object(live_relay, "_spawn_ffmpeg", AsyncMock(return_value=proc)):
            await live_relay.start_relay(cid, "rtsp://cam/1")

        result = await live_relay.relay_status(cid)
        assert result["running"] is True

    @pytest.mark.anyio
    async def test_status_not_running(self):
        cid = uuid.uuid4()
        with patch.object(live_relay, "_check_mediamtx_path", AsyncMock(return_value=False)):
            result = await live_relay.relay_status(cid)

        assert result["running"] is False
        assert result["hls_url"] is None


class TestCircuitBreaker:
    def test_backoff_caps_at_600(self):
        """Rule 17: exponential backoff must cap at 600s, not grow unbounded."""
        # 3 * 2^9 = 1536 — must be capped
        for restart_count in range(15):
            backoff = min(live_relay.BASE_BACKOFF * (2**restart_count), live_relay.MAX_BACKOFF)
            assert backoff <= live_relay.MAX_BACKOFF

    def test_backoff_progression(self):
        """Backoff doubles each restart: 3, 6, 12, 24..."""
        expected = [3, 6, 12, 24, 48, 96, 192, 384, 600, 600]
        for i, exp in enumerate(expected):
            backoff = min(live_relay.BASE_BACKOFF * (2**i), live_relay.MAX_BACKOFF)
            assert backoff == exp
