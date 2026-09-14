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

import os
import re
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import cv2

from ..core.config import settings
from ..core.logging_config import logger
from ..core.paths import BACKEND_ROOT, analysis_root, evidence_root
from ..database.database import SessionLocal
from ..database.models import Camera, VehicleEvent, VideoSource
from ..utils.timestamps import iso_utc
from .anpr_pipeline import (
    PLATE_STATUS_HIGH,
    read_plate_for_vehicle,
)

# Containers this feature is known to handle. Kept for the user-facing message
# only — it is NOT a gate. Real CCTV/DVR exports arrive as .3gp, .ts, .wmv,
# .dav or a raw .264/.h264 stream, and every one of those decodes fine because
# OpenCV/ffmpeg sniff the *content*, not the filename. Gating on the extension
# is what used to silently drop four of five uploaded clips.
ALLOWED_VIDEO_SUFFIXES = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v",
    ".3gp", ".3g2", ".asf", ".wmv", ".flv", ".f4v",
    ".ts", ".m2ts", ".mts", ".mpg", ".mpeg", ".mpe", ".mpv", ".vob",
    ".ogv", ".rm", ".rmvb", ".mxf", ".dav",
    ".h264", ".h265", ".hevc", ".264", ".265", ".avc",
}
# Files that are definitely not a video. Rejected on the extension alone so the
# operator gets "unsupported video type" instead of waiting for a decode of a
# PDF. Anything not listed here is *probed* — the decoder decides, not us.
NOT_VIDEO_SUFFIXES = {
    ".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".json", ".xml", ".html", ".htm", ".rtf", ".srt", ".ass", ".vtt",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg", ".ico",
    ".mp3", ".wav", ".aac", ".flac", ".m4a",
    ".zip", ".rar", ".7z", ".gz", ".tar", ".iso",
    ".py", ".js", ".sh", ".bat", ".exe", ".dll", ".so", ".bin", ".db",
}
# NOTE: .ts is deliberately NOT blacklisted — MPEG-TS is a common CCTV/DVR
# container. A TypeScript file of the same name simply fails the decode probe
# below and is rejected with the reason, which is the honest answer either way.
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

# Path resolution is centralized in app.core.paths so the API read side and
# this write side can never disagree (see the note in uploaded_video_service).
def _backend_root() -> Path:
    return BACKEND_ROOT


def analysis_dir() -> Path:
    return analysis_root()


def _evidence_root() -> Path:
    return evidence_root()


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


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

def _cv2_opens(path: Path) -> bool:
    """Can OpenCV actually pull a first frame out of this file?"""
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return False
        ok, frame = cap.read()
        return bool(ok) and frame is not None
    except Exception:
        return False
    finally:
        cap.release()


