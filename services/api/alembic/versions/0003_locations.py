"""add locations table + cameras.location_id FK.

Revision ID: 0003_locations
Revises: 0002_camera_connection_error
Create Date: 2026-07-22

"""

import sqlalchemy as sa
from alembic import op

revision: str = "0003_locations"
down_revision: str | None = "0002_camera_connection_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.func.uuid_generate_v4()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_locations_name"),
    )
    op.add_column("cameras", sa.Column("location_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_cameras_location_id",
        "cameras",
        "locations",
        ["location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_cameras_location", "cameras", ["location_id"])

    # Migrate existing free-text camera.location values into the locations table
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO locations (name)
            SELECT DISTINCT location FROM cameras
            WHERE location IS NOT NULL AND btrim(location) <> ''
            ON CONFLICT (name) DO NOTHING
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE cameras c SET location_id = l.id
            FROM locations l WHERE c.location = l.name
            """
        )
    )


def downgrade() -> None:
    op.drop_index("idx_cameras_location", table_name="cameras")
    op.drop_constraint("fk_cameras_location_id", "cameras", type_="foreignkey")
    op.drop_column("cameras", "location_id")
    op.drop_table("locations")
