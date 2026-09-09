"""
Multi-video analysis service.

Accepts N videos (local uploads and/or shared Google Drive links), runs each of
them through the project's *existing* OpenCV + YOLO11 + tracker + ANPR
pipeline, and stores every sighting in the existing ``vehicle_events`` table so
all pre-existing vehicle/GIS/watchlist endpoints keep working unchanged.

Per video:
    cv2.VideoCapture  ->  frame sampling
        -> vehicle_detection_service (YOLO11, car/motorcycle/bus/truck)
        -> SimpleTracker (greedy IoU)
        -> plate_detector_service    (plate localisation)
        -> ocr_service               (super-resolved, multi-variant OCR)
        -> normalize_plate           (GJ 01 AB 1234 -> GJ01AB1234)
        -> ONE VehicleEvent per tracked vehicle  (never one per frame)

Every number in the results comes from this loop. Nothing is fabricated: a
vehicle whose plate could not be read is stored with ``plate_status=UNKNOWN``
and a NULL plate, and it simply never participates in cross-video matching.
"""
from __future__ import annotations

import asyncio
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2

from ..core.config import settings
from ..core.logging_config import logger
from ..database.database import SessionLocal
from ..database.models import Camera, VehicleEvent, VideoSource
from ..utils.plate_normalizer import normalize_plate
from .anpr_pipeline import (
    PLATE_STATUS_HIGH,
    PLATE_STATUS_LOW,
    PLATE_STATUS_UNKNOWN,
    TrackPlateAccumulator,
    read_plate_for_vehicle,
)
from .plate_detector_service import PlateBox
from .simple_tracker import SimpleTracker

# Detection/evidence working resolution for very large frames (4K+). Keeps
# memory bounded on small hosts; ANPR plate crops remain native-resolution.
ANALYSIS_WORK_MAX_EDGE = 1600

ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
ANALYSIS_ZONE = "Video Analysis"

# VideoSource.status values
PENDING = "PENDING"
DOWNLOADING = "DOWNLOADING"
READY = "READY"
QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
DONE = "DONE"
FAILED = "FAILED"

TERMINAL = {DONE, FAILED}

_worker_lock = threading.Lock()
_active_workers: Dict[str, threading.Thread] = {}
_worker_slots_sem: Optional[threading.Semaphore] = None


def _worker_slots() -> threading.Semaphore:
    """
    Bound how many videos are decoded + inferred at the same time.

    ANALYSIS_MAX_WORKERS exists because this pipeline is CPU-bound: running
    more videos in parallel than the box has cores makes every video slower
    and can starve the API thread. Extra videos simply wait in QUEUED.
    """
    global _worker_slots_sem
    with _worker_lock:
        if _worker_slots_sem is None:
            n = max(1, int(getattr(settings, "ANALYSIS_MAX_WORKERS", 2)))
            _worker_slots_sem = threading.Semaphore(n)
        return _worker_slots_sem


class AnalysisError(Exception):
    """User-facing error (message is displayed verbatim in the UI)."""


# ---------------------------------------------------------------------------
# Paths & identifiers
# ---------------------------------------------------------------------------

def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def analysis_dir() -> Path:
    d = Path(getattr(settings, "ANALYSIS_DIR", "uploads/analysis"))
    if not d.is_absolute():
        d = _backend_root() / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def _evidence_root() -> Path:
    root = Path(settings.EVIDENCE_ROOT)
    if not root.is_absolute():
        root = (_backend_root() / root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "video.mp4")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "video.mp4"
    return base[:120]


def camera_id_from_filename(filename: str) -> str:
    """
    ``CAM1.mp4`` -> ``CAM1``. The filename *is* the camera identifier, as the
    brief specifies; anything unusable falls back to ``VIDn``.
    """
    stem = Path(safe_filename(filename)).stem
    # Collapse every run of separators into a single underscore so
    # "junction 7 - east.mov" becomes JUNCTION_7_EAST, not JUNCTION_7_-_EAST.
    cid = re.sub(r"[^A-Za-z0-9]+", "_", stem).upper().strip("_")
    return cid[:40] or "VIDEO"


