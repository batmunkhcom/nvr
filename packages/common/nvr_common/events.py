"""Camera discovery event schema constants."""

from enum import StrEnum


class DiscoveryPhase(StrEnum):
    ONVIF = "onvif"
    ARP = "arp"
    RTSP = "rtsp"
    HTTP = "http"
    VENDOR = "vendor"
    MDNS = "mdns"
    MERGE = "merge"
    COMPLETE = "complete"


class DiscoveryEventType(StrEnum):
    PHASE_START = "discovery.phase.start"
    PHASE_COMPLETE = "discovery.phase.complete"
    DEVICE_FOUND = "discovery.device.found"
    SCAN_COMPLETE = "discovery.scan.complete"
    ERROR = "discovery.error"
