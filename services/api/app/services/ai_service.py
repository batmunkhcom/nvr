"""AI Service — OpenAI-compatible + Ollama vision/chat client (optional, config-driven)."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from sqlalchemy import select

from ..core.database import async_session_factory
from ..models.system_config import SystemConfig

logger = structlog.get_logger()

AI_PREFIX = "ai."

_AI_DEFAULTS: dict[str, str] = {
    "enabled": "false",
    "provider": "openai",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "api_key": "",
    "motion_detection_enabled": "false",
    "confidence_threshold": "0.6",
}

_OLLAMA_DEFAULTS: dict[str, str] = {
    "base_url": "http://localhost:11434/v1",
    "model": "llama3.2-vision",
}


async def _load_config() -> dict[str, str]:
    cfg: dict[str, str] = dict(_AI_DEFAULTS)
    try:
        async with async_session_factory() as session:
            keys = list(_AI_DEFAULTS.keys())
            result = await session.execute(
                select(SystemConfig).where(SystemConfig.key.in_([f"{AI_PREFIX}{k}" for k in keys]))
            )
            for row in result.scalars().all():
                short = row.key.removeprefix(AI_PREFIX)
                cfg[short] = str(row.value)
    except Exception as exc:
        logger.warning("ai_config_load_failed", error=str(exc))
    if cfg["provider"] == "ollama":
        for k, v in _OLLAMA_DEFAULTS.items():
            if not cfg.get(k):
                cfg[k] = v
    return cfg


def _make_client(base_url: str, api_key: str) -> httpx.AsyncClient:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
        timeout=httpx.Timeout(30.0),
    )


async def is_ai_enabled() -> bool:
    cfg = await _load_config()
    enabled = cfg.get("enabled", "false").lower() == "true"
    if not enabled:
        return False
    return bool(cfg.get("api_key") or cfg.get("provider") == "ollama")


async def analyze_image(
    image_b64: str, prompt: str = "Describe this image in detail."
) -> dict[str, Any]:
    cfg = await _load_config()

    if cfg.get("enabled", "false").lower() != "true":
        return {"success": False, "error": "AI is disabled", "response": None}

    base_url = cfg["base_url"]
    model = cfg["model"]
    api_key = cfg.get("api_key", "")

    if cfg["provider"] == "ollama" and not api_key:
        api_key = "ollama"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 500,
    }

    try:
        async with _make_client(base_url, api_key) as client:
            resp = await client.post("/chat/completions", json=payload)
            if resp.status_code == 401:
                return {"success": False, "error": "Invalid API key", "response": None}
            if resp.status_code == 429:
                return {
                    "success": False,
                    "error": "Rate limited — try again later",
                    "response": None,
                }
            resp.raise_for_status()
            body = resp.json()
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "success": True,
                "error": None,
                "response": content,
                "model": model,
            }
    except httpx.HTTPStatusError as exc:
        logger.warning("ai_http_error", status=exc.response.status_code)
        return {
            "success": False,
            "error": f"AI API error: {exc.response.status_code}",
            "response": None,
        }
    except httpx.ConnectError:
        return {"success": False, "error": "Cannot reach AI server", "response": None}
    except Exception as exc:
        logger.error("ai_unexpected_error", error=str(exc))
        return {"success": False, "error": f"Unexpected error: {exc!s}", "response": None}
