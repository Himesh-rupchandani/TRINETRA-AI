"""LIVE Sentinel integration test.

Skipped by default. Enable with:  TRINETRA_LIVE=1 pytest tests/integration -k live

It is deliberately *not* part of CI: it needs real egress to the government
gateway and a reachable RTSP/HLS stream. It exists so a human can run one
command against the real feed and get a pass/fail plus measured numbers. It is
honest by construction — if the feed is unreachable it fails loudly, it never
pretends.
"""

from __future__ import annotations

import os
import time

import pytest

pytestmark = pytest.mark.integration

if os.environ.get("TRINETRA_LIVE") != "1":
    pytest.skip("set TRINETRA_LIVE=1 to run against the real Sentinel feed", allow_module_level=True)

from capture.capture_factory import open_capture  # noqa: E402
from capture.sentinel_catalogue import get_cameras, select_test_subset  # noqa: E402
from config.settings import load_settings  # noqa: E402


def test_catalogue_is_reachable():
    settings = load_settings()
    cameras = get_cameras(settings=settings, use_cache=False)
    assert cameras, "live run requires a reachable catalogue"
    assert all(c.camera_id for c in cameras)


def test_one_real_camera_delivers_frames_with_pts():
    settings = load_settings()
    cameras = select_test_subset(get_cameras(settings=settings), size=1)
    assert cameras
    camera = cameras[0]
    capture, error = open_capture(camera, settings)
    assert capture is not None, f"could not open {camera.camera_id}: {error}"

    deadline = time.monotonic() + 15
    packets = []
    while time.monotonic() < deadline and len(packets) < 30:
        packet = capture.read()
        if packet is None:
            time.sleep(0.05)
            continue
        packets.append(packet)
    capture.close()

    assert packets, f"{camera.camera_id} delivered no frames in 15s"
    continuous = [p.continuous_ms for p in packets]
    assert continuous == sorted(continuous), "continuous PTS must be monotonic"
    stats = capture.stats
    print(
        f"\n[live] {camera.camera_id} transport={capture.source} codec={stats.codec} "
        f"res={stats.width}x{stats.height} fps={stats.delivered_fps} frames={len(packets)}"
    )
