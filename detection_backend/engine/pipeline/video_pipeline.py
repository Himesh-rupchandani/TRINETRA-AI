"""
TRINETRA AI — Generalized Reusable Video Detection & ANPR Pipeline.

Processes any uploaded video (MP4, AVI, MOV, MKV, WEBM) through the real CV pipeline:
  1. Vehicles & number plates (via custom YOLO11 model weights)
  2. Vehicle track IDs (ByteTrack-style PTS-driven tracker)
  3. Plate crop extraction & RapidOCR text recognition
  4. Temporal plate voting & format normalization
  5. Sighting segmentation (FRAME -> TRACK -> SIGHTING)
  6. Annotated video rendering
  7. Genuine CSV + JSON + Evidence generation
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Ensure cv-engine root is importable
_cv_engine_dir = Path(__file__).resolve().parents[1]
if str(_cv_engine_dir) not in sys.path:
    sys.path.insert(0, str(_cv_engine_dir))

from detection.vehicle_detector import VehicleDetector, Detection
from tracking.vehicle_tracker import VehicleTracker, Track
from anpr.ocr import OcrEngine
from anpr.plate_detector import extract_plate_candidates, preprocess_for_ocr, vehicle_crop
from anpr.normalizer import candidate_from_ocr_text, normalize_plate, plate_format_score
from anpr.confidence import PlateReading, aggregate_readings
from pipeline.sighting_segmenter import SightingSegmenter, Sighting, _safe_crop

logger = logging.getLogger("cv_engine.video_pipeline")

DEFAULT_CONFIG = {
    "FRAME_SKIP": 4,              # Minimum frame skip
    "TARGET_FPS": 5.0,            # Surveillance CCTV target FPS (5 frames/sec)
    "INFERENCE_SIZE": 640,        # YOLO input size
    "DETECTION_CONFIDENCE": 0.25, # Detection threshold
    "PLATE_CONFIDENCE": 0.15,     # Minimum plate detection confidence
    "OCR_INTERVAL_FRAMES": 3,     # Run OCR every N processed frames per track
    "OCR_MIN_CONFIDENCE": 0.20,   # Minimum OCR confidence to consider
    "TRACK_MAX_AGE_SEC": 2.0,     # How long to keep lost tracks
    "TRACK_MIN_HITS": 2,          # Minimum detections before confirming track
    "TRACK_IOU_THRESHOLD": 0.25,  # IoU matching threshold
    "TRACK_END_GAP_SEC": 3.0,     # Gap before closing a sighting
    "SIGHTING_COOLDOWN_SEC": 5.0, # Minimum gap between sightings of same vehicle
    "MIN_SIGHTING_FRAMES": 2,     # Minimum frames for a valid sighting
    "MIN_SIGHTING_DURATION": 0.2, # Minimum duration (seconds) for valid sighting
    "ANNOTATED_VIDEO_FPS": 15,    # Output video FPS
    "EVIDENCE_JPEG_QUALITY": 92,  # JPEG quality for evidence frames
}


def find_model(repo_root: Optional[Path] = None) -> str:
    """Find the best available model in detection_backend or the repository."""
    here = Path(__file__).resolve()
    backend_root = here.parents[2]

    # Priority 0: local models directory inside detection_backend
    for m_cand in [
        backend_root / "models" / "best.pt",
        backend_root / "models" / "license-plate-finetune-v1n.pt",
        backend_root / "models" / "yolo11s.pt",
    ]:
        if m_cand.exists():
            return str(m_cand)

    if repo_root is None:
        repo_root = backend_root

    # Priority 1: Custom trained model (vehicle + number_plate)
    custom = repo_root / "yolo26_training" / "runs" / "train" / "vehicle_plate_yolo11" / "weights" / "best.pt"
    if custom.exists():
        return str(custom)
    # Priority 2: Fine-tuned plate model
    finetune = repo_root / "yolo26_training" / "license-plate-finetune-v1n.pt"
    if finetune.exists():
        return str(finetune)
    # Priority 3: Pre-trained YOLO11s
    yolo11s = repo_root / "cv-engine" / "yolo11s.pt"
    if yolo11s.exists():
        return str(yolo11s)
    return "yolo11s.pt"


def probe_video(video_path: str) -> dict:
    """Probe video properties using OpenCV."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip()

    props = {
        "path": video_path,
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
        "fourcc": fourcc,
        "codec": codec or "unknown",
        "duration_sec": frame_count / fps if fps > 0 else 0,
        "resolution": f"{width}x{height}",
    }

    ret, frame = cap.read()
    props["first_frame_readable"] = bool(ret)
    if ret and frame is not None:
        props["actual_shape"] = f"{frame.shape[1]}x{frame.shape[0]}"

    cap.release()
    return props


