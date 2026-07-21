"""Stream profile model — per-camera stream profiles (main, sub, third)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .camera import Camera


class StreamProfile(Base):
    __tablename__ = "stream_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    profile_name: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="video", server_default="video"
    )
    codec: Mapped[str | None] = mapped_column(String(20))
    resolution: Mapped[str | None] = mapped_column(String(20))
    fps: Mapped[int | None] = mapped_column(SmallInteger)
    bitrate_kbps: Mapped[int | None] = mapped_column(Integer)
    rtsp_uri: Mapped[str | None] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now, server_default=func.now()
    )

    camera: Mapped[Camera] = relationship("Camera", back_populates="stream_profiles")
