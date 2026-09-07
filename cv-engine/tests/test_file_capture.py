"""
Unit tests for the recorded-video capture source (Phase 23.1: "video opens").

Fixtures are tiny generated clips — the suite never depends on the large
Faculty-Parking video (that run is a separate, explicitly marked manual test).
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from capture.file_capture import VideoFileSource, probe_video  # noqa: E402
from capture.frame_packet import CaptureState  # noqa: E402


def make_clip(path, frames=30, fps=10.0, size=(160, 120)):
    w, h = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    assert writer.isOpened()
    for i in range(frames):
        frame = np.full((h, w, 3), (i * 3) % 255, dtype=np.uint8)
        cv2.rectangle(frame, (10 + i, 20), (40 + i, 60), (0, 0, 255), -1)
        writer.write(frame)
    writer.release()
    return path


@pytest.fixture()
def clip(tmp_path):
    return make_clip(tmp_path / "clip.mp4", frames=30, fps=10.0)


def test_probe_reports_real_properties(clip):
    p = probe_video(str(clip), measure_frames=10)
    assert p.opened is True
    assert (p.width, p.height) == (160, 120)
    assert p.fps_reported == pytest.approx(10.0, abs=0.5)
    assert p.frame_count_reported == 30
    assert p.duration_sec_reported == pytest.approx(3.0, abs=0.2)
    assert p.frames_decoded_in_probe == 10
    assert p.fourcc  # codec actually reported, not guessed


def test_probe_missing_file_is_reported_not_raised(tmp_path):
    p = probe_video(str(tmp_path / "nope.mp4"))
    assert p.opened is False
    assert p.error


def test_frames_decode_with_monotonic_pts(clip):
    src = VideoFileSource(str(clip), camera_id="cam-test")
    packets = list(src.frames())
    assert len(packets) == 30
    assert src.stats.frames_read == 30
    pts = [p.pts_ms for p in packets]
    assert pts == sorted(pts)
    assert packets[0].camera_id == "cam-test"
    assert packets[0].source_type == "file"
    assert packets[0].capture_state is CaptureState.ONLINE
    assert packets[0].frame.shape == (120, 160, 3)


def test_frame_skip_yields_every_nth_frame(clip):
    src = VideoFileSource(str(clip), frame_skip=3)
    packets = list(src.frames())
    assert len(packets) == 10
    assert [p.sequence_number for p in packets][:4] == [0, 3, 6, 9]


def test_analysis_window_limits_duration(clip):
    src = VideoFileSource(str(clip), start_sec=0.0, duration_sec=1.0)
    packets = list(src.frames())
    assert 0 < len(packets) <= 12  # ~10 fps for 1 second (+ boundary frame)
    assert max(p.pts_ms for p in packets) <= 1100


def test_source_tolerates_a_truncated_file(tmp_path):
    """A corrupt tail must end the stream cleanly, not raise (Phase 22).

    An AVI/MJPG container is used because it stays openable after truncation
    (an MP4 loses its trailing 'moov' atom and cannot be opened at all — that
    case is covered by :func:`test_unopenable_file_raises_a_clear_error`).
    """
    path = tmp_path / "trunc.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (160, 120))
    assert writer.isOpened()
    for i in range(40):
        writer.write(np.full((120, 160, 3), (i * 5) % 255, dtype=np.uint8))
    writer.release()
    data = path.read_bytes()
    path.write_bytes(data[: int(len(data) * 0.5)])

    src = VideoFileSource(str(path))
    packets = list(src.frames())  # must not raise
    assert 0 < len(packets) < 40
    assert src.stats.decode_failures >= 1


def test_unopenable_file_raises_a_clear_error(tmp_path):
    bad = tmp_path / "not_a_video.mp4"
    bad.write_bytes(b"definitely not a video")
    src = VideoFileSource(str(bad))
    with pytest.raises(IOError):
        list(src.frames())
