#!/usr/bin/env python3
"""
Fetch model assets for the hackathon network (where GitHub/HF are reachable).

- yolo11n.pt  (Ultralytics auto-download; ~5.5 MB)
- EasyOCR craft + english_g2 models (downloaded on first Reader init)

Run once before the live demo:

    python scripts/fetch_models.py            # everything
    python scripts/fetch_models.py --yolo yolo11s.pt   # bigger YOLO variant
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fetch_yolo(model_name: str) -> bool:
    try:
        from ultralytics import YOLO
        import numpy as np

        t0 = time.time()
        model = YOLO(model_name)  # triggers official asset download if missing
        model.predict(np.zeros((320, 320, 3), dtype=np.uint8), verbose=False, imgsz=320)
        print(f"[OK] YOLO {model_name} ready in {time.time()-t0:.1f}s")
        return True
    except Exception as exc:
        print(f"[FAIL] YOLO {model_name}: {exc}")
        print("       Download manually from https://github.com/ultralytics/assets/releases")
        print(f"       and place it at cv-engine/{model_name} (or set MODEL_PATH).")
        return False


def fetch_easyocr() -> bool:
    try:
        import numpy as np

        t0 = time.time()
        from anpr.ocr import OcrEngine

        eng = OcrEngine(gpu=False)
        eng.warmup()
        print(f"[OK] EasyOCR models ready in {time.time()-t0:.1f}s")
        return True
    except Exception as exc:
        print(f"[FAIL] EasyOCR: {exc}")
        print("       Models download from the jaided.ai/GitHub mirror on first use.")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yolo", default="yolo11n.pt")
    ap.add_argument("--skip-ocr", action="store_true")
    args = ap.parse_args()

    ok_yolo = fetch_yolo(args.yolo)
    ok_ocr = True if args.skip_ocr else fetch_easyocr()
    sys.exit(0 if (ok_yolo and ok_ocr) else 1)


if __name__ == "__main__":
    main()
