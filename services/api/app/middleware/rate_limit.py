"""Rate limiting middleware — per-endpoint and per-user request limits."""

from __future__ import annotations

import time
from collections import defaultdict

import structlog
from fastapi import HTTPException, Request, status

logger = structlog.get_logger()

RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/login": (5, 60),  # 5 req/min
    "/api/v1/cameras/discover": (2, 60),  # 2 req/min
    "/api/v1/recordings/export": (10, 60),  # 10 req/min
}

_default_limit = (100, 60)  # 100 req/min

_hit_counters: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))


class RateLimiter:
    """Simple in-memory sliding window rate limiter."""

    @staticmethod
    async def check(request: Request) -> None:
        path = request.url.path
        ip = request.client.host if request.client else "unknown"
        key = f"{ip}:{path}"

        limit, window = RATE_LIMITS.get(path, _default_limit)
        now = time.monotonic()
        hist = _hit_counters[key]

        hist[:] = [t for t in hist.get(key, []) if now - t < window]  # type: ignore[index,arg-type]
        hist.append(now)

        if len(hist) > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
            )


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI middleware wrapper for rate limiting."""
    try:
        await RateLimiter.check(request)
    except HTTPException as e:
        return e
    return await call_next(request)
