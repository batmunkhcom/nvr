"""
ARP Table Scanner — MAC-based vendor identification.

Reads the system ARP table to discover devices on the local network
and identifies camera vendors via MAC OUI lookup.
"""

from __future__ import annotations

from ipaddress import IPv4Address
from pathlib import Path

from .engine import DiscoveryResult, DiscoveryMethod, DeviceVendor
from .fingerprint import VendorFingerprinter


class ARPScanner:
    """Discover devices via ARP table analysis."""

    ARP_TABLE_PATH = Path("/proc/net/arp")

    def __init__(self):
        self.fingerprinter = VendorFingerprinter()

    async def scan(self) -> list[DiscoveryResult]:
        """Read ARP table and return discovered devices.

        Returns:
            List of DiscoveryResult for entries that match known camera vendors.
        """
        results: list[DiscoveryResult] = []

        try:
            entries = await self._read_arp_table()
            for ip, mac in entries.items():
                vendor = self.fingerprinter.identify_from_mac(mac)
                if vendor != DeviceVendor.UNKNOWN:
                    result = DiscoveryResult(
                        ip_address=IPv4Address(ip),
                        mac_address=mac,
                        method=DiscoveryMethod.ARP,
                        vendor=vendor,
                        confidence=40,  # Low confidence from ARP alone
                    )
                    results.append(result)
        except Exception:
            pass

        return results

    async def _read_arp_table(self) -> dict[str, str]:
        """Parse /proc/net/arp and return {ip: mac} mapping."""
        entries: dict[str, str] = {}

        if not self.ARP_TABLE_PATH.exists():
            return entries

        content = self.ARP_TABLE_PATH.read_text()
        for line in content.strip().split("\n")[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 4:
                ip = parts[0]
                mac = parts[3]
                if mac != "00:00:00:00:00:00" and ip.startswith(("192.", "10.", "172.")):
                    entries[ip] = mac

        return entries
