"""Live ANPR plumbing tests. Detector/OCR outputs are fixtures, NOT accuracy claims."""
import asyncio
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database.database import get_db
from app.database.models import Alert, Base, Camera, VehicleEvent, Watchlist
from app.services import live_anpr_service as live
from app.services.anpr_pipeline import PlateRead
from app.services.plate_detector_service import PlateBox
from app.services.vehicle_detection_service import VehicleDetection
from app.services.ws_manager import ConnectionManager


class Clock:
    value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds=1.1):
        self.value += seconds


PLATES = ["GJ01AB1234", "GJ02CD5678", "GJ03EF9012"]


def vehicles(count=3):
    return [VehicleDetection(10 + 200*i, 20, 180 + 200*i, 220, "car", .94) for i in range(count)]


def plate_read(frame, bbox, vehicle_class, confidence=.94, **kwargs):
    index = min(2, int(bbox[0]) // 200)
    x, y, _, _ = bbox
    return PlateRead(PLATES[index], PLATES[index], confidence, confidence, True,
                     PlateBox(int(x)+30, int(y)+80, int(x)+140, int(y)+110, .9, "fixture"))


@pytest.fixture
def rig(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'live.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([
            Camera(camera_id="CAM1", name="First camera", stream_url="rtsp://test.invalid/1", stream_type="rtsp", status="ONLINE"),
            Camera(camera_id="CAM2", name="Second camera", stream_url="/clips/recorded.mp4", stream_type="file", status="ONLINE"),
            Camera(camera_id="EMPTY", name="No source", stream_url="", status="OFFLINE"),
        ])
        db.commit()
    clock = Clock()
    svc = live.LiveAnprService(factory, clock=clock)
    # Process selected samples deterministically unless a test explicitly starts workers.
    monkeypatch.setattr(svc, "start", lambda: None)
    monkeypatch.setattr(live, "live_anpr_service", svc)
    monkeypatch.setattr(settings, "LIVE_ANPR_ENABLED", True)
    monkeypatch.setattr(settings, "VEHICLE_DETECTION_ENABLED", True)
    monkeypatch.setattr(settings, "LIVE_ANPR_SAMPLE_SECONDS", 1.0)
    monkeypatch.setattr(settings, "LIVE_ANPR_MAX_VEHICLES", 3)
    monkeypatch.setattr(settings, "LIVE_ANPR_WORKERS", 1)
    monkeypatch.setattr(settings, "LIVE_ANPR_DEDUP_SECONDS", 60)
    monkeypatch.setattr(settings, "LIVE_ANPR_OVERLAY_TTL_SECONDS", 3.0)
    monkeypatch.setattr(settings, "ANPR_MIN_AGREE_READS", 2)
    monkeypatch.setattr(settings, "OCR_LOW_CONFIDENCE_MARK", .8)
    monkeypatch.setattr(settings, "EVIDENCE_ROOT", str(tmp_path / "evidence"))
    monkeypatch.setattr(live.vehicle_detection_service, "_disabled_reason", None)
    monkeypatch.setattr(live.vehicle_detection_service, "last_error", None)
    monkeypatch.setattr(live.vehicle_detection_service, "detect", lambda frame: vehicles())
    monkeypatch.setattr(type(live.ocr_service), "available", property(lambda self: True))
    monkeypatch.setattr(live, "read_plate_for_vehicle", plate_read)
    messages = []
    monkeypatch.setattr(live.ws_manager, "broadcast_threadsafe", lambda kind, payload: messages.append((kind, payload)))

    def process(camera="CAM1", media_time=None, discontinuity=False, frame=None, source_id="test"):
        if frame is None:
            frame = np.full((360, 640, 3), 127, dtype=np.uint8)
        assert svc.submit(camera, frame, source_id=source_id, media_time=media_time, discontinuity=discontinuity)
        key = camera.upper()
        packet = svc._pending.pop(key)
        svc._process(packet, svc._states[key])
        clock.advance()
        return svc.snapshot(camera)

    yield svc, factory, clock, messages, process
    svc.stop()
    engine.dispose()


def rows(factory, model=VehicleEvent):
    with factory() as db:
        return db.query(model).all()


