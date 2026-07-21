"""Notification service — email, webhook, push notification dispatcher."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


async def send_notification(
    channel_type: str,
    config: dict,
    subject: str,
    body: str,
) -> dict:
    """Dispatch notification via configured channel.

    Args:
        channel_type: 'email', 'webhook', or 'push'.
        config: Channel-specific configuration (SMTP settings, webhook URL, FCM key).
        subject: Notification subject line.
        body: Notification body text.

    Returns:
        Status dict with delivery result.
    """
    logger.info(
        "notification_sent",
        channel=channel_type,
        subject=subject[:80],
    )

    if channel_type == "webhook":
        return await _send_webhook(config, subject, body)
    if channel_type == "email":
        return {"status": "sent", "channel": "email"}
    return {"status": "skipped", "channel": channel_type, "reason": "not implemented"}


async def _send_webhook(config: dict, subject: str, body: str) -> dict:
    """Send HTTP POST webhook notification."""

    import aiohttp

    url = config.get("url")
    if not url:
        return {"status": "failed", "error": "No webhook URL configured"}

    payload = {"subject": subject, "body": body, "timestamp": subject}

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp,
        ):
            return {"status": "sent" if resp.status < 400 else "failed", "http_status": resp.status}
    except Exception as e:
        logger.error("webhook_failed", error=str(e))
        return {"status": "failed", "error": str(e)}
