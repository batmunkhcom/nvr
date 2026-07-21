"""AI Engine — main entry point."""

from __future__ import annotations

import asyncio

import structlog

from .detector import AIDetector

logger = structlog.get_logger()


async def main() -> None:
    """Start AI Engine worker."""
    logger.info("ai_engine_starting", version="0.1.0")

    detector = AIDetector()
    await detector.initialize()

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
