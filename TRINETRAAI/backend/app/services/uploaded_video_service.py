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

import asyncio
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import cv2

from ..core.config import settings
from ..core.logging_config import logger
from ..database.database import SessionLocal
from ..database.models import Camera, VehicleEvent
from ..services.simple_tracker import SimpleTracker, TrackedBox
from ..utils.plate_normalizer import normalize_plate

ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
UPLOADED_ZONE = "Uploaded"

# Annotated-video overlay palette (BGR) — mirrors trinetra_detection/core/visualizer.py
COLOR_VEHICLE = (0, 220, 50)      # bright lime green
COLOR_PLATE = (0, 215, 255)       # gold / vibrant yellow
COLOR_BANNER_BG = (25, 25, 25)    # dark charcoal
COLOR_BANNER_TEXT = (255, 255, 255)

# Job states
IDLE = "IDLE"
QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
DONE = "DONE"
FAILED = "FAILED"

_jobs_lock = threading.Lock()
_jobs: Dict[str, dict] = {}


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def upload_dir() -> Path:
    d = Path(settings.UPLOAD_DIR)
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


def annotated_dir() -> Path:
    """Where OpenCV-annotated output videos live (one per uploaded camera)."""
    d = _backend_root() / "outputs" / "annotated_videos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def annotated_path(camera_id: str) -> Path:
    return annotated_dir() / f"{camera_id.upper()}.mp4"


def has_annotated(camera_id: str) -> bool:
    try:
        return annotated_path(camera_id).is_file() and annotated_path(camera_id).stat().st_size > 0
    except Exception:
        return False


def delete_annotated(camera_id: str) -> None:
    try:
        annotated_path(camera_id).unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# OpenCV overlay drawing (annotated output video)
# ---------------------------------------------------------------------------

def _draw_label(frame, text: str, x: int, y: int, color) -> None:
    """Filled label chip anchored so its bottom sits at y (drawn above boxes)."""
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
    y_top = max(0, y - th - baseline - 6)
    cv2.rectangle(frame, (x, y_top), (min(frame.shape[1] - 1, x + tw + 8), y_top + th + baseline + 6), color, -1)
    cv2.putText(frame, text, (x + 4, y_top + th + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (10, 10, 10), 1, cv2.LINE_AA)


def draw_overlay(frame, tracks: List[TrackedBox], plate_labels: Dict[int, str], header: str):
    """Draw vehicle boxes, plate reads and the status banner onto frame (in place)."""
    h, w = frame.shape[:2]
    for t in tracks:
        x1, y1 = max(0, int(t.x1)), max(0, int(t.y1))
        x2, y2 = min(w - 1, int(t.x2)), min(h - 1, int(t.y2))
        if x2 - x1 < 4 or y2 - y1 < 4:
            continue
        cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_VEHICLE, 2)
        _draw_label(frame, f"{t.class_name} {t.confidence:.2f}", x1, y1, COLOR_VEHICLE)
        plate = plate_labels.get(t.track_id)
        if plate:
            # Gold plate chip under the vehicle box (above it when clipped).
            (tw, th), baseline = cv2.getTextSize(plate, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
            y_top = y2 + 4
            if y_top + th + baseline + 6 > h:
                y_top = max(0, y1 - th - baseline - 6)
            cv2.rectangle(frame, (x1, y_top), (min(w - 1, x1 + tw + 10), y_top + th + baseline + 6), COLOR_PLATE, -1)
            cv2.putText(frame, plate, (x1 + 5, y_top + th + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (10, 10, 10), 1, cv2.LINE_AA)
    cv2.rectangle(frame, (0, 0), (w, 34), COLOR_BANNER_BG, -1)
    cv2.putText(frame, header, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.58, COLOR_BANNER_TEXT, 1, cv2.LINE_AA)


def _open_writer(path: Path, width: int, height: int, fps: float):
    """VideoWriter preferring a browser-playable H.264 ('avc1'), then mp4v."""
    for fourcc in ("avc1", "mp4v"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), fps, (width, height))
        if writer.isOpened():
            return writer, fourcc
        writer.release()
    return None, None


def _find_ffmpeg() -> Optional[str]:
    """ffmpeg binary: system PATH first, then the one bundled with imageio-ffmpeg."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # optional dependency — ships a static ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _reencode_h264(path: Path) -> bool:
    """Re-encode to H.264 yuv420p with ffmpeg when available (browser playback)."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return False
    tmp = path.with_suffix(".h264.mp4")
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(path),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)],
            timeout=600, check=False,
        )
        if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 0:
            tmp.replace(path)
            return True
    except Exception as exc:
        logger.debug(f"[UPLOAD] ffmpeg re-encode failed: {exc}")
    finally:
        tmp.unlink(missing_ok=True)
    return False


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


