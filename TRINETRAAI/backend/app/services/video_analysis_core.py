"""Deterministic detection + ANPR core shared by the dashboard and the CLI.

This module is the SINGLE implementation of the per-video loop:

    decode -> vehicle detection -> IoU tracking -> plate detection -> OCR
    -> ONE representative frame per tracked vehicle -> sighting records

It contains no database access and no HTTP: the dashboard service persists the
returned sightings, and the ``process_video.py`` CLI writes them to disk. Both
callers therefore produce byte-identical semantics, which is what makes the CLI
a trustworthy baseline for the dashboard.

The hard rule implemented here (the original evidence bug):

    ONE sighting == ONE frame == ONE vehicle == ONE plate == ONE evidence set.

Every field of a :class:`Sighting` — ``frame_number``, ``video_offset_sec``,
``vehicle_bbox``, ``plate_bbox``, ``plate_text`` and both crops — is taken from
a *single* frame chosen per track:

    1. the frame of the highest-confidence plate read (preferred), else
    2. the frame with the largest (clearest) vehicle box.

Nothing is indexed by position, sampled at random, or taken from "the last
frame" of the video. There is exactly one immutable record per tracked vehicle.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .simple_tracker import SimpleTracker, TrackedBox

logger = logging.getLogger("trinetra.analysis_core")

DEFAULT_CONFIG = {
    "EVERY_N_FRAMES": 5,        # detection every Nth decoded frame
    "MIN_TRACK_HITS": 2,        # ignore single-frame flicker
    "OCR_COOLDOWN_STEPS": 3,    # detection steps between OCR attempts per track
    "MIN_VEHICLE_AREA": 1200,   # px^2; smaller boxes are not OCR-able
    "TRACK_MAX_MISSES": 8,
    "TRACK_IOU_THRESHOLD": 0.25,
}

# A PlateRead-like value: the core only reads these fields, so both the real
# ``anpr_pipeline.PlateRead`` and the test stub satisfy it.


@dataclass
class Sighting:
    """One tracked vehicle, fully described by ONE representative frame."""

    track_id: int
    vehicle_class: str
    vehicle_confidence: float
    # The single frame every other field below comes from.
    frame_number: int
    video_offset_sec: float
    vehicle_bbox: List[int]                      # [x1, y1, x2, y2] in pixels
    # Plate — either all present (a real read) or all None (unreadable).
    plate_text: Optional[str] = None             # normalized
    plate_raw: Optional[str] = None              # exactly what OCR returned
    plate_confidence: Optional[float] = None
    plate_status: str = "UNKNOWN"                # HIGH | LOW_CONFIDENCE | UNKNOWN
    plate_bbox: Optional[List[int]] = None       # [x1, y1, x2, y2] or None
    # Evidence imagery (JPEG bytes) cut from the SAME frame as the fields above.
    vehicle_crop: Optional[bytes] = None
    plate_crop: Optional[bytes] = None
    # The full annotated frame the evidence came from, for the evidence ledger.
    full_frame: Optional[bytes] = None
    hits: int = 1

    @property
    def has_plate(self) -> bool:
        return bool(self.plate_text)

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "vehicle_class": self.vehicle_class,
            "vehicle_confidence": self.vehicle_confidence,
            "frame_number": self.frame_number,
            "video_offset_sec": self.video_offset_sec,
            "vehicle_bbox": self.vehicle_bbox,
            "plate_text": self.plate_text,
            "plate_raw": self.plate_raw,
            "plate_confidence": self.plate_confidence,
            "plate_status": self.plate_status,
            "plate_bbox": self.plate_bbox,
            "hits": self.hits,
        }


@dataclass
class AnalysisStats:
    frames_read: int = 0
    frames_analyzed: int = 0
    vehicles_detected: int = 0       # unique tracks seen
    plates_read: int = 0             # tracks with a readable plate
    unknown_plates: int = 0          # tracks with no readable plate
    ocr_reads: int = 0               # total plate reads attempted successfully


@dataclass
class AnalysisReport:
    video_path: str
    fps: float
    width: int
    height: int
    frames_total: int
    sightings: List[Sighting] = field(default_factory=list)
    stats: AnalysisStats = field(default_factory=AnalysisStats)


# ---------------------------------------------------------------------------
# Frame snapshotting
# ---------------------------------------------------------------------------

def _crop_jpeg(frame: np.ndarray, box: Sequence[float], quality: int = 88) -> Optional[bytes]:
    """Cut one crop out of ``frame`` and encode it as JPEG. Never raises."""
    if frame is None or frame.size == 0:
        return None
    fh, fw = frame.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in box)
    ix1 = max(0, min(fw - 1, int(x1)))
    iy1 = max(0, min(fh - 1, int(y1)))
    ix2 = max(ix1 + 1, min(fw, int(x2)))
    iy2 = max(iy1 + 1, min(fh, int(y2)))
    crop = frame[iy1:iy2, ix1:ix2]
    if crop.size == 0:
        return None
    try:
        ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    except Exception:
        return None
    return buf.tobytes() if ok else None


def _annotate_frame(
    frame: np.ndarray,
    tracks: Sequence[TrackedBox],
    plates: Dict[int, str],
) -> np.ndarray:
    """Draw the model's own boxes (track id + class + best-known plate)."""
    out = frame
    for t in tracks:
        x1, y1, x2, y2 = int(t.x1), int(t.y1), int(t.x2), int(t.y2)
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        plate = plates.get(t.track_id)
        label = f"#{t.track_id} {t.class_name}"
        if plate:
            label += f" {plate}"
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        ty = max(th + baseline, y1 - 6)
        cv2.rectangle(out, (x1, ty - th - baseline), (x1 + tw + 4, ty + 2), (0, 0, 0), -1)
        cv2.putText(out, label, (x1 + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (0, 255, 0), 2, cv2.LINE_AA)
    return out


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def analyze_video(
    video_path: str,
    *,
    detect: Callable,
    read_plate: Callable,
    config: Optional[dict] = None,
    annotate: bool = False,
    frame_sink: Optional[Callable[[np.ndarray], None]] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    max_frames: Optional[int] = None,
) -> AnalysisReport:
    """Run detection -> tracking -> plate -> OCR over one video.

    ``detect(frame, conf, imgsz)`` returns detections with
    ``x1, y1, x2, y2, class_name, confidence`` attributes.
    ``read_plate(frame, bbox, class_name)`` returns a ``PlateRead``-like object
    (``normalized``, ``raw``, ``confidence``, ``indian_format``, ``plate_box``,
    ``status``) or ``None`` when nothing plate-shaped could be read.

    ``frame_sink`` (optional) receives every decoded frame, for the CLI's
    annotated-video writer. ``max_frames`` caps decoding for a fast sample run.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    every_n = max(1, int(cfg["EVERY_N_FRAMES"]))
    min_hits = max(1, int(cfg["MIN_TRACK_HITS"]))
    cooldown_steps = max(1, int(cfg["OCR_COOLDOWN_STEPS"]))
    min_area = int(cfg["MIN_VEHICLE_AREA"])

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 0:
        fps = 25.0
    frames_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    tracker = SimpleTracker(
        iou_threshold=float(cfg["TRACK_IOU_THRESHOLD"]),
        max_misses=int(cfg["TRACK_MAX_MISSES"]),
    )

    # Per-track representative state. ``best_plate`` holds the best single read
    # seen for the track together with EVERYTHING captured from that same frame;
    # ``best_vehicle`` holds the clearest (largest) frame, used only when no
    # plate was ever read.
    best_plate: Dict[int, Tuple[float, Sighting]] = {}
    best_vehicle: Dict[int, Tuple[float, Sighting]] = {}
    plates_by_track: Dict[int, str] = {}          # for annotation only
    cooldown: Dict[int, int] = {}
    seen_tracks: set = set()

    stats = AnalysisStats()
    sightings: List[Sighting] = []

    def _snapshot(track: TrackedBox, frame: np.ndarray, frame_idx: int,
                  offset_sec: float, tracks: Sequence[TrackedBox]) -> Sighting:
        annotated = _annotate_frame(frame, tracks, plates_by_track)
        try:
            ok, full_buf = cv2.imencode(".jpg", annotated,
                                        [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            full_frame = full_buf.tobytes() if ok else None
        except Exception:
            full_frame = None
        return Sighting(
            track_id=track.track_id,
            vehicle_class=track.class_name,
            vehicle_confidence=round(float(track.confidence), 4),
            frame_number=frame_idx,
            video_offset_sec=round(offset_sec, 4),
            vehicle_bbox=[int(track.x1), int(track.y1), int(track.x2), int(track.y2)],
            hits=track.hits,
            vehicle_crop=_crop_jpeg(
                frame, (track.x1, track.y1, track.x2, track.y2)),
            full_frame=full_frame,
        )

    def _finalize(track: TrackedBox) -> None:
        """Close one track into a single immutable sighting record."""
        plate_entry = best_plate.pop(track.track_id, None)
        vehicle_entry = best_vehicle.pop(track.track_id, None)
        plates_by_track.pop(track.track_id, None)
        cooldown.pop(track.track_id, None)

        if plate_entry is not None:
            _conf, sight = plate_entry
            sight.hits = track.hits
            sightings.append(sight)
            return
        if vehicle_entry is not None:
            _area, sight = vehicle_entry
            sight.hits = track.hits
            sightings.append(sight)

    frame_idx = 0
    analyzed = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if max_frames is not None and frame_idx >= max_frames:
                break
            stats.frames_read += 1
            offset_sec = frame_idx / fps

            live: List[TrackedBox] = []
            if frame_idx % every_n == 0:
                analyzed += 1
                stats.frames_analyzed += 1
                try:
                    dets = detect(frame)
                except Exception as exc:  # a bad frame must not kill the run
                    logger.warning(f"[ANALYSIS] detect failed on frame {frame_idx}: {exc}")
                    dets = []
                live, retired = tracker.update(
                    [(d.x1, d.y1, d.x2, d.y2, d.class_name, d.confidence) for d in dets]
                )
                for t in retired:
                    _finalize(t)

                for t in live:
                    if t.track_id not in seen_tracks:
                        seen_tracks.add(t.track_id)
                        stats.vehicles_detected += 1
                    area = max(t.x2 - t.x1, 0) * max(t.y2 - t.y1, 0)
                    # Keep the clearest view as the no-plate fallback frame.
                    prev_area = best_vehicle.get(t.track_id, (-1.0, None))[0]
                    if area >= prev_area:
                        best_vehicle[t.track_id] = (float(area), _snapshot(t, frame, frame_idx, offset_sec, live))

                    if t.hits < min_hits or area < min_area:
                        continue
                    left = cooldown.get(t.track_id, 0)
                    if left > 0:
                        cooldown[t.track_id] = left - 1
                        continue
                    cooldown[t.track_id] = cooldown_steps

                    try:
                        read = read_plate(
                            frame, (t.x1, t.y1, t.x2, t.y2), t.class_name)
                    except Exception as exc:
                        logger.warning(f"[ANALYSIS] plate read failed on frame {frame_idx}: {exc}")
                        read = None
                    if read is None:
                        continue
                    stats.ocr_reads += 1
                    # This read becomes the representative frame iff it is the
                    # strongest single read so far — and then EVERYTHING (box,
                    # frame number, crops) is re-captured from THIS frame.
                    conf = float(getattr(read, "confidence", 0.0) or 0.0)
                    prev_conf = best_plate.get(t.track_id, (-1.0, None))[0]
                    if conf > prev_conf:
                        # Annotate the representative frame with the plate that
                        # is being stored, so the drawn label, the plate crop
                        # and the recorded plate_text always agree.
                        normalized = getattr(read, "normalized", None)
                        plates_by_track[t.track_id] = normalized
                        sight = _snapshot(t, frame, frame_idx, offset_sec, live)
                        sight.plate_text = normalized
                        sight.plate_raw = getattr(read, "raw", None)
                        sight.plate_confidence = round(conf, 4)
                        indian = bool(getattr(read, "indian_format", False))
                        sight.plate_status = "HIGH" if (indian and conf >= 0.80) else "LOW_CONFIDENCE"
                        pbox = getattr(read, "plate_box", None)
                        if pbox is not None:
                            sight.plate_bbox = [int(pbox.x1), int(pbox.y1), int(pbox.x2), int(pbox.y2)]
                            sight.plate_crop = _crop_jpeg(
                                frame, (pbox.x1, pbox.y1, pbox.x2, pbox.y2))
                        best_plate[t.track_id] = (conf, sight)

            if frame_sink is not None:
                out = frame
                if annotate:
                    out = _annotate_frame(frame, live, plates_by_track)
                frame_sink(out)
            if progress_cb is not None and analyzed and analyzed % 5 == 0:
                progress_cb(frame_idx + 1, frames_total)

            frame_idx += 1
    finally:
        cap.release()

    for t in tracker.flush():
        _finalize(t)

    # Deterministic output order: track creation order, not the order tracks
    # happened to be retired (which varies with interleaving and would make the
    # CSV/JSON/detection-id ordering unstable across identical runs).
    sightings.sort(key=lambda s: (s.track_id, s.frame_number))

    # Final pass: count readable vs unknown plates from the stored sightings.
    stats.plates_read = sum(1 for s in sightings if s.has_plate)
    stats.unknown_plates = sum(1 for s in sightings if not s.has_plate)

    return AnalysisReport(
        video_path=str(video_path),
        fps=fps,
        width=width,
        height=height,
        frames_total=frames_total,
        sightings=sightings,
        stats=stats,
    )
