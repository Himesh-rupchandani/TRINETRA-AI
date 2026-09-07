#!/usr/bin/env python3
"""
PART 5 — fine-tune ONLY the weak component: the number-plate detector.

Why this component and nothing else (see docs/MULTI_VIDEO_ASSESSMENT.md):

* the vehicle detector is a COCO YOLO11 model that already finds cars, buses,
  trucks and motorcycles in this footage — retraining it would burn hours to
  re-learn what it knows;
* the OCR engine is a general text recogniser that is accurate *once it is
  given a tight, upscaled plate crop* — its errors come from the crop, not the
  recogniser;
* the plate-localisation stage is the one that did not exist and is currently
  served by a classical OpenCV proposer. That is the weak link, so that is what
  gets trained.

Safety rules enforced here:

* the original weights are copied to ``models/baseline/`` first and are never
  written to;
* the fine-tuned model is saved as a NEW file (``models/plate_detector.pt``);
* defaults are sized for the machine this runs on (auto-detected), not for a
  workstation with a GPU.

Usage:
    python training/train_plate_detector.py --data training/dataset/plates.yaml
    python training/train_plate_detector.py --data ... --epochs 60 --imgsz 512
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "TRINETRAAI" / "backend"
MODELS = BACKEND / "models"
BASELINE = MODELS / "baseline"


def hardware_defaults() -> dict:
    """Pick settings the local machine can actually finish."""
    try:
        import torch

        gpu = torch.cuda.is_available()
    except Exception:
        gpu = False
    cpus = os.cpu_count() or 2
    if gpu:
        return {"device": "0", "batch": 16, "imgsz": 640, "epochs": 100, "workers": min(8, cpus)}
    # CPU box: small images, small batch, few workers — anything else just
    # never finishes.
    return {"device": "cpu", "batch": 4, "imgsz": 416, "epochs": 40, "workers": min(2, cpus)}


def backup_weights(path: Path) -> Path | None:
    if not path.is_file():
        return None
    BASELINE.mkdir(parents=True, exist_ok=True)
    dest = BASELINE / path.name
    if not dest.exists():
        shutil.copy2(path, dest)
        print(f"[train] backed up {path.name} -> {dest}")
    else:
        print(f"[train] baseline copy already present: {dest}")
    return dest


def main(argv: List[str]) -> int:
    hw = hardware_defaults()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(REPO_ROOT / "training/dataset/plates.yaml"))
    ap.add_argument("--base-model", default=str(BASELINE / "yolo11n.pt"),
                    help="starting weights (nano: the plate class is easy, the box is small)")
    ap.add_argument("--out", default=str(MODELS / "plate_detector.pt"))
    ap.add_argument("--project", default=str(REPO_ROOT / "training/runs"))
    ap.add_argument("--name", default=f"plate_{datetime.now():%Y%m%d_%H%M}")
    ap.add_argument("--epochs", type=int, default=hw["epochs"])
    ap.add_argument("--imgsz", type=int, default=hw["imgsz"])
    ap.add_argument("--batch", type=int, default=hw["batch"])
    ap.add_argument("--device", default=hw["device"])
    ap.add_argument("--workers", type=int, default=hw["workers"])
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args(argv)

    data = Path(args.data)
    if not data.is_file():
        raise SystemExit(f"data yaml not found: {data}\nRun training/build_dataset.py first.")
    base = Path(args.base_model)
    if not base.is_file():
        raise SystemExit(
            f"base weights not found: {base}\n"
            "Place YOLO11n weights in TRINETRAAI/backend/models/baseline/."
        )

    print("[train] plan:")
    print(f"        data      {data}")
    print(f"        base      {base.name}")
    print(f"        device    {args.device}   imgsz {args.imgsz}   batch {args.batch}")
    print(f"        epochs    {args.epochs} (early stop after {args.patience} flat epochs)")
    print(f"        output    {args.out}   (originals in {BASELINE} are never modified)")
    if args.dry_run:
        return 0

    backup_weights(base)
    out_path = Path(args.out)
    if out_path.exists():
        stamped = out_path.with_name(f"{out_path.stem}_{datetime.now():%Y%m%d_%H%M}{out_path.suffix}")
        shutil.move(str(out_path), stamped)
        print(f"[train] previous fine-tuned model kept as {stamped.name}")

    from ultralytics import YOLO

    model = YOLO(str(base))
    results = model.train(
        data=str(data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        project=args.project,
        name=args.name,
        exist_ok=True,
        pretrained=True,
        optimizer="auto",
        seed=0,
        deterministic=True,
        # CPU training cannot use mixed precision, and the AMP check tries to
        # download extra weights — off by default on CPU.
        amp=(args.device != "cpu"),
        # Augmentation matched to the footage problems found in PART 2:
        # motion blur, small/far plates, varying light. No vertical flips —
        # plates are never upside down.
        degrees=3.0, translate=0.08, scale=0.5, shear=2.0,
        perspective=0.0005, fliplr=0.0, flipud=0.0,
        hsv_h=0.015, hsv_s=0.5, hsv_v=0.4,
        mosaic=0.6, erasing=0.2,
    )

    save_dir = Path(getattr(results, "save_dir", Path(args.project) / args.name))
    best = save_dir / "weights" / "best.pt"
    if not best.is_file():
        raise SystemExit(f"training finished but {best} is missing")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, out_path)

    meta = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "base_model": str(base),
        "data": str(data),
        "epochs": args.epochs, "imgsz": args.imgsz, "batch": args.batch,
        "device": args.device, "run_dir": str(save_dir),
        "saved_to": str(out_path),
    }
    out_path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    print(f"[train] fine-tuned plate detector -> {out_path}")
    print("[train] the backend picks it up automatically via PLATE_MODEL_PATH.")
    print("[train] now run: python training/evaluate.py --plate-model", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
