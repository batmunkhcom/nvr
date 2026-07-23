"""add_display_order_to_cameras

Revision ID: 99ea062c5062
Revises: 0003_locations
Create Date: 2026-07-23 07:48:13.240698
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "99ea062c5062"
down_revision: str | None = "0003_locations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cameras", sa.Column("display_order", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("cameras", "display_order")
