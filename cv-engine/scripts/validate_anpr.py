#!/usr/bin/env python3
"""
ANPR quality evaluation (spec §29).

Reports the three stages SEPARATELY — vehicle detected / plate region read /
plate correctly formatted — and never merges them into one fake accuracy.

    python scripts/validate_anpr.py --images evidence_out/cam04
    python scripts/validate_anpr.py --images samples --truth truth.json

truth.json maps filename -> expected normalized plate (optional).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="directory of frames/evidence")
    ap.add_argument("--truth", default=None, help="optional JSON of ground-truth plates")
    args = ap.parse_args()

    import cv2
    from config.settings import Settings
    from detection.vehicle_detector import VehicleDetector
    from anpr.ocr import OcrEngine
    from anpr.plate_detector import extract_plate_candidates, preprocess_for_ocr
    from anpr.normalizer import candidate_from_ocr_text, is_indian_plate_format

    settings = Settings.from_env()
    detector = VehicleDetector(
        model_path=settings.model_path,
        conf_threshold=settings.conf_threshold,
        imgsz=settings.inference_imgsz,
        device=settings.device,
        include_bicycles=settings.include_bicycles,
        nms_iou_threshold=settings.nms_iou_threshold,
        duplicate_iou_threshold=settings.duplicate_iou_threshold,
        max_detections=settings.max_detections,
        tile_grid=settings.tile_grid,
        tile_overlap=settings.tile_overlap,
        tile_min_frame_edge=settings.tile_min_frame_edge,
    )
    ocr = OcrEngine(gpu=False)

    truth = {}
    if args.truth:
        truth = json.loads(Path(args.truth).read_text())

    files = sorted(p for p in Path(args.images).iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
    if not files:
        raise SystemExit(f"no images in {args.images}")

    n_images = len(files)
    n_vehicle_frames = 0
    n_vehicles = 0
    n_plate_reads = 0          # OCR produced a plate-like candidate
    n_indian_format = 0        # candidate matches Indian plate layout
    confidences = []
    correct = 0
    evaluated_truth = 0

    for f in files:
        frame = cv2.imread(str(f))
        if frame is None:
            continue
        dets = detector.detect(frame, camera_id="eval")
        if dets:
            n_vehicle_frames += 1
        for d in dets:
            n_vehicles += 1
            crops = extract_plate_candidates(frame, d.bbox, d.class_name)
            best = None
            for crop in crops[:2]:
                for line in ocr.read(preprocess_for_ocr(crop)):
                    cand = candidate_from_ocr_text(line.text)
                    if cand:
                        if best is None or line.confidence > best[1]:
                            best = (cand, float(line.confidence))
            if best:
                n_plate_reads += 1
                confidences.append(best[1])
                if is_indian_plate_format(best[0]):
                    n_indian_format += 1
                gt = truth.get(f.name)
                if gt:
                    evaluated_truth += 1
                    if best[0] == gt.upper().replace(" ", ""):
                        correct += 1

    print("=" * 64)
    print("ANPR validation report (stages reported separately)")
    print(f"images                        : {n_images}")
    print(f"vehicle detected (frames)     : {n_vehicle_frames}/{n_images}")
    print(f"vehicles detected (boxes)     : {n_vehicles}")
    print(f"plate read (OCR candidate)    : {n_plate_reads}/{n_vehicles or 0} vehicles")
    print(f"plate Indian-format           : {n_indian_format}/{n_plate_reads or 0} candidates")
    if confidences:
        confidences.sort()
        print(f"confidence                    : min={confidences[0]:.2f} "
              f"median={confidences[len(confidences)//2]:.2f} max={confidences[-1]:.2f}")
    if evaluated_truth:
        print(f"normalized plate accuracy     : {correct}/{evaluated_truth} "
              f"({100.0*correct/evaluated_truth:.1f}%) — only where ground truth provided")
    else:
        print("normalized plate accuracy     : not measured (no --truth provided)")


if __name__ == "__main__":
    main()
