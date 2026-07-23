"""Notification service — email, webhook, Telegram, push notification dispatcher.

Reads channel configuration from system_config DB table.
Intended callers: health_check_loop (status changes), test_camera_connection (auth failures).
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from ..core.database import async_session_factory
from .config_service import get_config_value

logger = structlog.get_logger()

CONFIG_KEYS = {
    "telegram_bot_token": "notification.telegram_bot_token",
    "telegram_chat_id": "notification.telegram_chat_id",
    "webhook_url": "notification.webhook_url",
    "channels_enabled": "notification.channels_enabled",  # json list: ["telegram","webhook"]
}


async def _get_notification_config() -> dict[str, str | None]:
    """Read all notification config keys from system_config."""
    config: dict[str, str | None] = {}
    async with async_session_factory() as session:
        for key, db_key in CONFIG_KEYS.items():
            val = await get_config_value(session, db_key, None)
            config[key] = str(val) if val is not None else None
    return config


async def send_camera_alert(
    camera_id: str,
    camera_name: str,
    status: str,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Notify configured channels when a camera status changes."""

    config = await _get_notification_config()

    channels_raw = config.get("channels_enabled") or "[]"
    try:
        channels: list[str] = json.loads(channels_raw)
    except (json.JSONDecodeError, TypeError):
        channels = []

    if not channels:
        return {"status": "skipped", "reason": "no enabled channels"}

    subject = f"NVR Alert: {camera_name} is {status}"
    body = f"Camera: {camera_name} ({camera_id})\nStatus: {status}"
    if error_message:
        body += f"\nError: {error_message}"

    results: list[dict[str, Any]] = []

    for ch in channels:
        if ch == "telegram":
            tok = config.get("telegram_bot_token")
            chat = config.get("telegram_chat_id")
            if tok and chat:
                results.append(await _send_telegram(tok, chat, body))
            else:
                results.append(
                    {"channel": "telegram", "status": "skipped", "reason": "missing config"}
                )
        elif ch == "webhook":
            url = config.get("webhook_url")
            if url:
                results.append(await _send_webhook(url, subject, body))
            else:
                results.append(
                    {"channel": "webhook", "status": "skipped", "reason": "missing config"}
                )

    return {"status": "dispatched", "results": results}


async def _send_telegram(bot_token: str, chat_id: str, text: str) -> dict[str, Any]:
    """Send message via Telegram Bot API (no external library needed)."""

    import aiohttp

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": "HTML",
    }

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp,
        ):
            data = await resp.json()
            if resp.status == 200 and data.get("ok"):
                logger.info("telegram_sent", chat_id=chat_id)
                return {"channel": "telegram", "status": "sent"}
            err_desc = data.get("description", f"HTTP {resp.status}")
            logger.warning("telegram_failed", error=err_desc)
            return {"channel": "telegram", "status": "failed", "error": err_desc}
    except Exception as exc:
        logger.error("telegram_error", error=str(exc))
        return {"channel": "telegram", "status": "failed", "error": str(exc)}


async def _send_webhook(url: str, subject: str, body: str) -> dict[str, Any]:
    """Send HTTP POST webhook notification."""

    import aiohttp

    payload = {"subject": subject, "body": body}

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp,
        ):
            ok = resp.status < 400
            logger.info("webhook_sent" if ok else "webhook_failed", http_status=resp.status)
            return {
                "channel": "webhook",
                "status": "sent" if ok else "failed",
                "http_status": resp.status,
            }
    except Exception as exc:
        logger.error("webhook_error", error=str(exc))
        return {"channel": "webhook", "status": "failed", "error": str(exc)}


async def send_test_notification() -> dict[str, Any]:
    """Send a test alert to verify notification channels work."""
    return await send_camera_alert(
        camera_id="test",
        camera_name="Test Camera",
        status="test",
        error_message="This is a test notification from mBm NVR System.",
    )
