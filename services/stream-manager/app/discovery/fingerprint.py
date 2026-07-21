"""
Vendor Fingerprint Matching System.

Identifies camera vendors based on:
- MAC address OUI prefix
- RTSP URL path patterns
- HTTP server headers
- ONVIF manufacturer strings
- HTTP page title/content patterns
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .engine import DeviceVendor


class VendorFingerprinter:
    """Matches cameras to vendors using multi-source fingerprinting.

    Loads vendor patterns from YAML (initial) and/or database (runtime).
    """

    def __init__(self, patterns_path: str | None = None):
        self._patterns: dict[str, dict[str, Any]] = {}
        self._mac_to_vendor: dict[str, DeviceVendor] = {}
        self._header_to_vendor: list[tuple[re.Pattern, DeviceVendor]] = []
        self._rtsp_to_vendor: list[tuple[re.Pattern, DeviceVendor]] = []
        self._onvif_to_vendor: dict[str, DeviceVendor] = {}
        self._title_to_vendor: list[tuple[re.Pattern, DeviceVendor]] = []

        if patterns_path:
            self.load_patterns(patterns_path)

    def load_patterns(self, path: str) -> None:
        """Load vendor patterns from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        self._patterns = data

        for vendor_key, patterns in data.items():
            if vendor_key == "generic_onvif":
                continue

            # Map vendor key to enum
            try:
                vendor = DeviceVendor(vendor_key)
            except ValueError:
                continue

            # MAC prefixes → vendor lookup
            for mac_prefix in patterns.get("mac_prefixes", []):
                norm = mac_prefix.lower().replace(":", "").replace("-", "")
                self._mac_to_vendor[norm] = vendor

            # HTTP server header patterns → vendor
            for header in patterns.get("http_server_headers", []):
                self._header_to_vendor.append((re.compile(re.escape(header), re.IGNORECASE), vendor))

            # RTSP path patterns → vendor
            for rtsp_path in patterns.get("rtsp_paths", []):
                escaped = re.escape(rtsp_path)
                self._rtsp_to_vendor.append((re.compile(escaped), vendor))

            # ONVIF manufacturer strings → vendor
            for mfr in patterns.get("onvif_manufacturer", []):
                self._onvif_to_vendor[mfr.lower()] = vendor

            # HTTP title patterns → vendor
            for title in patterns.get("http_title_patterns", []):
                self._title_to_vendor.append(
                    (re.compile(re.escape(title), re.IGNORECASE), vendor)
                )

    def identify_from_mac(self, mac_address: str) -> DeviceVendor | None:
        """Identify vendor from MAC address OUI prefix.

        Args:
            mac_address: MAC address in any common format
                         (00:40:48:XX:XX:XX, 004048XXXXXX, 00-40-48-XX-XX-XX)

        Returns:
            DeviceVendor or None if no match.
        """
        norm = mac_address.lower().replace(":", "").replace("-", "").replace(".", "")
        vendor = self._mac_to_vendor.get(norm)  # exact (full match)
        if vendor:
            return vendor
        # Try OUI prefix match (first 6 chars)
        for oui_prefix, vendor in self._mac_to_vendor.items():
            if norm.startswith(oui_prefix):
                return vendor
        return None

    def identify_from_rtsp_url(self, url: str) -> DeviceVendor | None:
        """Identify vendor from RTSP URL path.

        Args:
            url: RTSP URL (e.g., rtsp://192.168.1.100:554/Streaming/Channels/101)

        Returns:
            DeviceVendor or None if no match.
        """
        for pattern, vendor in self._rtsp_to_vendor:
            if pattern.search(url):
                return vendor
        return None

    def identify_from_http_header(self, server_header: str) -> DeviceVendor | None:
        """Identify vendor from HTTP Server response header.

        Args:
            server_header: Value of the 'Server' HTTP header.

        Returns:
            DeviceVendor or None if no match.
        """
        for pattern, vendor in self._header_to_vendor:
            if pattern.search(server_header):
                return vendor
        return None

    def identify_from_http_title(self, html_content: str) -> DeviceVendor | None:
        """Identify vendor from HTML <title> tag content.

        Args:
            html_content: Raw HTML page content.

        Returns:
            DeviceVendor or None if no match.
        """
        # Extract title tag
        title_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        if not title_match:
            return None
        title = title_match.group(1).strip()

        for pattern, vendor in self._title_to_vendor:
            if pattern.search(title):
                return vendor
        return None

    def identify_from_onvif_manufacturer(self, manufacturer: str) -> DeviceVendor | None:
        """Identify vendor from ONVIF GetDeviceInformation manufacturer field.

        Args:
            manufacturer: Manufacturer string from ONVIF response.

        Returns:
            DeviceVendor or None if no match.
        """
        return self._onvif_to_vendor.get(manufacturer.lower())

    def get_vendor_defaults(self, vendor: DeviceVendor) -> dict[str, Any] | None:
        """Get default configuration for a known vendor.

        Returns dict with keys: default_ports, rtsp_paths, default_username,
        default_password, api_paths.
        """
        defaults: dict[str, Any] = {}
        vendor_data = self._patterns.get(vendor.value, {})

        if "default_ports" in vendor_data:
            defaults["default_ports"] = vendor_data["default_ports"]
        if "rtsp_paths" in vendor_data:
            defaults["rtsp_paths"] = vendor_data["rtsp_paths"]
        if "default_credentials" in vendor_data:
            creds = vendor_data["default_credentials"]
            defaults["default_username"] = creds.get("username", "admin")
            defaults["default_password"] = creds.get("password", "")
        if "api_paths" in vendor_data:
            defaults["api_paths"] = vendor_data["api_paths"]

        return defaults if defaults else None

    def get_rtsp_url_template(
        self,
        vendor: DeviceVendor,
        ip: str,
        port: int = 554,
        username: str = "admin",
        password: str = "",
        channel: int = 1,
        stream_type: int = 0,
    ) -> str | None:
        """Generate a probable RTSP URL for a specific vendor.

        Args:
            vendor: Camera vendor.
            ip: Camera IP address.
            port: RTSP port.
            username: RTSP username.
            password: RTSP password.
            channel: Channel number (1-based).
            stream_type: 0 = main, 1 = sub stream.

        Returns:
            RTSP URL string or None if vendor not recognized.
        """
        vendor_data = self._patterns.get(vendor.value, {})
        rtsp_paths = vendor_data.get("rtsp_paths", [])

        if not rtsp_paths:
            return None

        # Use first path as template
        path = rtsp_paths[0]

        # Replace channel/subtype placeholders for patterns like Dahua/Amcrest
        path = path.replace("channel=1", f"channel={channel}")
        path = path.replace("subtype=0", f"subtype={stream_type}")
        path = path.replace("subtype=1", f"subtype={stream_type}")

        # Replace h264/h265 if needed for Reolink-like patterns
        if "{codec}" in path:
            path = path.replace("{codec}", "h264")

        auth = f"{username}:{password}@" if username else ""

        return f"rtsp://{auth}{ip}:{port}{path}"

    def get_onvif_service_url(self, vendor: DeviceVendor, ip: str, port: int = 80) -> str | None:
        """Get the ONVIF device service URL for a known vendor.

        Different vendors use different ONVIF service paths.
        """
        vendor_data = self._patterns.get(vendor.value, {})

        # Common ONVIF paths
        vendor_paths = {
            DeviceVendor.HIKVISION: "/onvif/device_service",
            DeviceVendor.DAHUA: "/onvif/device_service",
            DeviceVendor.AXIS: "/onvif/device_service",
            DeviceVendor.REOLINK: "/onvif/device_service",
            DeviceVendor.TP_LINK: "/onvif/device_service",
            DeviceVendor.GENERIC_ONVIF: "/onvif/device_service",
        }

        path = vendor_paths.get(vendor, "/onvif/device_service")
        return f"http://{ip}:{port}{path}"

    @property
    def known_vendors(self) -> list[str]:
        """Return list of known vendor keys."""
        return list(self._patterns.keys())

    @property
    def mac_oui_count(self) -> int:
        """Number of MAC OUI prefixes in database."""
        return len(self._mac_to_vendor)
