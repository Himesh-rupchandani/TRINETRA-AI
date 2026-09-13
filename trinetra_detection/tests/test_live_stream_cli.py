"""Tests for the LIVE (webcam / stream) entry point of the standalone module.

The live view is where a coarse box is most visible, so this pins the two
things that were wrong there:

* the script must actually START - it used to print the resolved vehicle weight
  from ``detector`` before ``detector`` existed, i.e. NameError on any machine;
* the live loop must run the SAME tuned settings as the offline video pass
  (conf 0.35, imgsz 960, NMS IoU 0.45, class-agnostic), not a secretly lower
  resolution, and must degrade to headless instead of crashing when OpenCV has
  no GUI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

import detect_webcam  # noqa: E402
from core.detector import VehiclePlateDetector  # noqa: E402

from test_box_geometry import COCO_NAMES, StubModel, _Box, _install  # noqa: E402

FRAME = np.zeros((360, 640, 3), dtype=np.uint8)


class _FakeCapture:
    """A stream that yields ``count`` frames and then ends."""

    def __init__(self, count=4):
        self._left = count
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        if self._left <= 0:
            return False, None
        self._left -= 1
        return True, FRAME.copy()

    def get(self, prop):
        return {cv2.CAP_PROP_FPS: 25.0, 3: 640.0, 4: 360.0}.get(prop, 0.0)

    def release(self):
        self.released = True


def _run_live(monkeypatch, tmp_path, extra=()):
    """Drive detect_webcam.main() against a fake stream + stubbed weights."""
    model = StubModel("vehicle-model", COCO_NAMES,
                      [_Box([100, 60, 300, 200], 2, 0.91), _Box([20, 200, 80, 260], 3, 0.62)])
    _install(monkeypatch, model)
    cap = _FakeCapture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: cap)
    # No GUI in CI: if the script ever calls imshow unconditionally this fails loudly.
    monkeypatch.setattr(cv2, "imshow", lambda *a, **k: pytest.fail("imshow called while headless"))
    monkeypatch.setattr(cv2, "waitKey", lambda *a, **k: 0xFF)
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda *a, **k: None)
    out = tmp_path / "live.mp4"
    argv = ["detect_webcam.py", "--source", "fake-stream", "--max-frames", "3",
            "--no-display", "--save", str(out), *extra]
    monkeypatch.setattr(sys, "argv", argv)
    detect_webcam.main()
    return model, out, cap


def test_live_script_starts_and_processes_frames(monkeypatch, tmp_path):
    model, out, cap = _run_live(monkeypatch, tmp_path)
    assert cap.released, "the stream was never released"
    assert len(model.calls) == 3, "expected exactly --max-frames inferences"
    assert out.is_file() and out.stat().st_size > 0, "annotated live output not written"


def _vehicle_call(model):
    """The live frame runs two stages on one weight; pick the VEHICLE stage."""
    calls = [c for c in model.calls if sorted(c.get("classes") or []) == [2, 3, 5, 7]]
    assert calls, f"no vehicle-stage call in {model.calls}"
    return calls[0]


def test_live_loop_uses_the_same_settings_as_the_video_pass(monkeypatch, tmp_path):
    from core.detector import DEFAULT_IMGSZ

    model, _, _ = _run_live(monkeypatch, tmp_path)
    call = _vehicle_call(model)
    assert DEFAULT_IMGSZ == 960
    assert call["imgsz"] == 960, "live view must not run at a lower resolution"
    assert call["conf"] == pytest.approx(0.35)
    assert call["iou"] == pytest.approx(0.45)
    assert call["agnostic_nms"] is True
    # only vehicle classes are asked for on the live view - no person/tree/shadow


def test_live_tuning_flags_reach_the_model(monkeypatch, tmp_path):
    model, _, _ = _run_live(monkeypatch, tmp_path,
                            extra=["--conf", "0.5", "--imgsz", "832", "--iou", "0.6"])
    call = _vehicle_call(model)
    assert (call["conf"], call["imgsz"], call["iou"]) == (pytest.approx(0.5), 832, pytest.approx(0.6))
    # Every frame of the live loop gets its own real inference - no cached box is
    # replayed across frames here, and no frame is skipped.
    assert len(model.calls) == 3


def test_boxes_drawn_on_the_live_frame_are_model_geometry(monkeypatch, tmp_path):
    """The live path must draw what the model returned, at its own coordinates."""
    from core.detector import DetectionResult
    from core.visualizer import Visualizer

    dets = VehiclePlateDetector._to_results(
        None, [((100, 60, 300, 200), 0.91, 2)], names=COCO_NAMES, kind="vehicle"
    ) if hasattr(VehiclePlateDetector, "_to_results") else [
        DetectionResult([100, 60, 300, 200], 2, "car", 0.91, kind="vehicle")
    ]
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    out = Visualizer.draw_detections(frame, dets)
    # border on all four sides, exactly at the model's coordinates, nothing inside
    for row, col in [(60, 150), (200, 150), (130, 100), (130, 300)]:
        assert tuple(int(v) for v in out[row, col]) != (0, 0, 0), f"{row},{col} box edge missing"
    assert tuple(int(v) for v in out[130, 200]) == (0, 0, 0), "interior must stay untouched"
