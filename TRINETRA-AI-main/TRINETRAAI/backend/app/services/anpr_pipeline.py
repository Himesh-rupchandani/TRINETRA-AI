"""
Full ANPR pipeline for one detected vehicle (Part 7 of the brief).

    vehicle box
        -> plate DETECTION      (plate_detector_service: learned model or OpenCV)
        -> plate CROP
        -> PREPROCESSING        (super-resolution + CLAHE / Otsu variants)
        -> OCR                  (ocr_service: RapidOCR / EasyOCR)
        -> NORMALISATION        (normalize_plate + Indian-format validation)
        -> confidence TIERING   (HIGH / LOW_CONFIDENCE / UNKNOWN)

Hard rules enforced here:
* A plate is **never invented**. If nothing plate-shaped is read, the result is
  ``None`` and the sighting is recorded with ``plate_status = UNKNOWN``.
* Confidence is never upgraded. Non-Indian-format strings are *discounted*.
* Both the raw OCR string and the normalised plate are always preserved.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

# Resolved through app/core/vision so the API also boots on hosts without the
# CV extras (serverless/API-only mode) — see that module for the contract.
from ..core.vision import np

from ..core.config import settings
from ..utils.plate_normalizer import INDIAN_PLATE_RE, LOOSE_PLATE_RE
from .ocr_service import candidate_from_text, ocr_service, preprocess_variants
from .plate_detector_service import PlateBox, plate_detector_service

# Plate patterns are defined once, in app/utils/plate_normalizer.py, and shared
# by the OCR stage, cv-engine and the frontend:
#   INDIAN_PLATE_RE — full Indian civilian layout SS DD L{1,3} N{3,4}
#                     (e.g. GJ01AB1234, GJ1AB1234)
#   LOOSE_PLATE_RE  — Bharat-series / older layouts still worth accepting as
#                     plausible (confidence discount tier only)

PLATE_STATUS_HIGH = "HIGH"
PLATE_STATUS_LOW = "LOW_CONFIDENCE"
PLATE_STATUS_UNKNOWN = "UNKNOWN"

@dataclass
class PlateRead:
    """One plate reading for one vehicle in one frame."""

    raw: str                  # exactly what OCR returned
    normalized: str           # uppercase, alphanumeric only
    confidence: float         # 0.0 - 1.0, after format discounting
    ocr_confidence: float     # 0.0 - 1.0, the engine's own score
    indian_format: bool
    plate_box: Optional[PlateBox] = None
    requires_review: bool = False  # broad fallback region is not precise localization

    @property
    def status(self) -> str:
        low = float(getattr(settings, "OCR_LOW_CONFIDENCE_MARK", 0.80))
        return PLATE_STATUS_HIGH if self.confidence >= low and not self.requires_review else PLATE_STATUS_LOW

def format_score(normalized: str) -> float:
    """1.0 = canonical Indian plate, 0.7 = plausible, 0.45 = generic alnum."""
    if not normalized:
        return 0.0
    if INDIAN_PLATE_RE.match(normalized):
        return 1.0
    if LOOSE_PLATE_RE.match(normalized):
        return 0.7
    return 0.45

def plate_text_candidates(lines: Sequence[tuple], *, join_lines: bool = False) -> List[tuple]:
    """Preserve individual OCR strings; also read two-/three-line bike plates.

    Joining is allowed only INSIDE a localized plate region, never across a
    whole vehicle/scene. Use the weakest line's score; concatenation cannot
    manufacture confidence. The normal format/rejection gate still applies.
    """
    candidates = list(lines)
    if join_lines:
        for count in (2, 3):
            for start in range(len(lines) - count + 1):
                group = lines[start:start + count]
                text = "\n".join(str(line[0]) for line in group)
                normalized = candidate_from_text(text)
                if normalized and (INDIAN_PLATE_RE.match(normalized) or LOOSE_PLATE_RE.match(normalized)):
                    candidates.append((text, min(float(line[1]) for line in group)))
    return candidates


@dataclass
class PlateAttempt:
    """Small per-read diagnostic; no raw unconfirmed plate text is published."""
    state: str = "NO_REGION"
    region: Optional[PlateBox] = None
    ocr_calls: int = 0
    fallback_used: bool = False


def _padded_region(region: PlateBox, frame, vehicle_bbox) -> PlateBox:
    if region.source == "heuristic":
        return region
    h, w = frame.shape[:2]
    vx1, vy1, vx2, vy2 = map(float, vehicle_bbox)
    vw, vh = vx2-vx1, vy2-vy1
    px, py = max(2, round(region.width*.05)), max(2, round(region.height*.12))
    return PlateBox(
        max(0, int(vx1-.03*vw), region.x1-px), max(0, int(vy1-.03*vh), region.y1-py),
        min(w, int(vx2+.03*vw), region.x2+px), min(h, int(vy2+.03*vh), region.y2+py),
        region.confidence, region.source,
    )


def read_plate_for_vehicle(
    frame: np.ndarray,
    vehicle_bbox: Sequence[float],
    vehicle_class: str = "car",
    max_regions: int = 2,
    *,
    diagnostics: Optional[PlateAttempt] = None,
) -> Optional[PlateRead]:
    """Read bounded localized regions, then one conservative rescue region.

    A model proposal can be a lamp/logo, or crop the edge of a glyph. Modest
    padding preserves edges. If localized OCR fails, try the lower vehicle
    ONCE (raw + contrast variants), rather than letting a bad proposal suppress
    the visible plate forever. Rescue reads require canonical format, remain
    Verify reads and still need independent-frame agreement in the live worker.
    """
    attempt = diagnostics if diagnostics is not None else PlateAttempt()
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    if not ocr_service.available:
        attempt.state = "UNAVAILABLE"
        return None
    reject = float(getattr(settings, "OCR_MIN_CONFIDENCE", .60))
    regions = plate_detector_service.detect(frame, vehicle_bbox, vehicle_class,
                                            max_candidates=max(1, min(max_regions, 2)))
    best: Optional[PlateRead] = None
    saw_text = saw_small = rejected = False

    def scan(region, *, rescue=False):
        nonlocal best, saw_text, saw_small, rejected
        attempt.region = region
        if region.width < 24 or region.height < 8:
            saw_small = True
            return
        original_height = region.height
        region = _padded_region(region, frame, vehicle_bbox)
        crop = frame[region.y1:region.y2, region.x1:region.x2]
        if crop.size == 0 or region.width < 24 or region.height < 8:
            saw_small = True
            return
        attempt.region = region
        # Padding must not shrink the actual letters below the old 128px
        # plate target; preserve the scale of the unpadded plate region.
        target_height = min(256, round(128 * region.height / max(1, original_height)))
        variants = preprocess_variants(crop, target_height=target_height)
        if rescue and len(variants) >= 3:
            variants = [variants[-1], variants[0]]  # raw colour, then contrast; max 2 extra calls
        for variant in variants[:2 if rescue else 3]:
            attempt.ocr_calls += 1
            lines = ocr_service.read_lines(variant)
            if ocr_service.last_read_error:
                attempt.state = "ERROR"
                return
            saw_text = saw_text or bool(lines)
            for text, ocr_conf in plate_text_candidates(lines, join_lines=region.source != "heuristic"):
                try:
                    score = float(ocr_conf)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(score) or not 0 <= score <= 1:
                    continue
                norm = candidate_from_text(text)
                if norm is None:
                    continue
                canonical = bool(INDIAN_PLATE_RE.match(norm))
                if region.source == "heuristic" and not canonical:
                    continue  # never join/guess loose text across a whole vehicle
                fscore = format_score(norm)
                confidence = score * fscore
                if confidence < reject:
                    rejected = rejected or canonical or bool(LOOSE_PLATE_RE.match(norm))
                    continue
                read = PlateRead(text, norm, round(confidence, 4), round(score, 4), canonical,
                                 region, requires_review=region.source == "heuristic")
                if best is None or read.confidence > best.confidence:
                    best = read
            if best is not None and best.indian_format and best.confidence >= .92:
                return

    for region in regions[:2]:
        scan(region)
        if attempt.state == "ERROR":
            break
        if best and best.indian_format and best.confidence >= .92:
            break
    if best is None and attempt.state != "ERROR" and not any(r.source == "heuristic" for r in regions):
        fallback = plate_detector_service.fallback_region(frame, vehicle_bbox, vehicle_class)
        if fallback:
            attempt.fallback_used = True
            scan(fallback, rescue=True)
    if best:
        attempt.state, attempt.region = "READ", best.plate_box
    elif attempt.state != "ERROR":
        attempt.state = ("LOW_CONFIDENCE" if rejected else "NO_PLATE_TEXT" if saw_text else
                         "TOO_SMALL" if saw_small and attempt.ocr_calls == 0 else
                         "NO_TEXT" if attempt.ocr_calls else "NO_REGION")
    return best

# ---------------------------------------------------------------------------
# Per-track aggregation
# ---------------------------------------------------------------------------

@dataclass
class TrackPlateVote:
    normalized: str
    best_raw: str
    best_confidence: float
    best_ocr_confidence: float
    reads: int
    confidence_sum: float
    indian_format: bool
    requires_review: bool = False

class TrackPlateAccumulator:
    """
    Collects every plate read for one tracked vehicle and produces a single
    stable identity for it.

    Multi-frame agreement is what makes an offline read trustworthy: a plate
    seen the same way in three frames beats a single lucky 0.95 read. The
    aggregate confidence blends the best read with the cluster mean, exactly
    like the cv-engine's ``aggregate_readings`` (so both engines agree).
    """

    def __init__(self) -> None:
        self._votes: dict[str, TrackPlateVote] = {}
        self.total_reads = 0

    def add(self, read: PlateRead) -> None:
        self.total_reads += 1
        v = self._votes.get(read.normalized)
        if v is None:
            self._votes[read.normalized] = TrackPlateVote(
                normalized=read.normalized,
                best_raw=read.raw,
                best_confidence=read.confidence,
                best_ocr_confidence=read.ocr_confidence,
                reads=1,
                confidence_sum=read.confidence,
                indian_format=read.indian_format,
                requires_review=read.requires_review,
            )
            return
        v.reads += 1
        v.requires_review = v.requires_review or read.requires_review
        v.confidence_sum += read.confidence
        if read.confidence > v.best_confidence:
            v.best_confidence = read.confidence
            v.best_raw = read.raw
            v.best_ocr_confidence = read.ocr_confidence
            v.indian_format = read.indian_format

    def best(self) -> Optional[TrackPlateVote]:
        if not self._votes:
            return None
        # (agreeing reads, mean confidence) — a consistent cluster always wins.
        return max(
            self._votes.values(),
            key=lambda v: (v.reads, v.confidence_sum / max(v.reads, 1)),
        )

    def aggregate_confidence(self) -> float:
        v = self.best()
        if v is None:
            return 0.0
        mean = v.confidence_sum / max(v.reads, 1)
        return round(min(1.0, 0.5 * v.best_confidence + 0.5 * mean), 4)

    def status(self) -> str:
        v = self.best()
        if v is None:
            return PLATE_STATUS_UNKNOWN
        low = float(getattr(settings, "OCR_LOW_CONFIDENCE_MARK", 0.80))
        min_agree = int(getattr(settings, "ANPR_MIN_AGREE_READS", 2))
        conf = self.aggregate_confidence()
        if conf >= low and v.reads >= min_agree and v.indian_format and not v.requires_review:
            return PLATE_STATUS_HIGH
        return PLATE_STATUS_LOW

    def candidates(self) -> List[TrackPlateVote]:
        return sorted(self._votes.values(), key=lambda v: -v.confidence_sum)
