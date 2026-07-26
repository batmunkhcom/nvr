# mBm NVR System — Wiki Home

Centralized Network Video Recorder for managing IP cameras (ONVIF, RTSP, Hikvision, Dahua, Axis, Reolink) with live monitoring, motion-triggered recording, AI object detection, and network health monitoring.

Built with **mBm AI Assistant** — an AI-powered engineering and operations assistant by [mBm TECHNOLOGY LLC](https://mbm.mn).

---

## Quick Links

- [Getting Started](Getting-Started) — Installation and first setup
- [Architecture](Architecture) — System design, service topology, data flows
- [API Reference](API-Reference) — All REST endpoints
- [Stream Playback](Stream-Playback) — Live HLS and recording playback guide
- [AI Detection](AI-Detection) — YOLOv8 object detection pipeline
- [Recording Engine](Recording-Engine) — FFmpeg recording, retention, analytics, pause control
- [Configuration](Configuration) — System config keys and tuning
- [Troubleshooting](Troubleshooting) — Common issues and fixes
- [Changelog](CHANGELOG) — Version history
- [Latest Releases](Latest-Releases) — Most recent updates (auto-generated)

---

## Features Overview

### Live Monitoring
- LL-HLS streaming with 1–3 second glass-to-glass latency
- Sub-stream support for bandwidth-efficient multi-camera previews
- Idle stream reaper — relays stop automatically after 10 min of zero viewers
- Audio playback, digital zoom (2D CSS), PTZ controls

### Recording
- Motion-triggered or continuous recording per camera
- 5-minute MP4 segments with `-c:v copy` (minimal CPU)
- HEVC→H.264 codec normalization for universal browser compatibility
- Circular retention at 85% disk / 2GB free floor
- GB/day analytics, timeline view, thumbnails, bulk delete

### AI Object Detection
- YOLOv8n ONNX on sub-stream frames (0.5 FPS)
- MOG2 motion gate saves ~80% CPU
- Zone-based filtering, position-aware deduplication
- Bounding box + label annotation on event snapshots
- Plugin counter — person/vehicle/animal/livestock with per-camera statistics
- Motion-only mode for cameras without AI
- LPR (license plate recognition) via EasyOCR

### Recording Control (v0.01.42)
- **Pause All** — global recording stop, admin password protected, streaming unaffected
- **Per-camera toggle** — quick pause/resume on dashboard cards, remembers previous mode

### Network Monitoring
- Real-time bandwidth, latency, packet loss per camera
- Multi-camera overlay charts with time-range selector

---

## Current Version

See [Latest Releases](Latest-Releases) for the most recent version.
