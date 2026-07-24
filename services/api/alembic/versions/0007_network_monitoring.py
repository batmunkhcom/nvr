"""add network monitoring tables (network_metrics, camera_network_config, network_alerts)

Revision ID: 0007_network_monitoring
Revises: 0006_location_color
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_network_monitoring"
down_revision: str | None = "0006_location_color"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. network_metrics table (time-series)
    op.create_table(
        "network_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        # Bandwidth (Mbps)
        sa.Column("inbound_mbps", sa.Numeric(10, 2)),
        sa.Column("outbound_mbps", sa.Numeric(10, 2)),

        # Latency (ms)
        sa.Column("rtt_ms", sa.Numeric(8, 2)),
        sa.Column("jitter_ms", sa.Numeric(8, 2)),
        sa.Column("rtsp_latency", sa.Numeric(8, 2)),

        # Packet stats
        sa.Column("packets_sent", sa.BIGINT),
        sa.Column("packets_recv", sa.BIGINT),
        sa.Column("packet_loss_pct", sa.Numeric(5, 2)),

        # Connection quality
        sa.Column("fps_current", sa.Integer()),
        sa.Column("bitrate_current", sa.Numeric(10, 2)),
        sa.Column("rtsp_reconnect_cnt", sa.Integer(), server_default=sa.text("0")),

        # FFmpeg process metrics
        sa.Column("ffmpeg_pid", sa.Integer()),
        sa.Column("ffmpeg_cpu", sa.Numeric(5, 2)),
        sa.Column("ffmpeg_memory_mb", sa.Numeric(8, 2)),

        # Status
        sa.Column("status", sa.String(20), server_default=sa.text("'unknown'")),
        sa.Column("error_message", sa.Text()),
    )

    # Hypertable if TimescaleDB available (must run outside alembic transaction)
    bind_conn = op.get_bind()
    result = bind_conn.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")).first()
    if result:
        try:
            raw_conn = bind_conn.connection.unwrap()
            with raw_conn.cursor() as cur:
                cur.execute("SELECT create_hypertable('network_metrics', 'recorded_at', if_not_exists => TRUE)")
            raw_conn.commit()
        except Exception:
            # TimescaleDB available but create_hypertable failed - continue as regular table
            pass

    # Indexes for network_metrics
    op.create_index("idx_network_metrics_camera_time", "network_metrics", ["camera_id", sa.text("recorded_at DESC")])
    op.create_index("idx_network_metrics_time", "network_metrics", [sa.text("recorded_at DESC")])
    try:
        bind_conn.execute(sa.text(
            "CREATE INDEX idx_network_metrics_status ON network_metrics (status, recorded_at DESC) WHERE status != 'online'"
        ))
        bind_conn.commit()
    except Exception:
        pass

    # 2. camera_network_config table (per-camera settings)
    op.create_table(
        "camera_network_config",
        sa.Column("camera_id", sa.UUID(as_uuid=True), sa.ForeignKey("cameras.id"), primary_key=True),
        sa.Column("poll_interval", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("ping_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ping_count", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("ping_timeout", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("rtsp_check_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("bandwidth_warn_mbps", sa.Numeric(8, 2), server_default=sa.text("10.0")),
        sa.Column("bandwidth_crit_mbps", sa.Numeric(8, 2), server_default=sa.text("5.0")),
        sa.Column("latency_warn_ms", sa.Numeric(8, 2), server_default=sa.text("100")),
        sa.Column("latency_crit_ms", sa.Numeric(8, 2), server_default=sa.text("300")),
        sa.Column("packet_loss_warn_pct", sa.Numeric(5, 2), server_default=sa.text("1.0")),
        sa.Column("packet_loss_crit_pct", sa.Numeric(5, 2), server_default=sa.text("5.0")),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default=sa.text("90")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Seed with all existing cameras
    op.execute(
        "INSERT INTO camera_network_config (camera_id) SELECT id FROM cameras ON CONFLICT (camera_id) DO NOTHING"
    )

    # 3. network_alerts table
    op.create_table(
        "network_alerts",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("camera_id", sa.UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("event_id", sa.UUID(as_uuid=True)),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", sa.JSON()),
        sa.Column("location", sa.String(255)),
        sa.CheckConstraint("severity IN ('warning', 'critical')", name="chk_network_alert_severity"),
    )

    # Indexes for network_alerts
    op.create_index("idx_network_alerts_camera_time", "network_alerts", ["camera_id", sa.text("triggered_at DESC")])
    try:
        bind_conn.execute(sa.text(
            "CREATE INDEX idx_network_alerts_unack ON network_alerts (triggered_at DESC) WHERE acknowledged_at IS NULL AND resolved_at IS NULL"
        ))
        bind_conn.commit()
    except Exception:
        pass
    op.create_index("idx_network_alerts_type", "network_alerts", ["alert_type", sa.text("triggered_at DESC")])


def downgrade() -> None:
    # Drop in reverse order (alerts -> config -> metrics)
    op.drop_index("idx_network_alerts_type", table_name="network_alerts")
    op.drop_index("idx_network_alerts_unack", table_name="network_alerts")
    op.drop_index("idx_network_alerts_camera_time", table_name="network_alerts")
    op.drop_table("network_alerts")

    op.drop_index("idx_network_metrics_status", table_name="network_metrics")
    op.drop_index("idx_network_metrics_time", table_name="network_metrics")
    op.drop_index("idx_network_metrics_camera_time", table_name="network_metrics")
    op.drop_table("network_metrics")

    op.drop_table("camera_network_config")
