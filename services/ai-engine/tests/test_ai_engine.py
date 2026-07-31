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


@pytest.fixture(scope="module")
def ai_main(ai_engine):
    return importlib.import_module("ai_engine_app.main")


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
# AI stream selection (recording_stream reuse)
# ----------------------------------------------------------------------


def test_resolve_ai_stream_defaults_to_sub(ai_main):
    cam = {
        "id": "00000000-0000-0000-0000-000000000001",
        "stream_main_uri": "rtsp://10.0.0.1/main",
        "stream_sub_uri": "rtsp://10.0.0.1/sub",
        "recording_stream": None,
    }
    use_main, stream_uri, relay_key = ai_main._resolve_ai_stream(cam)
    assert use_main is False
    assert stream_uri == "rtsp://10.0.0.1/sub"
    assert relay_key == "00000000-0000-0000-0000-000000000001_sub"


def test_resolve_ai_stream_sub_explicit(ai_main):
    cam = {
        "id": "00000000-0000-0000-0000-000000000001",
        "stream_main_uri": "rtsp://10.0.0.1/main",
        "stream_sub_uri": "rtsp://10.0.0.1/sub",
        "recording_stream": "sub",
    }
    use_main, stream_uri, relay_key = ai_main._resolve_ai_stream(cam)
    assert use_main is False
    assert stream_uri == "rtsp://10.0.0.1/sub"
    assert relay_key.endswith("_sub")


def test_resolve_ai_stream_main(ai_main):
    cam = {
        "id": "00000000-0000-0000-0000-000000000001",
        "stream_main_uri": "rtsp://10.0.0.1/main",
        "stream_sub_uri": "rtsp://10.0.0.1/sub",
        "recording_stream": "main",
    }
    use_main, stream_uri, relay_key = ai_main._resolve_ai_stream(cam)
    assert use_main is True
    assert stream_uri == "rtsp://10.0.0.1/main"
    assert not relay_key.endswith("_sub")


def test_resolve_ai_stream_main_fallback(ai_main):
    cam = {
        "id": "00000000-0000-0000-0000-000000000001",
        "stream_main_uri": None,
        "stream_sub_uri": "rtsp://10.0.0.1/sub",
        "recording_stream": "main",
    }
    use_main, stream_uri, relay_key = ai_main._resolve_ai_stream(cam)
    assert use_main is True
    assert stream_uri == "rtsp://10.0.0.1/sub"


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
    assert s.ai_min_confidence == 0.95


def test_confidence_default_when_none(sampler):
    s = _make_sampler(sampler, ai_min_confidence=None)
    assert s.ai_min_confidence == 0.25


def test_confidence_default_respects_env_var(monkeypatch, sampler):
    monkeypatch.setenv("AI_CONFIDENCE_THRESHOLD", "0.45")
    s = _make_sampler(sampler, ai_min_confidence=None)
    assert s.ai_min_confidence == 0.45


def test_confidence_valid_kept(sampler):
    s = _make_sampler(sampler, ai_min_confidence=0.7)
    assert s.ai_min_confidence == 0.7


# ----------------------------------------------------------------------
# Tracking / cooldown filtering
# ----------------------------------------------------------------------


def test_tracking_first_detection_passes(sampler):
    s = _make_sampler(sampler)
    dets = [
        {"class": "car", "confidence": 0.9, "box": [0, 0, 50, 50]},
        {"class": "car", "confidence": 0.9, "box": [300, 100, 350, 150]},
    ]
    assert len(s._apply_tracking(dets, 640, 360)) == 2


def test_tracking_immediate_repeat_suppressed(sampler):
    """Static object (same position) is filtered within the cooldown window."""
    s = _make_sampler(sampler)
    dets = [{"class": "car", "confidence": 0.9, "box": [0, 0, 50, 50]}]
    assert len(s._apply_tracking(dets, 640, 360)) == 1
    assert s._apply_tracking(dets, 640, 360) == []


def test_tracking_per_class(sampler):
    s = _make_sampler(sampler)
    s._apply_tracking([{"class": "car", "confidence": 0.9, "box": [0, 0, 50, 50]}], 640, 360)
    other = [{"class": "person", "confidence": 0.9, "box": [0, 0, 50, 50]}]
    assert len(s._apply_tracking(other, 640, 360)) == 1  # different class not blocked


# ----------------------------------------------------------------------
# Letterbox geometry
# ----------------------------------------------------------------------


def test_letterbox_output_shape(detector):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    blob, scale, _pad_x, pad_y = detector._letterbox(frame)
    assert blob.shape == (1, 3, 640, 640)
    assert scale == pytest.approx(1.0)
    assert pad_y == pytest.approx(80.0)


def test_letterbox_wide_image(detector):
    frame = np.zeros((360, 1280, 3), dtype=np.uint8)
    blob, scale, pad_x, pad_y = detector._letterbox(frame)
    assert blob.shape == (1, 3, 640, 640)
    assert scale == pytest.approx(0.5)
    assert pad_x == pytest.approx(0.0)
    assert pad_y == pytest.approx(230.0)


def test_detector_not_ready_without_model(detector):
    det = detector.AIDetector("nonexistent_model.onnx")
    assert det.ready is False
    assert det.detect(np.zeros((100, 100, 3), dtype=np.uint8)) == []


# ----------------------------------------------------------------------
# Zone filtering (cv2 required)
# ----------------------------------------------------------------------

cv2 = pytest.importorskip("cv2", reason="opencv not installed in this environment")


def _zone(x1, y1, x2, y2):
    """Rectangle zone as normalized polygon."""
    return {"name": "z", "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]}


def _det(x1, y1, x2, y2, cls="car"):
    return {"class": cls, "confidence": 0.9, "box": [x1, y1, x2, y2]}


def test_zones_empty_passes_all(sampler):
    s = _make_sampler(sampler, ai_zones=[])
    dets = [_det(0, 0, 100, 100), _det(500, 300, 600, 350)]
    assert len(s._filter_zones(dets, 640, 360)) == 2


def test_zones_keeps_detection_inside(sampler):
    s = _make_sampler(sampler, ai_zones=[_zone(0.0, 0.0, 0.5, 1.0)])  # left half
    inside = _det(50, 100, 100, 150)  # bottom-center (75, 150) -> inside left half
    assert len(s._filter_zones([inside], 640, 360)) == 1


def test_zones_filters_outside(sampler):
    s = _make_sampler(sampler, ai_zones=[_zone(0.0, 0.0, 0.5, 1.0)])  # left half
    outside = _det(500, 100, 600, 150)  # bottom-center (550, 150) -> right half
    assert s._filter_zones([outside], 640, 360) == []


def test_zones_uses_bottom_center_anchor(sampler):
    """Object standing ON the zone edge: top half outside, feet inside -> kept."""
    s = _make_sampler(sampler, ai_zones=[_zone(0.0, 0.5, 1.0, 1.0)])  # bottom half
    standing = _det(100, 100, 150, 200)  # bottom edge y=200 of 360 -> inside bottom half
    assert len(s._filter_zones([standing], 640, 360)) == 1


def test_zones_invalid_polygon_ignored(sampler):
    s = _make_sampler(sampler, ai_zones=[{"name": "bad", "points": [[0, 0], [1, 1]]}])
    assert s.ai_zones == []  # <3 points -> dropped at init
    assert len(s._filter_zones([_det(0, 0, 10, 10)], 640, 360)) == 1
