#!/usr/bin/env python3
"""TRINETRA AI — deterministic video detection + ANPR CLI baseline.

Usage:
    python process_video.py <video> [--output output] [--sample N] [--no-annotated]

Produces, under ``output/``:

    annotated.mp4      the decoded video with the detector's boxes drawn
    detections.csv     one row per tracked vehicle sighting (real records)
    detections.json    the same records with full provenance, as JSON
    summary.json       decode/detection statistics
    evidence/          per-sighting full frame + vehicle crop + plate crop

This is the SAME pipeline the dashboard's Video Analysis page runs
(``app.services.video_analysis_core.analyze_video``), so the CLI output is a
trustworthy, frontend-independent baseline for what the dashboard persists.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_BACKEND_ROOT = _REPO_ROOT / "TRINETRAAI" / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import cv2  # noqa: E402


def _format_offset(seconds):
    if seconds is None:
        return "--:--:--"
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def probe(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise SystemExit(f"ERROR: cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    codec = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4)).strip() or "unknown"
    cap.release()
    return {
        "filename": os.path.basename(video_path),
        "codec": codec,
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frames,
        "duration_sec": frames / fps if fps > 0 else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TRINETRA AI — process one video end-to-end.")
    parser.add_argument("video", help="path to the video file")
    parser.add_argument("--output", "-o", default="output", help="output directory (default: output)")
    parser.add_argument("--sample", "-s", type=int, default=0,
                        help="only decode the first N frames (0 = whole video)")
    parser.add_argument("--conf", type=float, default=0.35, help="detection confidence threshold")
    parser.add_argument("--imgsz", type=int, default=960, help="detection inference size")
    parser.add_argument("--no-annotated", action="store_true", help="skip annotated.mp4")
    parser.add_argument("--no-ocr", action="store_true", help="skip the plate/OCR stage")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.is_file():
        raise SystemExit(f"ERROR: video not found: {video_path}")

    from app.core.config import settings
    from app.services.anpr_pipeline import read_plate_for_vehicle
    from app.services.ocr_service import ocr_service
    from app.services.vehicle_detection_service import vehicle_detection_service
    from app.services.video_analysis_core import analyze_video

    out_dir = Path(args.output)
    ev_dir = out_dir / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    ev_dir.mkdir(parents=True, exist_ok=True)

    # STEP 4 — decoder check: report what the file actually is before doing
    # anything else, so a decode failure is never mistaken for an OCR failure.
    meta = probe(str(video_path))
    print("=" * 70)
    print("  TRINETRA AI — process_video.py")
    print("=" * 70)
    print(f"  filename     : {meta['filename']}")
    print(f"  codec        : {meta['codec']}")
    print(f"  resolution   : {meta['width']}x{meta['height']}")
    print(f"  fps          : {meta['fps']}")
    print(f"  frame_count  : {meta['frame_count']}")
    print(f"  duration     : {meta['duration_sec']:.2f}s")
    print(f"  output       : {out_dir.resolve()}")
    print(f"  conf/imgsz   : {args.conf}/{args.imgsz}")
    print("=" * 70)

    # STEP 5 — model check.
    vehicle_detection_service._ensure_model()
    if vehicle_detection_service._model is None:
        print("  vehicle model : NOT LOADED — "
              f"{vehicle_detection_service._disabled_reason or 'unknown reason'}")
        print("  Aborting: no detector means no real boxes.")
        return 1
    model_path = getattr(vehicle_detection_service._model, "ckpt_path", None) or "?"
    print(f"  vehicle model : {model_path}")
    print(f"  device        : cpu")
    print(f"  classes       : {vehicle_detection_service._vehicle_classes}")

    ocr_ok = ocr_service.available
    print(f"  OCR engine    : {ocr_service.engine_name if ocr_ok else 'NONE (plates stay UNKNOWN)'}")

    def _detect(frame):
        return vehicle_detection_service.detect(frame, conf=args.conf, imgsz=args.imgsz)

    def _read_plate(frame, bbox, vehicle_class):
        if args.no_ocr:
            return None
        return read_plate_for_vehicle(frame, bbox, vehicle_class)

    # Annotated video writer (decoder fps; the CLI replays at source rate).
    writer = None
    if not args.no_annotated:
        writer = cv2.VideoWriter(
            str(out_dir / "annotated.mp4"),
            cv2.VideoWriter_fourcc(*"mp4v"),
            meta["fps"],
            (meta["width"], meta["height"]),
        )
        if not writer.isOpened():
            print("  WARNING: could not open annotated.mp4 writer — skipping annotation.")
            writer = None

    def _frame_sink(frame):
        if writer is not None:
            writer.write(frame)

    t0 = time.time()
    report = analyze_video(
        str(video_path),
        detect=_detect,
        read_plate=_read_plate,
        annotate=True,
        frame_sink=_frame_sink,
        max_frames=args.sample or None,
        progress_cb=lambda cur, total: print(
            f"\r  [{cur}/{total}] frames", end="", flush=True),
    )
    if writer is not None:
        writer.release()
    print()

    sightings = report.sightings

    # Evidence + records.
    csv_path = out_dir / "detections.csv"
    json_path = out_dir / "detections.json"
    summary_path = out_dir / "summary.json"
    records = []

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "detection_id", "video_filename", "frame_number", "timestamp",
            "track_id", "plate", "plate_confidence", "vehicle_confidence",
            "evidence_frame", "vehicle_class", "plate_status", "plate_raw",
            "vehicle_bbox", "plate_bbox", "evidence_vehicle", "evidence_plate",
        ]
        writer_csv = csv.DictWriter(f, fieldnames=fieldnames)
        writer_csv.writeheader()
        for i, s in enumerate(sightings, 1):
            det_id = i
            full_name = f"sighting_{det_id:02d}_full.jpg"
            veh_name = f"sighting_{det_id:02d}_vehicle.jpg"
            plt_name = f"sighting_{det_id:02d}_plate.jpg"
            if s.full_frame:
                (ev_dir / full_name).write_bytes(s.full_frame)
            else:
                full_name = ""
            if s.vehicle_crop:
                (ev_dir / veh_name).write_bytes(s.vehicle_crop)
            else:
                veh_name = ""
            if s.plate_crop:
                (ev_dir / plt_name).write_bytes(s.plate_crop)
            else:
                plt_name = ""

            row = {
                "detection_id": det_id,
                "video_filename": meta["filename"],
                "frame_number": s.frame_number,
                "timestamp": _format_offset(s.video_offset_sec),
                "track_id": s.track_id,
                "plate": s.plate_text or "",
                "plate_confidence": s.plate_confidence if s.plate_confidence is not None else "",
                "vehicle_confidence": s.vehicle_confidence,
                "evidence_frame": f"evidence/{full_name}" if full_name else "",
                "vehicle_class": s.vehicle_class,
                "plate_status": s.plate_status,
                "plate_raw": s.plate_raw or "",
                "vehicle_bbox": json.dumps(s.vehicle_bbox),
                "plate_bbox": json.dumps(s.plate_bbox) if s.plate_bbox else "",
                "evidence_vehicle": f"evidence/{veh_name}" if veh_name else "",
                "evidence_plate": f"evidence/{plt_name}" if plt_name else "",
            }
            writer_csv.writerow(row)
            records.append({
                **row,
                "video_offset_sec": s.video_offset_sec,
                "vehicle_bbox": s.vehicle_bbox,
                "plate_bbox": s.plate_bbox,
                "hits": s.hits,
            })

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    summary = {
        "video": meta,
        "frames_read": report.stats.frames_read,
        "frames_analyzed": report.stats.frames_analyzed,
        "vehicles_detected": report.stats.vehicles_detected,
        "plates_read": report.stats.plates_read,
        "unknown_plates": report.stats.unknown_plates,
        "sightings": len(sightings),
        "processing_time_sec": round(time.time() - t0, 2),
        "output_dir": str(out_dir.resolve()),
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Human-readable report.
    print("=" * 70)
    print("  RESULT")
    print("=" * 70)
    print(f"  frames read        : {report.stats.frames_read}")
    print(f"  frames analysed    : {report.stats.frames_analyzed}")
    print(f"  vehicles detected  : {report.stats.vehicles_detected}")
    print(f"  readable plates    : {report.stats.plates_read}")
    print(f"  unreadable         : {report.stats.unknown_plates}")
    print(f"  sightings          : {len(sightings)}")
    print(f"  processing time    : {time.time() - t0:.1f}s")
    print("-" * 70)
    for s in sightings:
        plate = s.plate_text or ("UNREADABLE" if s.plate_status == "UNKNOWN" else "(none)")
        print(f"  track #{s.track_id:>2}  frame {s.frame_number:>4}  "
              f"{_format_offset(s.video_offset_sec)}  {s.vehicle_class:<10} "
              f"veh_conf={s.vehicle_confidence:.2f}  plate={plate}")
    print("-" * 70)
    print(f"  annotated.mp4     : {out_dir / 'annotated.mp4'}")
    print(f"  detections.csv    : {csv_path}")
    print(f"  detections.json   : {json_path}")
    print(f"  summary.json      : {summary_path}")
    print(f"  evidence/         : {ev_dir}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
