"""Live relay unit tests — start/stop/status lifecycle with mocked stream-manager."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.services import live_relay


@pytest.fixture(autouse=True)
def clean_streams():
    live_relay.STREAM_DICT.clear()
    yield
    live_relay.STREAM_DICT.clear()


def _sm_response(**kw):
    return {"hls_url": f"/hls/{kw.get('cid','test')}/index.m3u8", "status": "started"}


class TestStartRelay:
    @pytest.mark.anyio
    async def test_start_delegates_to_stream_manager(self):
        cid = uuid.uuid4()
        with patch.object(
            live_relay, "_call_stream_manager", AsyncMock(return_value=_sm_response(cid=str(cid)))
        ) as mock_call:
            result = await live_relay.start_relay(cid, "rtsp://cam/1")

        assert result["status"] == "started"
        assert result["hls_url"] is not None
        assert len(live_relay.STREAM_DICT) == 1
        mock_call.assert_called_once()

    @pytest.mark.anyio
    async def test_duplicate_start_idempotent(self):
        cid = uuid.uuid4()
        with patch.object(
            live_relay, "_call_stream_manager", AsyncMock(return_value=_sm_response(cid=str(cid)))
        ):
            first = await live_relay.start_relay(cid, "rtsp://cam/1")
            second = await live_relay.start_relay(cid, "rtsp://cam/1")

        assert first["status"] == "started"
        assert second["status"] == "already_running"

    @pytest.mark.anyio
    async def test_stream_manager_unreachable_returns_error(self):
        with patch.object(
            live_relay, "_call_stream_manager", AsyncMock(side_effect=RuntimeError("down"))
        ):
            result = await live_relay.start_relay(uuid.uuid4(), "rtsp://cam/1")

        assert result["status"] == "error"
        assert result["hls_url"] is None
        assert len(live_relay.STREAM_DICT) == 0

    @pytest.mark.anyio
    async def test_relay_key_accepts_string(self):
        with patch.object(
            live_relay, "_call_stream_manager",
            AsyncMock(return_value=_sm_response(cid="abc_sub")),
        ):
            result = await live_relay.start_relay("abc_sub", "rtsp://cam/1")

        assert result["status"] == "started"
        assert "abc_sub" in result["hls_url"]


class TestStopRelay:
    @pytest.mark.anyio
    async def test_stop_delegates_to_stream_manager(self):
        cid = uuid.uuid4()
        with patch.object(
            live_relay, "_call_stream_manager", AsyncMock(return_value={"status": "stopped"})
        ):
            with patch.object(
                live_relay, "_call_stream_manager", AsyncMock(return_value=_sm_response(cid=str(cid)))
            ):
                await live_relay.start_relay(cid, "rtsp://cam/1")

            result = await live_relay.stop_relay(cid)

        assert result["status"] == "stopped"
        assert str(cid) not in live_relay.STREAM_DICT

    @pytest.mark.anyio
    async def test_stop_not_running(self):
        with patch.object(
            live_relay, "_call_stream_manager", AsyncMock(return_value={"status": "stopped"})
        ):
            result = await live_relay.stop_relay(uuid.uuid4())
        assert result["status"] == "stopped"


class TestRelayStatus:
    @pytest.mark.anyio
    async def test_status_running(self):
        cid = uuid.uuid4()
        with patch.object(
            live_relay, "_call_stream_manager", AsyncMock(return_value=_sm_response(cid=str(cid)))
        ):
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


class TestErrorHandling:
    @pytest.mark.anyio
    async def test_stop_recovery_on_sm_failure(self):
        """stop_relay should not raise even when stream-manager is unreachable."""
        cid = uuid.uuid4()
        with patch.object(
            live_relay, "_call_stream_manager", AsyncMock(side_effect=RuntimeError("down"))
        ):
            result = await live_relay.stop_relay(cid)

        assert result["status"] == "stopped"
