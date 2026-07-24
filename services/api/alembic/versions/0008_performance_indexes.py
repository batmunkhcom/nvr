"""add performance indexes for events and recordings time-range queries

Revision ID: 0008_performance_indexes
Revises: 0007_network_monitoring
Create Date: 2026-07-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_performance_indexes"
down_revision: str | None = "0007_network_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_camera_time "
        "ON events (camera_id, start_time DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_time "
        "ON events (start_time DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recordings_camera_time "
        "ON recordings (camera_id, start_time DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_events_camera_time")
    op.execute("DROP INDEX IF EXISTS idx_events_time")
    op.execute("DROP INDEX IF EXISTS idx_recordings_camera_time")
