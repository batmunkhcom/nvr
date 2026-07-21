"""
Shared dataclasses for the NVR system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4


class RecordingMode(str, Enum):
    CONTINUOUS = "continuous"
    MOTION = "motion"
    SCHEDULED = "scheduled"


class EventType(str, Enum):
    MOTION_DETECTED = "motion_detected"
    OBJECT_DETECTED = "object_detected"
    FACE_DETECTED = "face_detected"
    AUDIO_DETECTED = "audio_detected"
    CAMERA_OFFLINE = "camera_offline"
    CAMERA_ONLINE = "camera_online"
    RECORDING_STARTED = "recording_started"
    RECORDING_ERROR = "recording_error"
    STORAGE_FULL = "storage_full"
    STORAGE_ERROR = "storage_error"
    SYSTEM_ERROR = "system_error"


class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class CameraInfo:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    ip_address: str = ""
    mac_address: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    stream_main_uri: str | None = None
    has_audio: bool = False
    has_ptz: bool = False
    is_online: bool = False
