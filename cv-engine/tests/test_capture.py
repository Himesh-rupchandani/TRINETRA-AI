"""Capture behaviour: real decode path, PTS, TCP enforcement, fallback.

The decode tests use a locally generated mp4, so they exercise the real
OpenCV/FFmpeg pipeline without touching a government feed. Live RTSP/HLS
behaviour is covered by ``tests/integration/test_live_sentinel.py`` (marked
``integration`` and skipped unless ``TRINETRA_LIVE=1``).
"""

from __future__ import annotations

import os
import time

import pytest

from capture.capture_factory import FallbackCapture, build_capture, make_capture_factory
from capture.file_capture import FileCapture, write_test_video
from capture.frames import STATE_OK
from capture.hls_capture import HlsCapture, open_hls
from capture.rtsp_capture import RTSP_FFMPEG_OPTIONS, RtspCapture, open_rtsp
from capture.sentinel_catalogue import Camera
from capture.stream_capture import OpenCVStreamCapture, PyAVStreamCapture


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    return write_test_video(tmp_path_factory.mktemp("video") / "sample.mp4", frame_count=25, fps=25.0)


def _camera(**kw) -> Camera:
    base = dict(
        camera_id="cam04",
        name="Paldi Circle",
        latitude=23.0126,
        longitude=72.5647,
        codec="H264",
        fps=25.0,
        rtsp_url="rtsp://103.250.160.189:8554/stream/cam04",
        hls_url="https://cctv.corp8.cloud/cam04/index.m3u8",
    )
    base.update(kw)
    return Camera(**base)


# ---------------------------------------------------------------------------
# real decode path
# ---------------------------------------------------------------------------


def test_decodes_every_frame_with_monotonic_pts(sample_video, settings):
    cap = FileCapture(sample_video, settings, camera_id="cam04", fps_hint=25.0)
    assert cap.open() is True
    packets = []
    while True:
        packet = cap.read()
        if packet is None:
            break
        packets.append(packet)
    cap.close()

    assert len(packets) == 25
    pts = [p.pts_ms for p in packets]
    assert pts == sorted(pts), "PTS must be monotonic"
    assert pts[0] < pts[-1]
    assert all(p.camera_id == "cam04" for p in packets)
    assert all(p.capture_state == STATE_OK for p in packets)
    assert all(p.source == "file" for p in packets)
    assert all(p.pts_valid for p in packets)
    assert packets[0].seq == 1 and packets[-1].seq == 25
    assert (packets[0].width, packets[0].height) == (320, 240)


def test_pts_spacing_matches_the_container_not_the_wall_clock(sample_video, settings):
    cap = FileCapture(sample_video, settings, fps_hint=25.0)
    assert cap.open()
    deltas = []
    previous = None
    while True:
        packet = cap.read()
        if packet is None:
            break
        if previous is not None:
            deltas.append(packet.continuous_ms - previous)
        previous = packet.continuous_ms
        time.sleep(0.01)  # decode slower than real time on purpose
    cap.close()

    assert deltas, "expected inter-frame deltas"
    # 25 fps -> 40 ms. Reading slowly must not change the measured spacing,
    # which is the whole point of using PTS instead of arrival time.
    assert 30.0 <= sum(deltas) / len(deltas) <= 55.0
    assert 20.0 <= cap.stats.delivered_fps <= 30.0


def test_read_returns_none_once_the_stream_ends(sample_video, settings):
    cap = FileCapture(sample_video, settings)
    assert cap.open()
    for _ in range(25):
        assert cap.read() is not None
    assert cap.read() is None
    assert cap.stats.frames_read == 25


def test_missing_file_is_reported_as_a_closed_capture(settings, tmp_path):
    cap = FileCapture(tmp_path / "does-not-exist.mp4", settings)
    assert cap.open() is False


# ---------------------------------------------------------------------------
# transport configuration
# ---------------------------------------------------------------------------


