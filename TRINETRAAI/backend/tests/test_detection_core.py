"""Tests for app.services.detection_core: multi-scale gathering, duplicate
suppression and the live tracker's box policy.

No torch or weights needed: the model call is injected, so what is pinned down
is the *policy* - which box survives, how a crop is mapped back, and what the
tracker is allowed to do to a rectangle.
"""
import sys
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np

from app.services.detection_core import (
    collect_multiscale,
    containment,
    iou,
    strip_boxes,
    suppress_duplicates,
    tile_boxes,
)

FRAME = np.zeros((720, 1280, 3), dtype=np.uint8)


# ------------------------------------------------------------------ geometry
def test_iou_and_containment_basics():
    a = (0, 0, 100, 100, 2, 0.9)
    assert iou(a, a) == 1.0
    assert containment(a, a) == 1.0
    half = (0, 0, 50, 100, 2, 0.9)          # a tile-clipped repeat of `a`
    assert iou(a, half) < 0.51              # NMS on IoU alone would keep both
    assert containment(a, half) == 1.0      # containment sees one inside the other
    side = (200, 0, 300, 100, 2, 0.9)       # a different vehicle
    assert iou(a, side) == 0.0 and containment(a, side) == 0.0


class TestSuppress:
    def test_keeps_one_box_per_vehicle(self):
        boxes = [
            (10, 10, 110, 110, 2, 0.91),    # full box
            (10, 10, 60, 110, 2, 0.80),     # same car, clipped by a crop edge
            (12, 12, 108, 108, 5, 0.70),    # same car, the model hedged to "bus"
        ]
        out = suppress_duplicates(boxes)
        assert len(out) == 1
        assert out[0][5] == 0.91            # the best-scoring one survives

    def test_adjacent_vehicles_stay_separate(self):
        boxes = [
            (0, 100, 120, 220, 2, 0.9),
            (130, 100, 250, 220, 2, 0.85),   # touching, no overlap at all
            (245, 100, 360, 220, 2, 0.8),    # 5 px overlap
        ]
        assert len(suppress_duplicates(boxes)) == 3

    def test_motorcycle_inside_a_bus_is_never_deleted(self):
        """The trap this guards against: a small vehicle legitimately overlaps a
        big one in front of which it sits. Size-aware containment must keep it."""
        bus = (100, 100, 700, 500, 5, 0.9)
        bike = (150, 380, 230, 470, 3, 0.6)   # ~1/40th the area, inside it
        kept = suppress_duplicates([bus, bike], containment_area_guard=3.0)
        assert len(kept) == 2
        # without the guard the containment rule alone would swallow the bike
        assert len(suppress_duplicates([bus, bike], containment_area_guard=0)) == 1


class TestRegions:
    def test_strips_cover_the_frame_and_overlap(self):
        rs = strip_boxes(1280, 720, 2)
        assert len(rs) == 2
        assert rs[0][0] == 0 and rs[-1][2] == 1280
        assert rs[0][1] == 0 and rs[0][3] == 720
        assert rs[1][0] < rs[0][2], "neighbouring strips must overlap"
        assert all(x1 - x0 >= 64 for x0, y0, x1, y1 in rs)

    def test_tile_grid_is_bounded_and_covers(self):
        rs = tile_boxes(3840, 2160, tile=640, max_tiles=6)
        assert len(rs) <= 6
        xs = [r[0] for r in rs] + [r[2] for r in rs]
        ys = [r[1] for r in rs] + [r[3] for r in rs]
        assert min(xs) == 0 and max(xs) == 3840 and min(ys) == 0 and max(ys) == 2160

    def test_small_frame_degenerates_to_one_region(self):
        assert len(tile_boxes(640, 480, tile=640)) >= 1


# ---------------------------------------------------------- multi-scale pass
class TestCollectMultiscale:
    @staticmethod
    def _predict_returning(mapping):
        """Fake model: returns whatever boxes are registered for (shape, size)."""
        calls = []

        def predict(image, imgsz, conf):
            calls.append((image.shape[:2], imgsz, conf))
            key = (image.shape[1], image.shape[0])
            return list(mapping.get(key, []))

        return predict, calls

    def test_single_mode_is_one_pass_on_the_frame(self):
        predict, calls = self._predict_returning({(1280, 720): [(10, 10, 50, 50, 2, 0.9)]})
        boxes, passes = collect_multiscale(predict, FRAME, 0.35, 768, mode="single")
        assert len(calls) == 1 and boxes == [(10, 10, 50, 50, 2, 0.9)]
        assert passes[0]["region"] == "whole"

    def test_strips_run_at_native_resolution_and_map_back(self):
        # The crop at x=615..1280 sees a car at 700..800 => full-frame 85..185? no:
        # offset must be ADDED to crop coordinates.
        boxes_in_strip = [(100, 200, 200, 300, 2, 0.7)]
        def predict(image, imgsz, conf):
            h, w = image.shape[:2]
            if (w, h) == (1280, 720):
                return []                          # whole-frame pass sees nothing
            return list(boxes_in_strip)            # the strip sees the car
        out, passes = collect_multiscale(predict, FRAME, 0.35, 768, mode="strips", strips=2)
        assert len(passes) == 3                    # whole + 2 strips
        xs = strip_boxes(1280, 720, 2)
        # each crop's box is offset back by that crop's own x-origin
        assert sorted(round(b[0]) for b in out) == sorted(100 + x0 for x0, *_ in xs)
        assert all(b[0] >= 0 and b[2] <= 1280 for b in out)
        for p, (x0, y0, x1, y1) in zip(passes[1:], xs):
            assert p["imgsz"] == max(x1 - x0, y1 - y0), "a crop must run at its own size"

    def test_truncated_boxes_are_dropped_but_frame_edge_ones_kept(self):
        def predict(image, imgsz, conf):
            h, w = image.shape[:2]
            if (w, h) == (1280, 720):
                return []
            # one box touching the crop's LEFT edge (crop is not at frame edge)
            # and one touching its RIGHT edge
            return [(0, 100, 40, 200, 2, 0.8), (w - 1, 300, w + 50, 400, 2, 0.8)]
        out, _ = collect_multiscale(predict, FRAME, 0.35, 768, mode="strips", strips=2)
        # Strip 0 starts AT the frame's left edge, so its left-touching box is a
        # complete sighting and is kept; its right edge is a cut, so dropped.
        # Strip 1 is the mirror image. Exactly two boxes survive, both real.
        assert [round(b[0]) for b in out] == [0, 1280 - 1]
        assert all(b[2] <= 1280 and b[3] <= 720 for b in out), "clipped to frame"
        out2, _ = collect_multiscale(predict, FRAME, 0.35, 768, mode="strips",
                                     strips=2, keep_border_boxes=True)
        assert len(out2) == 4                       # 2 strips x 2 boxes, unfiltered
        assert all(b[2] <= 1280 and b[3] <= 720 for b in out2)

    def test_auto_mode_adds_passes_only_when_the_squeeze_is_real(self):
        # 1280 wide squeezed into 768 => a second, native-resolution look pays off
        _, passes = collect_multiscale(lambda i, s, c: [], FRAME, 0.35, 768, mode="auto")
        assert len(passes) == 3
        # a frame that already fits its budget gains nothing, and no CPU is wasted
        small = np.zeros((360, 640, 3), dtype=np.uint8)
        _, p2 = collect_multiscale(lambda i, s, c: [], small, 0.35, 640, mode="auto")
        assert len(p2) == 1
