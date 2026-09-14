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

import asyncio
import mimetypes
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.logging_config import logger
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

@router.post(
    "/videos/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more local videos for analysis",
)
async def upload_videos(
    files: List[UploadFile] = File(..., description="One or more video files"),
    batch_id: Optional[str] = Form(None),
    camera_ids: Optional[str] = Form(
        None, description="Optional comma-separated camera ids, aligned with the files"
    ),
    auto_start: bool = Form(False, description="Start analysis immediately after upload"),
    db: Session = Depends(get_db),
):
    """
    Store each uploaded video and register it as its own camera/video id.
    The filename is used as the camera identifier (``CAM1.mp4`` → ``CAM1``)
    unless an explicit id is supplied.

    Every container the decoder can read is accepted — .mp4/.avi/.mov/.mkv/
    .webm plus the CCTV/DVR/phone formats (.3gp, .ts, .wmv, .dav, .264, ...).
    A clip OpenCV cannot decode is converted with ffmpeg before it is
    registered, so uploading five clips registers five videos. Each file is
    handled off the event loop: probing/converting is blocking work and must
    not stall the rest of the API while a batch uploads.
    """
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No files were uploaded.")

    batch = (batch_id or "").strip() or uuid.uuid4().hex[:12]
    explicit = [c.strip() for c in (camera_ids or "").split(",") if c.strip()]

    added, errors = [], []
    for idx, upload in enumerate(files):
        name = upload.filename or f"video_{idx + 1}.mp4"
        try:
            data = await upload.read()
            video = await asyncio.to_thread(
                vas.register_upload,
                db, name, data, batch,
                explicit[idx] if idx < len(explicit) else None,
            )
            added.append(vas.video_to_dict(video))
        except vas.AnalysisError as exc:
            errors.append({"source_name": name, "error": str(exc)})
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

@router.post("/run", summary="Run the detection + ANPR pipeline on the videos")
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
                # Served through the confined evidence route, so a browser can
                # show exactly the pixels the AI judged without being handed a
                # filesystem path (and cannot walk out of the evidence root).
                "evidence_url": f"/api/evidence/{e.evidence_ref}" if e.evidence_ref else None,
                "plate_crop_url": (
                    f"/api/evidence/{e.plate_evidence_ref}" if e.plate_evidence_ref else None
                ),
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
