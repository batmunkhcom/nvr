"""Prometheus metrics for the NVR system."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# API metrics
api_request_count = Counter(
    "nvr_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)
api_request_duration = Histogram(
    "nvr_api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

# Camera metrics
camera_online = Gauge(
    "nvr_camera_online",
    "Camera online status (1=online, 0=offline)",
    ["camera_id", "camera_name"],
)
camera_ffmpeg_processes = Gauge(
    "nvr_ffmpeg_process_count",
    "Number of active FFmpeg processes",
)
camera_fps = Gauge(
    "nvr_camera_fps",
    "Current frames per second",
    ["camera_id"],
)

# Recording metrics
recording_bytes_written = Counter(
    "nvr_recording_bytes_written_total",
    "Total bytes written to storage",
    ["storage_backend"],
)
recording_segment_count = Counter(
    "nvr_recording_segment_count_total",
    "Total recording segments created",
    ["recording_type"],
)
recording_errors = Counter(
    "nvr_recording_errors_total",
    "Total recording errors",
    ["error_type"],
)
active_recordings = Gauge(
    "nvr_active_recordings",
    "Number of cameras currently recording",
)

# Storage metrics
storage_free_bytes = Gauge(
    "nvr_storage_free_bytes",
    "Free storage bytes",
    ["backend", "backend_type"],
)
storage_total_bytes = Gauge(
    "nvr_storage_total_bytes",
    "Total storage bytes",
    ["backend", "backend_type"],
)
storage_used_pct = Gauge(
    "nvr_storage_used_percent",
    "Storage used percentage",
    ["backend"],
)

# AI metrics
ai_inference_duration = Histogram(
    "nvr_ai_inference_duration_seconds",
    "AI inference duration in seconds",
    ["model", "camera_id"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
ai_detection_count = Counter(
    "nvr_ai_detection_count_total",
    "Total AI detections",
    ["camera_id", "object_class"],
)
ai_inference_errors = Counter(
    "nvr_ai_inference_errors_total",
    "Total AI inference errors",
    ["error_type"],
)

# Events metrics
event_count = Counter(
    "nvr_event_count_total",
    "Total events triggered",
    ["camera_id", "event_type", "severity"],
)
event_rules_active = Gauge(
    "nvr_event_rules_active",
    "Number of active event rules",
)

# System metrics
circuit_breaker_trips = Counter(
    "nvr_circuit_breaker_trips_total",
    "Total circuit breaker trips",
    ["component", "breaker_name"],
)
db_connection_pool = Gauge(
    "nvr_db_connection_pool_size",
    "Database connection pool status",
    ["state"],
)


def get_metrics_text() -> str:
    """Generate Prometheus text format metrics."""
    return generate_latest().decode("utf-8")
