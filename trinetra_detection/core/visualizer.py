"""
Visualization utilities for Vehicle and Number Plate detections.
"""
from __future__ import annotations

import cv2
import numpy as np
from typing import List, Optional
from .detector import DetectionResult


# Color palette in BGR format
COLOR_VEHICLE = (0, 220, 50)      # Bright Lime Green
COLOR_PLATE = (0, 215, 255)       # Gold / Vibrant Yellow
COLOR_BANNER_BG = (25, 25, 25)    # Dark Charcoal
COLOR_BANNER_TEXT = (255, 255, 255)
COLOR_TEXT_DARK = (10, 10, 10)


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

        # Separate vehicles and plates so plates are drawn on top of vehicles
        vehicles = [d for d in detections if d.class_name == "vehicle"]
        plates = [d for d in detections if d.class_name == "number_plate"]

        # 1. Draw Vehicles (Green)
        for det in vehicles:
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_VEHICLE, 2)

            if draw_labels:
                label = f"Vehicle {det.confidence:.2f}"
                (tw, th), baseline = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
                )
                label_y1 = max(0, y1 - th - 8)
                label_y2 = y1
                cv2.rectangle(
                    annotated,
                    (x1, label_y1),
                    (x1 + tw + 6, label_y2),
                    COLOR_VEHICLE,
                    -1,
                )
                cv2.putText(
                    annotated,
                    label,
                    (x1 + 3, label_y2 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    COLOR_TEXT_DARK,
                    1,
                    cv2.LINE_AA,
                )

        # 2. Draw Number Plates (Gold / Amber Yellow)
        for det in plates:
            x1, y1, x2, y2 = det.bbox
            # Outer dark border + inner thick gold box for maximum contrast
            cv2.rectangle(annotated, (x1 - 1, y1 - 1), (x2 + 1, y2 + 1), (0, 0, 0), 1)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), COLOR_PLATE, 3)

            if draw_labels:
                label = f"PLATE {det.confidence:.2f}"
                (tw, th), baseline = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2
                )
                label_y1 = max(0, y1 - th - 10)
                label_y2 = y1
                cv2.rectangle(
                    annotated,
                    (x1, label_y1),
                    (x1 + tw + 8, label_y2),
                    COLOR_PLATE,
                    -1,
                )
                cv2.putText(
                    annotated,
                    label,
                    (x1 + 4, label_y2 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    COLOR_TEXT_DARK,
                    2,
                    cv2.LINE_AA,
                )

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
