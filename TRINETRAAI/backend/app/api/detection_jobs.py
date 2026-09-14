"""
Detection Jobs API — merged from the standalone ``detection_backend`` service.

    POST   /api/v1/detect/video                  — upload (or point at) a video, start a job
    GET    /api/v1/detect/jobs/{job_id}          — live status / progress
    GET    /api/v1/detect/jobs/{job_id}/results  — sightings + plate reads + evidence links
    GET    /api/v1/detect/jobs/{job_id}/csv      — CSV report download
    GET    /api/v1/detect/jobs/{job_id}/annotated— annotated MP4 download
    GET    /api/v1/detect/evidence/{job_id}/{f}  — evidence crop image
    POST   /api/v1/detect/frame                  — instant detection on a single image
    GET    /api/v1/videos                        — footages available on the server

Mounted under both /api and /api/v1 like every other router, so the old
standalone clients (sample_client, cli) keep working against port 8000.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from ..core.logging_config import logger
from ..services import detection_job_service as djs

router = APIRouter(prefix="/detect", tags=["Detection Jobs"])
footage_router = APIRouter(tags=["Footage"])


@footage_router.get("/videos", tags=["Footage"])
def list_available_videos():
    """List all sample and CCTV video footages available on the server."""
    videos = djs.list_videos()
    return {"videos": videos, "total": len(videos)}


@router.post("/video", status_code=status.HTTP_201_CREATED)
def detect_video(
    file: Optional[UploadFile] = File(None, description="Video file to upload and detect"),
    video_path: Optional[str] = Form(None, description="Or relative/absolute path to video file already on server"),
    sample_seconds: Optional[float] = Form(0.0, description="Process first N seconds (0 = full video, 15 = Turbo Mode)"),
    target_fps: Optional[float] = Form(5.0, description="Target analysis rate in FPS (default 5.0 for CCTV)"),
):
    """
    Start video detection & ANPR job on any uploaded or local footage.
    Returns the created job ID and initial status.
    """
    if not file and not video_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either a video file or a video_path must be provided.",
        )

    job_dir_parent = djs.jobs_dir()  # ensures the tree exists
    if file:
        # Land the upload in a shared uploads dir inside the (gitignored)
        # detection_jobs tree, then register the job around the finished file.
        upload_root = djs.jobs_dir() / "uploads"
        upload_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{stamp}_{os.path.basename(file.filename or 'upload.mp4')}"
        input_file_path = upload_root / filename
        stream = getattr(file, "file", file)
        djs.save_upload(stream, input_file_path)
        job = djs.create_job(
            filename=filename,
            input_path=input_file_path,
            sample_seconds=float(sample_seconds or 0.0),
            target_fps=float(target_fps or 5.0),
        )
        return _job_created_payload(job)

    # Local video path (relative to the footages dir or absolute)
    p = Path(video_path or "")
    if not p.is_absolute():
        p = (djs.videos_dir() / p).resolve()
        if not p.exists():
            p = (djs.videos_dir() / Path(video_path).name).resolve()
    if not p.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Video file not found: {video_path}")

    job = djs.create_job(
        filename=p.name,
        input_path=p,
        sample_seconds=float(sample_seconds or 0.0),
        target_fps=float(target_fps or 5.0),
    )
    return _job_created_payload(job)


def _job_created_payload(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "filename": job["filename"],
        "status": job["status"],
        "stage": job["stage"],
        "sample_seconds": job["sample_seconds"],
        "target_fps": job["target_fps"],
        "created_at": job["created_at"],
        "message": "Video queued for detection. Use GET /api/v1/detect/jobs/{job_id} to monitor progress.",
    }


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Get real-time status, progress stage, and frame metrics for a job."""
    job = djs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return job


