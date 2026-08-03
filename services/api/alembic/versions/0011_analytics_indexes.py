"""add covering index for analytics stored-size query

Revision ID: 0011_analytics_indexes
Revises: 0010_ai_plugins
Create Date: 2026-08-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_analytics_indexes"
down_revision: str | None = "0010_ai_plugins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recordings_camera_size "
        "ON recordings (camera_id) INCLUDE (file_size_bytes)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_recordings_camera_size")
