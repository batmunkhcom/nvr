"""Counter service — DB aggregation queries for object counters."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_counter_summary(
    db: AsyncSession,
    camera_id: str | None = None,
    days: int = 7,
) -> dict[str, int]:
    since = date.today()
    params: dict[str, Any] = {"counter_date": since, "days": days}
    where = ""
    if camera_id:
        where = "AND camera_id = CAST(:camera_id AS uuid)"
        params["camera_id"] = camera_id

    result = await db.execute(
        text(f"""
            SELECT object_category, SUM(count)::int AS total
            FROM object_counters
            WHERE counter_date >= :counter_date - CAST(:days AS int) * INTERVAL '1 day'
            {where}
            GROUP BY object_category
        """)
    )
    summary: dict[str, int] = {}
    for row in result.fetchall():
        summary[row[0]] = row[1]
    return summary


async def get_counter_hourly(
    db: AsyncSession,
    camera_id: str,
    target_date: date,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT hour, object_category, count
            FROM object_counters
            WHERE camera_id = CAST(:camera_id AS uuid)
              AND counter_date = :counter_date
            ORDER BY hour, object_category
        """),
        {"camera_id": camera_id, "counter_date": target_date},
    )
    rows = result.fetchall()
    hourly: dict[int, dict[str, int]] = {}
    for row in rows:
        hour = row[0]
        cat = row[1]
        cnt = row[2]
        if hour not in hourly:
            hourly[hour] = {}
        hourly[hour][cat] = cnt
    return [
        {"hour": h, **hourly[h]}
        for h in sorted(hourly)
    ]