@router.get("/jobs/{job_id}/results")
def get_job_results(job_id: str):
    """Retrieve full vehicle sightings and detected plate reads for a completed job."""
    job = get_job_status(job_id)
    job_dir = Path(job["output_dir"])

    sightings_file = job_dir / "vehicle_sightings.json"
    summary_file = job_dir / "summary.json"

    if not sightings_file.exists():
        if job.get("status") == "PROCESSING":
            return {"status": "PROCESSING", "sightings": [], "message": "Job is still processing."}
        if job.get("status") == "QUEUED":
            return {"status": "QUEUED", "sightings": [], "message": "Job is queued."}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Results not found for this job.")

    with open(sightings_file, "r", encoding="utf-8") as f:
        sightings = json.load(f)

    summary = {}
    if summary_file.exists():
        with open(summary_file, "r", encoding="utf-8") as f:
            summary = json.load(f)

    formatted_sightings = []
    for s in sightings:
        s_id = s.get("sighting_id", 1)
        v_crop = f"/api/v1/detect/evidence/{job_id}/sighting_{s_id:02d}_vehicle.jpg"
        p_crop = f"/api/v1/detect/evidence/{job_id}/sighting_{s_id:02d}_plate.jpg"
        f_crop = f"/api/v1/detect/evidence/{job_id}/sighting_{s_id:02d}.jpg"

        formatted_sightings.append(
            {
                "sighting_id": s_id,
                "track_id": s.get("track_ids", [1])[0] if s.get("track_ids") else s.get("track_id", 1),
                "vehicle_class": s.get("vehicle_class", "car"),
                "plate_number": s.get("final_plate") or s.get("final_plate_raw") or "UNKNOWN",
                "plate_confidence": round(float(s.get("plate_confidence", 0.0) or 0.0), 3),
                "detection_confidence": round(float(s.get("detection_confidence", 0.0) or 0.0), 3),
                "start_time": s.get("timestamp_str") or s.get("start_timestamp", "00:00.00"),
                "duration_sec": round(float(s.get("duration", s.get("duration_sec", 0.0)) or 0.0), 2),
                "evidence_urls": {
                    "vehicle_image": v_crop if (job_dir / "evidence" / f"sighting_{s_id:02d}_vehicle.jpg").exists() else None,
                    "plate_image": p_crop if (job_dir / "evidence" / f"sighting_{s_id:02d}_plate.jpg").exists() else None,
                    "full_frame": f_crop if (job_dir / "evidence" / f"sighting_{s_id:02d}.jpg").exists() else None,
                },
            }
        )

    return {
        "job_id": job_id,
        "filename": job["filename"],
        "status": job["status"],
        "total_sightings": len(formatted_sightings),
        "unique_plates": job.get("unique_plates", 0),
        "summary": summary,
        "sightings": formatted_sightings,
    }


@router.get("/jobs/{job_id}/csv")
def download_job_csv(job_id: str):
    """Download vehicle sightings report in CSV format."""
    job = get_job_status(job_id)
    csv_path = Path(job["output_dir"]) / "vehicle_sightings.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV report not generated.")
    return FileResponse(str(csv_path), media_type="text/csv", filename=f"{job_id}_sightings.csv")


@router.get("/jobs/{job_id}/annotated")
def stream_annotated_video(job_id: str):
    """Stream annotated MP4 video with bounding boxes & plate overlays."""
    job = get_job_status(job_id)
    video_path = Path(job["output_dir"]) / "annotated_video.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotated video not found.")
    return FileResponse(str(video_path), media_type="video/mp4", filename=f"{job_id}_annotated.mp4")


@router.get("/evidence/{job_id}/{filename}")
def get_evidence_image(job_id: str, filename: str):
    """Serve vehicle crop or license plate evidence frame."""
    job = get_job_status(job_id)
    img_path = Path(job["output_dir"]) / "evidence" / filename
    if img_path.exists():
        return FileResponse(str(img_path), media_type="image/jpeg")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Evidence image '{filename}' not found.")


@router.post("/frame")
def detect_single_frame(
    file: UploadFile = File(..., description="Image frame (JPEG, PNG) to detect vehicles and license plates on"),
):
    """
    Run instant YOLO detection and OCR on a single image frame.
    Useful for live camera snapshots or still photos.
    """
    from engine.anpr.ocr import RapidOcrEngine
    from engine.detection.vehicle_detector import VehicleDetector

    try:
        contents = file.file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid image file: {e}")

    model_path = djs.find_model()
    detector = VehicleDetector(model_path=model_path, device="cpu")
    all_classes = detector.class_ids + detector.plate_class_ids
    detections = detector.detect(img, classes=all_classes)

    vehicles = [d for d in detections if d.class_id in detector.class_ids]
    plates = [d for d in detections if d.class_id in detector.plate_class_ids]

    ocr = RapidOcrEngine()
    detected_plates_data = []
    for p in plates:
        x1, y1, x2, y2 = [int(v) for v in p.bbox]
        crop = img[max(0, y1):min(img.shape[0], y2), max(0, x1):min(img.shape[1], x2)]
        lines = ocr.read(crop) if crop.size > 0 else []
        text = lines[0].text if lines else None
        conf = lines[0].confidence if lines else 0.0
        detected_plates_data.append(
            {
                "bbox": p.bbox,
                "confidence": round(p.confidence, 3),
                "plate_text": text,
                "ocr_confidence": round(conf, 3),
            }
        )

    return {
        "filename": file.filename,
        "width": img.shape[1],
        "height": img.shape[0],
        "vehicle_count": len(vehicles),
        "plate_count": len(plates),
        "vehicles": [
            {"bbox": v.bbox, "class_name": v.class_name, "confidence": round(v.confidence, 3)}
            for v in vehicles
        ],
        "plates": detected_plates_data,
    }
