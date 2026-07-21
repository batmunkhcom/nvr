"""Recording schedule model — cron-like scheduling per camera."""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Time, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .camera import Camera


class RecordingSchedule(Base):
    __tablename__ = "recording_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    schedule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    days_of_week: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger),
        nullable=False,
        default=[1, 2, 3, 4, 5, 6, 7],
        server_default="{1,2,3,4,5,6,7}",
    )
    time_start: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(0, 0), server_default="00:00:00"
    )
    time_end: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(23, 59, 59), server_default="23:59:59"
    )
    pre_record_seconds: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=5, server_default="5"
    )
    post_record_seconds: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=10, server_default="10"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now, server_default=func.now()
    )

    camera: Mapped[Camera] = relationship("Camera", back_populates="recording_schedules")
