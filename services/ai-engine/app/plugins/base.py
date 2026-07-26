"""AI Plugin base class — all plugins inherit from this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import numpy as np


class AIPlugin(ABC):
    """Base class for AI engine plugins.

    Plugins receive detection results after YOLO inference and
    can perform additional analytics (counting, LPR, alerts, etc.)
    without modifying the core AI engine code.
    """

    name: str = "base"

    @abstractmethod
    async def on_detection(
        self,
        camera_id: str,
        detections: list[dict],
        frame: np.ndarray,
        timestamp: datetime,
    ) -> None:
        """Called after YOLO detection, before DB persistence.

        Args:
            camera_id: UUID of the camera.
            detections: List of {class, confidence, box} dicts.
            frame: Full BGR frame (numpy array).
            timestamp: Detection event time.
        """
        ...

    async def start(self) -> None:
        """One-time init at engine startup."""
        pass

    async def stop(self) -> None:
        """Cleanup on shutdown."""
        pass
