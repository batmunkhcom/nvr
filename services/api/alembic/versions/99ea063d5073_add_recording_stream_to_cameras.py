"""Add recording_stream column to cameras (per-camera override for system recording.stream)

Revision ID: 99ea063d5073
Revises: 99ea062c5062
Create Date: 2026-07-26
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "99ea063d5073"
down_revision: str | None = "0008_performance_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column(
            "recording_stream",
            sa.String(20),
            nullable=True,
            server_default=None,
        ),
    )


def downgrade() -> None:
    op.drop_column("cameras", "recording_stream")
