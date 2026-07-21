"""Initial schema — all 22 tables + TimescaleDB hypertables

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── enum creation helper ────────────────────────────────────────────────────

_enums = {
    "user_role": ("admin", "operator", "viewer"),
    "recording_mode": ("continuous", "motion", "scheduled"),
    "recording_type": ("continuous", "motion", "manual", "event"),
    "event_severity": ("info", "warning", "critical"),
    "storage_backend_type": ("local", "nfs", "smb", "s3"),
    "stream_transport": ("tcp", "udp", "http", "multicast"),
    "auth_type": ("basic", "digest", "onvif_token"),
    "camera_status": ("online", "offline", "degraded", "unknown"),
    "scan_status": ("running", "completed", "failed", "cancelled"),
    "discovery_phase": ("onvif", "arp", "rtsp", "http", "vendor", "mdns", "merge"),
}


def _create_enums(op_obj):
    for name, values in _enums.items():
        type_ = sa.Enum(*values, name=name)
        type_.create(op_obj.get_bind(), checkfirst=True)


def _drop_enums(op_obj):
    for name in _enums:
        op_obj.execute(sa.text(f"DROP TYPE IF EXISTS {name}"))


def upgrade() -> None:
    # ── extensions ──────────────────────────────────────────────────────
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

    # ── enums ───────────────────────────────────────────────────────────
    # Pre-create all enum types via DO block (PG16 doesn't support IF NOT EXISTS for CREATE TYPE).
    for name, values in _enums.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(sa.text(f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({vals}); EXCEPTION WHEN duplicate_object THEN NULL; END $$"))

    # ── system_config ───────────────────────────────────────────────────
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("description", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # ── users ───────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(255)),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(name="user_role", create_type=False),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_users_username", "users", ["username"])
    op.create_index("idx_users_role", "users", ["role"])

    # ── api_keys ────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column(
            "permissions", sa.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{read}'")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_api_keys_user", "api_keys", ["user_id"])
    op.create_unique_index("idx_api_keys_hash", "api_keys", ["key_hash"])
    op.create_index("idx_api_keys_prefix", "api_keys", ["key_prefix"])

    # ── cameras ─────────────────────────────────────────────────────────
    op.create_table(
        "cameras",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("ip_address", sa.dialects.postgresql.INET(), nullable=False),
        sa.Column("mac_address", sa.dialects.postgresql.MACADDR()),
        sa.Column("manufacturer", sa.String(100)),
        sa.Column("model", sa.String(255)),
        sa.Column("firmware_version", sa.String(50)),
        sa.Column("serial_number", sa.String(100)),
        sa.Column("stream_main_uri", sa.String(1024)),
        sa.Column("stream_sub_uri", sa.String(1024)),
        sa.Column("stream_audio_uri", sa.String(1024)),
        sa.Column(
            "auth_type",
            sa.Enum(name="auth_type", create_type=False),
            nullable=False,
            server_default="basic",
        ),
        sa.Column("username", sa.String(100), nullable=False, server_default="admin"),
        sa.Column("encrypted_password", sa.Text()),
        sa.Column("has_audio", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_talkback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_ptz", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_onvif", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "has_motion_detection", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("has_io_ports", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "onvif_motion_supported", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("motion_source", sa.String(20), server_default="server"),
        sa.Column("max_resolution", sa.String(20)),
        sa.Column("onvif_device_service_url", sa.String(1024)),
        sa.Column("onvif_media_service_url", sa.String(1024)),
        sa.Column("onvif_ptz_service_url", sa.String(1024)),
        sa.Column("onvif_events_service_url", sa.String(1024)),
        sa.Column(
            "recording_mode",
            sa.Enum(name="recording_mode", create_type=False),
            nullable=False,
            server_default="continuous",
        ),
        sa.Column(
            "stream_transport",
            sa.Enum(name="stream_transport", create_type=False),
            nullable=False,
            server_default="tcp",
        ),
        sa.Column("pre_record_seconds", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("post_record_seconds", sa.SmallInteger(), nullable=False, server_default="10"),
        sa.Column("preferred_ip", sa.dialects.postgresql.INET()),
        sa.Column("ip_binding", sa.String(20), server_default="dynamic"),
        sa.Column("network_interface", sa.String(50)),
        sa.Column("privacy_mode", sa.String(20), server_default="none"),
        sa.Column("ptz_presets", sa.JSON(), server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "status",
            sa.Enum(name="camera_status", create_type=False),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_discovery_at", sa.DateTime(timezone=True)),
        sa.Column("time_synced_at", sa.DateTime(timezone=True)),
        sa.Column("discovery_source", sa.String(50)),
        sa.Column("discovery_confidence", sa.SmallInteger(), server_default="0"),
        sa.Column("tags", sa.ARRAY(sa.Text())),
        sa.Column("location", sa.String(255)),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_cameras_ip", "cameras", ["ip_address"])
    op.create_index("idx_cameras_mac", "cameras", ["mac_address"])
    op.create_index("idx_cameras_status", "cameras", ["status"])
    op.create_index("idx_cameras_name", "cameras", ["name"])
    op.create_index("idx_cameras_manufacturer", "cameras", ["manufacturer"])
    op.create_index(
        "idx_cameras_recording",
        "cameras",
        ["recording_mode"],
        postgresql_where=sa.text("status = 'online'"),
    )

    # ── stream_profiles ─────────────────────────────────────────────────
    op.create_table(
        "stream_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "camera_id", sa.Uuid(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("profile_name", sa.String(50), nullable=False),
        sa.Column("profile_type", sa.String(20), nullable=False, server_default="video"),
        sa.Column("codec", sa.String(20)),
        sa.Column("resolution", sa.String(20)),
        sa.Column("fps", sa.SmallInteger()),
        sa.Column("bitrate_kbps", sa.Integer()),
        sa.Column("rtsp_uri", sa.String(1024)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("camera_id", "profile_name"),
    )
    op.create_index("idx_stream_profiles_camera", "stream_profiles", ["camera_id"])

    # ── recording_schedules ─────────────────────────────────────────────
    op.create_table(
        "recording_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "camera_id", sa.Uuid(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("schedule_name", sa.String(100), nullable=False),
        sa.Column(
            "schedule_type",
            sa.Enum(name="recording_mode", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "days_of_week",
            sa.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default=sa.text("'{1,2,3,4,5,6,7}'"),
        ),
        sa.Column("time_start", sa.Time(), nullable=False, server_default=sa.text("'00:00:00'")),
        sa.Column("time_end", sa.Time(), nullable=False, server_default=sa.text("'23:59:59'")),
        sa.Column("pre_record_seconds", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("post_record_seconds", sa.SmallInteger(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_schedules_camera", "recording_schedules", ["camera_id"])
    op.create_index(
        "idx_schedules_active",
        "recording_schedules",
        ["is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ── discovery_scans ─────────────────────────────────────────────────
    op.create_table(
        "discovery_scans",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "status",
            sa.Enum(name="scan_status", create_type=False),
            nullable=False,
            server_default="running",
        ),
        sa.Column("subnets", sa.ARRAY(sa.dialects.postgresql.INET()), nullable=False),
        sa.Column(
            "methods",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{onvif,rtsp,http,arp,mdns,vendor}'"),
        ),
        sa.Column("progress_pct", sa.SmallInteger(), server_default="0"),
        sa.Column("phases", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("found_count", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_discovery_scans_status", "discovery_scans", ["status"])

    # ── discovery_log ───────────────────────────────────────────────────
    op.create_table(
        "discovery_log",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("scan_id", sa.Uuid(), sa.ForeignKey("discovery_scans.id"), nullable=False),
        sa.Column("ip_address", sa.dialects.postgresql.INET(), nullable=False),
        sa.Column("mac_address", sa.dialects.postgresql.MACADDR()),
        sa.Column("discovery_method", sa.String(50), nullable=False),
        sa.Column("result_status", sa.String(20), nullable=False),
        sa.Column("manufacturer_detected", sa.String(100)),
        sa.Column("raw_response", sa.JSON()),
        sa.Column("confidence", sa.SmallInteger(), server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_discovery_log_scan", "discovery_log", ["scan_id"])

    # ── storage_backends ────────────────────────────────────────────────
    op.create_table(
        "storage_backends",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "backend_type",
            sa.Enum(name="storage_backend_type", create_type=False),
            nullable=False,
        ),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("mount_point", sa.String(512)),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("available_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("health_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("last_health_check", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_storage_type", "storage_backends", ["backend_type"])
    op.create_index("idx_storage_active", "storage_backends", ["is_active", "priority"])

    # ── storage_tiers ───────────────────────────────────────────────────
    op.create_table(
        "storage_tiers",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("backend_id", sa.Uuid(), sa.ForeignKey("storage_backends.id"), nullable=False),
        sa.Column("priority_level", sa.SmallInteger(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column(
            "applies_to_types",
            sa.ARRAY(sa.Enum(name="recording_type", create_type=False)),
            nullable=False,
            server_default=sa.text("'{continuous}'"),
        ),
        sa.Column("min_free_bytes", sa.BigInteger(), nullable=False, server_default="10737418240"),
        sa.Column("max_used_percent", sa.SmallInteger(), nullable=False, server_default="90"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("backend_id", "priority_level"),
    )

    # ── recordings (hypertable) ─────────────────────────────────────────
    op.create_table(
        "recordings",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("camera_id", sa.Uuid(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("storage_backend_id", sa.Uuid(), sa.ForeignKey("storage_backends.id")),
        sa.Column("file_path", sa.String(2048), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recording_type",
            sa.Enum(name="recording_type", create_type=False),
            nullable=False,
            server_default="continuous",
        ),
        sa.Column("has_audio", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolution", sa.String(20)),
        sa.Column("codec", sa.String(20)),
        sa.Column("bitrate_kbps", sa.Integer()),
        sa.Column("event_id", sa.Uuid()),
        sa.Column("retention_override_days", sa.Integer()),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("is_corrupt", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", "start_time"),
    )
    op.create_unique_index("idx_recordings_id_unique", "recordings", ["id"])
    op.execute(
        sa.text(
            "SELECT create_hypertable('recordings', 'start_time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
        )
    )
    op.create_index(
        "idx_recordings_camera_time", "recordings", ["camera_id", sa.text("start_time DESC")]
    )
    op.create_index(
        "idx_recordings_type", "recordings", ["recording_type", sa.text("start_time DESC")]
    )
    op.create_index(
        "idx_recordings_event",
        "recordings",
        ["event_id"],
        postgresql_where=sa.text("event_id IS NOT NULL"),
    )
    op.create_index("idx_recordings_storage", "recordings", ["storage_backend_id"])
    op.create_index("idx_recordings_created", "recordings", [sa.text("created_at DESC")])

    # ── storage_migrations ──────────────────────────────────────────────
    op.create_table(
        "storage_migrations",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("recording_id", sa.Uuid(), sa.ForeignKey("recordings.id"), nullable=False),
        sa.Column(
            "from_backend_id", sa.Uuid(), sa.ForeignKey("storage_backends.id"), nullable=False
        ),
        sa.Column("to_backend_id", sa.Uuid(), sa.ForeignKey("storage_backends.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("source_path", sa.String(2048), nullable=False),
        sa.Column("dest_path", sa.String(2048), nullable=False),
        sa.Column("checksum_source", sa.String(64)),
        sa.Column("checksum_dest", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_storage_migrations_status", "storage_migrations", ["status"])
    op.create_index("idx_storage_migrations_recording", "storage_migrations", ["recording_id"])
    op.create_index("idx_storage_migrations_from", "storage_migrations", ["from_backend_id"])
    op.create_index("idx_storage_migrations_to", "storage_migrations", ["to_backend_id"])

    # ── events (hypertable) ─────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("camera_id", sa.Uuid(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(name="event_severity", create_type=False),
            nullable=False,
            server_default="info",
        ),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True)),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("snapshot_path", sa.String(2048)),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("acknowledged_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", "created_at"),
    )
    op.create_unique_index("idx_events_id_unique", "events", ["id"])
    op.execute(
        sa.text(
            "SELECT create_hypertable('events', 'created_at', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
        )
    )
    op.create_index("idx_events_camera_time", "events", ["camera_id", sa.text("created_at DESC")])
    op.create_index("idx_events_type", "events", ["event_type", sa.text("created_at DESC")])
    op.create_index("idx_events_severity", "events", ["severity", sa.text("created_at DESC")])
    op.create_index("idx_events_start_time", "events", [sa.text("start_time DESC")])

    # ── event_rules ─────────────────────────────────────────────────────
    op.create_table(
        "event_rules",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("camera_id", sa.Uuid(), sa.ForeignKey("cameras.id", ondelete="CASCADE")),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("actions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column(
            "audio_config",
            sa.JSON(),
            server_default=sa.text('\'{"min_db":80,"duration_seconds":3}\''),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_event_rules_camera", "event_rules", ["camera_id"])
    op.create_index(
        "idx_event_rules_active",
        "event_rules",
        ["is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ── notifications ───────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # ── notification_templates ──────────────────────────────────────────
    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "notification_id",
            sa.Uuid(),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "subject_tpl",
            sa.String(500),
            nullable=False,
            server_default=sa.text("'NVR Alert: {{event_type}}'"),
        ),
        sa.Column(
            "body_tpl",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'Event: {{event_type}} at {{camera_name}} ({{timestamp}})'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # ── alert_log ───────────────────────────────────────────────────────
    op.create_table(
        "alert_log",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("notification_id", sa.Uuid(), sa.ForeignKey("notifications.id"), nullable=False),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("delivery_status", sa.String(20), nullable=False, server_default="sent"),
        sa.Column("error_message", sa.Text()),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.create_index("idx_alert_log_event", "alert_log", ["event_id"])
    op.create_index("idx_alert_log_notification", "alert_log", ["notification_id"])

    # ── audit_log (hypertable) ──────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("details", sa.JSON()),
        sa.Column("ip_address", sa.dialects.postgresql.INET()),
        sa.Column("user_agent", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        sa.text(
            "SELECT create_hypertable('audit_log', 'created_at', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
        )
    )
    op.create_index("idx_audit_user", "audit_log", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_audit_action", "audit_log", ["action", sa.text("created_at DESC")])

    # ── camera_ip_history ───────────────────────────────────────────────
    op.create_table(
        "camera_ip_history",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "camera_id", sa.Uuid(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("old_ip_address", sa.dialects.postgresql.INET()),
        sa.Column("new_ip_address", sa.dialects.postgresql.INET(), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("change_source", sa.String(50), server_default="auto"),
    )
    op.create_index("idx_camera_ip_history_camera", "camera_ip_history", ["camera_id"])

    # ── system_upgrades ─────────────────────────────────────────────────
    op.create_table(
        "system_upgrades",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("from_version", sa.String(20), nullable=False),
        sa.Column("to_version", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("checks_passed", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("backup_path", sa.String(512)),
        sa.Column("rolled_back", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("error_message", sa.Text()),
        sa.Column("logs", sa.JSON(), server_default=sa.text("'{}'")),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # ── audio_levels (hypertable) ───────────────────────────────────────
    op.create_table(
        "audio_levels",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column(
            "camera_id", sa.Uuid(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("decibel", sa.Float(), nullable=False),
        sa.Column("rms", sa.Float()),
        sa.Column("detected_class", sa.String(50)),
        sa.Column("confidence", sa.Float()),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        sa.text(
            "SELECT create_hypertable('audio_levels', 'recorded_at', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
        )
    )
    op.create_index(
        "idx_audio_levels_camera_time", "audio_levels", ["camera_id", sa.text("recorded_at DESC")]
    )


def downgrade() -> None:
    # Drop hypertables
    op.execute(sa.text("SELECT drop_chunks('audio_levels', older_than => INTERVAL '0 seconds')"))
    op.drop_table("audio_levels")

    op.drop_table("system_upgrades")

    op.drop_table("camera_ip_history")

    op.execute(sa.text("SELECT drop_chunks('audit_log', older_than => INTERVAL '0 seconds')"))
    op.drop_table("audit_log")

    op.drop_table("alert_log")

    op.drop_table("notification_templates")

    op.drop_table("notifications")

    op.drop_table("event_rules")

    op.execute(sa.text("SELECT drop_chunks('events', older_than => INTERVAL '0 seconds')"))
    op.drop_table("events")

    op.drop_table("storage_migrations")

    op.execute(sa.text("SELECT drop_chunks('recordings', older_than => INTERVAL '0 seconds')"))
    op.drop_table("recordings")

    op.drop_table("storage_tiers")

    op.drop_table("storage_backends")

    op.drop_table("discovery_log")

    op.drop_table("discovery_scans")

    op.drop_table("recording_schedules")

    op.drop_table("stream_profiles")

    op.drop_table("cameras")

    op.drop_table("api_keys")

    op.drop_table("users")

    op.drop_table("system_config")

    # Drop enums
    _drop_enums(op)

    # Extensions kept (no drop — they may be used by other DBs)
