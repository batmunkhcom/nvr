"""WebSocket manager — broadcast camera/event updates to connected clients."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket


class WSManager:
    """Simple pub/sub WebSocket manager for real-time UI updates."""

    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, default=str)
        dead: set[WebSocket] = set()
        for ws in self._connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        self._connections -= dead

    async def broadcast_camera_update(
        self, camera_id: str, status: str, error: str | None = None
    ) -> None:
        await self.broadcast(
            {
                "type": "camera_status",
                "camera_id": camera_id,
                "status": status,
                "connection_error": error,
            }
        )

    async def broadcast_event(self, event: dict[str, Any]) -> None:
        await self.broadcast({"type": "event", "event": event})

    @property
    def active_connections(self) -> int:
        return len(self._connections)


ws_manager = WSManager()
