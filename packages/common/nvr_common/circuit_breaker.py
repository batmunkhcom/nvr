"""Circuit breaker with timed auto-reset and exponential backoff.

Mandatory: ALL circuit breakers in NVR system must use timed cooldown auto-reset.
Never use manual-only reset patterns.
"""

from __future__ import annotations

import time

import structlog

logger = structlog.get_logger()


class CircuitBreaker:
    """Timed circuit breaker with auto-reset and exponential backoff cooldown."""

    def __init__(self, name: str, base_cooldown: int = 60, max_cooldown: int = 600):
        self.name = name
        self.base_cooldown = base_cooldown
        self.max_cooldown = max_cooldown
        self.trip_count = 0
        self.circuit_open_until: float = 0.0

    async def is_open(self) -> bool:
        """Check if circuit is open. Auto-resets when cooldown expires."""
        if self.circuit_open_until > time.time():
            return True
        if self.circuit_open_until > 0 and time.time() >= self.circuit_open_until:
            logger.info("circuit_auto_reset", name=self.name)
            self.circuit_open_until = 0.0
        return False

    def trip(self) -> None:
        """Trip the circuit breaker — open for cooldown period."""
        cooldown = min(self.base_cooldown * (2**self.trip_count), self.max_cooldown)
        self.trip_count += 1
        self.circuit_open_until = time.time() + cooldown
        logger.warning(
            "circuit_tripped",
            name=self.name,
            cooldown_s=cooldown,
            trip_count=self.trip_count,
        )

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self.trip_count = 0
        self.circuit_open_until = 0.0
        logger.info("circuit_reset", name=self.name)

    def cooldown_remaining(self) -> float:
        """Seconds remaining before circuit auto-resets."""
        if self.circuit_open_until <= 0:
            return 0
        return max(0, self.circuit_open_until - time.time())
