"""Confidence grading and multi-frame combination.

Confidence is never a binary. It is carried through the whole pipeline, graded
for display/alerting, and combined across frames so that a vehicle seen over
many frames is not judged by its worst single read.
"""

from __future__ import annotations

from typing import Iterable

GRADE_HIGH = "high"
GRADE_MEDIUM = "medium"
GRADE_LOW = "low"


def grade_confidence(confidence: float, high: float = 0.75, low: float = 0.55) -> str:
    """Three-band grade used to mark events (see the brief's low-confidence rule)."""
    if confidence >= high:
        return GRADE_HIGH
    if confidence >= low:
        return GRADE_MEDIUM
    return GRADE_LOW


def is_low_confidence(confidence: float, threshold: float = 0.55) -> bool:
    return confidence < threshold


def combine_confidences(values: Iterable[float]) -> float:
    """Combine repeated per-frame confidences for one agreed plate string.

    ``max`` would overstate certainty; a plain mean would let one bad frame drag
    a solid track down. The mean of the top half strikes the balance used in the
    brief's worked example (0.81/0.91/0.95 -> ~0.93, reported ~0.92).
    """
    vals = sorted((float(v) for v in values), reverse=True)
    if not vals:
        return 0.0
    top = vals[: max(1, len(vals) // 2 + (1 if len(vals) % 2 else 0))]
    return round(sum(top) / len(top), 4)


def confidence_weighted_agreement(votes: dict[str, float], total: float) -> float:
    """Fraction of accumulated confidence held by the winning plate string."""
    if total <= 0:
        return 0.0
    return round(max(votes.values(), default=0.0) / total, 4)
