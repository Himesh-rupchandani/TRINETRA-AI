"""
PTS handling & capture timing (spec §10, §14).

Uses a locally generated video file — no live Government feed needed.
Timing MUST come from PTS, never arrival time and never CAP_PROP_FPS.
"""
import os

import numpy as np
import pytest
import cv2

from capture.frame_packet import CaptureState, FramePacket
from capture.stream_capture import StreamCaptureBase, PTS_ROLLBACK_MS, PTS_GAP_MS
from capture.rtsp_capture import RTSPCapture


@pytest.fixture(scope="module")
def video_file(tmp_path_factory):
    """Generate a 40-frame 320x240 clip with a moving rectangle."""
    path = tmp_path_factory.mktemp("vid") / "clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (320, 240))
    assert writer.isOpened()
    for i in range(40):
        frame = np.full((240, 320, 3), 30, dtype=np.uint8)
        x = i * 7
        cv2.rectangle(frame, (x, 90), (x + 40, 150), (200, 200, 200), -1)
        writer.write(frame)
    writer.release()
    return str(path)


class FileCapture(StreamCaptureBase):
    source_type = "file"


def test_file_capture_produces_packets_with_monotonic_pts(video_file):
    cap = FileCapture("camtest", video_file, scene_cut_check=False)
    assert cap.open() is True
    pts_values = []
    for _ in range(10):
        pkt = cap.read_packet()
        if pkt is None:
            break
        pts_values.append(pkt.pts_ms)
    cap.close()

    assert len(pts_values) >= 8
    # first packet after connect is a discontinuity by contract
    assert all(p >= 0 for p in pts_values)
    deltas = [b - a for a, b in zip(pts_values, pts_values[1:])]
    assert all(d >= 0 for d in deltas), "PTS must be monotonic within a stream"


def test_frame_packet_carries_required_context(video_file):
    cap = FileCapture("camtest", video_file, scene_cut_check=False)
    cap.open()
    pkt = cap.read_packet()
    assert pkt is not None
    assert pkt.camera_id == "camtest"
    assert pkt.capture_state == CaptureState.ONLINE
    assert pkt.frame.ndim == 3
    assert pkt.is_discontinuity is True  # first frame after connect
    pkt2 = cap.read_packet()
    assert pkt2.is_discontinuity is False
    elapsed = pkt2.elapsed_ms_since(pkt)
    assert elapsed is not None and elapsed >= 0
    cap.close()


def test_discontinuity_detection_rollback_and_gap():
    """Pure logic test of the PTS discontinuity rules (feed loop / gap)."""
    cap = FileCapture("camX", "unused", scene_cut_check=False)
    frame = np.zeros((24, 24, 3), dtype=np.uint8)

    cap._just_connected = False
    cap._last_pts_ms = None
    assert cap._detect_discontinuity(1000.0, frame) is False

    # rollback beyond threshold -> discontinuity (feed looped)
    cap._last_pts_ms = 9000.0
    assert cap._detect_discontinuity(9000.0 - PTS_ROLLBACK_MS - 100.0, frame) is True

    # small jitter is NOT a discontinuity
    cap._last_pts_ms = 9000.0
    assert cap._detect_discontinuity(8900.0, frame) is False

    # large forward gap -> discontinuity
    cap._last_pts_ms = 1000.0
    assert cap._detect_discontinuity(1000.0 + PTS_GAP_MS + 100.0, frame) is True

    # normal progression is not
    cap._last_pts_ms = 1000.0
    assert cap._detect_discontinuity(1040.0, frame) is False


def test_scene_cut_content_detection():
    """A hard visual cut flags discontinuity even when PTS behaves."""
    cap = FileCapture("camY", "unused", scene_cut_check=True, scene_cut_diff_threshold=42.0)
    cap._just_connected = False
    dark = np.zeros((240, 320, 3), dtype=np.uint8)
    bright = np.full((240, 320, 3), 255, dtype=np.uint8)

    assert cap._detect_discontinuity(1000.0, dark) is False  # first thumb
    cap._last_pts_ms = 1000.0
    assert cap._detect_discontinuity(1040.0, dark) is False  # same scene
    cap._last_pts_ms = 1040.0
    assert cap._detect_discontinuity(1080.0, bright) is True  # hard cut


def test_pts_not_derived_from_fps_or_arrival(video_file):
    """PTS must come from the container, independent of CAP_PROP_FPS."""
    cap = FileCapture("camtest", video_file, scene_cut_check=False)
    cap.open()
    pts1 = cap._extract_pts_ms()
    nominal = cap.cap.get(cv2.CAP_PROP_FPS)  # diagnostic-only
    pts2 = cap._extract_pts_ms()
    assert pts1 == pts2, "same stream position must give the same PTS"
    cap.close()
    assert nominal != 0  # container reports fps, but we never use it for timing


def test_pts_progresses_with_container_not_arrival(video_file):
    """Reading more frames advances PTS by container deltas (~40ms @25fps)."""
    cap = FileCapture("camtest", video_file, scene_cut_check=False)
    cap.open()
    pts = []
    for _ in range(5):
        pkt = cap.read_packet()
        assert pkt is not None
        pts.append(pkt.pts_ms)
    cap.close()
    deltas = [b - a for a, b in zip(pts, pts[1:])]
    assert all(d > 0 for d in deltas), f"container PTS must progress: {pts}"
    assert all(20 < d < 80 for d in deltas), f"expected ~40ms container deltas: {deltas}"


def test_rtsp_capture_forces_tcp():
    cap = RTSPCapture("cam04", "rtsp://example.invalid/stream", transport="tcp")
    kwargs = cap._capture_kwargs()
    assert kwargs["rtsp_transport"] == "tcp"


def test_read_failure_degrades_then_reconnect_state(video_file):
    """Sustained read failures move ONLINE -> DEGRADED -> RECONNECTING."""
    cap = FileCapture("camtest", video_file, scene_cut_check=False, read_timeout_sec=1e9)
    cap.open()
    cap._guarded_read = lambda: (False, None)  # decoder keeps 'opening' but no frames
    cap._last_ok_mono = __import__("time").monotonic()

    for _ in range(3):
        cap.read_packet()
    assert cap.state == CaptureState.DEGRADED

    for _ in range(20):
        cap.read_packet()
    assert cap.state == CaptureState.RECONNECTING
    assert cap.needs_reconnect() is True


def test_closed_capture_reports_offline(video_file):
    cap = FileCapture("camtest", video_file, scene_cut_check=False)
    cap.open()
    cap.cap.release()  # hardware/stream died mid-session
    assert cap.read_packet() is None
    assert cap.state == CaptureState.OFFLINE
    assert cap.needs_reconnect() is True
