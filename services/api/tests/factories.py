"""Test factories for generating test data using factory-boy."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import factory


class NvrFactory(factory.Factory):
    """Base factory for NVR test data."""

    class Meta:
        abstract = True


class UserDictFactory(NvrFactory):
    """Generate user data dicts for tests."""

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    username = factory.Faker("user_name")
    email = factory.Faker("email")
    full_name = factory.Faker("name")
    role = "operator"
    is_active = True
    created_at = factory.LazyFunction(lambda: datetime.now(UTC).isoformat())

    class Meta:
        model = dict


class CameraDictFactory(NvrFactory):
    """Generate camera data dicts for tests."""

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    name = factory.Faker("word")
    ip_address = factory.Faker("ipv4")
    port = 554
    manufacturer = factory.Faker("company")
    model = factory.Faker("word")
    username = "admin"
    serial_number = factory.Faker("uuid4")
    status = "offline"
    stream_main_uri = factory.LazyAttribute(lambda o: f"rtsp://{o.ip_address}:{o.port}/stream")
    has_ptz = False
    has_audio = False
    created_at = factory.LazyFunction(lambda: datetime.now(UTC).isoformat())

    class Meta:
        model = dict


class RecordingDictFactory(NvrFactory):
    """Generate recording data dicts for tests."""

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    camera_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    file_path = factory.LazyFunction(lambda: f"/data/recordings/{uuid.uuid4()}.mp4")
    file_size_bytes = factory.Faker("random_int", min=100000, max=500000000)
    duration_seconds = factory.Faker("random_int", min=10, max=3600)
    start_time = factory.LazyFunction(lambda: datetime.now(UTC).isoformat())
    end_time = factory.LazyFunction(lambda: datetime.now(UTC).isoformat())
    recording_type = "continuous"
    has_audio = False
    resolution = "1920x1080"
    codec = "h264"
    is_corrupt = False
    created_at = factory.LazyFunction(lambda: datetime.now(UTC).isoformat())

    class Meta:
        model = dict


class EventDictFactory(NvrFactory):
    """Generate event data dicts for tests."""

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    camera_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    event_type = factory.Iterator(["motion_detected", "person_detected", "camera_offline"])
    severity = factory.Iterator(["info", "warning", "critical"])
    start_time = factory.LazyFunction(lambda: datetime.now(UTC).isoformat())
    confidence = factory.Faker("random_number", digits=2)
    is_acknowledged = False
    created_at = factory.LazyFunction(lambda: datetime.now(UTC).isoformat())

    class Meta:
        model = dict
