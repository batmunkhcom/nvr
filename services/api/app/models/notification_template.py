"""Notification template model — per-event Jinja2 templates."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_tpl: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="NVR Alert: {{event_type}}",
        server_default="'NVR Alert: {{event_type}}'",
    )
    body_tpl: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="Event: {{event_type}} at {{camera_name}} ({{timestamp}})",
        server_default="'Event: {{event_type}} at {{camera_name}} ({{timestamp}})'",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
