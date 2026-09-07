"""
Detection/tracking output-shape tests and evidence-quality metrics for the
recorded-video pipeline (Phase 23.2, 23.3, 23.11).

The detector is stubbed: these tests assert the CONTRACT between stages, not
model accuracy (model accuracy is measured by the manual full-video run).
"""
from __future__ import annotations

import numpy as np
import pytest

from detection.vehicle_detector import Detection
from sightings.quality import bbox_area, edge_distance_ratio, evidence_score, sharpness
from tracking.vehicle_tracker import VehicleTracker


def test_detection_dict_shape_matches_the_documented_contract():
    d = Detection(bbox=[10.0, 20.0, 110.0, 140.0], class_name="car", confidence=0.91,
                  camera_id="faculty_parking", pts_ms=6430.0, class_id=2)
    out = d.to_dict()
    assert set(out) == {"bbox", "class", "confidence", "camera_id", "pts_ms"}
    assert out["bbox"] == [10.0, 20.0, 110.0, 140.0]
    assert out["class"] == "car"
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["pts_ms"] == 6430.0


def test_tracker_assigns_a_stable_id_to_a_moving_vehicle():
    tracker = VehicleTracker(max_age_sec=1.0, min_hits=2, iou_threshold=0.2)
    ids = set()
    for i in range(12):
        x = 100 + i * 6
        det = Detection(bbox=[x, 100, x + 90, 190], class_name="car",
                        confidence=0.85, camera_id="cam", pts_ms=i * 100.0)
        tracks = tracker.update([det], pts_ms=i * 100.0)
        for t in tracks:
            ids.add(t.track_id)
    assert len(ids) == 1, "a continuously visible vehicle must keep one track id"
    (tid,) = ids
    tracks = tracker.update([], pts_ms=1300.0)
    assert all(t.first_pts_ms is not None for t in tracks)


def test_track_fields_required_by_sightings_are_present():
    tracker = VehicleTracker(max_age_sec=1.0, min_hits=1, iou_threshold=0.2)
    det = Detection(bbox=[10, 10, 100, 100], class_name="truck", confidence=0.7,
                    camera_id="cam", pts_ms=0.0)
    (track,) = tracker.update([det], pts_ms=0.0)
    for field in ("track_id", "bbox", "class_name", "confidence",
                  "first_pts_ms", "last_pts_ms", "time_since_update_ms"):
        assert hasattr(track, field)
    assert track.class_name == "truck"


def test_a_vehicle_that_leaves_is_dropped_after_max_age():
    tracker = VehicleTracker(max_age_sec=0.5, min_hits=1, iou_threshold=0.2)
    det = Detection(bbox=[10, 10, 100, 100], class_name="car", confidence=0.8,
                    camera_id="cam", pts_ms=0.0)
    tracker.update([det], pts_ms=0.0)
    tracker.update([], pts_ms=300.0)
    assert tracker.active_count() == 1
    tracker.update([], pts_ms=1200.0)
    assert tracker.active_count() == 0


# ----------------------------------------------------------- quality metrics
def test_sharpness_ranks_a_blurred_image_below_a_sharp_one():
    pytest.importorskip("cv2")
    import cv2

    sharp = np.zeros((80, 160, 3), dtype=np.uint8)
    cv2.putText(sharp, "GJ01AB1234", (5, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (255, 255, 255), 2)
    blurred = cv2.GaussianBlur(sharp, (9, 9), 6)
    assert sharpness(sharp) > sharpness(blurred) > 0


def test_evidence_score_is_monotonic_in_each_input():
    base = evidence_score(2000, 100, 0.7, 40000, 1.0)
    assert evidence_score(6000, 100, 0.7, 40000, 1.0) > base   # bigger plate
    assert evidence_score(2000, 300, 0.7, 40000, 1.0) > base   # sharper
    assert evidence_score(2000, 100, 0.95, 40000, 1.0) > base  # better OCR
    assert evidence_score(2000, 100, 0.7, 40000, 0.0) < base   # touching edge


def test_bbox_helpers():
    assert bbox_area([0, 0, 10, 20]) == 200
    assert bbox_area(None) == 0.0
    assert edge_distance_ratio([0, 0, 10, 10], 100, 100) == 0.0
    assert edge_distance_ratio([40, 40, 60, 60], 100, 100) == 1.0