def test_three_plates_confirmed_persisted_broadcast_and_drawn(rig):
    svc, factory, _, messages, process = rig
    first = process()
    assert all(d["plate_number"] is None for d in first["detections"])
    assert rows(factory) == []  # a single lucky OCR read is not a sighting
    second = process()
    assert {d["plate_number"] for d in second["detections"]} == set(PLATES)
    stored = rows(factory)
    assert len(stored) == len(messages) == 3
    assert all(e.plate_status == "HIGH" and e.evidence_ref and e.bbox for e in stored)
    for kind, payload in messages:
        assert kind == "VEHICLE_DETECTED"
        assert payload["evidence_ref"] and payload["plate_status"] == "HIGH"
        assert payload["event_id"] in {e.id for e in stored}
        assert (Path(settings.EVIDENCE_ROOT) / payload["evidence_ref"]).is_file()
    annotated = svc.annotate("cam1", np.full((360, 640, 3), 127, dtype=np.uint8))
    assert np.count_nonzero(annotated[:, :, 1] > 200) > 100


def test_unreadable_is_unknown_never_invented(rig, monkeypatch):
    _, factory, _, messages, process = rig
    monkeypatch.setattr(live, "read_plate_for_vehicle", lambda *args, **kwargs: None)
    for _ in range(3):
        result = process()
        assert all(d["plate_status"] == "UNKNOWN" and d["plate_number"] is None for d in result["detections"])
    assert not rows(factory) and not messages


def test_conflicting_reads_need_fresh_agreement(rig, monkeypatch):
    _, factory, _, _, process = rig
    monkeypatch.setattr(live.vehicle_detection_service, "detect", lambda frame: vehicles(1))
    process()
    read = PlateRead("GJ01ZZ9999", "GJ01ZZ9999", .95, .95, True)
    monkeypatch.setattr(live, "read_plate_for_vehicle", lambda *args, **kwargs: read)
    process()
    assert rows(factory) == []
    process()
    assert [e.plate_number for e in rows(factory)] == [read.normalized]


def test_low_confidence_read_is_labelled_and_cannot_trigger_watchlist(rig, monkeypatch):
    _, factory, _, messages, process = rig
    with factory() as db:
        db.add(Watchlist(plate_number=PLATES[0], category="stolen vehicle", active=True))
        db.commit()
    monkeypatch.setattr(live, "read_plate_for_vehicle", lambda *args, **kwargs: plate_read(*args, confidence=.7))
    process()
    process()
    assert len(rows(factory)) == 3
    assert all(e.plate_status == "LOW_CONFIDENCE" and not e.watchlist_match for e in rows(factory))
    assert rows(factory, Alert) == []
    assert all(kind == "VEHICLE_DETECTED" for kind, _ in messages)


def test_watchlist_uses_same_event_and_does_not_duplicate_broadcast(rig):
    _, factory, _, messages, process = rig
    with factory() as db:
        db.add(Watchlist(plate_number=PLATES[0], category="stolen vehicle", active=True))
        db.commit()
    process()
    process()
    assert len(rows(factory, Alert)) == 1
    alerts = [payload for kind, payload in messages if kind == "ALERT_CREATED"]
    assert len(messages) == 3 and len(alerts) == 1
    assert alerts[0]["event_id"] == rows(factory, Alert)[0].event_id


def test_repeated_frames_and_reconnect_do_not_spam(rig):
    svc, factory, _, messages, process = rig
    for _ in range(8):
        process()
    svc.forget("cam1")
    process()
    process()
    assert len(rows(factory)) == len(messages) == 3


def test_same_plate_on_another_camera_is_a_new_sighting(rig):
    _, factory, _, messages, process = rig
    for camera in ("cam1", "cam2"):
        process(camera)
        process(camera)
    assert len(rows(factory)) == len(messages) == 6
    recorded = [e for e in rows(factory) if e.camera_id == "CAM2"]
    assert all(e.video_file == "recorded.mp4" for e in recorded)


def test_genuine_revisit_after_cooldown_is_logged(rig):
    svc, factory, clock, messages, process = rig
    process()
    process()
    with factory() as db:
        for event in db.query(VehicleEvent):
            event.created_at = datetime.now(timezone.utc) - timedelta(seconds=70)
        db.commit()
    clock.advance(70)
    svc.forget("cam1")
    process()
    process()
    assert len(rows(factory)) == len(messages) == 6


