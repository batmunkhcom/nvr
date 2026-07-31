"""Tests for ai-engine YOLOv8 detector post-processing and NMS.

These tests run without an ONNX model by mocking the inference session output.
They verify the core requirement: many objects (cars, people, etc.) in a single
frame must all be detected and returned.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

AI_APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(scope="module")
def detector():
    spec = __import__("importlib").util.spec_from_file_location(
        "ai_engine_app_detector",
        AI_APP_DIR / "detector.py",
    )
    mod = __import__("importlib").util.module_from_spec(spec)
    sys.modules["ai_engine_app_detector"] = mod
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------
# Letterbox preprocessing
# ----------------------------------------------------------------------


def test_letterbox_square_frame(detector):
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    blob, scale, pad_x, pad_y = detector._letterbox(frame, input_size=640)
    assert blob.shape == (1, 3, 640, 640)
    assert scale == pytest.approx(1.0)
    assert pad_x == pytest.approx(0.0)
    assert pad_y == pytest.approx(0.0)


def test_letterbox_tall_frame(detector):
    frame = np.zeros((720, 480, 3), dtype=np.uint8)
    blob, scale, pad_x, pad_y = detector._letterbox(frame, input_size=640)
    assert blob.shape == (1, 3, 640, 640)
    assert scale == pytest.approx(640 / 720)
    assert pad_x > 0
    assert pad_y == pytest.approx(0.0)


def test_letterbox_wide_frame(detector):
    frame = np.zeros((360, 1280, 3), dtype=np.uint8)
    blob, scale, pad_x, pad_y = detector._letterbox(frame, input_size=640)
    assert blob.shape == (1, 3, 640, 640)
    assert scale == pytest.approx(0.5)
    assert pad_x == pytest.approx(0.0)
    assert pad_y > 0


def test_letterbox_different_input_size(detector):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    blob, _scale, _pad_x, _pad_y = detector._letterbox(frame, input_size=320)
    assert blob.shape == (1, 3, 320, 320)


# ----------------------------------------------------------------------
# NMS
# ----------------------------------------------------------------------


def test_nms_keeps_non_overlapping_boxes(detector):
    boxes = np.array([
        [0, 0, 10, 10],
        [20, 20, 30, 30],
        [40, 40, 50, 50],
    ], dtype=np.float32)
    scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
    class_ids = np.array([2, 2, 2], dtype=np.int64)
    keep = detector.nms(boxes, scores, class_ids, iou_threshold=0.5)
    assert len(keep) == 3


def test_nms_suppresses_exact_duplicates(detector):
    boxes = np.array([
        [0, 0, 10, 10],
        [0, 0, 10, 10],
        [0, 0, 10, 10],
    ], dtype=np.float32)
    scores = np.array([0.9, 0.85, 0.8], dtype=np.float32)
    class_ids = np.array([2, 2, 2], dtype=np.int64)
    keep = detector.nms(boxes, scores, class_ids, iou_threshold=0.5)
    assert len(keep) == 1
    assert keep[0] == 0


def test_nms_class_agnostic_suppresses_cross_class_overlap(detector):
    """Class-agnostic NMS: overlapping boxes of any class compete, only the best survives."""
    boxes = np.array([
        [0, 0, 10, 10],
        [1, 1, 11, 11],
    ], dtype=np.float32)
    scores = np.array([0.9, 0.8], dtype=np.float32)
    class_ids = np.array([0, 24], dtype=np.int64)  # person, backpack
    keep = detector.nms(boxes, scores, class_ids, iou_threshold=0.5, class_agnostic=True)
    assert len(keep) == 1


def test_nms_class_specific_keeps_cross_class_detections(detector):
    """Class-specific NMS: overlapping person + backpack are independent and both survive."""
    boxes = np.array([
        [0, 0, 10, 10],
        [1, 1, 11, 11],
    ], dtype=np.float32)
    scores = np.array([0.9, 0.8], dtype=np.float32)
    class_ids = np.array([0, 24], dtype=np.int64)  # person, backpack
    keep = detector.nms(
        boxes, scores, class_ids, iou_threshold=0.5, class_agnostic=False
    )
    assert len(keep) == 2


def test_nms_respects_max_detections(detector):
    boxes = np.array([[i, i, i + 5, i + 5] for i in range(100)], dtype=np.float32)
    scores = np.array([0.9 - i * 0.001 for i in range(100)], dtype=np.float32)
    class_ids = np.zeros(100, dtype=np.int64)
    keep = detector.nms(boxes, scores, class_ids, iou_threshold=0.01, max_detections=10)
    assert len(keep) == 10


def test_nms_crowded_same_class_many_survive(detector):
    """Many slightly overlapping cars in a parking lot should not be merged."""
    boxes = np.array([
        [i * 12, 0, i * 12 + 10, 10] for i in range(20)
    ], dtype=np.float32)
    scores = np.array([0.9] * 20, dtype=np.float32)
    class_ids = np.array([2] * 20, dtype=np.int64)  # car
    keep = detector.nms(boxes, scores, class_ids, iou_threshold=0.5, class_agnostic=True)
    # Each box is 10px wide, 2px apart → IoU is small, so all should be kept.
    assert len(keep) == 20


# ----------------------------------------------------------------------
# End-to-end detection post-processing (mocked ONNX)
# ----------------------------------------------------------------------


class _FakeSession:
    """ONNX-like session that returns a synthetic YOLOv8 output tensor."""

    def __init__(self, output: np.ndarray):
        self._output = output

    def run(self, _outputs, _inputs):
        return [self._output]


def _make_coco_output(
    boxes: list[tuple[float, float, float, float]],
    class_idx: int,
    confidence: float,
) -> np.ndarray:
    """Build a (1, 84, N) YOLOv8 output tensor with N detections."""
    num = len(boxes)
    out = np.zeros((1, 84, num), dtype=np.float32)
    for i, (cx, cy, w, h) in enumerate(boxes):
        out[0, 0, i] = cx
        out[0, 1, i] = cy
        out[0, 2, i] = w
        out[0, 3, i] = h
        out[0, 4 + class_idx, i] = confidence
    return out


def _make_mixed_output(
    detections: list[tuple[int, float, tuple[float, float, float, float]]],
) -> np.ndarray:
    """Build a (1, 84, N) tensor with detections of different classes."""
    num = len(detections)
    out = np.zeros((1, 84, num), dtype=np.float32)
    for i, (class_idx, conf, (cx, cy, w, h)) in enumerate(detections):
        out[0, 0, i] = cx
        out[0, 1, i] = cy
        out[0, 2, i] = w
        out[0, 3, i] = h
        out[0, 4 + class_idx, i] = conf
    return out


def test_detect_many_cars_in_one_frame(detector):
    """A single frame with many non-overlapping cars must return all of them."""
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    # 15 cars spread across the frame, each 60x40 px.
    car_boxes = [(40 + i * 40, 50, 60, 40) for i in range(15)]
    out = _make_coco_output(car_boxes, class_idx=2, confidence=0.75)
    det = detector.AIDetector("fake.onnx")
    det._session = _FakeSession(out)

    results = det.detect(frame, confidence=0.5)
    assert len(results) == 15
    for r in results:
        assert r["class"] == "car"
        assert r["confidence"] >= 0.5


def test_detect_many_people_in_one_frame(detector):
    """A crowded frame with many people must return all of them."""
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    person_boxes = [(30 + i * 35, 80, 25, 60) for i in range(12)]
    out = _make_coco_output(person_boxes, class_idx=0, confidence=0.82)
    det = detector.AIDetector("fake.onnx")
    det._session = _FakeSession(out)

    results = det.detect(frame, confidence=0.5)
    assert len(results) == 12
    for r in results:
        assert r["class"] == "person"


def test_detect_mixed_crowd(detector):
    """A frame with several cars and people must return all of them."""
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    detections = [
        (2, 0.8, (50, 50, 60, 40)),   # car
        (2, 0.75, (150, 60, 60, 40)),  # car
        (2, 0.78, (250, 55, 60, 40)),  # car
        (0, 0.85, (40, 120, 25, 60)),  # person
        (0, 0.88, (100, 130, 25, 60)), # person
        (0, 0.81, (300, 125, 25, 60)), # person
    ]
    out = _make_mixed_output(detections)
    det = detector.AIDetector("fake.onnx")
    det._session = _FakeSession(out)

    results = det.detect(frame, confidence=0.5)
    assert len(results) == 6
    assert sum(1 for r in results if r["class"] == "car") == 3
    assert sum(1 for r in results if r["class"] == "person") == 3


def test_detect_drops_low_confidence(detector):
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    boxes = [
        (50, 50, 60, 40),
        (150, 50, 60, 40),
    ]
    out = np.zeros((1, 84, 2), dtype=np.float32)
    out[0, 0, 0] = boxes[0][0]
    out[0, 1, 0] = boxes[0][1]
    out[0, 2, 0] = boxes[0][2]
    out[0, 3, 0] = boxes[0][3]
    out[0, 6, 0] = 0.85
    out[0, 0, 1] = boxes[1][0]
    out[0, 1, 1] = boxes[1][1]
    out[0, 2, 1] = boxes[1][2]
    out[0, 3, 1] = boxes[1][3]
    out[0, 6, 1] = 0.25
    det = detector.AIDetector("fake.onnx")
    det._session = _FakeSession(out)

    results = det.detect(frame, confidence=0.5)
    assert len(results) == 1
    assert results[0]["confidence"] == 0.85


def test_detect_coordinates_back_to_original_frame(detector):
    """Box coordinates must be returned in the original frame coordinate space."""
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    # A single box at the centre of the 640x640 letterboxed image.
    out = _make_coco_output([(320, 320, 100, 100)], class_idx=2, confidence=0.9)
    det = detector.AIDetector("fake.onnx")
    det._session = _FakeSession(out)

    results = det.detect(frame, confidence=0.5)
    assert len(results) == 1
    box = results[0]["box"]
    # With a 1280x720 frame scaled to fit 640, the image occupies 640x360
    # in the centre, padded by 140px top/bottom. The 320,320 letterboxed box
    # maps back to the original frame.
    assert box[0] >= 0 and box[2] <= 1280
    assert box[1] >= 0 and box[3] <= 720


def test_detect_no_session_returns_empty(detector):
    det = detector.AIDetector("fake.onnx")
    assert det.detect(np.zeros((100, 100, 3), dtype=np.uint8)) == []
