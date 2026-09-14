"""Tracking (spec §13, §14): stable track ids, PTS-driven, scene reset."""
from tracking.vehicle_tracker import VehicleTracker, iou_matrix
from detection.vehicle_detector import Detection
import numpy as np


def det(x1, y1, x2, y2, conf=0.9, cls="car"):
    return Detection(bbox=[x1, y1, x2, y2], class_name=cls, confidence=conf)


def test_track_id_stable_across_frames():
    tr = VehicleTracker(min_hits=1)
    t1 = tr.update([det(100, 100, 200, 200)], pts_ms=0.0)
    t2 = tr.update([det(105, 102, 205, 202)], pts_ms=40.0)
    t3 = tr.update([det(110, 104, 210, 204)], pts_ms=80.0)
    assert len(t1) == len(t2) == len(t3) == 1
    assert t1[0].track_id == t2[0].track_id == t3[0].track_id


def test_two_vehicles_get_distinct_ids():
    tr = VehicleTracker(min_hits=1)
    tracks = tr.update([det(10, 10, 60, 60), det(300, 300, 380, 380)], pts_ms=0.0)
    assert len(tracks) == 2
    assert tracks[0].track_id != tracks[1].track_id


def test_min_hits_delays_confirmation():
    tr = VehicleTracker(min_hits=3)
    assert tr.update([det(100, 100, 200, 200)], pts_ms=0.0) == []
    assert tr.update([det(105, 100, 205, 200)], pts_ms=40.0) == []
    confirmed = tr.update([det(110, 100, 210, 200)], pts_ms=80.0)
    assert len(confirmed) == 1


def test_track_dies_after_max_age_pts():
    """Tracks are dropped based on PTS elapsed, not frame count."""
    tr = VehicleTracker(min_hits=1, max_age_sec=1.0)
    tr.update([det(100, 100, 200, 200)], pts_ms=0.0)
    # still alive just under max_age
    assert len(tr.update([], pts_ms=900.0)) >= 0
    assert tr.active_count() >= 1
    # past max_age -> dropped
    tr.update([], pts_ms=2500.0)
    assert tr.active_count() == 0


def test_track_pts_deltas_not_frame_arrival():
    """first/last PTS are recorded from the packets, not wall clock."""
    tr = VehicleTracker(min_hits=1)
    a = tr.update([det(100, 100, 200, 200)], pts_ms=5000.0)[0]
    b = tr.update([det(104, 100, 204, 200)], pts_ms=5160.0)[0]
    assert a.first_pts_ms == 5000.0
    assert b.last_pts_ms == 5160.0
    assert b.confirmed_age_ms == 160.0  # PTS-based age


def test_scene_reset_clears_tracks_and_ids_increment():
    tr = VehicleTracker(min_hits=1)
    before = tr.update([det(100, 100, 200, 200)], pts_ms=0.0)
    tr.reset()
    assert tr.active_count() == 0
    after = tr.update([det(100, 100, 200, 200)], pts_ms=40.0)
    assert after[0].track_id != before[0].track_id, "new identity after scene cut"
    assert tr.resets == 1


def test_low_conf_detection_rescues_track():
    """ByteTrack second stage: weak det keeps an existing track alive."""
    tr = VehicleTracker(min_hits=1, high_conf=0.5, low_conf=0.1, max_age_sec=0.5)
    tr.update([det(100, 100, 200, 200, conf=0.9)], pts_ms=0.0)
    kept = tr.update([det(104, 100, 204, 200, conf=0.3)], pts_ms=40.0)
    assert len(kept) == 1, "low-conf detection should maintain the track"


def test_iou_matrix_correctness():
    a = np.array([[0, 0, 10, 10]], dtype=np.float32)
    b = np.array([[0, 0, 10, 10], [5, 5, 15, 15], [100, 100, 110, 110]], dtype=np.float32)
    m = iou_matrix(a, b)
    assert abs(m[0, 0] - 1.0) < 1e-6
    assert abs(m[0, 1] - (25.0 / 175.0)) < 1e-3
    assert m[0, 2] == 0.0


def test_handles_missing_pts_gracefully():
    """No PTS -> tracker still works using a nominal dt (documented fallback)."""
    tr = VehicleTracker(min_hits=1)
    t1 = tr.update([det(100, 100, 200, 200)], pts_ms=None)
    t2 = tr.update([det(104, 100, 204, 200)], pts_ms=None)
    assert t1 and t2 and t1[0].track_id == t2[0].track_id
