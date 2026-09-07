import os
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

from ..core.config import settings
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
from ..services.sentinel_stream_service import (
    can_decode_for_detection,
    has_embedded_credentials,
    redact,
    resolve_ingest_source,
    resolve_ingest_stream_type,
)

router = APIRouter(prefix="/cameras", tags=["Cameras"])


def _safe_camera_response(cam: Camera) -> CameraResponse:
    """Serialize mutable camera records without returning source credentials.

    Playback always goes through ``/{id}/stream``. The registry field is kept
    for backwards-compatible metadata clients, but userinfo and signed query
    values are stripped before this response leaves the server.
    """
    return CameraResponse(
        id=cam.id,
        camera_id=cam.camera_id,
        name=cam.name,
        stream_url=redact(cam.stream_url),
        stream_type=cam.stream_type,
        latitude=cam.latitude,
        longitude=cam.longitude,
        location=cam.location,
        codec=cam.codec,
        width=cam.width,
        height=cam.height,
        status=cam.status,
        last_seen=cam.last_seen,
        created_at=cam.created_at,
    )


def _reject_embedded_stream_credentials(stream_url: str) -> None:
    """Keep credentials in environment/secret storage rather than the DB/API."""
    if has_embedded_credentials(stream_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Camera URLs with embedded credentials or signed tokens are not accepted here. "
                "Configure authorized access server-side with LIVE_CAMERA_* environment variables."
            ),
        )


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
    # No source configured at all (e.g. the env-driven live camera slot
    # before an authorized URL is provided): never pretend it is online.
    if not (cam.stream_url or "").strip():
        return "NOT_CONFIGURED", cam.last_seen
    stream_status = camera_manager.get_camera_status(cam.camera_id)
    if stream_status and stream_status.get("is_alive"):
        mapped = _LIVE_TO_API_STATUS.get(stream_status.get("status"), None)
        if mapped:
            return mapped, stream_status.get("last_seen") or cam.last_seen
    # File-backed cameras are playable whenever their media exists on disk:
    # the live view is decoded on demand, so no permanent worker is required.
    if (cam.stream_type or "").lower() == "file" and cam.stream_url and os.path.exists(cam.stream_url):
        return "ONLINE", cam.last_seen
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
                stream_url=redact(cam.stream_url),
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
    """Register a new CCTV camera without storing browser-visible secrets."""
    _reject_embedded_stream_credentials(payload.stream_url)
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

    # Register the display reference, but only start a decoder when it has an
    # OpenCV-compatible source. WHEP/WebRTC remains browser playback unless a
    # paired server-side ingest has been configured for the live camera slot.
    source = resolve_ingest_source(new_cam.camera_id, new_cam.stream_url, new_cam.stream_type)
    source_type = resolve_ingest_stream_type(new_cam.camera_id, new_cam.stream_url, new_cam.stream_type)
    camera_manager.add_camera(
        camera_id=new_cam.camera_id,
        source=source,
        source_type=source_type,
        auto_start=can_decode_for_detection(new_cam.camera_id, new_cam.stream_type),
    )
    return _safe_camera_response(new_cam)


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
        stream_url=redact(cam.stream_url),
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

    if not (cam.stream_url or "").strip():
        return CameraStreamTicket(
            camera_id=cam.camera_id.lower(),
            stream_type=(cam.stream_type or "rtsp").upper(),
            stream_url="",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            playable=False,
            reason="Camera source not configured — set LIVE_CAMERA_* in TRINETRAAI/backend/.env",
        )

    # Single status authority: the same resolver the grid/detail endpoints use.
    # A Sentinel camera is continuously published at the gateway, so a camera
    # that is merely not being ingested by a local AI worker is still ONLINE
    # and viewable — the browser's WHEP pull is what opens the feed. The live
    # worker status only overrides when it is actually delivering frames.
    resolved_status, _ = _resolve_camera_status(cam)
    status_value = (resolved_status or "OFFLINE").upper()
    playable = status_value == "ONLINE"
    slug = cam.camera_id.lower()

    # File-backed cameras (local demo feeds) play natively in the browser via
    # the backend's MJPEG live view — no WebRTC gateway involved.
    # Real-time OpenCV vehicle detection view: the backend decodes the same
    # source (RTSP/HLS/file) and streams annotated MJPEG. Same-origin path,
    # no credentials — the authenticated URL is built backend-side only.
    detection_url = (
        f"/api/cameras/{slug}/live/detect"
        if playable
        and settings.VEHICLE_DETECTION_ENABLED
        and can_decode_for_detection(cam.camera_id, cam.stream_type)
        else None
    )

    if playable and (cam.stream_type or "").lower() == "file":
        return CameraStreamTicket(
            camera_id=slug,
            stream_type="MJPEG",
            stream_url=f"/api/cameras/{slug}/live",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            playable=True,
            reason=None,
            detection_url=detection_url,
        )

    # Sentinel WHEP endpoint is /stream/<id>/whep on the gateway (integrator
    # guide §1). Behind the same-origin /sentinel proxy that becomes
    # /sentinel/stream/<id>/whep — the ticket must carry the FULL path or the
    # proxy forwards /<id>/whep and the gateway answers 404.
    from ..services.sentinel_stream_service import get_whep_path

    return CameraStreamTicket(
        camera_id=slug,
        stream_type="WEBRTC" if playable else (cam.stream_type or "hls").upper(),
        stream_url=get_whep_path(slug) if playable else "",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        playable=playable,
        reason=None if playable else f"Camera is {status_value}",
        detection_url=detection_url,
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
        _reject_embedded_stream_credentials(payload.stream_url)
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
        source = resolve_ingest_source(cam.camera_id, cam.stream_url, cam.stream_type)
        source_type = resolve_ingest_stream_type(cam.camera_id, cam.stream_url, cam.stream_type)
        camera_manager.add_camera(
            camera_id=cam.camera_id,
            source=source,
            source_type=source_type,
            auto_start=can_decode_for_detection(cam.camera_id, cam.stream_type),
        )

    return _safe_camera_response(cam)


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
    """Start one camera's secure background ingestion worker."""
    cam = db.query(Camera).filter(func.upper(Camera.camera_id) == camera_id.strip().upper()).first()
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    # Sentinel and env-configured live cameras resolve their private ingest URL
    # only at connection time. Never re-use the public registry reference when
    # an authenticated source has just been resolved.
    if not can_decode_for_detection(cam.camera_id, cam.stream_type):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This camera needs an RTSP/HLS/file ingest source for OpenCV. "
                "For WHEP/WebRTC viewing, set LIVE_CAMERA_INGEST_URL and LIVE_CAMERA_INGEST_TYPE server-side."
            ),
        )
    source = resolve_ingest_source(cam.camera_id, cam.stream_url, cam.stream_type)
    source_type = resolve_ingest_stream_type(cam.camera_id, cam.stream_url, cam.stream_type)
    stream = camera_manager.get_camera(cam.camera_id)
    if stream is None or stream.source != source or stream.source_type != source_type:
        # add_camera() stops a stale worker before replacing it, preventing two
        # decoder threads from reading the same authorized camera.
        camera_manager.add_camera(
            camera_id=cam.camera_id,
            source=source,
            source_type=source_type,
            auto_start=True,
        )
    else:
        camera_manager.start_camera(cam.camera_id)

    return {"status": "started", "camera_id": cam.camera_id}


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


