"""Hard scene-cut detection for looping Sentinel feeds.

Sentinel streams loop, so the same camera can jump from the end of a clip back
to its beginning. If we ignore that, the tracker keeps "confident" tracks that
now belong to a completely different moment — which produces impossible
dwell times and duplicate ANPR events.

The detector is deliberately cheap (a 160x90 grayscale mean-absolute-difference,
well under a millisecond) because it runs on every frame, and deliberately
conservative: it only fires on a *large* global change, which is what a cut is.
A truck filling the frame is not a cut; a different junction is.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_THRESHOLD = 0.45
RESIZE_TO = (160, 90)


@dataclass
class SceneCutResult:
    is_cut: bool
    score: float
    threshold: float


class SceneCutDetector:
    """Stateful difference detector. ``process`` returns one result per frame."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, min_frames_between: int = 5) -> None:
        if not 0.0 < threshold < 1.0:
            raise ValueError("threshold must be within (0, 1)")
        self.threshold = float(threshold)
        self.min_frames_between = max(int(min_frames_between), 1)
        self._previous: np.ndarray | None = None
        self._frames_since_cut = 0
        self.cuts_detected = 0
        self.last_score = 0.0

    def reset(self) -> None:
        self._previous = None
        self._frames_since_cut = 0

    def process(self, frame: np.ndarray) -> SceneCutResult:
        """Compare against the previous frame; report a cut when it is a jump."""
        self._frames_since_cut += 1
        if frame is None or getattr(frame, "size", 0) == 0:
            return SceneCutResult(False, 0.0, self.threshold)

        small = self._downscale(frame)
        score = 0.0
        is_cut = False
        if self._previous is not None:
            score = float(np.mean(np.abs(small.astype(np.int16) - self._previous.astype(np.int16)))) / 255.0
            is_cut = score >= self.threshold and self._frames_since_cut >= self.min_frames_between
        self._previous = small
        self.last_score = score
        if is_cut:
            self.cuts_detected += 1
            self._frames_since_cut = 0
        return SceneCutResult(is_cut=is_cut, score=round(score, 4), threshold=self.threshold)

    @staticmethod
    def _downscale(frame: np.ndarray) -> np.ndarray:
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        return cv2.resize(gray, RESIZE_TO, interpolation=cv2.INTER_AREA)
