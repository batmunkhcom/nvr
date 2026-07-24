"""Tests for recording-engine: RTSP URL building, FFmpeg args, catalog parsing,
retention protection rules.

recording-engine's `app` package is loaded under an alias to avoid colliding
with the API service's own `app` package on sys.path.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

REC_APP_DIR = Path(__file__).resolve().parents[2] / "recording-engine" / "app"


@pytest.fixture(scope="module")
def rec_engine():
    spec = importlib.util.spec_from_file_location(
        "rec_engine",
        REC_APP_DIR / "__init__.py",
        submodule_search_locations=[str(REC_APP_DIR)],
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["rec_engine"] = pkg
    spec.loader.exec_module(pkg)
    yield pkg


@pytest.fixture(scope="module")
def recorder(rec_engine):
    return importlib.import_module("rec_engine.recorder")


@pytest.fixture(scope="module")
def catalog(rec_engine):
    return importlib.import_module("rec_engine.catalog")


@pytest.fixture(scope="module")
def retention(rec_engine):
    return importlib.import_module("rec_engine.retention")


# ----------------------------------------------------------------------
# recorder.build_rtsp_url
# ----------------------------------------------------------------------


def test_rtsp_url_embeds_credentials(recorder):
    url = recorder.build_rtsp_url("rtsp://10.0.0.5:554/stream1", "admin", "pass123")
    assert url == "rtsp://admin:pass123@10.0.0.5:554/stream1"


def test_rtsp_url_preserves_query_string(recorder):
    """Dahua-style URIs need ?channel=1&subtype=1 preserved."""
    url = recorder.build_rtsp_url(
        "rtsp://10.0.0.5:554/cam/realmonitor?channel=1&subtype=1", "admin", "pw"
    )
    assert url == "rtsp://admin:pw@10.0.0.5:554/cam/realmonitor?channel=1&subtype=1"


def test_rtsp_url_quotes_special_chars(recorder):
    url = recorder.build_rtsp_url("rtsp://10.0.0.5/stream", "admin", "p@ss/word")
    assert "p%40ss%2Fword" in url


def test_rtsp_url_keeps_existing_credentials(recorder):
    original = "rtsp://user:pw@10.0.0.5/stream"
    assert recorder.build_rtsp_url(original, "admin", "other") == original


def test_rtsp_url_no_password_unchanged(recorder):
    original = "rtsp://10.0.0.5/stream"
    assert recorder.build_rtsp_url(original, "admin", None) == original


# ----------------------------------------------------------------------
# recorder.build_ffmpeg_args
# ----------------------------------------------------------------------


def test_ffmpeg_args_segment_settings(recorder, tmp_path):
    args = recorder.build_ffmpeg_args("rtsp://x/stream", str(tmp_path), 300)
    joined = " ".join(args)
    assert "-c:v copy" in joined
    assert "-segment_time 300" in joined
    assert "-strftime 1" in joined
    assert "-rtsp_transport tcp" in joined
    assert "%Y/%m/%d" in joined  # strftime directory pattern


# ----------------------------------------------------------------------
# catalog filename parsing
# ----------------------------------------------------------------------


def test_parse_start_time_valid(catalog):
    ts = catalog._parse_start_time("20260724_153045.mp4")
    assert ts is not None
    assert (ts.year, ts.month, ts.day) == (2026, 7, 24)
    assert (ts.hour, ts.minute, ts.second) == (15, 30, 45)
    assert ts.tzinfo is not None


def test_parse_start_time_invalid(catalog):
    assert catalog._parse_start_time("random.mp4") is None
    assert catalog._parse_start_time("20269999_153045.mp4") is None
    assert catalog._parse_start_time("no_date_here.txt") is None


def test_filename_regex(catalog):
    assert catalog.FILENAME_RE.search("/data/recordings/abc/2026/07/24/20260724_000000.mp4")


# ----------------------------------------------------------------------
# retention deletion protection
# ----------------------------------------------------------------------


def test_is_deletable_old_file(retention, tmp_path):
    f = tmp_path / "old.mp4"
    f.write_bytes(b"x" * 100)
    old = time.time() - (retention.PROTECT_SECONDS + 60)
    os.utime(f, (old, old))
    assert retention.RetentionManager._is_deletable(str(f)) is True


def test_is_deletable_young_file_protected(retention, tmp_path):
    f = tmp_path / "new.mp4"
    f.write_bytes(b"x" * 100)  # just written -> protected
    assert retention.RetentionManager._is_deletable(str(f)) is False


def test_is_deletable_missing_file(retention):
    assert retention.RetentionManager._is_deletable("/nonexistent/file.mp4") is True
