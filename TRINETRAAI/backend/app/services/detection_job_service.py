"""
Detection job service — the standalone ``detection_backend`` server, merged in.

Owns the background video-detection jobs that the old standalone FastAPI app
(``detection_backend/server.py``) used to run on port 8010:

* upload (or point at) a video  → a queued job
* a worker thread runs the ``engine`` pipeline (YOLO11 detection + ByteTrack
  tracking + RapidOCR ANPR) with a semaphore of 2 concurrent pipelines
* job manifests persist as ``job.json`` inside each job directory so jobs
  survive a server restart

Everything lives under the unified backend (port 8000); the HTTP surface is in
``app/api/detection_jobs.py``.
"""
from __future__ import annotations

import json
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from ..core.logging_config import logger
from ..core.paths import BACKEND_ROOT, resolve_data_path

# The engine package keeps its own internal import style (``from detection...``,
# ``from tracking...``), exactly like the standalone server did: both the
# backend root and the engine root go on sys.path, once, here.
ENGINE_ROOT = BACKEND_ROOT / "engine"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from engine.pipeline.video_pipeline import (  # noqa: E402  (path bootstrap above)
    VideoAnalysisPipeline,
    find_model,
    probe_video,
)

# ---------------------------------------------------------------------------
# Data directories (single resolution authority: app.core.paths)
# ---------------------------------------------------------------------------


def jobs_dir(*, create: bool = True) -> Path:
    """Per-job output trees (manifest, evidence crops, annotated video, CSV)."""
    return resolve_data_path("detection_jobs", create=create)


def videos_dir(*, create: bool = True) -> Path:
    """Sample / CCTV footages the server can detect on without an upload."""
    return resolve_data_path("footages_and_videos", create=create)


_jobs_lock = threading.Lock()
_jobs: Dict[str, dict] = {}
_job_semaphore = threading.Semaphore(2)  # Allow up to 2 concurrent CV pipelines


def _save_job_manifest(job: dict) -> None:
    job_dir = Path(job.get("output_dir", ""))
    if job_dir.exists():
        try:
            with open(job_dir / "job.json", "w", encoding="utf-8") as f:
                json.dump(job, f, indent=2, ensure_ascii=False)
        except Exception as e:  # pragma: no cover - manifest is best-effort
            logger.debug(f"Failed to save job.json: {e}")


def _load_jobs() -> None:
    root = jobs_dir(create=False)
    if not root.exists():
        return
    for item in root.iterdir():
        if item.is_dir() and (item / "job.json").exists():
            try:
                with open(item / "job.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                _jobs[data["job_id"]] = data
            except Exception:  # pragma: no cover - corrupt manifest
                continue


_load_jobs()


def get_job(job_id: str) -> Optional[dict]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            return dict(job)
    manifest = jobs_dir(create=False) / job_id / "job.json"
    if manifest.exists():
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
            with _jobs_lock:
                _jobs[job_id] = data
            return dict(data)
        except Exception:  # pragma: no cover
            return None
    return None


def list_videos() -> list:
    videos = []
    for v in sorted(videos_dir().glob("*.mp4")):
        videos.append(
            {
                "filename": v.name,
                "path": str(v),
                "size_mb": round(v.stat().st_size / (1024 * 1024), 2),
            }
        )
    return videos


def create_job(
    *,
    filename: str,
    input_path: Path,
    sample_seconds: float = 0.0,
    target_fps: float = 5.0,
    job_dir: Optional[Path] = None,
) -> dict:
    """Register a job for an already-materialised input video and start it.

    ``job_dir`` lets the HTTP layer pre-create the directory (uploads write the
    video there first, so the worker never races a half-written file).
    """
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    job_id = f"job_{timestamp_str}_{uuid.uuid4().hex[:8]}"
    if job_dir is None:
        job_dir = jobs_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    job = {
        "job_id": job_id,
        "filename": filename,
        "input_path": str(input_path),
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

    worker = threading.Thread(
        target=_run_pipeline_job,
        args=(job_id,),
        daemon=True,
        name=f"Detection-{job_id}",
    )
    worker.start()
    return dict(job)


def save_upload(fileobj, dest: Path) -> None:
    """Fast 16 MB-chunk stream write of an uploaded video."""
    chunk_size = 16 * 1024 * 1024
    with open(dest, "wb") as buffer:
        shutil.copyfileobj(fileobj, buffer, length=chunk_size)


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
                    _jobs[job_id].update(
                        {
                            "stage": stage,
                            "progress_pct": min(100.0, pct),
                            "frames_total": total_frames,
                            "frames_processed": current_frame,
                            "vehicles_detected": stats.get("total_vehicle_detections", 0),
                            "plates_detected": stats.get("total_plate_detections", 0),
                            "ocr_reads": stats.get("total_ocr_reads", 0),
                            "elapsed_time_sec": elapsed,
                        }
                    )
            _save_job_manifest(_jobs[job_id])

        try:
            model_path = find_model()
            logger.info(
                f"[{job_id}] Running detection on {job['input_path']} with model {model_path}"
            )

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
                _jobs[job_id].update(
                    {
                        "status": "COMPLETED",
                        "stage": "COMPLETED",
                        "progress_pct": 100.0,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "elapsed_time_sec": round(time.time() - start_time, 1),
                        "vehicles_detected": summary.get("total_vehicle_detections", 0),
                        "plates_detected": summary.get("total_plate_detections", 0),
                        "total_sightings": summary.get("total_sightings", 0),
                        "unique_plates": summary.get("unique_plates", 0),
                    }
                )
                _save_job_manifest(_jobs[job_id])
            logger.info(f"[{job_id}] Detection completed in {round(time.time() - start_time, 1)}s")

        except Exception as e:
            logger.exception(f"[{job_id}] Pipeline execution failed: {e}")
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id].update(
                        {
                            "status": "FAILED",
                            "stage": "FAILED",
                            "error_message": str(e),
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    _save_job_manifest(_jobs[job_id])


__all__ = [
    "ENGINE_ROOT",
    "VideoAnalysisPipeline",
    "find_model",
    "probe_video",
    "jobs_dir",
    "videos_dir",
    "get_job",
    "list_videos",
    "create_job",
    "save_upload",
]
