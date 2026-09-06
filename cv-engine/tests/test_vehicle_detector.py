"""Offline tests for YOLO result handling in the CV-engine vehicle detector."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from detection.vehicle_detector import Detection, VehicleDetector


class _Array:
    def __init__(self, value):
        self.value = np.asarray(value, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self.value


class _Boxes:
    def __init__(self, boxes, scores, classes):
        self.xyxy = _Array(boxes)
        self.conf = _Array(scores)
        self.cls = _Array(classes)


class _Result:
    def __init__(self, boxes, scores, classes):
        self.boxes = _Boxes(boxes, scores, classes)


class _Model:
    def __init__(self, replies, delay=0.0):
        self.replies = list(replies)
        self.calls = 0
        self.delay = delay
        self.active = 0
        self.peak_active = 0

    def predict(self, _image, **_kwargs):
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            reply = self.replies[min(self.calls, len(self.replies) - 1)]
            self.calls += 1
            return [_Result(*reply)]
        finally:
            self.active -= 1


def _detector(replies, **kwargs):
    detector = VehicleDetector(**kwargs)
    model = _Model(replies)
    detector._model = model  # Model loading/weights are intentionally not part of unit tests.
    return detector, model


def test_default_classes_include_all_supported_road_vehicle_categories():
    detector = VehicleDetector()
    assert detector.class_ids == [1, 2, 3, 5, 7]
    assert VehicleDetector(include_bicycles=False).class_ids == [2, 3, 5, 7]
    assert detector._predict_kwargs()["agnostic_nms"] is False


def test_tiled_detections_are_offset_clipped_and_not_duplicated():
    empty = ([], [], [])
    detector, model = _detector(
        [
            # full frame; then top-left, top-right, bottom-left, bottom-right
            ([[120, 20, 150, 50]], [0.80], [2]),
            empty,
            ([[32, 20, 62, 50]], [0.93], [2]),
            empty,
            empty,
        ],
        tile_grid=2,
        tile_min_frame_edge=100,
        tile_overlap=0.20,
    )

    detections = detector.detect(np.zeros((100, 200, 3), dtype=np.uint8), camera_id="cam1", pts_ms=20.0)

    assert model.calls == 5
    assert len(detections) == 1
    detection = detections[0]
    assert detection.bbox == [120.0, 20.0, 150.0, 50.0]
    assert detection.confidence == pytest.approx(0.93)
    assert detection.camera_id == "cam1"
    assert detection.pts_ms == 20.0


def test_nearby_distinct_vehicles_are_not_removed_by_duplicate_guard():
    detector = VehicleDetector(duplicate_iou_threshold=0.82)
    deduplicated = detector._deduplicate(
        [
            Detection([10, 10, 70, 70], "car", 0.95),
            Detection([11, 11, 71, 71], "car", 0.85),  # duplicate of first
            Detection([73, 10, 133, 70], "car", 0.90),  # adjacent separate car
            Detection([150, 10, 172, 50], "bicycle", 0.75),
        ]
    )

    assert [(item.class_name, item.bbox) for item in deduplicated] == [
        ("car", [10, 10, 70, 70]),
        ("car", [73, 10, 133, 70]),
        ("bicycle", [150, 10, 172, 50]),
    ]


def test_shared_model_inference_is_serialized_between_camera_threads():
    detector, model = _detector(
        [([[10, 10, 30, 30]], [0.9], [2])],
        tile_grid=1,
    )
    model.delay = 0.03
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    threads = [threading.Thread(target=detector.detect, args=(frame,)) for _ in range(2)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=1.0)

    assert model.calls == 2
    assert model.peak_active == 1
