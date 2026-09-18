"""
Multi-video analysis API.

    POST   /api/analysis/videos/upload      — upload one or many local videos
    POST   /api/analysis/videos/gdrive      — add a shared Google Drive video
    POST   /api/analysis/videos/gdrive/validate — validate a Drive link only
    GET    /api/analysis/videos             — list registered videos
    DELETE /api/analysis/videos/{video_id}  — remove a video + its detections
    POST   /api/analysis/run                — start/restart the analysis
    GET    /api/analysis/status             — processing status of every video
    GET    /api/analysis/results            — cross-video comparison results
    GET    /api/analysis/search?plate=…     — search one number plate
    GET    /api/analysis/vehicles/{plate}   — full vehicle history
    GET    /api/analysis/videos/{id}/detections — raw detections of one video
    GET    /api/analysis/videos/{id}/file   — stream the stored video back

Mounted under both /api and /api/v1 like every other router in this backend.
No existing endpoint is modified.
"""
from __future__ import annotations

import mimetypes
import os
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logging_config import logger
from ..core.vision import require_vision
from ..database.database import get_db
from ..database.models import VehicleEvent, VideoSource
from ..services import gdrive_service, plate_matching
from ..services import video_analysis_service as vas

router = APIRouter(prefix="/analysis", tags=["Video Analysis"])


class GDriveRequest(BaseModel):
    url: str = Field(..., example="https://drive.google.com/file/d/FILE_ID/view?usp=sharing")
    camera_id: Optional[str] = Field(None, example="CAM2")
    batch_id: Optional[str] = None