def test_rtsp_open_forces_tcp_transport(monkeypatch, settings):
    import cv2

    seen = {}

    class FakeCap:
        def __init__(self, url, backend=None, params=None):
            seen["url"] = url
            seen["params"] = params
            seen["env"] = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")

        def isOpened(self):
            return True

        def get(self, prop):
            return 0.0

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", FakeCap)
    cap = RtspCapture(_camera(), settings)
    assert cap.open() is True
    assert "rtsp_transport;tcp" in seen["env"]
    assert seen["url"] == "rtsp://103.250.160.189:8554/stream/cam04"
    # The process environment must not be left modified.
    assert "OPENCV_FFMPEG_CAPTURE_OPTIONS" not in os.environ
    assert "rtsp_transport;tcp" in RTSP_FFMPEG_OPTIONS


def test_open_timeout_parameters_are_passed_when_supported(monkeypatch, settings):
    import cv2

    seen = {}

    class FakeCap:
        def __init__(self, url, backend=None, params=None):
            seen["params"] = params

        def isOpened(self):
            return True

        def get(self, prop):
            return 0.0

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", FakeCap)
    monkeypatch.setattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC", 12345, raising=False)
    monkeypatch.setattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC", 12346, raising=False)
    assert RtspCapture(_camera(), settings).open() is True
    assert seen["params"] == [12345, int(settings.capture_open_timeout_s * 1000),
                              12346, int(settings.read_timeout_s * 1000)]


def test_hls_capture_selects_the_m3u8_url(settings):
    cap = HlsCapture(_camera(), settings)
    assert cap.url() == "https://cctv.corp8.cloud/cam04/index.m3u8"
    assert cap.source == "hls"


def test_unreachable_rtsp_fails_cleanly_without_raising(settings):
    settings.capture_open_timeout_s = 1.0
    settings.read_timeout_s = 1.0
    cap = RtspCapture(_camera(rtsp_url="rtsp://127.0.0.1:1/stream/cam04"), settings)
    assert cap.open() is False
    assert cap.stats.decode_failures >= 1


def test_capture_without_a_url_is_refused(settings):
    cap = RtspCapture(_camera(rtsp_url=None), settings)
    assert cap.open() is False


# ---------------------------------------------------------------------------
# transport selection / fallback
# ---------------------------------------------------------------------------


def test_build_capture_honours_the_requested_transport(settings):
    assert build_capture(_camera(), settings, "rtsp").source == "rtsp"
    assert build_capture(_camera(), settings, "hls").source == "hls"


def test_fallback_capture_switches_to_hls_when_rtsp_fails(monkeypatch, settings):
    import capture.capture_factory as factory

    class Dead:
        source = "rtsp"
        stats = None
        timeline = None

        def open(self):
            return False

        def read(self):  # pragma: no cover
            return None

        def close(self):
            pass

    class Alive:
        source = "hls"
        stats = None
        timeline = None

        def open(self):
            return True

        def read(self):  # pragma: no cover
            return None

        def close(self):
            pass

    monkeypatch.setattr(factory, "open_rtsp", lambda c, s: Dead())
    monkeypatch.setattr(factory, "open_hls", lambda c, s: Alive())

    cap = FallbackCapture(_camera(), settings)
    assert cap.open() is True
    assert cap.active_source == "hls"


def test_fallback_is_disabled_when_the_setting_says_so(settings):
    settings.allow_hls_fallback = False
    capture = make_capture_factory(_camera(), settings)()
    assert isinstance(capture, OpenCVStreamCapture)
    assert capture.source == "rtsp"


def test_backend_selection_follows_the_configuration(settings):
    settings.capture_backend = "opencv"
    assert isinstance(open_rtsp(_camera(), settings), RtspCapture)
    assert isinstance(open_hls(_camera(), settings), HlsCapture)

    settings.capture_backend = "auto"
    chosen = open_rtsp(_camera(), settings)
    if PyAVStreamCapture.available():
        assert isinstance(chosen, PyAVStreamCapture)
    else:
        # No PyAV installed: the engine must still run on OpenCV.
        assert isinstance(chosen, RtspCapture)
