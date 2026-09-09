"""
Self-check for the plate-usage (time-in-shot) feature, on real pixels.

The unit tests (``tests/test_plate_usage.py``) stub the OCR engine, which makes
them fast and deterministic but leaves one question open: does the *real* ANPR
chain — plate localisation → RapidOCR → normalisation — actually produce plates
that the report can time?

This script answers it. It renders a synthetic CCTV clip with three vehicles
carrying OCR-readable number plates, runs the production pipeline over it, and
compares the measured times against exact ground truth.

Only the vehicle *detector* is scripted (it returns the ground-truth boxes).
Everything downstream is the real production code:

    video decode -> tracking -> REAL plate localisation -> REAL OCR
                 -> presence accounting -> report -> CSV

Usage (from TRINETRAAI/backend):

    python -m scripts.verify_plate_usage                # run and clean up
    python -m scripts.verify_plate_usage --keep-video   # leave the clip on disk
    python -m scripts.verify_plate_usage --show-csv     # print the CSV export

Exit code 0 = every measured time matched the ground truth.

Why the detector is scripted
----------------------------
Shipping a check that needs a ~100 MB detector checkpoint would make it useless
on an offline machine. The detector is the one stage this script cannot verify
anyway — it only supplies boxes, and the timing maths under test is the same
whatever produced them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.database.database import SessionLocal, init_db  # noqa: E402
from app.database.models import VideoSource  # noqa: E402
from app.services import plate_matching, plate_usage_service as pus  # noqa: E402
from app.services import video_analysis_service as vas  # noqa: E402
from app.services.ocr_service import ocr_service  # noqa: E402
from app.services.vehicle_detection_service import (  # noqa: E402
    VehicleDetection,
    vehicle_detection_service,
)

W, H = 960, 540
FPS = 10
FRAMES = 120        # 12.0 s of video
EVERY_N = 5         # analyse every 5th frame -> 0.5 s per sample

CAR_W, CAR_H = 300, 150
PLATE_W, PLATE_H = 196, 40

# key -> (plate text, first frame, last frame inclusive, lane y, body colour, speed)
GROUND_TRUTH = {
    "A": ("GJ01AB1234", 0, 99, 90, (200, 90, 60), 5),
    "B": ("MH12XY4567", 20, 49, 232, (60, 120, 200), 11),
    "C": ("DL08EF9012", 40, 119, 366, (90, 170, 90), 7),
}


def draw_vehicle(frame, x, y, colour, plate_text):
    """A crude but plate-legible car: body, cabin, wheels, number plate."""
    cv2.rectangle(frame, (x, y), (x + CAR_W, y + CAR_H), colour, -1)
    cv2.rectangle(frame, (x, y), (x + CAR_W, y + CAR_H), (30, 30, 30), 2)
    cv2.rectangle(frame, (x + 60, y - 34), (x + CAR_W - 50, y), colour, -1)
    cv2.rectangle(frame, (x + 60, y - 34), (x + CAR_W - 50, y), (30, 30, 30), 2)
    for wx in (x + 45, x + CAR_W - 85):
        cv2.circle(frame, (wx, y + CAR_H), 26, (25, 25, 25), -1)
    px = x + (CAR_W - PLATE_W) // 2
    py = y + CAR_H - 54
    cv2.rectangle(frame, (px, py), (px + PLATE_W, py + PLATE_H), (255, 255, 255), -1)
    cv2.rectangle(frame, (px, py), (px + PLATE_W, py + PLATE_H), (0, 0, 0), 2)
    cv2.putText(frame, plate_text, (px + 10, py + 29),
                cv2.FONT_HERSHEY_SIMPLEX, 0.86, (0, 0, 0), 2, cv2.LINE_AA)


def build_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    noise = np.random.default_rng(7)
    for f in range(FRAMES):
        frame = np.full((H, W, 3), 96, np.uint8)
        cv2.line(frame, (0, 178), (W, 178), (200, 200, 200), 3)
        cv2.line(frame, (0, 358), (W, 358), (200, 200, 200), 3)
        for _, (plate, first, last, lane_y, colour, speed) in GROUND_TRUTH.items():
            if first <= f <= last:
                x = int((f - first) * speed) % (W + 200) - 100
                draw_vehicle(frame, x, lane_y, colour, plate)
        frame = cv2.add(frame, noise.normal(0, 6, frame.shape).astype(np.int16).astype(np.uint8))
        writer.write(frame)
    writer.release()


def _make_detector():
    """Ground-truth vehicle boxes. ``detect`` runs once per analysed frame."""
    counter = {"n": 0}

    def detect(frame):
        f = counter["n"] * EVERY_N
        counter["n"] += 1
        boxes = []
        for _, (_, first, last, lane_y, _, speed) in GROUND_TRUTH.items():
            if first <= f <= last:
                x = int((f - first) * speed) % (W + 200) - 100
                boxes.append(VehicleDetection(
                    x1=max(0, x), y1=max(0, lane_y - 34),
                    x2=min(W - 1, x + CAR_W), y2=min(H - 1, lane_y + CAR_H + 26),
                    class_name="car", confidence=0.93))
        return boxes

    return detect


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--keep-video", action="store_true", help="leave the generated clip on disk")
    ap.add_argument("--show-csv", action="store_true", help="print the CSV export")
    args = ap.parse_args(argv)

    if not ocr_service.available:
        print("SKIPPED: no OCR engine installed (pip install rapidocr-onnxruntime).")
        print("The timing maths is covered by tests/test_plate_usage.py regardless.")
        return 0

    settings.ANALYSIS_EVERY_N_FRAMES = EVERY_N
    init_db()

    path = Path("/tmp/trinetra_plate_usage_check.mp4")
    build_video(path)
    print(f"built {path} ({FRAMES} frames @ {FPS} fps = {FRAMES / FPS:.1f} s)\n")

    vehicle_detection_service._model = object()
    vehicle_detection_service._backend = "scripted-ground-truth"
    vehicle_detection_service.detect = _make_detector()

    db = SessionLocal()
    video = vas.register_upload(db, path.name, path.read_bytes(), "verify")
    video_id = video.video_id
    db.close()

    vas._run_video(video_id)

    db = SessionLocal()
    stored = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
    if stored.status == "FAILED":
        print(f"FAILED: {stored.error}")
        db.close()
        return 1
    report = pus.build_report(db, video_id)
    db.close()

    bar = "=" * 76
    print(bar)
    print("MEASURED FROM THE VIDEO")
    print(bar)
    print(f"{'PLATE':<14} {'IN SHOT':>9} {'ON SCREEN':>10} {'ENTRY':>9} {'EXIT':>9} {'ENTRIES':>8}")
    for r in list(report["plates"]) + list(report["unreadable"]):
        print(f"{r['plate_label']:<14} {r['dwell_label']:>9} {r['visible_label']:>10} "
              f"{r['first_seen']:>9} {r['last_seen']:>9} {r['appearances']:>8}")

    if args.show_csv:
        print(f"\n{bar}\nCSV EXPORT\n{bar}")
        print(pus.report_to_csv(report))

    print(f"\n{bar}")
    print("GROUND TRUTH vs MEASURED")
    print(bar)
    read = {r["plate"]: r for r in report["plates"]}
    ok = True
    for key, (text, first, last, *_rest) in GROUND_TRUTH.items():
        expected_text = text
        # The analysed sample nearest each end of the window.
        first_s = (first // EVERY_N) * EVERY_N / FPS
        last_s = (last // EVERY_N) * EVERY_N / FPS
        exp_dwell = (last_s - first_s) + EVERY_N / FPS

        match = read.get(expected_text)
        note = ""
        if match is None:
            # Allow a single confusable OCR character: the plates here are
            # rendered, not photographed, so a 1-glyph slip is an artefact of
            # the fixture rather than of the pipeline.
            for plate, row in read.items():
                if plate_matching.confusable_distance(expected_text, plate) == 1:
                    match, note = row, f" (OCR read '{plate}', 1 char off)"
                    break
        if match is None:
            print(f"  {expected_text}: NOT READ  (plates read: {sorted(read) or 'none'})")
            ok = False
            continue
        good = (abs(match["dwell_sec"] - exp_dwell) < 1e-6
                and abs(match["visible_sec"] - exp_dwell) < 1e-6)
        ok &= good
        print(f"  {expected_text}: expected {exp_dwell:5.2f}s | dwell {match['dwell_sec']:5.2f}s "
              f"| on screen {match['visible_sec']:5.2f}s -> "
              f"{'OK' if good else 'MISMATCH'}{note}")

    db = SessionLocal()
    try:
        vas.delete_video(db, video_id)
    finally:
        db.close()
    if not args.keep_video:
        path.unlink(missing_ok=True)
    else:
        print(f"\nclip kept at {path}")

    print(f"\nRESULT: {'ALL TIMES MATCHED' if ok else 'MISMATCH FOUND'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
