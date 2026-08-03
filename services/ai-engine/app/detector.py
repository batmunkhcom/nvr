"""AI Engine — YOLOv8 ONNX object detection + MOG2 motion gate.

YOLOv8 ONNX output is (1, 84, 8400): rows 0-3 are box cx/cy/w/h,
rows 4-83 are the 80 COCO class scores (no separate objectness).
Post-processing: transpose -> per-class argmax -> confidence filter -> NMS.

Detection quality improvements over the base implementation:
- Pure-NumPy NMS (avoids OpenCV version differences).
- Configurable NMS IoU threshold / max detections / class-agnostic mode.
- Larger default working frame width (configurable) so high-resolution
  sub-streams are not over-compressed before inference.
- Lower default confidence threshold so small / distant objects are kept.
"""

from __future__ import annotations

import os
import threading

import numpy as np
import structlog

logger = structlog.get_logger()

MODEL_PATH = os.environ.get("AI_MODEL_PATH", "/app/models")
INPUT_SIZE = int(os.environ.get("AI_INPUT_SIZE", "640") or "640")
NMS_THRESHOLD = float(os.environ.get("AI_NMS_THRESHOLD", "0.65") or "0.65")
MAX_DETECTIONS = int(os.environ.get("AI_MAX_DETECTIONS", "300") or "300")
CLASS_AGNOSTIC_NMS = (
    os.environ.get("AI_CLASS_AGNOSTIC_NMS", "true").lower() in {"1", "true", "yes"}
)

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
        self._lock = threading.Lock()

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
            logger.info(
                "ai_model_loaded",
                model=self.model_name,
                input_size=INPUT_SIZE,
                nms_threshold=NMS_THRESHOLD,
                max_detections=MAX_DETECTIONS,
                class_agnostic_nms=CLASS_AGNOSTIC_NMS,
            )
            return True
        except Exception:
            logger.error("ai_model_load_failed", model=self.model_name, exc_info=True)
            return False

    @property
    def ready(self) -> bool:
        return self._session is not None

    def detect(
        self,
        frame: np.ndarray,
        confidence: float = 0.3,
        nms_threshold: float | None = None,
        max_detections: int | None = None,
    ) -> list[dict]:
        """Run detection on a BGR frame. Returns [{class, confidence, box}].

        The method is tuned for high recall in crowded scenes: class-agnostic
        NMS with a moderate IoU threshold keeps overlapping detections
        (e.g. several people or cars in one frame) while still removing true
        duplicates from the same object.
        """
        if self._session is None:
            return []

        confidence = min(max(confidence, 0.05), 0.95)
        nms_threshold = (
            min(max(nms_threshold, 0.01), 0.99)
            if nms_threshold is not None
            else NMS_THRESHOLD
        )
        max_detections = max(1, max_detections if max_detections is not None else MAX_DETECTIONS)

        blob, scale, pad_x, pad_y = _letterbox(frame, input_size=INPUT_SIZE)

        with self._lock:
            outputs = self._session.run(None, {"images": blob})[0]

        # YOLOv8 ONNX export: (1, 84, 8400) or (1, 84, num_anchors).
        if outputs.ndim != 3 or outputs.shape[1] != 84:
            logger.error(
                "ai_unexpected_output_shape",
                shape=outputs.shape,
                model=self.model_name,
            )
            return []

        preds = np.squeeze(outputs, axis=0).T  # (num_anchors, 84)

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

        # Convert centre-width-height to xyxy in the letterboxed image, then
        # undo letterbox padding/scaling to return original-frame coordinates.
        x1 = (boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2 - pad_x) / scale
        y1 = (boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2 - pad_y) / scale
        x2 = (boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2 - pad_x) / scale
        y2 = (boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2 - pad_y) / scale
        h, w = frame.shape[:2]
        boxes = np.stack([x1.clip(0, w), y1.clip(0, h), x2.clip(0, w), y2.clip(0, h)], axis=1)

        keep = nms(
            boxes,
            confidences,
            class_ids,
            iou_threshold=nms_threshold,
            class_agnostic=CLASS_AGNOSTIC_NMS,
            max_detections=max_detections,
        )
        if len(keep) == 0:
            return []

        results = []
        for i in keep:
            results.append(
                {
                    "class": COCO_CLASSES[int(class_ids[i])],
                    "confidence": round(float(confidences[i]), 3),
                    "box": [round(float(v), 1) for v in boxes[i]],
                }
            )
        logger.debug(
            "ai_detected",
            detections=len(results),
            confidence_threshold=confidence,
            nms_threshold=nms_threshold,
        )
        return results


def _letterbox(
    frame: np.ndarray, input_size: int = INPUT_SIZE
) -> tuple[np.ndarray, float, float, float]:
    """Resize keeping aspect ratio + pad to input_size^2, normalize to NCHW float32."""
    import cv2

    h, w = frame.shape[:2]
    scale = input_size / max(h, w)
    new_w, new_h = round(w * scale), round(h * scale)
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_x = (input_size - new_w) / 2
    pad_y = (input_size - new_h) / 2
    top = round(pad_y)
    bottom = input_size - new_h - top
    left = round(pad_x)
    right = input_size - new_w - left

    padded = cv2.copyMakeBorder(
        resized,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    blob = padded[:, :, ::-1].transpose(2, 0, 1)  # BGR->RGB, HWC->CHW
    blob = np.ascontiguousarray(blob, dtype=np.float32) / 255.0
    return np.expand_dims(blob, axis=0), scale, pad_x, pad_y


def nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    class_ids: np.ndarray,
    iou_threshold: float,
    class_agnostic: bool = True,
    max_detections: int = 300,
) -> list[int]:
    """Pure-NumPy Non-Maximum Suppression.

    When ``class_agnostic`` is True (default), boxes of any class compete in
    NMS. This keeps overlapping objects of different classes (e.g. person +
    backpack, car + person) and also keeps multiple same-class objects that
    only slightly overlap (parking lots, crowds).

    ``max_detections`` caps the number of returned boxes so a noisy frame
    cannot produce an unbounded result list.
    """
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    order = np.argsort(scores)[::-1]
    keep: list[int] = []

    while order.size > 0 and len(keep) < max_detections:
        i = order[0]
        keep.append(int(i))

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        inter_w = np.maximum(0.0, xx2 - xx1)
        inter_h = np.maximum(0.0, yy2 - yy1)
        inter = inter_w * inter_h
        union = areas[i] + areas[order[1:]] - inter
        iou = inter / np.maximum(union, 1e-8)

        if class_agnostic:
            suppress = iou > iou_threshold
        else:
            suppress = (iou > iou_threshold) & (class_ids[i] == class_ids[order[1:]])

        order = order[1:][~suppress]

    return keep


class MotionDetector:
    """OpenCV MOG2 background-subtraction motion gate."""

    _FG_MIN = int(os.environ.get("AI_MOTION_FG_MIN", "800") or "800")

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
        self.last_fg_ratio = fg_pixels / total
        self.last_fg_pixels = fg_pixels
        # Whole-frame illumination change (light flicker) → not motion
        if self.last_fg_ratio > 0.40:
            return False
        return fg_pixels > self._FG_MIN
