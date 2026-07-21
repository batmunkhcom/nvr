"""
Camera Auto-Discovery Engine — Smart Multi-Vendor Scanner.

Orchestrates multiple discovery methods to find and identify IP cameras
on the network with confidence scoring and vendor fingerprinting.
"""

from __future__ import annotations

import asyncio
from ipaddress import IPv4Address, IPv4Network
from uuid import uuid4

import structlog

from .arp_scanner import ARPScanner
from .engine_data import DeviceVendor, DiscoveryMethod, DiscoveryResult, MergedDevice
from .engine_merge import merge_results
from .fingerprint import VendorFingerprinter
from .http_scanner import HTTPScanner
from .mdns_scanner import MDNSScanner
from .onvif_scanner import ONVIFScanner
from .rtsp_scanner import RTSPscanner
from .vendor_scanner import VendorScanner

logger = structlog.get_logger()


class DiscoveryEngine:
    """Orchestrates multi-method camera discovery with result merging.

    Runs discovery methods in this order:
    1. ONVIF WS-Discovery (most reliable)
    2. ARP table + MAC OUI lookup
    3. Subnet IP scan → RTSP port probe
    4. HTTP scan with header analysis
    5. Vendor-specific UDP broadcast
    6. mDNS/Avahi query

    Results are deduplicated by MAC address (or IP fallback) and merged
    with confidence scoring.
    """

    def __init__(
        self,
        subnets: list[str] | None = None,
        onvif_timeout: int = 30,
        scan_timeout: int = 10,
        max_concurrent_scans: int = 50,
        vendor_patterns_path: str | None = None,
    ):
        self.subnets = [IPv4Network(s) for s in subnets] if subnets else []
        self.onvif_timeout = onvif_timeout
        self.scan_timeout = scan_timeout
        self.max_concurrent_scans = max_concurrent_scans

        self.onvif_scanner = ONVIFScanner(timeout=onvif_timeout)
        self.rtsp_scanner = RTSPscanner(timeout=scan_timeout)
        self.http_scanner = HTTPScanner(timeout=scan_timeout)
        self.arp_scanner = ARPScanner()
        self.mdns_scanner = MDNSScanner(timeout=scan_timeout)
        self.vendor_scanner = VendorScanner(timeout=scan_timeout)
        self.fingerprinter = VendorFingerprinter(patterns_path=vendor_patterns_path)

    async def discover(self) -> list[MergedDevice]:
        """Run full discovery pipeline and return merged device list."""
        all_results: list[DiscoveryResult] = []
        scan_id = str(uuid4())

        logger.info(
            "discovery_started",
            scan_id=scan_id,
            subnets=[str(s) for s in self.subnets],
        )

        # Phase 1: ONVIF WS-Discovery (multicast, fastest)
        await self._discovery_phase(
            "onvif_multicast", 1, all_results, self.onvif_scanner.discover()
        )

        # Phase 2: ARP table scan (no network traffic, instant)
        await self._discovery_phase("arp_table", 2, all_results, self.arp_scanner.scan())

        # Phase 3: RTSP port scanning on known subnets
        await self._discovery_phase_rtsp(3, all_results)

        # Phase 4: HTTP scanning
        await self._discovery_phase(
            "http_scan",
            4,
            all_results,
            self._run_http_scan(all_results),
        )

        # Phase 5: Vendor-specific broadcast
        await self._discovery_phase("vendor_broadcast", 5, all_results, self.vendor_scanner.scan())

        # Phase 6: mDNS/Avahi
        await self._discovery_phase("mdns", 6, all_results, self.mdns_scanner.scan())

        # Phase 7: Fingerprint all raw results
        for result in all_results:
            if result.vendor == DeviceVendor.UNKNOWN:
                self._fingerprint_result(result)

        # Merge and deduplicate
        merged = merge_results(
            all_results,
            self.fingerprinter.get_vendor_defaults,
        )

        logger.info(
            "discovery_complete",
            scan_id=scan_id,
            raw_results=len(all_results),
            merged_devices=len(merged),
        )

        merged.sort(key=lambda d: d.overall_confidence, reverse=True)
        return merged

    async def _discovery_phase(
        self,
        method: str,
        phase: int,
        results: list[DiscoveryResult],
        coro,
    ):
        """Run a single discovery phase with error handling."""
        logger.info("discovery_phase", phase=phase, method=method)
        try:
            phase_results = await coro
            results.extend(phase_results)
            logger.info(
                "discovery_phase_complete",
                phase=phase,
                found=len(phase_results),
            )
        except Exception as e:
            logger.error(f"{method}_failed", error=str(e), exc_info=True)

    async def _discovery_phase_rtsp(self, phase: int, results: list[DiscoveryResult]):
        """RTSP port scanning phase — scans all hosts in configured subnets."""
        logger.info("discovery_phase", phase=phase, method="rtsp_scan")
        try:
            rtsp_tasks = []
            for subnet in self.subnets:
                for host in subnet.hosts():
                    rtsp_tasks.append(self._scan_rtsp_host(host))
            if rtsp_tasks:
                rtsp_results = await self._run_concurrent(rtsp_tasks, tag="rtsp")
                results.extend(rtsp_results)
            found = len(rtsp_results) if rtsp_tasks else 0
            logger.info("discovery_phase_complete", phase=phase, found=found)
        except Exception as e:
            logger.error("rtsp_scan_failed", error=str(e), exc_info=True)

    async def _scan_rtsp_host(self, host: IPv4Address) -> DiscoveryResult | None:
        result = await self.rtsp_scanner.probe(host)
        if result:
            self._fingerprint_result(result)
        return result

    async def _run_http_scan(
        self, existing_results: list[DiscoveryResult]
    ) -> list[DiscoveryResult]:
        known_ips = {r.ip_address for r in existing_results}
        results: list[DiscoveryResult] = []
        for subnet in self.subnets:
            for host in subnet.hosts():
                if host in known_ips:
                    http_result = await self.http_scanner.probe(host)
                    if http_result:
                        self._fingerprint_result(http_result)
                        results.append(http_result)
        return results

    async def _run_concurrent(self, tasks: list, tag: str = "") -> list[DiscoveryResult]:
        semaphore = asyncio.Semaphore(self.max_concurrent_scans)
        results: list[DiscoveryResult] = []

        async def bounded(task):
            async with semaphore:
                try:
                    return await task
                except Exception as e:
                    logger.warning(f"{tag}_task_failed", error=str(e))
                    return None

        raw_results = await asyncio.gather(*[bounded(t) for t in tasks])
        for r in raw_results:
            if r is not None:
                results.append(r)
        return results

    # --- Fingerprinting ---

    def _fingerprint_result(self, result: DiscoveryResult) -> None:
        """Apply vendor fingerprinting to a discovery result."""
        if result.stream_main_uri:
            vendor = self.fingerprinter.identify_from_rtsp_url(result.stream_main_uri)
            if vendor:
                result.vendor = vendor
                self._apply_vendor_defaults(result, vendor)

        if result.mac_address:
            vendor = self.fingerprinter.identify_from_mac(result.mac_address)
            if vendor:
                result.vendor = vendor
                self._apply_vendor_defaults(result, vendor)

        if result.raw_data.get("http_server_header"):
            vendor = self.fingerprinter.identify_from_http_header(
                result.raw_data["http_server_header"]
            )
            if vendor:
                result.vendor = vendor
                self._apply_vendor_defaults(result, vendor)

        if result.manufacturer:
            vendor = self.fingerprinter.identify_from_onvif_manufacturer(result.manufacturer)
            if vendor:
                result.vendor = vendor
                self._apply_vendor_defaults(result, vendor)

        result.confidence = self._calculate_confidence(result)

    def _apply_vendor_defaults(self, result: DiscoveryResult, vendor: DeviceVendor) -> None:
        defaults = self.fingerprinter.get_vendor_defaults(vendor)
        if not defaults:
            return

        if not result.stream_main_uri and defaults.get("rtsp_paths"):
            primary_rtsp = defaults["rtsp_paths"][0]
            ip = str(result.ip_address)
            result.stream_main_uri = f"rtsp://{ip}:554{primary_rtsp}"

        if not result.http_url and defaults.get("default_ports"):
            http_port = next(
                (p for p in defaults["default_ports"] if p in {80, 443, 8080}),
                defaults["default_ports"][0],
            )
            result.http_url = f"http://{result.ip_address}:{http_port}"

    def _calculate_confidence(self, result: DiscoveryResult) -> int:
        """Calculate confidence score based on discovery method and attributes.

        ONVIF: 90-100 | RTSP: 70-85 | HTTP: 60-75 | ARP: 40-60
        Vendor broadcast: 70-80 | mDNS: 50-65 | Multiple indicators: bonus
        """
        method_scores = {
            DiscoveryMethod.ONVIF: 90,
            DiscoveryMethod.RTSP: 70,
            DiscoveryMethod.HTTP: 60,
            DiscoveryMethod.ARP: 40,
            DiscoveryMethod.VENDOR_BROADCAST: 70,
            DiscoveryMethod.MDNS: 50,
        }
        score = method_scores.get(result.method, 10)

        if result.vendor != DeviceVendor.UNKNOWN:
            score += 10
        if result.model:
            score += 5
        if result.stream_main_uri and result.method == DiscoveryMethod.RTSP:
            score += 5

        # Bonus for multiple attributes
        attrs = sum(
            [
                bool(result.manufacturer),
                bool(result.model),
                bool(result.mac_address),
                bool(result.stream_main_uri),
                result.has_onvif,
            ]
        )
        score += attrs * 2

        return min(score, 100)
