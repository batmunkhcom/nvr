"""Shared ONVIF WS-BaseNotification HTTP callback server.

A single process-wide server binds to port 8091 and routes incoming
Notification messages to the correct camera subscriber by path:

    POST /onvif-events/{camera_id}

This avoids the port-conflict that occurs when every OnvifBaseSubscriber
tries to start its own server on the same port.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()

DEFAULT_PORT = int(os.environ.get("ONVIF_CALLBACK_PORT", "8091") or "8091")
CALLBACK_PATH_PREFIX = "/onvif-events/"


class OnvifCallbackServer:
    """Singleton HTTP server that routes ONVIF callbacks per camera."""

    _instance: OnvifCallbackServer | None = None

    def __new__(cls) -> OnvifCallbackServer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        if self._initialized:
            return
        self._port = port
        self._server: asyncio.Server | None = None
        self._handlers: dict[str, asyncio.Queue[str]] = {}
        self._last_event_ts: dict[str, float] = {}
        self._running = False
        self._initialized = True

    @property
    def port(self) -> int:
        return self._port

    def callback_url(self, camera_id: str, host: str = "") -> str:
        """Build the callback URL advertised to a camera."""
        callback_host = host or os.environ.get("ONVIF_CALLBACK_HOST", "")
        if not callback_host:
            callback_host = "127.0.0.1"
        return f"http://{callback_host}:{self._port}{CALLBACK_PATH_PREFIX}{camera_id}"

    async def start(self) -> None:
        """Start the shared server if not already running."""
        if self._running:
            return
        self._server = await asyncio.start_server(
            self._handle_request,
            host="0.0.0.0",
            port=self._port,
        )
        self._running = True
        logger.info(
            "onvif_callback_server_started",
            port=self._port,
            host="0.0.0.0",
        )

    async def stop(self) -> None:
        """Stop the shared server and clear all handlers."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._running = False
        self._handlers.clear()
        logger.info("onvif_callback_server_stopped", port=self._port)

    def register(self, camera_id: str, queue: asyncio.Queue[str]) -> None:
        """Register a queue for a camera. Duplicates replace the old queue."""
        self._handlers[camera_id] = queue
        logger.debug(
            "onvif_callback_handler_registered",
            camera_id=camera_id,
            path=f"{CALLBACK_PATH_PREFIX}{camera_id}",
        )

    def unregister(self, camera_id: str) -> None:
        """Remove a camera's queue."""
        self._handlers.pop(camera_id, None)

    def last_event_time(self, camera_id: str) -> float | None:
        """Return the Unix timestamp of the last event for a camera."""
        return self._last_event_ts.get(camera_id)

    def handler_count(self) -> int:
        return len(self._handlers)

    async def _handle_request(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Parse a raw HTTP request and route the body to the right camera."""
        try:
            data = await asyncio.wait_for(reader.read(131072), timeout=10)
        except Exception:
            self._write(writer, 400, b"Bad Request")
            return

        request = data.decode("utf-8", errors="replace")
        lines = request.split("\r\n")
        if not lines:
            self._write(writer, 400, b"Bad Request")
            return

        request_line = lines[0]
        parts = request_line.split(" ")
        if len(parts) < 2 or parts[0] != "POST":
            self._write(writer, 405, b"Method Not Allowed")
            return

        path = parts[1]
        if not path.startswith(CALLBACK_PATH_PREFIX):
            self._write(writer, 404, b"Not Found")
            return

        camera_id = path[len(CALLBACK_PATH_PREFIX):].split("/")[0]
        if not camera_id:
            self._write(writer, 404, b"Not Found")
            return

        # Extract body after the empty line.
        body_parts = data.split(b"\r\n\r\n", 1)
        body_xml = body_parts[1].decode("utf-8", errors="replace") if len(body_parts) > 1 else ""

        if body_xml:
            queue = self._handlers.get(camera_id)
            if queue is not None:
                try:
                    queue.put_nowait(body_xml)
                    self._last_event_ts[camera_id] = datetime.now(UTC).timestamp()
                except asyncio.QueueFull:
                    logger.warning(
                        "onvif_callback_queue_full",
                        camera_id=camera_id,
                    )
            else:
                logger.debug(
                    "onvif_callback_no_handler",
                    camera_id=camera_id,
                    path=path,
                )

        self._write(writer, 200, b"OK")

    def _write(self, writer: asyncio.StreamWriter, status: int, body: bytes) -> None:
        try:
            writer.write(
                f"HTTP/1.1 {status} {self._reason(status)}\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n".encode()
                + body
            )
        except Exception:
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    @staticmethod
    def _reason(status: int) -> str:
        return {
            200: "OK",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
        }.get(status, "Unknown")
