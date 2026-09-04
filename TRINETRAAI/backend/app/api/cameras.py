import sys
from pathlib import Path
from datetime import timedelta
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
from ..utils.timestamps import utc_now
from ..database.database import get_db
from sqlalchemy import func
from ..database.models import Camera, VehicleEvent
from ..database.schemas import (
    CameraResponse,
    CameraCreate,
    CameraUpdate,
    CameraStreamInfo,
    CameraItem,
    CameraListResponse,
    CameraStreamTicket,
)
from ..camera.manager import camera_manager

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def _event_counts_24h(db: Session, camera_ids: list[str] | None = None) -> dict[str, int]:
    """Detections per camera in the last 24h, as ONE grouped query.

    Serialising cameras one-by-one with a COUNT each would be an N+1; the
    camera list asks for all 30 at once, so we aggregate up front and hand
    the result to _serialize_camera.
    """
    since = utc_now() - timedelta(hours=24)
    q = (
        db.query(VehicleEvent.camera_id, func.count(VehicleEvent.id))
        .filter(VehicleEvent.event_time >= since)
    )
    if camera_ids:
        q = q.filter(VehicleEvent.camera_id.in_(camera_ids))
    return {cid: int(n) for cid, n in q.group_by(VehicleEvent.camera_id).all()}


def _serialize_camera(cam: Camera, event_counts: dict[str, int] | None = None) -> CameraItem:
    """Single source of truth for the camera contract (spec Phase 3 / 39).

    Every endpoint returns cameras through this function so the registry, the
    grid, the map and the detail page can never disagree about a camera's
    status, department, codec or resolution. Live ingestion state (from the
    CameraManager) always wins over the last value persisted in the DB.
    """
    stream_status = camera_manager.get_camera_status(cam.camera_id)
    current_status = stream_status["status"] if stream_status else (cam.status or "OFFLINE")
    last_seen = (
        stream_status["last_seen"]
        if stream_status and stream_status.get("last_seen")
        else cam.last_seen
    )
    return CameraItem(
        id=cam.camera_id.lower(),
        camera_id=cam.camera_id,
        name=cam.name,
        location=cam.location or cam.name,
        latitude=cam.latitude,
        longitude=cam.longitude,
        department=cam.department,
        status=current_status,
        codec=cam.codec or "H264",
        width=cam.width or 1920,
        height=cam.height or 1080,
        stream_type=cam.stream_type.upper() if cam.stream_type else "HLS",
        stream_url=cam.stream_url,
        last_seen=last_seen,
        is_demo_feed=bool(stream_status.get("is_demo_feed")) if stream_status else False,
        last_error=stream_status.get("last_error") if stream_status else None,
        event_count_24h=(event_counts or {}).get(cam.camera_id, 0),
    )


@router.get("", response_model=CameraListResponse, summary="List cameras", description="Returns normalized list of all registered CCTV cameras.")
def list_cameras(db: Session = Depends(get_db)):
    """List all registered CCTV cameras normalized for frontend and analytics."""
    cameras = db.query(Camera).order_by(Camera.camera_id).all()
    counts = _event_counts_24h(db)
    return CameraListResponse(data=[_serialize_camera(c, counts) for c in cameras])


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


@router.get(
    "/{camera_id}/stream",
    response_model=CameraStreamTicket,
    summary="Get playback ticket for a camera",
    description=(
        "Returns how the browser should play this camera. The backend chooses "
        "the transport so the UI never guesses and never holds credentials."
    ),
)
def get_camera_stream(camera_id: str, db: Session = Depends(get_db)):
    """Resolve the playback transport for a camera.

    We serve MJPEG from our own ingestion pipeline. That is the transport that
    actually works everywhere: it is same-origin (no CORS, no mixed content),
    needs no WebRTC signalling to an external gateway, and carries the AI
    overlay we already draw. WebRTC/WHEP remains available for deployments
    where the media gateway is reachable from the browser.
    """
    cam = db.query(Camera).filter(func.upper(Camera.camera_id) == camera_id.strip().upper()).first()
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    live = camera_manager.get_camera_status(cam.camera_id)
    is_demo = bool(live.get("is_demo_feed")) if live else False

    return CameraStreamTicket(
        camera_id=cam.camera_id,
        stream_type="MJPEG",
        stream_url=f"/api/cameras/{cam.camera_id}/live",
        is_demo_feed=is_demo,
        note=(
            "Synthetic demo frames — the live source is unreachable."
            if is_demo
            else None
        ),
    )


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
    return _serialize_camera(cam, _event_counts_24h(db, [cam.camera_id]))


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

    Headers disable proxy/browser buffering; without them an intermediary can
    hold frames back and the player looks frozen.
    """
    return StreamingResponse(
        camera_manager.generate_mjpeg_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "close",
            "X-Accel-Buffering": "no",
        },
    )
