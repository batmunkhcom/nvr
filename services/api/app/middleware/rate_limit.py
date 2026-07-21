"""Rate limiting middleware — per-endpoint and per-user request limits."""

from __future__ import annotations

import time
from collections import defaultdict

import structlog
from fastapi import HTTPException, Request, status

logger = structlog.get_logger()

RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/login": (5, 60),
    "/api/v1/cameras/discover": (2, 60),
    "/api/v1/recordings/export": (10, 60),
}

DEFAULT_LIMIT = (100, 60)

_history: dict[str, list[float]] = defaultdict(list)


class RateLimiter:
    """Simple in-memory sliding window rate limiter."""

    @staticmethod
    async def check(request: Request) -> None:
        path = request.url.path
        ip = request.client.host if request.client else "unknown"
        key = f"{ip}:{path}"

        limit, window = RATE_LIMITS.get(path, DEFAULT_LIMIT)
        now = time.monotonic()
        hist = _history[key]

        hist[:] = [t for t in hist if now - t < window]
        if len(hist) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
            )
        hist.append(now)


async def rate_limit_middleware(request: Request, call_next):
    try:
        await RateLimiter.check(request)
    except HTTPException as e:
        return e
    return await call_next(request)