class RunRequest(BaseModel):
    video_ids: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@router.post(
    "/videos/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more local videos for analysis",
)
async def upload_videos(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Store each uploaded video and register it as its own camera/video id.
    The filename is used as the camera identifier (``CAM1.mp4`` → ``CAM1``)
    unless an explicit id is supplied.

    Form fields are parsed manually from ``request.form()`` instead of via
    FastAPI's ``File(...) / Form(...)`` magic because mixing ``List[UploadFile]``
    with ``Form(...)`` fields triggers a pydantic/FastAPI bug (HTTP 422
    "object() takes no arguments" / HTTP 500) on certain deployed versions.
    """
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse multipart form: {exc}",
        )

    # Collect every uploaded file (supports both "files" and legacy "file").
    files: List[UploadFile] = []
    for key in ("files", "file"):
        val = form.getlist(key)
        for item in val:
            if isinstance(item, UploadFile) and item.filename:
                files.append(item)

    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No files were uploaded.")

    batch_id_val = form.get("batch_id")
    camera_ids_val = form.get("camera_ids")
    auto_start = _as_bool(form.get("auto_start"))
    # NOTE: default for analysis is ALWAYS False here. The operator presses
    # "Start analysis" manually after uploads finish — matching the UX request.

    batch = (str(batch_id_val).strip() if batch_id_val else "") or uuid.uuid4().hex[:12]
    explicit = [c.strip() for c in (str(camera_ids_val) if camera_ids_val else "").split(",") if c.strip()]

    added, errors = [], []
    for idx, upload in enumerate(files):
        name = upload.filename or f"video_{idx + 1}.mp4"
        try:
            # Stream to disk instead of buffering the entire file in RAM —
            # avoids a multi-GB upload OOMing the function the moment it arrives.
            safe = vas.safe_filename(name)
            suffix = Path(safe).suffix.lower()
            if suffix not in vas.ALLOWED_VIDEO_SUFFIXES:
                raise vas.AnalysisError(
                    f"'{name}': unsupported video type '{suffix or '?'}'. "
                    f"Use {', '.join(sorted(vas.ALLOWED_VIDEO_SUFFIXES))}."
                )
            tmp_dir = vas.analysis_dir()
            tmp_dir.mkdir(parents=True, exist_ok=True)
            max_bytes = int(settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024
            tmp_path = Path(tempfile.mkstemp(prefix=".ul_", suffix=suffix, dir=tmp_dir)[1])
            bytes_written = 0
            try:
                with tmp_path.open("wb") as fh:
                    while True:
                        chunk = await upload.read(1024 * 1024)
                        if not chunk:
                            break
                        bytes_written += len(chunk)
                        if bytes_written > max_bytes:
                            raise vas.AnalysisError(
                                f"'{name}' exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit."
                            )
                        fh.write(chunk)
                if bytes_written == 0:
                    raise vas.AnalysisError(f"'{name}' is empty.")
                video = vas.register_from_path(
                    db, tmp_path, name, batch,
                    camera_id=explicit[idx] if idx < len(explicit) else None,
                )
                added.append(vas.video_to_dict(video))
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
        except vas.AnalysisError as exc:
            errors.append({"source_name": name, "error": str(exc)})
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - unexpected decode failures
            logger.exception(f"[ANALYSIS] upload of {name} failed")
            errors.append({"source_name": name, "error": str(exc)})

    if not added and errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=errors[0]["error"] if len(errors) == 1 else
            "; ".join(f"{e['source_name']}: {e['error']}" for e in errors),
        )

    if auto_start and added:
        try:
            vas.start_analysis(db, [v["video_id"] for v in added])
        except vas.AnalysisError as exc:
            errors.append({"source_name": "*", "error": str(exc)})

    return {"batch_id": batch, "added": added, "errors": errors}


@router.post("/videos/gdrive/validate", summary="Validate a Google Drive video link")
def validate_gdrive(payload: GDriveRequest):
    """
    Check a Drive share link *without* downloading it. Returns whether the file
    is reachable and, when it is not, exactly why.
    """
    try:
        link = gdrive_service.parse_drive_url(payload.url)
    except gdrive_service.DriveError as exc:
        return {"valid": False, "accessible": False, "reason": str(exc)}

    info = gdrive_service.probe(payload.url)
    return {
        "valid": True,
        "file_id": link.file_id,
        "normalized_url": link.normalized_url,
        "accessible": info.accessible,
        "file_name": info.file_name,
        "size_bytes": info.size_bytes,
        "content_type": info.content_type,
        "reason": info.reason,
        "suggested_camera_id": vas.camera_id_from_filename(info.file_name or link.file_id),
    }


@router.post(
    "/videos/gdrive",
    status_code=status.HTTP_201_CREATED,
    summary="Add a shared Google Drive video for analysis",
)
def add_gdrive_video(payload: GDriveRequest, db: Session = Depends(get_db)):
    """
    Download an "Anyone with the link" Drive video and register it.
    No Google account or credential is ever requested from the user.
    """
    batch = (payload.batch_id or "").strip() or uuid.uuid4().hex[:12]
    try:
        video = vas.register_gdrive(db, payload.url, batch, camera_id=payload.camera_id)
    except vas.AnalysisError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {"batch_id": batch, "added": [vas.video_to_dict(video)], "errors": []}


@router.get("/videos", summary="List every video registered for analysis")
def list_videos(batch_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    return {"videos": vas.list_videos(db, batch_id)}


@router.delete("/videos/{video_id}", summary="Remove a video and its detections")
def delete_video(video_id: str, db: Session = Depends(get_db)):
    try:
        vas.delete_video(db, video_id)
    except vas.AnalysisError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"deleted": video_id}


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

@router.post(
    "/run",
    summary="Run the detection + ANPR pipeline on the videos",
    dependencies=[Depends(require_vision)],
)
def run_analysis(payload: Optional[RunRequest] = None, db: Session = Depends(get_db)):
    ids = payload.video_ids if payload else None
    try:
        queued = vas.start_analysis(db, ids)
    except vas.AnalysisError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {
        "queued": [v.video_id for v in queued],
        "status": vas.batch_status(db, None),
    }


@router.get("/status", summary="Processing status of every analysis video")
def analysis_status(batch_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    return vas.batch_status(db, batch_id)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@router.get("/results", summary="Cross-video number-plate comparison")
def results(batch_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """
    Every plate read across every analysed video, which videos it appeared in,
    the observed camera sequence, and its full history. Generated live from
    stored detections — nothing is cached or hard-coded.
    """
    return plate_matching.analyse(db, batch_id)


@router.get("/search", summary="Search a number plate across all analysed videos")
def search_plate(
    plate: str = Query(..., min_length=1, description="Number plate, any formatting"),
    batch_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        return plate_matching.search(db, plate, batch_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/vehicles/{plate}", summary="Vehicle history across analysed videos")
def vehicle_history(plate: str, batch_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    record = plate_matching.vehicle_history(db, plate, batch_id)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"'{plate}' was not read in any analysed video.",
        )
    return record


@router.get("/videos/{video_id}/detections", summary="Raw detections from one video")
def video_detections(
    video_id: str,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    video = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
    if not video:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Video '{video_id}' not found.")
    events = (
        db.query(VehicleEvent)
        .filter(VehicleEvent.video_id == video_id)
        .order_by(VehicleEvent.video_offset_sec.asc())
        .limit(limit)
        .all()
    )
    return {
        "video": vas.video_to_dict(video),
        "detections": [
            {
                "event_id": e.id,
                "frame_number": e.frame_number,
                "video_offset_sec": e.video_offset_sec,
                "timestamp": vas.format_offset(e.video_offset_sec),
                "track_id": e.vehicle_track_id,
                "vehicle_class": e.vehicle_class,
                "detection_confidence": e.vehicle_confidence,
                "bbox": e.bbox,
                "plate": e.plate_number,
                "raw_ocr": e.plate_raw,
                "ocr_confidence": e.plate_confidence,
                "plate_status": e.plate_status,
                "evidence_ref": e.evidence_ref,
            }
            for e in events
        ],
    }


@router.get("/videos/{video_id}/file", summary="Stream a stored analysis video")
def get_video_file(video_id: str, db: Session = Depends(get_db)):
    video = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
    if not video or not video.file_path or not os.path.isfile(video.file_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video file not found.")
    media, _ = mimetypes.guess_type(video.file_path)
    return FileResponse(
        video.file_path,
        media_type=media or "video/mp4",
        filename=os.path.basename(video.file_path),
    )
