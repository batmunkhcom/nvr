"""AI detection diagnostics tests."""

from __future__ import annotations

import uuid
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.ai_diagnostic_service import get_camera_ai_diagnostics


class _Row:
    def __init__(self, **kwargs):
        self._mapping = kwargs


def _camera_row(cid=None, name="Cam", **overrides):
    defaults = {
        "id": cid or uuid.uuid4(),
        "name": name,
        "is_active": True,
        "status": "online",
        "stream_main_uri": "rtsp://10.0.0.1/stream1",
        "stream_sub_uri": "rtsp://10.0.0.1/stream2",
        "username": "admin",
        "ai_enabled": True,
        "ai_objects": ["person", "car", "truck"],
        "ai_min_confidence": 0.5,
        "ai_zones": [],
        "ai_sensitivity": "medium",
        "motion_source": "server",
        "recording_mode": "continuous",
        "onvif_events_service_url": None,
        "location_id": None,
        "storage_backend_id": None,
        "sb_id": None,
        "sb_name": None,
        "sb_type": None,
        "sb_mount_point": None,
        "sb_is_active": None,
    }
    defaults.update(overrides)
    return _Row(**defaults)


def _mock_result(row):
    m = MagicMock()
    m.one_or_none = MagicMock(return_value=row)
    return m


def _mock_events_result(count=0, last_at=None):
    Row = namedtuple("Row", ["event_count", "last_event_at"])
    m = MagicMock()
    m.one = MagicMock(return_value=Row(count, last_at))
    return m


@pytest.mark.anyio
async def test_healthy_camera():
    db = AsyncMock()
    cid = uuid.uuid4()
    db.execute = AsyncMock(side_effect=[
        _mock_result(_camera_row()),
        _mock_events_result(),
        _mock_events_result(),
    ])

    report = await get_camera_ai_diagnostics(cid, db)

    assert report["camera_id"] == str(cid)
    assert report["healthy"] is True
    assert report["checks"]["ai_enabled"] is True
    assert report["checks"]["vehicles_in_ai_objects"] is True


@pytest.mark.anyio
async def test_ai_disabled_and_not_motion_mode():
    db = AsyncMock()
    cid = uuid.uuid4()
    db.execute = AsyncMock(side_effect=[
        _mock_result(_camera_row(ai_enabled=False, recording_mode="continuous")),
        _mock_events_result(),
        _mock_events_result(),
    ])

    report = await get_camera_ai_diagnostics(cid, db)

    assert report["healthy"] is False
    assert any("AI detection is disabled" in i for i in report["issues"])


@pytest.mark.anyio
async def test_missing_stream_uri():
    db = AsyncMock()
    cid = uuid.uuid4()
    db.execute = AsyncMock(side_effect=[
        _mock_result(_camera_row(stream_main_uri=None, stream_sub_uri=None)),
        _mock_events_result(),
        _mock_events_result(),
    ])

    report = await get_camera_ai_diagnostics(cid, db)

    assert report["healthy"] is False
    assert any("No stream URI" in i for i in report["issues"])


@pytest.mark.anyio
async def test_no_vehicle_classes():
    db = AsyncMock()
    cid = uuid.uuid4()
    db.execute = AsyncMock(side_effect=[
        _mock_result(_camera_row(ai_objects=["person", "dog"])),
        _mock_events_result(),
        _mock_events_result(),
    ])

    report = await get_camera_ai_diagnostics(cid, db)

    assert report["healthy"] is False
    assert any("No vehicle classes" in i for i in report["issues"])


@pytest.mark.anyio
async def test_high_confidence_warning():
    db = AsyncMock()
    cid = uuid.uuid4()
    db.execute = AsyncMock(side_effect=[
        _mock_result(_camera_row(ai_min_confidence=0.95)),
        _mock_events_result(),
        _mock_events_result(),
    ])

    report = await get_camera_ai_diagnostics(cid, db)

    assert any("ai_min_confidence is very high" in i for i in report["issues"])


@pytest.mark.anyio
async def test_nfs_storage_warning():
    db = AsyncMock()
    cid = uuid.uuid4()
    sb_id = uuid.uuid4()
    db.execute = AsyncMock(side_effect=[
        _mock_result(_camera_row(
            storage_backend_id=sb_id,
            sb_id=sb_id,
            sb_name="Seaweed NFS",
            sb_type="nfs",
            sb_mount_point="/mnt/seaweed",
            sb_is_active=True,
        )),
        _mock_events_result(),
        _mock_events_result(),
    ])

    report = await get_camera_ai_diagnostics(cid, db)

    assert report["checks"]["storage_backend"]["type"] == "nfs"
    assert any("nfs" in i.lower() for i in report["issues"])