def test_recorded_offset_is_preserved_and_stale_boxes_expire(rig):
    svc, factory, clock, _, process = rig
    process("CAM2", media_time=12.0)
    result = process("CAM2", media_time=13.0)
    assert result["detections"]
    assert all(e.video_offset_sec == 13 for e in rows(factory))
    clock.advance(4)
    assert svc.snapshot("CAM2")["detections"] == []
    assert not svc.annotate("CAM2", np.zeros((360, 640, 3), dtype=np.uint8)).any()


@pytest.mark.parametrize("reset", ["backwards", "discontinuity", "shape", "gap"])
def test_scene_change_cannot_reuse_previous_vehicle_vote(rig, reset):
    _, factory, clock, _, process = rig
    process(media_time=10)
    if reset == "gap":
        clock.advance(6)
    process(media_time=2 if reset == "backwards" else 11,
            discontinuity=reset == "discontinuity",
            frame=np.zeros((400, 700, 3), dtype=np.uint8) if reset == "shape" else None)
    assert rows(factory) == []


def test_latest_frame_mailboxes_are_bounded_fair_and_throttled(rig, monkeypatch):
    svc, _, clock, _, _ = rig
    monkeypatch.setattr(settings, "LIVE_ANPR_MAX_CAMERAS", 2)
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    assert svc.submit("cam1", frame)
    assert not svc.submit("CAM1", frame)  # one sample/sec across ALL viewers
    assert svc.submit("cam2", frame)
    assert not svc.submit("cam3", frame)  # bounded memory
    clock.advance()
    assert svc.submit("cam1", frame + 42)
    assert list(svc._pending) == ["CAM1", "CAM2"]  # replacement preserves fairness
    assert int(svc._pending["CAM1"].frame[0, 0, 0]) == 42
    assert len(svc._states) == 2
    clock.advance(settings.LIVE_ANPR_IDLE_SECONDS + 1)
    assert svc.submit("cam3", frame)  # idle cameras free capacity
    assert list(svc._pending) == ["CAM3"]


def test_frozen_video_and_competing_viewer_do_not_count_as_agreement(rig):
    svc, factory, clock, _, process = rig
    process(media_time=12, source_id="viewer1")
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    assert not svc.submit("cam1", frame, source_id="viewer1", media_time=12)
    assert not svc.submit("cam1", frame, source_id="viewer2", media_time=12.5)
    assert svc.snapshot("cam1", source_id="viewer2")["detections"] == []
    clock.advance(4)
    process(media_time=13, source_id="viewer2")
    assert rows(factory) == []


def test_vehicle_budget_limits_ocr_work(rig, monkeypatch):
    _, factory, _, _, process = rig
    monkeypatch.setattr(live.vehicle_detection_service, "detect", lambda frame: vehicles(5))
    called = []
    monkeypatch.setattr(live, "read_plate_for_vehicle", lambda *args, **kwargs: called.append(args) or plate_read(*args))
    result = process(frame=np.zeros((400, 1200, 3), dtype=np.uint8))
    assert len(called) == len(result["detections"]) == 3
    assert rows(factory) == []


def test_capture_is_nonblocking_and_busy_worker_discards_old_pending_frames(rig, monkeypatch):
    svc, _, clock, _, _ = rig
    entered, release = threading.Event(), threading.Event()
    observed = []

    def detector(frame):
        observed.append(int(frame[0, 0, 0]))
        entered.set()
        assert release.wait(3)
        return []

    monkeypatch.setattr(live.vehicle_detection_service, "detect", detector)
    monkeypatch.setattr(svc, "start", lambda: live.LiveAnprService.start(svc))
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    try:
        assert svc.submit("cam1", frame)
        assert entered.wait(2)
        clock.advance()
        assert svc.submit("cam1", frame + 1)  # returns while model is still blocked
        clock.advance()
        assert svc.submit("cam1", frame + 2)
        assert len(svc._pending) == 1
    finally:
        release.set()
    with svc._condition:
        assert svc._condition.wait_for(lambda: not svc._pending and not svc._busy, timeout=3)
    assert observed == [0, 2]


