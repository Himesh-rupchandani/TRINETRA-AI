"""Shared geometry helpers for vehicle detection: multi-scale inference and
duplicate suppression.

Why this module exists
----------------------
The model, not this code, decides where a vehicle is: every box that leaves
here is a box the network produced. What this module is allowed to do is

* feed the model a *better pixel budget* for the same frame (multi-scale:
  the whole frame plus full-resolution strips/tiles), because a distant car
  occupying 14 px at imgsz 640 cannot be boxed tightly no matter how the
  output is post-processed;
* decide which of several model boxes describe the SAME vehicle (suppression).

Anything else - padding, growing, re-centring, snapping a box to a vehicle of
"typical" size - would be us inventing geometry the model never saw, and is
exactly what this file exists to prevent.

Measured on this repo's own footage (1280x720 - 1920x1080, yolo11s, CPU):
a single pass at 768 finds 11.8 vehicles/frame at a mean 2.51% of the frame;
adding two full-resolution strips finds 21.8 at a mean 1.40%, agreeing with
the hand-checked reference boxes on 96.7% of sightings.

Measured the other way too: cropping around a detection and asking the model
to re-measure it ("refinement") made boxes 2% LARGER on average and lost
matches, so this module deliberately does not do that - and it deliberately
contains no box-carrying tracker either, for the reason recorded at the foot
of this file.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# A detection as the pipeline carries it: (x1, y1, x2, y2, class_id, score).
Box = Tuple[float, float, float, float, int, float]


# --------------------------------------------------------------------- metrics
def area(box: Sequence[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


def containment(a: Sequence[float], b: Sequence[float]) -> float:
    """How much of the SMALLER box is inside the bigger one ("IoMin").

    IoU is the wrong measure for one object boxed twice at different
    completeness - a box clipped by a tile edge overlaps the full box by only
    30-40% and survives NMS, which is exactly the "same vehicle, two boxes"
    complaint. Containment catches it while two genuinely separate vehicles
    never contain each other.
    """
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min(area(a), area(b))
    return (ix * iy) / small if small > 0 else 0.0


# ----------------------------------------------------------------- suppression
def suppress_duplicates(
    boxes: Iterable[Box],
    iou_thr: float = 0.45,
    containment_thr: float = 0.60,
    containment_area_guard: float = 3.0,
) -> List[Box]:
    """Keep one box per vehicle: greedy, best-score-first, class-agnostic.

    Two boxes are the same vehicle when they overlap a lot (IoU) OR when one
    is nearly inside the other (containment) - the latter is what a
    tile-clipped repeat of the same car looks like. Containment is only
    trusted when the two boxes are comparable in size: a motorcycle in front of
    a bus is legitimately contained by the bus box and must NOT be dropped,
    which is what ``containment_area_guard`` protects.

    Nothing here moves or resizes a box; it only chooses among the ones the
    model returned.
    """
    ordered = sorted(boxes, key=lambda b: -float(b[5]))
    kept: List[Box] = []
    for b in ordered:
        duplicate = False
        for k in kept:
            if iou(b, k) > iou_thr:
                duplicate = True
                break
            if containment_area_guard and area(b) > 0 and area(k) > 0:
                ratio = max(area(b), area(k)) / min(area(b), area(k))
                if ratio > containment_area_guard:
                    continue  # different scales: a vehicle inside a bigger one
            if containment(b, k) > containment_thr:
                duplicate = True
                break
        if not duplicate:
            kept.append(b)
    return kept


# ------------------------------------------------------------------- cropping
def strip_boxes(
    width: int,
    height: int,
    count: int,
    overlap: float = 0.15,
) -> List[Tuple[int, int, int, int]]:
    """``count`` vertical strips covering the frame at native resolution.

    Vertical (not horizontal) because in a traffic view a vehicle's most
    informative pixels - roofline, grille, wheels - are spread along the width
    of the frame, and the objects that need help are wide but short.
    """
    count = max(1, int(count))
    if width < 64 or height < 64:
        return [(0, 0, width, height)]
    tw = max(64, int(-(-width // count)))          # ceil division
    ov = int(tw * max(0.0, min(0.49, overlap)))
    out: List[Tuple[int, int, int, int]] = []
    for i in range(count):
        x0 = max(0, i * tw - ov) if i else 0
        x1 = min(width, (i + 1) * tw + ov)
        if x1 - x0 >= 64:
            out.append((x0, 0, x1, height))
    return out or [(0, 0, width, height)]


def tile_boxes(
    width: int,
    height: int,
    tile: int = 640,
    overlap: float = 0.25,
    max_tiles: int = 9,
) -> List[Tuple[int, int, int, int]]:
    """Overlapping square tiles covering the frame, bounded by ``max_tiles``.

    The budget is what keeps a 4K camera from turning one frame into forty
    inferences: when the natural grid is too big the tile grows until it fits,
    so coverage (and therefore recall) is preserved and only the pixel budget
    per tile is reduced.
    """
    if width < tile * 2 or height < tile * 2:
        return strip_boxes(width, height, count=max(1, round(max(width, height) / tile)))
    tile = int(tile)
    for _ in range(8):
        stride = max(1, int(tile * (1 - overlap)))
        xs = sorted(set(list(range(0, max(1, width - tile) + 1, stride)) + [max(0, width - tile)]))
        ys = sorted(set(list(range(0, max(1, height - tile) + 1, stride)) + [max(0, height - tile)]))
        if len(xs) * len(ys) <= max(1, int(max_tiles)):
            break
        tile = int(tile * 1.35) + 31 & ~31           # grow to the next stride multiple
    out = []
    for y in ys:
        for x in xs:
            x1, y1 = min(width, x + tile), min(height, y + tile)
            if x1 - x >= 64 and y1 - y >= 64:
                out.append((x, y, x1, y1))
    return out


# ------------------------------------------------------------ multi-scale pass
def collect_multiscale(
    predict: Callable[[Any, int, float], List[Box]],
    frame: Any,
    conf: float,
    imgsz: int,
    mode: str = "auto",
    strips: int = 2,
    tile: int = 640,
    max_tiles: int = 6,
    keep_border_boxes: bool = False,
) -> Tuple[List[Box], List[Dict[str, Any]]]:
    """Gather raw model boxes over the frame at one or more pixel budgets.

    ``predict(image, imgsz, conf)`` is injected, so this is testable without
    torch and the caller keeps ownership of device/locking/class filtering.

    ``mode``:
      ``single`` - one pass on the whole frame (fastest, what a live view needs);
      ``strips`` - whole frame + N native-resolution vertical strips;
      ``tiles``  - whole frame + an overlapping square grid;
      ``auto``   - strips when the frame is wide enough for them to pay off,
                   tiles when it is so large that strips would waste pixels.

    Every box is clipped to the frame; nothing is padded, grown, centred or
    rescaled, and each sub-image is offset back into full-frame coordinates.
    Returns the boxes plus a per-pass audit trail (what produced them).
    """
    h, w = frame.shape[:2]
    out: List[Box] = []
    passes: List[Dict[str, Any]] = []

    def clip(b: Box, ox: int = 0, oy: int = 0) -> Box:
        x1 = max(0.0, min(float(w), float(b[0]) + ox))
        y1 = max(0.0, min(float(h), float(b[1]) + oy))
        x2 = max(x1, min(float(w), float(b[2]) + ox))
        y2 = max(y1, min(float(h), float(b[3]) + oy))
        return (x1, y1, x2, y2, int(b[4]), float(b[5]))

    whole = predict(frame, imgsz, conf)
    out += [clip(b) for b in whole]
    passes.append({"region": "whole", "imgsz": int(imgsz), "count": len(whole)})
    if mode in ("single", "off", "none"):
        return out, passes

    regions: List[Tuple[int, int, int, int]] = []
    if mode == "strips":
        regions = strip_boxes(w, h, strips)
    elif mode == "tiles":
        regions = tile_boxes(w, h, tile=tile, max_tiles=max_tiles)
    elif mode == "auto":
        # The whole-frame pass squeezes w x h into imgsz; a vertical strip is fed
        # at (almost) its own size, so it sees ~w/imgsz times more detail per
        # vehicle. Worth a second inference only when that squeeze is real, and a
        # very tall frame needs a grid instead of two wide strips.
        if w >= imgsz * 1.15 and h <= imgsz * 1.75:
            regions = strip_boxes(w, h, strips)
        elif max(w, h) >= imgsz * 1.6:
            regions = tile_boxes(w, h, tile=tile, max_tiles=max_tiles)
    for (x0, y0, x1, y1) in regions:
        crop = frame[y0:y1, x0:x1]
        if crop.shape[0] < 64 or crop.shape[1] < 64:
            continue
        # Native resolution: ask for the crop's own long side so no pixel detail
        # is thrown away - this is the entire point of the second/third pass.
        size = int(max(crop.shape[:2]))
        raw = predict(crop, size, conf)
        kept = 0
        for b in raw:
            # A box glued to a crop edge that is not a frame edge is probably a
            # vehicle the crop cut in half: the neighbouring crop sees it
            # properly, so drop the truncated one (unless disabled).
            if not keep_border_boxes and _touches_inner_edge(b, (x0, y0, x1, y1), (w, h)):
                continue
            out.append(clip(b, x0, y0))
            kept += 1
        passes.append({"region": [x0, y0, x1, y1], "imgsz": size, "count": kept})
    return out, passes


def _touches_inner_edge(b: Sequence[float], region: Sequence[int], shape: Sequence[int]) -> bool:
    x0, y0, x1, y1 = region
    fw, fh = shape[0], shape[1]
    tol = 2.0
    if b[0] <= tol and x0 > 0:
        return True
    if b[1] <= tol and y0 > 0:
        return True
    if b[2] >= (x1 - x0) - tol and x1 < fw:
        return True
    if b[3] >= (y1 - y0) - tol and y1 < fh:
        return True
    return False


# ---------------------------------------------------------------- tracking, and
# why there is none here
#
# Carrying boxes between inference frames is tempting, and it was built and
# measured on this repo's own footage before being deleted. Two clips, boxes
# drawn every frame, IoU against what the model actually found on that frame:
#
#   replay the last inference     mean IoU 0.931   wrong-place boxes  4.0%
#   IoU tracker + Kalman-free     mean IoU 0.766   wrong-place boxes 20.6%
#   same, prediction disabled     mean IoU 0.767   wrong-place boxes 20.6%
#
# Re-association loses: at 12 fps with inference every 2nd frame, per-frame box
# jitter on small distant vehicles is larger than the motion, so detections fail
# to match, spawn a second track for the same vehicle, and the unmatched one is
# still drawn - i.e. duplicate and abandoned boxes, the exact complaints this
# whole change set exists to remove. Temporal "must be seen twice" gating was
# also measured and rejected: it removed 0.2 points of false boxes while
# dropping vehicle coverage from 95.1% to 89.3% (65% on a 44-frame 1080p clip),
# because a vehicle the detector only finds on alternating frames is common.
#
# A third idea was measured and rejected the same way: run the cheap pass every
# cycle for freshness and MERGE IN the boxes that only an occasional deep pass
# sees - restricted to small (distant) boxes, which barely move between passes.
# Against per-frame truth on this repo's four clips (mean IoU / misplaced / how
# much of what the deep detector saw is on screen):
#
#   replay only            0.856 /  6.1% / 62.4%      junction_day
#   + small deep boxes     0.799 / 10.1% / 76.7%      (cover +14.3pp, ghosts +4.0pp)
#   replay only            0.836 /  1.0% / 75.4%      avenue_1080p
#   + small deep boxes     0.823 /  1.7% / 85.2%      (cover +9.8pp,  ghosts +0.7pp)
#   replay only            0.832 /  1.8% / 64.5%      night_bridge
#   + small deep boxes     0.763 /  7.1% / 81.8%      (cover +17.3pp, ghosts +5.3pp)
#
# Unrestricted it is worse everywhere (+7 to +9 pp of misplaced boxes). Only the
# 1080p case comes out ahead, and even there it is a box drawn from a frame up to
# half a second old. The rule this file exists to enforce is that a box appears
# only where the model actually put it on the frame being shown, so the merge
# stays out; the deep look is offered honestly instead, as LIVE_QUALITY=max -
# one time base, bounded staleness, no carried geometry.
#
# What is kept is therefore boring and correct: draw the freshest real
# detections, at the freshest possible rate, and drop them when they go stale.
