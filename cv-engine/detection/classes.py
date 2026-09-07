"""
Vehicle class mapping for COCO-trained YOLO11 (spec §11).

Only vehicle classes are kept — person/animal/furniture detections are never
requested from the model, keeping inference cheap.
"""
from __future__ import annotations

# Core COCO road-vehicle classes. COCO has no separate auto-rickshaw/van
# class; those vehicles are represented by the detector's closest car/truck
# category unless a domain-specific fine-tuned weight file is configured.
VEHICLE_CLASS_IDS = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Bicycle is a supported road vehicle too. It can be disabled for motor-only
# deployments, but is enabled by default in the live detector so a visible
# bike is not silently ignored.
EXTRA_VEHICLE_CLASS_IDS = {
    1: "bicycle",
}

ALL_VEHICLE_CLASS_IDS = {**EXTRA_VEHICLE_CLASS_IDS, **VEHICLE_CLASS_IDS}
VEHICLE_NAMES = set(ALL_VEHICLE_CLASS_IDS.values())


def class_name_for(cls_id: int) -> str:
    return ALL_VEHICLE_CLASS_IDS.get(cls_id, f"class_{cls_id}")