def save_upload(filename: str, data: bytes) -> Path:
    """Persist an uploaded video file; returns its absolute path."""
    safe = _safe_filename(filename)
    suffix = Path(safe).suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise ValueError(
            f"Unsupported video type '{suffix or '?'}'. "
            f"Use one of: {', '.join(sorted(ALLOWED_VIDEO_SUFFIXES))}."
        )
    max_bytes = int(settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024
    if len(data) > max_bytes:
        raise ValueError(f"Video exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit.")
    target = upload_dir() / safe
    if target.exists():
        stem, ext = target.stem, target.suffix
        i = 2
        while (upload_dir() / f"{stem}_{i}{ext}").exists():
            i += 1
        target = upload_dir() / f"{stem}_{i}{ext}"
    target.write_bytes(data)
    return target


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
                "annotated_available": has_annotated(cam.camera_id),
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
    try:
        from .ws_manager import ws_manager

        asyncio.run(ws_manager.broadcast(kind, payload))
    except Exception as exc:  # realtime is best-effort from worker threads
        logger.debug(f"[UPLOAD] realtime broadcast skipped: {exc}")


def _process_video(camera_id: str) -> None:
    db = SessionLocal()
    cap = None
    writer = None
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

        # ---- OpenCV annotated output video --------------------------------
        out_path = annotated_path(camera_id)
        delete_annotated(camera_id)
        writer = None
        encoder_used = None
        frame_size = (
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        if frame_size[0] > 0 and frame_size[1] > 0:
            writer, encoder_used = _open_writer(out_path, frame_size[0], frame_size[1], fps)
            if writer is None:
                logger.warning(f"[UPLOAD:{camera_id}] Could not open VideoWriter — no annotated video.")
        header_cam = cam.camera_id


        every_n = max(1, int(getattr(settings, "PROCESS_EVERY_N_FRAMES", 3)))
        # Adaptive sweep rate: ~UPLOAD_TARGET_DETECT_FPS det steps per second
        # of video (fps/6), clamped so short clips still track reliably and
        # long clips never sweep more than every 2nd frame.
        target_fps = int(getattr(settings, "UPLOAD_TARGET_DETECT_FPS", 6) or 6)
        every_n = min(6, max(2, round(fps / target_fps)))
        infer_imgsz = int(getattr(settings, "UPLOAD_DETECTION_IMGSZ", 448) or 448)
        infer_conf = float(getattr(settings, "UPLOAD_DETECTION_CONF", 0.40))

        # Annotated output is capped at UPLOAD_ANNOTATED_MAX_WIDTH to keep the
        # per-frame encode cheap on 1080p/4K uploads; box coords are scaled.
        max_w = int(getattr(settings, "UPLOAD_ANNOTATED_MAX_WIDTH", 1280) or 1280)
        out_scale = min(1.0, max_w / max(1, frame_size[0]))
        out_size = (
            max(2, int(frame_size[0] * out_scale) // 2 * 2),
            max(2, int(frame_size[1] * out_scale) // 2 * 2),
        )
        if writer is not None and (out_size[0], out_size[1]) != frame_size:
            writer.release()
            writer, encoder_used = _open_writer(out_path, out_size[0], out_size[1], fps)
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
        # Annotated-video state: last live tracks (redrawn between det steps)
        # and the best plate reading per track for the gold label.
        current_tracks: List[TrackedBox] = []
        plate_labels: Dict[int, str] = {}

        def finalize_track(track_id: int) -> None:
            nonlocal plates_read
            meta = track_meta.pop(track_id, None)
            votes = plate_votes.pop(track_id, {})
            ocr_cooldown.pop(track_id, None)
            plate_labels.pop(track_id, None)
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
            if best_norm:
                plates_read += 1
                entry = match_watchlist(db, best_norm)
                if entry:
                    event.watchlist_match = True
                    db.commit()
                    alert = create_watchlist_alert(db, event, entry)
                    kind = "ALERT_CREATED" if alert else "WATCHLIST_MATCH"
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
                    "event_time": event.event_time.isoformat() if event.event_time else None,
                    "video_file": video_filename,
                    "video_offset": format_video_offset(offset),
                    "watchlist_match": event.watchlist_match,
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
                    vehicle_detection_service.detect(frame, imgsz=infer_imgsz, conf=infer_conf)
                    if detector_ok and vehicle_detection_service._model is not None
                    else []
                )
                live, retired = tracker.update(
                    [(d.x1, d.y1, d.x2, d.y2, d.class_name, d.confidence) for d in dets]
                )
                current_tracks = live
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
                    # OCR is by far the slowest step (~0.5s/call on CPU):
                    # stable tracks only, wide enough plate region, and a
                    # longer cooldown between attempts per track.
                    if (track.x2 - track.x1) < 64:
                        continue
                    ocr_cooldown[track.track_id] = 6
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
                    # Gold label on the annotated video: the read that currently
                    # leads the votes for this track.
                    best_norm_so_far = max(
                        votes.items(), key=lambda kv: kv[1][0] + 0.05 * kv[1][1]
                    )[0]
                    plate_labels[track.track_id] = best_norm_so_far
                    if reading.normalized == best_norm_so_far:
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
            # Annotated output: overlay boxes + plate reads on EVERY frame so
            # the output video plays at full original smoothness. When the
            # output is downscaled (UPLOAD_ANNOTATED_MAX_WIDTH), the frame and
            # the box coordinates are scaled to match.
            if writer is not None:
                draw_frame = frame
                draw_tracks = current_tracks
                if out_scale < 1.0:
                    draw_frame = cv2.resize(
                        frame, (out_size[0], out_size[1]), interpolation=cv2.INTER_AREA
                    )
                    draw_tracks = [
                        TrackedBox(
                            track_id=t.track_id,
                            x1=int(t.x1 * out_scale),
                            y1=int(t.y1 * out_scale),
                            x2=int(t.x2 * out_scale),
                            y2=int(t.y2 * out_scale),
                            class_name=t.class_name,
                            confidence=t.confidence,
                            hits=t.hits,
                            misses=t.misses,
                        )
                        for t in current_tracks
                    ]
                offset_str = format_video_offset(offset_sec)
                header = (
                    f"TRINETRA AI  |  {header_cam}  |  {video_filename}  |  "
                    f"t {offset_str}  |  Vehicles: {len(current_tracks)}"
                )
                draw_overlay(draw_frame, draw_tracks, plate_labels, header)
                writer.write(draw_frame)
            frame_idx += 1

        for track in tracker.flush():
            finalize_track(track.track_id)

        # ---- finish the annotated output video -----------------------------
        if writer is not None:
            writer.release()
            writer = None
            if encoder_used != "avc1" and _reencode_h264(out_path):
                logger.info(f"[UPLOAD:{camera_id}] Annotated video re-encoded to H.264.")
            logger.info(f"[UPLOAD:{camera_id}] Annotated video saved: {out_path}")

        cam.status = "ONLINE"
        cam.last_seen = datetime.now(timezone.utc)
        db.commit()
        _set_job(
            camera_id,
            job_status=DONE,
            progress_pct=100.0,
            frames_processed=frame_idx,
            vehicles_seen=vehicles_seen,
            last_processed_at=datetime.now(timezone.utc).isoformat(),
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
            if writer is not None:
                writer.release()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass
