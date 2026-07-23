"""Camera model — registry of IP cameras."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .location import Location
    from .storage_backend import StorageBackend

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSON, MACADDR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .recording_schedule import RecordingSchedule
    from .stream_profile import StreamProfile


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    mac_address: Mapped[str | None] = mapped_column(MACADDR)
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(255))
    firmware_version: Mapped[str | None] = mapped_column(String(50))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    stream_main_uri: Mapped[str | None] = mapped_column(String(1024))
    stream_sub_uri: Mapped[str | None] = mapped_column(String(1024))
    stream_audio_uri: Mapped[str | None] = mapped_column(String(1024))
    auth_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="basic", server_default="basic"
    )
    username: Mapped[str] = mapped_column(
        String(100), nullable=False, default="admin", server_default="admin"
    )
    encrypted_password: Mapped[str | None] = mapped_column(Text)
    has_audio: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    has_talkback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    has_ptz: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    has_onvif: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    has_motion_detection: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    has_io_ports: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    onvif_motion_supported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    motion_source: Mapped[str | None] = mapped_column(
        String(20), default="server", server_default="server"
    )
    max_resolution: Mapped[str | None] = mapped_column(String(20))
    onvif_device_service_url: Mapped[str | None] = mapped_column(String(1024))
    onvif_media_service_url: Mapped[str | None] = mapped_column(String(1024))
    onvif_ptz_service_url: Mapped[str | None] = mapped_column(String(1024))
    onvif_events_service_url: Mapped[str | None] = mapped_column(String(1024))
    recording_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="continuous", server_default="continuous"
    )
    stream_transport: Mapped[str] = mapped_column(
        String(20), nullable=False, default="tcp", server_default="tcp"
    )
    pre_record_seconds: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=5, server_default="5"
    )
    post_record_seconds: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=10, server_default="10"
    )
    preferred_ip: Mapped[str | None] = mapped_column(INET)
    ip_binding: Mapped[str | None] = mapped_column(
        String(20), default="dynamic", server_default="dynamic"
    )
    network_interface: Mapped[str | None] = mapped_column(String(50))
    privacy_mode: Mapped[str | None] = mapped_column(
        String(20), default="none", server_default="none"
    )
    ptz_presets: Mapped[dict | None] = mapped_column(JSON, default=list, server_default="'[]'")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default="unknown"
    )
    connection_error: Mapped[str | None] = mapped_column(String(500))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovery_source: Mapped[str | None] = mapped_column(String(50))
    discovery_confidence: Mapped[int | None] = mapped_column(
        SmallInteger, default=0, server_default="0"
    )
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    location: Mapped[str | None] = mapped_column(String(255))
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
    )
    storage_backend_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_backends.id", ondelete="SET NULL"),
    )
    notes: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    location_ref: Mapped[Location | None] = relationship("Location", lazy="selectin")

    storage_backend: Mapped[StorageBackend | None] = relationship(
        "StorageBackend", lazy="selectin", foreign_keys=[storage_backend_id]
    )

    stream_profiles: Mapped[list[StreamProfile]] = relationship(
        "StreamProfile", back_populates="camera", lazy="selectin"
    )
    recording_schedules: Mapped[list[RecordingSchedule]] = relationship(
        "RecordingSchedule", back_populates="camera", lazy="selectin"
    )
