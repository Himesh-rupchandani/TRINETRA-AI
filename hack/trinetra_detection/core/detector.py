"""
Vehicle and Number Plate Detector using YOLO11.
Provides a clean, modular API for detecting vehicles and license plates.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import cv2
import numpy as np


@dataclass
class DetectionResult:
    """Represents a single detected object (Vehicle or Number Plate)."""
    bbox: List[int]        # [x1, y1, x2, y2]
    class_id: int          # 0: vehicle, 1: number_plate
    class_name: str        # 'vehicle' or 'number_plate'
    confidence: float      # 0.0 - 1.0

    @property
    def x1(self) -> int:
        return self.bbox[0]

    @property
    def y1(self) -> int:
        return self.bbox[1]

    @property
    def x2(self) -> int:
        return self.bbox[2]

    @property
    def y2(self) -> int:
        return self.bbox[3]

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    def crop(self, image: np.ndarray) -> np.ndarray:
        """Crop this detection from the original image/frame."""
        h, w = image.shape[:2]
        x1 = max(0, min(w - 1, self.x1))
        y1 = max(0, min(h - 1, self.y1))
        x2 = max(0, min(w, self.x2))
        y2 = max(0, min(h, self.y2))
        return image[y1:y2, x1:x2].copy()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": self.bbox,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
        }


class VehiclePlateDetector:
    """
    High-level detector for vehicles and number plates using trained YOLO11 weights.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        device: Optional[str] = None,
    ):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.model_path = self._resolve_model_path(model_path)
        self.device = device

        # Lazy import ultralytics
        from ultralytics import YOLO
        import torch

        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"[Detector] Loading model weights from: {self.model_path}")
        print(f"[Detector] Running on device: {self.device}")
        self.model = YOLO(self.model_path)
        self.class_names = self.model.names
        print(f"[Detector] Model loaded successfully! Classes: {self.class_names}")

    def _resolve_model_path(self, path: Optional[str]) -> str:
        if path and os.path.exists(path):
            return str(Path(path).resolve())

        # Check default paths relative to this file
        core_dir = Path(__file__).resolve().parent
        root_dir = core_dir.parent

        candidates = [
            root_dir / "models" / "best.pt",
            root_dir / "models" / "best.onnx",
            root_dir / "models" / "yolo11n.pt",
        ]

        if path:
            candidates.insert(0, Path(path))
            candidates.insert(1, root_dir / path)

        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve())

        raise FileNotFoundError(
            f"Could not find model weights. Checked candidates:\n"
            + "\n".join(str(c) for c in candidates)
        )

    def detect(
        self,
        image: np.ndarray,
        conf: Optional[float] = None,
        imgsz: int = 640,
    ) -> List[DetectionResult]:
        """
        Run inference on a single image frame (BGR numpy array).
        Returns a list of DetectionResult objects.
        """
        threshold = conf if conf is not None else self.conf_threshold
        h, w = image.shape[:2]

        results = self.model.predict(
            image,
            conf=threshold,
            iou=self.iou_threshold,
            imgsz=imgsz,
            device=self.device,
            verbose=False,
        )[0]

        detections: List[DetectionResult] = []
        boxes = results.boxes

        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                cls_id = int(box.cls.item())
                score = float(box.conf.item())
                cls_name = self.class_names.get(cls_id, str(cls_id))
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

                # Clip coordinates within image bounds
                x1 = max(0, min(w - 1, x1))
                y1 = max(0, min(h - 1, y1))
                x2 = max(0, min(w, x2))
                y2 = max(0, min(h, y2))

                detections.append(
                    DetectionResult(
                        bbox=[x1, y1, x2, y2],
                        class_id=cls_id,
                        class_name=cls_name,
                        confidence=score,
                    )
                )

        return detections

    def filter_by_class(
        self, detections: List[DetectionResult], class_name: str
    ) -> List[DetectionResult]:
        """Filter detections by class name ('vehicle' or 'number_plate')."""
        return [d for d in detections if d.class_name.lower() == class_name.lower()]
