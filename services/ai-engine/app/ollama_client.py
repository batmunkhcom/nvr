"""Ollama client — LLM-powered snapshot analysis and event summarization."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

OLLAMA_BASE = "http://10.10.20.83:11434"
DEFAULT_MODEL = "llama3.2-vision:latest"


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE, model: str = DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def analyze_snapshot(self, image_bytes: bytes, prompt: str | None = None) -> str:
        encoded = base64.b64encode(image_bytes).decode()
        user_prompt = prompt or (
            "Describe what you see in this security camera snapshot. "
            "Focus on: people (count, actions), vehicles (type, color), animals, "
            "and anything unusual. Be concise."
        )
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": user_prompt,
                        "images": [encoded],
                        "stream": False,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("response", "").strip()
                logger.warning("ollama_analysis_failed", status=resp.status_code, body=resp.text[:200])
                return ""
        except Exception:
            logger.warning("ollama_analysis_error", exc_info=True)
            return ""

    async def summarize_events(
        self,
        events: list[dict],
        camera_name: str,
        time_range: str,
    ) -> str:
        events_text = json.dumps(events, indent=2, default=str)
        prompt = (
            f"Camera '{camera_name}' recorded the following security events during {time_range}:\n\n"
            f"{events_text}\n\n"
            "Provide a brief 3-5 sentence summary of the important activities. "
            "Mention notable patterns, peak activity times, and anything unusual."
        )
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("response", "").strip()
                logger.warning("ollama_summary_failed", status=resp.status_code)
                return ""
        except Exception:
            logger.warning("ollama_summary_error", exc_info=True)
            return ""

    async def classify_event(self, snapshot_bytes: bytes, detected_objects: list[str]) -> str:
        encoded = base64.b64encode(snapshot_bytes).decode()
        objects_str = ", ".join(detected_objects) if detected_objects else "unknown objects"
        prompt = (
            f"The AI detected: {objects_str}. "
            "Is this event worth alerting a security operator? "
            "Answer with JUST one word: 'alert' or 'ignore'. "
            "Alert if the scene shows: an intrusion, theft, fighting, fire, accident, "
            "or a person in a restricted area. Ignore if it's normal: walking, parking, shadows, animals."
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "images": [encoded],
                        "stream": False,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("response", "").strip().lower()
                    return "alert" if "alert" in result else "ignore"
                return "ignore"
        except Exception:
            return "ignore"

    async def chat(self, messages: list[dict], snapshot_bytes: bytes | None = None) -> str:
        formatted = []
        for m in messages:
            formatted.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        if snapshot_bytes:
            encoded = base64.b64encode(snapshot_bytes).decode()
            formatted.append({
                "role": "user",
                "content": "Analyze the attached security camera snapshot.",
                "images": [encoded],
            })

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": formatted, "stream": False},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("message", {}).get("content", "").strip()
                return "Failed to get response from Ollama"
        except Exception:
            return "Ollama server is unreachable. Check that it's running at " + self.base_url

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
