"""Multi-frame ANPR aggregation per track.

One OCR pass per frame is noisy; a tracked vehicle is read many times. This
module accumulates the readings for a track and votes on the normalised string.
An event is only produced when the aggregate justifies it — a single weak read
is stored but not emitted as a sighting, and a vehicle is never re-emitted for
every frame it is seen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from anpr.confidence import combine_confidences
from logging_setup import log_event

log = logging.getLogger("trinetra.anpr.aggregate")


@dataclass
class PlateAggregate:
    track_id: int
    votes: dict[str, float] = field(default_factory=dict)      # normalised -> accumulated confidence
    counts: dict[str, int] = field(default_factory=dict)      # normalised -> # distinct frames
    raw_best: str = ""
    best_confidence: float = 0.0
    first_continuous_ms: float = 0.0
    last_continuous_ms: float = 0.0
    frames_read: int = 0

    @property
    def total_confidence(self) -> float:
        return sum(self.votes.values())

    @property
    def top_normalized(self) -> str:
        if not self.votes:
            return ""
        # Break ties on frame count, then on accumulated confidence.
        return max(self.votes.items(), key=lambda kv: (self.counts.get(kv[0], 0), kv[1]))[0]

    @property
    def top_count(self) -> int:
        top = self.top_normalized
        return self.counts.get(top, 0) if top else 0

    @property
    def confidence(self) -> float:
        """Confidence of the winning string across its frames."""
        top = self.top_normalized
        per_frame = getattr(self, "_frame_confs", None) or {}
        values = per_frame.get(top) or ([self.best_confidence] if self.best_confidence else [])
        return combine_confidences(values)

    def agreement(self) -> float:
        if self.total_confidence <= 0:
            return 0.0
        return round(self.votes.get(self.top_normalized, 0.0) / self.total_confidence, 4)


class TrackPlateAggregator:
    """Accumulates per-track plate readings and decides when a read is stable."""

    def __init__(self, min_votes: int = 2, single_shot_confidence: float = 0.9) -> None:
        self.min_votes = max(int(min_votes), 1)
        self.single_shot_confidence = float(single_shot_confidence)
        self._tracks: dict[int, PlateAggregate] = {}
        self._frame_confs: dict[int, dict[str, list[float]]] = {}

    def add(self, track_id: int, normalized: str, raw: str, confidence: float, continuous_ms: float) -> PlateAggregate:
        agg = self._tracks.get(track_id)
        if agg is None:
            agg = PlateAggregate(track_id=track_id)
            agg.first_continuous_ms = continuous_ms
            self._tracks[track_id] = agg
            self._frame_confs[track_id] = {}
        agg.last_continuous_ms = continuous_ms
        agg.frames_read += 1
        agg.votes[normalized] = agg.votes.get(normalized, 0.0) + confidence
        agg.counts[normalized] = agg.counts.get(normalized, 0) + 1
        self._frame_confs[track_id].setdefault(normalized, []).append(confidence)
        if confidence > agg.best_confidence:
            agg.best_confidence = confidence
            agg.raw_best = raw
        agg._frame_confs = self._frame_confs[track_id]  # type: ignore[attr-defined]
        return agg

    def should_emit(self, track_id: int) -> bool:
        """A read is stable enough to become a sighting event.

        * one very confident read is enough;
        * otherwise we want the same normalised string on >= ``min_votes``
          frames (the brief's multi-frame rule), with decent agreement.
        """
        agg = self._tracks.get(track_id)
        if agg is None or not agg.top_normalized:
            return False
        if agg.best_confidence >= self.single_shot_confidence:
            return True
        return agg.top_count >= self.min_votes and agg.agreement() >= 0.5

    def consume(self, track_id: int) -> PlateAggregate | None:
        """Return and clear the aggregate once it has been turned into an event."""
        return self._tracks.pop(track_id, None)

    def get(self, track_id: int) -> PlateAggregate | None:
        return self._tracks.get(track_id)

    def remove(self, track_id: int) -> None:
        self._tracks.pop(track_id, None)
        self._frame_confs.pop(track_id, None)

    def reset(self) -> None:
        self._tracks.clear()
        self._frame_confs.clear()

    def __len__(self) -> int:
        return len(self._tracks)
