"""System upgrade model — track upgrade and rollback operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SystemUpgrade(Base):
    __tablename__ = "system_upgrades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    from_version: Mapped[str] = mapped_column(String(20), nullable=False)
    to_version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_progress", server_default="in_progress"
    )
    checks_passed: Mapped[bool | None] = mapped_column(
        Boolean, default=False, server_default=func.false()
    )
    backup_path: Mapped[str | None] = mapped_column(String(512))
    rolled_back: Mapped[bool | None] = mapped_column(
        Boolean, default=False, server_default=func.false()
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    logs: Mapped[dict | None] = mapped_column(JSON, default=dict, server_default="'{}'")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