def test_model_failure_is_isolated_and_next_camera_still_works(rig, monkeypatch):
    svc, factory, _, _, _ = rig
    monkeypatch.setattr(svc, "start", lambda: live.LiveAnprService.start(svc))

    def detector(frame):
        if not frame.any():
            raise RuntimeError("fixture model error")
        return []

    monkeypatch.setattr(live.vehicle_detection_service, "detect", detector)
    svc.submit("cam1", np.zeros((24, 32, 3), dtype=np.uint8))
    svc.submit("cam2", np.ones((24, 32, 3), dtype=np.uint8))
    with svc._condition:
        assert svc._condition.wait_for(lambda: not svc._pending and not svc._busy, timeout=3)
    assert svc.snapshot("cam1")["status"] == "ERROR"
    assert svc.snapshot("cam2")["status"] == "SCANNING"
    assert not rows(factory)


def test_ocr_missing_and_feature_disabled_are_honest(rig, monkeypatch):
    svc, factory, _, messages, process = rig
    monkeypatch.setattr(type(live.ocr_service), "available", property(lambda self: False))
    assert process()["status"] == "UNAVAILABLE"
    assert not rows(factory) and not messages
    monkeypatch.setattr(settings, "LIVE_ANPR_ENABLED", False)
    assert not svc.submit("cam1", np.zeros((24, 32, 3), dtype=np.uint8))
    assert svc.snapshot("cam1")["status"] == "DISABLED"
    assert svc.snapshot("cam1")["detections"] == []


@pytest.fixture
def api(rig, monkeypatch):
    from app.api import live_anpr
    from app.api.alerts import router as alerts_router
    from app.api.events import router as events_router
    svc, factory, *_ = rig
    monkeypatch.setattr(live_anpr, "live_anpr_service", svc)
    app = FastAPI()
    app.include_router(live_anpr.router, prefix="/api")
    app.include_router(alerts_router, prefix="/api")
    app.include_router(events_router, prefix="/api")

    def db_session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    with TestClient(app) as client:
        yield client


def test_frame_api_validation_and_throttling(api, rig, monkeypatch):
    jpeg = cv2.imencode(".jpg", np.zeros((100, 200, 3), dtype=np.uint8))[1].tobytes()
    headers = {"Content-Type": "image/jpeg"}
    assert api.post("/api/cameras/unknown/detect-frame", content=jpeg, headers=headers).status_code == 404
    assert api.post("/api/cameras/empty/detect-frame", content=jpeg, headers=headers).status_code == 409
    assert api.post("/api/cameras/cam1/detect-frame", content=jpeg).status_code == 415
    assert api.post("/api/cameras/cam1/detect-frame", content=b"not a jpeg", headers=headers).status_code == 400
    assert api.post("/api/cameras/cam1/detect-frame", content=b"x" * (2*1024*1024+1), headers=headers).status_code == 413
    large = cv2.imencode(".jpg", np.zeros((2000, 2000, 3), dtype=np.uint8))[1].tobytes()
    assert api.post("/api/cameras/cam1/detect-frame", content=large, headers=headers).status_code == 413
    for time in ("nan", "inf", "-1"):
        assert api.post(f"/api/cameras/cam1/detect-frame?media_time={time}", content=jpeg, headers=headers).status_code == 422
    res = api.post("/api/cameras/cam1/detect-frame?client_id=tab1&media_time=1", content=jpeg, headers=headers)
    assert res.status_code == 200 and res.json()["accepted"] is True
    assert api.post("/api/cameras/CAM1/detect-frame", content=jpeg, headers=headers).json()["accepted"] is False
    assert api.get("/api/cameras/CAM1/anpr").json()["max_vehicles"] == 3
    assert api.get("/api/cameras/unknown/anpr").status_code == 404
    monkeypatch.setattr(settings, "LIVE_ANPR_ENABLED", False)
    assert api.post("/api/cameras/cam1/detect-frame", content=jpeg, headers=headers).status_code == 503


def test_vehicle_log_api_has_reliability_evidence_and_camera_provenance(api, rig):
    *_, process = rig
    process()
    process()
    data = api.get("/api/events?camera_id=CAM1").json()
    assert data["total"] == 3
    event = data["items"][0]
    assert event["plate_status"] == "HIGH" and event["evidence_ref"].startswith("live/cam1/")
    assert event["bbox"] and event["vehicle_confidence"] == .94
    assert api.get(f'/api/events/{event["id"]}').json()["plate_number"] == event["plate_number"]


