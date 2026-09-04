"""Evidence writer (spec §20) — deterministic JPEG evidence for vehicle events.

Design rules:
- The writer NEVER stores frames on its own; the pipeline decides when a
  sighting is significant and calls :meth:`save_event_evidence`.
- Filenames are deterministic functions of
  (camera_id, track_id, pts_ms, plate) so replays and tests are reproducible
  and the same sighting overwrites (not duplicates) its evidence.
- Filenames are sanitized: only [A-Za-z0-9-], path traversal impossible,
  bounded length — evidence dirs are served to the frontend.
- No frame dumping: one full frame + at most one plate crop per event,
  JPEG-encoded in memory (no temp files).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("trinetra.evidence")

# Anything that is not alphanumeric becomes a single '-'; collapse repeats.
_UNSAFE = re.compile(r"[^A-Za-z0-9]+")
_MAX_LEN = 48


def sanitize(value: Optional[str]) -> str:
    """Make an arbitrary string safe for use as a filename component.

    >>> sanitize("GJ 01 AB-1234")
    'GJ-01-AB-1234'
    >>> sanitize("../../etc/passwd")
    'etc-passwd'
    >>> sanitize("")
    'unknown'
    """
    if not value:
        return "unknown"
    cleaned = _UNSAFE.sub("-", str(value)).strip("-")
    if not cleaned:
        return "unknown"
    return cleaned[:_MAX_LEN]


class EvidenceWriter:
    """Writes deterministic JPEG evidence files under ``base_dir``."""

    def __init__(self, base_dir: str = "evidence", jpeg_quality: int = 90) -> None:
        self.base_dir = base_dir
        self.jpeg_quality = int(jpeg_quality)
        self.files_written = 0

    # ------------------------------------------------------------------
    def _write_jpg(self, path: str, image: np.ndarray) -> bool:
        ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if not ok:
            logger.warning("evidence encode failed: %s", path)
            return False
        with open(path, "wb") as fh:
            fh.write(buf.tobytes())
        self.files_written += 1
        return True

    # ------------------------------------------------------------------
    def save_event_evidence(
        self,
        frame: np.ndarray,
        camera_id: str,
        track_id: Optional[int],
        pts_ms: float,
        plate: Optional[str],
        plate_crop: Optional[np.ndarray] = None,
        store_full_frame: bool = True,
        store_plate_crop: bool = True,
    ) -> Optional[str]:
        """Persist evidence for one significant sighting.

        Returns a relative reference such as
        ``cam04/cam04_17_123456ms_GJ01AB1234.jpg`` (relative to ``base_dir``),
        or ``None`` when nothing was stored.
        """
        if frame is None or not store_full_frame and (plate_crop is None or not store_plate_crop):
            return None

        cam_dir = sanitize(camera_id)
        out_dir = os.path.join(self.base_dir, cam_dir)
        os.makedirs(out_dir, exist_ok=True)

        track_part = "na" if track_id is None else str(int(track_id))
        stem = f"{sanitize(camera_id)}_{track_part}_{max(0, int(pts_ms))}ms_{sanitize(plate)}"

        wrote_any = False
        ref: Optional[str] = None

        if store_full_frame:
            full_rel = os.path.join(cam_dir, f"{stem}.jpg")
            if self._write_jpg(os.path.join(self.base_dir, full_rel), frame):
                wrote_any = True
                ref = full_rel

        if store_plate_crop and plate_crop is not None:
            crop_rel = os.path.join(cam_dir, f"{stem}_plate.jpg")
            if self._write_jpg(os.path.join(self.base_dir, crop_rel), plate_crop):
                wrote_any = True
                ref = ref or crop_rel

        if not wrote_any:
            return None
        return ref
