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

from core.detector import VehiclePlateDetector
from core.visualizer import Visualizer


def main():
    parser = argparse.ArgumentParser(description="Trinetra AI Live Webcam Detection")
    parser.add_argument("--source", default="0", help="Camera index (0, 1) or video/RTSP URL")
    parser.add_argument("--model", default="models/best.pt", help="Path to YOLO weights")
    parser.add_argument("--conf", type=float, default=0.30, help="Confidence threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    args = parser.parse_args()

    # Determine camera source
    src = int(args.source) if args.source.isdigit() else args.source

    base_dir = Path(__file__).resolve().parent
    model_path = str((base_dir / args.model).resolve())

    print("=" * 65)
    print("  TRINETRA AI - Live Camera Stream Detection")
    print("=" * 65)
    print(f"  Source     : {src}")
    print(f"  Model      : {model_path}")
    print(f"  Confidence : {args.conf}")
    print("  Controls   : Press 'q' to Quit | Press 's' to Save Snapshot")
    print("=" * 65)

    detector = VehiclePlateDetector(model_path=model_path, conf_threshold=args.conf)

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        print(f"Error: Could not open camera source {src}")
        return

    output_dir = base_dir / "outputs" / "annotated_frames"
    output_dir.mkdir(parents=True, exist_ok=True)

    prev_time = time.time()
    fps = 0.0

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

        cv2.imshow("Trinetra AI - Live Vehicle & Plate Detection", annotated)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            snap_file = output_dir / f"webcam_snap_{int(time.time())}.jpg"
            cv2.imwrite(str(snap_file), annotated)
            print(f"[Snapshot Saved] {snap_file.name}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
