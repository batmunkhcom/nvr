"""Recording Engine — main entry point."""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger()


async def main() -> None:
    """Start recording engine worker."""
    logger.info("recording_engine_starting", version="0.1.0")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
