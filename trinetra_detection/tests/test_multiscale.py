"""Multi-scale vehicle geometry in the standalone module.

Two jobs. First: pin down what the extra passes are allowed to do (crop, offset
back, drop a sighting a crop cut in half) and what they are forbidden to do
(edit a rectangle). Second: prove the copy in ``core/multiscale.py`` still
behaves exactly like the backend's reference implementation - they are separate
files only because this module ships standalone, and drift between them would
mean the two halves of the product disagree about what a vehicle looks like.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.multiscale import (  # noqa: E402
    collect_multiscale,
    containment,
    iou,
    strip_boxes,
    suppress_duplicates,
    tile_boxes,
)

FRAME = np.zeros((720, 1280, 3), dtype=np.uint8)


class TestGeometry:
    def test_identical_boxes_score_one(self):
        b = (0, 0, 10, 10, 2, 0.9)
        assert iou(b, b) == pytest.approx(1.0)
        assert containment(b, b) == pytest.approx(1.0)

    def test_smaller_box_inside_bigger_is_high_containment_low_iou(self):
        big, small = (0, 0, 100, 100, 2, 0.9), (10, 10, 30, 30, 2, 0.8)
        assert iou(big, small) < 0.1
        assert containment(big, small) == pytest.approx(1.0)

    def test_strips_cover_every_column(self):
        strips = strip_boxes(1280, 720, 3)
        assert strips[0][0] == 0 and strips[-1][2] == 1280
        seen = np.zeros(1280, dtype=bool)
        for (x1, _y1, x2, _y2) in strips:
            seen[x1:x2] = True
        assert seen.all(), "no column of the frame may go unexamined"

    def test_tile_grid_is_bounded(self):
        tiles = tile_boxes(1920, 1080, tile=640, max_tiles=6)
        assert 1 < len(tiles) <= 6


class TestSuppression:
    def test_repeat_of_the_same_vehicle_is_dropped(self):
        raw = [(0, 0, 100, 100, 2, 0.9), (2, 0, 102, 100, 2, 0.7)]
        assert len(suppress_duplicates(raw)) == 1

    def test_two_neighbouring_vehicles_survive(self):
        raw = [(0, 0, 100, 100, 2, 0.9), (105, 0, 205, 100, 2, 0.8)]
        assert len(suppress_duplicates(raw)) == 2

    def test_two_vehicles_whose_boxes_touch_are_both_kept(self):
        # Bumper-to-bumper parked cars: heavy overlap, comparable size, and the
        # answer must still be two boxes - merging them is the original complaint.
        a = (0, 0, 100, 100, 2, 0.9)
        b = (40, 0, 140, 100, 2, 0.85)
        assert iou(a, b) < 0.45 and containment(a, b) <= 0.60
        out = suppress_duplicates([a, b], iou_thr=0.45, containment_thr=0.60,
                                  containment_area_guard=3.0)
        assert len(out) == 2

    def test_the_smaller_box_is_never_deleted_because_a_bigger_one_covers_it(self):
        # A motorcycle parked in front of a bus is *legitimately* contained by
        # the bus's box. So containment is refused once the sizes diverge past
        # the guard: we keep a possibly-redundant big box instead of deleting a
        # real vehicle. Choosing between them is the model's job, not ours.
        bus = (0, 0, 400, 200, 5, 0.9)
        bike = (10, 10, 90, 90, 3, 0.8)
        out = suppress_duplicates([bus, bike], containment_thr=0.60,
                                  containment_area_guard=3.0)
        assert out == [bus, bike]

    def test_the_same_vehicle_seen_twice_at_one_scale_collapse_to_one(self):
        # Same object, two near-identical boxes from two passes -> one box.
        tight = (10, 10, 90, 90, 2, 0.9)
        repeat = (12, 11, 92, 91, 2, 0.7)
        assert len(suppress_duplicates([tight, repeat])) == 1


class TestCollect:
    def test_no_extra_pass_when_the_frame_already_fits(self):
        small = np.zeros((360, 640, 3), dtype=np.uint8)
        _, passes = collect_multiscale(lambda i, s, c: [], small, 0.35, 640, mode="auto")
        assert len(passes) == 1

    def test_wide_frame_gets_a_native_resolution_look(self):
        _, passes = collect_multiscale(lambda i, s, c: [], FRAME, 0.35, 768, mode="auto")
        assert len(passes) == 3, "whole frame + 2 strips"
        assert passes[0]["region"] == "whole"
        assert all(p["imgsz"] >= 700 for p in passes[1:])

    def test_crop_boxes_are_mapped_back_by_the_offset(self):
        def predict(crop, imgsz, conf):
            # a box 40px in from the crop's left edge: complete in both strips
            return [(40, 40, 80, 80, 2, 0.8)] if crop.shape[1] < 1280 else []
        out, passes = collect_multiscale(predict, FRAME, 0.35, 768, mode="strips", strips=2)
        assert out, "expected boxes from the strips"
        assert all(b[0] >= 0 and b[2] <= 1280 for b in out), "clipped to the frame"
        # Each strip's box must land at that strip's own offset. The offsets come
        # from the audit trail rather than being hard-coded, so this asserts the
        # mapping rule and not a lucky geometry.
        regions = [pa["region"] for pa in passes if pa["region"] != "whole"]
        assert len(regions) == 2
        assert {round(bb[0]) for bb in out} == {40 + r[0] for r in regions}

    def test_a_sighting_cut_by_the_crop_is_dropped_but_frame_edges_are_kept(self):
        def predict(crop, imgsz, conf):
            h, w = crop.shape[:2]
            if (w, h) == (1280, 720):
                return []          # keep the whole-frame pass silent for this test
            return [(0, 100, 40, 200, 2, 0.8), (w - 1, 300, w + 50, 400, 2, 0.8)]
        out, _ = collect_multiscale(predict, FRAME, 0.35, 768, mode="strips", strips=2)
        # strip 0 begins AT the frame's left edge: its left-touching box is a
        # complete sighting and stays; its right edge is a cut, so that one goes.
        # strip 1 is the mirror image. Two real boxes survive, both whole.
        assert [round(b[0]) for b in out] == [0, 1280 - 1]
        assert all(b[2] <= 1280 and b[3] <= 720 for b in out)
        out2, _ = collect_multiscale(predict, FRAME, 0.35, 768, mode="strips", strips=2,
                                      keep_border_boxes=True)
        assert len(out2) == 4


def _backend_reference():
    backend = Path(__file__).resolve().parents[2] / "TRINETRAAI" / "backend"
    if not (backend / "app" / "services" / "detection_core.py").exists():
        pytest.skip("backend reference implementation not present")
    sys.path.insert(0, str(backend))
    from app.services import detection_core as ref
    return ref


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_mirror_produces_exactly_the_backends_boxes(seed):
    """Same frames, same fake model, same settings -> identical boxes and passes."""
    ref = _backend_reference()
    rng = np.random.default_rng(seed)
    for _ in range(6):
        h = int(rng.integers(360, 1081))
        w = int(rng.integers(640, 1921))
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        def predict(image, imgsz, conf, _seed=seed):
            # Deterministic in the *input*, so both modules are shown exactly the
            # same fake detections (a shared generator would advance between calls
            # and compare two different worlds).
            r = np.random.default_rng([_seed, image.shape[0], image.shape[1], imgsz])
            out = []
            for _ in range(int(r.integers(0, 6))):
                x1 = float(r.integers(0, max(1, image.shape[1])))
                y1 = float(r.integers(0, max(1, image.shape[0])))
                out.append((x1, y1,
                            x1 + float(r.integers(10, 220)),
                            y1 + float(r.integers(10, 140)),
                            int(r.choice([2, 3, 5, 7])),
                            float(r.uniform(0.3, 0.95))))
            return out

        for mode in ("single", "strips", "tiles", "auto"):
            mine, my_passes = collect_multiscale(predict, frame, 0.35, 768, mode=mode, strips=2)
            theirs, their_passes = ref.collect_multiscale(predict, frame, 0.35, 768,
                                                          mode=mode, strips=2)
            assert my_passes == their_passes, mode
            mine2 = suppress_duplicates(mine, iou_thr=0.45, containment_thr=0.60,
                                        containment_area_guard=3.0)
            theirs2 = ref.suppress_duplicates(theirs, iou_thr=0.45, containment_thr=0.60,
                                              containment_area_guard=3.0)
            norm = lambda bs: [tuple(round(float(v), 4) for v in b) for b in bs]
            assert norm(mine2) == norm(theirs2), (mode, (w, h))


def test_detector_runs_the_extra_passes_for_vehicles_only():
    """Plates keep their own single pass at their own settings - ANPR must not move."""
    from core.detector import DetectionResult, VehiclePlateDetector

    calls = []

    det = VehiclePlateDetector.__new__(VehiclePlateDetector)     # no weights loaded
    det.conf_threshold, det.iou_threshold, det.imgsz = 0.35, 0.45, 960
    det.device, det.plate_conf_threshold, det.plate_imgsz = "cpu", 0.25, 640
    det.multiscale, det.multiscale_strips, det.last_multiscale_passes = True, 2, 1
    det.multiscale_mode = "strips"
    det.model = det.vehicle_model = det.plate_model = type("M", (), {"names": {2: "car"}})()
    det.vehicle_class_ids, det.plate_class_ids = [2], [1]

    def fake_run(model, image, threshold, imgsz, classes, force_kind=None):
        calls.append((int(imgsz), list(classes or []), image.shape[1]))
        if 2 in (classes or []):
            # One box glued to the right edge of whatever image was passed in:
            # complete when that image is the frame or a strip ending at the
            # frame's right edge, a cut sighting everywhere else.
            w = image.shape[1]
            return [DetectionResult([w - 30, 60, w, 100], 2, "car", 0.8)]  # noqa: E501
        return [DetectionResult([9, 9, 30, 20], 1, "number_plate", 0.5, kind="plate")]

    det._run = fake_run  # type: ignore[method-assign]
    out = det.detect(FRAME)

    assert [d.class_name for d in out if d.is_plate] == ["number_plate"]
    plate_calls = [c for c in calls if c[1] == [1]]
    assert plate_calls and all(c[0] == 640 for c in plate_calls)
    assert len(plate_calls) == 1, "plates are never multi-scaled"

    vehicle_calls = [c for c in calls if c[1] == [2]]
    assert len(vehicle_calls) == 3, f"whole frame + 2 strips, got {vehicle_calls}"
    assert [c[2] for c in vehicle_calls][0] == 1280, "first call is the whole frame"
    assert det.last_multiscale_passes == 3
    vehicles = [d for d in out if d.is_vehicle]
    # strip 0 saw the same vehicle cut in half -> dropped; strip 1 ends at the
    # frame edge, so its sighting is complete and maps back onto the whole-frame
    # box exactly -> deduplicated. One vehicle, one box, in frame coordinates.
    assert [d.bbox for d in vehicles] == [[1250, 60, 1280, 100]], [d.bbox for d in vehicles]
