"""Honest output: a recorded clip is never labelled LIVE, and what the overlay
shows is limited to what the loaded weight actually detected.

These three properties are the difference between a control room display and a
demo. Each one is asserted at the layer that decides it - the registry API, the
frame source, and the drawing layer that receives the model's own classes - so
none of them can quietly regress into "looks live, is not" or "labelled as a
class the model never produced".
"""
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.camera.manager import camera_manager
from app.database.database import get_db
from app.database.models import Base, Camera
from app.services.detection_core import iou
from app.services.vehicle_detection_service import (
    VehicleDetection,
    _LiveView,
    resolve_vehicle_classes,
)


@pytest.fixture()
def client(tmp_path):
    """Isolated DB with one file-backed, one network and one empty camera."""
    clip = tmp_path / "junction.mp4"
    clip.write_bytes(b"\x00" * 64)
    engine = create_engine(f"sqlite:///{tmp_path / 'h.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    from contextlib import asynccontextmanager
    from app.main import app

    @asynccontextmanager
    async def noop(_app):
        yield

    app.dependency_overrides[get_db] = override
    original = app.router.lifespan_context
    app.router.lifespan_context = noop
    db = Session()
    db.add_all([
        Camera(camera_id="CLIP1", name="Rec", stream_url=str(clip), stream_type="file",
               status="ONLINE", latitude=23.0, longitude=72.5),
        Camera(camera_id="NET1", name="Net", stream_url="http://host/index.m3u8",
               stream_type="hls", status="ONLINE", latitude=23.0, longitude=72.5),
        Camera(camera_id="EMPTY", name="Empty", stream_url="", stream_type="rtsp",
               status="OFFLINE"),
    ])
    db.commit()
    db.close()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.router.lifespan_context = original


# --------------------------------------------------------------- source honesty
def test_recorded_camera_is_reported_as_recorded(client):
    body = client.get("/api/cameras").json()
    items = {c["camera_id"]: c for c in body["data"]}
    assert items["CLIP1"]["source_kind"] == "RECORDED"
    assert items["NET1"]["source_kind"] == "LIVE"
    assert items["EMPTY"]["source_kind"] == "UNPROVISIONED"
    # A playable recorded clip is still ONLINE - honesty is about LIVE vs
    # RECORDED, it does not have to break the camera to tell the truth.
    assert items["CLIP1"]["status"] == "ONLINE"


def _unwrap(body):
    """Registry routes answer inside {"data": ...} or {"ok": true, ...}."""
    return body["data"] if isinstance(body, dict) and "data" in body else body


def test_detail_endpoint_carries_the_same_kind(client):
    assert _unwrap(client.get("/api/cameras/CLIP1").json())["source_kind"] == "RECORDED"
    assert _unwrap(client.get("/api/cameras/clip1").json())["source_kind"] == "RECORDED"


def test_stream_ticket_declares_its_source_kind(client):
    # GET is what the player calls (cameraService.getCameraStream).
    ticket = _unwrap(client.get("/api/cameras/CLIP1/stream").json())
    assert ticket["source_kind"] == "RECORDED"
    # the detection overlay route is the one a wall display opens
    assert ticket["detection_url"] and "live/detect" in ticket["detection_url"]


# ------------------------------------------------- the frame source knows too
def test_manager_marks_file_sources_recorded():
    """A resident worker's frames must know where they came from too."""
    class _Stream:
        source_type = "file"

    class _Net:
        source_type = "rtsp"

    saved = dict(camera_manager._streams)
    try:
        camera_manager._streams["clipcam"] = _Stream()
        camera_manager._streams["netcam"] = _Net()
        assert camera_manager.is_recording_backed("clipcam") is True
        assert camera_manager.is_recording_backed("CLIPCAM") is True, "ids are lowercase keys"
        assert camera_manager.is_recording_backed("netcam") is False
        assert camera_manager.is_recording_backed("absent") is False
    finally:
        camera_manager._streams.clear()
        camera_manager._streams.update(saved)


# ------------------------------------------- classes come from the loaded weight
def test_classes_are_read_off_the_weight_not_assumed():
    class FineTuned:
        names = {0: "car", 1: "motorcycle", 2: "auto-rickshaw", 3: "number_plate", 4: "person"}
    got = resolve_vehicle_classes(FineTuned())
    assert got == {0: "car", 1: "motorcycle", 2: "auto-rickshaw"}
    assert 3 not in got and 4 not in got, "plates and pedestrians are never vehicles"

    class COCO:
        names = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck", 8: "traffic light"}
    assert resolve_vehicle_classes(COCO) == {1: "bicycle", 2: "car", 3: "motorcycle",
                                            5: "bus", 7: "truck"}

    # A single all-vehicles head is exactly the coarse model that boxed whole
    # rows of parked bikes: it is not accepted as a vehicle source, and the
    # COCO ids it does not have mean it contributes no boxes.
    class Coarse:
        names = {0: "vehicle", 1: "number_plate"}
    from app.services.vehicle_detection_service import VEHICLE_CLASS_IDS
    assert resolve_vehicle_classes(Coarse()) == VEHICLE_CLASS_IDS


# ------------------------------------------------------------- ids, never ghost boxes
class _FakeService:
    _iou = staticmethod(iou)


def _view():
    view = _LiveView.__new__(_LiveView)
    view._svc = _FakeService()
    view._prev_ids = []
    view._next_id = 1
    import threading
    view._lock = threading.Lock()
    return view


def test_track_ids_follow_the_vehicle_across_passes():
    view = _view()
    first = [VehicleDetection(10, 10, 60, 40, "car", 0.9)]
    view._assign_ids(first)
    assert first[0].track_id == 1
    moved = [VehicleDetection(13, 12, 63, 42, "car", 0.88),
             VehicleDetection(300, 200, 360, 240, "bus", 0.7)]
    view._assign_ids(moved)
    assert [d.track_id for d in moved] == [1, 2], "same vehicle keeps its id"
    gone = [VehicleDetection(500, 300, 560, 340, "car", 0.8)]
    view._assign_ids(gone)
    assert gone[0].track_id == 3, "a new vehicle gets a new id"
    assert view._prev_ids, "ids are remembered, boxes are not carried forward"


def test_only_confirmed_boxes_are_numbered():
    # The view keeps a result ring for replay, but _assign_ids never writes into
    # it: after a pass with nothing in it, no box survives with a stale number.
    view = _view()
    view._assign_ids([VehicleDetection(0, 0, 20, 20, "car", 0.9)])
    view._assign_ids([])
    assert view._prev_ids == []


def test_label_carries_type_confidence_and_id():
    import cv2
    frame = np.zeros((720, 1280, 3), np.uint8)
    from app.services.vehicle_detection_service import VehicleDetectionService as V

    plain = np.zeros((720, 1280, 3), np.uint8)
    V.draw(plain, [VehicleDetection(100, 100, 300, 200, "car", 0.91)])
    V.draw(frame, [VehicleDetection(100, 100, 300, 200, "car", 0.91, track_id=7)])
    ink = lambda a: int((a[:, :, 1] > 200).sum())
    assert ink(frame) > ink(plain), "the id adds to the label"


def test_on_demand_live_path_numbers_boxes_too(monkeypatch):
    """The sync replay path must carry ids as well as the async worker.

    Two MJPEG consumers of the same file camera take different code paths, and a
    control-room wall that shows "motorcycle 0.6" without an id next to a
    worker-driven tile that shows "#7" is an inconsistency an operator would
    read as two different vehicles.
    """
    from app.services import vehicle_detection_service as mod

    calls = {"n": 0}
    boxes = [(10, 10, 60, 40), (14, 12, 64, 42), (16, 13, 66, 44)]

    def fake_detect(self, frame, conf=None, imgsz=None):
        x1, y1, x2, y2 = boxes[min(calls["n"], len(boxes) - 1)]
        calls["n"] += 1
        return [VehicleDetection(x1, y1, x2, y2, "car", 0.9)]

    monkeypatch.setattr(mod.VehicleDetectionService, "detect", fake_detect)
    monkeypatch.setattr(mod.settings, "LIVE_ASYNC_DETECT", False)
    monkeypatch.setattr(mod.settings, "DETECTION_EVERY_N_FRAMES", 1)
    svc = mod.VehicleDetectionService()
    frame = np.zeros((720, 1280, 3), np.uint8)
    svc.forget("syncids")
    ids = []
    for _ in range(3):
        svc._annotate_sync("syncids", frame.copy())
        with svc._state_lock:
            cached = svc._last_detections.get("syncids", [])
        ids.append([d.track_id for d in cached])
    assert ids == [[1], [1], [1]], ids
    svc.forget("syncids")
    with svc._state_lock:
        assert "syncids" not in svc._id_state, "forget() must drop id state too"
