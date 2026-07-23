"""WebSocket endpoint — real-time camera status and event push."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from ...core.security import decode_token
from ...services.ws_manager import ws_manager

router = APIRouter()


@router.websocket("/api/v1/ws")
async def ws_endpoint(ws: WebSocket):
    """Accept WebSocket connections with token auth via query param."""
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4001, reason="Missing token")
        return
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await ws.close(code=4001, reason="Invalid token type")
            return
    except JWTError:
        await ws.close(code=4001, reason="Invalid token")
        return

    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(ws)
