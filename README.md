# NVR System

Centralized Network Video Recorder for managing multiple IP cameras (ONVIF, RTSP,
Hikvision, Dahua, Axis, Reolink, etc.) with live monitoring, recording, AI object
detection, and motion detection.

## Quick Start

```bash
# Start infrastructure
make infra

# Seed initial configuration
make seed

# Start API server
make dev
```

## Full Documentation

[PLAN.md](docs/PLAN.md) — Architecture plan, API spec, DB schema

## Development

[AGENTS.md](AGENTS.md) — AI development guide
