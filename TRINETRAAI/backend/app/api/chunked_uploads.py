"""
Chunked upload endpoints — the fix for Vercel's 413 "Request Entity Too Large".

Client flow:
  1. POST /api/uploads/chunks/init        -> { upload_id, chunk_size }
  2. For each chunk (1..N):
       POST /api/uploads/chunks/{upload_id}   (multipart: chunk_number, chunk)
       If response.done == true, proceed.
  3. POST /api/uploads/chunks/{upload_id}/complete   -> finalizes + returns
     whatever the original single-shot endpoint would have returned:
        - for source=upload   -> UploadedVideoResponse  (registers camera + starts job)
        - for source=analysis -> batch add response    (registers VideoSource rows)

Small files (< chunk_size) can still be POSTed the old way — these endpoints
are additive. The frontend picks chunked automatically for any file bigger
than ~3 MB so users never see the 413 again.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from ..core.logging_config import logger
from ..database.database import get_db
from ..database.models import Camera, VehicleEvent, VideoSource
from ..services import chunked_upload as cu
from ..services import uploaded_video_service as uvs
from ..services import video_analysis_service as vas
from ..core.vision import require_vision
try:
    _413 = status.HTTP_413_CONTENT_TOO_LARGE
except AttributeError:  # pragma: no cover
    _413 = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

router = APIRouter(prefix="/uploads", tags=["Uploads (chunked)"])


@router.post("/chunks/init")
async def init_chunk_upload(request: Request):
    """Begin a chunked upload session. Returns the id the client will tag
    subsequent chunks with, plus the recommended chunk size."""
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Invalid form: {exc}")

    def _str(k, default=None):
        v = form.get(k)
        if v is None:
            return default
        s = str(v).strip()
        return s or default

    def _int(k, default=0):
        v = form.get(k)
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return default

    def _bool(k, default=False):
        v = form.get(k)
        if v is None:
            return default
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    filename = _str("filename")
    if not filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="filename is required.")
    total_chunks = _int("total_chunks")
    total_size = _int("total_size")
    source = _str("source", "upload")

    if source not in ("upload", "analysis"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail='source must be "upload" or "analysis".')
    sess = cu.init_session(
        filename=filename,
        total_chunks=total_chunks,
        total_size=total_size,
        source=source,
        camera_id=_str("camera_id"),
        name=_str("name"),
        location=_str("location"),
        camera_ids_csv=_str("camera_ids"),
        batch_id=_str("batch_id"),
        auto_start=_bool("auto_start", False),
    )
    return {
        "upload_id": sess.upload_id,
        "chunk_size": cu.CHUNK_SIZE_BYTES,
        "total_chunks": sess.total_chunks,
        "total_size": sess.total_size,
    }


@router.post("/chunks/{upload_id}")
async def upload_chunk(upload_id: str, request: Request):
    """Append one chunk (0-based, in order) to the upload session."""
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Invalid form: {exc}")

    def _int(k, default=-1):
        v = form.get(k)
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return default

    chunk_number = _int("chunk_number", -1)
    if chunk_number < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="chunk_number is required.")
    chunk_file = form.get("chunk")
    if not isinstance(chunk_file, UploadFile):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="chunk file is required.")
    data = await chunk_file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty chunk.")
    if len(data) > cu.CHUNK_SIZE_BYTES + 1024 * 1024:  # +1 MB grace for FormData overhead
        raise HTTPException(_413, detail="Chunk too large — split further on the client.")
    progress = cu.append_chunk(upload_id, int(chunk_number), data)
    return progress


@router.post("/chunks/{upload_id}/abort")
def abort_chunk_upload(upload_id: str):
    cu.abort(upload_id)
    return {"aborted": upload_id}


@router.post("/chunks/{upload_id}/complete")
def complete_chunk_upload(upload_id: str, db: Session = Depends(get_db)):
    """Assemble chunks and finalize the upload into the correct domain model."""
    sess = cu.get_session(upload_id)
    path = cu.finalize_upload(upload_id)

    if sess.source == "upload":
        return _complete_single_upload(sess, path, db)
    return _complete_analysis_upload(sess, path, db)


# --------------------------------------------------------------------- helpers


def _summary(cam: Camera) -> dict:
    job = uvs.get_job(cam.camera_id)
    return {
        "camera_id": cam.camera_id,
        "name": cam.name,
        "location": cam.location,
        "video_file": cam.stream_url.split("/")[-1] if cam.stream_url else "",
        "status": cam.status or "OFFLINE",
        **job,
    }


def _complete_single_upload(sess, path, db: Session):
    """Single-video CCTV upload path (mirrors api/uploads.py::upload_video)."""
    cam_id_in = sess.camera_id or uvs.next_camera_id(db)
    try:
        cam_id = uvs.normalise_camera_id(cam_id_in)
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    display_name = (sess.name or "").strip() or cam_id
    place = (sess.location or "").strip() or f"Uploaded Feed — {path.name}"

    import os
    from sqlalchemy import func

    cam = db.query(Camera).filter(func.upper(Camera.camera_id) == cam_id).first()
    if cam:
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
        if old and old != str(path) and old.startswith(str(uvs.upload_dir())):
            try:
                os.remove(old)
            except OSError:
                pass
        db.query(VehicleEvent).filter(
            func.upper(VehicleEvent.camera_id) == cam_id,
            VehicleEvent.video_file.isnot(None),
        ).delete(synchronize_session=False)
        db.commit()
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

    from ..camera.manager import camera_manager
    camera_manager.add_camera(
        camera_id=cam.camera_id,
        source=cam.stream_url,
        source_type="file",
        auto_start=False,
    )
    job = uvs.start_processing(cam.camera_id)
    return {**_summary(cam), **job}


def _complete_analysis_upload(sess, path, db: Session):
    """Multi-video analysis path (mirrors api/video_analysis.py::upload_videos
    but for a single already-on-disk file, which is what chunked assembly
    delivers)."""
    import uuid
    # Chunked multi-upload path is driven one-file-at-a-time from the client
    # (one upload_id per file), so we register exactly one video per complete.
    batch = (sess.batch_id or "").strip() or uuid.uuid4().hex[:12]
    explicit = [c.strip() for c in (sess.camera_ids_csv or "").split(",") if c.strip()]
    camera_id = explicit[0] if explicit else None
    try:
        # register_from_path is added below; it takes an already-saved file
        # instead of raw bytes, keeping the RAM footprint tiny.
        video = vas.register_from_path(
            db, path=path, source_name=sess.filename,
            batch_id=batch, camera_id=camera_id,
        )
    except vas.AnalysisError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    added = [vas.video_to_dict(video)]
    errors = []
    if sess.auto_start:
        try:
            vas.start_analysis(db, [video.video_id])
        except vas.AnalysisError as exc:
            errors.append({"source_name": "*", "error": str(exc)})
    return {"batch_id": batch, "added": added, "errors": errors}
