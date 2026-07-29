"""AI Engine — YOLOv8 ONNX object detection + MOG2 motion gate.

YOLOv8 ONNX output is (1, 84, 8400): rows 0-3 are box cx/cy/w/h,
rows 4-83 are the 80 COCO class scores (no separate objectness).
Post-processing: transpose -> per-class argmax -> confidence filter -> NMS.
"""

from __future__ import annotations

import os

import numpy as np
import structlog

logger = structlog.get_logger()

MODEL_PATH = os.environ.get("AI_MODEL_PATH", "/app/models")
INPUT_SIZE = 640
NMS_THRESHOLD = 0.45

VEHICLE_CLASSES = {"bicycle", "car", "motorcycle", "bus", "truck"}

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
    """Shared YOLOv8n ONNX detector — one inference session for all cameras."""

    _instance: AIDetector | None = None

    def __init__(self, model_name: str = "yolov8n.onnx"):
        self.model_name = model_name
        self.model_path = os.path.join(MODEL_PATH, model_name)
        self._session = None

    @classmethod
    def shared(cls) -> AIDetector:
        """One model session per process (saves ~100MB per camera)."""
        if cls._instance is None:
            cls._instance = cls(os.environ.get("AI_YOLO_MODEL", "yolov8n.onnx"))
        return cls._instance

    async def initialize(self) -> bool:
        """Load the ONNX model. Returns True when ready for inference."""
        if self._session is not None:
            return True
        if not os.path.exists(self.model_path):
            logger.error("ai_model_missing", path=self.model_path)
            return False
        try:
            import onnxruntime as ort

            providers = ["CPUExecutionProvider"]
            if os.environ.get("AI_DEVICE", "cpu") == "cuda":
                providers.insert(0, "CUDAExecutionProvider")
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            self._session = ort.InferenceSession(
                self.model_path, sess_options=opts, providers=providers
            )
            logger.info("ai_model_loaded", model=self.model_name)
            return True
        except Exception:
            logger.error("ai_model_load_failed", model=self.model_name, exc_info=True)
            return False

    @property
    def ready(self) -> bool:
        return self._session is not None

    def detect(self, frame: np.ndarray, confidence: float = 0.5) -> list[dict]:
        """Run detection on a BGR frame. Returns [{class, confidence, box}]."""
        if self._session is None:
            return []
        import cv2

        confidence = min(max(confidence, 0.05), 0.95)
        blob, scale, pad_x, pad_y = _letterbox(frame)

        outputs = self._session.run(None, {"images": blob})[0]
        preds = np.squeeze(outputs, axis=0).T  # (8400, 84)

        boxes_xywh = preds[:, :4]
        class_scores = preds[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(len(class_scores)), class_ids]

        mask = confidences >= confidence
        if not np.any(mask):
            return []

        boxes_xywh = boxes_xywh[mask]
        confidences = confidences[mask]
        class_ids = class_ids[mask]

        # to xyxy in the letterboxed image, then back to original coords
        x1 = (boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2 - pad_x) / scale
        y1 = (boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2 - pad_y) / scale
        x2 = (boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2 - pad_x) / scale
        y2 = (boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2 - pad_y) / scale
        h, w = frame.shape[:2]
        boxes = np.stack([x1.clip(0, w), y1.clip(0, h), x2.clip(0, w), y2.clip(0, h)], axis=1)

        indices = cv2.dnn.NMSBoxes(boxes.tolist(), confidences.tolist(), confidence, NMS_THRESHOLD)
        if len(indices) == 0:
            return []

        results = []
        for i in np.array(indices).flatten():
            results.append(
                {
                    "class": COCO_CLASSES[int(class_ids[i])],
                    "confidence": round(float(confidences[i]), 3),
                    "box": [round(float(v), 1) for v in boxes[i]],
                }
            )
        return results


def _letterbox(frame: np.ndarray) -> tuple[np.ndarray, float, float, float]:
    """Resize keeping aspect ratio + pad to 640x640, normalize to NCHW float32."""
    import cv2

    h, w = frame.shape[:2]
    scale = min(INPUT_SIZE / w, INPUT_SIZE / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (new_w, new_h))
    pad_x = (INPUT_SIZE - new_w) / 2
    pad_y = (INPUT_SIZE - new_h) / 2
    padded = cv2.copyMakeBorder(
        resized,
        int(pad_y),
        INPUT_SIZE - new_h - int(pad_y),
        int(pad_x),
        INPUT_SIZE - new_w - int(pad_x),
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    blob = padded[:, :, ::-1].transpose(2, 0, 1)  # BGR->RGB, HWC->CHW
    blob = np.ascontiguousarray(blob, dtype=np.float32) / 255.0
    return np.expand_dims(blob, axis=0), scale, pad_x, pad_y


class MotionDetector:
    """OpenCV MOG2 background-subtraction motion gate."""

    def __init__(self, sensitivity: str = "medium"):
        import cv2

        thresholds = {"low": 50, "medium": 30, "high": 20}
        self.threshold = thresholds.get(sensitivity, 30)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=self.threshold, detectShadows=False
        )

    def detect(self, gray_frame: np.ndarray) -> bool:
        import cv2

        fg_mask = self.bg_subtractor.apply(gray_frame)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        fg_pixels = cv2.countNonZero(fg_mask)
        total = gray_frame.shape[0] * gray_frame.shape[1]
        # Whole-frame illumination change (light flicker) → not motion
        if fg_pixels / total > 0.40:
            return False
        return fg_pixels > 800
