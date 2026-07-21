"""Discovery engine data models — enums and dataclasses for auto-discovery results."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Any
from uuid import uuid4


class DiscoveryMethod(StrEnum):
    """Discovery method identifiers."""

    ONVIF = "onvif"
    RTSP = "rtsp"
    HTTP = "http"
    ARP = "arp"
    MDNS = "mdns"
    VENDOR_BROADCAST = "vendor_broadcast"
    MANUAL = "manual"


class DeviceVendor(StrEnum):
    """Known camera vendors."""

    HIKVISION = "hikvision"
    DAHUA = "dahua"
    AXIS = "axis"
    REOLINK = "reolink"
    TP_LINK = "tp_link"
    AMCREST = "amcrest"
    FOSCAM = "foscam"
    UNIVIEW = "uniview"
    BOSCH = "bosch"
    SAMSUNG_HANWHA = "samsung_hanwha"
    GENERIC_ONVIF = "generic_onvif"
    UNKNOWN = "unknown"


@dataclass
class StreamProfile:
    """A stream profile detected from camera."""

    name: str
    uri: str
    codec: str | None = None
    resolution: str | None = None
    fps: int | None = None
    bitrate_kbps: int | None = None
    is_main: bool = True


@dataclass
class DiscoveryResult:
    """Result from a single discovery method for one device."""

    ip_address: IPv4Address
    mac_address: str | None = None
    method: DiscoveryMethod = DiscoveryMethod.ONVIF
    vendor: DeviceVendor = DeviceVendor.UNKNOWN
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    serial_number: str | None = None

    # RTSP streams
    stream_main_uri: str | None = None
    stream_sub_uri: str | None = None
    stream_audio_uri: str | None = None
    streams: list[StreamProfile] = field(default_factory=list)

    # URLs
    http_url: str | None = None
    https_url: str | None = None

    # ONVIF service endpoints
    onvif_device_service_url: str | None = None
    onvif_media_service_url: str | None = None
    onvif_ptz_service_url: str | None = None
    onvif_events_service_url: str | None = None

    # Capabilities
    has_audio: bool = False
    has_talkback: bool = False
    has_ptz: bool = False
    has_onvif: bool = False
    has_motion_detection: bool = False
    has_io_ports: bool = False
    max_resolution: str | None = None

    # Confidence (0-100) per method
    confidence: int = 0

    # Raw data for debugging
    raw_data: dict[str, Any] = field(default_factory=dict)

    # Error info
    error: str | None = None

    # Timing
    discovered_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ip_address": str(self.ip_address),
            "mac_address": self.mac_address,
            "method": self.method.value,
            "vendor": self.vendor.value,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "serial_number": self.serial_number,
            "stream_main_uri": self.stream_main_uri,
            "stream_sub_uri": self.stream_sub_uri,
            "stream_audio_uri": self.stream_audio_uri,
            "http_url": self.http_url,
            "https_url": self.https_url,
            "onvif_device_service_url": self.onvif_device_service_url,
            "onvif_media_service_url": self.onvif_media_service_url,
            "onvif_ptz_service_url": self.onvif_ptz_service_url,
            "has_audio": self.has_audio,
            "has_talkback": self.has_talkback,
            "has_ptz": self.has_ptz,
            "has_onvif": self.has_onvif,
            "has_motion_detection": self.has_motion_detection,
            "has_io_ports": self.has_io_ports,
            "max_resolution": self.max_resolution,
            "confidence": self.confidence,
            "error": self.error,
        }


@dataclass
class MergedDevice:
    """Merged result from multiple discovery methods for the same physical device."""

    id: str = field(default_factory=lambda: str(uuid4()))
    ip_addresses: set[IPv4Address] = field(default_factory=set)
    mac_address: str | None = None
    vendor: DeviceVendor = DeviceVendor.UNKNOWN
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    serial_number: str | None = None

    # Merged stream profiles
    stream_main_uri: str | None = None
    stream_sub_uri: str | None = None
    stream_audio_uri: str | None = None
    streams: list[StreamProfile] = field(default_factory=list)

    # Best URLs
    http_url: str | None = None
    https_url: str | None = None

    # Best ONVIF endpoints
    onvif_device_service_url: str | None = None
    onvif_media_service_url: str | None = None
    onvif_ptz_service_url: str | None = None
    onvif_events_service_url: str | None = None

    # Merged capabilities (union)
    has_audio: bool = False
    has_talkback: bool = False
    has_ptz: bool = False
    has_onvif: bool = False
    has_motion_detection: bool = False
    has_io_ports: bool = False
    max_resolution: str | None = None

    # Overall confidence (weighted average of all sources)
    overall_confidence: int = 0

    # Discovery info
    discovery_methods: list[DiscoveryMethod] = field(default_factory=list)
    discovery_results: list[DiscoveryResult] = field(default_factory=list)

    # Known defaults from fingerprint
    default_username: str | None = None
    default_password_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "primary_ip": str(next(iter(self.ip_addresses))) if self.ip_addresses else None,
            "ip_addresses": [str(ip) for ip in self.ip_addresses],
            "mac_address": self.mac_address,
            "vendor": self.vendor.value,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "serial_number": self.serial_number,
            "stream_main_uri": self.stream_main_uri,
            "stream_sub_uri": self.stream_sub_uri,
            "stream_audio_uri": self.stream_audio_uri,
            "http_url": self.http_url,
            "https_url": self.https_url,
            "onvif_device_service_url": self.onvif_device_service_url,
            "onvif_media_service_url": self.onvif_media_service_url,
            "onvif_ptz_service_url": self.onvif_ptz_service_url,
            "has_audio": self.has_audio,
            "has_talkback": self.has_talkback,
            "has_ptz": self.has_ptz,
            "has_onvif": self.has_onvif,
            "has_motion_detection": self.has_motion_detection,
            "has_io_ports": self.has_io_ports,
            "max_resolution": self.max_resolution,
            "overall_confidence": self.overall_confidence,
            "discovery_methods": [m.value for m in self.discovery_methods],
            "default_username": self.default_username,
            "default_password_hint": self.default_password_hint,
        }
