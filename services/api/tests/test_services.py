"""Service layer unit tests — camera, recording, timeline, storage usage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.camera_service import camera_to_dict, get_camera_response
from app.services.recording_service import (
    delete_recording,
    get_recording,
    get_recording_stats,
    get_storage_usage,
    get_timeline_segments,
)
from fastapi import HTTPException


class _ExecResult:
    """Wraps a mock DB row result. When awaited, returns self for chaining."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._items

    def one(self):
        return self._tuple_value

    def scalar(self):
        return self._scalar_value

    def first(self):
        return self._value

    def __await__(self):
        yield
        return self


def _result_with_scalar_one(value):
    r = _ExecResult()
    r._value = value
    r._scalar_value = 1
    return r


def _result_with_items(items):
    r = _ExecResult()
    r._items = items
    return r


def _result_with_tuple(tup):
    r = _ExecResult()
    r._tuple_value = tup
    return r


def _result_with_scalar(val):
    r = _ExecResult()
    r._scalar_value = val
    return r


@pytest.fixture
def mock_db():
    m = MagicMock()
    m.add = MagicMock()

    async def _flush():
        pass

    m.flush = _flush
    m.delete = AsyncMock()
    m.commit = AsyncMock()
    m.rollback = AsyncMock()
    return m


class TestCameraToDict:
    def test_serializes(self):
        m = MagicMock()
        m.id = uuid.uuid4()
        m.name = "Cam"
        m.ip_address = "10.0.0.1"
        m.port = 554
        m.manufacturer = m.model = m.serial_number = m.firmware_version = m.username = None
        m.status = "offline"
        m.stream_main_uri = "rtsp://10.0.0.1/"
        m.stream_sub_uri = m.connection_error = m.raw_onvif_url = None
        m.has_ptz = False
        m.has_audio = False
        m.rtsp_transport = "tcp"
        m.created_at = m.updated_at = None

        r = camera_to_dict(m)
        assert r["name"] == "Cam"
        assert r["status"] == "offline"


class TestGetCameraResponse:
    @pytest.mark.anyio
    async def test_raises_404(self, mock_db):
        mock_db.execute.return_value = _result_with_scalar_one(None)

        with pytest.raises(HTTPException) as exc:
            await get_camera_response(uuid.uuid4(), mock_db)
        assert exc.value.status_code == 404

    @pytest.mark.anyio
    async def test_returns_camera(self, mock_db):
        cam = MagicMock()
        cam.id = uuid.uuid4()
        cam.name = "Found"
        cam.ip_address = "10.0.0.1"
        cam.port = 554
        cam.manufacturer = "Co"
        cam.model = cam.serial_number = cam.firmware_version = cam.username = None
        cam.status = "online"
        cam.stream_main_uri = "rtsp://10.0.0.1/"
        cam.stream_sub_uri = cam.connection_error = cam.raw_onvif_url = None
        cam.has_ptz = False
        cam.has_audio = False
        cam.rtsp_transport = "tcp"
        cam.created_at = cam.updated_at = None

        mock_db.execute.return_value = _result_with_scalar_one(cam)

        r = await get_camera_response(cam.id, mock_db)
        assert r["name"] == "Found"
        assert r["status"] == "online"


class TestGetRecording:
    @pytest.mark.anyio
    async def test_raises_404(self, mock_db):
        mock_db.execute.return_value = _result_with_scalar_one(None)

        with pytest.raises(HTTPException) as exc:
            await get_recording(uuid.uuid4(), mock_db)
        assert exc.value.status_code == 404

    @pytest.mark.anyio
    async def test_returns_recording(self, mock_db):
        r = MagicMock()
        r.id = uuid.uuid4()
        r.file_path = "/data/rec.mp4"

        mock_db.execute.return_value = _result_with_scalar_one(r)

        rec = await get_recording(r.id, mock_db)
        assert rec.file_path == "/data/rec.mp4"


class TestTimelineSegments:
    @pytest.mark.anyio
    async def test_empty(self, mock_db):
        mock_db.execute.return_value = _result_with_items([])

        segments = await get_timeline_segments(uuid.uuid4(), "2026-07-22", mock_db)
        assert segments == []

    @pytest.mark.anyio
    async def test_with_motion(self, mock_db):
        r = MagicMock()
        r.camera_id = uuid.uuid4()
        r.start_time = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
        r.end_time = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
        r.recording_type = "motion"

        mock_db.execute.return_value = _result_with_items([r])

        segments = await get_timeline_segments(r.camera_id, "2026-07-22", mock_db)
        assert len(segments) == 1
        assert segments[0]["has_motion"] is True


class TestStorageUsage:
    @pytest.mark.anyio
    async def test_aggregates(self, mock_db):
        b = MagicMock()
        b.name = "Local"
        b.backend_type = "local"
        b.total_bytes = 1000
        b.available_bytes = 500
        b.priority = 1
        b.is_active = True
        b.health_status = "healthy"
        b.last_health_check = None

        mock_db.execute.return_value = _result_with_items([b])

        usage = await get_storage_usage(mock_db)
        assert usage["total_bytes"] == 1000
        assert usage["free_bytes"] == 500


