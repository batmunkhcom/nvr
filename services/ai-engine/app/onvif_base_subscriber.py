"""ONVIF WS-BaseNotification subscriber — receives push events from cameras
that do NOT support PullPoint (WSPullPointSupport=false) but DO support
WSSubscriptionPolicy (the older Subscribe/Notify model).

The subscriber registers a per-camera callback path with the shared
`OnvifCallbackServer`, sends a WS-BaseNotification Subscribe request to the
camera, and processes incoming Notification messages by publishing motion
state + storing events.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime

import httpx
import structlog

from . import db as db_module
from .onvif_callback_server import OnvifCallbackServer
from .onvif_event_subscriber import _is_motion_event, _parse_onvif_events

logger = structlog.get_logger()

SUBSCRIPTION_TTL_S = 480
RETRY_DELAY_S = 30


def _subscribe_soap(callback_url: str) -> str:
    """WS-BaseNotification Subscribe SOAP envelope.

    Uses a concrete topic expression for the two topics all audited cameras
    expose: CellMotionDetector motion and human-shape (IVA) alarms.  Some
    cameras ignore broad wildcard filters; exact topics are safer.
    """
    topics = (
        "tns1:RuleEngine/CellMotionDetector/Motion OR "
        "tns1:UserAlarm/IVA/HumanShapeDetect"
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:wsa="http://www.w3.org/2005/08/addressing"'
        ' xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"'
        ' xmlns:tns1="http://www.onvif.org/ver10/topics">'
        "<s:Header>"
        "<wsa:Action>http://docs.oasis-open.org/wsn/bw-2/Subscribe/SubscribeRequest</wsa:Action>"
        "</s:Header>"
        "<s:Body>"
        "<wsnt:Subscribe>"
        "<wsnt:ConsumerReference>"
        f"<wsa:Address>{callback_url}</wsa:Address>"
        "</wsnt:ConsumerReference>"
        "<wsnt:Filter>"
        '<wsnt:TopicExpression Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">'
        f"{topics}"
        "</wsnt:TopicExpression>"
        "</wsnt:Filter>"
        "<wsnt:InitialTerminationTime>PT600S</wsnt:InitialTerminationTime>"
        "</wsnt:Subscribe>"
        "</s:Body>"
        "</s:Envelope>"
    )


def _renew_soap() -> str:
    """WS-BaseNotification Renew SOAP envelope (keeps subscription alive)."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">'
        "<s:Body>"
        "<wsnt:Renew>"
        "<wsnt:TerminationTime>PT600S</wsnt:TerminationTime>"
        "</wsnt:Renew>"
        "</s:Body>"
        "</s:Envelope>"
    )


def _unsubscribe_soap() -> str:
    """WS-BaseNotification Unsubscribe SOAP envelope."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">'
        "<s:Body>"
        "<wsnt:Unsubscribe />"
        "</s:Body>"
        "</s:Envelope>"
    )


class OnvifBaseSubscriber:
    """Subscribe for ONVIF events via WS-BaseNotification (push model).

    The camera POSTs Notification messages to our callback HTTP server.
    This subscriber handles the subscription lifecycle (Subscribe / Renew /
    Unsubscribe) and processes incoming events identically to the PullPoint
    subscriber.
    """

    def __init__(
        self,
        camera_id: str,
        camera_name: str,
        events_service_url: str,
        username: str,
        password: str,
        event_callback,
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.url = events_service_url.rstrip("/")
        self.username = username
        self.password = password
        self._event_callback = event_callback
        self._server = OnvifCallbackServer()
        self._running = False
        self._subscribed = False
        self._events: asyncio.Queue | None = None
        self._tasks: list[asyncio.Task] = []
        self._last_motion_ts: float = 0.0
        self._last_motion_active: bool | None = None
        self._last_event_ts: dict[str, float] = {}

    @property
    def callback_url(self) -> str:
        return self._server.callback_url(self.camera_id)

    async def start(self) -> None:
        self._running = True
        self._events = asyncio.Queue(maxsize=256)
        self._server.register(self.camera_id, self._events)
        logger.info(
            "onvif_base_handler_registered",
            camera=self.camera_name,
            callback=self.callback_url,
        )
        self._tasks = [
            asyncio.create_task(self._process_events()),
            asyncio.create_task(self._subscription_loop()),
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._server.unregister(self.camera_id)
        await self._unsubscribe()
        logger.info("onvif_base_subscriber_stopped", camera=self.camera_name)

    async def _subscription_loop(self) -> None:
        """Subscribe, then renew before TTL expires."""
        import time

        await self._subscribe()
        subscribed_at = time.time()
        while self._running:
            await asyncio.sleep(max(1, SUBSCRIPTION_TTL_S - 60))
            if not self._running:
                break
            if time.time() - subscribed_at > SUBSCRIPTION_TTL_S:
                await self._subscribe()
                subscribed_at = time.time()

    async def _subscribe(self) -> None:
        body = _subscribe_soap(self.callback_url)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    self.url,
                    content=body,
                    headers={"Content-Type": "application/soap+xml"},
                    auth=(self.username, self.password) if self.password else None,
                )
                if resp.status_code < 300:
                    self._subscribed = True
                    logger.info(
                        "onvif_base_subscribed",
                        camera=self.camera_name,
                        callback=self.callback_url,
                    )
                else:
                    logger.warning(
                        "onvif_base_subscribe_failed",
                        camera=self.camera_name,
                        status=resp.status_code,
                        body=resp.text[:300],
                    )
        except Exception:
            logger.warning(
                "onvif_base_subscribe_error",
                camera=self.camera_name,
                exc_info=True,
            )

    async def _unsubscribe(self) -> None:
        if not self._subscribed:
            return
        body = _unsubscribe_soap()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    self.url,
                    content=body,
                    headers={"Content-Type": "application/soap+xml"},
                    auth=(self.username, self.password) if self.password else None,
                )
        except Exception:
            pass

    # ── Event processing ──────────────────────────────────────────────

    async def _process_events(self) -> None:
        while self._running and self._events is not None:
            try:
                body = await asyncio.wait_for(self._events.get(), timeout=5)
            except TimeoutError:
                continue
            for evt in _parse_onvif_events(body):
                await self._handle_event(evt)

    async def _handle_event(self, event: dict) -> None:
        import json
        import time

        from sqlalchemy import text

        event_type = event.get("type", "motion_detected")
        is_motion = _is_motion_event(event)
        now_ts = time.time()

        # Deduplicate motion events: suppress repeated identical motion
        # state within 30s.  Cameras often re-fire motion events every few
        # seconds for the same stationary object — each one would otherwise
        # create a separate DB row + Redis publish.
        if is_motion:
            active = str(event.get("value", "true")).lower() == "true"
            if (
                self._last_motion_active is not None
                and self._last_motion_active == active
                and now_ts - self._last_motion_ts < 30.0
            ):
                return  # duplicate — suppress
            self._last_motion_ts = now_ts
            self._last_motion_active = active

            await db_module.RedisPublisher.shared().publish(
                "nvr:motion", {"camera_id": self.camera_id, "active": active}
            )

        # Deduplicate non-motion smart events: suppress same event_type
        # within 10s.
        if not is_motion:
            last = self._last_event_ts.get(event_type, 0)
            if now_ts - last < 10.0:
                return
            self._last_event_ts[event_type] = now_ts

        try:
            now = datetime.now(UTC)
            async with db_module.SessionFactory() as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO events
                            (id, camera_id, event_type, severity, start_time, metadata)
                        VALUES
                            (:id, :camera_id, :event_type, :severity, :start_time,
                             CAST(:metadata AS json))
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "camera_id": self.camera_id,
                        "event_type": event_type,
                        "severity": "warning" if is_motion else "info",
                        "start_time": now,
                        "metadata": json.dumps(
                            {"source": "camera_onvif", "raw": event, "is_motion": is_motion}
                        ),
                    },
                )
                await session.commit()

            if self._event_callback:
                await self._event_callback(self.camera_id, [event_type], None)
            logger.info(
                "onvif_base_event",
                camera=self.camera_name,
                event_type=event_type,
                is_motion=is_motion,
            )
        except Exception:
            logger.warning(
                "onvif_base_persist_failed",
                camera=self.camera_name,
                exc_info=True,
            )

    def describe(self) -> str:
        return (
            f"OnvifBaseSubscriber(camera={self.camera_name}, "
            f"url={self.url}, callback={self.callback_url})"
        )
