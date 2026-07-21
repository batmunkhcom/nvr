"""SQLAlchemy models — all 21 model classes."""

from .alert_log import AlertLog
from .api_key import ApiKey
from .audio_level import AudioLevel
from .audit_log import AuditLog
from .base import Base
from .camera import Camera
from .camera_ip_history import CameraIpHistory
from .discovery_log import DiscoveryLog
from .discovery_scan import DiscoveryScan
from .event import Event
from .event_rule import EventRule
from .notification import Notification
from .notification_template import NotificationTemplate
from .recording import Recording
from .recording_schedule import RecordingSchedule
from .storage_backend import StorageBackend
from .storage_migration import StorageMigration
from .storage_tier import StorageTier
from .stream_profile import StreamProfile
from .system_config import SystemConfig
from .system_upgrade import SystemUpgrade
from .user import User

__all__ = [
    "AlertLog",
    "ApiKey",
    "AudioLevel",
    "AuditLog",
    "Base",
    "Camera",
    "CameraIpHistory",
    "DiscoveryLog",
    "DiscoveryScan",
    "Event",
    "EventRule",
    "Notification",
    "NotificationTemplate",
    "Recording",
    "RecordingSchedule",
    "StorageBackend",
    "StorageMigration",
    "StorageTier",
    "StreamProfile",
    "SystemConfig",
    "SystemUpgrade",
    "User",
]
