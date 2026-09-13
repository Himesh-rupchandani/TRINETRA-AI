"""
Visualization utilities for Vehicle and Number Plate detections.

Box policy: what is drawn is exactly the rectangle the detector returned
(clipped to the frame by the detector). No padding, no growth, no fixed-size
boxes — the green rectangle is vehicle-boundary to vehicle-boundary.
"""
from __future__ import annotations

import cv2
import numpy as np
from typing import List, Optional

try:  # package-relative first, then flat-module import (scripts run from the root)
    from .detector import DetectionResult
except ImportError:  # pragma: no cover
    from detector import DetectionResult  # type: ignore


# Color palette in BGR format
COLOR_VEHICLE = (0, 220, 50)      # Bright Lime Green
COLOR_PLATE = (0, 215, 255)       # Gold / Vibrant Yellow
COLOR_BANNER_BG = (25, 25, 25)    # Dark Charcoal
COLOR_BANNER_TEXT = (255, 255, 255)
COLOR_TEXT_DARK = (10, 10, 10)

# Names that render as a vehicle when a DetectionResult carries no `kind`.
_VEHICLE_ALIASES = {
    "vehicle", "car", "bus", "truck", "motorcycle", "motorbike", "scooter",
    "van", "jeep", "auto", "auto_rickshaw", "three_wheeler", "tempo",
}


def _is_vehicle(det: DetectionResult) -> bool:
    kind = getattr(det, "kind", None)
    if kind is not None:
        return kind == "vehicle"
    name = str(det.class_name).lower().replace("-", "_")
    return name not in {"number_plate", "plate", "license_plate", "licence_plate"}


def _frame_scale(frame: np.ndarray) -> float:
    """Line thickness / text size that stay readable without dominating 1080p."""
    h, w = frame.shape[:2]
    return max(1.0, min(3.0, min(h, w) / 360.0))


def _draw_label(
    frame: np.ndarray,
    text: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color,
    scale: float,
) -> None:
    """Small tag for one box: above it when there is room, otherwise inside.

    The tag is deliberately minor — sized from the box it belongs to (a distant
    car must not carry a label wider than the car), clamped to the frame, and
    never allowed to bury the vehicle in text.
    """
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    box_h = max(6, y2 - y1)
    font_scale = max(0.32, min(0.58, box_h / 130.0))
    thickness = 1 if box_h < 110 else max(1, int(round(scale * 0.6)))
    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    pad = 2
    rect_w = tw + 2 * pad
    rect_h = th + baseline + 2 * pad
    left = min(max(0, x1), max(0, w - rect_w))          # never off the right edge
    top = y1 - rect_h if y1 - rect_h >= 0 else min(y1, max(0, h - rect_h))
    if top < y1 + rect_h and box_h < rect_h * 3:
        # No room above and the box is small: sit *inside* the top of the box
        # instead of painting over whatever is above the vehicle.
        top = y1
    cv2.rectangle(frame, (left, top), (left + rect_w, top + rect_h), color, -1)
    cv2.putText(
        frame, text,
        (left + pad, top + rect_h - pad - baseline // 2 - 1),
        font, font_scale, COLOR_TEXT_DARK, thickness, cv2.LINE_AA,
    )


class Visualizer:
    """Visualizes detection results with bounding boxes, confidence tags, and status banners."""

    @staticmethod
    def draw_detections(
        frame: np.ndarray,
        detections: List[DetectionResult],
        draw_labels: bool = True,
    ) -> np.ndarray:
        """
        Draw bounding boxes and labels for vehicles and number plates onto frame.
        """
        annotated = frame.copy()
        scale = _frame_scale(annotated)

        # Separate vehicles and plates so plates are drawn on top of vehicles
        vehicles = [d for d in detections if _is_vehicle(d)]
        plates = [d for d in detections if not _is_vehicle(d)]

        # 1. Draw Vehicles (Green) — the model's box, unmodified.
        for det in vehicles:
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_VEHICLE, max(1, int(round(scale))))

            if draw_labels:
                label = f"{det.class_name} {det.confidence:.2f}"
                _draw_label(annotated, label, x1, y1, x2, y2, COLOR_VEHICLE, scale)

        # 2. Draw Number Plates (Gold / Amber Yellow)
        for det in plates:
            x1, y1, x2, y2 = det.bbox
            # Outer dark border + inner gold box for maximum contrast
            cv2.rectangle(annotated, (x1 - 1, y1 - 1), (x2 + 1, y2 + 1), (0, 0, 0), 1)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_PLATE, max(2, int(round(scale))))

            if draw_labels:
                label = f"PLATE {det.confidence:.2f}"
                _draw_label(annotated, label, x1, y1, x2, y2, COLOR_PLATE, scale)

        return annotated

    @staticmethod
    def draw_banner(
        frame: np.ndarray,
        title: str = "TRINETRA AI DETECTION",
        info_text: str = "",
        height: int = 34,
    ) -> np.ndarray:
        """Draw an informational dark header banner across the top."""
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (w, height), COLOR_BANNER_BG, -1)
        # Subtle accent line under banner
        cv2.line(frame, (0, height), (w, height), COLOR_PLATE, 2)

        # Title
        cv2.putText(
            frame,
            title,
            (12, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            COLOR_PLATE,
            2,
            cv2.LINE_AA,
        )

        # Additional info on the right
        if info_text:
            cv2.putText(
                frame,
                f"|  {info_text}",
                (280, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                COLOR_BANNER_TEXT,
                1,
                cv2.LINE_AA,
            )

        return frame
