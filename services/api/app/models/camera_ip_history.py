"""Camera IP history model — track IP address changes over time."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CameraIpHistory(Base):
    __tablename__ = "camera_ip_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    old_ip_address: Mapped[str | None] = mapped_column(INET)
    new_ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now, server_default=func.now()
    )
    change_source: Mapped[str | None] = mapped_column(
        String(50), default="auto", server_default="auto"
    )
