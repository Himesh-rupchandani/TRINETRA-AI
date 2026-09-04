import sys
from pathlib import Path
from typing import List, Optional

# Allow running this file directly as a script
if __name__ == "__main__" and not __package__:
    project_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]
    for p in [str(project_root), str(backend_root)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    __package__ = "backend.app.api"

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.logging_config import logger
from ..database.database import get_db
from sqlalchemy import func
from ..database.models import Camera
from ..database.schemas import (
    CameraResponse,
    CameraCreate,
    CameraUpdate,
    CameraStreamInfo,
    CameraStreamTicket,
    CameraItem,
    CameraListResponse,
)
from ..camera.manager import camera_manager

router = APIRouter(prefix="/cameras", tags=["Cameras"])



# The API contract exposes exactly three camera states (ONLINE / OFFLINE /
# DEGRADED). The ingestion engine has a richer lifecycle, so map it down rather
# than leaking CONNECTING/RECONNECTING/STOPPED into the UI.
_LIVE_TO_API_STATUS = {
    "ONLINE": "ONLINE",
    "DEGRADED": "DEGRADED",
    "CONNECTING": "ONLINE",
    "RECONNECTING": "DEGRADED",
    "OFFLINE": "OFFLINE",
    "STOPPED": "OFFLINE",
}


def _resolve_camera_status(cam: "Camera") -> tuple:
    """Return (status, last_seen) for a camera.

    A live worker only overrides the registry status when it is actually
    delivering frames. Otherwise the registry value stands, so a camera whose
    stream has simply not been opened yet is not misreported as OFFLINE.
    """
    stream_status = camera_manager.get_camera_status(cam.camera_id)
    if stream_status and stream_status.get("is_alive"):
        mapped = _LIVE_TO_API_STATUS.get(stream_status.get("status"), None)
        if mapped:
            return mapped, stream_status.get("last_seen") or cam.last_seen
    return (cam.status or "OFFLINE"), cam.last_seen


@router.get("", response_model=CameraListResponse, summary="List cameras", description="Returns normalized list of all registered CCTV cameras.")
def list_cameras(db: Session = Depends(get_db)):
    """List all registered CCTV cameras normalized for frontend and analytics."""
    cameras = db.query(Camera).all()
    items = []
    for cam in cameras:
        current_status, last_seen = _resolve_camera_status(cam)
        items.append(
            CameraItem(
                id=cam.camera_id.lower(),
                camera_id=cam.camera_id,
                name=cam.name,
                location=cam.location or cam.name,
                latitude=cam.latitude,
                longitude=cam.longitude,
                status=current_status,
                department=cam.department,
                zone=cam.zone,
                codec=cam.codec or "H264",
                width=cam.width or 1920,
                height=cam.height or 1080,
                fps=cam.fps,
                stream_type=cam.stream_type.upper() if cam.stream_type else "HLS",
                stream_url=cam.stream_url,
                last_seen=last_seen,
            )
        )
    return CameraListResponse(data=items)


@router.get("/active-streams", response_model=List[CameraStreamInfo])
def list_active_streams():
    """List all active live camera ingestion streams."""
    cam_data = camera_manager.list_cameras()
    return [
        CameraStreamInfo(
            camera_id=c["camera_id"],
            status=c["status"],
            fps=c["fps"],
            frame_count=c["frame_count"],
            is_alive=c["is_alive"],
            last_error=c["last_error"],
        )
        for c in cam_data
    ]


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    """Register a new CCTV camera."""
    existing = db.query(Camera).filter(Camera.camera_id == payload.camera_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Camera with ID '{payload.camera_id}' already exists.",
        )

    new_cam = Camera(
        camera_id=payload.camera_id,
        name=payload.name,
        stream_url=payload.stream_url,
        stream_type=payload.stream_type,
        latitude=payload.latitude,
        longitude=payload.longitude,
        status="OFFLINE",
    )
    db.add(new_cam)
    db.commit()
    db.refresh(new_cam)

    # Register in CameraManager
    camera_manager.add_camera(
        camera_id=new_cam.camera_id,
        source=new_cam.stream_url,
        source_type=new_cam.stream_type,
        auto_start=True,
    )
    return new_cam


@router.get("/{camera_id}", response_model=CameraItem, summary="Get camera by ID")
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    """Get details of a specific camera (by camera_id like 'CAM04' / 'cam04' or integer id)."""
    filter_cond = (func.upper(Camera.camera_id) == camera_id.strip().upper())
    if camera_id.isdigit():
        filter_cond = filter_cond | (Camera.id == int(camera_id))
    cam = db.query(Camera).filter(filter_cond).first()
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )
    current_status, last_seen = _resolve_camera_status(cam)
    return CameraItem(
        id=cam.camera_id.lower(),
        camera_id=cam.camera_id,
        name=cam.name,
        location=cam.location or cam.name,
        latitude=cam.latitude,
        longitude=cam.longitude,
        status=current_status,
        department=cam.department,
        zone=cam.zone,
        codec=cam.codec or "H264",
        width=cam.width or 1920,
        height=cam.height or 1080,
        fps=cam.fps,
        stream_type=cam.stream_type.upper() if cam.stream_type else "HLS",
        stream_url=cam.stream_url,
        last_seen=last_seen,
    )


