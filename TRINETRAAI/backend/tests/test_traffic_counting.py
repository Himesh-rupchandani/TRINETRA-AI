"""Phase-one traffic tests: fixture geometry, not an accuracy benchmark."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.database.database import get_db
from app.database.models import CameraTrafficConfig
from app.services.live_tracker import LiveTracker
from app.services.motion_tracker_core import VehicleTracker
from app.services.simple_tracker import TrackedBox
from app.services.traffic_counting import TrafficConfig, TrafficCounter, segment_enters_box
from app.services.vehicle_detection_service import VehicleDetection
from app.services import live_anpr_service as live
from .test_live_anpr import rig, rows


def track(x=.5, y=.3, *, tid=1, hits=2, misses=0, kind="car", size=100):
    return TrackedBox(tid, int(x*size)-3, int(y*size)-3, int(x*size)+3, int(y*size)+3,
                      kind, .9, hits=hits, misses=misses)


def update(counter, tracks, time_s=0, size=100):
    counter.update(tracks, time_s, size, size, max_gap=5)
    return counter.snapshot()


def test_counts_wait_for_two_observations_and_are_not_frame_counts():
    counter = TrafficCounter()
    assert update(counter, [track(hits=1)])["observed_tracks"] == 0
    for sec in range(1, 12):
        result = update(counter, [track()], sec)
    assert result["observed_tracks"] == 1 and result["by_class"]["car"] == 1
    assert result["crossings"] == 0 and result["sample_hz"] == 1


def test_line_crossing_is_directional_deduplicated_and_not_an_initial_position():
    counter = TrafficCounter(TrafficConfig(mode="line", direction="positive"))
    assert update(counter, [track(y=.7)])["crossings"] == 0
    assert update(counter, [track(y=.3)], 1)["crossings"] == 0
    assert update(counter, [track(y=.7)], 2)["crossings"] == 1
    update(counter, [track(y=.3)], 3)
    result = update(counter, [track(y=.7)], 4)
    assert result["crossings"] == result["forward"] == 1
    assert result["reverse"] == 0


def test_line_detects_skipped_band_but_rejects_crossing_outside_span():
    cfg = TrafficConfig(mode="line", span_start=.2, span_end=.8)
    counter = TrafficCounter(cfg)
    update(counter, [track(x=.9, y=.3)], 0)
    assert update(counter, [track(x=.9, y=.7)], 1)["crossings"] == 0
    update(counter, [track(x=.5, y=.3)], 2)
    assert update(counter, [track(x=.5, y=.7)], 3)["crossings"] == 1


def test_jitter_predictions_frozen_time_and_long_gaps_do_not_cross():
    counter = TrafficCounter(TrafficConfig(mode="line"))
    update(counter, [track(y=.49)], 0)
    update(counter, [track(y=.51)], 1)
    update(counter, [track(y=.8, misses=1)], 2)
    assert counter.snapshot()["crossings"] == 0
    update(counter, [track(y=.3)], 3)
    assert update(counter, [track(y=.7)], 3)["crossings"] == 0
    assert update(counter, [track(y=.3)], 20)["crossings"] == 0


def test_zone_entry_not_first_seen_inside_and_only_once():
    counter = TrafficCounter(TrafficConfig(mode="zone"))
    assert update(counter, [track(y=.5)])["crossings"] == 0
    update(counter, [track(y=.1)], 1)
    assert update(counter, [track(y=.5)], 2)["crossings"] == 1
    update(counter, [track(y=.1)], 3)
    assert update(counter, [track(y=.5)], 4)["crossings"] == 1


def test_zone_skipped_between_samples_and_corner_tangency():
    cfg = TrafficConfig(mode="zone")
    assert segment_enters_box((.5, .1), (.5, .9), cfg)
    assert not segment_enters_box((.1, .25), (.9, .25), cfg)
    assert not segment_enters_box((.1, .1), (.2, .2), cfg)
    counter = TrafficCounter(cfg)
    update(counter, [track(y=.1)], 0)
    assert update(counter, [track(y=.9)], 1)["crossings"] == 1


def test_normalized_geometry_matches_different_resolutions():
    cfg = TrafficConfig(mode="line", axis="vertical", direction="negative")
    for size in (100, 1080, 1920):
        counter = TrafficCounter(cfg)
        update(counter, [track(x=.7, size=size)], 0, size)
        result = update(counter, [track(x=.3, size=size)], 1, size)
        assert result["crossings"] == result["reverse"] == 1


def test_retired_counting_state_is_pruned_and_totals_remain():
    counter = TrafficCounter()
    update(counter, [track()], 0)
    update(counter, [], 1)
    assert not counter._observations
    assert counter.observed == 1 and counter.visible == 0


@pytest.mark.parametrize("changes", [
    {"position": float("nan")}, {"position": float("inf")}, {"left": -1},
    {"right": .1}, {"span_start": .9, "span_end": .1}, {"mode": "wrong_way"}, {"unknown_field": 1},
])
def test_configuration_rejects_invalid_geometry(changes):
    with pytest.raises(ValidationError):
        TrafficConfig(**changes)


def core_det(x, *, kind="car", camera="A"):
    return SimpleNamespace(bbox=[x, 10, x+100, 110], class_name=kind, confidence=.9, camera_id=camera)


def test_motion_core_observations_are_exact_and_predictions_are_marked():
    tracker = VehicleTracker(min_hits=1)
    tracker.update([core_det(10)], 0)
    result = tracker.update([core_det(35)], 1000)[0]
    assert result.observed_bbox == [35, 10, 135, 110]
    predicted = tracker.update([], 1100)[0]
    assert predicted.time_since_update_ms > 0
    assert predicted.observed_bbox == result.observed_bbox


def test_expired_tracks_cannot_be_resurrected_by_an_identical_box():
    tracker = VehicleTracker(min_hits=1, max_age_sec=1)
    first = tracker.update([core_det(10)], 0)[0].track_id
    second = tracker.update([core_det(10)], 2000)[0].track_id
    assert second != first


def test_motion_core_never_associates_another_class_or_camera():
    tracker = VehicleTracker(min_hits=1)
    first = tracker.update([core_det(10)], 0)[0].track_id
    tracker.update([core_det(10, kind="bus")], 100)
    tracker.update([core_det(10, camera="B")], 200)
    assert tracker.active_count() == 3
    assert next(t for t in tracker._tracks if t.track_id == first).cls == "car"


def test_capacity_keeps_real_observations_instead_of_lost_predictions():
    tracker = VehicleTracker(min_hits=1, max_tracks=2)
    tracker.update([core_det(0), core_det(500)], 0)
    result = tracker.update([core_det(1000)], 1000)
    assert tracker.active_count() <= 2
    assert any(t.observed_bbox[0] == 1000 and t.time_since_update_ms == 0 for t in result)


def test_motion_adapter_recovers_motion_across_a_short_occlusion(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_ANPR_TRACKER", "motion")
    tracker = LiveTracker()
    box = lambda x: (x, 0, x+140, 100, "car", .9)
    identity = tracker.update([box(0)], 0)[0][0].track_id
    tracker.update([box(60)], 1)
    tracker.update([box(120)], 2)
    lost, _ = tracker.update([], 3)
    assert all(t.misses > 0 for t in lost)
    recovered, _ = tracker.update([box(240)], 4)
    observed = [t for t in recovered if t.misses == 0]
    assert observed[0].track_id == identity
    assert observed[0].x1 == 240  # not smoothed/predicted coordinates in evidence


@pytest.fixture
def traffic_api(rig, monkeypatch):
    from app.api import traffic
    svc, factory, *_ = rig
    monkeypatch.setattr(traffic, "live_anpr_service", svc)
    app = FastAPI()
    for prefix in ("/api", "/api/v1"):
        app.include_router(traffic.router, prefix=prefix)
    def session():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = session
    with TestClient(app) as client:
        yield client


def test_config_persists_is_camera_scoped_and_has_v1_alias(traffic_api, rig):
    _, factory, *_ = rig
    cfg = TrafficConfig(mode="line", position=.4).model_dump()
    response = traffic_api.put("/api/cameras/cam1/traffic-config", json=cfg)
    assert response.status_code == 200
    assert traffic_api.get("/api/v1/cameras/CAM1/traffic-config").json()["config"] == cfg
    assert traffic_api.get("/api/cameras/cam2/traffic-config").json()["config"]["mode"] == "off"
    assert len(rows(factory, CameraTrafficConfig)) == 1
    assert traffic_api.put("/api/cameras/cam1/traffic-config", json={"mode":"zone", "right":.1}).status_code == 422
    assert traffic_api.get("/api/cameras/cam1/traffic-config").json()["config"] == cfg
    assert traffic_api.get("/api/cameras/missing/traffic-config").status_code == 404


def test_config_reset_does_not_clear_plate_votes_or_saved_sightings(traffic_api, rig):
    svc, factory, _, _, process = rig
    before = process()
    cfg = TrafficConfig(mode="zone").model_dump()
    saved = traffic_api.put("/api/cameras/cam1/traffic-config", json=cfg).json()
    after = process()
    assert len(rows(factory)) == 3  # second agreeing read, not a cold OCR restart
    assert after["traffic"]["config_revision"] == saved["revision"]
    assert after["traffic"]["session_id"] != before["traffic"]["session_id"]
    assert after["traffic"]["crossings"] == 0  # already inside is not an entry
    assert traffic_api.post("/api/cameras/cam1/traffic-reset").status_code == 200
    reset = process()
    assert reset["traffic"]["reset_reason"] == "operator reset"
    assert len(rows(factory)) == 3
    assert {d["event_id"] for d in reset["detections"]} == {d["event_id"] for d in after["detections"]}


def test_counting_has_separate_budget_and_does_not_require_ocr(rig, monkeypatch):
    _, factory, _, messages, process = rig
    monkeypatch.setattr(live.vehicle_detection_service, "detect", lambda frame: [
        VehicleDetection(10+i*80, 20, 70+i*80, 150, "car", .94) for i in range(5)
    ])
    calls = []
    monkeypatch.setattr(live, "read_plate_for_vehicle", lambda *args: calls.append(args) or None)
    process()
    result = process()
    assert result["traffic"]["observed_tracks"] == result["traffic"]["by_class"]["car"] == 5
    assert len(result["detections"]) == len(result["photos"]) == 3
    assert len(calls) == 6  # no second detector/OCR pipeline for counting
    assert not rows(factory) and not messages


def test_sessions_are_separate_recordings_labelled_and_resets_are_honest(traffic_api, rig):
    _, _, _, _, process = rig
    process("CAM1"); first = process("CAM1")
    process("CAM2"); process("CAM2")
    entries = traffic_api.get("/api/traffic/sessions").json()["items"]
    assert len(entries) == 2
    assert next(e for e in entries if e["camera_id"] == "cam2")["recorded"] is True
    assert next(e for e in entries if e["camera_id"] == "cam1")["recorded"] is False
    after = process("CAM1", discontinuity=True)
    assert after["traffic"]["session_id"] != first["traffic"]["session_id"]
    assert after["traffic"]["observed_tracks"] == 0


def test_exact_two_percent_configuration_is_valid():
    TrafficConfig(span_start=.23, span_end=.25, left=.23, right=.25)


def test_invalid_internal_timestamps_never_enter_tracking(rig):
    import numpy as np
    svc, factory, _, _, _ = rig
    for value in (float('nan'), float('inf'), -1):
        assert not svc.submit('CAM1', np.zeros((30, 50, 3), np.uint8), media_time=value)
    assert not svc._states and not rows(factory)
