"""Backend loads fine-tuned weights when present and never invents plates."""
import sys
from pathlib import Path

for p in [str(Path(__file__).resolve().parents[1])]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np

from app.services.vehicle_detection_service import (
    VehicleDetectionService,
    _normalize_vehicle_name,
)
from app.utils.plate_normalizer import normalize_plate
from app.services.ocr_service import candidate_from_text
from app.services.plate_detector import morphology_plate_boxes


def test_normalize_vehicle_aliases():
    assert _normalize_vehicle_name("auto") == "autorickshaw"
    assert _normalize_vehicle_name("motorbike") == "motorcycle"
    assert _normalize_vehicle_name("person") is None


def test_resolve_prefers_trained(tmp_path, monkeypatch):
    trained = tmp_path / "models" / "trained" / "vehicles" / "best.pt"
    trained.parent.mkdir(parents=True)
    trained.write_bytes(b"t" * 2048)
    svc = VehicleDetectionService()
    monkeypatch.setattr("app.services.vehicle_detection_service._backend_root", lambda: str(tmp_path))
    monkeypatch.setattr("app.services.vehicle_detection_service._repo_root", lambda: str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "YOLO_MODEL_PATH", "models/yolo11s.pt", raising=False)
    monkeypatch.setattr(settings, "PREFER_TRAINED_MODEL", True, raising=False)
    assert svc._resolve_model_path() == str(trained.resolve())


def test_timedelta_is_imported():
    # Regression: finalize_track used timedelta without importing it.
    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "uploaded_video_service.py").read_text()
    assert "from datetime import datetime, timedelta, timezone" in src


def test_unknown_ocr_is_none_not_invented():
    assert candidate_from_text("????") is None
    assert candidate_from_text("abc") is None
    assert candidate_from_text("GJ 01 AB 1234") == "GJ01AB1234"
    assert normalize_plate("GJ-01-AB-1234") == "GJ01AB1234"


def test_morphology_plate_on_synthetic():
    crop = np.zeros((120, 200, 3), dtype=np.uint8)
    crop[80:100, 40:140] = (230, 230, 230)
    for x in range(48, 132, 8):
        crop[82:98, x:x + 3] = (20, 20, 20)
    boxes = morphology_plate_boxes(crop)
    assert boxes
