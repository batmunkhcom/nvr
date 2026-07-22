"""Storage migration model — track tier migration operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StorageMigration(Base):
    __tablename__ = "storage_migrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recordings.id"), nullable=False
    )
    from_backend_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_backends.id"), nullable=False
    )
    to_backend_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_backends.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    dest_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    checksum_source: Mapped[str | None] = mapped_column(String(64))
    checksum_dest: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
