"""
TRINETRA AI — Standalone Detection Backend API.

Zero UI dependencies. Exposes pure REST endpoints for external web, mobile,
or desktop UIs to perform vehicle detection, ByteTrack tracking, and ANPR on video footage.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# Add detection_backend root and engine to sys.path
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))
if str(_here / "engine") not in sys.path:
    sys.path.insert(0, str(_here / "engine"))

from engine.pipeline.video_pipeline import VideoAnalysisPipeline, find_model, probe_video
from engine.detection.vehicle_detector import VehicleDetector
from engine.anpr.ocr import RapidOcrEngine
from engine.anpr.normalizer import candidate_from_ocr_text, plate_format_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("detection_backend.server")

app = FastAPI(
    title="TRINETRA AI — Vehicle & ANPR Detection Engine API",
    description=(
        "Pure computer vision and ANPR backend service for integration with any external UI. "
        "Provides on-the-fly YOLO11 vehicle detection, ByteTrack vehicle tracking, RapidOCR "
        "license plate recognition, and padded evidence frame extraction."
    ),
    version="2.0.0",
)

# Allow all CORS origins so any frontend (React, Vue, mobile, Flutter) can communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS_DIR = _here / "jobs"
VIDEOS_DIR = _here / "footages_and_videos"
EVIDENCE_DIR = _here / "evidence_frames"
JOBS_DIR.mkdir(exist_ok=True)
VIDEOS_DIR.mkdir(exist_ok=True)
EVIDENCE_DIR.mkdir(exist_ok=True)

_jobs_lock = threading.Lock()
_jobs: Dict[str, dict] = {}
_job_semaphore = threading.Semaphore(2)  # Allow up to 2 concurrent CV pipelines


def _save_job_manifest(job: dict) -> None:
    job_dir = Path(job.get("output_dir", ""))
    if job_dir.exists():
        try:
            with open(job_dir / "job.json", "w", encoding="utf-8") as f:
                json.dump(job, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Failed to save job.json: {e}")


def _load_jobs() -> None:
    for item in JOBS_DIR.iterdir():
        if item.is_dir() and (item / "job.json").exists():
            try:
                with open(item / "job.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    _jobs[data["job_id"]] = data
            except Exception:
                pass


_load_jobs()


def _run_pipeline_job(job_id: str):
    with _job_semaphore:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job["status"] = "PROCESSING"
            job["stage"] = "PROCESSING"
            job["started_at"] = datetime.now(timezone.utc).isoformat()
        _save_job_manifest(job)

        start_time = time.time()

        def on_progress(stage: str, current_frame: int, total_frames: int, stats: dict):
            elapsed = round(time.time() - start_time, 1)
            pct = round((current_frame / total_frames * 100), 1) if total_frames > 0 else 0.0
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id].update({
                        "stage": stage,
                        "progress_pct": min(100.0, pct),
                        "frames_total": total_frames,
                        "frames_processed": current_frame,
                        "vehicles_detected": stats.get("total_vehicle_detections", 0),
                        "plates_detected": stats.get("total_plate_detections", 0),
                        "ocr_reads": stats.get("total_ocr_reads", 0),
                        "elapsed_time_sec": elapsed,
                    })
            _save_job_manifest(_jobs[job_id])

        try:
            model_path = find_model(_here)
            logger.info(f"[{job_id}] Running detection on {job['input_path']} with model {model_path}")

            target_fps = float(job.get("target_fps", 5.0) or 5.0)
            pipeline = VideoAnalysisPipeline(
                video_path=job["input_path"],
                output_dir=job["output_dir"],
                progress_callback=on_progress,
                config={"FRAME_SKIP": 4, "TARGET_FPS": target_fps},
            )

            sample_sec = float(job.get("sample_seconds", 0.0) or 0.0)
            summary = pipeline.process_video(
                model_path=model_path,
                max_seconds=sample_sec,
                generate_annotated=True,
            )

            with _jobs_lock:
                _jobs[job_id].update({
                    "status": "COMPLETED",
                    "stage": "COMPLETED",
                    "progress_pct": 100.0,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "elapsed_time_sec": round(time.time() - start_time, 1),
                    "vehicles_detected": summary.get("total_vehicle_detections", 0),
                    "plates_detected": summary.get("total_plate_detections", 0),
                    "total_sightings": summary.get("total_sightings", 0),
                    "unique_plates": summary.get("unique_plates", 0),
                })
                _save_job_manifest(_jobs[job_id])
            logger.info(f"[{job_id}] Detection completed in {round(time.time() - start_time, 1)}s")

        except Exception as e:
            logger.exception(f"[{job_id}] Pipeline execution failed: {e}")
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id].update({
                        "status": "FAILED",
                        "stage": "FAILED",
                        "error_message": str(e),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    _save_job_manifest(_jobs[job_id])


# ─────────────────────────────────────────────────────────────
# REST API Endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint to verify detection backend status."""
    return {
        "status": "ok",
        "service": "TRINETRA AI Detection Backend",
        "version": "2.0.0",
        "models_available": [m.name for m in (_here / "models").glob("*.pt")],
        "footages_available": len(list(VIDEOS_DIR.glob("*.mp4"))),
    }


