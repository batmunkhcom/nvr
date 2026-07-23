"""add storage_backend_id to cameras

Revision ID: 0004_storage_backend_on_camera
Revises: 99ea062c5062
Create Date: 2025-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_storage_backend_on_camera"
down_revision: str | None = "99ea062c5062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column(
            "storage_backend_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_cameras_storage_backend_id",
        "cameras",
        "storage_backends",
        ["storage_backend_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_cameras_storage_backend_id", "cameras", type_="foreignkey")
    op.drop_column("cameras", "storage_backend_id")
