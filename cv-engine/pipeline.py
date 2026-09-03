"""The core CV loop: frame -> detect/track -> ANPR -> dedup -> evidence -> event.

This module ties the pieces together. Two entry points:

* :meth:`CameraPipeline.process_packet` — drive one frame in, get events out.
  Deterministic and unit-testable (inject a fake tracker), and used by the
  integration test.
* :func:`run_camera` — the real, unattended run for one camera: reconnecting
  capture, scene-cut handling, throttled inference, and a live backend client.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import numpy as np

from anpr.aggregator import TrackPlateAggregator
from anpr.confidence import grade_confidence
from anpr.normalizer import normalize_plate
from anpr.plate_detector import PlateDetector
from capture.capture_factory import make_capture_factory
from capture.frames import FramePacket
from capture.reconnect import ReconnectingCapture
from capture.sentinel_catalogue import Camera
from config.settings import Settings
from detection.vehicle_detector import InferenceGate
from events.dedup import EventDeduplicator
from events.event_builder import build_event, build_unplated_event
from evidence.evidence_writer import EvidenceWriter
from integration.backend_client import BackendClient
from logging_setup import log_event
from tracking.scene_cut import SceneCutDetector
from tracking.vehicle_tracker import TrackedVehicle, VehicleTracker

log = logging.getLogger("trinetra.pipeline")


class CameraPipeline:
    """Stateful per-camera processing. Inject a tracker/OCR for tests."""

    def __init__(
        self,
        settings: Settings,
        camera: Camera,
        tracker: Optional[object] = None,
        ocr_engine: Optional[object] = None,
        backend: Optional[BackendClient] = None,
        emit_to_backend: bool = True,
    ) -> None:
        self.settings = settings
        self.camera = camera
        self.tracker = tracker or VehicleTracker(settings)
        self.ocr = ocr_engine
        self.plate_detector = PlateDetector(settings, ocr_engine) if ocr_engine else None
        self.backend = backend
        self.emit_to_backend = emit_to_backend
        self.aggregator = TrackPlateAggregator()
        self.dedup = EventDeduplicator(settings.dedup_window_s, settings.dedup_unplated_window_s)
        self.scene = SceneCutDetector(settings.scene_cut_threshold)
        self.evidence = EvidenceWriter(settings)
        self.gate = InferenceGate(settings.frame_skip, settings.inference_interval_s)
        self._last_ocr_ms: dict[int, float] = {}
        self.events_emitted = 0
        self.frames_processed = 0

    # -- one frame ----------------------------------------------------------
    def process_packet(self, packet: FramePacket) -> list[object]:
        """Process one frame; return the events it produced (for tests/metrics)."""
        emitted: list[object] = []
        self.frames_processed += 1

        cut_result = self.scene.process(packet.frame)
        is_cut = bool(cut_result.is_cut) or bool(packet.scene_cut)
        if is_cut:
            log_event(
                log,
                "scene_discontinuity",
                level=logging.WARNING,
                camera=self.camera.camera_id,
                pts_ms=packet.pts_ms,
                score=cut_result.score,
            )
            self.tracker.reset(reason="scene_cut")
            self.aggregator.reset()
            self._last_ocr_ms.clear()
            return emitted

        if not self.gate.should_infer():
            return emitted

        tracks = self.tracker.update(
            packet.frame,
            camera_id=self.camera.camera_id,
            pts_ms=packet.pts_ms,
            continuous_ms=packet.continuous_ms,
        )
        for track in tracks:
            emitted.extend(self._handle_track(packet, track))
        return emitted

    def _handle_track(self, packet: FramePacket, track: TrackedVehicle) -> list[object]:
        emitted: list[object] = []
        now = time.monotonic()
        last = self._last_ocr_ms.get(track.track_id)
        if last is not None and (now - last) < self.settings.anpr_interval_s:
            return emitted
        self._last_ocr_ms[track.track_id] = now

        crop = track.crop(packet.frame)
        if crop is None or crop.size == 0 or self.plate_detector is None:
            return emitted
        candidate = self.plate_detector.best(crop)
        if candidate is None:
            return emitted

        normalized = normalize_plate(
            candidate.raw_text,
            min_len=self.settings.anpr_min_plate_len,
            max_len=self.settings.anpr_max_plate_len,
        )
        agg = self.aggregator.add(
            track.track_id,
            normalized.normalized,
            candidate.raw_text,
            candidate.confidence,
            packet.continuous_ms,
        )
        log_event(
            log,
            "plate_recognized",
            level=logging.DEBUG,
            camera=self.camera.camera_id,
            track_id=track.track_id,
            raw=candidate.raw_text,
            normalized=normalized.normalized,
            conf=candidate.confidence,
        )
        if self.aggregator.should_emit(track.track_id):
            aggregate = self.aggregator.consume(track.track_id)
            event = self._finalize(packet, track, aggregate.top_normalized, aggregate)
            emitted.append(event)
        return emitted

    def _finalize(self, packet: FramePacket, track: TrackedVehicle, plate: str, aggregate) -> object:
        evidence_ref = None
        if self.evidence.enabled(aggregate.confidence):
            evidence_ref = self.evidence.write(
                packet.frame, track.crop(packet.frame), self.camera.camera_id,
                track.track_id, plate, packet.continuous_ms,
            )
        event = build_event(
            self.settings,
            self.camera,
            track,
            plate=plate,
            plate_raw=aggregate.raw_best,
            plate_confidence=aggregate.confidence,
            evidence_ref=evidence_ref,
            source_transport=packet.source,
        )
        if self.dedup.should_emit(self.camera.camera_id, track.track_id, plate, packet.continuous_ms):
            self.events_emitted += 1
            log_event(
                log,
                "event_emitted",
                camera=self.camera.camera_id,
                track_id=track.track_id,
                plate=plate,
                conf=round(aggregate.confidence, 3),
                grade=grade_confidence(aggregate.confidence),
            )
            if self.emit_to_backend and self.backend is not None:
                self.backend.enqueue(event.to_payload())
            return event
        return None


def run_camera(
    camera: Camera,
    settings: Settings,
    backend: Optional[BackendClient] = None,
    max_frames: Optional[int] = None,
    max_reconnects: Optional[int] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    tracker: Optional[object] = None,
    ocr_engine: Optional[object] = None,
) -> dict:
    """Unattended run for one camera. Returns a metrics summary dict."""
    backend = backend or BackendClient(settings)
    backend.start()
    pipeline = CameraPipeline(settings, camera, tracker=tracker, ocr_engine=ocr_engine, backend=backend)
    supervisor = ReconnectingCapture(
        camera=camera,
        factory=make_capture_factory(camera, settings),
        min_s=settings.reconnect_min_s,
        max_s=settings.reconnect_max_s,
        multiplier=settings.reconnect_multiplier,
        jitter=settings.reconnect_jitter,
        stable_s=settings.stable_connection_s,
        max_reconnects=max_reconnects,
    )
    processed = 0
    try:
        for packet in supervisor.frames():
            pipeline.process_packet(packet)
            processed += 1
            if max_frames and processed >= max_frames:
                break
            if stop_flag and stop_flag():
                break
    finally:
        supervisor.stop()
        backend.stop()
    return {
        "camera": camera.camera_id,
        "frames_processed": processed,
        "events_emitted": pipeline.events_emitted,
        "dedup_suppressed": pipeline.dedup.suppressed,
        "scene_cuts": pipeline.scene.cuts_detected,
        "backend_sent": backend.sent,
        "backend_dead_lettered": backend.dead_lettered,
    }
