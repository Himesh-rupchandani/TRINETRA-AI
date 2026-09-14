"""
Vehicle class mapping for COCO-trained YOLO11 (spec §11).

Only vehicle classes are kept — person/animal/furniture detections are never
requested from the model, keeping inference cheap.
"""
from __future__ import annotations

# COCO class id -> name, restricted to vehicles
VEHICLE_CLASS_IDS = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Optional extras (disabled by default; enable via config if a scene needs them)
EXTRA_VEHICLE_CLASS_IDS = {
    1: "bicycle",
}

VEHICLE_NAMES = set(VEHICLE_CLASS_IDS.values())


def class_name_for(cls_id: int) -> str:
    return VEHICLE_CLASS_IDS.get(cls_id, f"class_{cls_id}")
