"""Tracking must never enlarge a box beyond the detector's own vehicle box.

Regression guard for the "boxes are too large" complaint: the tracker keeps the
Kalman model for association and for bridging frames where the detector lost the
vehicle, but while a real detection exists the track must report *that*
rectangle — verbatim.
"""
from detection.vehicle_detector import Detection
from tracking.vehicle_tracker import VehicleTracker


def det(x1, y1, x2, y2, conf=0.9, cls="car"):
    return Detection(bbox=[x1, y1, x2, y2], class_name=cls, confidence=conf)


def test_matched_track_reports_the_detector_box_exactly():
    tr = VehicleTracker(min_hits=1)
    tr.update([det(100, 100, 200, 180)], pts_ms=0.0)
    (track,) = tr.update([det(104, 101, 205, 183)], pts_ms=40.0)
    assert track.bbox == [104, 101, 205, 183]


def test_kalman_smoothing_does_not_grow_the_box():
    """A jittery detector must not turn into a growing rectangle."""
    tr = VehicleTracker(min_hits=1)
    for i, b in enumerate([(100, 100, 160, 140), (102, 99, 161, 141), (99, 101, 159, 139)]):
        (track,) = tr.update([det(*b)], pts_ms=i * 40.0)
        assert track.bbox == list(b), "box drifted away from the model's rectangle"


def test_occluded_frames_are_predicted_then_expire():
    """While occluded a track may be predicted (that is the point of tracking),
    but a stale prediction must not survive past max_age — no ghost box left
    hanging over the road."""
    tr = VehicleTracker(min_hits=1, max_age_sec=0.5)
    tr.update([det(100, 100, 200, 200)], pts_ms=0.0)
    seen = tr.update([det(100, 100, 200, 200)], pts_ms=40.0)
    assert len(seen) == 1

    gone = tr.update([], pts_ms=80.0)          # detector lost it this frame
    if gone:                                    # still bridged by the tracker
        assert gone[0].time_since_update_ms > 0
        assert gone[0].bbox == [100, 100, 200, 200]  # prediction, not growth

    assert tr.update([], pts_ms=900.0) == []    # expired: nothing to draw


def test_two_vehicles_never_merge_into_one_box():
    tr = VehicleTracker(min_hits=1)
    a = (10, 10, 60, 60)
    b = (70, 10, 120, 60)
    tr.update([det(*a), det(*b)], pts_ms=0.0)
    tracks = tr.update([det(*a), det(*b)], pts_ms=40.0)
    assert len(tracks) == 2
    boxes = sorted(tuple(int(v) for v in t.bbox) for t in tracks)
    assert boxes == [a, b], "nearby vehicles must stay two separate detections"