@router.get("/{camera_id}/live/detect")
def live_detection_stream(camera_id: str, db: Session = Depends(get_db)):
    """
    Live MJPEG stream with real-time OpenCV vehicle detection (green boxes).

    Same source as ``/live``; frames are decoded backend-side (resident worker
    when running, otherwise on demand for this connection only), passed
    through the YOLO vehicle detector and annotated with OpenCV.
    """
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
    if not (cam.stream_url or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Camera source not configured.",
        )

    # Resolve the source the backend should decode. For Sentinel cameras this
    # is an authenticated RTSP URL built from environment credentials; for a
    # configured WHEP viewer it can be a paired server-side RTSP/HLS ingest
    # source. Nothing private is returned to the client.
    if not can_decode_for_detection(cam.camera_id, cam.stream_type):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This WHEP/WebRTC camera has no OpenCV ingest source configured. "
                "Set LIVE_CAMERA_INGEST_URL and LIVE_CAMERA_INGEST_TYPE server-side."
            ),
        )
    source = resolve_ingest_source(cam.camera_id, cam.stream_url, cam.stream_type)
    source_type = resolve_ingest_stream_type(cam.camera_id, cam.stream_url, cam.stream_type)
    existing = camera_manager.get_camera(cam.camera_id)
    if existing is None or (not existing.is_alive() and (existing.source != source or existing.source_type != source_type)):
        # Replace only an idle stale registration. An active worker already
        # owns the authenticated source and remains the single capture reader.
        camera_manager.add_camera(
            camera_id=cam.camera_id, source=source, source_type=source_type, auto_start=False,
        )

    return StreamingResponse(
        camera_manager.generate_mjpeg_stream(cam.camera_id, detect_vehicles=True),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
