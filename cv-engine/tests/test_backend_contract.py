"""
Backend payload validation (spec §21, §34).

The cv-engine event payload is validated against the REAL backend pydantic
schema (VehicleEventCreate) — if either side renames a field, this fails.
"""
import sys
from pathlib import Path

import pytest

from capture.sentinel_catalogue import Camera
from tracking.vehicle_tracker import Track
from events.event_builder import build_event

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "TRINETRAAI" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.database.schemas import VehicleEventCreate
    BACKEND_IMPORTABLE = True
except Exception:
    BACKEND_IMPORTABLE = False


CAM = Camera(camera_id="cam04", latitude=23.0338, longitude=72.585, location="Paldi Circle")


def _track():
    return Track(track_id=17, bbox=[10, 10, 90, 90], class_name="car",
                 confidence=0.9, camera_id="cam04",
                 first_pts_ms=123000.0, last_pts_ms=123456.78)


@pytest.mark.skipif(not BACKEND_IMPORTABLE, reason="backend schema not importable")
def test_full_plate_event_accepted_by_backend_schema():
    event = build_event(
        CAM, _track(),
        plate={"plate": "GJ01AB1234", "confidence": 0.94,
               "plate_raw": "GJ 01 AB-1234", "n_readings": 3},
        evidence_ref="cam04/cam04_17_123456ms_GJ01AB1234.jpg",
    )
    parsed = VehicleEventCreate.model_validate(event)
    assert parsed.camera_id == "cam04"
    assert parsed.vehicle_id == 17
    assert parsed.plate_raw == "GJ 01 AB-1234"
    assert parsed.plate == "GJ01AB1234"
    assert parsed.plate_confidence == 0.94
    assert parsed.timestamp_pts == 123456.78
    assert parsed.latitude == 23.0338
    assert parsed.longitude == 72.585
    assert parsed.vehicle_class == "car"
    assert parsed.evidence_ref.endswith(".jpg")


@pytest.mark.skipif(not BACKEND_IMPORTABLE, reason="backend schema not importable")
def test_plateless_and_null_optional_fields_accepted():
    event = build_event(CAM, _track(), plate=None)
    parsed = VehicleEventCreate.model_validate(event)
    assert parsed.plate is None
    assert parsed.plate_raw is None
    assert parsed.plate_confidence is None


@pytest.mark.skipif(not BACKEND_IMPORTABLE, reason="backend schema not importable")
def test_low_confidence_event_still_accepted():
    """Low confidence must travel through unchanged (spec §30)."""
    event = build_event(
        CAM, _track(),
        plate={"plate": "GJ01AB1234", "confidence": 0.62,
               "plate_raw": "GJ O1 AB-1234", "n_readings": 1},
    )
    parsed = VehicleEventCreate.model_validate(event)
    assert parsed.plate_confidence == 0.62  # not upgraded, not dropped


@pytest.mark.skipif(not BACKEND_IMPORTABLE, reason="backend schema not importable")
def test_event_time_iso_zulu_parses():
    event = build_event(CAM, _track())
    parsed = VehicleEventCreate.model_validate(event)
    assert parsed.event_time is not None
    assert parsed.event_time.tzinfo is not None  # timezone-aware
