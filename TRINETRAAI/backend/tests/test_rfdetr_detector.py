"""
RF-DETR adapter — contract, class mapping and graceful degradation.

These tests deliberately do **not** need ``rfdetr`` (or torch) installed: the
prediction payload is stubbed with the exact object shape RF-DETR returns (a
``supervision``-style ``Detections`` with ``xyxy`` / ``confidence`` /
``class_id``). That keeps the suite runnable on a CPU-only box while still
locking the two things most likely to break silently:

1. the COCO class-id → vehicle-name mapping, and
2. the "RF-DETR missing ⇒ fall back, never crash" guarantee.
"""
import sys
from pathlib import Path

for _p in [str(Path(__file__).resolve().parents[1])]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pytest

from app.core.config import settings
from app.services import rfdetr_detector as rd
from app.services.rfdetr_detector import rfdetr_detector
from app.services.vehicle_detection_service import vehicle_detection_service


class FakeDetections:
    """The subset of ``supervision.Detections`` that the adapter reads."""

    def __init__(self, xyxy, confidence, class_id):
        self.xyxy = np.asarray(xyxy, dtype=float)
        self.confidence = np.asarray(confidence, dtype=float)
        self.class_id = np.asarray(class_id, dtype=int)


def _names():
    return rd._coco_class_names()


def _ids_for(*labels):
    """COCO name -> RF-DETR's 0-indexed class id, from the real name table."""
    names = list(_names())
    return [names.index(label) for label in labels]


# --------------------------------------------------------------------------- #
# COCO class mapping
# --------------------------------------------------------------------------- #
def test_coco_index_zero_is_person_and_two_is_car():
    names = _names()
    assert names[0] == "person"
    assert names[1] == "bicycle"
    assert names[2] == "car"
    assert names[3] == "motorcycle"
    assert names[5] == "bus"
    assert names[7] == "truck"


def test_vehicle_classes_are_kept_and_others_dropped():
    """car/motorcycle/bus/truck survive; a person box must not."""
    ids = _ids_for("car", "person", "bus", "motorcycle", "truck", "bicycle", "dog")
    det = FakeDetections(
        [
            [10, 10, 100, 80],
            [10, 10, 100, 80],
            [10, 10, 100, 80],
            [10, 10, 100, 80],
            [10, 10, 100, 80],
            [10, 10, 100, 80],
            [10, 10, 100, 80],
        ],
        [0.9] * 7,
        ids,
    )
    out = rfdetr_detector._to_tuples(det, rd.VEHICLE_CLASS_NAMES, (480, 640))
    assert [o[4] for o in out] == ["car", "bus", "motorcycle", "truck"]


def test_boxes_are_clamped_to_the_frame_and_degenerate_ones_dropped():
    """A box wider than the frame or 1 px tall must not reach the tracker."""
    ids = _ids_for("car", "car", "car")
    det = FakeDetections(
        [[-20, -5, 5000, 60], [10, 10, 100, 80], [10, 10, 11, 80]],
        [0.9, 0.9, 0.9],
        ids,
    )
    out = rfdetr_detector._to_tuples(det, rd.VEHICLE_CLASS_NAMES, (480, 640))
    assert len(out) == 2                       # the 1 px-wide box is dropped
    assert out[0][0] == 0 and out[0][1] == 0   # clamped to the frame
    assert out[0][2] == 640 and out[0][3] == 60


def test_empty_prediction_is_not_an_error():
    det = FakeDetections(np.zeros((0, 4)), np.zeros((0,)), np.zeros((0,), dtype=int))
    assert rfdetr_detector._to_tuples(det, rd.VEHICLE_CLASS_NAMES, (480, 640)) == []


# --------------------------------------------------------------------------- #
# Graceful degradation
# --------------------------------------------------------------------------- #
def test_detect_returns_empty_when_model_unavailable(monkeypatch):
    """No RF-DETR installed (or it failed to load) ⇒ no boxes, no exception."""
    monkeypatch.setattr(rfdetr_detector, "_model", None)
    monkeypatch.setattr(rfdetr_detector, "_attempted", True)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    assert rfdetr_detector.detect(frame) == []


def test_detect_swallows_inference_errors(monkeypatch):
    """A model that raises on predict() must not take the analysis worker down."""
    class Boom:
        def predict(self, *a, **kw):
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(rfdetr_detector, "_model", Boom())
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    assert rfdetr_detector.detect(frame) == []


def test_available_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "RFDETR_ENABLED", False)
    assert rfdetr_detector.available is False


