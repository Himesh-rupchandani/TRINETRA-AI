"""
TRINETRA AI — Standalone Detection CLI Runner.

Run vehicle detection and license plate recognition directly on any video from the terminal.

Usage:
  python cli.py --video footages_and_videos/detection1video.mp4 --sample 15 --output results/my_run
  python cli.py --video footages_and_videos/VID_20260907_113743_faculty_parking.mp4 --fps 5.0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))
if str(_here / "engine") not in sys.path:
    sys.path.insert(0, str(_here / "engine"))

from engine.pipeline.video_pipeline import VideoAnalysisPipeline, find_model, probe_video


def main():
    parser = argparse.ArgumentParser(
        description="TRINETRA AI — Run YOLO11 vehicle detection & ANPR on any video file.",
    )
    parser.add_argument(
        "--video",
        "-v",
        required=True,
        help="Path to video file (.mp4, .avi, .mov, .mkv, .webm)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="results",
        help="Directory to save results, CSV, JSON, and crops (default: results)",
    )
    parser.add_argument(
        "--sample",
        "-s",
        type=float,
        default=0.0,
        help="Process first N seconds of video (0.0 = full video, 15.0 = Turbo Mode)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=5.0,
        help="Target frame rate for surveillance analysis (default: 5.0 FPS)",
    )
    parser.add_argument(
        "--no-annotated",
        action="store_true",
        help="Skip annotated video generation for maximum speed",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=None,
        help="Optional custom model path (defaults to models/best.pt)",
    )

    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.exists():
        cand = _here / "footages_and_videos" / video_path.name
        if cand.exists():
            video_path = cand
        else:
            print(f"Error: Video file not found at {args.video}", file=sys.stderr)
            sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = args.model or find_model(_here)
    print(f"\n=======================================================")
    print(f"  TRINETRA AI — STANDALONE DETECTION PIPELINE")
    print(f"=======================================================")
    print(f"  Video:      {video_path}")
    print(f"  Output Dir: {out_dir}")
    print(f"  Model:      {model_path}")
    print(f"  Sample Sec: {args.sample if args.sample > 0 else 'Full Video'}")
    print(f"  Target FPS: {args.fps}")
    print(f"=======================================================\n")

    t0 = time.time()

    def progress(stage, frame_idx, total_frames, stats):
        pct = (frame_idx / total_frames * 100) if total_frames > 0 else 0
        veh = stats.get("total_vehicle_detections", 0)
        ocr = stats.get("total_ocr_reads", 0)
        print(f"\r[{stage:24s}] {pct:5.1f}% | Frame {frame_idx}/{total_frames} | Vehicles: {veh} | OCR: {ocr}", end="", flush=True)

    pipeline = VideoAnalysisPipeline(
        video_path=str(video_path),
        output_dir=str(out_dir),
        progress_callback=progress,
        config={"FRAME_SKIP": 4, "TARGET_FPS": args.fps},
    )

    summary = pipeline.process_video(
        model_path=model_path,
        max_seconds=args.sample,
        generate_annotated=not args.no_annotated,
    )

    dur = time.time() - t0
    print(f"\n\n=======================================================")
    print(f"  DETECTION & ANPR COMPLETE ({dur:.1f}s)")
    print(f"=======================================================")
    print(f"  Vehicles Detected: {summary.get('total_vehicle_detections', 0)}")
    print(f"  Plates Detected:   {summary.get('total_plate_detections', 0)}")
    print(f"  Total Sightings:   {summary.get('total_sightings', 0)}")
    print(f"  Unique Plates:     {summary.get('unique_plates', 0)}")
    print(f"  Output CSV:        {out_dir / 'vehicle_sightings.csv'}")
    print(f"  Output JSON:       {out_dir / 'vehicle_sightings.json'}")
    if not args.no_annotated:
        print(f"  Annotated Video:   {out_dir / 'annotated_video.mp4'}")
    print(f"  Evidence Crops:    {out_dir / 'evidence'}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
