"""
Per-camera CV pipeline (spec §24):

    Frame -> Detection -> Tracking -> ANPR -> Event builder
          -> Deduplication -> Evidence -> POST /api/events

All timing is PTS-based. A single instance handles ONE camera; multi-camera
operation = one CameraPipeline per camera (each produces independent
sightings; the backend aggregates traces).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from engine.anpr.confidence import PlateReading, classify_confidence, is_usable, ConfidenceTier
from engine.anpr.normalizer import candidate_from_ocr_text, plate_format_score
from engine.anpr.plate_detector import extract_plate_candidates, preprocess_for_ocr
from engine.anpr.plate_memory import PlateMemory
from events.dedup import SightingDeduplicator
from events.event_builder import build_event
from engine.tracking.vehicle_tracker import Track, VehicleTracker

logger = logging.getLogger("cv_engine.pipeline")


@dataclass
class PipelineStats:
    frames: int = 0
    frames_processed: int = 0
    detections: int = 0
    ocr_reads: int = 0
    events_emitted: int = 0
    events_suppressed: int = 0
    discontinuities: int = 0


class CameraPipeline:
    def __init__(
        self,
        camera,
        settings,
        detector,                 # detection.vehicle_detector.VehicleDetector
        ocr_engine,               # anpr.ocr.OcrEngine (or stub)
        backend_client,           # integration.backend_client.BackendClient
        evidence_writer=None,     # evidence.evidence_writer.EvidenceWriter
        tracker: Optional[VehicleTracker] = None,
        emit_plateless_sightings: bool = False,
        on_packet=None,  # optional hook(packet) called first — demo wiring only
        on_tracks=None,  # optional hook(packet, tracks) after tracking — annotated preview
    ):
        self.camera = camera
        self.settings = settings
        self.detector = detector
        self.ocr_engine = ocr_engine
        self.backend_client = backend_client
        self.evidence_writer = evidence_writer
        self.on_tracks = on_tracks

        self.tracker = tracker or VehicleTracker(
            max_age_sec=settings.track_max_age_sec,
            min_hits=settings.track_min_hits,
            iou_threshold=settings.track_iou_threshold,
        )
        self.plate_memory = PlateMemory(
            camera.camera_id,
            reject_threshold=settings.anpr_conf_threshold,
            min_agree_reads=settings.anpr_min_agree_reads,
        )
        self.dedup = SightingDeduplicator(suppression_sec=settings.event_suppression_sec)

        self.emit_plateless_sightings = emit_plateless_sightings
        self.on_packet = on_packet
        self.stats = PipelineStats()

        self._last_process_pts: Optional[float] = None
        self._last_ocr_pts: Optional[float] = None
        self._last_hold_emit_pts: Dict[int, float] = {}
        self._last_plate_crop: Dict[int, np.ndarray] = {}
        self._last_track_frames: Dict[int, np.ndarray] = {}  # last frame each track was SEEN
        self._last_track_pts: Dict[int, float] = {}
        self._current_frame: Optional[np.ndarray] = None
        self._current_pts: Optional[float] = None

    # ------------------------------------------------------------------
    def process_packet(self, packet) -> List[dict]:
        """
        Run one FramePacket through the full pipeline.
        Returns the list of events emitted for this packet (already submitted
        to the backend client).
        """
        self.stats.frames += 1
        if self.on_packet is not None:
            self.on_packet(packet)

        # --- Scene discontinuity (spec §14): reset all track/plate state ---
        if packet.is_discontinuity:
            self.stats.discontinuities += 1
            self.tracker.reset()
            self.plate_memory.reset()
            self.dedup.reset()
            self._last_hold_emit_pts.clear()
            self._last_plate_crop.clear()
            self._last_track_frames.clear()
            self._last_track_pts.clear()
            # PTS may have rolled back (feed loop): PTS-anchored pacing must
            # restart, otherwise interval gates stay closed forever.
            self._last_process_pts = None
            self._last_ocr_pts = None
            logger.info("[%s] pipeline state reset after discontinuity", self.camera.camera_id)

        self._current_frame = packet.frame
        self._current_pts = packet.pts_ms

        # --- Pacing: frame skip + min inference interval (spec §12) ---
        if self.settings.frame_skip > 1 and (packet.sequence_number % self.settings.frame_skip) != 1:
            self._flush_finished_tracks(packet.pts_ms)
            return []
        if (
            self.settings.process_interval_ms > 0
            and self._last_process_pts is not None
            and (packet.pts_ms - self._last_process_pts) < self.settings.process_interval_ms
        ):
            return []
        self._last_process_pts = packet.pts_ms
        self.stats.frames_processed += 1

        # --- Detection ---
        detections = self.detector.detect(
            packet.frame, camera_id=self.camera.camera_id, pts_ms=packet.pts_ms
        )
        self.stats.detections += len(detections)
        if detections:
            logger.debug(
                "[%s] %d vehicle(s) detected @ pts=%.1f",
                self.camera.camera_id, len(detections), packet.pts_ms,
            )

        # --- Tracking (PTS-driven) ---
        tracks = self.tracker.update(detections, pts_ms=packet.pts_ms)

        # Live annotated preview (used by the local feed runner). Receives every
        # processed frame with its tracks; no effect on the pipeline by default.
        if self.on_tracks is not None:
            try:
                self.on_tracks(packet, tracks)
            except Exception:
                pass

        # Record the last frame/PTS where each track was actually seen, so
        # evidence for track-loss events shows the vehicle, not an empty scene.
        for t in tracks:
            if t.time_since_update_ms == 0:
                self._last_track_frames[t.track_id] = packet.frame
                self._last_track_pts[t.track_id] = packet.pts_ms

        # --- ANPR ---
        emitted: List[dict] = []
        if self.settings.anpr_enabled:
            self._run_anpr(tracks, packet.pts_ms)

        # --- Emission triggers ---
        emitted += self._emit_stable_plates(tracks, packet.pts_ms)
        emitted += self._flush_finished_tracks(packet.pts_ms)
        emitted += self._periodic_hold_emits(tracks, packet.pts_ms)
        return emitted

    # ------------------------------------------------------------------
    def _anpr_due(self, pts_ms: float) -> bool:
        if self._last_ocr_pts is None:
            return True
        return (pts_ms - self._last_ocr_pts) >= self.settings.anpr_interval_ms

    def _run_anpr(self, tracks: List[Track], pts_ms: float) -> None:
        if not tracks or not self._anpr_due(pts_ms):
            return

        # Pick tracks lacking a stable plate; prefer longer-lived tracks.
        candidates = [t for t in tracks if not self.plate_memory.is_stable(t.track_id)]
        candidates.sort(key=lambda t: -(t.confirmed_age_ms or 0))

        budget = self.settings.anpr_max_reads_per_frame
        for track in candidates:
            if budget <= 0:
                break
            crops = extract_plate_candidates(self._current_frame, track.bbox, track.class_name)
            if not crops:
                continue
            crop = crops[0]
            prep = preprocess_for_ocr(crop)
            lines = self.ocr_engine.read(prep)
            self._last_ocr_pts = pts_ms
            self.stats.ocr_reads += 1
            budget -= 1
            self._last_plate_crop[track.track_id] = crop

            for line in lines:
                norm = candidate_from_ocr_text(line.text)
                if norm is None:
                    continue
                # Format plausibility discounts implausible strings — it never
                # upgrades, and the raw OCR output is preserved either way.
                conf = float(line.confidence) * (
                    1.0 if plate_format_score(norm) == 1.0 else 0.85 if plate_format_score(norm) == 0.5 else 0.0
                )
                if conf <= 0.0:
                    continue
                self.plate_memory.add_reading(
                    track.track_id,
                    PlateReading(
                        plate_raw=line.text,
                        plate_normalized=norm,
                        confidence=min(conf, 1.0),
                        pts_ms=pts_ms,
                    ),
                )
                tier = classify_confidence(
                    conf,
                    reject_threshold=self.settings.anpr_conf_threshold,
                    low_mark=self.settings.anpr_low_conf_mark,
                )
                if is_usable(tier):
                    logger.info(
                        "[%s] plate candidate track=%d '%s' -> %s conf=%.2f tier=%s",
                        self.camera.camera_id, track.track_id, line.text, norm, conf, tier.value,
                    )

    # ------------------------------------------------------------------
    def _emit(
        self,
        track: Track,
        plate: Optional[dict],
        pts_ms: float,
        evidence_frame: Optional[np.ndarray] = None,
    ) -> Optional[dict]:
        plate_str = plate["plate"] if plate else None
        if not self.dedup.should_emit(self.camera.camera_id, track.track_id, plate_str, pts_ms):
            self.stats.events_suppressed += 1
            return None

        frame_for_evidence = evidence_frame if evidence_frame is not None else self._current_frame
        evidence_ref = None
        if self.evidence_writer is not None and frame_for_evidence is not None:
            evidence_ref = self.evidence_writer.save_event_evidence(
                frame=frame_for_evidence,
                camera_id=self.camera.camera_id,
                track_id=track.track_id,
                pts_ms=pts_ms,
                plate=plate_str,
                plate_crop=self._last_plate_crop.get(track.track_id),
                store_full_frame=self.settings.evidence_store_full_frame,
                store_plate_crop=self.settings.evidence_store_plate_crop,
            )

        event = build_event(
            self.camera, track, plate=plate, evidence_ref=evidence_ref, pts_ms=pts_ms
        )
        self.backend_client.submit(event)
        self.stats.events_emitted += 1
        logger.info(
            "[%s] EVENT emitted: track=%d plate=%s conf=%s pts=%.1f",
            self.camera.camera_id,
            track.track_id,
            plate_str,
            event.get("plate_confidence"),
            pts_ms,
        )
        return event

    def _emit_stable_plates(self, tracks: List[Track], pts_ms: float) -> List[dict]:
        """Emit as soon as a track's plate becomes stable (multi-frame agreed)."""
        out = []
        for track in tracks:
            if not self.plate_memory.is_stable(track.track_id):
                continue
            plate = self.plate_memory.best(track.track_id)
            if not plate:
                continue
            st = self.plate_memory.state_for(track.track_id)
            if st.last_emitted_key == plate["plate"]:
                continue
            event = self._emit(track, plate, pts_ms)
            if event:
                st.last_emitted_key = plate["plate"]
                st.last_emitted_pts = pts_ms
                st.emitted_count += 1
                out.append(event)
        return out

    def _flush_finished_tracks(self, pts_ms: float) -> List[dict]:
        """
        Emit final events for tracks that went silent (vehicle left the scene)
        and forget them. Plateless tracks only emit when explicitly enabled.
        """
        out = []
        loss_ms = self.settings.event_on_track_loss_sec * 1000.0
        finished = [
            t for t in self.tracker.lost_tracks(pts_ms)
            if t.time_since_update_ms >= loss_ms
        ]
        for track in finished:
            plate = self.plate_memory.best(track.track_id)
            if plate or self.emit_plateless_sightings:
                st = self.plate_memory.state_for(track.track_id)
                if plate and st.last_emitted_key == plate["plate"] and st.emitted_count > 0:
                    pass  # already reported this plate; don't spam on exit
                else:
                    event = self._emit(
                        track,
                        plate,
                        pts_ms,
                        evidence_frame=self._last_track_frames.get(track.track_id),
                    )
                    if event:
                        out.append(event)
            self.plate_memory.drop(track.track_id)
            self.dedup.forget_track(self.camera.camera_id, track.track_id)
            self._last_hold_emit_pts.pop(track.track_id, None)
            self._last_plate_crop.pop(track.track_id, None)
            self._last_track_frames.pop(track.track_id, None)
            self._last_track_pts.pop(track.track_id, None)
        return out

    def _periodic_hold_emits(self, tracks: List[Track], pts_ms: float) -> List[dict]:
        """Long-lived tracks re-emit their best plate every hold window."""
        out = []
        hold_ms = self.settings.event_max_track_hold_sec * 1000.0
        for track in tracks:
            plate = self.plate_memory.best(track.track_id)
            if not plate and not self.emit_plateless_sightings:
                continue
            last = self._last_hold_emit_pts.get(track.track_id)
            if last is not None and (pts_ms - last) < hold_ms:
                continue
            st = self.plate_memory.state_for(track.track_id)
            plate_key = plate["plate"] if plate else None
            if plate_key is not None and st.last_emitted_key == plate_key and last is not None:
                continue
            event = self._emit(track, plate, pts_ms)
            if event:
                self._last_hold_emit_pts[track.track_id] = pts_ms
                st.last_emitted_key = plate_key
                st.last_emitted_pts = pts_ms
                st.emitted_count += 1
                out.append(event)
        return out

    # ------------------------------------------------------------------
    def run(self, packets, stop_check=None) -> None:
        """Consume an iterable of FramePackets (e.g. ManagedCapture.packets())."""
        logger.info("[%s] pipeline starting", self.camera.camera_id)
        for packet in packets:
            if stop_check and stop_check():
                break
            self.process_packet(packet)
        logger.info(
            "[%s] pipeline stopped: %s",
            self.camera.camera_id,
            self.stats,
        )
