"""Pydantic schemas for recordings, storage, and timeline."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RecordingResponse(BaseModel):
    id: UUID
    camera_id: UUID
    storage_backend_id: UUID | None = None
    file_path: str
    file_size_bytes: int
    duration_seconds: float
    start_time: datetime
    end_time: datetime
    recording_type: str
    has_audio: bool
    resolution: str | None = None
    codec: str | None = None
    bitrate_kbps: int | None = None
    event_id: UUID | None = None
    retention_override_days: int | None = None
    checksum_sha256: str | None = None
    is_corrupt: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RecordingListResponse(BaseModel):
    data: list[RecordingResponse]
    metadata: dict


class TimelineSegment(BaseModel):
    camera_id: UUID
    start_time: datetime
    end_time: datetime
    recording_type: str
    has_motion: bool


class TimelineResponse(BaseModel):
    data: list[TimelineSegment]


class StorageBackendResponse(BaseModel):
    id: UUID
    name: str
    backend_type: str
    mount_point: str | None = None
    total_bytes: int
    available_bytes: int
    priority: int
    is_active: bool
    health_status: str
    last_health_check: datetime | None = None

    model_config = {"from_attributes": True}


class StorageUsageResponse(BaseModel):
    total_bytes: int
    used_bytes: int
    free_bytes: int
    backends: list[StorageBackendResponse]