def unique_camera_id(db, desired: str) -> str:
    """First free camera id based on ``desired`` (CAM1, CAM1_2, CAM1_3, ...)."""
    taken = {str(r[0]).upper() for r in db.query(Camera.camera_id).all()}
    if desired.upper() not in taken:
        return desired.upper()
    i = 2
    while f"{desired.upper()}_{i}" in taken:
        i += 1
    return f"{desired.upper()}_{i}"


def _unique_path(directory: Path, file_name: str) -> Path:
    target = directory / safe_filename(file_name)
    if not target.exists():
        return target
    stem, ext = target.stem, target.suffix
    i = 2
    while (directory / f"{stem}_{i}{ext}").exists():
        i += 1
    return directory / f"{stem}_{i}{ext}"


def format_offset(seconds: Optional[float]) -> str:
    """134.2 -> '00:02:14'."""
    if seconds is None:
        return "--:--:--"
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def crop_plate_region(frame, plate_box, pad_x: float = 0.10, pad_y: float = 0.20):
    """
    The number-plate image itself: crop ``plate_box`` (the existing plate
    detector's bounding box, absolute pixels) out of the analysed frame with
    a small sensible padding so the characters are not clipped.

    Returned as JPEG bytes at native resolution (never upscaled), or None if
    the box is degenerate. Mirrors the cv-engine EvidenceWriter's
    ``{stem}_plate.jpg`` convention that the frontend already expects.
    """
    try:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = (int(v) for v in (
            plate_box.x1, plate_box.y1, plate_box.x2, plate_box.y2))
        bw, bh = x2 - x1, y2 - y1
        if bw < 8 or bh < 4:
            return None
        px = max(2, int(bw * pad_x))
        py = max(2, int(bh * pad_y))
        cx1, cy1 = max(0, x1 - px), max(0, y1 - py)
        cx2, cy2 = min(w, x2 + px), min(h, y2 + py)
        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return None
        ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return buf.tobytes() if ok else None
    except Exception:
        return None


