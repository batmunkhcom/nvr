"""Live view WebSocket endpoint for camera streaming."""

from __future__ import annotations

import json
import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger()

router = APIRouter()


@router.websocket("/api/v1/cameras/{camera_id}/live")
async def camera_live_ws(websocket: WebSocket, camera_id: uuid.UUID):
    """WebSocket endpoint for WebRTC signaling + HLS fallback.

    Protocol:
      Client → Server: {"type":"offer","sdp":"v=0..."} or {"type":"hls"}
      Server → Client: {"type":"answer","sdp":"v=0..."} or {"type":"hls_url","url":"..."}
    """
    await websocket.accept()
    logger.info("live_ws_connected", camera_id=str(camera_id))

    try:
        await websocket.send_json(
            {
                "type": "status",
                "online": True,
                "recording": False,
                "resolution": "1920x1080",
                "fps": 25,
            }
        )

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "hls":
                await websocket.send_json(
                    {
                        "type": "hls_url",
                        "url": f"/api/v1/streams/{camera_id}/live.m3u8",
                    }
                )
            elif msg_type == "offer":
                await websocket.send_json(
                    {
                        "type": "answer",
                        "sdp": "v=0\r\no=- 0 0 IN IP4 0.0.0.0\r\ns=stream\r\nt=0 0\r\n",
                    }
                )
            elif msg_type == "ice":
                pass
    except WebSocketDisconnect:
        logger.info("live_ws_disconnected", camera_id=str(camera_id))
