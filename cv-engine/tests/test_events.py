"""Event schema, builder and de-duplication."""

from __future__ import annotations

import pytest

from capture.sentinel_catalogue import Camera
from events.dedup import EventDeduplicator
from events.event_builder import build_event, build_unplated_event
from events.event_schema import CORE_EVENT_FIELDS, VehicleEvent, validate_payload
from tracking.vehicle_tracker import TrackedVehicle


def _camera(**kw) -> Camera:
    base = dict(camera_id="cam04", name="Paldi Circle", latitude=23.0126, longitude=72.5647)
    base.update(kw)
    return Camera(**base)


def _track(**kw) -> TrackedVehicle:
    base = dict(
        track_id=17,
        bbox=(10, 10, 100, 60),
        class_name="car",
        confidence=0.91,
        camera_id="cam04",
        pts_ms=123456.78,
        continuous_ms=123456.78,
        first_seen_pts_ms=123000.0,
    )
    base.update(kw)
    return TrackedVehicle(**base)


def test_payload_contains_every_core_field_in_order():
    event = build_event(
        load(), _camera(), _track(),
        plate="GJ01AB1234", plate_raw="GJ 01 AB 1234", plate_confidence=0.94,
        evidence_ref="cam04/x.jpg", source_transport="rtsp",
    )
    payload = event.to_payload()
    for field_name in CORE_EVENT_FIELDS:
        assert field_name in payload, field_name
    assert payload["camera_id"] == "cam04"
    assert payload["vehicle_id"] == 17
    assert payload["plate"] == "GJ01AB1234"
    assert payload["plate_confidence"] == 0.94
    assert payload["timestamp_pts"] == 123456.78
    assert payload["latitude"] == 23.0126
    assert payload["longitude"] == 72.5647
    assert payload["vehicle_class"] == "car"
    assert validate_payload(payload) == []


def test_location_comes_from_camera_metadata_only():
    camera_without_geo = _camera(latitude=None, longitude=None)
    event = build_event(load(), camera_without_geo, _track(), "GJ01AB1234", "x", 0.9)
    payload = event.to_payload()
    assert payload["latitude"] is None
    assert payload["longitude"] is None
    assert validate_payload(payload) == []  # absence is valid per the spec


def test_low_confidence_is_flagged_not_dropped(settings_low):
    event = build_event(settings_low, _camera(), _track(), "GJ01AB1234", "6J01AB1234", 0.4)
    assert event.low_confidence is True
    assert event.confidence_grade == "low"
    payload = event.to_payload()
    assert payload["low_confidence"] is True
    assert validate_payload(payload) == []  # still stored, just marked


def test_unplated_event_is_a_detection_not_an_anpr_read():
    event = build_unplated_event(load(), _camera(), _track())
    assert event.event_type == "VEHICLE_DETECTION"
    assert event.plate == ""
    assert event.low_confidence is True
    assert validate_payload(event.to_payload()) == []


def test_validate_catches_bad_confidence_and_missing_fields():
    payload = {field: None for field in CORE_EVENT_FIELDS}
    payload["camera_id"] = "cam04"
    payload["plate_confidence"] = 7.5
    payload["timestamp_pts"] = 1.0
    payload["event_time"] = "2026-09-02T00:00:00Z"
    problems = validate_payload(payload)
    assert any("plate_confidence" in p for p in problems)

    empty = {"plate": "GJ01AB1234"}
    problems2 = validate_payload(empty)
    assert any("missing core field" in p for p in problems2)


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------


def test_same_camera_track_plate_within_window_suppresses():
    dedup = EventDeduplicator(window_s=45.0)
    assert dedup.should_emit("cam04", 17, "GJ01AB1234", 1000.0) is True
    assert dedup.should_emit("cam04", 17, "GJ01AB1234", 20000.0) is False
    assert dedup.suppressed == 1


def test_different_camera_always_gets_its_own_sighting():
    dedup = EventDeduplicator(window_s=45.0)
    assert dedup.should_emit("cam04", 17, "GJ01AB1234", 1000.0) is True
    assert dedup.should_emit("cam08", 3, "GJ01AB1234", 1000.0) is True


def test_after_the_window_a_reappearance_is_a_new_sighting():
    dedup = EventDeduplicator(window_s=45.0)
    assert dedup.should_emit("cam04", 17, "GJ01AB1234", 0.0) is True
    assert dedup.should_emit("cam04", 17, "GJ01AB1234", 60_000.0) is True


def test_unplated_uses_a_shorter_window():
    dedup = EventDeduplicator(unplated_window_s=20.0)
    assert dedup.should_emit("cam04", 5, "", 0.0) is True
    assert dedup.should_emit("cam04", 5, "", 25_000.0) is True  # window elapsed
    assert dedup.should_emit("cam04", 5, "", 25_500.0) is False


# fixtures ------------------------------------------------------------------
def load():
    from config.settings import load_settings

    return load_settings(env={})


@pytest.fixture
def settings_low():
    from config.settings import load_settings

    return load_settings(env={}, anpr_low_confidence=0.55)
