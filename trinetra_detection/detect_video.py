"""
Run Vehicle and Number Plate Detection on Video files.
Generates:
  1. Annotated output video
  2. Cropped license plate images in outputs/detected_plates/
  3. Key annotated frames in outputs/annotated_frames/
  4. Terminal summary of detected plates and vehicles
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import Optional
import cv2
from tqdm import tqdm

from core.detector import VehiclePlateDetector
from core.visualizer import Visualizer


def run_video_detection(
    video_path: str,
    model_path: str,
    output_video: str,
    plates_dir: str,
    frames_dir: str,
    conf: float = 0.35,
    stride: int = 2,
    max_frames: int = None,
    iou: float = 0.45,
    imgsz: int = 960,
    vehicle_model: Optional[str] = None,
):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    os.makedirs(plates_dir, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_video)), exist_ok=True)

    print("=" * 70)
    print("  TRINETRA AI - Vehicle & Number Plate Video Inference")
    print("=" * 70)
    print(f"  Input Video  : {video_path}")
    print(f"  Model Weights: {model_path}")
    print(f"  Confidence   : {conf}")
    print(f"  NMS IoU      : {iou}")
    print(f"  Inference size: {imgsz}")
    print(f"  Frame Stride : {stride}")
    print("=" * 70)

    detector = VehiclePlateDetector(
        model_path=model_path,
        conf_threshold=conf,
        iou_threshold=iou,
        imgsz=imgsz,
        vehicle_model_path=vehicle_model,
    )
    print(f"  Vehicle Weights: {detector.vehicle_model_path or model_path} "
          f"(classes: {list(detector.vehicle_model.names.values()) if detector.vehicle_class_ids is None else ['car', 'motorcycle', 'bus', 'truck']})")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video file: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_fps = fps / stride

    print(f"Video Info   : {width}x{height} @ {fps:.1f} fps | {total_frames} total frames ({total_frames / fps:.1f}s)")
    frames_to_process = total_frames if max_frames is None else min(total_frames, max_frames)
    print(f"Processing   : {frames_to_process // stride} frames...\n")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_writer = cv2.VideoWriter(output_video, fourcc, out_fps, (width, height))

    frame_idx = 0
    processed_count = 0
    total_vehicles = 0
    total_plates = 0
    plate_detections = []
    saved_frames_count = 0

    pbar = tqdm(total=frames_to_process // stride, desc="Processing Video")

    while True:
        ret, frame = cap.read()
        if not ret or frame_idx >= frames_to_process:
            break

        if frame_idx % stride == 0:
            timestamp_sec = frame_idx / fps
            detections = detector.detect(frame, conf=conf, imgsz=imgsz)

            vehicles = detector.filter_by_class(detections, "vehicle")
            plates = detector.filter_by_class(detections, "number_plate")

            total_vehicles += len(vehicles)
            total_plates += len(plates)

            # Crop and save plates
            for p in plates:
                plate_crop = p.crop(frame)
                crop_filename = f"plate_f{frame_idx:05d}_conf{int(p.confidence * 100)}.jpg"
                crop_path = os.path.join(plates_dir, crop_filename)
                if plate_crop.size > 0:
                    cv2.imwrite(crop_path, plate_crop)

                plate_detections.append({
                    "frame": frame_idx,
                    "time_sec": timestamp_sec,
                    "conf": p.confidence,
                    "bbox": p.bbox,
                    "crop_filename": crop_filename,
                })

            # Draw visualizer boxes
            annotated = Visualizer.draw_detections(frame, detections)
            info = f"Frame: {frame_idx} | Time: {timestamp_sec:.1f}s | Vehicles: {len(vehicles)} | Plates: {len(plates)}"
            annotated = Visualizer.draw_banner(annotated, title="TRINETRA AI", info_text=info)

            # Save key sample annotated frames when plates are detected
            if len(plates) > 0 and saved_frames_count < 30 and frame_idx % 30 == 0:
                snap_path = os.path.join(frames_dir, f"detected_frame_{frame_idx:05d}.jpg")
                cv2.imwrite(snap_path, annotated)
                saved_frames_count += 1

            out_writer.write(annotated)
            processed_count += 1
            pbar.update(1)

        frame_idx += 1

    cap.release()
    out_writer.release()
    pbar.close()

    print("\n" + "=" * 70)
    print("  DETECTION COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print(f"  Frames Processed        : {processed_count}")
    print(f"  Total Vehicle Detections: {total_vehicles}")
    print(f"  Total Plate Detections  : {total_plates}")
    print(f"  Output Video Saved      : {output_video}")
    print(f"  Cropped Plates Saved    : {plates_dir} ({len(plate_detections)} crops)")
    print(f"  Annotated Frames Saved  : {frames_dir} ({saved_frames_count} snapshots)")
    print("=" * 70)

    # Print top detected plates
    if plate_detections:
        print("\nTop Detected Number Plates (Sorted by Confidence):")
        print("-" * 70)
        sorted_plates = sorted(plate_detections, key=lambda x: -x["conf"])
        for p in sorted_plates[:15]:
            m = int(p['time_sec'] // 60)
            s = p['time_sec'] % 60
            print(f"  Frame {p['frame']:5d} ({m:02d}:{s:04.1f}) | Conf: {p['conf']:.2f} | Crop: {p['crop_filename']} | Box: {p['bbox']}")
        print("-" * 70)


def main():
    parser = argparse.ArgumentParser(description="Run Trinetra AI Detection on a video")
    parser.add_argument("--video", required=True, help="Path to input video file")
    parser.add_argument("--model", default="models/best.pt", help="Path to YOLO weights")
    parser.add_argument("--output-video", default="outputs/annotated_video.mp4", help="Output annotated video path")
    parser.add_argument("--plates-dir", default="outputs/detected_plates", help="Directory to save cropped plates")
    parser.add_argument("--frames-dir", default="outputs/annotated_frames", help="Directory to save sample frames")
    parser.add_argument("--conf", type=float, default=0.35,
                        help="Confidence threshold (default 0.35: below this the "
                             "model's boxes are mostly background guesses)")
    parser.add_argument("--iou", type=float, default=0.45,
                        help="NMS IoU threshold (default 0.45: suppresses double boxes "
                             "on one vehicle while keeping neighbouring vehicles separate)")
    parser.add_argument("--imgsz", type=int, default=960,
                        help="Inference resolution (default 960; 640 merges parked "
                             "vehicles into one box and misses distant ones)")
    parser.add_argument("--vehicle-model", default=None,
                        help="Per-class weight used for VEHICLE boxes (default: auto — "
                             "the repo's yolo11s/yolo11n COCO weight). Pass 'none' to "
                             "keep vehicle boxes from --model.")
    parser.add_argument("--stride", type=int, default=2, help="Frame stride (default 2)")
    parser.add_argument("--max-frames", type=int, default=None, help="Max frames to process (optional)")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    video_path = str((base_dir / args.video).resolve()) if not os.path.isabs(args.video) else args.video
    model_path = str((base_dir / args.model).resolve()) if not os.path.isabs(args.model) else args.model
    output_video = str((base_dir / args.output_video).resolve()) if not os.path.isabs(args.output_video) else args.output_video
    plates_dir = str((base_dir / args.plates_dir).resolve()) if not os.path.isabs(args.plates_dir) else args.plates_dir
    frames_dir = str((base_dir / args.frames_dir).resolve()) if not os.path.isabs(args.frames_dir) else args.frames_dir

    run_video_detection(
        video_path=video_path,
        model_path=model_path,
        output_video=output_video,
        plates_dir=plates_dir,
        frames_dir=frames_dir,
        conf=args.conf,
        stride=args.stride,
        max_frames=args.max_frames,
        iou=args.iou,
        imgsz=args.imgsz,
        vehicle_model=args.vehicle_model,
    )


if __name__ == "__main__":
    main()
