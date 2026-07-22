"""Storage tier model — hot/warm/cold retention policies."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StorageTier(Base):
    __tablename__ = "storage_tiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    backend_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_backends.id"), nullable=False
    )
    priority_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    applies_to_types: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=["continuous"], server_default="{continuous}"
    )
    min_free_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=10_737_418_240, server_default="10737418240"
    )
    max_used_percent: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=90, server_default="90"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
