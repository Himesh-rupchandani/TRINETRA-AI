"""
Real-Time Webcam or RTSP Stream Vehicle & Plate Detection.
Usage:
    python detect_webcam.py                 # Uses default webcam (0)
    python detect_webcam.py --source 1      # Uses secondary camera
    python detect_webcam.py --source "rtsp://..." # Uses RTSP camera stream
"""
from __future__ import annotations

import time
import argparse
from pathlib import Path
import cv2
import numpy as np

from core.detector import VehiclePlateDetector
from core.visualizer import Visualizer


def main():
    parser = argparse.ArgumentParser(description="Trinetra AI Live Webcam Detection")
    parser.add_argument("--source", default="0", help="Camera index (0, 1) or video/RTSP URL")
    parser.add_argument("--model", default="models/best.pt", help="Path to YOLO weights")
    parser.add_argument("--conf", type=float, default=0.35,
                        help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45,
                        help="NMS IoU threshold (double-box suppression)")
    parser.add_argument("--imgsz", type=int, default=960,
                        help="Inference image size. 960 matches the offline video pass "
                             "so the LIVE view is not coarser than the recording; drop "
                             "to 640 on a weak CPU (fewer distant vehicles, same tight "
                             "boxes for the ones it finds)")
    parser.add_argument("--vehicle-model", default=None,
                        help="Per-class weight for VEHICLE boxes ('none' = keep --model)")
    parser.add_argument("--no-display", action="store_true",
                        help="Do not open a window (auto-enabled when OpenCV has no GUI; "
                             "a headless server must not crash just because nobody is looking)")
    parser.add_argument("--save", default=None, metavar="OUT.mp4",
                        help="Also write the annotated live frames to this video file")
    parser.add_argument("--max-frames", type=int, default=0,
                        help="Stop after N frames (0 = run until 'q' / end of stream)")
    args = parser.parse_args()

    # Determine camera source
    src = int(args.source) if args.source.isdigit() else args.source

    base_dir = Path(__file__).resolve().parent
    model_path = str((base_dir / args.model).resolve())

    print("=" * 65)
    print("  TRINETRA AI - Live Camera Stream Detection")
    print("=" * 65)
    print("=" * 65)
    print("  TRINETRA AI - Live Camera Stream Detection")
    print("=" * 65)
    print(f"  Source     : {src}")
    print(f"  Model      : {model_path}")
    print(f"  Confidence : {args.conf}")
    print(f"  NMS IoU    : {args.iou}")
    print(f"  Img size   : {args.imgsz}")

    detector = VehiclePlateDetector(
        model_path=model_path,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
        imgsz=args.imgsz,
        vehicle_model_path=args.vehicle_model,
    )

    # Reported after construction: which weight the vehicle boxes actually come
    # from is only known once the detector has inspected each model's classes.
    print(f"  Vehicle wt : {detector.vehicle_model_path or model_path}")
    print("  Controls   : Press 'q' to Quit | Press 's' to Save Snapshot")
    print("=" * 65)

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        print(f"Error: Could not open camera source {src}")
        return

    show = not args.no_display
    if show:
        try:
            cv2.imshow("Trinetra AI - Live Vehicle & Plate Detection",
                       np.zeros((64, 64, 3), dtype=np.uint8))
            cv2.waitKey(1)
        except Exception:
            show = False
            print("[Notice] No display available: running headless (no window).")
    writer = None
    if args.save:
        out_path = Path(args.save).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc,
                                 float(cap.get(cv2.CAP_PROP_FPS) or 25.0),
                                 (int(cap.get(3)), int(cap.get(4))))

    output_dir = base_dir / "outputs" / "annotated_frames"
    output_dir.mkdir(parents=True, exist_ok=True)

    prev_time = time.time()
    fps = 0.0
    frames_seen = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame from stream.")
            break

        # Calculate FPS
        curr_time = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(1e-5, (curr_time - prev_time)))
        prev_time = curr_time

        detections = detector.detect(frame, conf=args.conf, imgsz=args.imgsz)
        vehicles = detector.filter_by_class(detections, "vehicle")
        plates = detector.filter_by_class(detections, "number_plate")

        annotated = Visualizer.draw_detections(frame, detections)
        info = f"FPS: {fps:.1f} | Vehicles: {len(vehicles)} | Plates: {len(plates)}"
        annotated = Visualizer.draw_banner(annotated, title="TRINETRA AI LIVE", info_text=info)

        if writer is not None:
            writer.write(annotated)
        if show:
            cv2.imshow("Trinetra AI - Live Vehicle & Plate Detection", annotated)

        key = cv2.waitKey(1) & 0xFF if show else 0xFF
        frames_seen += 1
        if args.max_frames and frames_seen >= args.max_frames:
            break
        if key == ord('q'):
            break
        elif key == ord('s'):
            snap_file = output_dir / f"webcam_snap_{int(time.time())}.jpg"
            cv2.imwrite(str(snap_file), annotated)
            print(f"[Snapshot Saved] {snap_file.name}")

    cap.release()
    if writer is not None:
        writer.release()
        print(f"[Saved] annotated live stream -> {args.save}")
    if show:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