def _bbox_overlap(bbox_a, bbox_b) -> float:
    """Compute IoU-like overlap ratio of bbox_b inside bbox_a."""
    ax1, ay1, ax2, ay2 = [float(v) for v in bbox_a]
    bx1, by1, bx2, by2 = [float(v) for v in bbox_b]

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)
    area_b = max((bx2 - bx1) * (by2 - by1), 1e-6)
    return inter / area_b


def _pts_to_str(pts_ms: float) -> str:
    total_sec = max(0.0, pts_ms / 1000.0)
    minutes = int(total_sec // 60)
    seconds = total_sec % 60
    return f"{minutes:02d}:{seconds:05.2f}"


def enhance_plate_crop(plate_img: Optional[np.ndarray], target_min_width: int = 240) -> Optional[np.ndarray]:
    """Enhance and upscale small plate crops for sharp, legible display."""
    if plate_img is None or plate_img.size == 0:
        return plate_img
    try:
        ph, pw = plate_img.shape[:2]
        if 0 < pw < target_min_width and ph > 0:
            scale = min(4.0, max(1.5, float(target_min_width) / float(pw)))
            new_w = int(pw * scale)
            new_h = int(ph * scale)
            upscaled = cv2.resize(plate_img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            gaussian = cv2.GaussianBlur(upscaled, (0, 0), 1.0)
            sharpened = cv2.addWeighted(upscaled, 1.25, gaussian, -0.25, 0)
            return sharpened
    except Exception:
        pass
    return plate_img


class VideoAnalysisPipeline:
    """
    End-to-end CV pipeline for processing any video file.
    Supports honest stage-based status callbacks and produces
    downloadable CSV, JSON, annotated video, and evidence crops.
    """

    def __init__(
        self,
        video_path: str,
        output_dir: str,
        config: Optional[dict] = None,
        progress_callback: Optional[Callable[[str, int, int, dict], None]] = None,
    ):
        self.video_path = str(video_path)
        self.output_dir = str(output_dir)
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.progress_callback = progress_callback

        self.evidence_dir = os.path.join(output_dir, "evidence")
        self.logs_dir = os.path.join(output_dir, "logs")
        os.makedirs(self.evidence_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)

        self.detector: Optional[VehicleDetector] = None
        self.tracker: Optional[VehicleTracker] = None
        self.ocr_engine = None
        self.segmenter: Optional[SightingSegmenter] = None

        self.stats = {
            "total_frames_read": 0,
            "total_frames_processed": 0,
            "total_vehicle_detections": 0,
            "total_plate_detections": 0,
            "total_ocr_reads": 0,
            "processing_start": None,
            "processing_end": None,
        }

    def _report_progress(self, stage: str, current_frame: int, total_frames: int):
        if self.progress_callback:
            try:
                self.progress_callback(stage, current_frame, total_frames, dict(self.stats))
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")

    def _init_components(self, model_path: str):
        """Initialize all CV components."""
        logger.info(f"Initializing CV components with model: {model_path}")
        self._report_progress("INITIALIZING", 0, 0)

        # Optimize PyTorch CPU multi-threading
        try:
            import torch
            num_threads = min(8, max(2, os.cpu_count() or 4))
            torch.set_num_threads(num_threads)
        except Exception:
            pass

        self.detector = VehicleDetector(
            model_path=model_path,
            conf_threshold=self.config["DETECTION_CONFIDENCE"],
            imgsz=self.config["INFERENCE_SIZE"],
            device="cpu",
        )
        self.detector.warmup()

        self.tracker = VehicleTracker(
            max_age_sec=self.config["TRACK_MAX_AGE_SEC"],
            min_hits=self.config["TRACK_MIN_HITS"],
            iou_threshold=self.config["TRACK_IOU_THRESHOLD"],
        )

        try:
            from anpr.ocr import RapidOcrEngine
            self.ocr_engine = RapidOcrEngine(gpu=False)
            logger.info("Using RapidOCR engine (ONNX runtime, offline)")
        except Exception as e:
            logger.info(f"RapidOCR unavailable ({e}), falling back to EasyOCR")
            self.ocr_engine = OcrEngine(languages=("en",), gpu=False)

        self.ocr_engine.warmup()

        self.segmenter = SightingSegmenter(
            track_end_gap_seconds=self.config["TRACK_END_GAP_SEC"],
            sighting_cooldown_seconds=self.config["SIGHTING_COOLDOWN_SEC"],
            min_sighting_frames=self.config["MIN_SIGHTING_FRAMES"],
            min_sighting_duration_sec=self.config["MIN_SIGHTING_DURATION"],
        )
        logger.info("All CV components initialized successfully.")

    def process_video(
        self,
        model_path: Optional[str] = None,
        max_seconds: float = 0,
        generate_annotated: bool = True,
    ) -> dict:
        """Process the video end-to-end."""
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"Video file not found: {self.video_path}")

        if not model_path:
            model_path = find_model()

        self._init_components(model_path)
        video_props = probe_video(self.video_path)
        if not video_props.get("first_frame_readable"):
            raise RuntimeError(f"Could not read first frame of video: {self.video_path}")

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {self.video_path}")

        fps = video_props["fps"]
        total_frames = video_props["frame_count"]
        width, height = video_props["width"], video_props["height"]

        if max_seconds > 0:
            max_frames = min(total_frames, int(max_seconds * fps))
        else:
            max_frames = total_frames

        target_fps = float(self.config.get("TARGET_FPS", 5.0))
        configured_skip = int(self.config.get("FRAME_SKIP", 4))
        if target_fps > 0 and fps > target_fps:
            effective_skip = max(configured_skip, int(round(fps / target_fps)))
        else:
            effective_skip = configured_skip

        out_writer = None
        annotated_path = None
        if generate_annotated:
            annotated_path = os.path.join(self.output_dir, "annotated_video.mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out_fps = max(5.0, min(30.0, fps / effective_skip if effective_skip > 1 else fps))
            out_width = min(1920, width)
            out_height = int(height * (out_width / width)) if width > 0 else height
            out_writer = cv2.VideoWriter(annotated_path, fourcc, out_fps, (out_width, out_height))

        self.stats["processing_start"] = time.time()
        frame_index = 0
        processed_count = 0
        ocr_counter: Dict[int, int] = {}
        confirmed_tracks: Dict[int, dict] = {}
        last_progress_time = 0.0

        try:
            while True:
                ret, frame = cap.read()
                if not ret or (max_frames > 0 and frame_index >= max_frames):
                    break

                self.stats["total_frames_read"] += 1
                pts_ms = (frame_index / fps) * 1000.0 if fps > 0 else frame_index * 33.33

                # Adaptive frame stride: surveillance vehicles only need ~5 fps
                if effective_skip > 1 and (frame_index % effective_skip) != 0:
                    frame_index += 1
                    continue

                processed_count += 1
                self.stats["total_frames_processed"] += 1

                # ── Detection ──
                if getattr(self.detector, "plate_class_ids", None):
                    all_classes = self.detector.class_ids + self.detector.plate_class_ids
                    all_detections = self.detector.detect(
                        frame, camera_id="video_upload", pts_ms=pts_ms, classes=all_classes
                    )
                    vehicle_detections = [d for d in all_detections if d.class_id in self.detector.class_ids]
                    plate_detections = [d for d in all_detections if d.class_id in self.detector.plate_class_ids]
                else:
                    vehicle_detections = self.detector.detect(
                        frame, camera_id="video_upload", pts_ms=pts_ms
                    )
                    plate_detections = self.detector.detect_plates(
                        frame, camera_id="video_upload", pts_ms=pts_ms
                    )

                self.stats["total_vehicle_detections"] += len(vehicle_detections)
                self.stats["total_plate_detections"] += len(plate_detections)

                # ── Tracking ──
                tracks = self.tracker.update(vehicle_detections, pts_ms=pts_ms)

                # ── ANPR: Plate detection + OCR ──
                plate_readings: Dict[int, Tuple[Optional[str], Optional[str], float]] = {}
                plate_crops: Dict[int, np.ndarray] = {}
                plate_bboxes: Dict[int, List[float]] = {}

                # 1-to-1 greedy matching between tracks and detected plate boxes
                matched_plates: Dict[int, Detection] = {}
                if plate_detections:
                    overlap_pairs = []
                    for track in tracks:
                        if track.time_since_update_ms > 0:
                            continue
                        for p_idx, pdet in enumerate(plate_detections):
                            overlap = _bbox_overlap(track.bbox, pdet.bbox)
                            if overlap > 0.25:
                                overlap_pairs.append((overlap, track.track_id, p_idx))
                    overlap_pairs.sort(key=lambda x: x[0], reverse=True)
                    assigned_tracks = set()
                    assigned_plates = set()
                    for _, tid, p_idx in overlap_pairs:
                        if tid not in assigned_tracks and p_idx not in assigned_plates:
                            matched_plates[tid] = plate_detections[p_idx]
                            assigned_tracks.add(tid)
                            assigned_plates.add(p_idx)

                for track in tracks:
                    if track.time_since_update_ms > 0:
                        continue

                    tid = track.track_id
                    ocr_counter.setdefault(tid, 0)
                    ocr_counter[tid] += 1

                    # Smart OCR Gating:
                    # If this track already has a confirmed plate (conf >= 0.78 or format score == 1.0)
                    # and >= 2 reads, throttle OCR to once every 15 processed frames.
                    is_confirmed = False
                    if tid in confirmed_tracks:
                        info = confirmed_tracks[tid]
                        if info.get("hits", 0) >= 2 and (info.get("conf", 0.0) >= 0.78 or info.get("score", 0.0) == 1.0):
                            is_confirmed = True

                    interval = 15 if is_confirmed else self.config.get("OCR_INTERVAL_FRAMES", 3)
                    if ocr_counter[tid] % interval != 1:
                        # Retain plate crop and bbox from current frame if plate was detected
                        if tid in matched_plates:
                            pdet = matched_plates[tid]
                            plate_crops[tid] = _safe_crop(frame, pdet.bbox, padding_ratio=0.06)
                            plate_bboxes[tid] = [float(v) for v in pdet.bbox]
                        continue

                    plate_crop = None
                    p_bbox = None

                    if tid in matched_plates:
                        pdet = matched_plates[tid]
                        plate_crop = _safe_crop(frame, pdet.bbox, padding_ratio=0.06)
                        p_bbox = [float(v) for v in pdet.bbox]
                    elif ocr_counter[tid] <= 3 and tid not in confirmed_tracks:
                        # Fallback plate candidate extraction only on first few frames for unseen tracks
                        candidates = extract_plate_candidates(frame, track.bbox, track.class_name)
                        if candidates and candidates[0] is not None and candidates[0].size > 0:
                            plate_crop = candidates[0]
                            bx1, by1, bx2, by2 = track.bbox
                            bw, bh = bx2 - bx1, by2 - by1
                            if track.class_name != "motorcycle":
                                p_bbox = [float(bx1 + bw * 0.15), float(by1 + bh * 0.5), float(bx2 - bw * 0.15), float(by2)]
                            else:
                                p_bbox = [float(bx1 + bw * 0.1), float(by1 + bh * 0.35), float(bx2 - bw * 0.1), float(by2)]

                    if plate_crop is None or plate_crop.size == 0:
                        continue

                    try:
                        prep = preprocess_for_ocr(plate_crop)
                        lines = self.ocr_engine.read(prep)
                        self.stats["total_ocr_reads"] += 1
                    except Exception as ocr_err:
                        logger.debug("OCR reading error: %s", ocr_err)
                        lines = []

                    best_candidate = None
                    best_conf = 0.0
                    best_raw = None

                    for line in lines:
                        norm = candidate_from_ocr_text(line.text)
                        if norm and line.confidence >= self.config["OCR_MIN_CONFIDENCE"]:
                            score = plate_format_score(norm)
                            effective_conf = float(line.confidence) * (1.0 if score == 1.0 else 0.75)
                            if effective_conf > best_conf:
                                best_candidate = norm
                                best_conf = float(line.confidence)
                                best_raw = line.text

                    if len(lines) > 1:
                        combined_text = " ".join(l.text for l in lines)
                        combined_norm = candidate_from_ocr_text(combined_text)
                        if combined_norm:
                            combined_conf = sum(float(l.confidence) for l in lines) / len(lines)
                            score = plate_format_score(combined_norm)
                            effective_conf = combined_conf * (1.0 if score == 1.0 else 0.75)
                            if effective_conf > best_conf and combined_conf >= self.config["OCR_MIN_CONFIDENCE"]:
                                best_candidate = combined_norm
                                best_conf = combined_conf
                                best_raw = combined_text

                    if best_candidate is not None:
                        plate_readings[tid] = (best_raw, best_candidate, best_conf)
                        plate_crops[tid] = plate_crop.copy()
                        if p_bbox is not None:
                            plate_bboxes[tid] = p_bbox

                        # Register confirmed reading for smart throttling
                        score = plate_format_score(best_candidate)
                        c_info = confirmed_tracks.setdefault(
                            tid, {"hits": 0, "conf": 0.0, "score": 0.0, "plate": best_candidate}
                        )
                        c_info["hits"] += 1
                        c_info["conf"] = max(c_info["conf"], best_conf)
                        c_info["score"] = max(c_info["score"], score)
                    elif plate_crop is not None and plate_crop.size > 0:
                        # Retain plate crop even if OCR was unreadable
                        plate_crops[tid] = plate_crop.copy()
                        if p_bbox is not None:
                            plate_bboxes[tid] = p_bbox

                # ── Sighting Segmentation ──
                active_track_ids = [t.track_id for t in tracks]
                track_data = {}
                for t in tracks:
                    track_data[t.track_id] = {
                        "bbox": t.bbox,
                        "class_name": t.class_name,
                        "confidence": t.confidence,
                    }

                self.segmenter.update(
                    frame_index=frame_index,
                    pts_ms=pts_ms,
                    active_track_ids=active_track_ids,
                    track_data=track_data,
                    plate_readings=plate_readings,
                    frame=frame,
                    plate_crops=plate_crops,
                    plate_bboxes=plate_bboxes,
                )

                # ── Annotated Frame ──
                if out_writer is not None:
                    annotated = self._annotate_frame(
                        frame.copy(), frame_index, pts_ms,
                        vehicle_detections, plate_detections, tracks,
                        plate_readings,
                    )
                    if (annotated.shape[1], annotated.shape[0]) != (out_width, out_height):
                        annotated = cv2.resize(annotated, (out_width, out_height))
                    out_writer.write(annotated)

                # Honest stage callback (throttled to avoid flooding)
                now = time.time()
                if now - last_progress_time >= 0.5 or frame_index == 0:
                    current_stage = (
                        "READING_NUMBER_PLATES"
                        if len(plate_readings) > 0 or self.stats["total_plate_detections"] > 0
                        else "DETECTING_VEHICLES"
                    )
                    self._report_progress(current_stage, frame_index + 1, max_frames or total_frames)
                    last_progress_time = now

                frame_index += 1

        finally:
            cap.release()
            if out_writer is not None:
                out_writer.release()
                if annotated_path and os.path.exists(annotated_path):
                    try:
                        import imageio_ffmpeg, subprocess
                        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                        tmp_web = annotated_path + ".web.mp4"
                        cmd = [
                            ffmpeg_exe, "-y", "-i", annotated_path,
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                            tmp_web,
                        ]
                        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if os.path.exists(tmp_web):
                            os.replace(tmp_web, annotated_path)
                    except Exception:
                        pass

        self.stats["processing_end"] = time.time()
        self._report_progress("GENERATING_RESULTS", max_frames or total_frames, max_frames or total_frames)

        # Finalize sightings
        self.segmenter.finalize()

        # Generate outputs
        results = self._generate_outputs(video_props, annotated_path)
        self._report_progress("COMPLETED", max_frames or total_frames, max_frames or total_frames)
        return results

    def _annotate_frame(
        self,
        frame: np.ndarray,
        frame_index: int,
        pts_ms: float,
        vehicle_dets: List[Detection],
        plate_dets: List[Detection],
        tracks: List[Track],
        plate_readings: Dict[int, Tuple],
    ) -> np.ndarray:
        """Draw detection overlays on a frame."""
        h, w = frame.shape[:2]
        scale = max(1.0, w / 1280.0)
        thickness = max(2, int(2 * scale))
        font_scale = max(0.45, 0.45 * scale)
        font_thick = max(1, int(1.5 * scale))

        # Vehicle bboxes
        for det in vehicle_dets:
            x1, y1, x2, y2 = [int(v) for v in det.bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), thickness)

        # Plate bboxes
        for det in plate_dets:
            x1, y1, x2, y2 = [int(v) for v in det.bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 255), thickness)

        # Tracks + OCR text
        for track in tracks:
            x1, y1, x2, y2 = [int(v) for v in track.bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 128, 0), thickness)

            label = f"{track.class_name.upper()} | TRACK {track.track_id}"
            if track.track_id in plate_readings:
                raw, norm, conf = plate_readings[track.track_id]
                if conf >= 0.5:
                    label += f" | {norm} {conf*100:.0f}%"
                else:
                    label += " | PLATE UNCERTAIN"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thick)
            pad = int(4 * scale)
            cv2.rectangle(frame, (x1, max(0, y1 - th - pad * 2)), (x1 + tw + pad * 2, y1), (255, 128, 0), -1)
            cv2.putText(frame, label, (x1 + pad, max(th + pad, y1 - pad)),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), font_thick, cv2.LINE_AA)

        # Top banner
        filename = os.path.basename(self.video_path)
        timestamp = pts_ms / 1000.0
        banner = f"TRINETRA AI | {filename} | Frame: {frame_index} | Time: {timestamp:.1f}s | Active Tracks: {len(tracks)}"
        banner_h = int(36 * scale)
        cv2.rectangle(frame, (0, 0), (w, banner_h), (20, 20, 20), -1)
        cv2.putText(frame, banner, (int(10 * scale), int(24 * scale)),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale * 1.1, (255, 255, 255), font_thick, cv2.LINE_AA)

        return frame

    def _generate_outputs(self, video_props: dict, annotated_path: Optional[str]) -> dict:
        """Generate all output files: JSON, CSV, evidence, summary."""
        sightings = self.segmenter.get_all_sightings()
        by_plate = self.segmenter.get_sightings_by_plate()
        plate_summary = self.segmenter.get_plate_summary()

        processing_time = (self.stats["processing_end"] - self.stats["processing_start"]
                           if self.stats["processing_end"] and self.stats["processing_start"]
                           else 0)

        # ── Save evidence frames ──
        for sighting in sightings:
            if sighting.best_frame_image is not None:
                fname = f"sighting_{sighting.sighting_id:02d}.jpg"
                fpath = os.path.join(self.evidence_dir, fname)
                cv2.imwrite(fpath, sighting.best_frame_image,
                            [cv2.IMWRITE_JPEG_QUALITY, self.config["EVIDENCE_JPEG_QUALITY"]])

            # Vehicle crop (atomic to representative frame with padding)
            if sighting.best_vehicle_crop is not None and sighting.best_vehicle_crop.size > 0:
                vname = f"sighting_{sighting.sighting_id:02d}_vehicle.jpg"
                vpath = os.path.join(self.evidence_dir, vname)
                cv2.imwrite(vpath, sighting.best_vehicle_crop,
                            [cv2.IMWRITE_JPEG_QUALITY, self.config["EVIDENCE_JPEG_QUALITY"]])
            elif sighting.best_frame and sighting.best_frame_image is not None:
                v_crop = _safe_crop(sighting.best_frame_image, sighting.best_frame.bbox, padding_ratio=0.08)
                if v_crop is not None and v_crop.size > 0:
                    vname = f"sighting_{sighting.sighting_id:02d}_vehicle.jpg"
                    vpath = os.path.join(self.evidence_dir, vname)
                    cv2.imwrite(vpath, v_crop,
                                [cv2.IMWRITE_JPEG_QUALITY, self.config["EVIDENCE_JPEG_QUALITY"]])

            # Plate crop (strictly atomic to representative frame - enhanced and saved)
            p_saved = False
            if sighting.best_plate_crop is not None and sighting.best_plate_crop.size > 0:
                fname = f"sighting_{sighting.sighting_id:02d}_plate.jpg"
                fpath = os.path.join(self.evidence_dir, fname)
                enhanced_plate = enhance_plate_crop(sighting.best_plate_crop)
                cv2.imwrite(fpath, enhanced_plate if enhanced_plate is not None else sighting.best_plate_crop,
                            [cv2.IMWRITE_JPEG_QUALITY, self.config["EVIDENCE_JPEG_QUALITY"]])
                p_saved = True
            elif sighting.best_frame and sighting.best_frame.plate_bbox and sighting.best_frame_image is not None:
                p_cr = _safe_crop(sighting.best_frame_image, sighting.best_frame.plate_bbox, padding_ratio=0.06)
                if p_cr is not None and p_cr.size > 0:
                    fname = f"sighting_{sighting.sighting_id:02d}_plate.jpg"
                    fpath = os.path.join(self.evidence_dir, fname)
                    enhanced_plate = enhance_plate_crop(p_cr)
                    cv2.imwrite(fpath, enhanced_plate if enhanced_plate is not None else p_cr,
                                [cv2.IMWRITE_JPEG_QUALITY, self.config["EVIDENCE_JPEG_QUALITY"]])
                    p_saved = True
            elif sighting.best_vehicle_crop is not None and sighting.best_vehicle_crop.size > 0:
                vh, vw = sighting.best_vehicle_crop.shape[:2]
                if vh >= 24 and vw >= 24:
                    cand_plate = sighting.best_vehicle_crop[int(vh * 0.5):, int(vw * 0.15):int(vw * 0.85)]
                    if cand_plate is not None and cand_plate.size > 0:
                        fname = f"sighting_{sighting.sighting_id:02d}_plate.jpg"
                        fpath = os.path.join(self.evidence_dir, fname)
                        enhanced_plate = enhance_plate_crop(cand_plate)
                        cv2.imwrite(fpath, enhanced_plate if enhanced_plate is not None else cand_plate,
                                    [cv2.IMWRITE_JPEG_QUALITY, self.config["EVIDENCE_JPEG_QUALITY"]])
                        p_saved = True

        # ── vehicle_sightings.json ──
        sightings_data = []
        video_filename = os.path.basename(self.video_path)
        for s in sightings:
            d = s.to_dict()
            d["video_filename"] = video_filename
            rep_frame = s.representative_frame_index if s.representative_frame_index is not None else (s.best_frame.frame_index if s.best_frame else s.first_frame_index)
            rep_pts = s.representative_pts_ms if s.representative_pts_ms is not None else (s.best_frame.pts_ms if s.best_frame else s.first_pts_ms)
            d["frame_number"] = rep_frame
            d["pts_ms"] = round(rep_pts, 2)
            d["evidence_frame"] = f"evidence/sighting_{s.sighting_id:02d}.jpg" if s.best_frame_image is not None else None
            has_vcrop = os.path.exists(os.path.join(self.evidence_dir, f"sighting_{s.sighting_id:02d}_vehicle.jpg"))
            d["evidence_vehicle"] = f"evidence/sighting_{s.sighting_id:02d}_vehicle.jpg" if has_vcrop else None
            has_pcrop = os.path.exists(os.path.join(self.evidence_dir, f"sighting_{s.sighting_id:02d}_plate.jpg"))
            d["evidence_plate"] = f"evidence/sighting_{s.sighting_id:02d}_plate.jpg" if has_pcrop else None
            sightings_data.append(d)

        json_path = os.path.join(self.output_dir, "vehicle_sightings.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sightings_data, f, indent=2, ensure_ascii=False)

        # ── vehicle_sightings.csv ──
        csv_rows = []
        for s in sightings:
            primary_track = s.track_ids[0] if s.track_ids else ""
            plate_txt = s.final_plate if s.final_plate else "UNKNOWN"
            ev_img = f"evidence/sighting_{s.sighting_id:02d}.jpg" if s.best_frame_image is not None else ""
            has_vcrop = os.path.exists(os.path.join(self.evidence_dir, f"sighting_{s.sighting_id:02d}_vehicle.jpg"))
            ev_veh = f"evidence/sighting_{s.sighting_id:02d}_vehicle.jpg" if has_vcrop else ""
            has_pcrop = os.path.exists(os.path.join(self.evidence_dir, f"sighting_{s.sighting_id:02d}_plate.jpg"))
            ev_plt = f"evidence/sighting_{s.sighting_id:02d}_plate.jpg" if has_pcrop else ""
            det_conf = round(s.best_frame.confidence, 4) if s.best_frame else 0.0
            rep_frame = s.representative_frame_index if s.representative_frame_index is not None else (s.best_frame.frame_index if s.best_frame else s.first_frame_index)
            rep_pts = s.representative_pts_ms if s.representative_pts_ms is not None else (s.best_frame.pts_ms if s.best_frame else s.first_pts_ms)
            v_bbox = s.representative_vehicle_bbox or (s.best_frame.bbox if s.best_frame else None)
            p_bbox = s.representative_plate_bbox or (s.best_frame.plate_bbox if s.best_frame else None)

            csv_rows.append({
                "sighting_id": s.sighting_id,
                "vehicle_track_id": primary_track,
                "plate_text": plate_txt,
                "plate_confidence": round(s.plate_confidence, 4) if s.final_plate else 0.0,
                "detection_confidence": det_conf,
                "start_timestamp": s.timestamp_str,
                "end_timestamp": _pts_to_str(s.last_pts_ms),
                "duration": round(s.duration_sec, 2),
                "frame_number": rep_frame,
                "pts_ms": round(rep_pts, 2),
                "vehicle_bbox": json.dumps(v_bbox) if v_bbox else "",
                "plate_bbox": json.dumps(p_bbox) if p_bbox else "",
                "evidence_frame": ev_img,
                "evidence_vehicle": ev_veh,
                "evidence_plate": ev_plt,
                "video_filename": video_filename,
            })

        csv_path = os.path.join(self.output_dir, "vehicle_sightings.csv")
        fieldnames = [
            "sighting_id", "vehicle_track_id", "plate_text", "plate_confidence",
            "detection_confidence", "start_timestamp", "end_timestamp", "duration",
            "frame_number", "pts_ms", "vehicle_bbox", "plate_bbox",
            "evidence_frame", "evidence_vehicle", "evidence_plate", "video_filename",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

        # ── Target vehicle report ──
        target = self.segmenter.find_target_vehicle(expected_sightings=5)
        target_report = self._build_target_report(target)
        target_path = os.path.join(self.output_dir, "target_vehicle_report.json")
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(target_report, f, indent=2, ensure_ascii=False)

        # ── Summary ──
        avg_inference = 0
        if self.detector and self.detector.frames_inferred > 0:
            avg_inference = (self.detector.last_inference_ms or 0)

        summary = {
            "video_path": video_props.get("path", ""),
            "video_filename": video_filename,
            "video_duration_sec": round(video_props.get("duration_sec", 0), 2),
            "video_resolution": video_props.get("resolution", ""),
            "video_fps": video_props.get("fps", 0),
            "video_codec": video_props.get("codec", ""),
            "total_frames_in_video": video_props.get("frame_count", 0),
            "total_frames_read": self.stats["total_frames_read"],
            "total_frames_processed": self.stats["total_frames_processed"],
            "frame_skip": self.config["FRAME_SKIP"],
            "total_vehicle_detections": self.stats["total_vehicle_detections"],
            "total_plate_detections": self.stats["total_plate_detections"],
            "total_ocr_reads": self.stats["total_ocr_reads"],
            "unique_tracks": self.tracker._next_id - 1 if self.tracker else 0,
            "total_sightings": len(sightings),
            "unique_plates": len([p for p in by_plate.keys() if p != "UNKNOWN"]),
            "plate_summary": plate_summary,
            "target_vehicle": target_report.get("plate") if target_report else None,
            "target_sighting_count": target_report.get("sighting_count") if target_report else 0,
            "processing_time_sec": round(processing_time, 2),
            "average_inference_ms": round(avg_inference, 2),
            "annotated_video": annotated_path,
            "output_dir": self.output_dir,
            "config": self.config,
        }
        summary_path = os.path.join(self.output_dir, "summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        return summary

    def _build_target_report(self, target: Optional[dict]) -> dict:
        """Build target vehicle report."""
        if target is None:
            return {
                "status": "No vehicle with validated plate sightings was found.",
                "plate": None,
                "sighting_count": 0,
                "exact_match": False,
                "sightings": [],
            }

        sightings_detail = []
        for i, s in enumerate(target["sightings"], 1):
            detail = {
                "sighting_number": i,
                "sighting_id": s.sighting_id,
                "timestamp": s.timestamp_str,
                "timestamp_pts_ms": s.first_pts_ms,
                "track_ids": s.track_ids,
                "vehicle_class": s.vehicle_class,
                "plate": s.final_plate,
                "plate_confidence": round(s.plate_confidence, 4),
                "supporting_frames": s.supporting_frame_count,
                "duration_sec": round(s.duration_sec, 2),
                "evidence_frame": f"evidence/sighting_{s.sighting_id:02d}.jpg" if os.path.exists(os.path.join(self.evidence_dir, f"sighting_{s.sighting_id:02d}.jpg")) else None,
                "evidence_plate": f"evidence/sighting_{s.sighting_id:02d}_plate.jpg" if os.path.exists(os.path.join(self.evidence_dir, f"sighting_{s.sighting_id:02d}_plate.jpg")) else None,
            }
            sightings_detail.append(detail)

        return {
            "status": "exact_match" if target["exact_match"] else "closest_match",
            "plate": target["plate"],
            "sighting_count": target["sighting_count"],
            "exact_match": target["exact_match"],
            "sightings": sightings_detail,
        }

    def _print_report(self, summary: dict, target_report: dict, plate_summary: list):
        """Print the final human-readable report."""
        print("\n" + "=" * 70)
        print("  TRINETRA AI — VIDEO DETECTION & ANPR REPORT")
        print("=" * 70)
        print(f"  VIDEO:             {summary.get('video_path')}")
        print(f"  DURATION:          {summary.get('video_duration_sec', 0):.1f}s")
        print(f"  RESOLUTION:        {summary.get('video_resolution')}")
        print(f"  FPS:               {summary.get('video_fps')}")
        print(f"  CODEC:             {summary.get('video_codec')}")
        print(f"  FRAMES:            {summary.get('total_frames_in_video', 0)} total, {summary.get('total_frames_processed', 0)} processed")
        print(f"  VEHICLES:          {summary.get('total_vehicle_detections', 0)} detections")
        print(f"  PLATES:            {summary.get('total_plate_detections', 0)} detections")
        print(f"  OCR READS:         {summary.get('total_ocr_reads', 0)}")
        print(f"  UNIQUE TRACKS:     {summary.get('unique_tracks', 0)}")
        print(f"  TOTAL SIGHTINGS:   {summary.get('total_sightings', 0)}")
        print(f"  UNIQUE PLATES:     {summary.get('unique_plates', 0)}")
        print(f"  PROCESSING TIME:   {summary.get('processing_time_sec', 0):.1f}s")
        print("-" * 70)

        if plate_summary:
            print("\n  PLATE SUMMARY:")
            for ps in plate_summary:
                print(f"    {ps['plate']:15s} → {ps['sighting_count']} sightings (avg conf: {ps['avg_confidence']:.2f})")
                for ts in ps.get('timestamps', []):
                    print(f"      @ {ts}")

        print("-" * 70)
        print("\n  TARGET VEHICLE REPORT:")
        if target_report.get("plate"):
            print(f"    Plate:           {target_report['plate']}")
            print(f"    Sightings:       {target_report['sighting_count']}")
            print(f"    Exact match:     {target_report.get('exact_match', False)}")
            if target_report.get("note"):
                print(f"    Note:            {target_report['note']}")
            print()
            for s in target_report.get("sightings", []):
                print(f"    SIGHTING #{s['sighting_number']}")
                print(f"      Timestamp:     {s['timestamp']} ({s.get('timestamp_pts_ms', 0):.0f}ms)")
                print(f"      Track IDs:     {s['track_ids']}")
                print(f"      Confidence:    {s['plate_confidence']:.2f}")
                print(f"      Duration:      {s['duration_sec']:.1f}s")
                print(f"      Evidence:      {s['evidence_frame']}")
                print()
        else:
            print(f"    {target_report.get('status', 'No target found')}")

        print("-" * 70)
        print(f"  ANNOTATED VIDEO:   {summary.get('annotated_video', 'N/A')}")
        print(f"  JSON:              {os.path.join(summary['output_dir'], 'vehicle_sightings.json')}")
        print(f"  CSV:               {os.path.join(summary['output_dir'], 'vehicle_sightings.csv')}")
        print(f"  EVIDENCE:          {os.path.join(summary['output_dir'], 'evidence/')}")
        print(f"  SUMMARY:           {os.path.join(summary['output_dir'], 'summary.json')}")
        print("=" * 70)