class TestDeleteRecording:
    @pytest.mark.anyio
    async def test_deletes(self, mock_db):
        rec = MagicMock()
        rec.id = uuid.uuid4()

        mock_db.execute.return_value = _result_with_scalar_one(rec)

        await delete_recording(rec.id, mock_db)
        mock_db.delete.assert_called_once()


class TestRecordingStats:
    @pytest.mark.anyio
    async def test_zero_stats(self, mock_db):
        mock_db.execute.side_effect = [
            _result_with_scalar(0),
            _result_with_tuple((0, 0)),
        ]

        stats = await get_recording_stats(mock_db)
        assert stats["recordings_24h"] == 0
        assert stats["storage_bytes_24h"] == 0


class TestCameraConnectionTest:
    """Connection test must surface auth failures, not just reachability."""

    def _camera(self):
        cam = MagicMock()
        cam.id = uuid.uuid4()
        cam.name = "Cam"
        cam.ip_address = "10.0.0.1"
        cam.username = "admin"
        cam.encrypted_password = "enc"
        cam.stream_main_uri = "rtsp://10.0.0.1:554/stream1"
        cam.status = "unknown"
        cam.connection_error = None
        return cam

    @pytest.mark.anyio
    async def test_auth_failed_sets_degraded(self, mock_db, monkeypatch):
        from app.services import camera_service
        from app.services.camera_rtsp_check import RtspCheckResult

        cam = self._camera()
        mock_db.execute.return_value = _result_with_scalar_one(cam)

        async def fake_probe(ip, timeout=5.0):
            return {"reachable": True, "manufacturer": "hikvision", "open_ports": [554]}

        async def fake_check(url, username=None, password=None, timeout=6.0):
            return RtspCheckResult(
                ok=False,
                error_code="auth_failed",
                error_message="Wrong username or password (RTSP 401 Unauthorized)",
            )

        monkeypatch.setattr("app.services.camera_probe.probe_ip", fake_probe)
        monkeypatch.setattr("app.services.camera_rtsp_check.check_rtsp_stream", fake_check)
        monkeypatch.setattr(camera_service, "decrypt_password_aes", lambda c: "pw")

        result = await camera_service.test_camera_connection(cam.id, mock_db)

        assert result["error_code"] == "auth_failed"
        assert "password" in result["error_message"].lower()
        assert result["auth_ok"] is False
        assert cam.status == "degraded"
        assert cam.connection_error == result["error_message"]

    @pytest.mark.anyio
    async def test_unreachable_sets_offline(self, mock_db, monkeypatch):
        from app.services import camera_service

        cam = self._camera()
        mock_db.execute.return_value = _result_with_scalar_one(cam)

        async def fake_probe(ip, timeout=5.0):
            return {"reachable": False, "manufacturer": None, "open_ports": []}

        monkeypatch.setattr("app.services.camera_probe.probe_ip", fake_probe)

        result = await camera_service.test_camera_connection(cam.id, mock_db)

        assert result["error_code"] == "unreachable"
        assert cam.status == "offline"
        assert cam.connection_error

    @pytest.mark.anyio
    async def test_success_clears_error(self, mock_db, monkeypatch):
        from app.services import camera_service
        from app.services.camera_rtsp_check import RtspCheckResult

        cam = self._camera()
        cam.connection_error = "old error"
        mock_db.execute.return_value = _result_with_scalar_one(cam)

        async def fake_probe(ip, timeout=5.0):
            return {"reachable": True, "manufacturer": "dahua", "open_ports": [554]}

        async def fake_check(url, username=None, password=None, timeout=6.0):
            return RtspCheckResult(ok=True, latency_ms=12)

        monkeypatch.setattr("app.services.camera_probe.probe_ip", fake_probe)
        monkeypatch.setattr("app.services.camera_rtsp_check.check_rtsp_stream", fake_check)
        monkeypatch.setattr(camera_service, "decrypt_password_aes", lambda c: "pw")

        result = await camera_service.test_camera_connection(cam.id, mock_db)

        assert result["error_code"] is None
        assert result["auth_ok"] is True
        assert result["latency_ms"] == 12
        assert cam.status == "online"
        assert cam.connection_error is None

    @pytest.mark.anyio
    async def test_no_stream_uri(self, mock_db, monkeypatch):
        from app.services import camera_service

        cam = self._camera()
        cam.stream_main_uri = None
        mock_db.execute.return_value = _result_with_scalar_one(cam)

        async def fake_probe(ip, timeout=5.0):
            return {"reachable": True, "manufacturer": None, "open_ports": [80]}

        monkeypatch.setattr("app.services.camera_probe.probe_ip", fake_probe)

        result = await camera_service.test_camera_connection(cam.id, mock_db)

        assert result["error_code"] == "no_stream_uri"
        assert cam.status == "offline"
