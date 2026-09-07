"""
Recorded-video events must satisfy the REAL backend schema (Phase 25).

If either side renames a field, or if the recorded-video path starts inventing
an ``event_time`` that does not exist, these tests fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from events.event_schema import to_backend_payload
from sightings.reporting import ReportContext, build_events
from sightings.segmenter import PlateObservation, SightingSegmenter

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "TRINETRAAI" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.database.schemas import VehicleEventCreate
    BACKEND_IMPORTABLE = True
except Exception:  # pragma: no cover - backend deps optional in CV-only envs
    BACKEND_IMPORTABLE = False


CTX = ReportContext(
    video_id="faculty_parking_01",
    camera_id="faculty_parking",
    location_name="Faculty Parking",
)


def one_sighting(plate="GJ03AB1234", conf=0.93):
    s = SightingSegmenter(camera_id=CTX.camera_id, video_id=CTX.video_id,
                          keep_evidence_frames=False)
    for t in range(0, 3000, 100):
        s.observe_track(17, t, t // 40, "car", 0.9, [10, 10, 200, 160])
        s.tick(t)
    for t in (400, 900, 1400):
        s.add_plate_observation(17, PlateObservation(
            pts_ms=t, frame_index=t // 40, plate_raw="GJ 03 AB-1234",
            plate_normalized=plate, ocr_confidence=conf, plate_det_confidence=0.85,
            plate_bbox=[40, 90, 120, 116], plate_area_px=2080.0, sharpness=180.0,
            quality=0.7,
        ))
    return s.finalize()


def test_events_pass_the_engine_side_contract():
    events = build_events(one_sighting(), CTX)
    payload = to_backend_payload(events[0])
    assert set(payload) <= {
        "camera_id", "vehicle_id", "plate_raw", "plate", "plate_confidence",
        "timestamp_pts", "event_time", "latitude", "longitude",
        "vehicle_class", "evidence_ref",
    }


@pytest.mark.skipif(not BACKEND_IMPORTABLE, reason="backend schema not importable")
def test_events_are_accepted_by_the_backend_pydantic_schema():
    events = build_events(one_sighting(), CTX)
    parsed = VehicleEventCreate.model_validate(events[0])
    assert parsed.camera_id == "faculty_parking"
    assert parsed.vehicle_id == 17
    assert parsed.plate == "GJ03AB1234"
    assert parsed.plate_raw == "GJ 03 AB-1234"
    assert 0.0 <= parsed.plate_confidence <= 1.0
    assert parsed.vehicle_class == "car"
    # A recorded upload has no capture clock: the backend defaults it itself.
    assert parsed.event_time is None
    assert parsed.timestamp_pts == 0.0


@pytest.mark.skipif(not BACKEND_IMPORTABLE, reason="backend schema not importable")
def test_low_confidence_sighting_is_ingestable_without_a_plate():
    events = build_events(one_sighting(conf=0.3), CTX)
    parsed = VehicleEventCreate.model_validate(events[0])
    assert parsed.plate is None
    assert parsed.plate_confidence is None
    assert parsed.vehicle_id == 17