def annotate_frame(frame, bbox, plate: str, confidence: Optional[float]):
    """
    Full video frame with the detection box and plate label drawn on it,
    returned as JPEG bytes (or None if anything goes wrong).

    This is the wide shot stored with every plate sighting so a number-plate
    search can show the whole scene — where the vehicle was in the frame and
    which box the AI read — not just a tight crop.
    """
    try:
        out = frame.copy()
        h, w = out.shape[:2]
        x1, y1, x2, y2 = (int(v) for v in bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        colour = (80, 220, 120)  # green BGR — matches the live detection overlay
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        label = f"{plate} {confidence * 100:.0f}%" if confidence is not None else plate
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = max(0.45, min(out.shape[1] / 1280.0, 0.9))
        thickness = 1 if scale < 0.6 else 2
        (tw, th), baseline = cv2.getTextSize(label, font, scale, thickness)
        ty = max(y1 - th - baseline - 4, 0)
        cv2.rectangle(out, (x1, ty), (x1 + tw + 6, ty + th + baseline + 4), colour, -1)
        cv2.putText(out, label, (x1 + 3, ty + th + 1), font, scale, (15, 15, 15), thickness, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return buf.tobytes() if ok else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

def probe_video(path: Path) -> dict:
    """
    Read real technical metadata from the file with OpenCV.
    Raises AnalysisError when the file cannot be decoded.
    """
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise AnalysisError(
                "This file could not be decoded as a video. Check that it is a "
                "valid MP4/AVI/MOV/MKV/WEBM file and not corrupted."
            )
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise AnalysisError("The video contains no readable frames.")
        if width <= 0 or height <= 0:
            height, width = frame.shape[:2]
        if fps <= 0 or fps > 240:
            fps = 25.0
        duration = (frames / fps) if frames > 0 else None
        return {
            "fps": round(fps, 3),
            "width": width,
            "height": height,
            "frames_total": frames,
            "duration_sec": round(duration, 2) if duration else None,
            "size_bytes": path.stat().st_size,
        }
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _register(
    db,
    *,
    path: Path,
    source_type: str,
    source_name: str,
    source_ref: Optional[str],
    batch_id: str,
    camera_id: Optional[str] = None,
    display_name: Optional[str] = None,
) -> VideoSource:
    """Create the VideoSource + its paired Camera registry row."""
    meta = probe_video(path)

    cam_id = unique_camera_id(db, (camera_id or camera_id_from_filename(source_name)))
    cam = Camera(
        camera_id=cam_id,
        name=display_name or cam_id,
        location=f"Video analysis — {source_name}",
        stream_url=str(path),
        stream_type="file",
        # No real-world coordinates are known for an uploaded/Drive video, and
        # inventing them would put a fake pin on the operational map.
        latitude=None,
        longitude=None,
        department="Traffic Police",
        zone=ANALYSIS_ZONE,
        codec="H264",
        width=meta["width"],
        height=meta["height"],
        fps=int(round(meta["fps"])),
        status="ONLINE",
    )
    db.add(cam)

    video = VideoSource(
        video_id=uuid.uuid4().hex[:16],
        batch_id=batch_id,
        camera_id=cam_id,
        source_type=source_type,
        source_name=source_name,
        source_ref=source_ref,
        file_path=str(path),
        status=READY,
        progress_pct=0.0,
        fps=meta["fps"],
        width=meta["width"],
        height=meta["height"],
        duration_sec=meta["duration_sec"],
        size_bytes=meta["size_bytes"],
        frames_total=meta["frames_total"],
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    logger.info(
        f"[ANALYSIS] Registered {source_type} video '{source_name}' as {cam_id} "
        f"({meta['width']}x{meta['height']} @ {meta['fps']}fps, {meta['frames_total']} frames)"
    )
    return video


def register_upload(db, filename: str, data: bytes, batch_id: str,
                    camera_id: Optional[str] = None) -> VideoSource:
    """Persist an uploaded file and register it for analysis."""
    safe = safe_filename(filename)
    suffix = Path(safe).suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise AnalysisError(
            f"'{filename}': unsupported video type '{suffix or '?'}'. "
            f"Use {', '.join(sorted(ALLOWED_VIDEO_SUFFIXES))}."
        )
    if not data:
        raise AnalysisError(f"'{filename}' is empty.")
    max_bytes = int(settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024
    if len(data) > max_bytes:
        raise AnalysisError(
            f"'{filename}' exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit."
        )
    path = _unique_path(analysis_dir(), safe)
    path.write_bytes(data)
    try:
        return _register(
            db, path=path, source_type="UPLOAD", source_name=safe,
            source_ref=None, batch_id=batch_id, camera_id=camera_id,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Chunked upload — for connections with a request-body cap in front of the
# backend (hosted previews return HTTP 413 on one big multipart). The client
# posts small parts; each part is far below any proxy limit; the server
# reassembles and registers exactly like a normal upload.
# ---------------------------------------------------------------------------

CHUNK_PART_MAX_BYTES = 16 * 1024 * 1024     # per-request cap (proxies allow far more)
CHUNK_MAX_PARTS = 2000                       # 2000 * 16 MB >> any single video


def chunks_dir(upload_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", upload_id or "").strip("._")[:64] or "upload"
    d = analysis_dir() / "_chunks" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_chunk(upload_id: str, part: int, data: bytes) -> int:
    """Persist one part; returns total bytes received so far for this id."""
    if part < 0 or part >= CHUNK_MAX_PARTS:
        raise AnalysisError("Invalid chunk index.")
    if not data:
        raise AnalysisError("Empty chunk.")
    d = chunks_dir(upload_id)
    (d / f"{part:06d}").write_bytes(data)
    total = sum(p.stat().st_size for p in d.iterdir())
    max_bytes = int(settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024
    if total > max_bytes:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
        raise AnalysisError(
            f"'{upload_id}' exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit."
        )
    return total


def assemble_chunks(
    db, upload_id: str, filename: str, batch_id: str,
    camera_id: Optional[str] = None,
) -> VideoSource:
    """Reassemble stored parts into the final video file and register it."""
    import shutil

    d = chunks_dir(upload_id)
    parts = sorted((p for p in d.iterdir() if p.is_file()), key=lambda p: p.name)
    if not parts:
        raise AnalysisError("No chunks were received for this upload id.")
    expected = list(range(len(parts)))
    if [int(p.name) for p in parts] != expected:
        shutil.rmtree(d, ignore_errors=True)
        raise AnalysisError("Chunks are missing or out of order — retry the upload.")
    target = _unique_path(analysis_dir(), filename)
    try:
        with open(target, "wb") as out:
            for p in parts:
                out.write(p.read_bytes())
        shutil.rmtree(d, ignore_errors=True)
        return _register(
            db, path=target, source_type="UPLOAD", source_name=safe_filename(filename),
            source_ref=None, batch_id=batch_id, camera_id=camera_id,
        )
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def register_gdrive(db, url: str, batch_id: str, camera_id: Optional[str] = None) -> VideoSource:
    """Validate + download a shared Drive video and register it for analysis."""
    from . import gdrive_service

    try:
        link = gdrive_service.parse_drive_url(url)
    except gdrive_service.DriveError as exc:
        raise AnalysisError(str(exc))

    try:
        path, file_name = gdrive_service.download(url, analysis_dir())
    except gdrive_service.DriveError as exc:
        raise AnalysisError(str(exc))

    try:
        return _register(
            db, path=path, source_type="GDRIVE", source_name=file_name,
            source_ref=link.normalized_url, batch_id=batch_id, camera_id=camera_id,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


def delete_video(db, video_id: str) -> None:
    video = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
    if not video:
        raise AnalysisError(f"Video '{video_id}' not found.")
    if video.status in (PROCESSING, QUEUED, DOWNLOADING):
        raise AnalysisError("This video is being processed — wait for it to finish first.")
    db.query(VehicleEvent).filter(VehicleEvent.video_id == video_id).delete(synchronize_session=False)
    cam = db.query(Camera).filter(Camera.camera_id == video.camera_id).first()
    if cam is not None and (cam.zone or "") == ANALYSIS_ZONE:
        db.delete(cam)
    if video.file_path:
        try:
            Path(video.file_path).unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(video)
    db.commit()


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def start_analysis(db, video_ids: Optional[List[str]] = None) -> List[VideoSource]:
    """
    Queue analysis for the given videos (or every non-terminal video).
    Returns the queued VideoSource rows.
    """
    q = db.query(VideoSource)
    if video_ids:
        q = q.filter(VideoSource.video_id.in_(video_ids))
    videos = q.order_by(VideoSource.id.asc()).all()
    if not videos:
        raise AnalysisError("No videos to analyse. Upload a file or add a Google Drive link first.")

    queued: List[VideoSource] = []
    for video in videos:
        if video.status in (QUEUED, PROCESSING, DOWNLOADING):
            continue
        if not video.file_path or not os.path.isfile(video.file_path):
            video.status = FAILED
            video.error = "The video file is missing from disk. Re-add it."
            continue
        video.status = QUEUED
        video.error = None
        video.progress_pct = 0.0
        video.frames_read = 0
        video.frames_analyzed = 0
        video.vehicles_detected = 0
        video.plates_read = 0
        video.unknown_plates = 0
        video.started_at = None
        video.completed_at = None
        queued.append(video)
    db.commit()

    for video in queued:
        _spawn(video.video_id)
    return queued


def _spawn(video_id: str) -> None:
    with _worker_lock:
        existing = _active_workers.get(video_id)
        if existing is not None and existing.is_alive():
            return
        thread = threading.Thread(
            target=_run_video, args=(video_id,), daemon=True, name=f"Analysis-{video_id}"
        )
        _active_workers[video_id] = thread
    thread.start()


def _broadcast(kind: str, payload: dict) -> None:
    """Best-effort realtime notification from a worker thread."""
    try:
        from .ws_manager import ws_manager

        asyncio.run(ws_manager.broadcast(kind, payload))
    except Exception as exc:
        logger.debug(f"[ANALYSIS] realtime broadcast skipped: {exc}")


def _run_video(video_id: str) -> None:
    slots = _worker_slots()
    slots.acquire()  # the video stays QUEUED until a CPU slot is free
    db = SessionLocal()
    cap = None
    try:
        from .event_service import create_watchlist_alert, match_watchlist
        from .ocr_service import ocr_service
        from .vehicle_detection_service import vehicle_detection_service

        video = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
        if video is None:
            return
        cam = db.query(Camera).filter(Camera.camera_id == video.camera_id).first()

        video.status = PROCESSING
        video.started_at = datetime.now(timezone.utc)
        db.commit()

        # Wall-clock anchor for this video: sighting times are
        # start_of_analysis + offset_in_video, so cross-video ordering is
        # deterministic and reproducible.
        anchor = video.started_at

        vehicle_detection_service._ensure_model()
        detector_ok = vehicle_detection_service._model is not None
        ocr_ok = ocr_service.available
        notes = []
        if not detector_ok:
            notes.append("Vehicle detection model unavailable — install ultralytics + torch (CPU).")
        if not ocr_ok:
            notes.append("No OCR engine installed — plates stay Unknown. Install rapidocr-onnxruntime.")
        if notes:
            video.error = " ".join(notes)
            db.commit()
        if not detector_ok:
            video.status = FAILED
            video.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        cap = cv2.VideoCapture(video.file_path)
        if not cap.isOpened():
            video.status = FAILED
            video.error = "Could not decode this video file."
            video.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        fps = float(video.fps or cap.get(cv2.CAP_PROP_FPS) or 25.0)
        if fps <= 0:
            fps = 25.0
        total = int(video.frames_total or cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        every_n = max(1, int(getattr(settings, "ANALYSIS_EVERY_N_FRAMES", 5)))
        cooldown_steps = max(1, int(getattr(settings, "ANALYSIS_OCR_COOLDOWN_STEPS", 3)))
        min_hits = max(1, int(getattr(settings, "ANALYSIS_MIN_TRACK_HITS", 2)))
        min_area = int(getattr(settings, "ANALYSIS_MIN_VEHICLE_AREA", 1200))

        tracker = SimpleTracker(iou_threshold=0.25, max_misses=8)
        accum: Dict[int, TrackPlateAccumulator] = {}
        # track_id -> dict of the best frame seen for this vehicle
        track_meta: Dict[int, dict] = {}
        cooldown: Dict[int, int] = {}
        best_crop: Dict[int, bytes] = {}
        # track_id -> JPEG bytes of the FULL annotated frame at the best plate
        # read, plus the confidence of that read (only re-encoded on a better
        # read, so memory stays bounded to one frame per tracked vehicle).
        best_frame: Dict[int, bytes] = {}
        best_frame_conf: Dict[int, float] = {}
        # track_id -> JPEG bytes of the PLATE-ONLY crop (the ANPR crop the
        # evidence panel shows), taken from the plate detector's bounding box
        # at the best read. Written as {stem}_plate.jpg, the convention the
        # frontend's EvidencePanel already resolves from evidence_ref.
        best_plate_crop: Dict[int, bytes] = {}

        counters = {"vehicles": 0, "plates": 0, "unknown": 0}
        seen_tracks: set = set()
        frame_idx = 0
        analyzed = 0
        video_filename = os.path.basename(video.file_path or "")

        def finalize(track_id: int) -> None:
            meta = track_meta.pop(track_id, None)
            acc = accum.pop(track_id, None)
            cooldown.pop(track_id, None)
            crop_bytes = best_crop.pop(track_id, None)
            frame_bytes = best_frame.pop(track_id, None)
            plate_crop_bytes = best_plate_crop.pop(track_id, None)
            best_frame_conf.pop(track_id, None)
            if meta is None or meta["hits"] < min_hits:
                return  # detector flicker, not a real vehicle sighting

            vote = acc.best() if acc else None
            if vote is not None:
                plate_norm = vote.normalized
                plate_raw = vote.best_raw
                plate_conf = acc.aggregate_confidence()
                plate_status = acc.status()
            else:
                plate_norm, plate_raw, plate_conf = None, None, None
                plate_status = PLATE_STATUS_UNKNOWN

            offset = float(meta["offset_sec"])
            evidence_ref = None
            frame_ref = None
            if crop_bytes or frame_bytes:
                try:
                    ev_dir = _evidence_root() / "analysis" / video.camera_id.lower()
                    ev_dir.mkdir(parents=True, exist_ok=True)
                    tag = (plate_norm or "unknown").lower()
                    stem = f"{video.camera_id.lower()}_{track_id}_{int(offset * 1000)}ms_{tag}"
                    if crop_bytes:
                        (ev_dir / f"{stem}.jpg").write_bytes(crop_bytes)
                        evidence_ref = f"analysis/{video.camera_id.lower()}/{stem}.jpg"
                    if frame_bytes:
                        # Wide shot with the detection box drawn on it — the
                        # image a number-plate search displays per occurrence.
                        (ev_dir / f"{stem}_frame.jpg").write_bytes(frame_bytes)
                        frame_ref = f"analysis/{video.camera_id.lower()}/{stem}_frame.jpg"
                    if plate_crop_bytes:
                        # Plate-only ANPR crop — the image the evidence panel
                        # shows next to the OCR text. Same {stem}_plate.jpg
                        # naming the cv-engine EvidenceWriter uses for live
                        # cameras, so the existing frontend URL just works.
                        (ev_dir / f"{stem}_plate.jpg").write_bytes(plate_crop_bytes)
                except Exception as exc:
                    logger.warning(f"[ANALYSIS:{video.camera_id}] evidence write failed: {exc}")

            event = VehicleEvent(
                camera_id=video.camera_id,
                vehicle_track_id=track_id,
                plate_raw=plate_raw,
                plate_number=plate_norm,
                plate_confidence=plate_conf,
                plate_status=plate_status,
                vehicle_class=meta["class_name"],
                vehicle_confidence=round(float(meta["confidence"]), 4),
                event_time=anchor + timedelta(seconds=offset),
                latitude=cam.latitude if cam else None,
                longitude=cam.longitude if cam else None,
                evidence_ref=evidence_ref,
                frame_ref=frame_ref,
                video_file=video_filename,
                video_offset_sec=offset,
                video_id=video.video_id,
                frame_number=int(meta["frame_number"]),
                watchlist_match=False,
            )
            event.bbox = meta["bbox"]
            db.add(event)
            db.commit()
            db.refresh(event)

            if plate_norm:
                counters["plates"] += 1
                entry = match_watchlist(db, plate_norm)
                if entry and plate_status == PLATE_STATUS_HIGH:
                    event.watchlist_match = True
                    db.commit()
                    alert = create_watchlist_alert(db, event, entry)
                    kind = "ALERT_CREATED" if alert else "WATCHLIST_MATCH"
                else:
                    kind = "VEHICLE_DETECTED"
            else:
                counters["unknown"] += 1
                kind = "VEHICLE_DETECTED"

            _broadcast(kind, {
                "event_id": event.id,
                "camera_id": event.camera_id,
                "video_id": video.video_id,
                "plate": event.plate_number,
                "plate_number": event.plate_number,
                "plate_status": plate_status,
                "vehicle_class": event.vehicle_class,
                "confidence": event.plate_confidence,
                "event_time": event.event_time.isoformat() if event.event_time else None,
                "video_file": video_filename,
                "video_offset": format_offset(offset),
                "watchlist_match": event.watchlist_match,
            })

        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            # Bound memory/CPU on 4K+ sources: detection, tracking and the
            # stored evidence snapshots run at a capped working resolution;
            # the ANPR plate crop itself stays NATIVE (its box is mapped
            # back below), so crop quality is unchanged.
            fh, fw = frame.shape[:2]
            scale = min(1.0, float(ANALYSIS_WORK_MAX_EDGE) / max(fh, fw))
            if scale < 1.0:
                work = cv2.resize(
                    frame, (int(fw * scale), int(fh * scale)),
                    interpolation=cv2.INTER_AREA)
            else:
                work = frame
            offset_sec = frame_idx / fps
            if frame_idx % every_n == 0:
                analyzed += 1
                detections = vehicle_detection_service.detect(work)
                live, retired = tracker.update(
                    [(d.x1, d.y1, d.x2, d.y2, d.class_name, d.confidence) for d in detections]
                )
                for track in retired:
                    finalize(track.track_id)

                for track in live:
                    if track.track_id not in seen_tracks:
                        seen_tracks.add(track.track_id)
                        counters["vehicles"] += 1
                    area = max(track.x2 - track.x1, 0) * max(track.y2 - track.y1, 0)
                    prev = track_meta.get(track.track_id)
                    # Keep the *largest* (closest / sharpest) view of the vehicle
                    # as its representative record.
                    if prev is None or area >= prev["area"]:
                        track_meta[track.track_id] = {
                            "class_name": track.class_name,
                            "confidence": track.confidence,
                            "hits": track.hits,
                            "area": area,
                            "bbox": [track.x1, track.y1, track.x2, track.y2],
                            "frame_number": frame_idx,
                            "offset_sec": offset_sec,
                        }
                    else:
                        prev["hits"] = track.hits

                    if not ocr_ok or track.hits < min_hits or area < min_area * scale * scale:
                        continue
                    left = cooldown.get(track.track_id, 0)
                    if left > 0:
                        cooldown[track.track_id] = left - 1
                        continue
                    cooldown[track.track_id] = cooldown_steps

                    read = read_plate_for_vehicle(
                        frame, (track.x1, track.y1, track.x2, track.y2), track.class_name
                    )
                    if read is None:
                        continue
                    accum.setdefault(track.track_id, TrackPlateAccumulator()).add(read)
                    # Snapshot the vehicle at the best read for evidence.
                    try:
                        crop = frame[max(0, track.y1):track.y2, max(0, track.x1):track.x2]
                        if crop.size:
                            ok_enc, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
                            if ok_enc:
                                best_crop[track.track_id] = buf.tobytes()
                    except Exception:
                        pass
                    # Also keep the FULL annotated frame from the *best* plate
                    # read for this track — this is what a plate search shows,
                    # so an officer sees the whole scene, not just the crop.
                    if float(read.confidence) >= best_frame_conf.get(track.track_id, -1.0):
                        annotated = annotate_frame(
                            work,
                            (track.x1, track.y1, track.x2, track.y2),
                            read.normalized,
                            float(read.confidence),
                        )
                        if annotated is not None:
                            best_frame[track.track_id] = annotated
                            best_frame_conf[track.track_id] = float(read.confidence)
                        # Plate-only crop from the EXISTING plate bounding box
                        # (never the vehicle box) — this is the ANPR crop,
                        # taken from the NATIVE frame for full resolution.
                        if read.plate_box is not None:
                            pb = read.plate_box
                            if scale < 1.0:
                                pb = PlateBox(
                                    int(pb.x1 / scale), int(pb.y1 / scale),
                                    int(pb.x2 / scale), int(pb.y2 / scale),
                                    pb.confidence, pb.source,
                                )
                            pcrop = crop_plate_region(frame, pb)
                            if pcrop is not None:
                                best_plate_crop[track.track_id] = pcrop

                if analyzed % 10 == 0:
                    video.frames_read = frame_idx + 1
                    video.frames_analyzed = analyzed
                    video.progress_pct = round((frame_idx + 1) / total * 100, 1) if total else 0.0
                    video.vehicles_detected = counters["vehicles"]
                    video.plates_read = counters["plates"]
                    video.unknown_plates = counters["unknown"]
                    db.commit()
            frame_idx += 1

        for track in tracker.flush():
            finalize(track.track_id)

        video.frames_read = frame_idx
        video.frames_analyzed = analyzed
        video.vehicles_detected = counters["vehicles"]
        video.plates_read = counters["plates"]
        video.unknown_plates = counters["unknown"]
        video.progress_pct = 100.0
        video.status = DONE
        video.completed_at = datetime.now(timezone.utc)
        if counters["vehicles"] == 0:
            video.error = "No vehicles were detected in this video."
        elif counters["plates"] == 0:
            video.error = ("Vehicles were detected but no number plate could be read "
                           "with sufficient confidence.")
        db.commit()
        if cam is not None:
            cam.last_seen = datetime.now(timezone.utc)
            db.commit()

        logger.info(
            f"[ANALYSIS:{video.camera_id}] Done — {frame_idx} frames read, {analyzed} analysed, "
            f"{counters['vehicles']} vehicles, {counters['plates']} plates, "
            f"{counters['unknown']} unknown."
        )
        _broadcast("ANALYSIS_VIDEO_DONE", {
            "video_id": video.video_id,
            "camera_id": video.camera_id,
            "vehicles_detected": counters["vehicles"],
            "plates_read": counters["plates"],
        })
    except Exception as exc:
        logger.exception(f"[ANALYSIS:{video_id}] failed: {exc}")
        try:
            video = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
            if video is not None:
                video.status = FAILED
                video.error = str(exc) or "Processing failed."
                video.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass
        slots.release()
        with _worker_lock:
            _active_workers.pop(video_id, None)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def video_to_dict(video: VideoSource) -> dict:
    return {
        "video_id": video.video_id,
        "batch_id": video.batch_id,
        "camera_id": video.camera_id,
        "source_type": video.source_type,
        "source_name": video.source_name,
        "source_ref": video.source_ref,
        "status": video.status,
        "error": video.error,
        "progress_pct": video.progress_pct,
        "fps": video.fps,
        "width": video.width,
        "height": video.height,
        "duration_sec": video.duration_sec,
        "duration_label": format_offset(video.duration_sec) if video.duration_sec else None,
        "size_bytes": video.size_bytes,
        "frames_total": video.frames_total,
        "frames_read": video.frames_read,
        "frames_analyzed": video.frames_analyzed,
        "vehicles_detected": video.vehicles_detected,
        "plates_read": video.plates_read,
        "unknown_plates": video.unknown_plates,
        "created_at": video.created_at,
        "started_at": video.started_at,
        "completed_at": video.completed_at,
    }


def list_videos(db, batch_id: Optional[str] = None) -> List[dict]:
    q = db.query(VideoSource)
    if batch_id:
        q = q.filter(VideoSource.batch_id == batch_id)
    return [video_to_dict(v) for v in q.order_by(VideoSource.id.asc()).all()]


def batch_status(db, batch_id: Optional[str] = None) -> dict:
    videos = list_videos(db, batch_id)
    statuses = [v["status"] for v in videos]
    if not videos:
        overall = "EMPTY"
    elif any(s in (QUEUED, PROCESSING, DOWNLOADING) for s in statuses):
        overall = "PROCESSING"
    elif all(s == DONE for s in statuses):
        overall = "DONE"
    elif all(s in TERMINAL for s in statuses):
        overall = "PARTIAL" if DONE in statuses else "FAILED"
    else:
        overall = "READY"
    done = sum(1 for s in statuses if s in TERMINAL)
    return {
        "batch_id": batch_id,
        "status": overall,
        "total_videos": len(videos),
        "completed_videos": done,
        "progress_pct": round(
            sum(v["progress_pct"] for v in videos) / len(videos), 1
        ) if videos else 0.0,
        "videos": videos,
    }
