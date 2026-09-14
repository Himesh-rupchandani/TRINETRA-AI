"""
fix_cam04_detection.py
======================
Fixes the "NO SIGNAL - CAM04" issue in the AI Detection view.

Problem:  CAM04 points to https://cctv.corp8.cloud/cam04/index.m3u8, which
          requires Sentinel credentials that are not configured locally.
          The AI Detection /live/detect endpoint therefore gets no frames
          and shows a blank "NO SIGNAL" placeholder.

Fix:      1. Generates a looping demo video (demo_cam04.mp4) from the
             sample JPEG images in trinetra_detection/sample_data/ using
             OpenCV.
          2. Updates CAM04 in the database to stream_type='file' and
             stream_url=<path to that video>, status='ONLINE'.
          3. On the next /api/cameras/cam04/live/detect request the backend
             decodes the file on-demand, runs YOLO, and streams annotated
             MJPEG — fully offline.

Usage (from TRINETRAAI/backend, with venv active):
    python -m scripts.fix_cam04_detection
"""
import sys
import os
from pathlib import Path

# Ensure backend root is importable
backend_root = Path(__file__).resolve().parents[1]
project_root = Path(__file__).resolve().parents[3]
for p in [str(project_root), str(backend_root)]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SAMPLE_DIR = project_root / "trinetra_detection" / "sample_data"
OUTPUT_VIDEO = backend_root / "demo_cam04.mp4"
DB_PATH = backend_root / "trinetra.db"

# ---------------------------------------------------------------------------
# Step 1: Build a looping demo video from sample JPEGs
# ---------------------------------------------------------------------------
def build_demo_video(output: Path, sample_dir: Path, fps: int = 12, duration_sec: int = 30):
    images = sorted(sample_dir.glob("*.jpg")) + sorted(sample_dir.glob("*.jpeg"))
    if not images:
        print(f"[ERROR] No sample images found in {sample_dir}")
        sys.exit(1)

    # Read all sample frames
    frames = []
    for img_path in images:
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        # Resize to 1280×720 for a consistent stream
        frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)
        frames.append(frame)

    if not frames:
        print("[ERROR] Could not read any sample images.")
        sys.exit(1)

    total_frames = fps * duration_sec
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output), fourcc, fps, (1280, 720))
    for i in range(total_frames):
        base_frame = frames[i % len(frames)].copy()
        # Stamp a timestamp so the video looks different each loop
        ts = f"DEMO CAM04  frame {i:05d}"
        cv2.putText(base_frame, ts, (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (0, 230, 255), 2, cv2.LINE_AA)
        cv2.putText(base_frame, "LOCAL DEMO FEED - NOT LIVE", (20, 700),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 1, cv2.LINE_AA)
        writer.write(base_frame)
    writer.release()
    print(f"[OK] Demo video written: {output}  ({total_frames} frames @ {fps} fps)")

# ---------------------------------------------------------------------------
# Step 2: Point CAM04 at the local video in the DB
# ---------------------------------------------------------------------------
def update_cam04_db(db_path: Path, video_path: Path):
    import sqlite3
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "UPDATE cameras SET stream_type='file', stream_url=?, status='ONLINE' WHERE camera_id='CAM04'",
        (str(video_path.resolve()),),
    )
    if cur.rowcount == 0:
        print("[WARN] CAM04 not found in database — no rows updated.")
    else:
        print(f"[OK] CAM04 updated in DB: stream_type=file, stream_url={video_path.resolve()}")
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=== TRINETRA AI — Fix CAM04 AI Detection ===")

    # Build video if missing or stale
    if OUTPUT_VIDEO.exists():
        print(f"[SKIP] Demo video already exists: {OUTPUT_VIDEO}")
        print("       Delete it and re-run this script to regenerate.")
    else:
        print(f"Building demo video from {SAMPLE_DIR} ...")
        build_demo_video(OUTPUT_VIDEO, SAMPLE_DIR)

    # Update DB
    update_cam04_db(DB_PATH, OUTPUT_VIDEO)

    print()
    print("=== Done ===")
    print("Restart the backend (Ctrl+C + uvicorn ...) to pick up the change.")
    print("Then open http://localhost:5173, go to Camera List → CAM04 → click Watch live video.")
    print("The AI Detection overlay (green boxes) should appear automatically.")

if __name__ == "__main__":
    main()
