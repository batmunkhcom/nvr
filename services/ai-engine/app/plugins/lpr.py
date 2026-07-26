"""LPR Plugin — License Plate Recognition with pattern-based OCR.

Uses EasyOCR (default) or PaddleOCR for text extraction, then matches
against selected country regex patterns. Per-camera config via
``cameras.lpr_config`` JSONB field.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime

import numpy as np
import structlog

from .. import db
from .base import AIPlugin
from .lpr_patterns import DEFAULT_PATTERN, LPR_PATTERNS

logger = structlog.get_logger()

PLATE_DEDUP_S = 120  # skip same plate_number + camera_id within this window


class LPRPlugin(AIPlugin):
    name = "lpr"

    def __init__(self) -> None:
        self._ocr = None
        self._ocr_ready = False
        self._camera_configs: dict[str, dict] = {}
        self._last_plate_ts: dict[tuple, float] = {}
        self._running = False
        self._config_reload_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        await self._init_ocr()
        await self._load_configs()
        self._config_reload_task = asyncio.create_task(self._config_reload_loop())
        logger.info("lpr_plugin_started", ocr_ready=self._ocr_ready)

    async def stop(self) -> None:
        self._running = False
        if self._config_reload_task:
            self._config_reload_task.cancel()
        self._ocr = None
        self._ocr_ready = False
        logger.info("lpr_plugin_stopped")

    async def _init_ocr(self) -> None:
        try:
            import easyocr
            self._ocr = await asyncio.to_thread(
                easyocr.Reader,
                ["en", "mn"],
                gpu=False,
                verbose=False,
            )
            self._ocr_ready = True
            logger.info("lpr_ocr_loaded", engine="easyocr")
        except ImportError:
            logger.warning("lpr_easyocr_not_installed", hint="pip install easyocr")
        except Exception:
            logger.warning("lpr_ocr_init_failed", exc_info=True)

    async def _load_configs(self) -> None:
        try:
            from sqlalchemy import text

            async with db.SessionFactory() as session:
                result = await session.execute(
                    text(
                        "SELECT id, lpr_config FROM cameras WHERE is_active AND lpr_config->>'enabled' = 'true'"
                    )
                )
                for row in result.fetchall():
                    cam_id = str(row[0])
                    config = row[1] or {}
                    self._camera_configs[cam_id] = config
        except Exception:
            logger.warning("lpr_config_load_failed", exc_info=True)

    async def _config_reload_loop(self) -> None:
        while self._running:
            await asyncio.sleep(60)
            await self._load_configs()

    async def on_detection(
        self,
        camera_id: str,
        detections: list[dict],
        frame: np.ndarray,
        timestamp: datetime,
    ) -> None:
        if not self._ocr_ready:
            return

        config = self._camera_configs.get(camera_id)
        if not config or not config.get("enabled"):
            return

        pattern_name = config.get("pattern") or DEFAULT_PATTERN
        min_confidence = float(config.get("min_confidence", 0.75))
        custom_regex = config.get("custom_regex")

        vehicle_classes = {"car", "truck", "bus", "motorcycle"}
        for det in detections:
            if det["class"] not in vehicle_classes:
                continue

            box = det.get("box")
            if not box or len(box) != 4:
                continue

            crop = self._crop_plate_region(frame, box)
            if crop.size == 0:
                continue

            raw_text = await self._ocr_read(crop)
            if not raw_text:
                continue

            plate_number, ocr_conf = await self._match_pattern(
                raw_text, pattern_name, custom_regex
            )
            if not plate_number or ocr_conf < min_confidence:
                continue

            dedup_key = (camera_id, plate_number)
            now_ts = timestamp.timestamp()
            last = self._last_plate_ts.get(dedup_key, 0)
            if now_ts - last < PLATE_DEDUP_S:
                continue
            self._last_plate_ts[dedup_key] = now_ts

            await self._persist_plate(
                camera_id=camera_id,
                plate_number=plate_number,
                pattern_name=pattern_name,
                confidence=ocr_conf,
                timestamp=timestamp,
                frame=frame,
                box=box,
            )

    def _crop_plate_region(self, frame: np.ndarray, box: list[float]) -> np.ndarray:
        x1, y1, x2, y2 = [int(v) for v in box]
        h, w = frame.shape[:2]
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        # focus on lower 35% of vehicle bbox where plates typically sit
        plate_top = y1 + int((y2 - y1) * 0.65)
        return frame[plate_top:y2, x1:x2]

    async def _ocr_read(self, crop: np.ndarray) -> str | None:
        if self._ocr is None:
            return None
        try:
            results = await asyncio.to_thread(
                self._ocr.readtext, crop, detail=1, paragraph=False
            )
            if not results:
                return None
            # pick highest-confidence result
            best = max(results, key=lambda r: r[2])
            return best[1].strip().replace(" ", "")
        except Exception:
            return None

    async def _match_pattern(
        self, raw_text: str, pattern_name: str, custom_regex: str | None
    ) -> tuple[str | None, float]:
        entry = LPR_PATTERNS.get(pattern_name)
        patterns: list[str] = []

        if entry and entry["patterns"]:
            patterns = entry["patterns"]
        if pattern_name == "custom" and custom_regex:
            patterns = [custom_regex]

        for pattern in patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                # OCR confidence heuristic: longer match = higher confidence
                matched_text = match.group()
                conf = min(0.99, 0.55 + len(matched_text) * 0.08)
                return matched_text.upper(), conf

        return None, 0.0

    async def _persist_plate(
        self,
        camera_id: str,
        plate_number: str,
        pattern_name: str,
        confidence: float,
        timestamp: datetime,
        frame: np.ndarray,
        box: list[float],
    ) -> None:
        import cv2

        country_code = "XX"
        entry = LPR_PATTERNS.get(pattern_name)
        if entry:
            country_code = entry.get("code", "XX")

        plate_image_path = None
        try:
            crop = self._crop_plate_region(frame, box)
            plate_dir = os.path.join(
                os.environ.get("STORAGE_LOCAL_PATH", "/data/recordings"),
                "lpr_plates",
            )
            os.makedirs(plate_dir, exist_ok=True)
            plate_image_path = os.path.join(
                plate_dir,
                f"{camera_id}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{plate_number}.jpg",
            )
            await asyncio.to_thread(cv2.imwrite, plate_image_path, crop)
        except Exception:
            logger.warning("lpr_crop_save_failed", exc_info=True)

        try:
            async with db.SessionFactory() as session:
                await db.insert_license_plate(
                    session,
                    camera_id=camera_id,
                    plate_number=plate_number,
                    country_code=country_code,
                    pattern_name=pattern_name,
                    confidence=confidence,
                    detected_at=timestamp,
                    plate_image_path=plate_image_path,
                )
        except Exception:
            logger.warning("lpr_persist_failed", exc_info=True)

        logger.info(
            "lpr_detected",
            camera_id=camera_id,
            plate=plate_number,
            confidence=round(confidence, 3),
        )
