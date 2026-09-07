"""
Offline VIDEO-FILE pipeline (recorded footage → sightings → events).

    frames -> YOLO11 vehicle detection -> ByteTrack-style tracking
           -> plate detection (YOLO) -> OCR -> multi-frame voting
           -> SIGHTING segmentation -> evidence -> events

It deliberately reuses the live engine's building blocks
(``detection.vehicle_detector``, ``tracking.vehicle_tracker``,
``anpr.*``, ``events.*``) so the recorded-video path and the live-camera path
cannot drift apart. What is new here is everything a *file* needs and a live
stream does not: deterministic full-file traversal, annotated-video rendering,
best-frame evidence selection and distinct-sighting segmentation.

Every knob is a constructor parameter (see ``VideoPipelineConfig``) — nothing
is tuned to one particular clip.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from anpr.normalizer import candidate_from_ocr_text, plate_format_score
from anpr.plate_detector import extract_plate_candidates, preprocess_for_ocr
from anpr.plate_yolo import PlateBox, YoloPlateDetector, crop_plate
from capture.file_capture import VideoFileSource, probe_video
from detection.vehicle_detector import VehicleDetector
from sightings.quality import bbox_area, edge_distance_ratio, evidence_score, sharpness
from sightings.segmenter import PlateObservation, Sighting, SightingSegmenter
from tracking.vehicle_tracker import VehicleTracker

logger = logging.getLogger("cv_engine.video_pipeline")


@dataclass
class VideoPipelineConfig:
    """All tunables for a recorded-video run (spec §21: everything configurable)."""

    # identity
    video_id: str = "video"
    camera_id: str = "video"
    location_name: str = "Unknown"
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # models
    vehicle_model: str = "yolo11n.pt"
    plate_model: Optional[str] = None
    device: str = "cpu"

    # detection
    frame_skip: int = 2
    inference_imgsz: int = 640
    detection_confidence: float = 0.35

    # tracking
    track_max_age_sec: float = 1.2
    track_min_hits: int = 2
    track_iou_threshold: float = 0.25

    # plate detection / OCR
    plate_confidence: float = 0.25
    plate_imgsz: int = 320
    min_plate_width_px: int = 26          # never OCR a crop smaller than this
    min_vehicle_area_px: int = 3000       # never OCR a distant/tiny vehicle
    ocr_interval_ms: float = 400.0        # per-track OCR pacing
    max_ocr_per_frame: int = 2            # CPU budget per processed frame
    max_reads_per_track: int = 14         # stop OCR'ing an already-solved track
    stable_reads_to_stop: int = 4         # agreeing reads that end OCR for a track
    min_ocr_confidence: float = 0.30      # below: discard the read (never stored)

    # sighting segmentation
    track_end_gap_sec: float = 2.0
    sighting_cooldown_sec: float = 3.0
    min_sighting_frames: int = 3
    min_sighting_duration_sec: float = 0.3

    # plate acceptance (shared with the live pipeline's thresholds)
    plate_reject_threshold: float = 0.60
    plate_min_agree_reads: int = 2

    # analysis window
    start_sec: float = 0.0
    duration_sec: Optional[float] = None

    # output
    annotate: bool = True
    annotated_fps: Optional[float] = None
    progress_every: int = 50


@dataclass
class VideoRunStats:
    frames_read: int = 0
    frames_processed: int = 0
    detections: int = 0
    tracks_created: int = 0
    plate_detections: int = 0
    ocr_reads: int = 0
    ocr_accepted: int = 0
    ocr_rejected_small: int = 0
    ocr_rejected_conf: int = 0
    ocr_rejected_format: int = 0
    frame_failures: int = 0
    detect_ms_total: float = 0.0
    plate_ms_total: float = 0.0
    ocr_ms_total: float = 0.0
    wall_sec: float = 0.0

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["avg_detect_ms"] = round(self.detect_ms_total / self.frames_processed, 2) if self.frames_processed else 0.0
        d["avg_plate_ms"] = round(self.plate_ms_total / self.plate_detections, 2) if self.plate_detections else 0.0
        d["avg_ocr_ms"] = round(self.ocr_ms_total / self.ocr_reads, 2) if self.ocr_reads else 0.0
        for k in ("detect_ms_total", "plate_ms_total", "ocr_ms_total", "wall_sec"):
            d[k] = round(d[k], 2)
        return d


class _TrackOcrState:
    __slots__ = ("last_ocr_pts", "reads", "votes", "solved")

    def __init__(self):
        self.last_ocr_pts: Optional[float] = None
        self.reads = 0
        self.votes: Dict[str, int] = {}
        self.solved = False


class VideoAnalysisPipeline:
    """Runs one recorded video end-to-end and returns finalized sightings."""

    def __init__(
        self,
        video_path: str,
        config: VideoPipelineConfig,
        detector: Optional[VehicleDetector] = None,
        tracker: Optional[VehicleTracker] = None,
        plate_detector: Optional[YoloPlateDetector] = None,
        ocr_engine=None,
        annotated_path: Optional[str] = None,
    ):
        self.video_path = str(video_path)
        self.cfg = config
        self.stats = VideoRunStats()
        self.annotated_path = annotated_path

        self.detector = detector or VehicleDetector(
            model_path=config.vehicle_model,
            conf_threshold=config.detection_confidence,
            imgsz=config.inference_imgsz,
            device=config.device,
        )
        self.tracker = tracker or VehicleTracker(
            max_age_sec=config.track_max_age_sec,
            min_hits=config.track_min_hits,
            iou_threshold=config.track_iou_threshold,
        )
        self.plate_detector = plate_detector if plate_detector is not None else YoloPlateDetector(
            model_path=config.plate_model,
            conf_threshold=config.plate_confidence,
            imgsz=config.plate_imgsz,
            device=config.device,
        )
        self.ocr = ocr_engine
        self.segmenter = SightingSegmenter(
            camera_id=config.camera_id,
            video_id=config.video_id,
            track_end_gap_sec=config.track_end_gap_sec,
            sighting_cooldown_sec=config.sighting_cooldown_sec,
            min_frames=config.min_sighting_frames,
            min_duration_sec=config.min_sighting_duration_sec,
            reject_threshold=config.plate_reject_threshold,
            min_agree_reads=config.plate_min_agree_reads,
        )
        self._ocr_state: Dict[int, _TrackOcrState] = {}
        self._track_plate_label: Dict[int, tuple] = {}  # track -> (plate, conf)
        self._seen_track_ids = set()
        self.probe = None
        self._writer = None

    # ------------------------------------------------------------------
    def _ensure_ocr(self):
        if self.ocr is None:
            from anpr.ocr import RapidOcrEngine

            self.ocr = RapidOcrEngine()
        return self.ocr

    # ------------------------------------------------------------------
    def _ocr_due(self, track_id: int, pts_ms: float) -> bool:
        st = self._ocr_state.setdefault(track_id, _TrackOcrState())
        if st.solved or st.reads >= self.cfg.max_reads_per_track:
            return False
        if st.last_ocr_pts is None:
            return True
        return (pts_ms - st.last_ocr_pts) >= self.cfg.ocr_interval_ms

    def _register_vote(self, track_id: int, plate: str) -> None:
        st = self._ocr_state.setdefault(track_id, _TrackOcrState())
        st.votes[plate] = st.votes.get(plate, 0) + 1
        if st.votes[plate] >= self.cfg.stable_reads_to_stop:
            st.solved = True

    # ------------------------------------------------------------------
    def _read_plate_for_track(self, frame: np.ndarray, track, pts_ms: float, frame_index: int) -> None:
        """Plate detection + OCR for ONE tracked vehicle in ONE frame."""
        h, w = frame.shape[:2]
        v_area = bbox_area(track.bbox)
        if v_area < self.cfg.min_vehicle_area_px:
            return

        plate_box: Optional[PlateBox] = None
        if self.plate_detector is not None and self.plate_detector.available:
            t0 = time.perf_counter()
            boxes = self.plate_detector.detect_in_vehicle(frame, track.bbox)
            self.stats.plate_ms_total += (time.perf_counter() - t0) * 1000.0
            self.stats.plate_detections += 1
            plate_box = boxes[0] if boxes else None

        if plate_box is not None:
            if plate_box.width < self.cfg.min_plate_width_px:
                self.stats.ocr_rejected_small += 1
                return
            crop = crop_plate(frame, plate_box)
            plate_bbox = plate_box.bbox
            plate_det_conf = plate_box.confidence
        else:
            # Fallback: the existing heuristic vehicle sub-crop (no plate model).
            crops = extract_plate_candidates(frame, track.bbox, track.class_name)
            if not crops:
                return
            crop = crops[0]
            plate_bbox = None
            plate_det_conf = 0.0

        if crop is None or crop.size == 0:
            return

        prep = preprocess_for_ocr(crop)
        ocr = self._ensure_ocr()
        t0 = time.perf_counter()
        lines = ocr.read(prep)
        self.stats.ocr_ms_total += (time.perf_counter() - t0) * 1000.0
        self.stats.ocr_reads += 1
        st = self._ocr_state.setdefault(track.track_id, _TrackOcrState())
        st.last_ocr_pts = pts_ms
        st.reads += 1

        crop_sharp = sharpness(crop)
        best_for_frame = None
        for line in lines:
            if line.confidence < self.cfg.min_ocr_confidence:
                self.stats.ocr_rejected_conf += 1
                continue
            candidate = candidate_from_ocr_text(line.text)
            if not candidate:
                self.stats.ocr_rejected_format += 1
                continue
            fmt = plate_format_score(candidate)
            if fmt <= 0.0:
                self.stats.ocr_rejected_format += 1
                continue
            # Format score never upgrades a reading, it only discounts it.
            conf = float(line.confidence) * (1.0 if fmt >= 1.0 else 0.85)
            if best_for_frame is None or conf > best_for_frame[1]:
                best_for_frame = (candidate, conf, line.text)

        if best_for_frame is None:
            # Still offer this frame as plateless evidence for the track.
            self.segmenter.offer_plateless_evidence(
                track.track_id, frame, pts_ms, frame_index, track.bbox,
                quality=evidence_score(0.0, crop_sharp, 0.0, v_area,
                                       edge_distance_ratio(track.bbox, w, h)),
            )
            return

        candidate, conf, raw = best_for_frame
        p_area = bbox_area(plate_bbox) if plate_bbox else float(crop.shape[0] * crop.shape[1])
        obs = PlateObservation(
            pts_ms=pts_ms,
            frame_index=frame_index,
            plate_raw=raw,
            plate_normalized=candidate,
            ocr_confidence=round(conf, 4),
            plate_det_confidence=round(plate_det_conf, 4),
            plate_bbox=[float(v) for v in plate_bbox] if plate_bbox else None,
            plate_area_px=p_area,
            sharpness=crop_sharp,
            quality=evidence_score(p_area, crop_sharp, conf, v_area,
                                   edge_distance_ratio(track.bbox, w, h)),
        )
        self.segmenter.add_plate_observation(
            track.track_id, obs, frame=frame, plate_crop=crop, vehicle_bbox=track.bbox
        )
        self._register_vote(track.track_id, candidate)
        self.stats.ocr_accepted += 1
        # Live label for the annotated video (track-scoped: never leaks to
        # another vehicle).
        prev = self._track_plate_label.get(track.track_id)
        if prev is None or conf > prev[1]:
            self._track_plate_label[track.track_id] = (candidate, conf)

    # ------------------------------------------------------------------
    def _annotate(self, frame: np.ndarray, tracks, pts_ms: float) -> np.ndarray:
        import cv2

        out = frame.copy()
        for t in tracks:
            x1, y1, x2, y2 = [int(v) for v in t.bbox]
            label_top = f"{t.class_name.upper()} | TRACK {t.track_id}"
            plate = self._track_plate_label.get(t.track_id)
            if plate and plate[1] >= self.cfg.plate_reject_threshold:
                label_bottom = f"{plate[0]} | {int(round(plate[1] * 100))}%"
                colour = (0, 220, 60)
            elif plate:
                label_bottom = "PLATE UNCERTAIN"
                colour = (0, 190, 255)
            else:
                label_bottom = "PLATE UNCERTAIN"
                colour = (150, 150, 150)
            cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
            for i, text in enumerate((label_top, label_bottom)):
                y = max(14, y1 - 24 + i * 18)
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(out, (x1, y - th - 4), (x1 + tw + 6, y + 3), (0, 0, 0), -1)
                cv2.putText(out, text, (x1 + 3, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1,
                            cv2.LINE_AA)
        ts = pts_ms / 1000.0
        stamp = f"{self.cfg.location_name}  |  t={int(ts // 60):02d}:{ts % 60:05.2f}"
        cv2.rectangle(out, (0, 0), (max(360, 9 * len(stamp)), 26), (0, 0, 0), -1)
        cv2.putText(out, stamp, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1,
                    cv2.LINE_AA)
        return out

    # ------------------------------------------------------------------
    def run(self) -> List[Sighting]:
        import cv2

        cfg = self.cfg
        self.probe = probe_video(self.video_path, measure_frames=30)
        if not self.probe.opened:
            raise IOError(f"cannot open video {self.video_path}: {self.probe.error}")
        logger.info("[VIDEO] %s", self.probe.to_dict())

        source = VideoFileSource(
            self.video_path,
            camera_id=cfg.camera_id,
            frame_skip=cfg.frame_skip,
            start_sec=cfg.start_sec,
            duration_sec=cfg.duration_sec,
        )
        src_fps = self.probe.fps_measured or self.probe.fps_reported or 25.0
        out_fps = cfg.annotated_fps or max(1.0, src_fps / cfg.frame_skip)

        if self.annotated_path and cfg.annotate:
            Path(self.annotated_path).parent.mkdir(parents=True, exist_ok=True)
            self._writer = cv2.VideoWriter(
                self.annotated_path,
                cv2.VideoWriter_fourcc(*"mp4v"),
                out_fps,
                (self.probe.width, self.probe.height),
            )
            if not self._writer.isOpened():
                logger.error("[VIDEO] annotated writer could not open; continuing without it")
                self._writer = None

        t_start = time.perf_counter()
        last_pts = 0.0
        for packet in source.frames():
            self.stats.frames_read += 1
            try:
                frame = packet.frame
                pts_ms = packet.pts_ms
                last_pts = pts_ms

                t0 = time.perf_counter()
                detections = self.detector.detect(
                    frame, camera_id=cfg.camera_id, pts_ms=pts_ms
                )
                self.stats.detect_ms_total += (time.perf_counter() - t0) * 1000.0
                self.stats.frames_processed += 1
                self.stats.detections += len(detections)

                tracks = self.tracker.update(detections, pts_ms=pts_ms)
                for t in tracks:
                    if t.track_id not in self._seen_track_ids:
                        self._seen_track_ids.add(t.track_id)
                        self.stats.tracks_created += 1

                visible = [t for t in tracks if t.time_since_update_ms == 0]
                for t in visible:
                    self.segmenter.observe_track(
                        t.track_id, pts_ms, packet.sequence_number,
                        t.class_name, t.confidence, t.bbox,
                    )

                # --- ANPR budget: longest-lived unsolved tracks first --------
                budget = cfg.max_ocr_per_frame
                ordered = sorted(visible, key=lambda t: -(t.confirmed_age_ms or 0))
                for t in ordered:
                    if budget <= 0:
                        break
                    if not self._ocr_due(t.track_id, pts_ms):
                        continue
                    self._read_plate_for_track(frame, t, pts_ms, packet.sequence_number)
                    budget -= 1

                self.segmenter.tick(pts_ms)

                if self._writer is not None:
                    self._writer.write(self._annotate(frame, visible, pts_ms))

                if cfg.progress_every and self.stats.frames_processed % cfg.progress_every == 0:
                    logger.info(
                        "[VIDEO] t=%.1fs frames=%d dets=%d tracks=%d ocr=%d sightings_closed=%d",
                        pts_ms / 1000.0, self.stats.frames_processed, self.stats.detections,
                        len(visible), self.stats.ocr_reads, len(self.segmenter.closed),
                    )
            except Exception as exc:  # one bad frame must never kill the run
                self.stats.frame_failures += 1
                logger.exception("[VIDEO] frame %s failed: %s", packet.sequence_number, exc)
                continue

        if self._writer is not None:
            self._writer.release()
            self._writer = None

        self.source_stats = source.stats
        self.stats.wall_sec = time.perf_counter() - t_start
        sightings = self.segmenter.finalize()
        logger.info(
            "[VIDEO] done: %d frame(s) processed, %d sighting(s), %.1fs wall",
            self.stats.frames_processed, len(sightings), self.stats.wall_sec,
        )
        return sightings
