"""Shared paths / helpers for the TRINETRA training toolkit."""
from __future__ import annotations

import sys
from pathlib import Path

CV_ROOT = Path(__file__).resolve().parents[1]
if str(CV_ROOT) not in sys.path:
    sys.path.insert(0, str(CV_ROOT))

REPO_ROOT = CV_ROOT.parent
FEEDS_DIR = CV_ROOT / "feeds"
REFERENCE_VIDEO = FEEDS_DIR / "reference_traffic.mp4"
REFERENCE_DRIVE_ID = "1PQZz_WTHp9OOvepr86E9iihFBpej3TYF"
REFERENCE_DRIVE_URL = (
    "https://drive.google.com/file/d/1PQZz_WTHp9OOvepr86E9iihFBpej3TYF/view?usp=drivesdk"
)
REFERENCE_FILENAME = "VID20260907113848.mp4"
REFERENCE_BYTES = 184 * 1024 * 1024  # Google Drive listing

DOMAIN_STILLS = REPO_ROOT / "trinetra-ai" / "public" / "cctv"

DATASETS = CV_ROOT / "training" / "datasets"
VEHICLE_DS = DATASETS / "vehicles"
PLATE_DS = DATASETS / "plates"
RUNS = CV_ROOT / "training" / "runs"
REPORTS = CV_ROOT / "training" / "reports"
FRAMES_DIR = REPORTS / "frames"

ORIGINAL_VEHICLE = CV_ROOT / "models" / "original" / "yolo11s.pt"
TRAINED_VEHICLE = CV_ROOT / "models" / "trained" / "vehicles" / "best.pt"
TRAINED_PLATE = CV_ROOT / "models" / "trained" / "plates" / "best.pt"

VEHICLE_CLASSES = ["car", "motorcycle", "bus", "truck", "autorickshaw"]
PLATE_CLASSES = ["license_plate"]


def ensure_dirs() -> None:
    for p in (
        FEEDS_DIR,
        VEHICLE_DS / "images" / "train",
        VEHICLE_DS / "images" / "val",
        VEHICLE_DS / "images" / "test",
        VEHICLE_DS / "labels" / "train",
        VEHICLE_DS / "labels" / "val",
        VEHICLE_DS / "labels" / "test",
        PLATE_DS / "images" / "train",
        PLATE_DS / "images" / "val",
        PLATE_DS / "images" / "test",
        PLATE_DS / "labels" / "train",
        PLATE_DS / "labels" / "val",
        PLATE_DS / "labels" / "test",
        RUNS,
        REPORTS,
        FRAMES_DIR,
        ORIGINAL_VEHICLE.parent,
        TRAINED_VEHICLE.parent,
        TRAINED_PLATE.parent,
    ):
        p.mkdir(parents=True, exist_ok=True)
