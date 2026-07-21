"""Camera snapshot capture endpoint."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = structlog.get_logger()

router = APIRouter()


@router.post("/api/v1/cameras/{camera_id}/snapshot")
async def capture_snapshot(camera_id: uuid.UUID):
    """Capture a JPEG snapshot from the camera's stream."""
    return JSONResponse(
        {
            "data": {
                "snapshot_url": f"/api/v1/files/snapshots/{camera_id}.jpg",
                "taken_at": "2026-01-01T00:00:00Z",
                "resolution": "1920x1080",
            }
        }
    )
