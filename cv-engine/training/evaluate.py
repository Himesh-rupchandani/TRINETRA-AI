#!/usr/bin/env python3
"""Validate a trained detector and print precision / recall / mAP.

    python training/evaluate.py --weights models/trained/vehicles/best.pt --split val
    python training/evaluate.py --weights models/trained/vehicles/best.pt --split test
    python training/evaluate.py --weights models/trained/plates/best.pt \\
        --data training/datasets/plates/data.yaml --split val

mAP on auto-labels is an upper bound on self-agreement, NOT true accuracy.
The number that matters is the comparison against held-out video seconds
(the time-based test split) and a visual pass of infer_video.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import REPORTS, TRAINED_VEHICLE, VEHICLE_DS, ensure_dirs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", default=str(TRAINED_VEHICLE))
    ap.add_argument("--data", default=str(VEHICLE_DS / "data.yaml"))
    ap.add_argument("--split", choices=["val", "test"], default="val")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch", type=int, default=4)
    args = ap.parse_args()
    ensure_dirs()

    if not Path(args.weights).is_file() and args.weights.endswith(".pt"):
        # Allow the bare ultralytics name as a baseline comparison.
        pass
    if not Path(args.data).is_file():
        raise SystemExit(f"missing {args.data}")

    from ultralytics import YOLO

    model = YOLO(args.weights)
    metrics = model.val(
        data=args.data,
        split=args.split,
        imgsz=args.imgsz,
        device=args.device,
        batch=args.batch,
        plots=True,
    )
    out = {
        "weights": args.weights,
        "data": args.data,
        "split": args.split,
        "imgsz": args.imgsz,
        "metrics": {
            "precision": float(metrics.box.mp) if hasattr(metrics, "box") else None,
            "recall": float(metrics.box.mr) if hasattr(metrics, "box") else None,
            "mAP50": float(metrics.box.map50) if hasattr(metrics, "box") else None,
            "mAP50-95": float(metrics.box.map) if hasattr(metrics, "box") else None,
        },
    }
    # Per-class when available.
    try:
        out["per_class"] = {
            "precision": [float(x) for x in metrics.box.p],
            "recall": [float(x) for x in metrics.box.r],
            "mAP50": [float(x) for x in metrics.box.ap50],
        }
    except Exception:
        pass
    REPORTS.mkdir(parents=True, exist_ok=True)
    dest = REPORTS / f"eval_{Path(args.weights).stem}_{args.split}.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out["metrics"], indent=2))
    print(f"[ok] {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
