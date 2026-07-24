"""Network metrics WebSocket broadcast bridge.

Bridges network_monitor to existing ws_manager for real-time metric push.
No auth needed - ws_manager already handles connection lifecycle.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from .ws_manager import ws_manager


async def broadcast_metric(camera_id: UUID | str, metrics: dict[str, Any]) -> None:
    """Broadcast network metric via existing ws_manager."""
    await ws_manager.broadcast(
        {
            "type": "network_metric",
            "camera_id": str(camera_id),
            "metrics": metrics,
        }
    )
