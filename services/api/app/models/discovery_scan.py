"""Discovery scan model — scan sessions."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DiscoveryScan(Base):
    __tablename__ = "discovery_scans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running", server_default="running"
    )
    subnets: Mapped[list[str]] = mapped_column(ARRAY(INET), nullable=False)
    methods: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=["onvif", "rtsp", "http", "arp", "mdns", "vendor"],
        server_default="{onvif,rtsp,http,arp,mdns,vendor}",
    )
    progress_pct: Mapped[int | None] = mapped_column(SmallInteger, default=0, server_default="0")
    phases: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="'{}'")
    found_count: Mapped[int | None] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now, server_default=func.now()
    )
