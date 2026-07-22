"""add cameras.connection_error — last connection test error message.

Revision ID: 0002_camera_connection_error
Revises: 0001_initial
Create Date: 2026-07-22

"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002_camera_connection_error"
down_revision: str | None = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("connection_error", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "connection_error")
