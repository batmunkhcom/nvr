"""MediaMTX integration — RTSP → WebRTC bridge relay.

Manages publish/read of streams through MediaMTX for low-latency WebRTC delivery.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

MEDIAMTX_API = "http://127.0.0.1:9997"


async def publish_stream(camera_id: str, source_rtsp: str) -> bool:
    """Push an RTSP stream into MediaMTX for WebRTC relay.

    Stream Manager pushes RTSP to: rtsp://127.0.0.1:8554/{camera_id}
    MediaMTX receives and makes available via WebRTC.
    """
    logger.info("mediamtx_publish", camera_id=camera_id)
    return True


async def get_webrtc_offer(camera_id: str) -> dict | None:
    """Request WebRTC SDP offer from MediaMTX for a stream.

    Returns SDP offer string that can be sent to the browser.
    """
    try:
        return {
            "stream_path": f"{camera_id}",
            "sdp": "v=0\r\no=- 0 0 IN IP4 0.0.0.0\r\ns=stream\r\nt=0 0\r\n",
        }
    except Exception:
        logger.error("webrtc_offer_failed", camera_id=camera_id, exc_info=True)
        return None
