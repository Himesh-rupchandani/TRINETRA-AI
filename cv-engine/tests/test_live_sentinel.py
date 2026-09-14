"""
REAL LIVE SENTINEL TESTS (spec §35).

These tests touch the actual Government feed at cctv.corp8.cloud. They are
NOT run in CI: they require network access to the Sentinel infrastructure
and are non-deterministic. Enable explicitly:

    TRINETRA_LIVE=1 pytest tests/test_live_sentinel.py -v

Nothing in the offline suite pretends to be live. If these tests skip, the
pipeline has NOT been validated against the real feed — say so in reports.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LIVE = os.environ.get("TRINETRA_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="live Sentinel tests disabled (set TRINETRA_LIVE=1 to run against the real feed)",
)


@pytest.mark.live
def test_live_catalogue_fetch():
    from capture.sentinel_catalogue import SentinelCatalogue

    cat = SentinelCatalogue(timeout_sec=15.0)
    cameras = cat.fetch()
    assert len(cameras) > 0
    ids = {c.camera_id.lower() for c in cameras}
    print(f"\nLIVE catalogue: {len(cameras)} cameras: {sorted(ids)[:10]}...")


@pytest.mark.live
def test_live_cam04_rtsp_capture_and_pts():
    """Open the real cam04 RTSP over TCP, read frames, verify PTS progresses."""
    from capture.reconnect import ManagedCapture
    from capture.sentinel_catalogue import SentinelCatalogue
    from config.settings import Settings

    settings = Settings.from_env()
    settings.reconnect_max_attempts = 2
    cat = SentinelCatalogue(timeout_sec=15.0)
    cat.fetch()
    cam = cat.get_camera("cam04")
    assert cam is not None, "cam04 must exist in the live catalogue"

    managed = ManagedCapture(cam, settings)
    packets = []
    for pkt in managed.packets():
        packets.append(pkt)
        if len(packets) >= 10:
            break
    managed.stop()

    assert len(packets) == 10, "expected 10 real frames from cam04"
    pts = [p.pts_ms for p in packets]
    assert all(p >= 0 for p in pts)
    assert any(b >= a for a, b in zip(pts, pts[1:])), "PTS should generally progress"
    print(f"\nLIVE cam04: 10 frames, PTS span {pts[-1]-pts[0]:.0f}ms, shape {packets[0].frame.shape}")


@pytest.mark.live
def test_live_yolo_on_real_frame():
    """Detection sanity check on a genuine Sentinel frame (requires model weights)."""
    from capture.reconnect import ManagedCapture
    from capture.sentinel_catalogue import SentinelCatalogue
    from config.settings import Settings
    from detection.vehicle_detector import VehicleDetector

    settings = Settings.from_env()
    settings.reconnect_max_attempts = 2
    cat = SentinelCatalogue(timeout_sec=15.0)
    cat.fetch()
    cam = cat.get_camera("cam04")
    managed = ManagedCapture(cam, settings)
    pkt = next(iter(managed.packets()))
    managed.stop()

    detector = VehicleDetector(model_path=settings.model_path, conf_threshold=0.3)
    dets = detector.detect(pkt.frame, camera_id=cam.camera_id, pts_ms=pkt.pts_ms)
    # Not asserting count: real scenes vary. Only that inference runs cleanly.
    assert isinstance(dets, list)
    print(f"\nLIVE YOLO: {len(dets)} vehicle(s) on real cam04 frame")
