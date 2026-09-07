#!/usr/bin/env python3
"""
TRINETRA cv-engine — recorded-video ANPR analysis (Faculty Parking demo runner).

Runs the REAL CV pipeline over a REAL video file and produces distinct vehicle
SIGHTINGS (not per-frame detections), plate readings validated by multi-frame
OCR voting, evidence images, an annotated video and backend-ready events.

    # 25-second sample first (Phase 2 of the brief)
    python scripts/analyze_video_file.py /path/faculty_parking.mp4 \
        --location "Faculty Parking" --camera-id faculty_parking \
        --sample 25 --output-dir ../outputs/faculty_parking_sample

    # full run
    python scripts/analyze_video_file.py /path/faculty_parking.mp4 \
        --location "Faculty Parking" --camera-id faculty_parking \
        --output-dir ../outputs/faculty_parking

The same command works for any other Rajkot location video — nothing in the
pipeline is specific to one clip.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CV_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CV_ROOT))

from pipeline.video_pipeline import VideoAnalysisPipeline, VideoPipelineConfig  # noqa: E402
from sightings.reporting import (  # noqa: E402
    ReportContext,
    build_events,
    build_target_report,
    plate_summary,
    write_evidence,
    write_json,
    write_sightings,
)

def _find_model(filename: str) -> Path:
    """
    Locate a weights file without hard-coding one machine's layout.

    Search order: $TRINETRA_MODELS_DIR, cv-engine/models_dev (git-ignored dev
    cache), TRINETRAAI/backend/models, ~/models. Falls back to the bare name so
    Ultralytics can resolve it from its own cache when present.
    """
    candidates = []
    env_dir = os.environ.get("TRINETRA_MODELS_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / filename)
    candidates += [
        CV_ROOT / "models_dev" / filename,
        CV_ROOT.parent / "TRINETRAAI" / "backend" / "models" / filename,
        Path.home() / "models" / filename,
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path(filename)


DEFAULT_VEHICLE_MODEL = _find_model("yolo11n.pt")
DEFAULT_PLATE_MODEL = _find_model("license_plate_detector.pt")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Analyse a recorded video for vehicle sightings")
    p.add_argument("video", type=Path, nargs="?", default=None,
                   help="local video file (omit when using --drive-url)")
    p.add_argument("--drive-url", default=None,
                   help="public Google Drive link; downloaded via the backend's "
                        "existing gdrive_service before analysis")
    p.add_argument("--download-dir", type=Path, default=CV_ROOT / "samples")
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--video-id", default=None)
    p.add_argument("--camera-id", default=None)
    p.add_argument("--location", default="Unknown")
    p.add_argument("--latitude", type=float, default=None)
    p.add_argument("--longitude", type=float, default=None)

    p.add_argument("--vehicle-model", type=Path, default=DEFAULT_VEHICLE_MODEL)
    p.add_argument("--plate-model", type=Path, default=DEFAULT_PLATE_MODEL)
    p.add_argument("--no-plate-model", action="store_true",
                   help="disable the plate detector and fall back to heuristic crops")
    p.add_argument("--device", default="cpu")

    p.add_argument("--frame-skip", type=int, default=2)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--conf", type=float, default=0.35, dest="detection_confidence")
    p.add_argument("--plate-conf", type=float, default=0.25)
    p.add_argument("--plate-imgsz", type=int, default=320)
    p.add_argument("--min-plate-width", type=int, default=26)
    p.add_argument("--min-vehicle-area", type=int, default=3000)
    p.add_argument("--ocr-interval-ms", type=float, default=400.0)
    p.add_argument("--max-ocr-per-frame", type=int, default=2)
    p.add_argument("--max-reads-per-track", type=int, default=14)
    p.add_argument("--min-ocr-conf", type=float, default=0.30)

    p.add_argument("--track-max-age", type=float, default=1.2)
    p.add_argument("--track-min-hits", type=int, default=2)
    p.add_argument("--track-iou", type=float, default=0.25)
    p.add_argument("--track-end-gap", type=float, default=2.0,
                   help="TRACK_END_GAP_SECONDS: close a sighting after this silence")
    p.add_argument("--sighting-cooldown", type=float, default=3.0,
                   help="SIGHTING_COOLDOWN_SECONDS: re-appearance inside this gap = same sighting")
    p.add_argument("--min-sighting-frames", type=int, default=3)
    p.add_argument("--min-sighting-duration", type=float, default=0.3)
    p.add_argument("--plate-reject-threshold", type=float, default=0.60)
    p.add_argument("--min-agree-reads", type=int, default=2)

    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--sample", type=float, default=None,
                   help="shortcut for --duration (sample-mode run)")
    p.add_argument("--no-annotate", action="store_true")
    p.add_argument("--target-sightings", type=int, default=5)
    p.add_argument("--ocr-engine", choices=["rapidocr", "easyocr"], default="rapidocr")
    p.add_argument("--log-level", default="INFO")
    return p


def configure_logging(log_file: Path, level: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s :: %(message)s", datefmt="%H:%M:%S"
    )
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def overlay_sighting_markers(src: Path, dst: Path, markers: list, location: str) -> bool:
    """
    Second pass (no inference): stamp "SIGHTING #n" on the frames belonging to
    the target vehicle's sighting windows. Only real, detected sightings are
    ever drawn.
    """
    import cv2

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        cap.release()
        return False

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        # This pass reads the ANNOTATED video, whose own timeline starts at 0
        # and advances at its own fps; map back to source seconds.
        t = idx / fps
        for m in markers:
            if m["start_sec"] - 0.2 <= t <= m["end_sec"] + 0.8:
                text = f"SIGHTING #{m['sighting_number']}  {m['timestamp']}  {m['plate']}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                x, y = 12, h - 18
                cv2.rectangle(frame, (x - 8, y - th - 12), (x + tw + 12, y + 10), (0, 0, 0), -1)
                cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 220, 255), 2, cv2.LINE_AA)
                break
        writer.write(frame)
        idx += 1
    cap.release()
    writer.release()
    return True


def fetch_from_drive(url: str, dest_dir: Path) -> Path:
    """
    Download a public Drive video by REUSING the backend's gdrive_service
    (same link parsing, virus-scan interstitial handling and error messages the
    upload UI already uses). Raises RuntimeError with an actionable message.
    """
    backend_root = CV_ROOT.parent / "TRINETRAAI" / "backend"
    sys.path.insert(0, str(backend_root))
    try:
        from app.services.gdrive_service import DriveError, download
    except Exception as exc:  # pragma: no cover - depends on backend deps
        raise RuntimeError(
            f"backend gdrive_service unavailable ({exc}). Install the backend "
            f"requirements or download the video manually and pass its path."
        ) from exc

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        path, _name = download(url, dest_dir)
    except DriveError as exc:
        raise RuntimeError(f"Google Drive download failed: {exc}") from exc
    except Exception as exc:  # network/proxy failures surface honestly
        raise RuntimeError(f"Google Drive download failed: {exc}") from exc
    return Path(path)


def main() -> int:
    args = build_parser().parse_args()

    if args.drive_url:
        print(f"downloading from Google Drive: {args.drive_url}")
        try:
            args.video = fetch_from_drive(args.drive_url, args.download_dir)
            print(f"downloaded → {args.video}")
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
    if args.video is None:
        print("ERROR: provide a video path or --drive-url", file=sys.stderr)
        return 2

    video = args.video.expanduser().resolve()
    if not video.exists():
        print(f"ERROR: video not found: {video}", file=sys.stderr)
        return 2

    video_id = args.video_id or video.stem
    camera_id = args.camera_id or video_id
    out_dir = (args.output_dir or (CV_ROOT.parent / "outputs" / video_id)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(out_dir / "logs" / "processing.log", args.log_level)
    log = logging.getLogger("analyze_video_file")

    duration = args.sample if args.sample is not None else args.duration
    plate_model = None if args.no_plate_model else str(args.plate_model)
    if plate_model and not Path(plate_model).exists():
        log.warning("plate model %s not found — falling back to heuristic crops", plate_model)
        plate_model = None

    cfg = VideoPipelineConfig(
        video_id=video_id,
        camera_id=camera_id,
        location_name=args.location,
        latitude=args.latitude,
        longitude=args.longitude,
        vehicle_model=str(args.vehicle_model),
        plate_model=plate_model,
        device=args.device,
        frame_skip=args.frame_skip,
        inference_imgsz=args.imgsz,
        detection_confidence=args.detection_confidence,
        track_max_age_sec=args.track_max_age,
        track_min_hits=args.track_min_hits,
        track_iou_threshold=args.track_iou,
        plate_confidence=args.plate_conf,
        plate_imgsz=args.plate_imgsz,
        min_plate_width_px=args.min_plate_width,
        min_vehicle_area_px=args.min_vehicle_area,
        ocr_interval_ms=args.ocr_interval_ms,
        max_ocr_per_frame=args.max_ocr_per_frame,
        max_reads_per_track=args.max_reads_per_track,
        min_ocr_confidence=args.min_ocr_conf,
        track_end_gap_sec=args.track_end_gap,
        sighting_cooldown_sec=args.sighting_cooldown,
        min_sighting_frames=args.min_sighting_frames,
        min_sighting_duration_sec=args.min_sighting_duration,
        plate_reject_threshold=args.plate_reject_threshold,
        plate_min_agree_reads=args.min_agree_reads,
        start_sec=args.start,
        duration_sec=duration,
        annotate=not args.no_annotate,
    )

    ocr_engine = None
    if args.ocr_engine == "easyocr":
        from anpr.ocr import OcrEngine

        ocr_engine = OcrEngine(gpu=(args.device != "cpu"))

    raw_annotated = out_dir / "annotated_raw.mp4"
    pipe = VideoAnalysisPipeline(
        str(video), cfg,
        ocr_engine=ocr_engine,
        annotated_path=str(raw_annotated) if cfg.annotate else None,
    )

    t0 = time.perf_counter()
    sightings = pipe.run()
    wall = time.perf_counter() - t0

    ctx = ReportContext(
        video_id=video_id,
        camera_id=camera_id,
        location_name=args.location,
        latitude=args.latitude,
        longitude=args.longitude,
        reject_threshold=args.plate_reject_threshold,
        min_agree_reads=args.min_agree_reads,
    )
    write_evidence(sightings, out_dir / "evidence")
    rows = write_sightings(sightings, ctx, out_dir)
    events = build_events(sightings, ctx)
    write_json(out_dir / "events.json", events)
    target = build_target_report(rows, target_count=args.target_sightings)
    write_json(out_dir / "target_vehicle_report.json", target)

    # Sighting markers for the target vehicle (Phase 15) — only real events.
    annotated_final = out_dir / "annotated_video.mp4"
    if cfg.annotate and raw_annotated.exists():
        markers = [
            {
                "sighting_number": s["sighting_number"],
                "start_sec": s["start_sec"] - cfg.start_sec,
                "end_sec": s["end_sec"] - cfg.start_sec,
                "timestamp": s["timestamp"],
                "plate": target.get("plate") or "",
            }
            for s in target.get("sightings", [])
        ]
        if markers and overlay_sighting_markers(raw_annotated, annotated_final, markers, args.location):
            raw_annotated.unlink(missing_ok=True)
        else:
            raw_annotated.replace(annotated_final)

    probe = pipe.probe.to_dict() if pipe.probe else {}
    src_stats = getattr(pipe, "source_stats", None)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "video_file": str(video),
        "video_id": video_id,
        "camera_id": camera_id,
        "location_name": args.location,
        "video_duration_sec": probe.get("duration_sec_measured") or probe.get("duration_sec_reported"),
        "video_resolution": probe.get("resolution"),
        "fps_reported": probe.get("fps_reported"),
        "actual_fps_measured": probe.get("fps_measured"),
        "codec_fourcc": probe.get("fourcc"),
        "analysis_window": {"start_sec": cfg.start_sec, "duration_sec": cfg.duration_sec},
        "frames_read": pipe.stats.frames_read,
        "total_frames_processed": pipe.stats.frames_processed,
        "total_vehicle_detections": pipe.stats.detections,
        "unique_tracks": pipe.stats.tracks_created,
        "sightings_total": len(rows),
        "sightings_with_validated_plate": sum(1 for r in rows if r["plate_status"] == "DETECTED"),
        "unique_plate_candidates": len({
            c["plate"] for r in rows for c in r["plate_candidates"]
        }),
        "validated_unique_plates": len(plate_summary(rows)),
        "plate_counts": plate_summary(rows),
        "target_vehicle": target.get("plate"),
        "target_sighting_count": target.get("total_sightings"),
        "target_exact_match": target.get("found"),
        "processing_time_sec": round(wall, 2),
        "processing_realtime_factor": (
            round((probe.get("duration_sec_measured") or 0) / wall, 3) if wall else None
        ),
        "pipeline_stats": pipe.stats.to_dict(),
        "capture_stats": src_stats.to_dict() if src_stats else None,
        "config": {
            k: (str(v) if isinstance(v, Path) else v) for k, v in cfg.__dict__.items()
        },
        "models": {
            "vehicle_detector": str(args.vehicle_model),
            "plate_detector": plate_model,
            "ocr_engine": args.ocr_engine,
        },
        "environment": {
            "python": platform.python_version(),
            "device": args.device,
            "cpu_count": __import__("os").cpu_count(),
        },
    }
    write_json(out_dir / "summary.json", summary)

    # ---------------------------------------------------------------- report
    print("\n" + "=" * 62)
    print(f"VIDEO           : {video.name}")
    print(f"DURATION        : {summary['video_duration_sec']}s   RESOLUTION: {summary['video_resolution']}")
    print(f"FPS (measured)  : {summary['actual_fps_measured']}   CODEC: {summary['codec_fourcc']}")
    print(f"FRAMES PROCESSED: {pipe.stats.frames_processed}  (frame_skip={cfg.frame_skip})")
    print(f"DETECTIONS      : {pipe.stats.detections}")
    print(f"UNIQUE TRACKS   : {pipe.stats.tracks_created}")
    print(f"SIGHTINGS       : {len(rows)}  (validated plate: {summary['sightings_with_validated_plate']})")
    print(f"PROCESSING      : {summary['processing_time_sec']}s")
    print("-" * 62)
    print("PLATE → SIGHTINGS")
    for p in plate_summary(rows):
        print(f"  {p['plate']:<14} → {p['sightings']} sighting(s)   max_conf={p['max_confidence']}")
    print("-" * 62)
    if target.get("found"):
        print(f"TARGET VEHICLE  : {target['plate']}  ({target['total_sightings']} sightings)")
    else:
        print(f"TARGET VEHICLE  : {target.get('note')}")
    for s in target.get("sightings", []):
        print(
            f"  SIGHTING {s['sighting_number']}  t={s['timestamp']}  track={s['track_id']} "
            f"conf={s['plate_confidence']}  frames={s['supporting_frame_count']}  "
            f"evidence={s['evidence_ref']}"
        )
    print("=" * 62)
    print(f"outputs → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
