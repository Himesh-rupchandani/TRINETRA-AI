"""
Vehicle and Number Plate Detector using YOLO11.
Provides a clean, modular API for detecting vehicles and license plates.

Bounding-box policy (important — this is what the visualisation depends on):

* Every box drawn as a VEHICLE comes from the detector's own ``xyxy`` output.
  Nothing here pads, grows, recentres, snaps to a grid or clamps a box to a
  region of interest. The only geometric operation performed is clipping to
  the real frame bounds (a box may never reach outside the image).
* The frames are handed to Ultralytics at their native resolution; Ultralytics
  letterboxes internally for inference and returns coordinates already mapped
  back to the input array, so no external rescale correction is needed (and
  none is applied — applying one would *create* the oversized/offset boxes).
* Vehicle boxes come from a model that was trained per vehicle CLASS
  (car / motorcycle / bus / truck). The fine-tuned 2-class weights
  (``vehicle`` + ``number_plate``) are still used for the plate boxes, but
  their single coarse ``vehicle`` class is annotated around whole clusters of
  parked bikes, which is what produced boxes 3-5x larger than the vehicle
  itself (measured: one box covering 74.9% of a 1280x720 frame). When such a
  model is loaded, a per-class COCO weight is used for vehicles instead —
  see ``_resolve_vehicle_model``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import cv2
import numpy as np

# Class names that mean "number plate" on the fine-tuned weights.
PLATE_CLASS_NAMES = {
    "number_plate", "number plate", "numberplate", "plate",
    "license_plate", "licence_plate", "reg_plate", "no_plate",
}
# Road-vehicle classes of the official COCO weights. Anything else the model
# can name (person, bench, traffic light, ...) is never a vehicle and is
# filtered out *inside* the model call via ``classes=``, not afterwards.
COCO_VEHICLE_CLASS_IDS: Dict[int, str] = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
# Class names treated as vehicles on any non-COCO (fine-tuned) weight.
GENERIC_VEHICLE_CLASS_NAMES = {"vehicle", "car", "bus", "truck", "motorcycle", "auto",
                             "auto-rickshaw", "van", "scooter", "jeep"}

# Inference resolution. 640 was merging neighbouring vehicles into one box and
# missing distant ones entirely (measured on a night traffic frame: 0 vehicles
# at 640 vs 34 at 1024 with the same weight). 960 keeps that gain at ~1.5x cost.
DEFAULT_IMGSZ = 960

# Plate stage keeps its historical settings (see __init__): conf 0.25 @ imgsz 640.
PLATE_IMGSZ = 640
PLATE_CONF_CEILING = 0.25  # plates never need a *stricter* cut than this


@dataclass
class DetectionResult:
    """Represents a single detected object (Vehicle or Number Plate)."""
    bbox: List[int]        # [x1, y1, x2, y2] in the ORIGINAL frame's pixels
    class_id: int          # id as reported by the model that produced the box
    class_name: str        # 'car' | 'motorcycle' | 'bus' | 'truck' | 'vehicle' | 'number_plate'
    confidence: float      # 0.0 - 1.0
    # Which *role* the box plays. Decoupled from class_name so that a per-class
    # vehicle model ('car') and the coarse fine-tuned model ('vehicle') both
    # render the same way, and plate code keeps keying off the plate class.
    kind: str = "vehicle"  # 'vehicle' | 'plate'

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

    @property
    def is_vehicle(self) -> bool:
        return self.kind == "vehicle"

    @property
    def is_plate(self) -> bool:
        return self.kind == "plate"

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
            "kind": self.kind,
            "confidence": round(self.confidence, 4),
        }


def _class_name_of(model_names: Any, cls_id: int) -> str:
    """Read a class name out of whatever mapping Ultralytics returned."""
    try:
        if isinstance(model_names, dict):
            return str(model_names.get(cls_id, str(cls_id)))
        return str(model_names[cls_id])
    except Exception:
        return str(cls_id)


class VehiclePlateDetector:
    """
    High-level detector for vehicles and number plates using YOLO11 weights.

    Two weights can be in play:
      * ``model_path``      — the project's fine-tuned weights (plate boxes; also
                              vehicle boxes when they are per-class).
      * ``vehicle_model_path`` — a per-class vehicle weight used for the green
                              vehicle boxes when the fine-tuned weight only has
                              a coarse single ``vehicle`` class.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        device: Optional[str] = None,
        imgsz: int = DEFAULT_IMGSZ,
        vehicle_model_path: Optional[str] = None,
        use_coco_vehicles: bool = True,
        plate_conf_threshold: float = PLATE_CONF_CEILING,
        plate_imgsz: int = PLATE_IMGSZ,
    ):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.imgsz = imgsz
        # The plate stage keeps the settings it has always used (conf 0.25,
        # imgsz 640). Raising the *vehicle* confidence or inference size must
        # not silently change number-plate recall — and a bigger imgsz makes the
        # coarse plate head fire on whole road sections. Keeping them separate keeps
        # ANPR behaviour exactly as before while vehicles get tighter.
        self.plate_conf_threshold = plate_conf_threshold
        self.plate_imgsz = plate_imgsz
        self.device = device
        self.model_path = self._resolve_model_path(model_path)
        self._use_coco_vehicles = use_coco_vehicles

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

        # --- which weight produces which box ------------------------------
        # The fine-tuned 2-class weights describe a whole cluster of parked
        # vehicles as ONE 'vehicle' label, which is what produced boxes 3-5x
        # larger than the vehicle. Their plate class is still the best plate
        # localiser in the repo, so: plates always come from `self.model`,
        # vehicles come from a per-class weight when `self.model` is coarse.
        self.vehicle_model = self.model
        self.vehicle_model_path: Optional[str] = None
        self.vehicle_class_ids: Optional[List[int]] = self._ids_for(self.model, "vehicle")
        if self._use_coco_vehicles and self._is_coarse_vehicle_model():
            resolved = self._resolve_vehicle_model(vehicle_model_path)
            if resolved:
                print(f"[Detector] Vehicles: per-class weight {resolved}")
                self.vehicle_model = YOLO(resolved)
                self.vehicle_model_path = resolved
                self.vehicle_class_ids = self._ids_for(self.vehicle_model, "vehicle")
            else:
                print("[Detector] WARNING: no per-class vehicle weight found; "
                      "vehicle boxes will come from the coarse fine-tuned model.")
        self.plate_model = self.model
        self.plate_class_ids: Optional[List[int]] = self._ids_for(self.plate_model, "plate")
        print(f"[Detector] Vehicle classes: {self.vehicle_class_ids or 'all vehicle-named'} | "
              f"plate classes: {self.plate_class_ids or 'none (no plate head)'}")

    def _ids_for(self, model, role: str) -> Optional[List[int]]:
        """Class ids of `model` that mean *vehicle* or *plate*.

        Reading the ids from the weight itself (rather than assuming them) is
        what lets one code path serve both the fine-tuned 2-class model and a
        COCO model — and it is how non-vehicle classes (person, bench, traffic
        light) are excluded *inside* the model call instead of by post-hoc
        box surgery.
        """
        names = getattr(model, "names", None) or {}
        try:
            items = list(names.items())
        except AttributeError:
            items = list(enumerate(names))
        ids: List[int] = []
        for cid, cname in items:
            low = str(cname).lower().replace("-", "_").replace(" ", "_")
            if role == "plate":
                if low in PLATE_CLASS_NAMES:
                    ids.append(int(cid))
            else:
                if low in PLATE_CLASS_NAMES:
                    continue
                if low in COCO_VEHICLE_CLASS_IDS.values() or low in GENERIC_VEHICLE_CLASS_NAMES:
                    ids.append(int(cid))
        return sorted(ids) or None

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

    def _is_coarse_vehicle_model(self) -> bool:
        """True when this weight has a single all-vehicles 'vehicle' class.

        That is the signature of the project's fine-tuned 2-class model
        (``0: vehicle, 1: number_plate``). A COCO weight names car / bus / ...
        separately and already gives one tight box per vehicle.
        """
        names = self.class_names or {}
        try:
            values = [str(v).lower().replace("-", "_") for v in names.values()]
        except AttributeError:
            values = [str(v).lower().replace("-", "_") for v in names]
        has_coarse = "vehicle" in values
        per_class = any(v in COCO_VEHICLE_CLASS_IDS.values() for v in values)
        return has_coarse and not per_class

    def _resolve_vehicle_model(self, path: Optional[str]) -> Optional[str]:
        """Pick the per-class weight used for vehicle boxes (best first).

        Order: explicit argument -> the backend's yolo11s (bigger, tighter on
        dense traffic) -> this module's bundled yolo11n (offline fallback).
        Returning None keeps the original single-model behaviour. Pass
        'none'/'off'/'none-please' as ``path`` to disable it explicitly.
        """
        if path and path.strip().lower() in {"none", "off", "no", "disable", "disabled"}:
            return None
        repo_root = Path(__file__).resolve().parent.parent.parent
        candidates: List[Path] = []
        if path:
            candidates += [Path(path), Path(__file__).resolve().parent.parent / path]
        candidates += [
            repo_root / "TRINETRAAI" / "backend" / "yolo11s.pt",
            repo_root / "TRINETRAAI" / "backend" / "models" / "yolo11s.pt",
            Path(__file__).resolve().parent.parent / "models" / "yolo11s.pt",
            Path(__file__).resolve().parent.parent / "models" / "yolo11n.pt",
        ]
        for c in candidates:
            try:
                if c.is_file():
                    return str(c.resolve())
            except OSError:
                continue
        return None

    # --------------------------------------------------------------- inference
    def detect(
        self,
        image: np.ndarray,
        conf: Optional[float] = None,
        imgsz: Optional[int] = None,
        classes: Optional[List[int]] = None,
    ) -> List[DetectionResult]:
        """
        Run inference on a single image frame (BGR numpy array) and return the
        vehicle boxes (green role) plus the plate boxes (gold role).

        Coordinates are the model's own, mapped back to this exact array by
        Ultralytics; they are clipped to the frame and nothing else is done.
        """
        threshold = conf if conf is not None else self.conf_threshold
        size = imgsz if imgsz is not None else self.imgsz
        # Plates keep their historical cut so tightening the vehicle stage
        # cannot quietly change number-plate recall.
        plate_conf = min(threshold, self.plate_conf_threshold)

        vehicle_classes = classes if classes is not None else self.vehicle_class_ids
        one_weight = self.plate_model is self.vehicle_model
        if one_weight and size == self.plate_imgsz:
            # Single weight, same working resolution: one pass for both roles.
            ids = sorted(set(vehicle_classes or []) | set(self.plate_class_ids or [])) or None
            dets = self._run(self.vehicle_model, image, min(threshold, plate_conf),
                             size, ids, force_kind=None)
            return [d for d in dets if d.is_plate or d.confidence >= threshold]

        detections: List[DetectionResult] = []
        detections += self._run(self.vehicle_model, image, threshold, size,
                                vehicle_classes, force_kind=None)
        if self.plate_class_ids:
            detections += self._run(self.plate_model, image, plate_conf, self.plate_imgsz,
                                    self.plate_class_ids, force_kind="plate")
        return detections

    def _run(
        self,
        model,
        image: np.ndarray,
        threshold: float,
        imgsz: int,
        classes: Optional[List[int]],
        force_kind: Optional[str],
    ) -> List[DetectionResult]:
        h, w = image.shape[:2]
        kwargs: Dict[str, Any] = dict(
            conf=threshold,
            iou=self.iou_threshold,
            imgsz=imgsz,
            device=self.device,
            verbose=False,
            # One vehicle, one box: suppress a car/bus/truck double-label of the
            # same vehicle without touching genuinely separate vehicles (NMS is
            # IoU based, so two neighbouring vehicles stay two detections).
            agnostic_nms=True,
        )
        if classes:
            kwargs["classes"] = list(classes)

        results = model.predict(image, **kwargs)
        if not results:
            return []
        results = results[0]
        boxes = results.boxes
        detections: List[DetectionResult] = []
        if boxes is None or len(boxes) == 0:
            return detections

        for box in boxes:
            cls_id = int(box.cls.item())
            score = float(box.conf.item())
            # Enforce the threshold here too: an exported weight (best.onnx)
            # can bake in its own cut, and then `conf=` alone would silently
            # let weak detections through as big green boxes.
            if score < threshold:
                continue
            cls_name = _class_name_of(model.names, cls_id)
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

            # Clip coordinates within image bounds (never enlarge — only bound).
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(x1 + 1, min(w, x2))
            y2 = max(y1 + 1, min(h, y2))
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue  # zero-area box: nothing to draw and nothing to crop

            low = cls_name.lower().replace("-", "_")
            if force_kind:
                kind = force_kind
            elif low in PLATE_CLASS_NAMES:
                kind = "plate"
            else:
                kind = "vehicle"
            # When no explicit class filter was possible (unknown weight),
            # never let a person/bench/tree become a "vehicle".
            if (kind == "vehicle" and not classes
                    and low not in GENERIC_VEHICLE_CLASS_NAMES
                    and not low.startswith(("car", "bus", "truck", "motorcycle", "vehicle"))):
                continue

            detections.append(
                DetectionResult(
                    bbox=[x1, y1, x2, y2],
                    class_id=cls_id,
                    class_name=cls_name,
                    confidence=score,
                    kind=kind,
                )
            )
        return detections

    # ------------------------------------------------------------------ filters
    def filter_by_class(
        self, detections: List[DetectionResult], class_name: str
    ) -> List[DetectionResult]:
        """Filter detections by role ('vehicle' / 'number_plate') or exact class.

        Kept for backward compatibility: ``filter_by_class(dets, "vehicle")``
        still returns every vehicle box, whatever the vehicle weight calls it
        ('vehicle', 'car', 'motorcycle', ...), and ``"number_plate"`` still
        returns the plate boxes.
        """
        want = (class_name or "").lower()
        role = "plate" if want in PLATE_CLASS_NAMES else want
        return [
            d for d in detections
            if d.kind == role or d.class_name.lower().replace("-", "_") == want
        ]

    def vehicles(self, detections: List[DetectionResult]) -> List[DetectionResult]:
        return [d for d in detections if d.is_vehicle]

    def plates(self, detections: List[DetectionResult]) -> List[DetectionResult]:
        return [d for d in detections if d.is_plate]
