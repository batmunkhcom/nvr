"""add ai_plugins, lpr_config to cameras; create object_counters, license_plates, smart_alerts tables

Revision ID: 0010_ai_plugins
Revises: 99ea063d5073
Create Date: 2026-07-26
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_ai_plugins"
down_revision: str | None = "99ea063d5073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── cameras: ai_plugins + lpr_config JSONB columns ──────────────────
    op.add_column(
        "cameras",
        sa.Column(
            "ai_plugins",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "cameras",
        sa.Column(
            "lpr_config",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text(
                """'{"enabled": false, "pattern": "mongolia", "custom_regex": null, "min_confidence": 0.75}'::jsonb"""
            ),
        ),
    )

    # ── object_counters table ───────────────────────────────────────────
    op.create_table(
        "object_counters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_category", sa.String(32), nullable=False),
        sa.Column("counter_date", sa.Date(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint(
        "uq_object_counters_camera_cat_date_hour",
        "object_counters",
        ["camera_id", "object_category", "counter_date", "hour"],
    )
    op.create_index(
        "idx_counters_camera_time",
        "object_counters",
        ["camera_id", sa.text("counter_date DESC")],
    )

    # ── license_plates table ────────────────────────────────────────────
    op.create_table(
        "license_plates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plate_number", sa.String(20), nullable=False),
        sa.Column("country_code", sa.String(3), nullable=True),
        sa.Column("pattern_name", sa.String(50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("snapshot_path", sa.Text(), nullable=True),
        sa.Column("plate_image_path", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_lpr_camera_time",
        "license_plates",
        ["camera_id", sa.text("detected_at DESC")],
    )
    op.create_index(
        "idx_lpr_plate_number",
        "license_plates",
        ["plate_number"],
    )

    # ── smart_alerts table ──────────────────────────────────────────────
    op.create_table(
        "smart_alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), server_default="warning", nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column("acknowledged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("snapshot_path", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_smart_alerts_camera_time",
        "smart_alerts",
        ["camera_id", sa.text("triggered_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_smart_alerts_camera_time", table_name="smart_alerts")
    op.drop_table("smart_alerts")

    op.drop_index("idx_lpr_plate_number", table_name="license_plates")
    op.drop_index("idx_lpr_camera_time", table_name="license_plates")
    op.drop_table("license_plates")

    op.drop_index("idx_counters_camera_time", table_name="object_counters")
    op.drop_constraint("uq_object_counters_camera_cat_date_hour", "object_counters")
    op.drop_table("object_counters")

    op.drop_column("cameras", "lpr_config")
    op.drop_column("cameras", "ai_plugins")
