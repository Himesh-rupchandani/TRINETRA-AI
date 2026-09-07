#!/usr/bin/env python3
"""
PART 4b — propose number-plate boxes for the extracted frames.

Hand-labelling thousands of plates is the real cost of this project, so this
script does the boring 80 %: it runs the production vehicle detector, then the
production classical plate proposer inside each vehicle, and keeps a proposal
only when the OCR engine actually reads plate-like text out of it. Proposals
are written as YOLO-format labels (single class ``plate``).

    THESE ARE PROPOSALS, NOT GROUND TRUTH.
    Review them (LabelImg / CVAT / Roboflow) before training. Every file is
    listed in ``autolabel_report.json`` with its OCR text and confidence so you
    can review the weakest ones first. Frames where nothing was found get an
    empty label file — which is a valid "no plate here" negative, but check it.

Usage:
    python training/autolabel_plates.py --dataset training/dataset
    python training/autolabel_plates.py --dataset training/dataset --review-below 0.75
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "TRINETRAAI" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SPLITS = ("train", "val", "test")


def _yolo_line(cls: int, x1: float, y1: float, x2: float, y2: float, w: int, h: int) -> str:
    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    bw, bh = (x2 - x1) / w, (y2 - y1) / h
    return f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="training/dataset")
    ap.add_argument("--min-ocr-confidence", type=float, default=0.45,
                    help="keep a proposal only if OCR read something this confident")
    ap.add_argument("--review-below", type=float, default=0.75,
                    help="flag proposals under this confidence for manual review")
    ap.add_argument("--limit", type=int, default=0, help="0 = all frames")
    args = ap.parse_args(argv)

    from app.services.ocr_service import ocr_service  # noqa: E402
    from app.services.plate_detector_service import plate_detector_service  # noqa: E402
    from app.services.vehicle_detection_service import vehicle_detection_service  # noqa: E402

    if vehicle_detection_service._ensure_model() is None:
        raise SystemExit("Vehicle detector unavailable — check models/ and ultralytics install.")
    if not ocr_service.available:
        print("[autolabel] WARNING: no OCR engine — every proposal will need manual review.")

    root = Path(args.dataset)
    report = {"proposals": [], "frames": 0, "with_plate": 0, "needs_review": 0}

    for split in SPLITS:
        img_dir, lbl_dir = root / "images" / split, root / "labels" / split
        if not img_dir.is_dir():
            continue
        lbl_dir.mkdir(parents=True, exist_ok=True)
        images = sorted(img_dir.glob("*.jpg"))
        if args.limit:
            images = images[: args.limit]
        for img_path in images:
            frame = cv2.imread(str(img_path))
            if frame is None:
                continue
            report["frames"] += 1
            h, w = frame.shape[:2]
            lines: List[str] = []
            for det in vehicle_detection_service.detect(frame):
                for box in plate_detector_service.detect(
                    frame, (det.x1, det.y1, det.x2, det.y2), det.class_name, max_candidates=2
                ):
                    crop = frame[box.y1:box.y2, box.x1:box.x2]
                    if crop.size == 0 or box.width < 24 or box.height < 8:
                        continue
                    text, conf = "", 0.0
                    for t, c in ocr_service.read_lines(crop):
                        cleaned = "".join(ch for ch in t.upper() if ch.isalnum())
                        if len(cleaned) >= 4 and c > conf:
                            text, conf = cleaned, float(c)
                    if conf < args.min_ocr_confidence:
                        continue
                    lines.append(_yolo_line(0, box.x1, box.y1, box.x2, box.y2, w, h))
                    entry = {
                        "image": str(img_path.relative_to(root)),
                        "box": box.as_list(),
                        "source": box.source,
                        "ocr_text": text,
                        "ocr_confidence": round(conf, 4),
                        "needs_review": conf < args.review_below,
                    }
                    report["proposals"].append(entry)
                    if entry["needs_review"]:
                        report["needs_review"] += 1
                    break  # one plate per vehicle
            (lbl_dir / f"{img_path.stem}.txt").write_text("\n".join(lines))
            if lines:
                report["with_plate"] += 1

    out = root / "autolabel_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"[autolabel] {report['frames']} frames, {report['with_plate']} with a proposed plate, "
          f"{len(report['proposals'])} proposals, {report['needs_review']} flagged for review")
    print(f"[autolabel] report -> {out}")
    print("[autolabel] REVIEW THE LABELS BEFORE TRAINING — these are machine proposals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