def test_no_scripted_alerts_in_live_mode(api, rig, monkeypatch):
    _, factory, *_ = rig
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "DEMO_ALERTS_ENABLED", False)
    assert api.post("/api/alerts/trigger").status_code == 409
    assert rows(factory) == [] and rows(factory, Alert) == []


@pytest.mark.asyncio
async def test_worker_fanout_reaches_application_sse_queue(rig, monkeypatch):
    _, factory, _, _, process = rig
    manager = ConnectionManager()
    manager.attach_loop(asyncio.get_running_loop())
    queue = manager.subscribe_sse()
    monkeypatch.setattr(live, "ws_manager", manager)
    try:
        await asyncio.to_thread(process)
        assert queue.empty()
        await asyncio.to_thread(process)
        import json
        payloads = [json.loads(await asyncio.wait_for(queue.get(), 2)) for _ in range(3)]
        assert all(p["type"] == "VEHICLE_DETECTED" for p in payloads)
        assert {p["payload"]["event_id"] for p in payloads} == {e.id for e in rows(factory)}
    finally:
        manager.unsubscribe_sse(queue)
        manager.detach_loop()


def test_ocr_uses_bounded_threads_and_does_not_enlarge_every_crop_to_736px(monkeypatch):
    from types import SimpleNamespace
    from app.services.ocr_service import OcrService
    supplied = {}
    def engine(**kwargs):
        supplied.update(kwargs)
        return object()
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", SimpleNamespace(RapidOCR=engine))
    monkeypatch.setattr(settings, "OCR_ENABLED", True)
    assert OcrService().available
    assert supplied["intra_op_num_threads"] == settings.CV_CPU_THREADS
    assert supplied["inter_op_num_threads"] == 1
    assert supplied["det_limit_type"] == "max"
    assert supplied["det_limit_side_len"] == 640


def test_two_line_bike_plates_use_weakest_line_confidence():
    from app.services.anpr_pipeline import plate_text_candidates
    lines = [("GJ03D", .96), ("E8157", .72)]
    joined = plate_text_candidates(lines, join_lines=True)
    assert ("GJ03D\nE8157", .72) in joined
    assert plate_text_candidates(lines, join_lines=False) == lines
    # Never concatenate two complete plates from neighbouring vehicles.
    assert len(plate_text_candidates([(PLATES[0], .9), (PLATES[1], .9)], join_lines=True)) == 2


def test_bundled_plate_model_fallback_and_class_filter(monkeypatch):
    from types import SimpleNamespace
    from app.services.plate_detector_service import PlateDetectorService
    service = PlateDetectorService()
    monkeypatch.setattr(settings, "PLATE_MODEL_PATH", "models/missing-site-model.pt")
    assert service._resolve_model_path().endswith("trinetra_detection/models/best.pt")
    monkeypatch.setattr(settings, "PLATE_MODEL_PATH", "")
    assert service._resolve_model_path() is None  # explicit classical-only choice

    class Array:
        def __init__(self, value): self.value = np.array(value)
        def cpu(self): return self
        def numpy(self): return self.value

    supplied = {}
    def predict(*args, **kwargs):
        supplied.update(kwargs)
        return [SimpleNamespace(boxes=SimpleNamespace(
            xyxy=Array([[0, 0, 100, 100], [10, 50, 80, 75]]),
            conf=Array([.99, .88]), cls=Array([0, 1]))) ]
    service._model_attempted = True
    service._model = SimpleNamespace(predict=predict)
    service._plate_class_ids = [1]
    boxes = service._detect_model(np.zeros((100, 100, 3), dtype=np.uint8), 5, 10)
    assert supplied["classes"] == [1]
    assert len(boxes) == 1 and boxes[0].as_list() == [15, 60, 85, 85]


def test_synthetic_camera_fallback_cannot_create_real_sightings(rig):
    from app.camera.packet import FramePacket
    svc, factory, *_ = rig
    packet = FramePacket(np.zeros((32, 64, 3), dtype=np.uint8), 1.0, "CAM1", 1, source_type="demo")
    assert svc.submit_packet(packet) is False
    assert not svc._pending and not rows(factory)


