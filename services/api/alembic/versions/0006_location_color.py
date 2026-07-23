"""add color column to locations

Revision ID: 0006_location_color
Revises: 0005_camera_ai_config
Create Date: 2025-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_location_color"
down_revision: str | None = "0005_camera_ai_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "locations",
        sa.Column(
            "color",
            sa.String(7),
            nullable=False,
            server_default=sa.text("'#3b82f6'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("locations", "color")
