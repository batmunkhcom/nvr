"""NVR common types and events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventType(StrEnum):
    MOTION_DETECTED = "motion_detected"
    OBJECT_DETECTED = "object_detected"
    PERSON_DETECTED = "person_detected"
    FACE_DETECTED = "face_detected"
    FACE_RECOGNIZED = "face_recognized"
    AUDIO_DETECTED = "audio_detected"
    CAMERA_OFFLINE = "camera_offline"
    CAMERA_ONLINE = "camera_online"
    RECORDING_ERROR = "recording_error"
    STORAGE_FULL = "storage_full"
    STORAGE_ERROR = "storage_error"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"


@dataclass
class DetectionEvent:
    camera_id: str
    event_type: EventType
    confidence: float
    objects: list[dict]

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "event_type": self.event_type.value,
            "confidence": self.confidence,
            "objects": self.objects,
        }