def test_confirmed_plate_stays_visible_while_next_sample_is_processing(rig, monkeypatch):
    svc, factory, _, _, process = rig
    process()
    process()

    def next_read(*args, **kwargs):
        snapshot = svc.snapshot("cam1")
        assert snapshot["status"] == "PROCESSING"
        assert {d["plate_number"] for d in snapshot["detections"]} == set(PLATES)
        return plate_read(*args)

    monkeypatch.setattr(live, "read_plate_for_vehicle", next_read)
    process()
    assert len(rows(factory)) == 3


def test_continuing_vehicle_detection_cannot_keep_an_old_unreadable_identity_forever(rig, monkeypatch):
    _, factory, _, _, process = rig
    process()
    process()
    monkeypatch.setattr(live, "read_plate_for_vehicle", lambda *args, **kwargs: None)
    for _ in range(6):
        snapshot = process()
    assert all(d["plate_number"] is None and d["event_id"] is None for d in snapshot["detections"])
    assert len(rows(factory)) == 3
    monkeypatch.setattr(live, "read_plate_for_vehicle", plate_read)
    first = process()
    assert all(d["plate_number"] is None for d in first["detections"])
    second = process()
    assert {d["plate_number"] for d in second["detections"]} == set(PLATES)
    assert len(rows(factory)) == 3  # rediscovery still respects the cooldown


def test_slow_configured_sampling_can_still_agree(rig, monkeypatch):
    _, factory, clock, _, process = rig
    monkeypatch.setattr(settings, "LIVE_ANPR_SAMPLE_SECONDS", 6.0)
    process()
    clock.advance(5.0)  # process() already advances by 1.1 seconds
    process()
    assert len(rows(factory)) == 3



def test_conflict_clears_an_already_confirmed_label_immediately(rig, monkeypatch):
    _, factory, _, _, process = rig
    monkeypatch.setattr(live.vehicle_detection_service, "detect", lambda frame: vehicles(1))
    process()
    process()
    monkeypatch.setattr(live, "read_plate_for_vehicle", lambda *args, **kwargs: PlateRead("GJ01ZZ9999", "GJ01ZZ9999", .95, .95, True))
    snapshot = process()
    assert snapshot["detections"][0]["plate_number"] is None
    assert snapshot["detections"][0]["event_id"] is None
    assert len(rows(factory)) == 1
    snapshot = process()
    assert snapshot["detections"][0]["plate_number"] == "GJ01ZZ9999"
    assert len(rows(factory)) == 2



def test_scene_cuts_reset_votes_and_old_boxes_never_paint_another_picture(rig):
    svc, factory, _, _, process = rig
    process()
    process()
    different_picture = np.full((360, 640, 3), 35, dtype=np.uint8)
    assert np.array_equal(svc.annotate("CAM1", different_picture.copy()), different_picture)
    first = process(frame=different_picture)
    assert all(d["plate_number"] is None for d in first["detections"])
    assert len(rows(factory)) == 3
    # New scene must agree again. Deduplication of the same real plate survives.
    second = process(frame=different_picture)
    assert {d["plate_number"] for d in second["detections"]} == set(PLATES)
    assert len(rows(factory)) == 3


def test_scene_guard_tolerates_small_brightness_changes(rig):
    svc, _, _, _, process = rig
    process()
    process()
    similar = np.full((360, 640, 3), 133, dtype=np.uint8)
    assert np.count_nonzero(svc.annotate("CAM1", similar)[:, :, 1] > 200) > 100



def test_mjpeg_loop_seek_and_fast_decoder_do_not_draw_old_offsets(rig):
    svc, _, _, _, process = rig
    process("CAM2", media_time=12.0)
    process("CAM2", media_time=13.0)
    raw = np.full((360, 640, 3), 127, dtype=np.uint8)
    for media_time in (0.5, 11.0, 18.0):
        assert np.array_equal(svc.annotate("CAM2", raw.copy(), media_time=media_time), raw)
    assert np.count_nonzero(svc.annotate("CAM2", raw.copy(), media_time=13.1)[:, :, 1] > 200) > 100


