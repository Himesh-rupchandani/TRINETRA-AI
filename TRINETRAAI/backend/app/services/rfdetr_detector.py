"""
RF-DETR detection backend.

`RF-DETR <https://github.com/roboflow/rf-detr>`_ is Roboflow's real-time
DETR architecture (SOTA on COCO, ICLR 2026). This module is the adapter that
lets TRINETRA AI use it anywhere a vehicle/plate detector is needed, without
making the rest of the project depend on it:

    from .rfdetr_detector import rfdetr_detector
    if rfdetr_detector.ready:
        boxes = rfdetr_detector.detect(bgr_frame)

Two jobs, both strictly optional:

1. **Vehicle detection** — the COCO-pretrained checkpoint finds
   ``car / motorcycle / bus / truck`` out of the box, so it can stand in for
   (or be preferred over) the existing YOLO11 vehicle detector.
2. **Number-plate localisation** — if you fine-tune RF-DETR on your own plate
   data and point ``PLATE_RFDETR_MODEL_PATH`` at the checkpoint, it becomes the
   first-choice plate proposer, ahead of the classical OpenCV proposer.

Design rules that keep this safe to deploy:

* ``rfdetr`` (and torch) are imported **lazily**. If the package is missing,
  :attr:`available` is ``False``, :meth:`load` is a no-op, and every caller
  silently keeps using its existing detector. Nothing in the app breaks.
* The model is built **once** and shared by every thread; the build is guarded
  by a lock and an ``_attempted`` flag so parallel video-analysis workers do
  not race each other into building two copies of a ~100 MB model.
* :meth:`detect` never raises. A broken model degrades to ``[]`` (no boxes),
  which downstream code already treats as "nothing detected here".

COCO class-id convention
------------------------
RF-DETR's COCO models emit **0-indexed** class ids over
``rfdetr.assets.coco_classes.COCO_CLASS_NAMES`` (i.e. the COCO category ids
sorted ascending, then indexed): ``0 -> person(1)``, ``2 -> car(3)``, ...
We map ids to *names* rather than trusting raw numbers, so a future checkpoint
with a different label order still behaves correctly.
"""
from __future__ import annotations

import os
import threading
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from ..core.config import settings
from ..core.logging_config import logger

# Road vehicles we care about, by COCO name.
VEHICLE_CLASS_NAMES = frozenset({"car", "motorcycle", "bus", "truck"})

# Fallback copy of rfdetr's COCO class order (index -> name). Used only when
# the installed rfdetr does not expose COCO_CLASS_NAMES.
_FALLBACK_COCO_CLASS_NAMES: Tuple[str, ...] = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
)

# Variant name -> rfdetr class name. Kept as a dict so a bad config value
# falls back instead of crashing the detector at import time.
_VARIANTS = {
    "nano": "RFDETRNano",
    "small": "RFDETRSmall",
    "medium": "RFDETRMedium",
    "base": "RFDETRBase",
    "large": "RFDETRLarge",
}


def _coco_class_names() -> Tuple[str, ...]:
    """COCO class names in RF-DETR's index order (0-indexed)."""
    try:
        from rfdetr.assets.coco_classes import COCO_CLASS_NAMES

        return tuple(COCO_CLASS_NAMES)
    except Exception:
        return _FALLBACK_COCO_CLASS_NAMES


