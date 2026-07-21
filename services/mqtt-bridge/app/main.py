"""MQTT Bridge — subscribes to NVR events and publishes to MQTT broker."""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger()


async def main() -> None:
    """Start MQTT bridge service."""
    logger.info("mqtt_bridge_starting", version="0.1.0")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