@router.get(
    "/{camera_id}/stream",
    response_model=CameraStreamTicket,
    summary="Issue a playback ticket for one camera",
    description=(
        "Returns safe, short-lived playback info. Browsers receive a same-origin "
        "WebRTC/WHEP signalling path served by the reverse proxy — RTSP URLs and "
        "Sentinel credentials never reach the client."
    ),
)
def get_camera_stream_ticket(camera_id: str, db: Session = Depends(get_db)):
    """Resolve the browser-playable stream for a camera.

    - ONLINE camera -> WEBRTC ticket on the same-origin WHEP path.
    - anything else -> unplayable ticket; the UI shows its offline state.
    """
    from datetime import datetime, timezone, timedelta

    cam = (
        db.query(Camera)
        .filter(func.upper(Camera.camera_id) == camera_id.strip().upper())
        .first()
    )
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    stream_status = camera_manager.get_camera_status(cam.camera_id)
    status_value = (stream_status["status"] if stream_status else (cam.status or "OFFLINE")).upper()
    playable = status_value == "ONLINE"
    slug = cam.camera_id.lower()

    return CameraStreamTicket(
        camera_id=slug,
        stream_type="WEBRTC" if playable else (cam.stream_type or "hls").upper(),
        stream_url=f"/sentinel/{slug}/whep" if playable else "",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        playable=playable,
        reason=None if playable else f"Camera is {status_value}",
    )


@router.put("/{camera_id}", response_model=CameraResponse)
def update_camera(camera_id: str, payload: CameraUpdate, db: Session = Depends(get_db)):
    """Update camera configuration and restart stream if URL changed."""
    cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    stream_changed = False
    if payload.name is not None:
        cam.name = payload.name
    if payload.stream_url is not None and payload.stream_url != cam.stream_url:
        cam.stream_url = payload.stream_url
        stream_changed = True
    if payload.stream_type is not None and payload.stream_type != cam.stream_type:
        cam.stream_type = payload.stream_type
        stream_changed = True
    if payload.latitude is not None:
        cam.latitude = payload.latitude
    if payload.longitude is not None:
        cam.longitude = payload.longitude
    if payload.status is not None:
        cam.status = payload.status

    db.commit()
    db.refresh(cam)

    if stream_changed:
        camera_manager.add_camera(
            camera_id=cam.camera_id,
            source=cam.stream_url,
            source_type=cam.stream_type,
            auto_start=True,
        )

    return cam


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    """Remove a camera from the database and stop its ingestion stream."""
    cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    camera_manager.remove_camera(camera_id)
    db.delete(cam)
    db.commit()
    return None


@router.post("/{camera_id}/start")
def start_camera(camera_id: str, db: Session = Depends(get_db)):
    """Start ingestion worker for a camera."""
    cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    stream = camera_manager.get_camera(camera_id)
    if not stream:
        camera_manager.add_camera(
            camera_id=cam.camera_id,
            source=cam.stream_url,
            source_type=cam.stream_type,
            auto_start=True,
        )
    else:
        camera_manager.start_camera(camera_id)

    return {"status": "started", "camera_id": camera_id}


@router.post("/{camera_id}/stop")
def stop_camera(camera_id: str):
    """Stop ingestion worker and release resources for a camera."""
    success = camera_manager.stop_camera(camera_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera stream '{camera_id}' is not active.",
        )
    return {"status": "stopped", "camera_id": camera_id}


@router.post("/{camera_id}/restart")
def restart_camera(camera_id: str):
    """Restart stream ingestion for a camera."""
    success = camera_manager.restart_camera(camera_id)
    return {"status": "restarted", "camera_id": camera_id, "success": success}


@router.get("/{camera_id}/live")
def live_mjpeg_stream(camera_id: str):
    """
    Live Multipart MJPEG Stream endpoint for browser and dashboard video feeds.
    """
    return StreamingResponse(
        camera_manager.generate_mjpeg_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
