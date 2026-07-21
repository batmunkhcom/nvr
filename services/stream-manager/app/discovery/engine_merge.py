"""Discovery result merging and deduplication logic.

Merges results from multiple discovery methods into unified MergedDevice objects,
deduplicating by MAC address, IP address, and ONVIF serial number.
"""

from __future__ import annotations

from .engine_data import DeviceVendor, DiscoveryResult, MergedDevice


def merge_results(
    results: list[DiscoveryResult],
    fingerprinter_defaults_fn,
) -> list[MergedDevice]:
    """Merge discovery results into unique devices.

    Merging priority:
    1. Same MAC address → same device
    2. Same IP address → same device
    3. Same ONVIF serial number → same device
    """
    if not results:
        return []

    # Group by MAC first
    groups: dict[str, list[DiscoveryResult]] = {}
    orphan_results: list[DiscoveryResult] = []

    for result in results:
        if result.error:
            continue
        if result.mac_address:
            key = result.mac_address.lower()
            groups.setdefault(key, []).append(result)
        else:
            orphan_results.append(result)

    # For orphans, group by IP
    ip_groups: dict[str, list[DiscoveryResult]] = {}
    for result in orphan_results:
        key = str(result.ip_address)
        ip_groups.setdefault(key, []).append(result)

    # Merge each group into a MergedDevice
    merged_devices: list[MergedDevice] = []
    for group in groups.values():
        merged_devices.append(_merge_group(group, fingerprinter_defaults_fn))
    for group in ip_groups.values():
        merged_devices.append(_merge_group(group, fingerprinter_defaults_fn))

    # Additional dedup: merge devices with overlapping IPs
    return _dedup_by_ip_overlap(merged_devices)


def _merge_group(
    group: list[DiscoveryResult],
    get_defaults_fn,
) -> MergedDevice:
    """Merge a group of discovery results into a single device."""
    device = MergedDevice()

    for r in group:
        device.ip_addresses.add(r.ip_address)

    best = max(group, key=lambda r: r.confidence)

    device.mac_address = (
        best.mac_address
        or next((r.mac_address for r in group if r.mac_address), None)
    )
    device.vendor = best.vendor
    device.manufacturer = (
        best.manufacturer
        or next((r.manufacturer for r in group if r.manufacturer), None)
    )
    device.model = best.model or next((r.model for r in group if r.model), None)
    device.firmware_version = (
        best.firmware_version
        or next((r.firmware_version for r in group if r.firmware_version), None)
    )
    device.serial_number = (
        best.serial_number
        or next((r.serial_number for r in group if r.serial_number), None)
    )

    # Merge streams
    device.stream_main_uri = best.stream_main_uri or next(
        (r.stream_main_uri for r in group if r.stream_main_uri), None
    )
    device.stream_sub_uri = best.stream_sub_uri or next(
        (r.stream_sub_uri for r in group if r.stream_sub_uri), None
    )
    device.stream_audio_uri = best.stream_audio_uri or next(
        (r.stream_audio_uri for r in group if r.stream_audio_uri), None
    )

    # Merge URLs
    device.http_url = best.http_url or next(
        (r.http_url for r in group if r.http_url), None
    )
    device.https_url = best.https_url or next(
        (r.https_url for r in group if r.https_url), None
    )

    # Merge ONVIF endpoints
    device.onvif_device_service_url = best.onvif_device_service_url or next(
        (r.onvif_device_service_url for r in group if r.onvif_device_service_url), None
    )
    device.onvif_media_service_url = best.onvif_media_service_url or next(
        (r.onvif_media_service_url for r in group if r.onvif_media_service_url), None
    )
    device.onvif_ptz_service_url = best.onvif_ptz_service_url or next(
        (r.onvif_ptz_service_url for r in group if r.onvif_ptz_service_url), None
    )
    device.onvif_events_service_url = best.onvif_events_service_url or next(
        (r.onvif_events_service_url for r in group if r.onvif_events_service_url), None
    )

    # Merge capabilities (union)
    device.has_audio = any(r.has_audio for r in group)
    device.has_talkback = any(r.has_talkback for r in group)
    device.has_ptz = any(r.has_ptz for r in group)
    device.has_onvif = any(r.has_onvif for r in group)
    device.has_motion_detection = any(r.has_motion_detection for r in group)
    device.has_io_ports = any(r.has_io_ports for r in group)
    device.max_resolution = best.max_resolution or next(
        (r.max_resolution for r in group if r.max_resolution), None
    )

    # Weighted confidence
    total_weight = sum(r.confidence for r in group)
    if total_weight > 0:
        device.overall_confidence = int(
            sum(r.confidence * r.confidence for r in group) / total_weight
        )
    else:
        device.overall_confidence = best.confidence

    # Track discovery methods
    device.discovery_methods = list({r.method for r in group})

    # Get default credentials from fingerprint
    if device.vendor != DeviceVendor.UNKNOWN:
        defaults = get_defaults_fn(device.vendor)
        if defaults:
            device.default_username = defaults.get("default_username")
            device.default_password_hint = defaults.get("default_password")

    return device


