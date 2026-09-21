"""
Manually-uploaded CCTV video pipeline (demo/test only — never live cameras).

Flow per uploaded video:
  upload file -> register as CAM<ID> (stream_type='file') -> background job:
  decode frames -> YOLO vehicle detection -> IoU tracking -> ANPR/OCR per
  track -> normalize plate -> one VehicleEvent per track (camera id +
  video timestamp + vehicle id + plate) -> watchlist match + alert.

Cross-camera paths (CAM1 -> CAM2 -> CAM4) then fall out of the existing
plate-based vehicle endpoints: the same normalized plate seen by several
uploaded cameras is one vehicle with one chronological history.
"""
from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Resolved through app/core/vision so the API also boots on hosts without the
# CV extras (serverless/API-only mode) — see that module for the contract.
from ..core.vision import cv2

from ..core.config import settings
from ..core.logging_config import logger
from ..core.paths import BACKEND_ROOT, evidence_root, upload_root
from ..database.database import SessionLocal
from ..database.models import Camera, VehicleEvent
from ..services.simple_tracker import SimpleTracker
from ..utils.timestamps import iso_utc

ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
UPLOADED_ZONE = "Uploaded"

# Job states
IDLE = "IDLE"
QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
DONE = "DONE"
FAILED = "FAILED"

_jobs_lock = threading.Lock()
_jobs: Dict[str, dict] = {}

# Path resolution is centralized in app.core.paths so the API read side and
# this write side can never disagree (relative EVIDENCE_ROOT used to resolve
# against the process CWD in one place and the backend root in another).
def _backend_root() -> Path:
    return BACKEND_ROOT

def upload_dir() -> Path:
    return upload_root()

def _evidence_root() -> Path:
    return evidence_root()

def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "upload.mp4")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload.mp4"
    return base[:120]

def normalise_camera_id(camera_id: str) -> str:
    cam = re.sub(r"[^A-Za-z0-9_-]", "", (camera_id or "").strip()).upper()
    if not cam:
        raise ValueError("Camera ID is required (e.g. CAM1).")
    return cam

def next_camera_id(db) -> str:
    """First free CAM<n> id (CAM1, CAM2, ...). Sample metadata only."""
    existing = {str(r[0]).upper() for r in db.query(Camera.camera_id).all()}
    n = 1
    while f"CAM{n}" in existing:
        n += 1
    return f"CAM{n}"

def is_uploaded_camera(cam: Camera) -> bool:
    try:
        return (
            (cam.stream_type or "").lower() == "file"
            and bool(cam.stream_url)
            and str(Path(cam.stream_url).resolve()).startswith(str(upload_dir().resolve()))
        )
    except Exception:
        return False

UPLOAD_CHUNK_BYTES = 1024 * 1024

def _validate_upload_suffix(filename: str) -> str:
    """Return the sanitized filename, rejecting unsupported container types."""
    safe = _safe_filename(filename)
    suffix = Path(safe).suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise ValueError(
            f"Unsupported video type '{suffix or '?'}'. "
            f"Use one of: {', '.join(sorted(ALLOWED_VIDEO_SUFFIXES))}."
        )
    return safe

