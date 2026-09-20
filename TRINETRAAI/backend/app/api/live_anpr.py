"""Browser frame ingress for WHEP/HLS feeds; heavy inference stays off the API loop."""
from io import BytesIO
import asyncio
from weakref import WeakKeyDictionary
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..core.resource_budget import inference_budget
from ..core.vision import cv2, np, require_vision
from ..database.database import get_db
from ..database.models import Camera
from ..services.live_anpr_service import live_anpr_service

router = APIRouter(prefix="/cameras", tags=["Live ANPR"])
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_FRAME_PIXELS = 1920 * 1920
# Serialize image decompression per ASGI loop without occupying all threadpool
# slots needed by MJPEG playback. Queued JPEG bodies remain compressed.
_decode_gates = WeakKeyDictionary()


def decode_gate():
    loop = asyncio.get_running_loop()
    gate = _decode_gates.get(loop)
    if gate is None:
        gate = _decode_gates[loop] = asyncio.Semaphore(1)
    return gate


def registered_camera(camera_id: str, db: Session) -> Camera:
    camera = db.query(Camera).filter(func.upper(Camera.camera_id) == camera_id.strip().upper()).first()
    if camera is None:
        raise HTTPException(404, "Camera not found.")
    return camera


def decode_frame(body: bytes):
    # Check the JPEG header BEFORE allocating the decoded image. A tiny
    # compressed body can otherwise expand into an enormous image in memory.
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(BytesIO(body)) as image:
            if image.format != "JPEG":
                raise HTTPException(415, "Send a JPEG camera frame.")
            if image.width * image.height > MAX_FRAME_PIXELS:
                raise HTTPException(413, "Frame resolution too large; sample at 1280 pixels.")
        frame = cv2.imdecode(np.frombuffer(body, dtype=np.uint8), cv2.IMREAD_COLOR)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, "Invalid JPEG frame.")
    if frame is None or frame.size == 0:
        raise HTTPException(400, "Invalid JPEG frame.")
    return frame


@router.post("/{camera_id}/detect-frame", dependencies=[Depends(require_vision)])
async def detect_frame(
    camera_id: str,
    request: Request,
    client_id: str = Query("browser", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"),
    media_time: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
    db: Session = Depends(get_db),
):
    """Accept one sampled frame and return the last fresh, shared ANPR result.

    No blocking inference or unbounded job queue. ``accepted=false`` means the
    sample was throttled/at capacity; playback should continue unchanged.
    """
    camera = registered_camera(camera_id, db)
    if not (camera.stream_url or "").strip():
        raise HTTPException(409, "Camera source not configured.")
    if not live_anpr_service.enabled:
        raise HTTPException(503, "Live ANPR is disabled on the backend.")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "image/jpeg":
        raise HTTPException(415, "Send the sampled frame as image/jpeg.")
    source_id = f"browser:{client_id}"
    budget = inference_budget()
    delay = live_anpr_service.admission_delay(camera.camera_id, source_id)
    if not budget["allowed"] or delay:
        result = live_anpr_service.snapshot(camera.camera_id, source_id=source_id)
        if delay and result["status"] == "IDLE":
            result.update(status="BUSY", reason="ANPR is at capacity; video continues.")
        return {**result, "accepted": False, "retry_after_ms": max(delay, budget["retry_after_ms"])}
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_FRAME_BYTES:
            raise HTTPException(413, "Frame exceeds the 2 MB limit.")
        body.extend(chunk)
    async with decode_gate():
        # Resource pressure may have changed while waiting for the decode slot.
        if not inference_budget()["allowed"]:
            return {**live_anpr_service.snapshot(camera.camera_id, source_id=source_id), "accepted": False}
        frame = await run_in_threadpool(decode_frame, bytes(body))
    accepted = live_anpr_service.submit(camera.camera_id, frame, source_id=source_id, media_time=media_time)
    result = live_anpr_service.snapshot(camera.camera_id, source_id=source_id)
    if not accepted and result["status"] == "IDLE":
        result.update(status="BUSY", reason="ANPR camera limit reached; retrying without interrupting video.")
    return {**result, "accepted": accepted}


@router.get("/{camera_id}/anpr", dependencies=[Depends(require_vision)])
def anpr_status(camera_id: str, db: Session = Depends(get_db)):
    """Lightweight state/box poll for a backend-rendered MJPEG camera."""
    camera = registered_camera(camera_id, db)
    return live_anpr_service.snapshot(camera.camera_id)


@router.get("/{camera_id}/anpr/photos/{capture_id}/{track_id}/{kind}.jpg", dependencies=[Depends(require_vision)])
def detection_photo(
    camera_id: str, capture_id: UUID, kind: Literal["vehicle", "plate"],
    track_id: int = Path(..., ge=1), db: Session = Depends(get_db),
):
    """Short-lived actual detector crop; no filesystem path supplied by clients."""
    camera = registered_camera(camera_id, db)
    image = live_anpr_service.photo(camera.camera_id, capture_id.hex, track_id, kind)
    if image is None:
        raise HTTPException(404, "This temporary capture has expired; wait for the next detection. Saved evidence remains in the Vehicle Log.")
    return Response(content=image, media_type="image/jpeg", headers={
        "Cache-Control": "private, max-age=30", "X-Content-Type-Options": "nosniff",
    })
