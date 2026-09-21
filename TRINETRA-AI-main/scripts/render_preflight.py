#!/usr/bin/env python3
"""Fail fast when a Render ML service would otherwise start as a vision-less API.

No database writes, camera connections, credential logging or model downloads.
--imports-only is used during build (persistent disks are runtime-only).
The normal startup check also resolves local weights without loading them.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def import_checks():
    checks = {}
    failures = []
    for name in ("numpy", "cv2", "PIL", "torch", "torchvision", "ultralytics", "rapidocr_onnxruntime"):
        try:
            module = importlib.import_module(name)
            checks[name] = {"available": True, "version": str(getattr(module, "__version__", "installed"))}
        except Exception as exc:
            # Return error TYPES only: library exceptions can contain local
            # filesystem paths or environment details we should not expose.
            checks[name] = {"available": False, "error_type": type(exc).__name__}
            failures.append(name)
    if not failures:
        try:
            torch = importlib.import_module("torch")
            torchvision = importlib.import_module("torchvision")
            kept = torchvision.ops.nms(torch.tensor([[0., 0., 5., 5.]]), torch.tensor([.9]), .5)
            if kept.tolist() != [0]:
                raise RuntimeError("Unexpected NMS result")
            checks["torchvision_cpu_ops"] = {"available": True}
        except Exception as exc:
            checks["torchvision_cpu_ops"] = {"available": False, "error_type": type(exc).__name__}
            failures.append("torchvision_cpu_ops")
    return checks, failures


def is_weight_file(path):
    file = Path(path)
    if not file.is_file() or file.stat().st_size < 1024:
        return False
    with file.open("rb") as handle:
        return not handle.read(100).startswith(b"version https://git-lfs.github.com/spec/")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--imports-only", action="store_true")
    args = parser.parse_args(argv)
    if os.environ.get("TRINETRA_API_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}:
        print("ERROR: TRINETRA_API_ONLY disables the vision stack. Unset it or set 0 in Render Environment, then redeploy.", file=sys.stderr)
        return 1
    if not args.imports_only:
        sys.path.insert(0, str(ROOT / "TRINETRAAI/backend"))
        from app.core.resource_budget import inference_budget
        budget = inference_budget()
        if not budget["allowed"]:
            # Avoid importing Torch during preflight and OOM-restarting the API
            # before its live-inference guard can report the resource warning.
            print(json.dumps({"resource_budget": budget}, indent=2))
            print("Starting the API/player with live AI paused for resources. This does not make a small instance a full ML backend.")
            return 0
    checks, failures = import_checks()
    print(json.dumps({"python": sys.version.split()[0], "vision_imports": checks}, indent=2))
    if failures:
        print("ERROR: ML runtime checks failed: " + ", ".join(failures), file=sys.stderr)
        print("Use bash scripts/render_build.sh from the repository root. Check that build and start use the same Python interpreter. Repair OpenCV with scripts/ensure_headless_opencv.py.", file=sys.stderr)
        return 1
    if args.imports_only:
        return 0
    sys.path.insert(0, str(ROOT / "TRINETRAAI/backend"))
    from app.services.vehicle_detection_service import vehicle_detection_service
    from app.services.plate_detector_service import plate_detector_service
    from app.core.config import settings
    vehicle = vehicle_detection_service._resolve_model_path()
    if not is_weight_file(vehicle):
        print("ERROR: Vehicle weights are missing. Leave Render Root Directory blank so the bundled models are included, or set YOLO_MODEL_PATH to an existing local model file.", file=sys.stderr)
        return 1
    plate = plate_detector_service._resolve_model_path()
    if settings.PLATE_MODEL_PATH.strip() and (not plate or not is_weight_file(plate)):
        print("ERROR: Plate weights are missing. Include trinetra_detection/models/best.pt or set PLATE_MODEL_PATH to an existing local model. Empty PLATE_MODEL_PATH explicitly opts into classical-only localization.", file=sys.stderr)
        return 1
    print("ML imports, CPU operators and configured local weights are ready. Camera reachability and OCR accuracy still require a real-feed check.")
    if os.environ.get("RENDER"):
        print("Storage reminder: Render's local filesystem is not durable without a persistent disk. Keep your database and evidence/uploads on persistent storage; do not replace an existing DATABASE_URL without a backup/migration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
