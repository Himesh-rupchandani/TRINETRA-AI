"""
Plate confidence handling (spec §17, §30).

Principles:
- Confidence is ALWAYS preserved and propagated.
- Below the reject threshold the reading is dropped (it never becomes an
  invented plate), but the *vehicle sighting* can still produce an event.
- Between reject and the low-confidence mark the event is kept and flagged
  low_confidence=True — never silently upgraded.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class ConfidenceTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REJECT = "reject"


@dataclass
class PlateReading:
    """One OCR reading of a plate region in one frame."""

    plate_raw: str
    plate_normalized: str
    confidence: float
    pts_ms: Optional[float] = None


def classify_confidence(
    confidence: float,
    reject_threshold: float = 0.60,
    low_mark: float = 0.80,
) -> ConfidenceTier:
    """
    Boundaries:
      conf >= low_mark          -> HIGH (trustworthy)
      reject <= conf < low_mark -> MEDIUM/LOW band kept & flagged
      conf < reject_threshold   -> REJECT (no plate attached to event)
    """
    if confidence >= low_mark:
        return ConfidenceTier.HIGH
    if confidence >= reject_threshold:
        # Between reject and low mark: keep, but flag as low confidence.
        mid = (reject_threshold + low_mark) / 2.0
        return ConfidenceTier.MEDIUM if confidence >= mid else ConfidenceTier.LOW
    return ConfidenceTier.REJECT


def is_usable(tier: ConfidenceTier) -> bool:
    return tier != ConfidenceTier.REJECT


def aggregate_readings(readings: List[PlateReading]) -> Optional[Tuple[str, float, str]]:
    """
    Multi-frame aggregation (spec §18).

    Groups readings by normalized plate, picks the cluster with the highest
    (count, mean confidence) and returns (plate_normalized, aggregate_conf,
    plate_raw_of_best).

    Aggregate confidence blends the best reading with the cluster mean:
        agg = 0.5 * max_conf + 0.5 * mean_conf
    e.g. [0.81, 0.91, 0.95] -> max 0.95, mean 0.89 -> 0.92 (spec example).
    Conflicting singletons cannot beat a consistent cluster.
    Returns None when there are no readings.
    """
    if not readings:
        return None

    clusters = {}
    for r in readings:
        if not r.plate_normalized:
            continue
        clusters.setdefault(r.plate_normalized, []).append(r)
    if not clusters:
        return None

    def score(item):
        _, rs = item
        confs = [r.confidence for r in rs]
        return (len(rs), sum(confs) / len(confs))

    plate, rs = max(clusters.items(), key=score)
    confs = [r.confidence for r in rs]
    agg_conf = 0.5 * max(confs) + 0.5 * (sum(confs) / len(confs))
    best = max(rs, key=lambda r: r.confidence)
    return plate, round(min(agg_conf, 1.0), 4), best.plate_raw
