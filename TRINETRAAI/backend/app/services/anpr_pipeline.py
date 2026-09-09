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

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..core.config import settings
from ..utils.plate_normalizer import normalize_plate
from .ocr_service import candidate_from_text, ocr_service, preprocess_variants
from .plate_detector_service import PlateBox, plate_detector_service

# Full Indian civilian layout: SS DD LL(L) NNNN  (e.g. GJ01AB1234, GJ1AB1234)
INDIAN_PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$")
# Bharat-series / older layouts still worth accepting as plausible.
LOOSE_PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{4,8}$")

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

    @property
    def status(self) -> str:
        low = float(getattr(settings, "OCR_LOW_CONFIDENCE_MARK", 0.80))
        return PLATE_STATUS_HIGH if self.confidence >= low else PLATE_STATUS_LOW


def format_score(normalized: str) -> float:
    """1.0 = canonical Indian plate, 0.7 = plausible, 0.45 = generic alnum."""
    if not normalized:
        return 0.0
    if INDIAN_PLATE_RE.match(normalized):
        return 1.0
    if LOOSE_PLATE_RE.match(normalized):
        return 0.7
    return 0.45

# Confusable-glyph repair, applied per character class (letters stay letters,
# digit runs become digits): O/Q->0, I->1, Z->2, S->5, G->6, B->8, T->7 and the
# inverse. This is what turns "GJO3P"+"C3535" into GJ03PC3535.
_DIGIT_CONF = str.maketrans({"O": "0", "Q": "0", "I": "1", "Z": "2", "S": "5", "G": "6", "B": "8", "T": "7"})
_LETTER_CONF = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "6": "G", "2": "Z", "7": "T"})
_STRUCTURE_RE = re.compile(r"^([A-Z]{2})([A-Z0-9]{1,2})([A-Z]{0,3})([A-Z0-9]{3,4})$")


def canonical_variants(norm: str) -> List[Tuple[str, bool]]:
    """((canonical, repaired)) variants of one normalised candidate.

    First entry is the text as-is; the optional second repairs confusable
    glyphs per structure (SS DD LL NNNN) when the layout matches.
    """
    variants = [(norm, False)]
    m = _STRUCTURE_RE.match(norm)
    if m:
        ss, dd, ll, nn = m.groups()
        fixed = (
            ss.translate(_LETTER_CONF)
            + dd.translate(_DIGIT_CONF)
            + ll.translate(_LETTER_CONF)
            + nn.translate(_DIGIT_CONF)
        )
        if fixed != norm:
            variants.append((fixed, True))
    return variants


def read_plate_for_vehicle(
    frame: np.ndarray,
    vehicle_bbox: Sequence[float],
    vehicle_class: str = "car",
    max_regions: int = 2,
) -> Optional[PlateRead]:
    """
    Run the complete plate stage for one vehicle box.

    Returns the best :class:`PlateRead`, or ``None`` when nothing plate-shaped
    could be read (caller stores the sighting as ``UNKNOWN``).
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    if not ocr_service.available:
        return None

    reject = float(getattr(settings, "OCR_MIN_CONFIDENCE", 0.60))
    regions = plate_detector_service.detect(frame, vehicle_bbox, vehicle_class,
                                            max_candidates=max_regions)
    # When the learned plate model sees no plate-shaped region here, OCR can
    # only burn CPU producing garbage — skip it (classical/heuristic
    # proposals keep a chance because they are not confidence-calibrated).
    if regions and regions[0].source == "model":
        best_region_conf = max(r.confidence for r in regions)
        min_region = float(getattr(settings, "PLATE_CONF_THRESHOLD", 0.25))
        if best_region_conf < max(0.30, min_region + 0.05):
            return None
    best: Optional[PlateRead] = None
    for region in regions:
        crop = frame[region.y1:region.y2, region.x1:region.x2]
        if crop is None or crop.size == 0:
            continue
        if crop.shape[1] < 24 or crop.shape[0] < 8:
            continue
        for variant in preprocess_variants(crop):
            lines = list(ocr_service.read_lines(variant))
            for text, ocr_conf in lines:
                norm = candidate_from_text(text)
                if norm is None:
                    continue
                for canon, repaired in canonical_variants(norm):
                    fscore = format_score(canon)
                    if fscore <= 0.0:
                        continue
                    conf = float(ocr_conf) * fscore * (0.95 if repaired else 1.0)
                    if conf < reject:
                        continue
                    read = PlateRead(
                        raw=text,
                        normalized=canon,
                        confidence=round(min(conf, 1.0), 4),
                        ocr_confidence=round(float(ocr_conf), 4),
                        indian_format=bool(INDIAN_PLATE_RE.match(canon)),
                        plate_box=region,
                    )
                    if best is None or read.confidence > best.confidence:
                        best = read
            # Two-line plates (Indian commercial: "GJ 03 P" / "C 3535"): OCR
            # reads each row (or row piece — "C3535" often splits into "35"
            # + "35") as fragments that alone are never a valid plate. Merge
            # ordered pairs and the full concatenation, then score.
            raw_frags = [(t, float(c)) for t, c in lines if t and t.strip()]
            if len(raw_frags) >= 2:
                texts = [t for t, _ in raw_frags]
                confs = [c for _, c in raw_frags]
                combos = {texts[i] + texts[j]
                          for i in range(len(texts))
                          for j in range(len(texts)) if i != j}
                combos.add("".join(texts))
                for combo in combos:
                    merged = candidate_from_text(combo)
                    if merged is None:
                        continue
                    used = [c for t, c in raw_frags if combo.find(t) != -1]
                    base = min(used) if used else min(confs)
                    for canon, repaired in canonical_variants(merged):
                        fscore = format_score(canon)
                        if fscore <= 0.0:
                            continue
                        conf = base * fscore * (0.9 if repaired else 1.0)
                        if conf < reject:
                            continue
                        read = PlateRead(
                            raw=" ".join(texts),
                            normalized=canon,
                            confidence=round(min(conf, 1.0), 4),
                            ocr_confidence=round(base, 4),
                            indian_format=bool(INDIAN_PLATE_RE.match(canon)),
                            plate_box=region,
                        )
                        if best is None or read.confidence > best.confidence:
                            best = read
            # A confident canonical plate is good enough — stop burning CPU.
            if best is not None and best.indian_format and best.confidence >= 0.92:
                return best
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
            )
            return
        v.reads += 1
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
        if conf >= low and v.reads >= min_agree and v.indian_format:
            return PLATE_STATUS_HIGH
        return PLATE_STATUS_LOW

    def candidates(self) -> List[TrackPlateVote]:
        return sorted(self._votes.values(), key=lambda v: -v.confidence_sum)