def _ffmpeg_exe() -> Optional[str]:
    """Bundled ffmpeg binary (imageio-ffmpeg, already a project dependency)."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # not installed, or the binary cannot be fetched
        logger.warning(f"[ANALYSIS] ffmpeg unavailable — cannot convert videos: {exc}")
        return None


def _convert_to_mp4(path: Path) -> Optional[Path]:
    """
    Re-encode a clip OpenCV could not read into plain H.264 MP4, which both
    OpenCV and every browser can read.

    This is the difference between "4 of your 5 clips were dropped" and "all 5
    analysed": DVR exports (.dav, .wmv/VC-1, odd profiles) are perfectly good
    video that the OpenCV build in a given environment sometimes cannot decode.
    Audio is dropped — the analysis only ever looks at frames.
    Returns None when the conversion is not possible.
    """
    exe = _ffmpeg_exe()
    if not exe:
        return None
    dest = _unique_path(path.parent, f"{path.stem}_converted.mp4")
    cmd = [
        exe, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(path),
        "-map", "0:v:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        str(dest),
    ]
    logger.info(f"[ANALYSIS] Converting {path.name} -> {dest.name} with ffmpeg")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=int(getattr(settings, "ANALYSIS_CONVERT_TIMEOUT_SEC", 1800)),
        )
    except Exception as exc:
        logger.warning(f"[ANALYSIS] ffmpeg conversion of {path.name} failed: {exc}")
        dest.unlink(missing_ok=True)
        return None
    if proc.returncode != 0 or not dest.is_file() or not _cv2_opens(dest):
        logger.warning(
            f"[ANALYSIS] ffmpeg could not convert {path.name}: "
            f"{(proc.stderr or '').strip()[:300]}"
        )
        dest.unlink(missing_ok=True)
        return None
    return dest


def ensure_decodable(path: Path, display_name: str) -> Path:
    """
    Return a path OpenCV can decode, converting the file when it cannot.

    The extension is never the reason a video is refused: the decoder is the
    only authority. A file that neither OpenCV nor ffmpeg can read is rejected
    with the reason, so nothing is ever silently dropped from a batch.
    """
    if _cv2_opens(path):
        return path
    converted = _convert_to_mp4(path)
    if converted is None:
        raise AnalysisError(
            f"'{display_name}': this file could not be decoded as a video. "
            f"Re-export it as MP4 (H.264) and add it again."
            + ("" if _ffmpeg_exe() else
               " (No ffmpeg converter is available on this server — "
               "pip install imageio-ffmpeg.)")
        )
    logger.info(f"[ANALYSIS] '{display_name}' converted to {converted.name} for analysis")
    path.unlink(missing_ok=True)  # the converted copy replaces the original
    return converted


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
    """
    Persist an uploaded file and register it for analysis.

    Any container the decoder can actually read is accepted (.mp4, .avi, .mov,
    .mkv, .webm and the DVR/phone formats .3gp, .ts, .wmv, .dav, .264, ...);
    a clip OpenCV cannot decode is converted with ffmpeg first, so a batch of
    five clips stays a batch of five instead of "only the MP4 got through".
    """
    safe = safe_filename(filename)
    suffix = Path(safe).suffix.lower()
    if suffix in NOT_VIDEO_SUFFIXES:
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
        path = ensure_decodable(path, filename)
        return _register(
            db, path=path, source_type="UPLOAD", source_name=safe,
            source_ref=None, batch_id=batch_id, camera_id=camera_id,
        )
    except Exception:
        path.unlink(missing_ok=True)
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
        path = ensure_decodable(path, file_name)
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
    """Best-effort realtime notification from a worker thread.

    Scheduled onto the application's running event loop rather than a throwaway
    ``asyncio.run()`` loop, which could never reach the SSE/WebSocket clients.
    """
    try:
        from .ws_manager import ws_manager

        ws_manager.broadcast_threadsafe(kind, payload)
    except Exception as exc:
        logger.warning(f"[ANALYSIS] realtime broadcast failed: {exc}")


def _run_video(video_id: str) -> None:
    slots = _worker_slots()
    slots.acquire()  # the video stays QUEUED until a CPU slot is free
    db = SessionLocal()
    cap = None
    try:
        from .event_service import create_watchlist_alert, match_watchlist
        from .ocr_service import ocr_service
        from .vehicle_detection_service import vehicle_detection_service
        from .video_analysis_core import analyze_video

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

        if not video.file_path or not os.path.isfile(video.file_path):
            video.status = FAILED
            video.error = "The video file is missing from disk. Re-add it."
            video.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        fps = float(video.fps or 0.0) or 25.0
        total = int(video.frames_total or 0)
        video_filename = os.path.basename(video.file_path or "")

        def _detect(frame):
            return vehicle_detection_service.detect(
                frame,
                conf=float(getattr(settings, "ANALYSIS_CONFIDENCE_THRESHOLD", 0.35)),
                imgsz=int(getattr(settings, "ANALYSIS_DETECTION_IMGSZ", 960)),
            )

        def _on_progress(current_frame: int, total_frames: int) -> None:
            video.frames_read = current_frame
            video.progress_pct = (
                round(current_frame / total_frames * 100, 1) if total_frames else 0.0
            )
            try:
                db.commit()
            except Exception:
                pass

        # Idempotent (re)runs: a re-analysis replaces this video's previous
        # sightings instead of appending a second copy of each track. The model
        # and file have already been confirmed above, so nothing is cleared on a
        # run that fails before it can produce new results.
        db.query(VehicleEvent).filter(
            VehicleEvent.video_id == video_id
        ).delete(synchronize_session=False)
        db.commit()

        report = analyze_video(
            video.file_path,
            detect=_detect,
            read_plate=read_plate_for_vehicle,
            config={
                "EVERY_N_FRAMES": int(getattr(settings, "ANALYSIS_EVERY_N_FRAMES", 5)),
                "MIN_TRACK_HITS": int(getattr(settings, "ANALYSIS_MIN_TRACK_HITS", 2)),
                "OCR_COOLDOWN_STEPS": int(getattr(settings, "ANALYSIS_OCR_COOLDOWN_STEPS", 3)),
                "MIN_VEHICLE_AREA": int(getattr(settings, "ANALYSIS_MIN_VEHICLE_AREA", 1200)),
            },
            progress_cb=_on_progress,
        )

        for sight in report.sightings:
            offset = float(sight.video_offset_sec)
            tag = (sight.plate_text or "unknown").lower()
            cam_lower = video.camera_id.lower()

            evidence_ref = None
            if sight.vehicle_crop:
                try:
                    ev_dir = evidence_root() / "analysis" / cam_lower
                    ev_dir.mkdir(parents=True, exist_ok=True)
                    fname = f"{cam_lower}_{sight.track_id}_{int(offset * 1000)}ms_{tag}.jpg"
                    (ev_dir / fname).write_bytes(sight.vehicle_crop)
                    evidence_ref = f"analysis/{cam_lower}/{fname}"
                except Exception as exc:
                    logger.warning(f"[ANALYSIS:{video.camera_id}] evidence write failed: {exc}")

            plate_evidence_ref = None
            if sight.plate_crop:
                try:
                    ev_dir = evidence_root() / "analysis" / cam_lower
                    ev_dir.mkdir(parents=True, exist_ok=True)
                    pfname = f"{cam_lower}_{sight.track_id}_{int(offset * 1000)}ms_{tag}_plate.jpg"
                    (ev_dir / pfname).write_bytes(sight.plate_crop)
                    plate_evidence_ref = f"analysis/{cam_lower}/{pfname}"
                except Exception as exc:
                    logger.warning(f"[ANALYSIS:{video.camera_id}] plate crop write failed: {exc}")

            event = VehicleEvent(
                camera_id=video.camera_id,
                vehicle_track_id=sight.track_id,
                plate_raw=sight.plate_raw,
                plate_number=sight.plate_text,
                plate_confidence=sight.plate_confidence,
                plate_status=sight.plate_status,
                vehicle_class=sight.vehicle_class,
                vehicle_confidence=sight.vehicle_confidence,
                event_time=anchor + timedelta(seconds=offset),
                latitude=cam.latitude if cam else None,
                longitude=cam.longitude if cam else None,
                evidence_ref=evidence_ref,
                plate_evidence_ref=plate_evidence_ref,
                video_file=video_filename,
                video_offset_sec=offset,
                video_id=video.video_id,
                frame_number=sight.frame_number,
                watchlist_match=False,
            )
            event.bbox = sight.vehicle_bbox
            db.add(event)
            db.commit()
            db.refresh(event)

            alert_extra: dict = {}
            if sight.plate_text:
                entry = match_watchlist(db, sight.plate_text)
                if entry and sight.plate_status == PLATE_STATUS_HIGH:
                    event.watchlist_match = True
                    db.commit()
                    alert = create_watchlist_alert(db, event, entry)
                    kind = "ALERT_CREATED" if alert else "WATCHLIST_MATCH"
                    if alert:
                        alert_extra = {
                            "alert_id": alert.id,
                            "alert_ref": f"AL-{alert.id}",
                            "id": alert.id,
                            "alert_type": alert.alert_type,
                            "severity": alert.severity,
                            "message": alert.message,
                            "status": alert.status,
                            "timestamp": iso_utc(alert.timestamp) if alert.timestamp else None,
                        }
                else:
                    kind = "VEHICLE_DETECTED"
            else:
                kind = "VEHICLE_DETECTED"

            _broadcast(kind, {
                "event_id": event.id,
                "camera_id": event.camera_id,
                "video_id": video.video_id,
                "plate": event.plate_number,
                "plate_number": event.plate_number,
                "plate_status": event.plate_status,
                "vehicle_class": event.vehicle_class,
                "confidence": event.plate_confidence,
                "event_time": iso_utc(event.event_time) if event.event_time else None,
                "video_file": video_filename,
                "video_offset": format_offset(offset),
                "watchlist_match": event.watchlist_match,
                **alert_extra,
            })

        video.frames_read = report.stats.frames_read
        video.frames_analyzed = report.stats.frames_analyzed
        video.vehicles_detected = report.stats.vehicles_detected
        video.plates_read = report.stats.plates_read
        video.unknown_plates = report.stats.unknown_plates
        video.progress_pct = 100.0
        video.status = DONE
        video.completed_at = datetime.now(timezone.utc)
        if report.stats.vehicles_detected == 0:
            video.error = "No vehicles were detected in this video."
        elif report.stats.plates_read == 0:
            video.error = ("Vehicles were detected but no number plate could be read "
                           "with sufficient confidence.")
        else:
            video.error = None
        db.commit()
        if cam is not None:
            cam.last_seen = datetime.now(timezone.utc)
            db.commit()

        logger.info(
            f"[ANALYSIS:{video.camera_id}] Done — {report.stats.frames_read} frames read, "
            f"{report.stats.frames_analyzed} analysed, {report.stats.vehicles_detected} vehicles, "
            f"{report.stats.plates_read} plates, {report.stats.unknown_plates} unknown."
        )
        _broadcast("ANALYSIS_VIDEO_DONE", {
            "video_id": video.video_id,
            "camera_id": video.camera_id,
            "vehicles_detected": report.stats.vehicles_detected,
            "plates_read": report.stats.plates_read,
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