def test_vehicle_photos_available_before_plate_confirmation(api, rig):
    _, factory, _, messages, process = rig
    first = process()
    assert len(first["photos"]) == 3
    assert not rows(factory) and not messages
    for photo in first["photos"]:
        assert photo["plate_number"] is None and photo["event_id"] is None
        assert photo["captured_at"] and photo["plate_image_path"]
        response = api.get("/api" + photo["image_path"])
        assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
        assert "private" in response.headers["cache-control"]
        image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
        assert image.shape == (200, 170, 3)  # exact detected vehicle, not a stock photo
        assert abs(float(image.mean()) - 127) < 2
        assert api.get("/api" + photo["plate_image_path"]).status_code == 200
    second = process()
    assert {photo["plate_number"] for photo in second["photos"]} == set(PLATES)
    assert {photo["event_id"] for photo in second["photos"]} == {e.id for e in rows(factory)}


def test_unreadable_or_missing_ocr_still_shows_actual_vehicle_photos(api, rig, monkeypatch):
    _, factory, _, messages, process = rig
    monkeypatch.setattr(type(live.ocr_service), "available", property(lambda self: False))
    result = process()
    assert result["status"] == "UNAVAILABLE" and len(result["photos"]) == 3
    assert all(p["plate_number"] is None and p["plate_image_path"] is None for p in result["photos"])
    assert all(api.get("/api" + p["image_path"]).status_code == 200 for p in result["photos"])
    assert not rows(factory) and not messages


def test_photo_preview_is_camera_scoped_and_expires(api, rig):
    svc, _, clock, _, process = rig
    photo = process()["photos"][0]
    path = "/api" + photo["image_path"]
    assert api.get(path.replace("/cam1/", "/cam2/")).status_code == 404
    assert api.get(path.replace("/vehicle.jpg", "/arbitrary.jpg")).status_code == 422
    assert api.get(path.replace("/cam1/", "/missing/")).status_code == 404
    clock.advance(live.PHOTO_PREVIEW_SECONDS + 1)
    assert svc.snapshot("cam1")["photos"] == []
    assert api.get(path).status_code == 404
    assert svc._photo_bytes == 0


def test_photo_cache_is_bounded_by_count_and_bytes(api, rig, monkeypatch):
    svc, _, _, _, process = rig
    monkeypatch.setattr(live, "MAX_PHOTO_BATCHES", 2)
    first = process()["photos"][0]
    for _ in range(4):
        result = process()
    assert len(svc._photo_batches) == 2
    assert api.get("/api" + first["image_path"]).status_code == 404
    assert api.get("/api" + result["photos"][0]["image_path"]).status_code == 200
    assert svc._photo_bytes == sum(batch.size for batch in svc._photo_batches.values())
    monkeypatch.setattr(live, "MAX_PHOTO_BYTES", 100)
    process()
    assert svc._photo_bytes <= 100
    assert svc.snapshot("cam1")["photos"] == []


def test_photo_capture_is_immutable_and_forget_releases_only_that_camera(api, rig):
    svc, _, _, _, process = rig
    first = process("CAM1")["photos"][0]
    original = api.get("/api" + first["image_path"]).content
    second = process("CAM1", frame=np.full((360, 640, 3), 210, dtype=np.uint8))["photos"][0]
    assert first["image_path"] != second["image_path"]
    assert api.get("/api" + first["image_path"]).content == original
    other = process("CAM2")["photos"][0]
    svc.forget("cam1")
    assert api.get("/api" + first["image_path"]).status_code == 404
    assert api.get("/api" + other["image_path"]).status_code == 200
    assert svc._photo_bytes == sum(batch.size for batch in svc._photo_batches.values())


def test_photo_endpoint_does_not_wait_for_ocr(api, rig, monkeypatch):
    svc, factory, _, _, _ = rig
    monkeypatch.setattr(svc, "start", lambda: live.LiveAnprService.start(svc))
    entered, release = threading.Event(), threading.Event()

    def slow_ocr(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return None

    monkeypatch.setattr(live, "read_plate_for_vehicle", slow_ocr)
    try:
        assert svc.submit("CAM1", np.full((360, 640, 3), 127, dtype=np.uint8))
        assert entered.wait(3)
        result = api.get("/api/cameras/cam1/anpr").json()
        assert result["status"] == "PROCESSING" and len(result["photos"]) == 3
        assert api.get("/api" + result["photos"][0]["image_path"]).status_code == 200
        assert not rows(factory)
    finally:
        release.set()
