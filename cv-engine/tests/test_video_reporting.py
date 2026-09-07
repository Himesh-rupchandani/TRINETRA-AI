"""
Reporting tests: CSV/JSON export, evidence naming, backend event generation and
target-sighting counting (Phase 23.8-23.10 of the brief).
"""
from __future__ import annotations

import csv
import json

import numpy as np
import pytest

from events.event_schema import validate_event
from sightings.reporting import (
    ReportContext,
    build_events,
    build_target_report,
    plate_summary,
    write_evidence,
    write_sightings,
)
from sightings.segmenter import PlateObservation, SightingSegmenter


CTX = ReportContext(
    video_id="faculty_parking_01",
    camera_id="faculty_parking",
    location_name="Faculty Parking",
)


def build_sightings(visits, plate="GJ03AB1234", conf=0.9, with_frames=False):
    s = SightingSegmenter(
        camera_id=CTX.camera_id, video_id=CTX.video_id,
        track_end_gap_sec=2.0, sighting_cooldown_sec=3.0,
        min_frames=3, min_duration_sec=0.3, keep_evidence_frames=with_frames,
    )
    frame = np.zeros((60, 80, 3), dtype=np.uint8) if with_frames else None
    crop = np.zeros((20, 60, 3), dtype=np.uint8) if with_frames else None
    for i, start in enumerate(visits):
        tid = 100 + i
        for t in range(start, start + 3000, 100):
            s.observe_track(tid, t, t // 100, "car", 0.9, [10, 10, 60, 50])
            s.tick(t)
        for k, t in enumerate(range(start + 200, start + 2200, 500)):
            s.add_plate_observation(
                tid,
                PlateObservation(
                    pts_ms=t, frame_index=t // 100, plate_raw=plate,
                    plate_normalized=plate, ocr_confidence=conf,
                    plate_det_confidence=0.8, plate_bbox=[10, 30, 50, 44],
                    plate_area_px=560.0, sharpness=100.0, quality=0.5 + 0.01 * k,
                ),
                frame=frame, plate_crop=crop, vehicle_bbox=[10, 10, 60, 50],
            )
    return s.finalize()


# --------------------------------------------------------------- exports
def test_csv_and_json_exports_have_one_row_per_sighting(tmp_path):
    sightings = build_sightings([0, 20000, 45000])
    rows = write_sightings(sightings, CTX, tmp_path)
    assert len(rows) == 3

    data = json.loads((tmp_path / "vehicle_sightings.json").read_text())
    assert len(data) == 3
    assert data[0]["plate"] == "GJ03AB1234"
    assert data[0]["plate_status"] == "DETECTED"
    assert data[0]["supporting_frame_count"] == 4
    assert data[0]["start_timestamp"] == "00:00.0"
    assert data[1]["start_timestamp"] == "00:20.0"

    with (tmp_path / "vehicle_sightings.csv").open() as fh:
        csv_rows = list(csv.DictReader(fh))
    assert len(csv_rows) == 3
    assert csv_rows[0]["plate"] == "GJ03AB1234"
    assert csv_rows[0]["sighting_index_for_plate"] == "1"


def test_evidence_files_are_named_per_sighting_and_refs_point_at_real_files(tmp_path):
    sightings = build_sightings([0, 20000], with_frames=True)
    write_evidence(sightings, tmp_path / "evidence")
    rows = write_sightings(sightings, CTX, tmp_path)
    assert rows[0]["evidence_ref"] == "evidence/sighting_01.jpg"
    assert rows[0]["plate_crop_ref"] == "evidence/sighting_01_plate.jpg"
    assert rows[1]["evidence_ref"] == "evidence/sighting_02.jpg"
    for r in rows:
        assert (tmp_path / r["evidence_ref"]).exists()
        assert (tmp_path / r["plate_crop_ref"]).exists()


def test_evidence_ref_is_null_when_no_image_was_stored(tmp_path):
    sightings = build_sightings([0], with_frames=False)
    write_evidence(sightings, tmp_path / "evidence")
    rows = write_sightings(sightings, CTX, tmp_path)
    assert rows[0]["evidence_ref"] is None  # never a lie about a missing file


# ---------------------------------------------------------------- events
def test_events_are_backend_contract_valid_and_one_per_sighting():
    sightings = build_sightings([0, 20000, 45000])
    events = build_events(sightings, CTX)
    assert len(events) == 3
    for e in events:
        validate_event(e)  # raises on contract violation
        assert e["camera_id"] == "faculty_parking"
        assert e["plate"] == "GJ03AB1234"
        assert 0.0 <= e["plate_confidence"] <= 1.0
        assert e["vehicle_class"] == "car"
        # recorded upload: the upload clock is NOT the capture clock
        assert e["event_time"] is None
        assert e["timestamp_pts"] is not None


def test_uncertain_plate_is_not_published_as_a_plate():
    sightings = build_sightings([0], conf=0.35)
    events = build_events(sightings, CTX)
    assert events[0]["plate"] is None
    assert events[0]["plate_raw"] is None
    assert events[0]["plate_confidence"] is None
    assert events[0]["vehicle_id"] is not None  # the vehicle sighting still exists


# ------------------------------------------------------- target counting
def test_plate_summary_counts_sightings_per_plate(tmp_path):
    rows = write_sightings(build_sightings([0, 20000, 45000]), CTX, tmp_path)
    rows += write_sightings(build_sightings([80000], plate="MH12MV8899"), CTX, tmp_path / "b")
    summary = plate_summary(rows)
    assert summary[0]["plate"] == "GJ03AB1234"
    assert summary[0]["sightings"] == 3
    assert summary[1]["plate"] == "MH12MV8899"
    assert summary[1]["sightings"] == 1


def test_target_report_finds_the_vehicle_with_exactly_five_sightings(tmp_path):
    rows = write_sightings(
        build_sightings([0, 20000, 45000, 70000, 95000]), CTX, tmp_path
    )
    report = build_target_report(rows, target_count=5)
    assert report["found"] is True
    assert report["plate"] == "GJ03AB1234"
    assert report["total_sightings"] == 5
    assert [s["sighting_number"] for s in report["sightings"]] == [1, 2, 3, 4, 5]
    assert all(s["timestamp"] for s in report["sightings"])


def test_target_report_never_fabricates_a_fifth_sighting(tmp_path):
    rows = write_sightings(build_sightings([0, 20000, 45000]), CTX, tmp_path)
    report = build_target_report(rows, target_count=5)
    assert report["found"] is False
    assert report["total_sightings"] == 3
    assert len(report["sightings"]) == 3
    assert "No vehicle with exactly 5 validated sightings" in report["note"]


def test_target_report_handles_a_video_with_no_readable_plate(tmp_path):
    rows = write_sightings(build_sightings([0], conf=0.2), CTX, tmp_path)
    report = build_target_report(rows, target_count=5)
    assert report["found"] is False
    assert report["plate"] is None
    assert report["sightings"] == []
