"""Tests for the standalone detection module's box geometry.

These run without torch/ultralytics: the model is stubbed, so what is being
pinned down is the module's *policy* around the boxes, not the network:

* vehicle rectangles are the model's, clipped to the frame, never padded grown
  or replaced by fixed-size boxes;
* non-vehicle class names can never be drawn as vehicles;
* a coarse single-class ``vehicle`` weight is not used for vehicle boxes when a
  per-class weight is available (that is what stopped one box covering several
  parked vehicles);
* the number-plate stage keeps its own confidence/resolution, so tightening the
  vehicle stage cannot change ANPR behaviour.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.detector import DetectionResult, VehiclePlateDetector  # noqa: E402
from core.visualizer import Visualizer  # noqa: E402


# --------------------------------------------------------------------- stubs
class _T:
    """Minimal tensor stand-in (float list with .item()/.tolist())."""

    def __init__(self, values):
        self._v = list(values)

    def __len__(self):
        return len(self._v)

    def __getitem__(self, i):
        return _T([self._v[i]]) if isinstance(i, int) else _T(self._v)

    def item(self):
        return self._v[0]

    def tolist(self):
        return self._v


class _Box:
    def __init__(self, xyxy, cls, conf):
        self.xyxy = [_T(xyxy)]
        self.cls = _T([cls])
        self.conf = _T([conf])

    def __len__(self):
        return 1


class _Result:
    def __init__(self, boxes):
        self.boxes = boxes


class StubModel:
    """Stand-in for ultralytics.YOLO: records the call, replays fixed boxes."""

    def __init__(self, path, names, boxes):
        self.names = names
        self._boxes = boxes
        self.calls = []
        self.path = path

    def predict(self, image, **kw):
        self.calls.append(kw)
        keep = kw.get("classes")
        boxes = [b for b in self._boxes if keep is None or int(b.cls.tolist()[0]) in keep]
        return [_Result(boxes)]


def _install(monkeypatch, primary, vehicle=None):
    """Make `from ultralytics import YOLO` / `import torch` return the stubs."""
    def YOLO(path):  # noqa: N802 - mirrors ultralytics' API
        if vehicle is not None and str(path) == str(getattr(vehicle, "path", None)):
            return vehicle
        return primary

    ultra = types.ModuleType("ultralytics")
    ultra.YOLO = YOLO
    # never touch the real weights directory while resolving a stub path
    monkeypatch.setattr(VehiclePlateDetector, "_resolve_model_path",
                        lambda self, path: str(path))
    torch_stub = types.ModuleType("torch")
    torch_stub.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "ultralytics", ultra)
    monkeypatch.setitem(sys.modules, "torch", torch_stub)


PRIMARY_NAMES = {0: "vehicle", 1: "number_plate"}
COCO_NAMES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck", 62: "tv"}
FRAME = np.zeros((360, 640, 3), dtype=np.uint8)


# ----------------------------------------------------------------- geometry
def test_boxes_are_the_models_own_clipped_to_the_frame(monkeypatch):
    primary = StubModel("p", PRIMARY_NAMES, [_Box([100, 60, 300, 200], 0, 0.9),
                                             _Box([500, 300, 900, 800], 0, 0.8)])
    _install(monkeypatch, primary)
    monkeypatch.setattr(VehiclePlateDetector, "_resolve_vehicle_model", lambda self, p: None)
    d = VehiclePlateDetector(model_path="p", conf_threshold=0.35, use_coco_vehicles=False)
    dets = d.detect(FRAME)
    assert d.vehicles(dets)[0].bbox == [100, 60, 300, 200]          # untouched
    assert d.vehicles(dets)[1].bbox == [500, 300, 640, 360]         # clipped, not grown


def test_tuning_is_asked_of_the_model_not_applied_afterwards(monkeypatch):
    primary = StubModel("p", PRIMARY_NAMES, [_Box([10, 10, 40, 40], 0, 0.9)])
    _install(monkeypatch, primary)
    monkeypatch.setattr(VehiclePlateDetector, "_resolve_vehicle_model", lambda self, p: None)
    d = VehiclePlateDetector(model_path="p", conf_threshold=0.35, iou_threshold=0.45,
                             imgsz=960, use_coco_vehicles=False)
    d.detect(FRAME)
    call = primary.calls[0]
    assert call["conf"] == 0.35 and call["iou"] == 0.45 and call["imgsz"] == 960
    assert call["agnostic_nms"] is True          # one vehicle, one box
    assert "resize" not in call and "scale" not in call  # no coordinate surgery


def test_plate_stage_keeps_its_own_confidence_and_resolution(monkeypatch):
    """Raising the vehicle threshold must not change what ANPR is fed."""
    primary = StubModel("p", PRIMARY_NAMES, [_Box([10, 10, 40, 40], 0, 0.55),
                                             _Box([20, 20, 60, 40], 1, 0.30)])
    _install(monkeypatch, primary)
    monkeypatch.setattr(VehiclePlateDetector, "_resolve_vehicle_model", lambda self, p: None)
    d = VehiclePlateDetector(model_path="p", conf_threshold=0.60, imgsz=1024,
                             use_coco_vehicles=False)
    dets = d.detect(FRAME)
    # a 0.55 vehicle misses the 0.60 cut, a 0.30 plate still passes the plate floor
    assert [x.class_name for x in d.vehicles(dets)] == []
    assert [x.class_name for x in d.plates(dets)] == ["number_plate"]
    plate_call = primary.calls[-1]
    assert plate_call["conf"] == 0.25            # historical plate floor
    assert plate_call["imgsz"] == 640            # historical plate resolution
    assert primary.calls[0]["imgsz"] == 1024     # vehicles use the vehicle size


# --------------------------------------------------------- model / class roles
def test_coarse_vehicle_weight_is_not_used_for_vehicle_boxes(monkeypatch, tmp_path):
    """The fix for 'one huge box over several vehicles'."""
    primary = StubModel("p", PRIMARY_NAMES, [_Box([0, 0, 640, 360], 0, 1.0)])
    good = StubModel("per-class", COCO_NAMES, [_Box([10, 10, 90, 70], 2, 0.8),
                                               _Box([200, 100, 260, 150], 3, 0.7),
                                               _Box([300, 10, 340, 60], 0, 0.9)])  # person
    good.path = "weights/coco.pt"
    _install(monkeypatch, primary, good)
    monkeypatch.setattr(VehiclePlateDetector, "_resolve_vehicle_model",
                        lambda self, p: "weights/coco.pt")
    d = VehiclePlateDetector(model_path="p", conf_threshold=0.35)
    dets = d.detect(FRAME)
    names = sorted(x.class_name for x in d.vehicles(dets))
    assert names == ["car", "motorcycle"], "vehicle boxes must come from the per-class weight"
    assert all(x.bbox != [0, 0, 640, 360] for x in d.vehicles(dets))
    assert d.plates(dets) == []                   # plate head still on the fine-tuned weight
    assert primary.calls, "the plate model must still be consulted"


def test_explicit_opt_out_keeps_single_weight_behaviour(monkeypatch):
    primary = StubModel("p", PRIMARY_NAMES, [_Box([5, 5, 50, 50], 0, 0.9)])
    _install(monkeypatch, primary)
    monkeypatch.setattr(VehiclePlateDetector, "_resolve_vehicle_model",
                        lambda self, p: None if (p or "").lower() == "none" else "x")
    d = VehiclePlateDetector(model_path="p", vehicle_model_path="none")
    assert d.vehicle_model_path is None
    assert len(d.vehicles(d.detect(FRAME))) == 1


def test_filter_by_class_still_matches_the_legacy_names():
    dets = [DetectionResult([0, 0, 10, 10], 2, "car", 0.9, kind="vehicle"),
            DetectionResult([1, 1, 11, 11], 3, "motorcycle", 0.8, kind="vehicle"),
            DetectionResult([2, 2, 22, 12], 1, "number_plate", 0.7, kind="plate")]
    # the three helpers are pure filters; `self` is unused, so call them bare
    assert len(VehiclePlateDetector.filter_by_class(None, dets, "vehicle")) == 2
    assert len(VehiclePlateDetector.filter_by_class(None, dets, "number_plate")) == 1
    assert len(VehiclePlateDetector.vehicles(None, dets)) == 2
    assert len(VehiclePlateDetector.plates(None, dets)) == 1


# -------------------------------------------------------------------- drawing
def test_visualizer_draws_exactly_the_box_in_green():
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    dets = [DetectionResult([100, 60, 300, 200], 2, "car", 0.91, kind="vehicle")]
    out = Visualizer.draw_detections(frame, dets)
    green = (0, 220, 50)
    # border pixels on each side of the rectangle...
    for pt in [(60, 150), (200, 150), (130, 100), (130, 300)]:
        assert tuple(int(v) for v in out[pt[0], pt[1]]) == green, f"{pt} is not the box line"
    # ...and the interior is left alone (no fill, no overlay over the vehicle)
    assert tuple(int(v) for v in out[130, 200]) == (0, 0, 0)


def test_plate_boxes_keep_their_own_colour():
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    dets = [DetectionResult([10, 10, 60, 30], 1, "number_plate", 0.9, kind="plate")]
    out = Visualizer.draw_detections(frame, dets)
    assert tuple(int(v) for v in out[10, 35]) == (0, 215, 255)