@app.get("/api/v1/videos", tags=["Footage"])
def list_available_videos():
    """List all sample and CCTV video footages available on the server."""
    videos = []
    for v in sorted(VIDEOS_DIR.glob("*.mp4")):
        size_mb = round(v.stat().st_size / (1024 * 1024), 2)
        videos.append({
            "filename": v.name,
            "path": str(v),
            "size_mb": size_mb,
        })
    return {"videos": videos, "total": len(videos)}


@app.post("/api/v1/detect/video", status_code=status.HTTP_201_CREATED, tags=["Detection"])
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

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    job_id = f"job_{timestamp_str}_{uuid.uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_file_path = None

    if file:
        filename = os.path.basename(file.filename or "upload.mp4")
        input_file_path = job_dir / filename
        # Fast 16MB stream write
        chunk_size = 16 * 1024 * 1024
        stream = getattr(file, "file", file)
        with open(input_file_path, "wb") as buffer:
            shutil.copyfileobj(stream, buffer, length=chunk_size)
    else:
        # Local video path
        p = Path(video_path or "")
        if not p.is_absolute():
            p = (_here / p).resolve()
            if not p.exists():
                p = (VIDEOS_DIR / Path(video_path).name).resolve()
        if not p.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Video file not found: {video_path}")
        filename = p.name
        input_file_path = p

    job = {
        "job_id": job_id,
        "filename": filename,
        "input_path": str(input_file_path),
        "output_dir": str(job_dir),
        "status": "QUEUED",
        "stage": "QUEUED",
        "progress_pct": 0.0,
        "frames_total": 0,
        "frames_processed": 0,
        "vehicles_detected": 0,
        "plates_detected": 0,
        "ocr_reads": 0,
        "elapsed_time_sec": 0.0,
        "sample_seconds": float(sample_seconds or 0.0),
        "target_fps": float(target_fps or 5.0),
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
    }

    with _jobs_lock:
        _jobs[job_id] = job
    _save_job_manifest(job)

    # Start detection in background worker thread
    worker = threading.Thread(
        target=_run_pipeline_job,
        args=(job_id,),
        daemon=True,
        name=f"Detection-{job_id}",
    )
    worker.start()

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