def _max_upload_bytes() -> int:
    return int(settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024

def _unique_target(safe: str) -> Path:
    target = upload_dir() / safe
    if target.exists():
        stem, ext = target.stem, target.suffix
        i = 2
        while (upload_dir() / f"{stem}_{i}{ext}").exists():
            i += 1
        target = upload_dir() / f"{stem}_{i}{ext}"
    return target

class UploadWriter:
    """Memory-safe writer for one uploaded video.

    The endpoint used to do ``await file.read()`` — the whole upload in RAM —
    and only *then* checked ``MAX_UPLOAD_SIZE_MB``, so a multi-GB submission was
    fully buffered before it could be rejected. Chunks are now written straight
    to a temporary file and the limit is enforced while streaming: the request
    is abandoned as soon as the cap is crossed, with no partial file left behind.
    """

    def __init__(self, filename: str):
        self.safe_name = _validate_upload_suffix(filename)
        self._max_bytes = _max_upload_bytes()
        self._written = 0
        self._tmp = upload_dir() / f".{self.safe_name}.part"
        self._fh = None
        self._closed = False

    def __enter__(self) -> "UploadWriter":
        self._fh = self._tmp.open("wb")
        return self

    def write(self, chunk: bytes) -> int:
        if self._fh is None:
            raise ValueError("Upload writer is not open.")
        if not chunk:
            return 0
        self._written += len(chunk)
        if self._written > self._max_bytes:
            self._discard()
            raise ValueError(
                f"Video exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit."
            )
        self._fh.write(chunk)
        return len(chunk)

    @property
    def bytes_written(self) -> int:
        return self._written

    def finish(self) -> Path:
        """Close the temp file and move it to its final, de-duplicated name."""
        if self._closed:
            raise ValueError("Upload writer already finished.")
        if self._fh is not None:
            self._fh.flush()
            os.fsync(self._fh.fileno())
            self._fh.close()
            self._fh = None
        self._closed = True
        if self._written == 0:
            self._discard()
            raise ValueError("Empty file uploaded.")
        target = _unique_target(self.safe_name)
        os.replace(self._tmp, target)
        return target

    def _discard(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
        self._closed = True
        try:
            self._tmp.unlink(missing_ok=True)
        except OSError:
            pass

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None or not self._closed:
            self._discard()

def open_upload_writer(filename: str) -> UploadWriter:
    """Context manager that streams one upload to disk (see ``UploadWriter``)."""
    return UploadWriter(filename)

def save_upload(filename: str, data: bytes) -> Path:
    """Persist an in-memory upload; returns its absolute path.

    Kept for callers/scripts that already hold the bytes — it goes through the
    same streaming writer, so the size limit is enforced identically.
    """
    with open_upload_writer(filename) as writer:
        writer.write(data)
        return writer.finish()

def get_job(camera_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(camera_id.upper())
        if job is None:
            return {
                "job_status": IDLE,
                "progress_pct": 0.0,
                "frames_total": 0,
                "frames_processed": 0,
                "vehicles_seen": 0,
                "plates_read": 0,
                "job_error": None,
                "note": None,
                "last_processed_at": None,
            }
        return dict(job)

def _set_job(camera_id: str, **fields) -> None:
    with _jobs_lock:
        job = _jobs.setdefault(camera_id.upper(), {"job_status": IDLE})
        job.update(fields)

def summaries(db) -> List[dict]:
    """Uploaded cameras + their job state, newest first."""
    cams = db.query(Camera).order_by(Camera.id.desc()).all()
    out = []
    for cam in cams:
        if not is_uploaded_camera(cam):
            continue
        job = get_job(cam.camera_id)
        out.append(
            {
                "camera_id": cam.camera_id,
                "name": cam.name,
                "location": cam.location,
                "video_file": os.path.basename(cam.stream_url or ""),
                "status": cam.status or "OFFLINE",
                **job,
            }
        )
    return out

def format_video_offset(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--:--"
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

def start_processing(camera_id: str) -> dict:
    """Queue (or re-queue) a background detection job for an uploaded video."""
    cam_id = normalise_camera_id(camera_id)
    with _jobs_lock:
        current = (_jobs.get(cam_id) or {}).get("job_status")
        if current in (QUEUED, PROCESSING):
            return get_job(cam_id)
    _set_job(
        cam_id,
        job_status=QUEUED,
        progress_pct=0.0,
        frames_total=0,
        frames_processed=0,
        vehicles_seen=0,
        plates_read=0,
        job_error=None,
        note=None,
        last_processed_at=None,
    )
    thread = threading.Thread(target=_process_video, args=(cam_id,), daemon=True, name=f"UploadProc-{cam_id}")
    thread.start()
    return get_job(cam_id)

def _broadcast(payload: dict, kind: str) -> None:
    """Best-effort realtime notification from a worker thread.

    The fan-out is scheduled onto the application's running event loop (see
    ``ws_manager.broadcast_threadsafe``) instead of ``asyncio.run()``: a worker
    thread has no loop of its own, and a fresh loop can never reach the SSE
    queues / WebSocket transports that live on the app loop.
    """
    try:
        from .ws_manager import ws_manager

        ws_manager.broadcast_threadsafe(kind, payload)
    except Exception as exc:
        logger.warning(f"[UPLOAD:{payload.get('camera_id', '?')}] realtime broadcast failed: {exc}")

def _process_video(camera_id: str) -> None:
    db = SessionLocal()
    cap = None
    try:
        from sqlalchemy import func

        from .event_service import create_watchlist_alert, match_watchlist
        from .ocr_service import ocr_service
        from .vehicle_detection_service import vehicle_detection_service

        cam = (
            db.query(Camera)
            .filter(func.upper(Camera.camera_id) == camera_id.upper())
            .first()
        )
        if not cam or not is_uploaded_camera(cam):
            _set_job(camera_id, job_status=FAILED, job_error=f"Uploaded video for '{camera_id}' not found.")
            return
        if not cam.stream_url or not os.path.isfile(cam.stream_url):
            _set_job(camera_id, job_status=FAILED, job_error="Uploaded video file is missing from disk.")
            return

        _set_job(camera_id, job_status=PROCESSING)
        started_at = datetime.now(timezone.utc)
        logger.info(f"[UPLOAD:{camera_id}] Processing {cam.stream_url}")

        # Detection availability is checked up front so the job can say so.
        detector_ok = vehicle_detection_service.enabled
        vehicle_detection_service._ensure_model()
        detector_ok = vehicle_detection_service._model is not None
        ocr_ok = ocr_service.available
        notes = []
        if not detector_ok:
            notes.append("Vehicle detection model unavailable — install ultralytics + torch (CPU).")
        if not ocr_ok:
            notes.append("No OCR engine installed — plates will be Unknown. Install rapidocr-onnxruntime.")
        if notes:
            _set_job(camera_id, note=" ".join(notes))

        cap = cv2.VideoCapture(cam.stream_url)
        if not cap.isOpened():
            _set_job(camera_id, job_status=FAILED, job_error="Could not decode this video file.")
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if fps <= 0:
            fps = 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        _set_job(camera_id, frames_total=total)

        every_n = max(1, int(getattr(settings, "PROCESS_EVERY_N_FRAMES", 3)))
        tracker = SimpleTracker(iou_threshold=0.25, max_misses=8)
        # track_id -> {normalized: [conf_sum, count, best_raw, best_conf]}
        plate_votes: Dict[int, Dict[str, list]] = {}
        # track_id -> (vehicle crop jpeg bytes, offset_sec) at the best read
        best_crops: Dict[int, tuple] = {}
        # track_id -> detection steps since last OCR attempt
        ocr_cooldown: Dict[int, int] = {}
        # track_id -> (class_name, hits)
        track_meta: Dict[int, tuple] = {}

        frame_idx = 0
        det_step = 0
        vehicles_seen = 0
        plates_read = 0
        seen_track_ids: set = set()
        video_filename = os.path.basename(cam.stream_url)

        def finalize_track(track_id: int) -> None:
            nonlocal plates_read
            meta = track_meta.pop(track_id, None)
            votes = plate_votes.pop(track_id, {})
            ocr_cooldown.pop(track_id, None)
            crop_info = best_crops.pop(track_id, None)
            if meta is None:
                return
            class_name, hits = meta
            if hits < 2:
                return  # single-frame flicker, not a real sighting
            best_norm, best_raw, best_conf, best_count = None, None, 0.0, 0
            for norm, (conf_sum, count, raw, conf) in votes.items():
                score = conf_sum + 0.05 * count
                if best_norm is None or score > (best_conf + 0.05 * best_count):
                    best_norm, best_raw, best_conf, best_count = norm, raw, conf, count
            offset = (crop_info[1] if crop_info else None)
            if offset is None:
                offset = 0.0
            event_time = started_at + timedelta(seconds=float(offset))

            evidence_ref = None
            if crop_info is not None:
                try:
                    ev_dir = _evidence_root() / "uploads" / camera_id.lower()
                    ev_dir.mkdir(parents=True, exist_ok=True)
                    plate_tag = best_norm.lower() if best_norm else "unknown"
                    fname = f"{camera_id.lower()}_{track_id}_{int(offset * 1000)}ms_{plate_tag}.jpg"
                    (ev_dir / fname).write_bytes(crop_info[0])
                    evidence_ref = f"uploads/{camera_id.lower()}/{fname}"
                except Exception as exc:
                    logger.warning(f"[UPLOAD:{camera_id}] evidence write failed: {exc}")

            event = VehicleEvent(
                camera_id=cam.camera_id,
                vehicle_track_id=track_id,
                plate_raw=best_raw,
                plate_number=best_norm,
                plate_confidence=float(best_conf) if best_norm else None,
                vehicle_class=class_name or "car",
                event_time=event_time,
                latitude=cam.latitude,
                longitude=cam.longitude,
                evidence_ref=evidence_ref,
                video_file=video_filename,
                video_offset_sec=float(offset),
                watchlist_match=False,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            alert_extra: dict = {}
            if best_norm:
                plates_read += 1
                entry = match_watchlist(db, best_norm)
                if entry:
                    event.watchlist_match = True
                    db.commit()
                    alert = create_watchlist_alert(db, event, entry)
                    kind = "ALERT_CREATED" if alert else "WATCHLIST_MATCH"
                    if alert:
                        # Same alert keys the live pipeline broadcasts: without
                        # alert_id the UI had no id to ack/resolve against.
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
            _broadcast(
                {
                    "event_id": event.id,
                    "camera_id": event.camera_id,
                    "plate": event.plate_number,
                    "plate_number": event.plate_number,
                    "vehicle_class": event.vehicle_class,
                    "confidence": event.plate_confidence,
                    "event_time": iso_utc(event.event_time) if event.event_time else None,
                    "video_file": video_filename,
                    "video_offset": format_video_offset(offset),
                    "watchlist_match": event.watchlist_match,
                    **alert_extra,
                },
                kind,
            )
            _set_job(camera_id, plates_read=plates_read)

        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            offset_sec = frame_idx / fps
            if frame_idx % every_n == 0:
                det_step += 1
                dets = (
                    vehicle_detection_service.detect(frame)
                    if detector_ok and vehicle_detection_service._model is not None
                    else []
                )
                live, retired = tracker.update(
                    [(d.x1, d.y1, d.x2, d.y2, d.class_name, d.confidence) for d in dets]
                )
                for track in retired:
                    finalize_track(track.track_id)
                for track in live:
                    if track.track_id not in seen_track_ids:
                        seen_track_ids.add(track.track_id)
                        vehicles_seen += 1
                    track_meta[track.track_id] = (track.class_name, track.hits)
                    # OCR throttling: stable tracks only, every few det steps.
                    left = ocr_cooldown.get(track.track_id, 0)
                    if left > 0:
                        ocr_cooldown[track.track_id] = left - 1
                        continue
                    if track.hits < 2:
                        continue
                    area = max(track.x2 - track.x1, 0) * max(track.y2 - track.y1, 0)
                    if area < 2500:
                        continue
                    ocr_cooldown[track.track_id] = 4
                    if not ocr_ok:
                        continue
                    reading = ocr_service.read_plate(
                        frame,
                        (track.x1, track.y1, track.x2, track.y2),
                        track.class_name,
                    )
                    if reading is None:
                        continue
                    votes = plate_votes.setdefault(track.track_id, {})
                    slot = votes.setdefault(reading.normalized, [0.0, 0, reading.raw, 0.0])
                    slot[0] += reading.confidence
                    slot[1] += 1
                    if reading.confidence > slot[3]:
                        slot[2], slot[3] = reading.raw, reading.confidence
                        # Keep the vehicle crop behind the best read as evidence.
                        try:
                            h, w = frame.shape[:2]
                            x1 = max(0, track.x1)
                            y1 = max(0, track.y1)
                            x2 = min(w, track.x2)
                            y2 = min(h, track.y2)
                            if x2 - x1 >= 16 and y2 - y1 >= 16:
                                ok_enc, buf = cv2.imencode(
                                    ".jpg", frame[y1:y2, x1:x2],
                                    [int(cv2.IMWRITE_JPEG_QUALITY), 82],
                                )
                                if ok_enc:
                                    best_crops[track.track_id] = (buf.tobytes(), offset_sec)
                        except Exception:
                            pass
                _set_job(
                    camera_id,
                    frames_processed=frame_idx + 1,
                    progress_pct=(round((frame_idx + 1) / total * 100, 1) if total else 0.0),
                    vehicles_seen=vehicles_seen,
                )
            frame_idx += 1

        for track in tracker.flush():
            finalize_track(track.track_id)

        cam.status = "ONLINE"
        cam.last_seen = datetime.now(timezone.utc)
        db.commit()
        _set_job(
            camera_id,
            job_status=DONE,
            progress_pct=100.0,
            frames_processed=frame_idx,
            vehicles_seen=vehicles_seen,
            last_processed_at=iso_utc(),
        )
        logger.info(
            f"[UPLOAD:{camera_id}] Done: {frame_idx} frames, "
            f"{vehicles_seen} vehicles, {plates_read} plates read."
        )
    except Exception as exc:
        logger.exception(f"[UPLOAD:{camera_id}] Processing failed: {exc}")
        _set_job(camera_id, job_status=FAILED, job_error=str(exc) or "Processing failed.")
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
