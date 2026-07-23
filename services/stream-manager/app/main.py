"""Stream Manager — main entry point for RTSP/ONVIF stream management."""

from __future__ import annotations

import asyncio

import structlog

from .manager import StreamManager
from .relay_api import start_relay_api

logger = structlog.get_logger()


async def main() -> None:
    """Start stream manager service."""
    logger.info("stream_manager_starting", version="0.1.0")
    await StreamManager.start()
    await start_relay_api(port=8001)
    logger.info("relay_api_started", port=8001)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
