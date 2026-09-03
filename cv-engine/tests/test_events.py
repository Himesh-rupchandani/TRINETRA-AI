"""Event schema/builder (spec §21) and CV-layer deduplication (spec §19)."""
import pytest
from datetime import datetime, timezone

from capture.sentinel_catalogue import Camera
from tracking.vehicle_tracker import Track
from events.dedup import SightingDeduplicator
from events.event_builder import build_event
from events.event_schema import (
    EVENT_FIELDS,
    EventValidationError,
    to_backend_payload,
    validate_event,
)


CAM = Camera(camera_id="cam04", latitude=23.0001, longitude=72.5001, location="Paldi")


def _track(tid=17, pts=123456.78, cls="car"):
    return Track(track_id=tid, bbox=[10, 10, 50, 50], class_name=cls,
                 confidence=0.9, camera_id="cam04", first_pts_ms=pts - 500,
                 last_pts_ms=pts)


def test_build_event_full_contract():
    plate = {"plate": "GJ01AB1234", "confidence": 0.94, "plate_raw": "GJ 01 AB-1234", "n_readings": 3}
    ev = build_event(
        CAM, _track(),
        plate=plate,
        evidence_ref="cam04/cam04_17_123456ms_GJ01AB1234.jpg",
        event_time=datetime(2026, 9, 2, 14, 32, 18, tzinfo=timezone.utc),
    )
    assert set(ev.keys()) == set(EVENT_FIELDS)
    assert ev["camera_id"] == "cam04"
    assert ev["vehicle_id"] == 17
    assert ev["plate_raw"] == "GJ 01 AB-1234"
    assert ev["plate"] == "GJ01AB1234"
    assert ev["plate_confidence"] == 0.94
    assert ev["timestamp_pts"] == 123456.78
    assert ev["event_time"] == "2026-09-02T14:32:18Z"
    assert ev["latitude"] == 23.0001
    assert ev["longitude"] == 72.5001
    assert ev["vehicle_class"] == "car"
    assert ev["evidence_ref"].endswith(".jpg")


def test_build_plateless_event_keeps_sighting():
    ev = build_event(CAM, _track(), plate=None)
    assert ev["plate"] is None
    assert ev["plate_raw"] is None
    assert ev["plate_confidence"] is None
    assert ev["vehicle_id"] == 17


def test_location_only_from_camera_metadata():
    """No GPS in metadata -> null coords; never inferred from video (spec §22)."""
    cam_noloc = Camera(camera_id="cam09")
    ev = build_event(cam_noloc, _track())
    assert ev["latitude"] is None and ev["longitude"] is None

    cam_badloc = Camera(camera_id="cam09", latitude=999.0, longitude=72.0)
    ev2 = build_event(cam_badloc, _track())
    assert ev2["latitude"] is None  # out-of-range metadata rejected


def test_validate_event_rejects_bad_payloads():
    base = build_event(CAM, _track())

    with pytest.raises(EventValidationError):
        validate_event({**base, "camera_id": ""})
    with pytest.raises(EventValidationError):
        validate_event({**base, "plate_confidence": 1.5})
    with pytest.raises(EventValidationError):
        validate_event({**base, "plate_confidence": -0.1})
    with pytest.raises(EventValidationError):
        validate_event({**base, "latitude": 95.0})
    with pytest.raises(EventValidationError):
        validate_event({**base, "timestamp_pts": -5})
    with pytest.raises(EventValidationError):
        validate_event({**base, "unexpected_field": 1})


def test_to_backend_payload_preserves_field_names():
    """The contract owner passes names through unchanged (spec §21)."""
    ev = build_event(CAM, _track())
    payload = to_backend_payload(ev)
    assert payload == {k: ev[k] for k in EVENT_FIELDS}


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_dedup_suppresses_same_camera_track_plate():
    dd = SightingDeduplicator(suppression_sec=30.0)
    assert dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=1000.0)
    assert not dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=5000.0)
    assert not dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=29000.0)
    assert dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=32000.0)  # window passed
    assert dd.stats() == {"emitted": 2, "suppressed": 2}


def test_dedup_does_not_suppress_across_cameras():
    """Different cameras must produce independent sightings (spec §19/§25)."""
    dd = SightingDeduplicator(suppression_sec=30.0)
    assert dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=1000.0)
    assert dd.should_emit("cam08", 3, "GJ01AB1234", pts_ms=1000.0)
    assert dd.should_emit("cam12", 9, "GJ01AB1234", pts_ms=1000.0)


def test_dedup_distinguishes_tracks_and_plates():
    dd = SightingDeduplicator(suppression_sec=30.0)
    assert dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=1000.0)
    assert dd.should_emit("cam04", 18, "GJ01AB1234", pts_ms=1000.0)  # different track
    assert dd.should_emit("cam04", 17, "MH02CD5678", pts_ms=1000.0)  # different plate
    assert dd.should_emit("cam04", 17, None, pts_ms=1000.0)          # plateless sighting


def test_dedup_forget_track_and_reset():
    dd = SightingDeduplicator(suppression_sec=30.0)
    dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=1000.0)
    dd.forget_track("cam04", 17)
    assert dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=2000.0)
    dd.reset()
    assert dd.should_emit("cam04", 17, "GJ01AB1234", pts_ms=3000.0)
