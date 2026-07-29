"""LPR service — DB operations for license plate readings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_lpr_readings(
    db: AsyncSession,
    camera_id: str | None = None,
    plate_number: str | None = None,
    days: int = 7,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    params: dict[str, Any] = {"days": days, "limit": per_page, "offset": (page - 1) * per_page}
    conditions: list[str] = ["TRUE"]
    if camera_id:
        conditions.append("lp.camera_id = CAST(:camera_id AS uuid)")
        params["camera_id"] = camera_id
    if plate_number:
        conditions.append("lp.plate_number ILIKE :plate_number")
        params["plate_number"] = f"%{plate_number}%"

    # Every condition is a hardcoded literal — no user input is concatenated
    # into the SQL text.  The assertion prevents a future regression.
    _SAFE = {"TRUE", "lp.camera_id = CAST(:camera_id AS uuid)", "lp.plate_number ILIKE :plate_number"}
    assert set(conditions).issubset(_SAFE), f"unsafe LPR condition: {conditions}"

    where_clause = " AND ".join(conditions)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM license_plates lp WHERE {where_clause}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        text(f"""
            SELECT lp.id, lp.camera_id, c.name AS camera_name, lp.plate_number,
                   lp.country_code, lp.pattern_name, lp.confidence,
                   lp.detected_at, lp.plate_image_path, lp.snapshot_path
            FROM license_plates lp
            LEFT JOIN cameras c ON c.id = lp.camera_id
            WHERE {where_clause}
            ORDER BY lp.detected_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    readings = []
    for row in result.fetchall():
        readings.append({
            "id": str(row[0]),
            "camera_id": str(row[1]),
            "camera_name": row[2],
            "plate_number": row[3],
            "country_code": row[4],
            "pattern_name": row[5],
            "confidence": round(float(row[6]), 3) if row[6] else None,
            "detected_at": row[7].isoformat() if row[7] else None,
            "plate_image_path": row[8],
            "snapshot_path": row[9],
        })

    return {"data": readings, "metadata": {"page": page, "per_page": per_page, "total": total}}
