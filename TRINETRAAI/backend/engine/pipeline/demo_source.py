"""
DEMO MODE frame source (spec §36).

⚠ DEMO MODE IS NOT LIVE SENTINEL MODE.

This source produces scripted FramePackets with synthetic PTS so the full
pipeline (tracking -> ANPR aggregation -> dedup -> evidence -> backend POST)
can be exercised end-to-end without a Government feed. It exists for local
development, CI and the "own feed" part of the demo. The final Government
demo MUST use the real Sentinel feed via --mode live.

The scripted detections/OCR are injected through lightweight stubs so the
demo never pretends real inference happened.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

from capture.frame_packet import CaptureState, FramePacket


@dataclass
class ScriptedVehicle:
    """A synthetic vehicle moving top->bottom through the frame."""

    plate_text: str              # e.g. "GJ 01 AB-1234"
    plate_normalized: str        # e.g. "GJ01AB1234"
    x_center: int
    start_frame: int
    end_frame: int
    y_start: int = -120
    y_end: int = 620
    cls: str = "car"
    ocr_confidence: float = 0.9
    visible_ocr_frames: Tuple[int, ...] = ()  # absolute frame indices where OCR "sees" it

    def bbox_at(self, frame_idx: int) -> Optional[List[float]]:
        if not (self.start_frame <= frame_idx <= self.end_frame):
            return None
        span = max(self.end_frame - self.start_frame, 1)
        progress = (frame_idx - self.start_frame) / span
        y = self.y_start + (self.y_end - self.y_start) * progress
        w, h = 96, 128
        return [self.x_center - w / 2, y, self.x_center + w / 2, y + h]


@dataclass
class DemoScenario:
    """Full scripted scene."""

    camera_id: str = "cam04"
    n_frames: int = 90
    frame_interval_ms: float = 40.0   # 25 fps PTS cadence
    vehicles: List[ScriptedVehicle] = field(default_factory=list)
    pts_rollback_at_frame: Optional[int] = None  # simulate a feed loop

    @classmethod
    def default(cls) -> "DemoScenario":
        """Two vehicles, one watchlist-style plate, one feed loop mid-scene.

        OCR visibility windows are DENSE on purpose: real OCR pacing skips
        frames, so the scripted plate must be readable whenever the pipeline
        happens to look.
        """
        return cls(
            camera_id="cam04",
            n_frames=90,
            vehicles=[
                ScriptedVehicle(
                    plate_text="GJ 01 AB-1234",
                    plate_normalized="GJ01AB1234",
                    x_center=220,
                    start_frame=5,
                    end_frame=40,
                    visible_ocr_frames=tuple(range(12, 39)),
                ),
                ScriptedVehicle(
                    plate_text="MH 02 CD-5678",
                    plate_normalized="MH02CD5678",
                    x_center=420,
                    start_frame=50,
                    end_frame=85,
                    visible_ocr_frames=tuple(range(55, 84)),
                    cls="car",
                ),
            ],
            pts_rollback_at_frame=45,
        )


class DemoArray(np.ndarray):
    """ndarray subclass carrying the demo frame index (scripts only, never live)."""

    demo_index = -1
    demo_scenario = None


def render_frame(scenario: DemoScenario, frame_idx: int) -> np.ndarray:
    """Draw a simple synthetic traffic frame (clearly synthetic)."""
    h, w = 480, 640
    frame = np.zeros((h, w, 3), dtype=np.uint8).view(DemoArray)
    frame.demo_index = frame_idx
    frame.demo_scenario = scenario
    frame[:] = (40, 44, 48)
    if cv2 is not None:
        cv2.rectangle(frame, (120, 0), (520, h), (58, 62, 66), -1)
        cv2.putText(frame, f"DEMO FRAME {frame_idx} [{scenario.camera_id}]", (12, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 180), 1)
        for veh in scenario.vehicles:
            bbox = veh.bbox_at(frame_idx)
            if bbox is None:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 80, 200), -1)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (230, 230, 230), 2)
            cv2.putText(frame, veh.plate_normalized, (x1 + 6, y2 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
    return frame


def demo_packets(scenario: DemoScenario) -> Iterator[FramePacket]:
    """
    Yield scripted FramePackets with monotonic PTS (plus optional rollback).
    On a PTS rollback the packet is flagged is_discontinuity — mirroring what
    the real capture layer does for looping Sentinel feeds.
    """
    pts = 0.0
    seq = 0
    last_pts = None
    for i in range(scenario.n_frames):
        is_disc = False
        if scenario.pts_rollback_at_frame == i:
            pts = 0.0  # feed looped: PTS resets
        if last_pts is not None and pts < last_pts - 500.0:
            is_disc = True  # same rule as capture.StreamCaptureBase
        seq += 1
        yield FramePacket(
            frame=render_frame(scenario, i),
            camera_id=scenario.camera_id,
            pts_ms=pts,
            capture_state=CaptureState.ONLINE,
            sequence_number=seq,
            is_discontinuity=is_disc,
            source_type="demo",
        )
        last_pts = pts
        pts += scenario.frame_interval_ms


class DemoDetector:
    """
    Scripted detector: returns the scenario's ground-truth boxes. NOT a model.
    The demo is explicit about this — no real inference happens in DEMO mode.
    """

    def detect(self, frame, camera_id=None, pts_ms=None):
        from detection.vehicle_detector import Detection

        idx = getattr(frame, "demo_index", -1)
        scenario = getattr(frame, "demo_scenario", None)
        out = []
        if idx is None or idx < 0 or scenario is None:
            return out
        for veh in scenario.vehicles:
            bbox = veh.bbox_at(idx)
            if bbox:
                out.append(
                    Detection(
                        bbox=bbox,
                        class_name=veh.cls,
                        confidence=0.92,
                        camera_id=camera_id,
                        pts_ms=pts_ms,
                    )
                )
        return out


class DemoOcr:
    """
    Scripted OCR: returns plate text on frames listed in visible_ocr_frames.
    The caller (demo wiring) sets `.ctx = (scenario, frame_idx)` per packet.
    """

    def __init__(self):
        self.ctx = None

    def read(self, image):
        from anpr.ocr import OcrLine

        if not self.ctx:
            return []
        scenario, idx = self.ctx
        lines = []
        for veh in scenario.vehicles:
            if idx in veh.visible_ocr_frames and veh.bbox_at(idx) is not None:
                lines.append(OcrLine(text=veh.plate_text, confidence=veh.ocr_confidence))
        return lines
