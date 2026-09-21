"""Evidence writer (spec §20) — deterministic, safe, bounded evidence capture.

Design rules this module enforces:

1. **Never dumps frames on its own.** ``save_event_evidence`` is called by the
   pipeline only for events it decided to emit. A freshly constructed writer
   touches the filesystem zero times.
2. **Deterministic paths.** The reference is a pure function of
   ``(camera_id, track_id, pts_ms, plate)``. Re-running the same sighting
   produces the same path, so a retransmitted event overwrites instead of
   multiplying evidence files (no evidence spam, no storage leak).
3. **Path safety.** Every component goes through :func:`sanitize`, so a plate
   like ``../../etc/passwd`` can never escape ``base_dir``.
4. **Honest return value.** Returns the stored reference, or ``None`` when
   nothing was stored — so ``evidence_ref`` in the event JSON is never a lie
   pointing at a file that does not exist.

The reference is returned *relative* to ``base_dir`` so it stays portable when
the evidence directory is later mounted, synced or served under a different
root (e.g. ``/evidence/cam04/....jpg``).
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("trinetra.cv.evidence")

# Anything that is not alnum, '-' or '_' becomes a separator; runs of
# separators collapse and leading/trailing separators are stripped.
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")
_SEPARATORS = re.compile(r"-{2,}")

_MAX_NAME_LEN = 48
_NO_PLATE_TOKEN = "no-plate"


def sanitize(value: Optional[str], max_len: int = _MAX_NAME_LEN) -> str:
    """Return a filesystem-safe token for ``value``.

    >>> sanitize("GJ 01 AB-1234")
    'GJ-01-AB-1234'
    >>> sanitize("../../etc/passwd")
    'etc-passwd'
    >>> sanitize("")
    'unknown'
    """
    if not value:
        return "unknown"
    cleaned = _UNSAFE.sub("-", str(value))
    cleaned = _SEPARATORS.sub("-", cleaned).strip("-")
    if not cleaned:
        return "unknown"
    return cleaned[:max_len]


class EvidenceWriter:
    """Stores full-frame and plate-crop JPEGs for emitted sighting events."""

    def __init__(self, base_dir: str = "evidence", jpeg_quality: int = 90,
                 max_files: int = 0) -> None:
        self.base_dir = base_dir
        self.jpeg_quality = max(1, min(int(jpeg_quality), 100))
        self.max_files = max(0, int(max_files))  # 0 disables retention pruning
        self.files_written = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ API
    def save_event_evidence(
        self,
        frame: Optional[np.ndarray],
        camera_id: str,
        track_id: int,
        pts_ms: float,
        plate: Optional[str],
        plate_crop: Optional[np.ndarray] = None,
        store_full_frame: bool = True,
        store_plate_crop: bool = True,
    ) -> Optional[str]:
        """Persist evidence for one emitted sighting event.

        Returns the full-frame reference relative to ``base_dir``, or the plate
        crop reference when only the crop is enabled, or ``None`` when nothing
        was stored (nothing enabled, or no usable pixels).
        """
        if not store_full_frame and not store_plate_crop:
            return None
        if frame is None and (plate_crop is None or not store_plate_crop):
            return None

        cam = sanitize(camera_id)
        plate_token = sanitize(plate) if plate else _NO_PLATE_TOKEN
        pts_token = int(max(float(pts_ms), 0.0))
        # Same (camera, track, pts, plate) always maps to the same file.
        stem = f"{cam}_{int(track_id)}_{pts_token}ms_{plate_token}"

        full_name = f"{stem}.jpg"
        crop_name = f"{stem}_plate.jpg"
        full_ref = os.path.join(cam, full_name)
        crop_ref = os.path.join(cam, crop_name)

        wrote_any = False
        if store_full_frame and frame is not None:
            wrote_any = self._write(full_ref, frame) or wrote_any
        if store_plate_crop and plate_crop is not None:
            self._write(crop_ref, plate_crop)
            wrote_any = True

        if not wrote_any:
            return None
        if store_full_frame and frame is not None:
            return full_ref
        return crop_ref

    # -------------------------------------------------------------- helpers
    def _prune_if_needed(self) -> None:
        """Occasionally delete the oldest evidence files beyond ``max_files``.

        A long-running live demo writes thousands of crops; without a cap the
        disk eventually fills and the whole stack dies. Runs every 250 writes.
        """
        if self.max_files <= 0 or self.files_written % 250 != 0:
            return
        try:
            files = []
            for root, _dirs, names in os.walk(self.base_dir):
                for name in names:
                    if name.endswith(".jpg"):
                        p = os.path.join(root, name)
                        try:
                            files.append((os.path.getmtime(p), p))
                        except OSError:
                            pass
            excess = len(files) - self.max_files
            if excess <= 0:
                return
            files.sort()
            for _mtime, p in files[:excess]:
                try:
                    os.remove(p)
                except OSError:
                    pass
            logger.info("evidence retention: pruned %d file(s), kept %d", excess, len(files) - excess)
        except Exception as exc:  # never let housekeeping crash the pipeline
            logger.warning("evidence retention sweep failed: %s", exc)

    def _write(self, rel_ref: str, image: np.ndarray) -> bool:
        """JPEG-encode ``image`` to ``base_dir/rel_ref``. True on success."""
        if not isinstance(image, np.ndarray) or image.size == 0:
            logger.debug("skipping empty evidence image for %s", rel_ref)
            return False

        abs_path = os.path.join(self.base_dir, rel_ref)
        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            ok = cv2.imwrite(
                abs_path, image, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            )
        except OSError as exc:  # disk full / bad mount — never crash the pipeline
            logger.warning("evidence write failed for %s: %s", rel_ref, exc)
            return False

        if not ok:
            logger.warning("cv2 could not encode evidence for %s", rel_ref)
            return False

        self._prune_if_needed()

        with self._lock:
            self.files_written += 1
        return True

    # ------------------------------------------------------------- reporting
    def stats(self) -> dict:
        return {"files_written": self.files_written, "base_dir": self.base_dir}
