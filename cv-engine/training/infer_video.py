#!/usr/bin/env python3
"""Run the trained pipeline on a traffic video and write an annotated MP4.

    python training/infer_video.py \\
        --video feeds/reference_traffic.mp4 \\
        --weights models/trained/vehicles/best.pt \\
        --plate-weights models/trained/plates/best.pt \\
        --out training/runs/infer_reference.mp4

Overlay per vehicle:
    CAR  #17  0.92
    Plate: GJ01AB1234
    (or Plate: Unknown  when OCR is below the reject threshold)

Never invents a plate. Uses the same tracker + normalizer as production.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from common import (
    REFERENCE_VIDEO,
    RUNS,
    TRAINED_PLATE,
    TRAINED_VEHICLE,
    ensure_dirs,
)


def _draw(frame, tracks, plates: dict) -> np.ndarray:
    out = frame.copy()
    live = [t for t in tracks if getattr(t, "time_since_update_ms", 0) == 0]
    for t in live:
        x1, y1, x2, y2 = (int(v) for v in t.bbox)
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        info = plates.get(t.track_id) or {}
        plate = info.get("plate")
        conf = info.get("confidence")
        if plate:
            plate_line = f"Plate: {plate}"
            if conf is not None:
                plate_line += f"  {conf * 100:.0f}%"
        else:
            plate_line = "Plate: Unknown"
        label = f"{t.class_name.upper()} #{t.track_id} {t.confidence:.2f}"
        y = y1 - 8 if y1 > 40 else y2 + 18
        cv2.putText(out, label, (x1, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
        cv2.putText(out, plate_line, (x1, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1, cv2.LINE_AA)
    h, w = out.shape[:2]
    cv2.rectangle(out, (0, 0), (w, 28), (15, 18, 24), -1)
    cv2.putText(
        out,
        f"TRINETRA trained detector | vehicles {len(live)}",
        (10, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, default=REFERENCE_VIDEO)
    ap.add_argument("--weights", default=str(TRAINED_VEHICLE if TRAINED_VEHICLE.is_file() else "yolo11s.pt"))
    ap.add_argument("--plate-weights", default=str(TRAINED_PLATE) if TRAINED_PLATE.is_file() else "")
    ap.add_argument("--out", type=Path, default=RUNS / "infer_reference.mp4")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--iou", type=float, default=0.50)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--skip", type=int, default=1, help="process every Nth frame")
    ap.add_argument("--max-frames", type=int, default=0, help="0 = whole video")
    ap.add_argument("--no-ocr", action="store_true")
    args = ap.parse_args()
    ensure_dirs()

    if not args.video.is_file():
        raise SystemExit(f"video not found: {args.video}")

    from anpr.normalizer import candidate_from_ocr_text, plate_format_score
    from anpr.ocr import RapidOcrEngine
    from anpr.plate_detector import plate_crops_for_vehicle, preprocess_for_ocr, reset_plate_model_cache
    from detection.vehicle_detector import VehicleDetector
    from tracking.vehicle_tracker import VehicleTracker

    if args.plate_weights:
        reset_plate_model_cache()
        # Force the plate singleton to this path on first use.
        import os
        os.environ["PLATE_MODEL_PATH"] = args.plate_weights

    detector = VehicleDetector(
        model_path=args.weights,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        iou_threshold=args.iou,
        prefer_trained=False,  # honour --weights exactly
    )
    detector.warmup()
    tracker = VehicleTracker(max_age_sec=1.5, min_hits=2, iou_threshold=0.25)
    ocr = None if args.no_ocr else RapidOcrEngine()

    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(args.out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    plates: dict = {}
    idx = 0
    pts = 0.0
    interval = 1000.0 / max(fps, 1.0)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if args.max_frames and idx >= args.max_frames:
            break
        pts = idx * interval
        if idx % max(1, args.skip) == 0:
            dets = detector.detect(frame, camera_id="eval", pts_ms=pts)
            tracks = tracker.update(dets, pts_ms=pts)
            if ocr is not None:
                for t in tracks:
                    if t.time_since_update_ms != 0:
                        continue
                    if t.track_id in plates and plates[t.track_id].get("plate"):
                        continue
                    crops = plate_crops_for_vehicle(frame, t.bbox, t.class_name)
                    best = None
                    for crop in crops[:2]:
                        if crop is None or crop.size == 0 or crop.shape[1] < 20:
                            continue
                        for line in ocr.read(preprocess_for_ocr(crop)):
                            norm = candidate_from_ocr_text(line.text)
                            if not norm:
                                continue
                            score = float(line.confidence) * (
                                1.0 if plate_format_score(norm) == 1.0
                                else 0.85 if plate_format_score(norm) == 0.5
                                else 0.0
                            )
                            if score < 0.60:
                                continue
                            if best is None or score > best[1]:
                                best = (norm, score, line.text)
                    if best:
                        plates[t.track_id] = {"plate": best[0], "confidence": best[1], "raw": best[2]}
            annotated = _draw(frame, tracks, plates)
        else:
            tracks = tracker.update([], pts_ms=pts)
            annotated = _draw(frame, tracks, plates)
        writer.write(annotated)
        idx += 1
        if idx % 50 == 0:
            print(f"[infer] {idx} frames, {len(plates)} plates read")

    cap.release()
    writer.release()
    print(f"[ok] wrote {args.out}  ({idx} frames, {len(plates)} plates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
