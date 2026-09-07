"""
Vehicle class mapping.

Two layouts are supported:

* Stock COCO-trained YOLO11 (spec §11) — numeric ids 2/3/5/7.
* Fine-tuned TRINETRA vehicle model — custom names
  ``car | motorcycle | bus | truck | autorickshaw``.

Auto-rickshaws dominate Gujarat urban CCTV and are NOT a COCO class; the
stock model often labels them ``car`` or misses them. The fine-tuned model
adds the class. ``normalize_vehicle_class`` maps either layout onto the
stable names the rest of the pipeline already stores on events.
"""
from __future__ import annotations

from typing import Optional

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

# Classes used by the fine-tuned TRINETRA vehicle model (data.yaml order).
TRAINED_VEHICLE_CLASSES = [
    "car",
    "motorcycle",
    "bus",
    "truck",
    "autorickshaw",
]

NAME_ALIASES = {
    "motorbike": "motorcycle",
    "bike": "motorcycle",
    "scooter": "motorcycle",
    "lorry": "truck",
    "pickup": "truck",
    "van": "truck",
    "minitruck": "truck",
    "mini-truck": "truck",
    "auto": "autorickshaw",
    "auto-rickshaw": "autorickshaw",
    "autorickshaw": "autorickshaw",
    "rickshaw": "autorickshaw",
    "three-wheeler": "autorickshaw",
    "threewheeler": "autorickshaw",
    "automobile": "car",
    "sedan": "car",
    "suv": "car",
    "taxi": "car",
    "hatchback": "car",
    "coach": "bus",
    "minibus": "bus",
}

VEHICLE_NAMES = set(VEHICLE_CLASS_IDS.values()) | {"autorickshaw"}


def class_name_for(cls_id: int) -> str:
    return VEHICLE_CLASS_IDS.get(cls_id, f"class_{cls_id}")


def normalize_vehicle_class(name: Optional[str]) -> Optional[str]:
    """Map a raw detector name onto the stable TRINETRA vehicle classes."""
    if not name:
        return None
    key = str(name).strip().lower().replace("_", "-").replace(" ", "-")
    if key in VEHICLE_NAMES or key == "bicycle":
        return key
    return NAME_ALIASES.get(key)


def is_coco_layout(names) -> bool:
    """True when ``model.names`` looks like the 80-class COCO taxonomy."""
    if not names:
        return True
    values = {str(v).lower() for v in (names.values() if hasattr(names, "values") else names)}
    return "person" in values or len(values) >= 70
