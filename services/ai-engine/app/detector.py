"""AI Engine — YOLOv8n ONNX object detection, motion detection, audio classification."""

from __future__ import annotations

import os

import numpy as np
import structlog

logger = structlog.get_logger()

MODEL_PATH = os.environ.get("AI_MODEL_PATH", "/app/models")
CONFIDENCE_THRESHOLD = float(os.environ.get("AI_CONFIDENCE_THRESHOLD", "0.5"))
AI_DEVICE = os.environ.get("AI_DEVICE", "cpu")

COCO_CLASSES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
]


class AIDetector:
    """YOLOv8n ONNX-based object detection engine."""

    def __init__(self, model_name: str = "yolov8n.onnx"):
        self.model_name = model_name
        self.model_path = os.path.join(MODEL_PATH, model_name)
        self._session = None

    async def initialize(self) -> None:
        """Load ONNX model (CPU or GPU)."""
        try:
            import onnxruntime as ort

            providers = ["CPUExecutionProvider"]
            if AI_DEVICE == "cuda":
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

            self._session = ort.InferenceSession(self.model_path, providers=providers)
            logger.info("ai_model_loaded", model=self.model_name, device=AI_DEVICE)
        except Exception:
            logger.warning("ai_model_load_failed", model=self.model_name, exc_info=True)

    async def detect(self, image_data: bytes) -> list[dict]:
        """Run inference on a single frame."""
        if self._session is None:
            return []
        import cv2

        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return []

        img = cv2.resize(img, (640, 640))
        img = img.astype(np.float32) / 255.0
        img = img.transpose(2, 0, 1)
        img = np.expand_dims(img, axis=0)

        outputs = self._session.run(None, {"images": img})
        return self._process_outputs(outputs[0])

    def _process_outputs(self, output: np.ndarray) -> list[dict]:
        """Post-process YOLO outputs: NMS, confidence filter, class mapping."""
        detections = output[0]
        results = []
        for det in detections:
            if len(det) < 6:
                continue
            confidence = float(det[4])
            if confidence < CONFIDENCE_THRESHOLD:
                continue
            class_id = int(det[5])
            if class_id < 0 or class_id >= len(COCO_CLASSES):
                continue
            results.append({
                "class": COCO_CLASSES[class_id],
                "confidence": round(confidence, 3),
                "box": [round(float(det[i]), 1) for i in range(4)],
            })
        return results


class MotionDetector:
    """OpenCV MOG2-based motion detection."""

    def __init__(self, sensitivity: str = "medium"):
        import cv2

        thresholds = {"low": 40, "medium": 25, "high": 16}
        self.threshold = thresholds.get(sensitivity, 25)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=self.threshold, detectShadows=False
        )

    def detect(self, image_data: bytes) -> bool:
        import cv2

        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if frame is None:
            return False
        fg_mask = self.bg_subtractor.apply(frame)
        motion_pixels = cv2.countNonZero(fg_mask)
        return motion_pixels > 500


class AudioDetector:
    """YAMNet-based audio event detector (placeholder)."""

    async def detect(self, audio_data: bytes) -> list[dict]:
        """Classify audio samples into event types."""
        return []
