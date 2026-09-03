"""Vehicle class definitions and the mapping onto the backend contract.

The detector is COCO-trained, so the classes we can honestly claim are the COCO
vehicle classes. Two classes the backend enum knows about — ``AUTO_RICKSHAW``
and ``VAN`` — are *not* separable with a COCO model: an auto-rickshaw is
reported as ``car``/``truck`` and a van as ``truck``. That is stated here rather
than papered over with a guess, because a wrong class on an evidence record is
worse than an absent one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

#: COCO class ids that are vehicles, mapped to our internal names.
COCO_VEHICLE_CLASSES: dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

#: Explicitly *not* treated as vehicles for this pipeline. Kept here so the
#: exclusion is a decision on the record, not an accident of the class list.
COCO_NON_VEHICLE_CLASSES: dict[int, str] = {
    0: "person",
    1: "bicycle",
    4: "airplane",
    6: "train",
    8: "boat",
}

VEHICLE_CLASS_IDS: tuple[int, ...] = tuple(sorted(COCO_VEHICLE_CLASSES))

#: Internal name -> the backend/frontend ``VehicleClass`` enum.
BACKEND_CLASS_MAP: dict[str, str] = {
    "car": "CAR",
    "motorcycle": "MOTORCYCLE",
    "bus": "BUS",
    "truck": "TRUCK",
    "auto_rickshaw": "AUTO_RICKSHAW",
    "van": "VAN",
}

UNKNOWN_CLASS = "UNKNOWN"


def is_vehicle_class(class_id: int) -> bool:
    return int(class_id) in COCO_VEHICLE_CLASSES


def vehicle_class_name(class_id: int) -> str | None:
    return COCO_VEHICLE_CLASSES.get(int(class_id))


def to_backend_class(name: str | None) -> str:
    """Map a detector class name onto the backend enum, defaulting to UNKNOWN."""
    if not name:
        return UNKNOWN_CLASS
    return BACKEND_CLASS_MAP.get(str(name).strip().lower(), UNKNOWN_CLASS)


def class_ids_from_names(names: Iterable[str]) -> list[int]:
    """Inverse lookup, used when a run is restricted to a subset of vehicles."""
    wanted = {n.strip().lower() for n in names}
    return [cid for cid, name in COCO_VEHICLE_CLASSES.items() if name in wanted]


@dataclass(frozen=True)
class Detection:
    """One vehicle in one frame.

    Carries the frame PTS, because a detection without its timestamp cannot be
    correlated with anything downstream.
    """

    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels
    class_name: str
    confidence: float
    camera_id: str
    pts_ms: float
    continuous_ms: float = 0.0
    class_id: int | None = None

    @property
    def x1(self) -> float:
        return self.bbox[0]

    @property
    def y1(self) -> float:
        return self.bbox[1]

    @property
    def x2(self) -> float:
        return self.bbox[2]

    @property
    def y2(self) -> float:
        return self.bbox[3]

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_dict(self) -> dict:
        """The internal detection shape documented in the CV engine contract."""
        return {
            "bbox": [round(v, 2) for v in self.bbox],
            "class": self.class_name,
            "confidence": round(self.confidence, 4),
            "camera_id": self.camera_id,
            "pts_ms": self.pts_ms,
        }

    def cropped(self, frame):
        """Integer pixel crop of this detection, clipped to the frame."""
        import numpy as np

        if frame is None or frame.size == 0:
            return None
        h, w = frame.shape[:2]
        x1 = int(max(0, min(self.x1, w - 1)))
        y1 = int(max(0, min(self.y1, h - 1)))
        x2 = int(max(x1 + 1, min(self.x2, w)))
        y2 = int(max(y1 + 1, min(self.y2, h)))
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size else None
