"""Camera Pydantic schemas."""

from pydantic import BaseModel, Field


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ip_address: str
    username: str = "admin"
    password: str | None = None
    auth_type: str = "basic"
    stream_main_uri: str | None = None
    stream_sub_uri: str | None = None
    stream_audio_uri: str | None = None
    recording_mode: str = "continuous"
    stream_transport: str = "tcp"
    tags: list[str] | None = None
    location: str | None = None
    location_id: str | None = None
    notes: str | None = None


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    ip_address: str | None = None
    username: str | None = None
    password: str | None = None
    auth_type: str | None = None
    stream_main_uri: str | None = None
    stream_sub_uri: str | None = None
    stream_audio_uri: str | None = None
    recording_mode: str | None = None
    stream_transport: str | None = None
    is_active: bool | None = None
    tags: list[str] | None = None
    location: str | None = None
    location_id: str | None = None
    notes: str | None = None
    privacy_mode: str | None = None


class CameraResponse(BaseModel):
    id: str
    name: str
    ip_address: str
    mac_address: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    serial_number: str | None = None
    stream_main_uri: str | None = None
    stream_sub_uri: str | None = None
    stream_audio_uri: str | None = None
    auth_type: str
    username: str
    has_audio: bool
    has_talkback: bool
    has_ptz: bool
    has_onvif: bool
    has_motion_detection: bool
    has_io_ports: bool
    motion_source: str | None = None
    max_resolution: str | None = None
    recording_mode: str
    stream_transport: str
    ptz_presets: list | None = None
    status: str
    connection_error: str | None = None
    last_seen_at: str | None = None
    tags: list[str] | None = None
    location: str | None = None
    location_id: str | None = None
    location_name: str | None = None
    notes: str | None = None
    privacy_mode: str | None = None
    created_at: str
    updated_at: str


class DiscoveryRequest(BaseModel):
    subnets: list[str] = ["192.168.1.0/24"]
    methods: list[str] | None = None
    timeout: int = Field(default=120, ge=10, le=600)


class ProbeRequest(BaseModel):
    ip_address: str


class ProbeResponse(BaseModel):
    reachable: bool
    ip: str
    open_ports: list[int]
    manufacturer: str | None = None
    model: str | None = None
    server_header: str | None = None
    http_title: str | None = None
    stream_main_uri: str | None = None
    has_rtsp: bool = False
    has_http: bool = False
    has_audio: bool = False
    has_ptz: bool = False
    has_onvif: bool = False
    has_motion_detection: bool = False


class DiscoveryStatusResponse(BaseModel):
    scan_id: str
    status: str
    phases: dict
    found_count: int
    progress_pct: int
    scanned_ips: int = 0
    total_ips: int = 0


class DiscoveredDevice(BaseModel):
    ip_address: str
    manufacturer: str | None = None
    model: str | None = None
    http_title: str | None = None
    stream_main_uri: str | None = None
    open_ports: list[int] = []
    has_rtsp: bool = False
    has_http: bool = False
    has_audio: bool = False
    has_ptz: bool = False
    has_onvif: bool = False
    has_motion_detection: bool = False
    confidence: int = 0


class CameraTestResponse(BaseModel):
    reachable: bool
    rtsp_ok: bool
    auth_ok: bool = False
    error_code: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    stream_resolution: str | None = None
    stream_codec: str | None = None
    manufacturer: str | None = None
    open_ports: list[int] = []