def test_label_reports_why_it_is_unavailable(monkeypatch):
    monkeypatch.setattr(rfdetr_detector, "_model", None)
    monkeypatch.setattr(rfdetr_detector, "_error", "no weights")
    assert "unavailable" in rfdetr_detector.label
    assert "no weights" in rfdetr_detector.label


# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #
def test_backend_order_respects_setting(monkeypatch):
    monkeypatch.setattr(settings, "DETECTOR_BACKEND", "yolo")
    assert vehicle_detection_service._backend_order() == ["yolo"]

    monkeypatch.setattr(settings, "DETECTOR_BACKEND", "rfdetr")
    assert vehicle_detection_service._backend_order() == ["rfdetr", "yolo"]

    monkeypatch.setattr(settings, "DETECTOR_BACKEND", "auto")
    assert vehicle_detection_service._backend_order() == ["rfdetr", "yolo"]


def test_detector_falls_back_to_next_backend(monkeypatch):
    """If RF-DETR cannot be built, YOLO is tried instead of giving up."""
    monkeypatch.setattr(settings, "DETECTOR_BACKEND", "rfdetr")
    monkeypatch.setattr(rd.rfdetr_detector, "load", lambda: None)
    monkeypatch.setattr(rd.rfdetr_detector, "_error", "weights unavailable", raising=False)

    service = type(vehicle_detection_service)()
    monkeypatch.setattr(service, "_load_yolo", lambda: "yolo-model")
    assert service._ensure_model() == "yolo-model"
    assert service.backend == "yolo"


def test_detector_disables_itself_when_every_backend_fails(monkeypatch):
    """No detector at all ⇒ enabled=False, detect()=[] — never a crash."""
    monkeypatch.setattr(settings, "DETECTOR_BACKEND", "rfdetr")
    monkeypatch.setattr(rd.rfdetr_detector, "load", lambda: None)
    monkeypatch.setattr(rd.rfdetr_detector, "_error", "no weights", raising=False)

    service = type(vehicle_detection_service)()

    def _boom():
        raise RuntimeError("ultralytics missing")

    monkeypatch.setattr(service, "_load_yolo", _boom)
    assert service._ensure_model() is None
    assert service.enabled is False
    assert service.detect(np.zeros((8, 8, 3), dtype=np.uint8)) == []


def test_vehicle_service_routes_frames_through_rfdetr(monkeypatch):
    """DETECTOR_BACKEND=rfdetr ⇒ detect() uses RF-DETR and converts its tuples."""
    monkeypatch.setattr(settings, "DETECTOR_BACKEND", "rfdetr")
    monkeypatch.setattr(rd.rfdetr_detector, "load", lambda: object())
    monkeypatch.setattr(
        rd.rfdetr_detector,
        "detect",
        lambda frame, threshold=None: [(10, 20, 110, 90, "car", 0.88),
                                       (200, 30, 300, 120, "bus", 0.71)],
    )
    monkeypatch.setattr(rd.rfdetr_detector, "last_inference_ms", 42.0)

    service = type(vehicle_detection_service)()
    assert service._ensure_model() is not None
    assert service.backend == "rfdetr"

    out = service.detect(np.zeros((240, 320, 3), dtype=np.uint8))
    assert [(d.class_name, d.confidence, d.x1, d.y2) for d in out] == [
        ("car", 0.88, 10, 90),
        ("bus", 0.71, 200, 120),
    ]
    assert service.last_inference_ms == 42.0


def test_vehicle_service_still_uses_yolo_when_asked(monkeypatch):
    """DETECTOR_BACKEND=yolo must not touch RF-DETR at all."""
    monkeypatch.setattr(settings, "DETECTOR_BACKEND", "yolo")

    def _boom(*_a, **_kw):
        raise AssertionError("RF-DETR must not be used when backend=yolo")

    monkeypatch.setattr(rd.rfdetr_detector, "detect", _boom)

    class FakeYolo:
        def predict(self, frame, **kw):
            class B:
                xyxy = type("T", (), {"cpu": lambda self: type("N", (), {"numpy": lambda self: [[1, 2, 30, 40]]})()})()
                conf = type("T", (), {"cpu": lambda self: type("N", (), {"numpy": lambda self: [0.9]})()})()
                cls = type("T", (), {"cpu": lambda self: type("N", (), {"numpy": lambda self: [2.0]})()})()
            return [type("R", (), {"boxes": B()})()]

    service = type(vehicle_detection_service)()
    monkeypatch.setattr(service, "_load_yolo", lambda: FakeYolo())
    service._ensure_model()
    assert service.backend == "yolo"
    out = service.detect(np.zeros((240, 320, 3), dtype=np.uint8))
    assert [d.class_name for d in out] == ["car"]