class RFDETRDetector:
    """
    Lazy, thread-safe wrapper around one RF-DETR model.

    One instance serves vehicle detection. A *separate* instance (created
    on demand) serves plate detection when fine-tuned weights are supplied,
    because the two checkpoints have different class heads.
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._plate_model: Any = None
        self._lock = threading.Lock()
        self._attempted = False
        self._plate_attempted = False
        self._error: Optional[str] = None
        self._plate_error: Optional[str] = None
        self._label: str = ""
        self._names: Tuple[str, ...] = ()
        self.last_inference_ms: Optional[float] = None

    # ------------------------------------------------------------- lifecycle
    @property
    def available(self) -> bool:
        """``True`` when the ``rfdetr`` package can be imported at all."""
        if getattr(settings, "RFDETR_ENABLED", True) is False:
            return False
        try:
            import rfdetr  # noqa: F401

            return True
        except Exception:
            return False

    @property
    def ready(self) -> bool:
        """:meth:`load` has succeeded and :meth:`detect` can be called."""
        return self._model is not None

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def label(self) -> str:
        """Human-readable backend name for logs/UI, e.g. ``rfdetr:base``."""
        if self.ready:
            return self._label or "rfdetr"
        return f"rfdetr-unavailable ({self._error or 'not loaded'})"

    def _build(self) -> Any:
        """Construct the model object. Raises on any failure."""
        import time

        import rfdetr

        variant = str(getattr(settings, "RFDETR_VARIANT", "base") or "base").strip().lower()
        cls_name = _VARIANTS.get(variant, "RFDETRBase")
        cls = getattr(rfdetr, cls_name, None) or rfdetr.RFDETRBase

        kwargs: dict = {}
        weights = (getattr(settings, "RFDETR_PRETRAIN_WEIGHTS", "") or "").strip()
        if weights and os.path.isfile(weights):
            # Custom checkpoint: skip the published-weights download.
            kwargs["pretrain_weights"] = weights
        resolution = int(getattr(settings, "RFDETR_RESOLUTION", 0) or 0)
        if resolution > 0:
            kwargs["resolution"] = resolution

        logger.info(f"[RFDETR] Loading {cls_name} (kwargs={kwargs or 'defaults'}) …")
        t0 = time.perf_counter()
        model = cls(**kwargs)

        if getattr(settings, "RFDETR_OPTIMIZE", True):
            try:
                model.optimize_for_inference()
            except Exception as exc:  # optimisation is a bonus, never fatal
                logger.debug(f"[RFDETR] optimize_for_inference skipped: {exc}")

        self._names = _coco_class_names()
        self._label = f"rfdetr:{variant}"
        logger.info(f"[RFDETR] {cls_name} ready in {time.perf_counter() - t0:.1f}s")
        return model

    def load(self) -> Optional[Any]:
        """Build the model once. Returns it, or ``None`` if unavailable."""
        if self._model is not None or self._attempted:
            return self._model
        with self._lock:
            if self._model is not None or self._attempted:
                return self._model
            try:
                self._model = self._build()
            except Exception as exc:
                self._error = str(exc) or exc.__class__.__name__
                logger.warning(
                    f"[RFDETR] unavailable ({self._error}). "
                    "Falling back to the existing YOLO/OpenCV detector."
                )
            finally:
                self._attempted = True
        return self._model

    def unload(self) -> None:
        """Drop the model so a later :meth:`load` retries (used by tests)."""
        with self._lock:
            self._model = None
            self._plate_model = None
            self._attempted = False
            self._plate_attempted = False
            self._error = None
            self._plate_error = None
            self._label = ""

    # ------------------------------------------------------------- inference
    def detect(
        self,
        frame: np.ndarray,
        threshold: Optional[float] = None,
        classes: Optional[Sequence[str]] = None,
    ) -> List[Tuple[int, int, int, int, str, float]]:
        """
        Run RF-DETR on one **BGR** frame (OpenCV's native order).

        Returns ``[(x1, y1, x2, y2, class_name, confidence), ...]`` in pixel
        coordinates — the same tuple shape :class:`SimpleTracker` already
        consumes. Never raises; returns ``[]`` when unavailable.
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            return []
        model = self.load()
        if model is None:
            return []

        import time

        conf = float(
            threshold
            if threshold is not None
            else getattr(settings, "CONFIDENCE_THRESHOLD", 0.45)
        )
        wanted = frozenset(classes) if classes else VEHICLE_CLASS_NAMES

        try:
            rgb = frame[:, :, ::-1]  # BGR -> RGB; no copy, just a view
            t0 = time.perf_counter()
            det = model.predict(np.ascontiguousarray(rgb), threshold=conf)
            self.last_inference_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as exc:
            logger.error(f"[RFDETR] inference failed: {exc}")
            return []

        return self._to_tuples(det, wanted, frame.shape)

    def _to_tuples(
        self, det: Any, wanted: frozenset, shape: Sequence[int]
    ) -> List[Tuple[int, int, int, int, str, float]]:
        """Convert a supervision ``Detections`` into plain pixel tuples."""
        try:
            xyxy = np.asarray(det.xyxy, dtype=float).reshape(-1, 4)
            conf = np.asarray(det.confidence, dtype=float).reshape(-1)
            cls_ids = np.asarray(det.class_id, dtype=int).reshape(-1)
        except Exception as exc:
            logger.error(f"[RFDETR] unexpected prediction payload: {exc}")
            return []

        h = int(shape[0]) if len(shape) > 0 else 0
        w = int(shape[1]) if len(shape) > 1 else 0
        names = self._names or _coco_class_names()

        out: List[Tuple[int, int, int, int, str, float]] = []
        for (x1, y1, x2, y2), c, cid in zip(xyxy, conf, cls_ids):
            name = names[cid] if 0 <= cid < len(names) else str(cid)
            if name not in wanted:
                continue
            x1, x2 = max(0, int(round(x1))), min(w, int(round(x2)))
            y1, y2 = max(0, int(round(y1))), min(h, int(round(y2)))
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            out.append((x1, y1, x2, y2, name, float(c)))
        return out

    # ------------------------------------------------- optional plate model
    @property
    def plate_ready(self) -> bool:
        return self._plate_model is not None

    def _resolve_plate_weights(self) -> Optional[str]:
        configured = (getattr(settings, "PLATE_RFDETR_MODEL_PATH", "") or "").strip()
        if not configured:
            return None
        if os.path.isfile(configured):
            return configured
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidate = os.path.join(backend_root, configured)
        return candidate if os.path.isfile(candidate) else None

    def load_plate_model(self) -> Optional[Any]:
        """
        Load a **fine-tuned** RF-DETR plate detector (single class ``plate``).

        Returns ``None`` when no checkpoint is configured — the pipeline then
        uses the classical OpenCV proposer exactly as it did before.
        """
        if self._plate_model is not None or self._plate_attempted:
            return self._plate_model
        with self._lock:
            if self._plate_model is not None or self._plate_attempted:
                return self._plate_model
            try:
                path = self._resolve_plate_weights()
                if not path:
                    return None
                import rfdetr

                variant = str(
                    getattr(settings, "PLATE_RFDETR_VARIANT", "nano") or "nano"
                ).strip().lower()
                cls_name = _VARIANTS.get(variant, "RFDETRNano")
                cls = getattr(rfdetr, cls_name, None) or rfdetr.RFDETRNano
                logger.info(f"[RFDETR] Loading fine-tuned plate detector: {path}")
                model = cls(pretrain_weights=path, num_classes=1)
                try:
                    model.optimize_for_inference()
                except Exception:
                    pass
                self._plate_model = model
            except Exception as exc:
                self._plate_error = str(exc) or exc.__class__.__name__
                logger.warning(
                    f"[RFDETR] plate detector unavailable ({self._plate_error}); "
                    "using the classical plate proposer."
                )
            finally:
                self._plate_attempted = True
        return self._plate_model

    def detect_plates(
        self, crop: np.ndarray, threshold: Optional[float] = None
    ) -> List[Tuple[int, int, int, int, float]]:
        """
        Fine-tuned plate boxes inside one vehicle crop.

        Returns ``[(x1, y1, x2, y2, confidence), ...]`` in **crop** pixel
        coordinates, or ``[]`` when no fine-tuned checkpoint is configured.
        """
        if crop is None or getattr(crop, "size", 0) == 0:
            return []
        model = self.load_plate_model()
        if model is None:
            return []
        conf = float(
            threshold
            if threshold is not None
            else getattr(settings, "PLATE_CONF_THRESHOLD", 0.25)
        )
        try:
            rgb = np.ascontiguousarray(crop[:, :, ::-1])
            det = model.predict(rgb, threshold=conf)
            xyxy = np.asarray(det.xyxy, dtype=float).reshape(-1, 4)
            scores = np.asarray(det.confidence, dtype=float).reshape(-1)
        except Exception as exc:
            logger.error(f"[RFDETR] plate inference failed: {exc}")
            return []

        h, w = crop.shape[:2]
        out: List[Tuple[int, int, int, int, float]] = []
        for (x1, y1, x2, y2), c in zip(xyxy, scores):
            x1, x2 = max(0, int(round(x1))), min(w, int(round(x2)))
            y1, y2 = max(0, int(round(y1))), min(h, int(round(y2)))
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            out.append((x1, y1, x2, y2, float(c)))
        out.sort(key=lambda b: -b[4])
        return out


# Global singleton — the checkpoint is loaded once per backend process.
rfdetr_detector = RFDETRDetector()
