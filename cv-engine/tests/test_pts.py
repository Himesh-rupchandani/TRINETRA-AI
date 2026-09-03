"""PTS handling — the timing contract of the whole engine.

Sentinel guidance is explicit: use PTS, never frame arrival time, never
``CAP_PROP_FPS``. These tests pin that behaviour, including the loop case
(feeds restart, so raw PTS jumps backwards).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

from capture.frames import FramePacket, PtsTimeline, nominal_interval_from_fps


def _frame(w=8, h=8):
    return np.zeros((h, w, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# PtsTimeline
# ---------------------------------------------------------------------------


def test_first_frame_starts_the_clock_and_deltas_are_pts_deltas():
    tl = PtsTimeline(nominal_interval_ms=40)
    c0, d0, valid0, disc0 = tl.update(1000.0)
    assert (c0, d0, valid0, disc0) == (1000.0, 0.0, True, False)
    c1, d1, _, _ = tl.update(1040.0)
    assert d1 == 40.0 and c1 == 1040.0
    c2, d2, _, _ = tl.update(1080.0)
    assert d2 == 40.0 and c2 == 1080.0


def test_variable_inter_frame_gaps_are_preserved_not_smoothed():
    tl = PtsTimeline(nominal_interval_ms=40)
    tl.update(0.0)
    _, d1, _, _ = tl.update(40.0)
    _, d2, _, _ = tl.update(160.0)  # a real 120 ms gap (dropped frames)
    assert d1 == 40.0
    assert d2 == 120.0  # the gap is reported honestly, not replaced by 40 ms


def test_stream_loop_keeps_continuous_pts_monotonic_and_flags_the_cut():
    tl = PtsTimeline(nominal_interval_ms=40)
    for pts in (0.0, 40.0, 80.0, 120.0):
        tl.update(pts)
    continuous_before = tl.last_continuous_ms
    # Feed restarts: PTS goes back to ~0.
    continuous, delta, valid, discontinuity = tl.update(0.0)
    assert discontinuity is True
    assert valid is True
    assert tl.loops == 1
    assert continuous > continuous_before  # monotonic across the loop
    assert delta == 40.0  # nominal interval, not a negative jump


def test_large_forward_jump_is_a_discontinuity():
    tl = PtsTimeline(nominal_interval_ms=40)
    tl.update(0.0)
    _, delta, _, discontinuity = tl.update(600_000.0)
    assert discontinuity is True
    assert delta == 600_000.0


def test_missing_or_invalid_pts_is_flagged_and_never_faked():
    tl = PtsTimeline(nominal_interval_ms=40)
    tl.update(0.0)
    for bad in (None, float("nan"), -5.0):
        continuous, delta, valid, _ = tl.update(bad)
        assert valid is False
        assert delta == 40.0  # nominal fallback, explicitly marked invalid
        assert continuous > 0
    assert tl.invalid_count == 3


def test_reset_clears_loop_state():
    tl = PtsTimeline(nominal_interval_ms=40)
    tl.update(500.0)
    tl.update(0.0)
    assert tl.loops == 1
    tl.reset()
    continuous, delta, valid, disc = tl.update(10.0)
    assert (continuous, delta, valid, disc) == (10.0, 0.0, True, False)
    assert tl.loops == 1  # history is kept for reporting, clock state is cleared


def test_nominal_interval_is_only_a_fallback_hint():
    assert nominal_interval_from_fps(25) == 40.0
    assert nominal_interval_from_fps(None) == 40.0
    assert nominal_interval_from_fps(0) == 40.0
    assert nominal_interval_from_fps(30, default_ms=33.3) == 1000.0 / 30


# ---------------------------------------------------------------------------
# FramePacket
# ---------------------------------------------------------------------------


def test_frame_packet_carries_camera_id_pts_and_state():
    packet = FramePacket(frame=_frame(640, 480), camera_id="cam04", pts_ms=123456.78)
    assert packet.camera_id == "cam04"
    assert packet.pts_ms == 123456.78
    assert packet.capture_state == "OK"
    assert (packet.width, packet.height) == (640, 480)


def test_wall_clock_is_iso_utc_and_separate_from_pts():
    packet = FramePacket(
        frame=_frame(),
        camera_id="cam04",
        pts_ms=1.0,
        arrived_at=datetime(2026, 9, 2, 14, 32, 18, tzinfo=timezone.utc),
    )
    assert packet.wall_clock_iso == "2026-09-02T14:32:18Z"
    # The two clocks are independent fields — nothing derives one from the other.
    assert packet.pts_ms == 1.0


def test_invalid_pts_is_representable_without_raising():
    packet = FramePacket(frame=_frame(), camera_id="cam04", pts_ms=float("nan"), pts_valid=False)
    assert math.isnan(packet.pts_ms)
    assert packet.pts_valid is False
