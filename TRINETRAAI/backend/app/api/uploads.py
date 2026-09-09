"""
Uploaded CCTV videos API (demo/test only — never live cameras).

POST /api/uploads/videos                  — upload a video as CAM<n> (+ auto-process)
GET  /api/uploads/videos                  — uploaded cameras + job states
GET  /api/uploads/videos/next-camera-id   — first free CAM<n> id
GET  /api/uploads/videos/{camera_id}      — one upload + recent plate reads
POST /api/uploads/videos/{camera_id}/process — (re-)run detection
GET  /api/uploads/videos/{camera_id}/annotated-video — OpenCV output video (boxes + plate reads)
GET  /api/uploads/videos/{camera_id}/file — download/stream the uploaded file
"""
import mimetypes
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.logging_config import logger
from ..database.database import get_db
from ..database.models import Camera, VehicleEvent
from ..database.schemas import (
    UploadedVideoDetailResponse,
    UploadedVideoResponse,
    VehicleEventResponse,
)
from ..services import uploaded_video_service as uvs

router = APIRouter(prefix="/uploads", tags=["Uploads"])


def _summary(cam: Camera) -> dict:
    job = uvs.get_job(cam.camera_id)
    return {
        "camera_id": cam.camera_id,
        "name": cam.name,
        "location": cam.location,
        "video_file": os.path.basename(cam.stream_url or ""),
        "status": cam.status or "OFFLINE",
        "annotated_available": uvs.has_annotated(cam.camera_id),
        **job,
    }


@router.get("/videos/next-camera-id")
def get_next_camera_id(db: Session = Depends(get_db)):
    """First free CAM<n> id for a new upload (sample metadata only)."""
    return {"camera_id": uvs.next_camera_id(db)}


@router.get("/videos", response_model=list[UploadedVideoResponse])
def list_uploaded_videos(db: Session = Depends(get_db)):
    """Every manually-uploaded CCTV video + its processing state."""
    return uvs.summaries(db)


@router.post(
    "/videos",
    response_model=UploadedVideoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CCTV video as a camera",
)
async def upload_video(
    file: UploadFile = File(..., description="CCTV video file (mp4/avi/mov/mkv/webm)"),
    camera_id: str = Form(..., description="Camera ID for this video, e.g. CAM1"),
    name: str | None = Form(None, description="Display name (defaults to the camera ID)"),
    location: str | None = Form(None, description="Where this footage was recorded"),
    db: Session = Depends(get_db),
):
    """Store a CCTV video, register it as a camera, and start detection."""
    try:
        cam_id = uvs.normalise_camera_id(camera_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty file uploaded.")
    try:
        path = uvs.save_upload(file.filename or "upload.mp4", data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    display_name = (name or "").strip() or cam_id
    place = (location or "").strip() or f"Uploaded Feed — {path.name}"

    cam = (
        db.query(Camera)
        .filter(func.upper(Camera.camera_id) == cam_id)
        .first()
    )
    if cam:
        # Re-upload to the same camera replaces the footage and reprocesses.
        old = cam.stream_url
        cam.name = display_name
        cam.location = place
        cam.stream_url = str(path)
        cam.stream_type = "file"
        cam.department = cam.department or "Traffic Police"
        cam.zone = uvs.UPLOADED_ZONE
        cam.status = "ONLINE"
        db.commit()
        db.refresh(cam)
        uvs.delete_annotated(cam.camera_id)  # stale annotated output from the old file
        if old and old != str(path) and old.startswith(str(uvs.upload_dir())):
            try:
                os.remove(old)
            except OSError:
                pass
        # Drop this camera's previous upload sightings so results always
        # reflect the current file — never a mix of two videos.
        db.query(VehicleEvent).filter(
            func.upper(VehicleEvent.camera_id) == cam_id,
            VehicleEvent.video_file.isnot(None),
        ).delete(synchronize_session=False)
        db.commit()
        logger.info(f"[UPLOAD:{cam_id}] Replaced footage with {path.name}; old upload sightings cleared.")
    else:
        cam = Camera(
            camera_id=cam_id,
            name=display_name,
            location=place,
            stream_url=str(path),
            stream_type="file",
            latitude=23.0225,
            longitude=72.5714,
            department="Traffic Police",
            zone=uvs.UPLOADED_ZONE,
            codec="H264",
            width=1920,
            height=1080,
            status="ONLINE",
        )
        db.add(cam)
        db.commit()
        db.refresh(cam)
        logger.info(f"[UPLOAD:{cam_id}] Registered {path.name} as {display_name}.")

    from ..camera.manager import camera_manager

    camera_manager.add_camera(
        camera_id=cam.camera_id,
        source=cam.stream_url,
        source_type="file",
        auto_start=False,
    )

    job = uvs.start_processing(cam.camera_id)
    return {**_summary(cam), **job}


@router.get("/videos/{camera_id}", response_model=UploadedVideoDetailResponse)
def get_uploaded_video(camera_id: str, db: Session = Depends(get_db)):
    """One uploaded video + its most recent plate reads."""
    cam = (
        db.query(Camera)
        .filter(func.upper(Camera.camera_id) == camera_id.strip().upper())
        .first()
    )
    if not cam or not uvs.is_uploaded_camera(cam):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Uploaded video '{camera_id}' not found."
        )
    recent = (
        db.query(VehicleEvent)
        .filter(func.upper(VehicleEvent.camera_id) == cam.camera_id.upper())
        .order_by(VehicleEvent.event_time.desc())
        .limit(50)
        .all()
    )
    return {
        **_summary(cam),
        "recent_plates": [VehicleEventResponse.model_validate(e) for e in recent],
    }


@router.post("/videos/{camera_id}/process", response_model=UploadedVideoResponse)
def process_uploaded_video(camera_id: str, db: Session = Depends(get_db)):
    """(Re-)run vehicle + number-plate detection on an uploaded video."""
    cam = (
        db.query(Camera)
        .filter(func.upper(Camera.camera_id) == camera_id.strip().upper())
        .first()
    )
    if not cam or not uvs.is_uploaded_camera(cam):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Uploaded video '{camera_id}' not found."
        )
    job = uvs.start_processing(cam.camera_id)
    return {**_summary(cam), **job}


@router.get("/videos/{camera_id}/annotated-video")
def get_annotated_video(camera_id: str, db: Session = Depends(get_db)):
    """
    OpenCV-annotated output video for an uploaded video — the original
    footage with green vehicle boxes, gold number-plate reads and the
    TRINETRA banner burned in. Produced by the detection job.
    """
    cam_id = camera_id.strip().upper()
    cam = db.query(Camera).filter(func.upper(Camera.camera_id) == cam_id).first()
    if not cam or not uvs.is_uploaded_camera(cam):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Uploaded video '{camera_id}' not found.")
    if not uvs.has_annotated(cam.camera_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Annotated video not ready yet — run detection first.",
        )
    path = uvs.annotated_path(cam.camera_id)
    return FileResponse(path, media_type="video/mp4", filename=f"{cam.camera_id}_annotated.mp4")


@router.get("/videos/{camera_id}/file")
def download_uploaded_video(camera_id: str, db: Session = Depends(get_db)):
    """Stream the uploaded video file itself."""
    cam = (
        db.query(Camera)
        .filter(func.upper(Camera.camera_id) == camera_id.strip().upper())
        .first()
    )
    if not cam or not uvs.is_uploaded_camera(cam):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Uploaded video '{camera_id}' not found."
        )
    path = cam.stream_url or ""
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video file missing from disk.")
    media, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=media or "video/mp4", filename=os.path.basename(path))
