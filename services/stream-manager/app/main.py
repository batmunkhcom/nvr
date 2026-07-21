"""Stream Manager — main entry point for RTSP/ONVIF stream management."""

from __future__ import annotations

import asyncio

import structlog

from .manager import StreamManager

logger = structlog.get_logger()


async def main() -> None:
    """Start stream manager service."""
    logger.info("stream_manager_starting", version="0.1.0")
    await StreamManager.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