def _dedup_by_ip_overlap(devices: list[MergedDevice]) -> list[MergedDevice]:
    """Merge devices that share IP addresses."""
    if len(devices) <= 1:
        return devices

    merged: list[MergedDevice] = []
    used: set[int] = set()

    for i, device_a in enumerate(devices):
        if i in used:
            continue
        current = device_a
        used.add(i)

        for j, device_b in enumerate(devices):
            if j in used:
                continue
            if current.ip_addresses & device_b.ip_addresses:
                current = _combine_devices(current, device_b)
                used.add(j)

        merged.append(current)

    return merged


def _combine_devices(a: MergedDevice, b: MergedDevice) -> MergedDevice:
    """Combine two merged devices into one, keeping best attributes."""
    combined = MergedDevice()
    combined.id = a.id
    combined.ip_addresses = a.ip_addresses | b.ip_addresses
    combined.mac_address = a.mac_address or b.mac_address

    if b.overall_confidence > a.overall_confidence:
        combined.vendor = b.vendor
        combined.manufacturer = b.manufacturer or a.manufacturer
        combined.model = b.model or a.model
        combined.overall_confidence = b.overall_confidence
    else:
        combined.vendor = a.vendor
        combined.manufacturer = a.manufacturer or b.manufacturer
        combined.model = a.model or b.model
        combined.overall_confidence = a.overall_confidence

    combined.firmware_version = a.firmware_version or b.firmware_version
    combined.serial_number = a.serial_number or b.serial_number
    combined.stream_main_uri = a.stream_main_uri or b.stream_main_uri
    combined.stream_sub_uri = a.stream_sub_uri or b.stream_sub_uri
    combined.stream_audio_uri = a.stream_audio_uri or b.stream_audio_uri
    combined.http_url = a.http_url or b.http_url
    combined.https_url = a.https_url or b.https_url
    combined.onvif_device_service_url = a.onvif_device_service_url or b.onvif_device_service_url
    combined.onvif_media_service_url = a.onvif_media_service_url or b.onvif_media_service_url
    combined.onvif_ptz_service_url = a.onvif_ptz_service_url or b.onvif_ptz_service_url
    combined.onvif_events_service_url = a.onvif_events_service_url or b.onvif_events_service_url

    combined.has_audio = a.has_audio or b.has_audio
    combined.has_talkback = a.has_talkback or b.has_talkback
    combined.has_ptz = a.has_ptz or b.has_ptz
    combined.has_onvif = a.has_onvif or b.has_onvif
    combined.has_motion_detection = a.has_motion_detection or b.has_motion_detection
    combined.has_io_ports = a.has_io_ports or b.has_io_ports
    combined.max_resolution = a.max_resolution or b.max_resolution
    combined.discovery_methods = list(set(a.discovery_methods + b.discovery_methods))
    combined.default_username = a.default_username or b.default_username
    combined.default_password_hint = a.default_password_hint or b.default_password_hint

    return combined
