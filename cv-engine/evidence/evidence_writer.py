"""Evidence frames: full frame + plate crop, deterministic and safe.

Only *significant* events get evidence written — the pipeline never stores every
frame. Filenames are deterministic (camera/plate/track/PTS) and sanitised, so a
hostile or broken plate string cannot escape the evidence directory.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import cv2
import numpy as np

from config.settings import Settings
from logging_setup import log_event

log = logging.getLogger("trinetra.evidence")

_SAFE = re.compile(r"[^A-Za-z0-9_]+")


def _sanitize(value: str, fallback: str = "x") -> str:
    cleaned = _SAFE.sub("_", value or "").strip("_")
    return (cleaned or fallback)[:32]


class EvidenceWriter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = Path(settings.evidence_dir)
        self.written = 0
        self.skipped = 0

    def enabled(self, plate_confidence: float) -> bool:
        return self.settings.evidence_keep_frames and plate_confidence >= self.settings.evidence_min_confidence

    def write(
        self,
        frame: np.ndarray,
        crop: np.ndarray | None,
        camera_id: str,
        track_id: int | None,
        plate: str,
        continuous_ms: float,
    ) -> str | None:
        """Write frame + crop. Returns the evidence ref, or None on failure."""
        if frame is None or frame.size == 0:
            self.skipped += 1
            return None
        try:
            camera_dir = self.root / _sanitize(camera_id, "cam")
            camera_dir.mkdir(parents=True, exist_ok=True)
            stem = f"{_sanitize(plate, 'unplated')}_{track_id if track_id is not None else 0}_{int(continuous_ms)}"
            frame_ref = f"{_sanitize(camera_id, 'cam')}/{stem}.jpg"
            self._imwrite(camera_dir / f"{stem}.jpg", frame)
            if crop is not None and crop.size:
                self._imwrite(camera_dir / f"{stem}_plate.jpg", crop)
            self.written += 1
            log_event(
                log,
                "evidence_written",
                level=logging.DEBUG,
                ref=frame_ref,
                camera=camera_id,
                track_id=track_id,
            )
            return frame_ref
        except Exception as exc:  # noqa: BLE001 - evidence must never kill the loop
            self.skipped += 1
            log_event(
                log,
                "evidence_write_failed",
                level=logging.WARNING,
                camera=camera_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None

    def _imwrite(self, path: Path, image: np.ndarray) -> None:
        quality = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.settings.evidence_jpeg_quality)]
        if not cv2.imwrite(str(path), image, quality):
            raise IOError(f"cv2.imwrite failed for {path}")
