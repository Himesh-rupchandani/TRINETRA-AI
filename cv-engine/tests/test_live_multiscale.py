"""Live-view multi-scale detection in cv-engine.

The fake model below is not a stub that returns canned boxes: it *simulates the
resolution limit* that motivated the change. A detector sees what the resized
input shows it, so a vehicle shorter than roughly 18 px after the letterbox is
simply not resolvable. Every component big enough at that scale is reported with
an exact, tight box.

That makes the test say something real:

* the single pass at imgsz 960 misses the small distant vehicle;
* the multi-scale pass finds it, because its strips are fed at native resolution;
* the merge maps crop boxes back by their offset and keeps exactly ONE box per
  vehicle, with the true coordinates - so the extra passes cannot double-box a
  car, merge two cars, or invent geometry;
* ingest (`multiscale=False`) still makes exactly one model call.
"""
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from detection.vehicle_detector import VehicleDetector, _multiscale

torch = pytest.importorskip("torch")

FRAME_W, FRAME_H = 1280, 720
MIN_SIDE_AT_MODEL_RES = 18          # px needed after resizing to `imgsz`
VEHICLES = [
    (100, 100, 180, 60),            # a car, clearly resolvable at any scale
    (700, 300, 120, 70),            # a van
    (1150, 600, 30, 18),            # a distant motorcycle: 22x13 at 0.75 scale
]


def _frame():
    img = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
    for (x, y, w, h) in VEHICLES:
        img[y:y + h, x:x + w] = 255
    return img


class _ResolutionLimitedModel:
    """Connected components, but only those the given imgsz can actually resolve."""

    names = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
    calls = None          # class attribute: shared across instances on purpose

    def __init__(self):
        pass

    def predict(self, image, **kw):
        if _ResolutionLimitedModel.calls is None:
            _ResolutionLimitedModel.calls = []
        _ResolutionLimitedModel.calls.append((int(image.shape[1]), int(kw.get("imgsz", 0))))
        h, w = image.shape[:2]
        scale = float(kw.get("imgsz", max(h, w))) / max(h, w)
        gray = (image.max(axis=2) > 128).astype(np.uint8)
        count, _labels, stats, _cent = cv2.connectedComponentsWithStats(gray, 8)
        boxes, confs, clss = [], [], []
        for i in range(1, count):
            x, y, bw, bh, area = (int(v) for v in stats[i])
            if area < 40:
                continue
            if min(bw, bh) * scale < MIN_SIDE_AT_MODEL_RES:
                continue          # invisible at this working resolution
            boxes.append([x, y, x + bw, y + bh])
            confs.append(0.8)
            clss.append(2)
        # .reshape(-1, 4) keeps an empty result a correctly shaped empty tensor
        ns = SimpleNamespace(boxes=SimpleNamespace(
            xyxy=torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
            conf=torch.tensor(confs, dtype=torch.float32).reshape(-1),
            cls=torch.tensor(clss, dtype=torch.float32).reshape(-1),
        ))
        return [ns]


@pytest.fixture(autouse=True)
def _reset_calls():
    _ResolutionLimitedModel.calls = []
    yield


def test_the_shared_geometry_module_is_loadable():
    """Guards the by-path import: a moved file must degrade, never crash."""
    mod = _multiscale()
    assert mod is not None, "trinetra_detection/core/multiscale.py must be reachable"
    assert hasattr(mod, "collect_multiscale") and hasattr(mod, "suppress_duplicates")


def test_single_pass_misses_the_vehicle_it_cannot_resolve():
    d = VehicleDetector(imgsz=960, multiscale=False)
    d._model = _ResolutionLimitedModel()
    dets = d.detect(_frame())
    assert len(dets) == 2, [det.bbox for det in dets]
    assert len(_ResolutionLimitedModel.calls) == 1, "ingest pays for one pass only"


def test_multiscale_finds_it_and_still_draws_one_tight_box_per_vehicle():
    d = VehicleDetector(imgsz=960, multiscale=True, strips=2)
    d._model = _ResolutionLimitedModel()
    dets = d.detect(_frame())

    assert len(_ResolutionLimitedModel.calls) >= 3, "whole frame + the strips"
    assert [det.bbox for det in dets], "some boxes"
    got = sorted(round(v) for det in dets for v in det.bbox)
    # VEHICLES are (x, y, w, h); a detector answers in corners
    want = sorted(v for (x, y, w, h) in VEHICLES for v in (x, y, x + w, y + h))
    assert got == want, f"expected one exact box per vehicle, got {[d_.bbox for d_ in dets]}"
    assert len(dets) == len(VEHICLES), "no duplicates from the overlapping crops"
    assert [d.class_name for d in dets] == ["car"] * 3
    assert all(det.class_name == "car" for det in dets)
    # audit trail proves the extra passes ran at the crops' native size
    assert any(p["region"] != "whole" for p in d.last_passes)
    strip_passes = [p for p in d.last_passes if p["region"] != "whole"]
    for p in strip_passes:
        x0, _y0, x1, _y1 = p["region"]
        assert p["imgsz"] == max(x1 - x0, FRAME_H), "each crop is fed at its own size"


def test_boxes_never_leave_the_frame_and_are_never_grown():
    d = VehicleDetector(imgsz=768, multiscale=True, strips=3)
    d._model = _ResolutionLimitedModel()
    for det in d.detect(_frame()):
        x1, y1, x2, y2 = det.bbox
        assert 0 <= x1 < x2 <= FRAME_W and 0 <= y1 < y2 <= FRAME_H
        assert (x2 - x1) <= 200 and (y2 - y1) <= 80, "no box grew past its vehicle"
