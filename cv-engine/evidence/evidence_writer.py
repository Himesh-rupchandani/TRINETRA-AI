"""Deterministic evidence writer (spec §20).

Design rules:

* The writer NEVER dumps frames on its own — the pipeline decides when an
  event is worth persisting. This keeps disk usage bounded on ~50 cameras.
* Filenames are deterministic: the same (camera, track, pts, plate) always
  resolves to the same path, so re-processing a stream cannot duplicate
  evidence and ``evidence_ref`` stays a stable reference for the backend.
* Paths are sanitised — a plate string coming out of OCR is untrusted input
  and must never be able to traverse the filesystem.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^A-Za-z0-9]+")
MAX_NAME_LEN = 48


def sanitize(value: Optional[str]) -> str:
    """Reduce untrusted text to a filesystem-safe token.

    Runs of unsafe characters collapse to a single dash, so
    ``"GJ 01 AB-1234"`` -> ``"GJ-01-AB-1234"`` and ``"../../etc/passwd"`` ->
    ``"etc-passwd"`` (no traversal possible). Empty input -> ``"unknown"``.
    """
    if not value:
        return "unknown"
    cleaned = _UNSAFE.sub("-", value).strip("-")
    if not cleaned:
        return "unknown"
    return cleaned[:MAX_NAME_LEN]


class EvidenceWriter:
    """Writes the full CCTV frame and the plate crop for a vehicle event."""

    def __init__(self, base_dir: str = "evidence", jpeg_quality: int = 90) -> None:
        self.base_dir = base_dir
        self.jpeg_quality = int(jpeg_quality)
        self.files_written = 0
        os.makedirs(self.base_dir, exist_ok=True)

    # ------------------------------------------------------------------
    def event_ref(
        self,
        camera_id: str,
        track_id: int,
        pts_ms: float,
        plate: Optional[str],
    ) -> str:
        """Deterministic, backend-facing relative reference for an event."""
        name = "{cam}_{track}_{pts}ms_{plate}.jpg".format(
            cam=sanitize(camera_id),
            track=int(track_id),
            pts=int(pts_ms),
            plate=sanitize(plate),
        )
        return os.path.join(sanitize(camera_id), name)

    # ------------------------------------------------------------------
    def save_event_evidence(
        self,
        frame: Optional[np.ndarray],
        camera_id: str,
        track_id: int,
        pts_ms: float,
        plate: Optional[str] = None,
        plate_crop: Optional[np.ndarray] = None,
        store_full_frame: bool = True,
        store_plate_crop: bool = True,
    ) -> Optional[str]:
        """Persist evidence for one sighting.

        Returns the relative ``evidence_ref`` (full-frame path) or ``None``
        when nothing was stored, so the event carries no dangling reference.
        """
        ref = self.event_ref(camera_id, track_id, pts_ms, plate)
        full_path = os.path.join(self.base_dir, ref)
        stored_frame = False

        if store_full_frame and frame is not None:
            stored_frame = self._write(full_path, frame)

        if store_plate_crop and plate_crop is not None:
            crop_path = full_path[: -len(".jpg")] + "_plate.jpg"
            self._write(crop_path, plate_crop)

        return ref if stored_frame else None

    # ------------------------------------------------------------------
    def _write(self, path: str, image: np.ndarray) -> bool:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            ok = cv2.imwrite(
                path, image, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            )
            if ok:
                self.files_written += 1
            else:
                logger.warning("evidence write failed (encoder): %s", path)
            return bool(ok)
        except Exception as exc:  # never let evidence I/O kill the pipeline
            logger.warning("evidence write failed: %s (%s)", path, exc)
            return False