@app.get("/api/v1/detect/jobs/{job_id}", tags=["Detection"])
def get_job_status(job_id: str):
    """Get real-time status, progress stage, and frame metrics for a job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            return dict(job)

    manifest = JOBS_DIR / job_id / "job.json"
    if manifest.exists():
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
                with _jobs_lock:
                    _jobs[job_id] = data
                return dict(data)
        except Exception:
            pass

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")


@app.get("/api/v1/detect/jobs/{job_id}/results", tags=["Detection"])
def get_job_results(job_id: str):
    """Retrieve full vehicle sightings and detected plate reads for a completed job."""
    job = get_job_status(job_id)
    job_dir = Path(job["output_dir"])

    sightings_file = job_dir / "vehicle_sightings.json"
    summary_file = job_dir / "summary.json"

    if not sightings_file.exists():
        if job.get("status") == "PROCESSING":
            return {"status": "PROCESSING", "sightings": [], "message": "Job is still processing."}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Results not found for this job.")

    with open(sightings_file, "r", encoding="utf-8") as f:
        sightings = json.load(f)

    summary = {}
    if summary_file.exists():
        with open(summary_file, "r", encoding="utf-8") as f:
            summary = json.load(f)

    # Format sightings for external UI consumption with relative evidence links
    formatted_sightings = []
    for s in sightings:
        s_id = s.get("sighting_id", 1)
        v_crop = f"/api/v1/detect/evidence/{job_id}/sighting_{s_id:02d}_vehicle.jpg"
        p_crop = f"/api/v1/detect/evidence/{job_id}/sighting_{s_id:02d}_plate.jpg"
        f_crop = f"/api/v1/detect/evidence/{job_id}/sighting_{s_id:02d}.jpg"

        formatted_sightings.append({
            "sighting_id": s_id,
            "track_id": s.get("track_ids", [1])[0] if s.get("track_ids") else s.get("track_id", 1),
            "vehicle_class": s.get("vehicle_class", "car"),
            "plate_number": s.get("final_plate") or s.get("final_plate_raw") or "UNKNOWN",
            "plate_confidence": round(float(s.get("plate_confidence", 0.0) or 0.0), 3),
            "detection_confidence": round(float(s.get("detection_confidence", 0.0) or 0.0), 3),
            "start_time": s.get("timestamp_str") or s.get("start_timestamp", "00:00.00"),
            "duration_sec": round(float(s.get("duration", s.get("duration_sec", 0.0)) or 0.0), 2),
            "evidence_urls": {
                "vehicle_image": v_crop if (job_dir / f"evidence/sighting_{s_id:02d}_vehicle.jpg").exists() else None,
                "plate_image": p_crop if (job_dir / f"evidence/sighting_{s_id:02d}_plate.jpg").exists() else None,
                "full_frame": f_crop if (job_dir / f"evidence/sighting_{s_id:02d}.jpg").exists() else None,
            },
        })

    return {
        "job_id": job_id,
        "filename": job["filename"],
        "status": job["status"],
        "total_sightings": len(formatted_sightings),
        "unique_plates": job.get("unique_plates", 0),
        "summary": summary,
        "sightings": formatted_sightings,
    }


@app.get("/api/v1/detect/jobs/{job_id}/csv", tags=["Detection"])
def download_job_csv(job_id: str):
    """Download vehicle sightings report in CSV format."""
    job = get_job_status(job_id)
    csv_path = Path(job["output_dir"]) / "vehicle_sightings.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV report not generated.")
    return FileResponse(
        str(csv_path),
        media_type="text/csv",
        filename=f"{job_id}_sightings.csv",
    )


@app.get("/api/v1/detect/jobs/{job_id}/annotated", tags=["Detection"])
def stream_annotated_video(job_id: str):
    """Stream annotated MP4 video with bounding boxes & plate overlays."""
    job = get_job_status(job_id)
    video_path = Path(job["output_dir"]) / "annotated_video.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotated video not found.")
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=f"{job_id}_annotated.mp4",
    )


@app.get("/api/v1/detect/evidence/{job_id}/{filename}", tags=["Evidence"])
def get_evidence_image(job_id: str, filename: str):
    """Serve vehicle crop or license plate evidence frame."""
    # Check job directory first
    job = get_job_status(job_id)
    img_path = Path(job["output_dir"]) / "evidence" / filename
    if img_path.exists():
        return FileResponse(str(img_path), media_type="image/jpeg")

    # Fallback to evidence_frames benchmark directory
    for subdir in EVIDENCE_DIR.iterdir():
        if subdir.is_dir() and (subdir / filename).exists():
            return FileResponse(str(subdir / filename), media_type="image/jpeg")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Evidence image '{filename}' not found.")


@app.post("/api/v1/detect/frame", tags=["Single Frame"])
def detect_single_frame(
    file: UploadFile = File(..., description="Image frame (JPEG, PNG) to detect vehicles and license plates on"),
):
    """
    Run instant YOLO detection and OCR on a single image frame.
    Useful for live camera snapshots or still photos.
    """
    try:
        contents = file.file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid image file: {e}")

    model_path = find_model(_here)
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
        detected_plates_data.append({
            "bbox": p.bbox,
            "confidence": round(p.confidence, 3),
            "plate_text": text,
            "ocr_confidence": round(conf, 3),
        })

    return {
        "filename": file.filename,
        "width": img.shape[1],
        "height": img.shape[0],
        "vehicle_count": len(vehicles),
        "plate_count": len(plates),
        "vehicles": [
            {
                "bbox": v.bbox,
                "class_name": v.class_name,
                "confidence": round(v.confidence, 3),
            }
            for v in vehicles
        ],
        "plates": detected_plates_data,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8010))
    print(f"\n=======================================================")
    print(f"  TRINETRA AI — DETECTION BACKEND API SERVER")
    print(f"  Server URL:  http://localhost:{port}")
    print(f"  API Docs:    http://localhost:{port}/docs")
    print(f"=======================================================\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
