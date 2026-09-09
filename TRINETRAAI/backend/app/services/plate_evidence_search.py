"""
Photo-evidence search: number plate → clustered real video frames.

Uses frames captured during analysis (``plate_evidence_frames``). If those
rows are missing (older analyses), falls back to ``vehicle_events`` and
extracts the actual frame from the stored video file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import cv2
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logging_config import logger
from ..database.models import PlateEvidenceFrame, VehicleEvent, VideoSource
from ..utils.plate_normalizer import normalize_plate

OCCURRENCE_GAP_SEC = 2.5


def _fmt_offset(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, r = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{r:02d}"
    return f"{m:02d}:{r:02d}"


def _evidence_root() -> Path:
    root = Path(settings.EVIDENCE_ROOT)
    if not root.is_absolute():
        root = (Path(__file__).resolve().parents[2] / root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def evidence_url(ref: Optional[str]) -> Optional[str]:
    if not ref:
        return None
    return f"/api/evidence/{ref}"


def _write_jpeg(path: Path, image) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not ok:
            return False
        path.write_bytes(buf.tobytes())
        return True
    except Exception as exc:
        logger.warning(f"[PHOTO-EV] write failed {path}: {exc}")
        return False


def save_ocr_frame(
    db: Session,
    *,
    video: VideoSource,
    frame,
    plate: str,
    plate_raw: Optional[str],
    confidence: float,
    frame_number: int,
    offset_sec: float,
    bbox,
    track_id: Optional[int],
    vehicle_class: Optional[str],
) -> Optional[PlateEvidenceFrame]:
    """Persist a full video frame for one successful OCR read."""
    plate_n = normalize_plate(plate)
    if not plate_n or frame is None:
        return None
    try:
        ev_dir = _evidence_root() / "analysis" / "frames" / video.camera_id.lower()
        fname = (
            f"{video.camera_id.lower()}_{int(offset_sec * 1000)}ms_"
            f"f{frame_number}_{plate_n.lower()}.jpg"
        )
        if not _write_jpeg(ev_dir / fname, frame):
            return None
        ref = f"analysis/frames/{video.camera_id.lower()}/{fname}"
        row = PlateEvidenceFrame(
            video_id=video.video_id,
            camera_id=video.camera_id,
            plate_number=plate_n,
            plate_raw=plate_raw,
            plate_confidence=float(confidence or 0.0),
            vehicle_class=vehicle_class,
            track_id=track_id,
            frame_number=int(frame_number),
            video_offset_sec=float(offset_sec),
        )
        row.bbox = list(bbox) if bbox else None
        row.evidence_ref = ref
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        logger.warning(f"[PHOTO-EV] save_ocr_frame failed: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


def delete_for_video(db: Session, video_id: str) -> None:
    rows = db.query(PlateEvidenceFrame).filter(PlateEvidenceFrame.video_id == video_id).all()
    root = _evidence_root()
    for row in rows:
        if row.evidence_ref:
            try:
                (root / row.evidence_ref).unlink(missing_ok=True)
            except OSError:
                pass
        db.delete(row)


def _extract_frame(video_path: str, frame_number: Optional[int], offset_sec: Optional[float]):
    if not video_path or not os.path.isfile(video_path):
        return None
    cap = cv2.VideoCapture(video_path)
    try:
        if not cap.isOpened():
            return None
        if frame_number is not None and frame_number >= 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_number))
        elif offset_sec is not None:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(offset_sec) * 1000.0)
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def _ensure_frame_file(row_like: dict, video: Optional[VideoSource]) -> Optional[str]:
    ref = row_like.get("evidence_ref")
    root = _evidence_root()
    if ref and (root / ref).is_file():
        return ref
    if video is None or not video.file_path:
        return None
    frame = _extract_frame(video.file_path, row_like.get("frame_number"), row_like.get("video_offset_sec"))
    if frame is None:
        return None
    cam = (video.camera_id or "video").lower()
    plate = (row_like.get("plate") or "plate").lower()
    offset_ms = int(float(row_like.get("video_offset_sec") or 0) * 1000)
    fname = f"{cam}_{offset_ms}ms_f{row_like.get('frame_number') or 0}_{plate}.jpg"
    dest = root / "analysis" / "frames" / cam / fname
    if not _write_jpeg(dest, frame):
        return None
    return f"analysis/frames/{cam}/{fname}"


def _cluster(rows: List[dict]) -> List[dict]:
    """Group near-identical consecutive detections of the same plate in one video."""
    rows = sorted(
        rows,
        key=lambda r: (
            r.get("video_id") or "",
            float(r.get("video_offset_sec") or 0.0),
            r.get("frame_number") or 0,
        ),
    )
    groups: List[List[dict]] = []
    for r in rows:
        if not groups:
            groups.append([r])
            continue
        prev = groups[-1][-1]
        same_video = (prev.get("video_id") or "") == (r.get("video_id") or "")
        gap = abs(float(r.get("video_offset_sec") or 0) - float(prev.get("video_offset_sec") or 0))
        if same_video and gap <= OCCURRENCE_GAP_SEC:
            groups[-1].append(r)
        else:
            groups.append([r])

    out = []
    for i, g in enumerate(groups, start=1):
        best = max(g, key=lambda x: float(x.get("plate_confidence") or 0.0))
        first = g[0]
        last = g[-1]
        out.append({
            **best,
            "occurrence": i,
            "grouped_detections": len(g),
            "first_seen_sec": first.get("video_offset_sec"),
            "last_seen_sec": last.get("video_offset_sec"),
        })
    return out


def search_frames(
    db: Session,
    plate_query: str,
    video_id: Optional[str] = None,
) -> dict:
    query = normalize_plate(plate_query)
    if not query:
        raise ValueError("Enter a number plate to search for.")

    q = db.query(PlateEvidenceFrame).filter(PlateEvidenceFrame.plate_number == query)
    if video_id:
        q = q.filter(PlateEvidenceFrame.video_id == video_id)
    frames = q.order_by(PlateEvidenceFrame.video_offset_sec.asc()).all()

    videos = {v.video_id: v for v in db.query(VideoSource).all()}

    rows: List[dict] = []
    if frames:
        for f in frames:
            rows.append({
                "event_id": f.id,
                "video_id": f.video_id,
                "camera_id": f.camera_id,
                "source_name": videos.get(f.video_id).source_name if videos.get(f.video_id) else None,
                "plate": f.plate_number,
                "raw_ocr": f.plate_raw,
                "plate_confidence": float(f.plate_confidence or 0.0),
                "vehicle_class": f.vehicle_class,
                "track_id": f.track_id,
                "frame_number": f.frame_number,
                "bbox": f.bbox,
                "video_offset_sec": f.video_offset_sec,
                "evidence_ref": f.evidence_ref,
            })
    else:
        eq = db.query(VehicleEvent).filter(VehicleEvent.plate_number == query)
        if video_id:
            eq = eq.filter(VehicleEvent.video_id == video_id)
        for e in eq.order_by(VehicleEvent.video_offset_sec.asc()).all():
            if not e.plate_number:
                continue
            rows.append({
                "event_id": e.id,
                "video_id": e.video_id,
                "camera_id": e.camera_id,
                "source_name": e.video_file,
                "plate": e.plate_number,
                "raw_ocr": e.plate_raw,
                "plate_confidence": float(e.plate_confidence or 0.0),
                "vehicle_class": e.vehicle_class,
                "track_id": e.vehicle_track_id,
                "frame_number": e.frame_number,
                "bbox": e.bbox,
                "video_offset_sec": e.video_offset_sec,
                "evidence_ref": e.evidence_ref,
            })

    clustered = _cluster(rows)
    matches = []
    for c in clustered:
        video = videos.get(c.get("video_id") or "")
        ref = _ensure_frame_file(c, video)
        if not ref:
            continue
        matches.append({
            "occurrence": c["occurrence"],
            "plate": c["plate"],
            "timestamp": _fmt_offset(c.get("video_offset_sec")),
            "video_offset_sec": c.get("video_offset_sec"),
            "frame_number": c.get("frame_number"),
            "confidence": round(float(c.get("plate_confidence") or 0.0), 4),
            "camera_id": c.get("camera_id"),
            "video_id": c.get("video_id"),
            "source_name": c.get("source_name"),
            "vehicle_class": c.get("vehicle_class"),
            "bbox": c.get("bbox"),
            "grouped_detections": c.get("grouped_detections"),
            "frame_url": evidence_url(ref),
            "evidence_ref": ref,
        })

    return {
        "query": plate_query,
        "normalized_query": query,
        "found": len(matches) > 0,
        "match_count": len(matches),
        "matches": matches,
        "message": None if matches else "No matching number plate found in this video.",
    }
