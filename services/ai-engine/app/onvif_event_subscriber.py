"""ONVIF event subscriber — pull smart events from cameras with built-in AI."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import structlog

logger = structlog.get_logger()

ONVIF_PULLPOINT_PATH = "/Events/PullPoint"
PULL_TIMEOUT = 20
RETRY_DELAY = 30


class OnvifEventSubscriber:
    def __init__(
        self,
        camera_id: uuid.UUID,
        camera_name: str,
        events_service_url: str,
        username: str,
        password: str,
        db_session_factory,
        event_callback,
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.url = events_service_url.rstrip("/")
        self.username = username
        self.password = password
        self._db_factory = db_session_factory
        self._event_callback = event_callback
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("onvif_subscriber_started", camera=self.camera_name)
        asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False

    async def _loop(self) -> None:
        await self._subscribe()
        while self._running:
            try:
                events = await self._pull_messages()
                for evt in events:
                    await self._handle_event(evt)
            except Exception:
                logger.warning("onvif_pull_failed", camera=self.camera_name, exc_info=True)
                await asyncio.sleep(RETRY_DELAY)
                await self._subscribe()

    async def _subscribe(self) -> None:
        body = _soap_envelope(
            "tns:CreatePullPointSubscription",
            "<tns:InitialTerminationTime>PT600S</tns:InitialTerminationTime>",
        )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    self.url,
                    content=body,
                    headers={"Content-Type": "application/soap+xml"},
                    auth=(self.username, self.password) if self.password else None,
                )
                if resp.status_code == 200:
                    logger.info("onvif_subscribed", camera=self.camera_name)
                else:
                    logger.warning("onvif_subscribe_failed", status=resp.status_code)
                    await asyncio.sleep(RETRY_DELAY)
        except Exception:
            await asyncio.sleep(RETRY_DELAY)

    async def _pull_messages(self) -> list[dict]:
        body = _soap_envelope(
            "tns:PullMessages",
            "<tns:Timeout>PT20S</tns:Timeout><tns:MessageLimit>10</tns:MessageLimit>",
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.url,
                content=body,
                headers={"Content-Type": "application/soap+xml"},
                auth=(self.username, self.password) if self.password else None,
            )
            if resp.status_code != 200:
                return []
            return _parse_onvif_events(resp.text)

    async def _handle_event(self, event: dict) -> None:
        event_type = event.get("type", "motion_detected")
        is_motion = _is_motion_event(event)

        try:
            from app.models.event import Event

            async with self._db_factory() as db:

                now = datetime.now(UTC)
                ev = Event(
                    id=uuid.uuid4(),
                    camera_id=self.camera_id,
                    event_type=event_type,
                    severity="info" if not is_motion else "warning",
                    start_time=now,
                    event_metadata={
                        "source": "camera_onvif",
                        "raw": event,
                        "is_motion": is_motion,
                    },
                )
                db.add(ev)
                await db.commit()

                if self._event_callback:
                    await self._event_callback(
                        self.camera_id,
                        [event_type],
                        None,
                    )
                logger.info(
                    "onvif_event", camera=self.camera_name,
                    event_type=event_type, is_motion=is_motion,
                )
        except Exception:
            logger.warning("onvif_persist_failed", camera=self.camera_name, exc_info=True)

    def describe(self) -> str:
        return f"OnvifSubscriber(camera={self.camera_name}, url={self.url})"


def _soap_envelope(action: str, body_content: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:tns="http://www.onvif.org/ver10/events/wsdl">'
        f"<s:Body><{action}>{body_content}</{action}></s:Body>"
        "</s:Envelope>"
    )


def _parse_onvif_events(xml_text: str) -> list[dict]:
    events: list[dict] = []
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_text)
        ns = {
            "tns": "http://www.onvif.org/ver10/events/wsdl",
            "wsnt": "http://docs.oasis-open.org/wsn/b-2",
            "tt": "http://www.onvif.org/ver10/schema",
        }
        for msg in root.findall(".//tns:NotificationMessage", ns):
            topic_elem = msg.find("wsnt:Topic", ns)
            topic = topic_elem.text if topic_elem is not None else ""
            is_motion = _is_motion_topic(topic.lower())

            data_elem = msg.find(".//tt:SimpleItem", ns)
            value = "true"
            if data_elem is not None:
                value = data_elem.get("Value", "true")

            events.append({
                "type": "motion_detected" if is_motion else "smart_event",
                "topic": topic,
                "value": value,
                "is_motion": is_motion,
            })
    except Exception:
        pass
    return events


def _is_motion_topic(topic: str) -> bool:
    keywords = ["motion", "movement", "videoanalytics", "cellmotion", "fielddetector", "ivs", "vmd"]
    return any(kw in topic.lower() for kw in keywords)


def _is_motion_event(event: dict) -> bool:
    if event.get("is_motion"):
        return True
    topic = event.get("topic", "").lower()
    return _is_motion_topic(topic)
