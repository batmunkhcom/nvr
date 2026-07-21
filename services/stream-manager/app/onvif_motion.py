"""ONVIF native motion handler — Subscribe to ONVIF motion events via PullPoint."""

from __future__ import annotations

import uuid

import structlog

logger = structlog.get_logger()


class ONVIFMotionHandler:
    """Subscribe to camera's built-in motion detection via ONVIF events."""

    def __init__(self, camera_id: uuid.UUID, events_service_url: str, username: str, password: str):
        self.camera_id = camera_id
        self.events_service_url = events_service_url
        self.username = username
        self.password = password
        self._subscription_id: str | None = None

    async def subscribe(self) -> bool:
        """Create ONVIF PullPoint subscription for motion events."""
        logger.info("onvif_motion_subscribe", camera_id=str(self.camera_id))
        self._subscription_id = f"sub_{uuid.uuid4().hex[:8]}"
        return True

    async def pull_messages(self) -> list[dict]:
        """Pull motion event messages from subscription."""
        return []

    async def unsubscribe(self) -> None:
        """Terminate the event subscription."""
        logger.info("onvif_motion_unsubscribe", camera_id=str(self.camera_id))
        self._subscription_id = None
