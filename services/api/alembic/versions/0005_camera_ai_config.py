"""add ai_enabled, ai_objects, ai_zones, ai_sensitivity, ai_min_confidence to cameras

Revision ID: 0005_camera_ai_config
Revises: 0004_storage_backend_on_camera
Create Date: 2025-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_camera_ai_config"
down_revision: str | None = "0004_storage_backend_on_camera"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column(
            "ai_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "cameras",
        sa.Column(
            "ai_objects",
            postgresql.JSON,
            nullable=True,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "cameras",
        sa.Column(
            "ai_zones",
            postgresql.JSON,
            nullable=True,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "cameras",
        sa.Column(
            "ai_sensitivity",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'medium'"),
        ),
    )
    op.add_column(
        "cameras",
        sa.Column(
            "ai_min_confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
    )


def downgrade() -> None:
    op.drop_column("cameras", "ai_min_confidence")
    op.drop_column("cameras", "ai_sensitivity")
    op.drop_column("cameras", "ai_zones")
    op.drop_column("cameras", "ai_objects")
    op.drop_column("cameras", "ai_enabled")
