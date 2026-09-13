"""Detector post-processing: model geometry preserved, NMS tuned, frames clipped.

Covers the tight-box contract for cv-engine:
- boxes are the model's ``xyxy`` clipped to the frame, never padded/grown;
- only vehicle classes are requested from the model (persons/benches cannot
  become vehicles at all, because they are filtered inside the model call);
- the tuning (conf, NMS IoU, class-agnostic NMS, imgsz) is passed to the model
  rather than applied to the rectangles afterwards.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from detection.vehicle_detector import VehicleDetector

torch = pytest.importorskip("torch")


def _fake_model(boxes, confs, clss, captured):
    class Model:
        names = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

        def predict(self, frame, **kw):
            captured.update(kw)
            ns = SimpleNamespace(
                boxes=SimpleNamespace(
                    xyxy=torch.tensor(boxes, dtype=torch.float32),
                    conf=torch.tensor(confs, dtype=torch.float32),
                    cls=torch.tensor(clss, dtype=torch.float32),
                )
            )
            return [ns]

    return Model()


FRAME = np.zeros((360, 640, 3), dtype=np.uint8)


def test_geometry_is_the_models_and_only_gets_clipped():
    seen = {}
    d = VehicleDetector()
    d._model = _fake_model(
        [[120.0, 60.0, 300.0, 200.0], [-40.0, -10.0, 700.0, 400.0], [5.0, 5.0, 6.0, 6.0]],
        [0.8, 0.7, 0.9],
        [2, 5, 7],
        seen,
    )
    dets = d.detect(FRAME)
    assert len(dets) == 2  # the 1x1 box is not a vehicle anyone can read
    assert dets[0].bbox == [120.0, 60.0, 300.0, 200.0]  # exactly what the model said
    # the overflowing box is bound to the frame, never the other way round
    assert dets[1].bbox == [0.0, 0.0, 640.0, 360.0]


def test_nms_and_class_filtering_are_asked_of_the_model():
    seen = {}
    d = VehicleDetector(nms_iou=0.45)
    d._model = _fake_model([[10, 10, 40, 40]], [0.9], [2], seen)
    d.detect(FRAME)
    assert seen["iou"] == 0.45
    assert seen["agnostic_nms"] is True
    assert seen["classes"] == d.class_ids
    assert set(seen["classes"]) <= {2, 3, 5, 7}
    assert seen["conf"] == d.conf_threshold


def test_non_vehicle_classes_are_dropped():
    seen = {}
    d = VehicleDetector()
    # person (0) and bicycle (1) are not vehicle classes -> no boxes at all
    d._model = _fake_model([[10, 10, 40, 40], [60, 60, 90, 90]], [0.95, 0.95], [0, 1], seen)
    assert d.detect(FRAME) == []
