"""Tests for ai-engine: RTSP URL building, confidence clamp, detection cooldown.

ai-engine's `app` package is loaded under an alias to avoid colliding with
the API service's own `app` package on sys.path. numpy-dependent detector
tests are skipped when numpy is unavailable.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed in this environment")

AI_APP_DIR = Path(__file__).resolve().parents[2] / "ai-engine" / "app"


@pytest.fixture(scope="module")
def ai_engine():
    spec = importlib.util.spec_from_file_location(
        "ai_engine_app",
        AI_APP_DIR / "__init__.py",
        submodule_search_locations=[str(AI_APP_DIR)],
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["ai_engine_app"] = pkg
    spec.loader.exec_module(pkg)
    yield pkg


@pytest.fixture(scope="module")
def sampler(ai_engine):
    return importlib.import_module("ai_engine_app.frame_sampler")


@pytest.fixture(scope="module")
def detector(ai_engine):
    return importlib.import_module("ai_engine_app.detector")


def _make_sampler(sampler, **kwargs):
    params = {
        "camera_id": "00000000-0000-0000-0000-000000000001",
        "camera_name": "testcam",
        "stream_uri": "rtsp://10.0.0.5/sub",
        "username": None,
        "password": None,
        "ai_objects": None,
        "ai_sensitivity": "medium",
        "ai_min_confidence": 0.5,
    }
    params.update(kwargs)
    return sampler.FrameSampler(**params)


# ----------------------------------------------------------------------
# RTSP URL building
# ----------------------------------------------------------------------


def test_rtsp_url_embeds_credentials(sampler):
    url = sampler.build_rtsp_url("rtsp://10.0.0.5:554/sub", "admin", "pw")
    assert url == "rtsp://admin:pw@10.0.0.5:554/sub"


def test_rtsp_url_no_creds(sampler):
    assert sampler.build_rtsp_url("rtsp://10.0.0.5/sub", None, None) == "rtsp://10.0.0.5/sub"


# ----------------------------------------------------------------------
# Confidence clamp
# ----------------------------------------------------------------------


def test_confidence_clamp_invalid_high(sampler):
    s = _make_sampler(sampler, ai_min_confidence=2.0)
    assert s.ai_min_confidence == 0.5


def test_confidence_default_when_none(sampler):
    s = _make_sampler(sampler, ai_min_confidence=None)
    assert s.ai_min_confidence == 0.5


def test_confidence_valid_kept(sampler):
    s = _make_sampler(sampler, ai_min_confidence=0.7)
    assert s.ai_min_confidence == 0.7


# ----------------------------------------------------------------------
# Cooldown filtering
# ----------------------------------------------------------------------


def test_cooldown_first_detection_passes(sampler):
    s = _make_sampler(sampler)
    dets = [{"class": "car", "confidence": 0.9, "box": [0, 0, 10, 10]}]
    assert len(s._apply_cooldown(dets, 640, 360)) == 1


def test_cooldown_static_repeat_filtered(sampler):
    """Static object (same position) is filtered within the cooldown window."""
    s = _make_sampler(sampler)
    dets = [{"class": "car", "confidence": 0.9, "box": [0, 0, 10, 10]}]
    s._apply_cooldown(dets, 640, 360)
    s._last_events["car"] = (s._last_events["car"][0] - sampler.MIN_EVENT_GAP_S - 1, *s._last_events["car"][1:])
    assert s._apply_cooldown(dets, 640, 360) == []


def test_cooldown_moved_object_is_new_event(sampler):
    """Object that moved significantly counts as a new event."""
    s = _make_sampler(sampler)
    s._apply_cooldown([{"class": "car", "confidence": 0.9, "box": [0, 0, 10, 10]}], 640, 360)
    s._last_events["car"] = (s._last_events["car"][0] - sampler.MIN_EVENT_GAP_S - 1, *s._last_events["car"][1:])
    moved = [{"class": "car", "confidence": 0.9, "box": [300, 100, 310, 110]}]
    assert len(s._apply_cooldown(moved, 640, 360)) == 1


def test_cooldown_per_class(sampler):
    s = _make_sampler(sampler)
    s._apply_cooldown([{"class": "car", "confidence": 0.9, "box": [0, 0, 10, 10]}], 640, 360)
    other = [{"class": "person", "confidence": 0.9, "box": [0, 0, 10, 10]}]
    assert len(s._apply_cooldown(other, 640, 360)) == 1  # different class not blocked


# ----------------------------------------------------------------------
# Letterbox geometry
# ----------------------------------------------------------------------


def test_letterbox_output_shape(detector):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    blob, scale, pad_x, pad_y = detector._letterbox(frame)
    assert blob.shape == (1, 3, 640, 640)
    assert scale == pytest.approx(1.0)
    assert pad_y == pytest.approx(80.0)


def test_letterbox_wide_image(detector):
    frame = np.zeros((360, 1280, 3), dtype=np.uint8)
    blob, scale, pad_x, pad_y = detector._letterbox(frame)
    assert blob.shape == (1, 3, 640, 640)
    assert scale == pytest.approx(0.5)
    assert pad_x == pytest.approx(0.0)
    assert pad_y == pytest.approx(160.0)


def test_detector_not_ready_without_model(detector):
    det = detector.AIDetector("nonexistent_model.onnx")
    assert det.ready is False
    assert det.detect(np.zeros((100, 100, 3), dtype=np.uint8)) == []
