"""Unit coverage for the live YOLO vehicle overlay and its stable tracker.

The model is deliberately faked here: these tests exercise the important
post-model guarantees (one box per vehicle, track continuity, low-confidence
occlusion recovery and no repeated inference for the same live packet) without
downloading weights or contacting a camera.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.core.config import settings
from app.services.vehicle_detection_service import VehicleDetectionService


class _Array:
    """Tiny torch-like array wrapper used by an Ultralytics result fake."""

    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self.values


class _Boxes:
    def __init__(self, boxes, confidences, classes):
        self.xyxy = _Array(boxes)
        self.conf = _Array(confidences)
        self.cls = _Array(classes)


class _Result:
    def __init__(self, boxes, confidences, classes):
        self.boxes = _Boxes(boxes, confidences, classes)


class _FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def predict(self, _frame, **_kwargs):
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        boxes, confidences, classes = self.responses[index]
        return [_Result(boxes, confidences, classes)]


@pytest.fixture
def detector_settings(monkeypatch):
    values = {
        "VEHICLE_DETECTION_ENABLED": True,
        "CONFIDENCE_THRESHOLD": 0.35,
        "DETECTION_LOW_CONFIDENCE": 0.20,
        "DETECTION_EVERY_N_FRAMES": 1,
        "DETECTION_IMGSZ": 640,
        "DETECTION_DEVICE": "cpu",
        "DETECTION_NMS_IOU_THRESHOLD": 0.70,
        "DETECTION_DUPLICATE_IOU_THRESHOLD": 0.82,
        "DETECTION_MAX_DETECTIONS": 300,
        "DETECTION_MIN_BOX_AREA": 4.0,
        "DETECTION_INCLUDE_BICYCLES": True,
        "DETECTION_TRACK_MAX_AGE_SEC": 1.25,
        "DETECTION_TRACK_MIN_HITS": 1,
        "DETECTION_LOW_CONFIDENCE_CONFIRM_HITS": 2,
        "DETECTION_TRACK_IOU_THRESHOLD": 0.18,
        "DETECTION_TRACK_CENTER_DISTANCE": 1.35,
        "DETECTION_TILE_GRID": 1,
        "DETECTION_TILE_OVERLAP": 0.20,
        "DETECTION_TILE_MIN_FRAME_EDGE": 1400,
        "DETECTION_TILE_EVERY_N_INFERENCES": 4,
        "DETECTION_SHOW_TRACK_IDS": False,
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value, raising=False)


def _service_with(responses) -> tuple[VehicleDetectionService, _FakeModel]:
    service = VehicleDetectionService()
    fake = _FakeModel(responses)
    # Skip lazy import/download: the rest of the service interacts with model
    # results exactly as it would with Ultralytics Boxes.
    service._model = fake
    return service, fake


def test_model_results_keep_nearby_vehicles_and_drop_duplicate_boxes(detector_settings):
    service, _ = _service_with(
        [
            (
                # First two are the same car; third is a separate adjacent car;
                # fourth proves the supported bicycle class is retained.
                [[10, 10, 70, 70], [11, 11, 71, 71], [78, 12, 138, 72], [150, 20, 168, 55]],
                [0.94, 0.88, 0.86, 0.78],
                [2, 2, 2, 1],
            )
        ]
    )

    detections = service.detect(np.zeros((180, 240, 3), dtype=np.uint8))

    assert len(detections) == 3
    assert [d.class_name for d in detections] == ["car", "car", "bicycle"]
    assert all(d.confidence >= 0.20 for d in detections)


def test_tiled_inference_offsets_boxes_to_source_coordinates_and_deduplicates(detector_settings, monkeypatch):
    monkeypatch.setattr(settings, "DETECTION_TILE_GRID", 2, raising=False)
    monkeypatch.setattr(settings, "DETECTION_TILE_MIN_FRAME_EDGE", 100, raising=False)
    empty = ([], [], [])
    service, fake = _service_with(
        [
            # Full frame sees the car, then the top-right tile sees the same
            # car at tile-relative coordinates x=32..62 (tile starts at 88).
            ([[120, 20, 150, 50]], [0.80], [2]),
            empty,
            ([[32, 20, 62, 50]], [0.92], [2]),
            empty,
            empty,
        ]
    )

    detections = service.detect(np.zeros((100, 200, 3), dtype=np.uint8), use_tiling=True)

    assert fake.calls == 5  # one full-frame pass + four overlapping tiles
    assert len(detections) == 1
    assert detections[0].xyxy == (120, 20, 150, 50)
    assert detections[0].confidence == pytest.approx(0.92)


def test_multi_vehicle_tracks_stay_distinct_and_move_between_frames(detector_settings):
    service, _ = _service_with(
        [
            ([[10, 20, 60, 70], [130, 20, 180, 70]], [0.92, 0.91], [2, 3]),
            ([[17, 21, 67, 71], [123, 20, 173, 70]], [0.90, 0.89], [2, 3]),
        ]
    )
    frame = np.zeros((120, 220, 3), dtype=np.uint8)

    service.annotate("view-a", frame.copy(), pts_ms=0.0, frame_key=1)
    first = service.tracks_for("view-a")
    service.annotate("view-a", frame.copy(), pts_ms=80.0, frame_key=2)
    second = service.tracks_for("view-a")

    assert len(first) == len(second) == 2
    ids_first = {track.class_name: track.track_id for track in first}
    ids_second = {track.class_name: track.track_id for track in second}
    assert ids_first == ids_second
    assert next(track for track in second if track.class_name == "car").x1 > 10
    assert next(track for track in second if track.class_name == "motorcycle").x1 < 130


def test_low_confidence_detection_rescues_existing_track_and_duplicate_packet_skips_model(detector_settings, monkeypatch):
    monkeypatch.setattr(settings, "DETECTION_EVERY_N_FRAMES", 2, raising=False)
    service, fake = _service_with(
        [
            ([[40, 30, 100, 90]], [0.93], [2]),
            ([[46, 31, 106, 91]], [0.24], [2]),
        ]
    )
    frame = np.zeros((130, 180, 3), dtype=np.uint8)

    # Strong first sighting creates an immediately visible track.
    service.annotate("view-b", frame.copy(), pts_ms=0.0, frame_key=1)
    first_id = service.tracks_for("view-b")[0].track_id
    # A skipped model frame still advances the tracker rather than retaining a
    # frozen cache. The next low-confidence result matches the existing ID.
    service.annotate("view-b", frame.copy(), pts_ms=40.0, frame_key=2)
    service.annotate("view-b", frame.copy(), pts_ms=80.0, frame_key=3)
    tracks = service.tracks_for("view-b")

    assert len(tracks) == 1
    assert tracks[0].track_id == first_id
    assert fake.calls == 2

    # Re-emitting the same resident FramePacket only redraws; it must not
    # invoke YOLO again. The camera generator consumes a discontinuity flag
    # once, before it emits this duplicate packet.
    service.annotate("view-b", frame.copy(), pts_ms=80.0, frame_key=3)
    assert fake.calls == 2
    assert service.tracks_for("view-b")[0].track_id == first_id


def test_resident_packet_inference_is_shared_but_tracks_stay_session_isolated(detector_settings):
    response = ([[20, 20, 70, 70]], [0.90], [2])
    service, fake = _service_with([response])
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    shared_key = ("camera-a", ("resident", 14))

    service.annotate(
        "camera-a:operator-1",
        frame.copy(),
        pts_ms=0,
        frame_key=("resident", 14),
        shared_frame_key=shared_key,
    )
    service.annotate(
        "camera-a:operator-2",
        frame.copy(),
        pts_ms=0,
        frame_key=("resident", 14),
        shared_frame_key=shared_key,
    )

    assert fake.calls == 1
    assert service.tracks_for("camera-a:operator-1")[0].track_id == 1
    assert service.tracks_for("camera-a:operator-2")[0].track_id == 1


def test_track_state_is_isolated_per_view_session(detector_settings):
    response = ([[20, 20, 70, 70]], [0.90], [2])
    service, fake = _service_with([response])
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    service.annotate("camera-a:operator-1", frame.copy(), pts_ms=0, frame_key=1)
    service.annotate("camera-a:operator-2", frame.copy(), pts_ms=0, frame_key=1)

    assert service.tracks_for("camera-a:operator-1")[0].track_id == 1
    assert service.tracks_for("camera-a:operator-2")[0].track_id == 1
    assert fake.calls == 2
    service.forget("camera-a:operator-1")
    assert service.tracks_for("camera-a:operator-2")[0].track_id == 1
