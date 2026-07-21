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
