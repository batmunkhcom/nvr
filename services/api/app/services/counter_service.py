"""Counter service — DB aggregation queries for object counters."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config_service import get_timezone, local_date

# All counter categories, in display order. Zero-filled so charts stay dense.
COUNTER_CATEGORIES = ["person", "vehicle", "animal", "livestock"]


async def _get_start_date(db: AsyncSession, days: int) -> date:
    tz = await get_timezone(db)
    return local_date(tz) - timedelta(days=days - 1)


async def get_counter_daily(
    db: AsyncSession,
    camera_id: str | None = None,
    days: int = 7,
) -> list[dict[str, Any]]:
    """Daily object counts per category, zero-filled for the full range.

    Returns one entry per calendar day (local timezone) in the last ``days``
    days: ``{"date": "YYYY-MM-DD", "person": .., "vehicle": .., ...}``.
    """
    tz = await get_timezone(db)
    today = local_date(tz)
    start_date = today - timedelta(days=days - 1)

    if camera_id:
        result = await db.execute(
            text("""
                SELECT counter_date, object_category, SUM(count)::int AS total
                FROM object_counters
                WHERE counter_date >= :start_date
                  AND counter_date <= :today
                  AND camera_id = CAST(:camera_id AS uuid)
                GROUP BY counter_date, object_category
            """),
            {"start_date": start_date, "today": today, "camera_id": camera_id},
        )
    else:
        result = await db.execute(
            text("""
                SELECT counter_date, object_category, SUM(count)::int AS total
                FROM object_counters
                WHERE counter_date >= :start_date
                  AND counter_date <= :today
                GROUP BY counter_date, object_category
            """),
            {"start_date": start_date, "today": today},
        )

    by_date: dict[date, dict[str, int]] = {}
    for row in result.fetchall():
        by_date.setdefault(row[0], {})[row[1]] = row[2]

    series: list[dict[str, Any]] = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        entry: dict[str, Any] = {"date": d.isoformat()}
        row = by_date.get(d, {})
        for cat in COUNTER_CATEGORIES:
            entry[cat] = row.get(cat, 0)
        series.append(entry)
    return series


async def get_counter_summary(
    db: AsyncSession,
    camera_id: str | None = None,
    days: int = 7,
) -> dict[str, int]:
    start_date = await _get_start_date(db, days)

    if camera_id:
        result = await db.execute(
            text("""
                SELECT object_category, SUM(count)::int AS total
                FROM object_counters
                WHERE counter_date >= :start_date
                  AND camera_id = CAST(:camera_id AS uuid)
                GROUP BY object_category
            """),
            {"start_date": start_date, "camera_id": camera_id},
        )
    else:
        result = await db.execute(
            text("""
                SELECT object_category, SUM(count)::int AS total
                FROM object_counters
                WHERE counter_date >= :start_date
                GROUP BY object_category
            """),
            {"start_date": start_date},
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


async def get_counter_per_camera(
    db: AsyncSession,
    days: int = 7,
) -> list[dict]:
    start_date = await _get_start_date(db, days)
    result = await db.execute(
        text("""
            SELECT
                oc.camera_id,
                c.name AS camera_name,
                oc.object_category,
                SUM(oc.count)::int AS total
            FROM object_counters oc
            JOIN cameras c ON c.id = oc.camera_id
            WHERE oc.counter_date >= :start_date
            GROUP BY oc.camera_id, c.name, oc.object_category
            ORDER BY c.name, oc.object_category
        """),
        {"start_date": start_date},
    )
    rows = result.fetchall()
    by_camera: dict[str, dict] = {}
    for row in rows:
        cid = str(row[0])
        cname = row[1]
        cat = row[2]
        cnt = row[3]
        if cid not in by_camera:
            by_camera[cid] = {"camera_id": cid, "camera_name": cname}
        by_camera[cid][cat] = cnt
    return list(by_camera.values())
