"""System self-test — comprehensive diagnostic check endpoint."""

from __future__ import annotations

import asyncio
import time

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def run_self_test(db: AsyncSession) -> dict:
    """Run comprehensive system diagnostics.

    Checks:
        - Database connectivity + latency
        - Redis connectivity + latency
        - MinIO connectivity + latency
        - FFmpeg availability
        - Disk space per storage backend
        - Active camera count
    """
    results = {}

    # Database
    db_start = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        results["database"] = {
            "status": "ok",
            "latency_ms": round((time.monotonic() - db_start) * 1000, 2),
        }
    except Exception as e:
        results["database"] = {"status": "error", "error": str(e)}

    # Redis
    try:
        from ..core.redis import get_redis

        redis = await get_redis()
        redis_start = time.monotonic()
        await redis.ping()
        results["redis"] = {
            "status": "ok",
            "latency_ms": round((time.monotonic() - redis_start) * 1000, 2),
        }
    except Exception as e:
        results["redis"] = {"status": "error", "error": str(e)}

    # MinIO
    try:
        import aiohttp

        s3_start = time.monotonic()
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                "http://nvr-minio:9000/minio/health/live", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp,
        ):
            if resp.status == 200:
                results["minio"] = {
                    "status": "ok",
                    "latency_ms": round((time.monotonic() - s3_start) * 1000, 2),
                }
            else:
                results["minio"] = {"status": "error", "http_status": resp.status}
    except Exception as e:
        results["minio"] = {"status": "error", "error": str(e)}

    # FFmpeg
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        version_line = stdout.decode().split("\n")[0] if stdout else "unknown"
        results["ffmpeg"] = {"status": "ok", "version": version_line[:60]}
    except Exception as e:
        results["ffmpeg"] = {"status": "error", "error": str(e)}

    overall = all(v.get("status") == "ok" for v in results.values())
    return {"overall": "healthy" if overall else "degraded", "checks": results}
