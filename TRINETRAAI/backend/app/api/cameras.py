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
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from ..core.logging_config import logger
from ..database.database import get_db
from sqlalchemy import func, case
from ..database.models import Camera, VehicleEvent
from ..database.schemas import (
    CameraResponse,
    CameraCreate,
    CameraUpdate,
    CameraStreamInfo,
    CameraItem,
    CameraListResponse,
)
from ..camera.manager import camera_manager

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def _camera_event_stats(db: Session) -> Dict[str, tuple]:
    """One grouped query: {UPPER(camera_id): (last_event_at, events_in_24h)}."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = (
        db.query(
            func.upper(VehicleEvent.camera_id),
            func.max(VehicleEvent.event_time),
            func.sum(case((VehicleEvent.event_time >= since, 1), else_=0)),
        )
        .group_by(func.upper(VehicleEvent.camera_id))
        .all()
    )
    return {str(r[0]).upper(): (r[1], int(r[2] or 0)) for r in rows}


def _build_camera_item(cam: Camera, stream_status: Optional[dict], stats: Optional[tuple]) -> CameraItem:
    current_status = stream_status["status"] if stream_status else (cam.status or "OFFLINE")
    last_seen = stream_status["last_seen"] if stream_status and stream_status.get("last_seen") else cam.last_seen
    last_event_at, event_count_24h = stats if stats else (None, 0)
    return CameraItem(
        id=cam.camera_id.lower(),
        camera_id=cam.camera_id,
        name=cam.name,
        location=cam.location or cam.name,
        latitude=cam.latitude,
        longitude=cam.longitude,
        status=current_status,
        codec=cam.codec or "H264",
        width=cam.width or 1920,
        height=cam.height or 1080,
        stream_type=cam.stream_type.upper() if cam.stream_type else "HLS",
        stream_url=cam.stream_url,
        last_seen=last_seen,
        last_event_at=last_event_at,
        event_count_24h=event_count_24h,
    )


@router.get("", response_model=CameraListResponse, summary="List cameras", description="Returns normalized list of all registered CCTV cameras.")
def list_cameras(db: Session = Depends(get_db)):
    """List all registered CCTV cameras normalized for frontend and analytics."""
    cameras = db.query(Camera).all()
    stats = _camera_event_stats(db)
    items = []
    for cam in cameras:
        stream_status = camera_manager.get_camera_status(cam.camera_id)
        items.append(_build_camera_item(cam, stream_status, stats.get(cam.camera_id.upper())))
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
    stream_status = camera_manager.get_camera_status(cam.camera_id)
    stats_row = (
        db.query(
            func.max(VehicleEvent.event_time),
            func.sum(
                case(
                    (VehicleEvent.event_time >= datetime.now(timezone.utc) - timedelta(hours=24), 1),
                    else_=0,
                )
            ),
        )
        .filter(func.upper(VehicleEvent.camera_id) == cam.camera_id.upper())
        .one()
    )
    return _build_camera_item(
        cam,
        stream_status,
        (stats_row[0], int(stats_row[1] or 0)) if stats_row[0] else None,
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
