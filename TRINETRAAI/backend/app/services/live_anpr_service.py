"""Bounded live-camera ANPR, independent of the video playback clock.

One replaceable pending frame per camera, a small shared worker pool and no
per-frame database writes. Slow inference drops old frames, never stalls a
player. Only agreeing, real OCR reads produce sightings; unreadable plates
remain unknown. All viewers of a camera share its tracker and dedup window.
"""
from __future__ import annotations

import re
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4
from urllib.parse import quote

from sqlalchemy import func

from ..core.config import settings
from ..core.logging_config import logger
from ..core.paths import evidence_root
from ..core.vision import cv2, np
from ..database.database import SessionLocal
from ..database.models import Camera, CameraTrafficConfig, VehicleEvent
from .anpr_pipeline import PlateAttempt, PlateRead, TrackPlateAccumulator, read_plate_for_vehicle
from .event_service import event_message, store_event
from .ocr_service import ocr_service
from .live_tracker import LiveTracker
from .traffic_counting import TrafficConfig, TrafficCounter
from .vehicle_detection_service import vehicle_detection_service
from .ws_manager import ws_manager


# Small appearance sketch, not another model. Used to suppress an asynchronous
# overlay when the picture has visibly cut/panned since the sampled frame.
FRAME_SIGNATURE_SIZE = (16, 9)
SCENE_CHANGE_MEAN_ERROR = 24.0
# Photos are a bounded short-lived preview, not a write for every video frame.
PHOTO_PREVIEW_SECONDS = 30.0
MAX_PHOTO_BATCHES = 64
MAX_PHOTO_BYTES = 16 * 1024 * 1024


def frame_signature(frame) -> list[int]:
    small = cv2.resize(frame, FRAME_SIGNATURE_SIZE, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).reshape(-1).tolist()


def scenes_match(first, second) -> bool:
    if first is None or second is None:
        return True
    return bool(len(first) == len(second) and len(first) > 0
                and sum(abs(a - b) for a, b in zip(first, second)) / len(first) <= SCENE_CHANGE_MEAN_ERROR)


@dataclass
class LiveFrame:
    camera_id: str
    frame: np.ndarray
    source_id: str
    media_time: Optional[float]
    captured_at: datetime
    submitted_at: float
    discontinuity: bool = False
    signature: Optional[list[int]] = None
    capture_id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class PhotoBatch:
    submitted_at: float
    photos: list[dict]
    images: dict[tuple[int, str], bytes]

    @property
    def size(self) -> int:
        return sum(len(image) for image in self.images.values())


@dataclass
class TrackState:
    votes: TrackPlateAccumulator = field(default_factory=TrackPlateAccumulator)
    event_id: Optional[int] = None
    last_seen: float = 0.0
    last_read: float = float("-inf")


@dataclass
class CameraState:
    tracker: LiveTracker = field(default_factory=LiveTracker)
    traffic: Optional[TrafficCounter] = None
    traffic_config: Optional[TrafficConfig] = None
    traffic_revision: str = "default"
    pending_traffic_config: Optional[tuple] = None
    reset_traffic: bool = False
    traffic_config_error: Optional[str] = None
    tracks: dict[int, TrackState] = field(default_factory=dict)
    # plate -> (last time actually seen, persisted event id). Sliding cooldown
    # means a parked vehicle does NOT produce a notification every 60 seconds.
    recent: dict[str, tuple[float, int]] = field(default_factory=dict)
    source_id: str = ""
    last_submit: float = float("-inf")
    last_processed: float = float("-inf")
    media_time: Optional[float] = None
    shape: tuple = ()
    result: dict = field(default_factory=dict)
    cancelled: bool = False
    latest_capture_id: str = ""


class LiveAnprService:
    def __init__(self, session_factory=None, clock=time.monotonic):
        self._session_factory = session_factory or SessionLocal
        self._clock = clock
        self._condition = threading.Condition(threading.RLock())
        self._pending: OrderedDict[str, LiveFrame] = OrderedDict()
        self._states: dict[str, CameraState] = {}
        self._busy: set[str] = set()
        self._threads: list[threading.Thread] = []
        self._shutdown = False
        self._photo_batches: OrderedDict[tuple[str, str], PhotoBatch] = OrderedDict()
        self._photo_bytes = 0

    @property
    def enabled(self) -> bool:
        return settings.LIVE_ANPR_ENABLED and settings.VEHICLE_DETECTION_ENABLED

    def start(self) -> None:
        with self._condition:
            if any(t.is_alive() for t in self._threads):
                return
            self._shutdown = False
            self._threads = []
            if self.enabled:
                for n in range(settings.LIVE_ANPR_WORKERS):
                    thread = threading.Thread(target=self._worker, name=f"LiveANPR-{n}", daemon=True)
                    self._threads.append(thread)
                    thread.start()

    def stop(self) -> None:
        with self._condition:
            self._shutdown = True
            self._pending.clear()
            for state in self._states.values():
                state.cancelled = True
            self._condition.notify_all()
        for thread in self._threads:
            thread.join(timeout=5)
        with self._condition:
            self._states.clear()
            self._photo_batches.clear()
            self._photo_bytes = 0

    def forget(self, camera_id: str) -> None:
        key = camera_id.strip().upper()
        with self._condition:
            self._pending.pop(key, None)
            state = self._states.pop(key, None)
            if state:
                state.cancelled = True
            for photo_key in [k for k in self._photo_batches if k[0] == key]:
                self._photo_bytes -= self._photo_batches.pop(photo_key).size

    def _reap(self, now: float) -> None:
        self._trim_photos(now)
        for key, state in list(self._states.items()):
            if key not in self._busy and now - state.last_submit > settings.LIVE_ANPR_IDLE_SECONDS:
                self.forget(key)

    def submit(self, camera_id: str, frame, *, source_id: str = "capture",
               media_time: Optional[float] = None, captured_at: Optional[datetime] = None,
               discontinuity: bool = False) -> bool:
        """Non-blocking admission. At most one pending frame per camera.

        A short source lease prevents independent playback sessions (two tabs
        looping the same file at different offsets) from mixing tracker votes.
        The next viewer takes over when the old source stops submitting frames.
        """
        if not self.enabled or frame is None or getattr(frame, "size", 0) == 0:
            return False
        if media_time is not None and (not math.isfinite(media_time) or media_time < 0):
            return False
        key = camera_id.strip().upper()
        now = self._clock()
        with self._condition:
            if self._shutdown:
                return False
            self._reap(now)
            state = self._states.get(key)
            if state is None:
                if len(self._states) >= settings.LIVE_ANPR_MAX_CAMERAS:
                    return False
                state = self._states[key] = CameraState()
            gap = now - state.last_submit
            if state.source_id != source_id and gap < max(3, settings.LIVE_ANPR_SAMPLE_SECONDS * 3):
                return False
            if gap < settings.LIVE_ANPR_SAMPLE_SECONDS and not discontinuity:
                return False
            # Never count a frozen decoder frame twice as multi-frame agreement.
            if (source_id == state.source_id and media_time is not None
                    and media_time == state.media_time and not discontinuity):
                return False
            reset = discontinuity or state.source_id != source_id
            state.source_id = source_id
            state.last_submit = now
            state.media_time = media_time
            # Copy only admitted frames; bound retained memory even for 4K cameras.
            h, w = frame.shape[:2]
            scale = min(1.0, 1280 / max(w, h))
            copied = (cv2.resize(frame, (round(w * scale), round(h * scale)))
                      if scale < 1 else frame.copy())
            previous = self._pending.get(key)
            self._pending[key] = LiveFrame(
                key, copied, source_id, media_time, captured_at or datetime.now(timezone.utc), now,
                reset or bool(previous and previous.discontinuity),
            )
            # Replacing a frame does not move a camera to the back of the queue:
            # one noisy camera cannot starve the others.
            self.start()
            self._condition.notify_all()
            return True

    def submit_packet(self, packet) -> bool:
        # CameraStream can generate clearly labelled demo frames on a failed
        # source in DEMO_MODE. They must NEVER enter the real sighting log.
        if packet.source_type == "demo":
            return False
        return self.submit(
            packet.camera_id, packet.frame, source_id="resident",
            media_time=packet.pts_ms / 1000.0, captured_at=packet.received_at,
            discontinuity=packet.is_discontinuity,
        )

    def snapshot(self, camera_id: str, *, source_id: Optional[str] = None) -> dict:
        key = camera_id.strip().upper()
        now = self._clock()
        with self._condition:
            state = self._states.get(key)
            result = dict(state.result) if state else {}
            submitted_at = result.pop("submitted_at", None)
            age = now - submitted_at if submitted_at is not None else None
            fresh = age is not None and age <= settings.LIVE_ANPR_OVERLAY_TTL_SECONDS
            if not fresh or (source_id and result.get("source_id") != source_id):
                result["detections"] = []
            status = result.get("status", "WARMING_UP" if state else "IDLE")
            if state and now - state.last_submit > settings.LIVE_ANPR_IDLE_SECONDS:
                status = "IDLE"
            if source_id and state and state.source_id != source_id:
                status = "SHARED"
                result["reason"] = "This camera is already being scanned by another active viewer."
            if not self.enabled:
                status = "DISABLED"
                result["detections"] = []
                result["reason"] = "Live ANPR is disabled on the backend."
            batch = self._photo_batches.get((key, state.latest_capture_id)) if state else None
            photos = ([dict(photo) for photo in batch.photos]
                      if batch and now - batch.submitted_at <= PHOTO_PREVIEW_SECONDS else [])
            return {
                **result, "camera_id": key.lower(), "status": status,
                "photos": photos,
                "detections": result.get("detections", []),
                "frame_width": result.get("frame_width", 0),
                "frame_height": result.get("frame_height", 0),
                "result_age_ms": round(age * 1000) if age is not None else None,
                "overlay_ttl_ms": round(settings.LIVE_ANPR_OVERLAY_TTL_SECONDS * 1000),
                "sample_interval_ms": round(settings.LIVE_ANPR_SAMPLE_SECONDS * 1000),
                "max_vehicles": settings.LIVE_ANPR_MAX_VEHICLES,
                "pending": key in self._pending or key in self._busy,
            }

    def _worker(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._shutdown or any(k not in self._busy for k in self._pending),
                    timeout=settings.LIVE_ANPR_IDLE_SECONDS,
                )
                if self._shutdown:
                    return
                self._reap(self._clock())
                key = next((k for k in self._pending if k not in self._busy), None)
                if key is None:
                    continue
                packet = self._pending.pop(key)
                state = self._states[key]
                self._busy.add(key)
            try:
                # Already superseded/offline by the time this worker became free.
                if self._clock() - packet.submitted_at <= settings.LIVE_ANPR_IDLE_SECONDS:
                    self._process(packet, state)
            except Exception:
                logger.exception("[LIVE ANPR:%s] Sample failed; playback is unaffected", key)
                self._publish(packet, state, [], "ERROR", "Plate processing failed; retrying the next sample.")
            finally:
                with self._condition:
                    self._busy.discard(key)
                    self._condition.notify_all()

    def _publish(self, packet, state, detections, status="SCANNING", reason=None) -> None:
        h, w = packet.frame.shape[:2]
        if packet.signature is None:
            packet.signature = frame_signature(packet.frame)
        with self._condition:
            if not state.cancelled:
                batch = self._photo_batches.get((packet.camera_id, packet.capture_id))
                if batch:
                    current = {d["track_id"]: d for d in detections}
                    for photo in batch.photos:
                        detection = current.get(photo["track_id"])
                        if detection:
                            for name in ("plate_number", "plate_status", "plate_confidence", "event_id",
                                         "ocr_state", "ocr_agreement_reads", "ocr_required_reads", "ocr_region_source"):
                                photo[name] = detection.get(name)
                state.result = {
                    "status": status, "reason": reason,
                    "source_id": packet.source_id, "media_time": packet.media_time,
                    "frame_width": w, "frame_height": h,
                    "frame_signature": packet.signature,
                    "submitted_at": packet.submitted_at,
                    "detections": [dict(d) for d in detections],
                    "processing_ms": round((self._clock() - packet.submitted_at) * 1000),
                    "ocr": ocr_service.runtime_status(),
                    "traffic": ({**state.traffic.snapshot(), "tracker": state.tracker.name,
                                 "max_tracked_vehicles": settings.LIVE_ANPR_MAX_TRACKED_VEHICLES,
                                 "ocr_budget": settings.LIVE_ANPR_MAX_VEHICLES,
                                 "configuration_error": state.traffic_config_error}
                                if state.traffic else None),
                }

    @staticmethod
    def _identity(ts: TrackState) -> dict:
        vote = ts.votes.best()
        if not vote or vote.reads < max(2, settings.ANPR_MIN_AGREE_READS):
            return dict(plate_number=None, plate_status="UNKNOWN", plate_confidence=None, event_id=None)
        return dict(plate_number=vote.normalized, plate_status=ts.votes.status(),
                    plate_confidence=ts.votes.aggregate_confidence(), event_id=ts.event_id)

    def _process(self, packet: LiveFrame, state: CameraState) -> None:
        if state.cancelled:
            return
        # Track/read expiry must scale with the configured cadence. A supported
        # 6s sampling interval must not reset every vote at a hardcoded 5s gap.
        max_gap = max(5.0, settings.LIVE_ANPR_SAMPLE_SECONDS * 3)
        packet.signature = frame_signature(packet.frame)
        scene_cut = not scenes_match(state.result.get("frame_signature"), packet.signature)
        previous_time = state.result.get("media_time")
        backwards = (packet.media_time is not None and previous_time is not None
                     and packet.media_time < previous_time)
        reset_reason = ("source changed/reconnected" if packet.discontinuity else
                        "video seek/loop" if backwards else "scene changed" if scene_cut else
                        "resolution changed" if state.shape and state.shape != packet.frame.shape else
                        "sampling gap" if packet.submitted_at - state.last_processed > max_gap else None)
        if reset_reason or not state.shape:
            state.tracker = LiveTracker()
            state.tracks.clear()
        self._prepare_traffic(packet, state, reset_reason)
        state.shape = packet.frame.shape
        state.last_processed = packet.submitted_at
        dets = vehicle_detection_service.detect(packet.frame)
        if not vehicle_detection_service.enabled:
            self._publish(packet, state, [], "UNAVAILABLE", "Vehicle model unavailable; install the ML requirements and weights.")
            return
        if vehicle_detection_service.last_error:
            self._publish(packet, state, [], "ERROR", "Vehicle inference failed; retrying the next sample.")
            return
        # Larger vehicles provide more plate pixels. Keep OCR cost bounded.
        dets = sorted(dets, key=lambda d: (d.x2-d.x1)*(d.y2-d.y1), reverse=True)
        input_limited = len(dets) > settings.LIVE_ANPR_MAX_TRACKED_VEHICLES
        dets = dets[:settings.LIVE_ANPR_MAX_TRACKED_VEHICLES]
        h, w = packet.frame.shape[:2]
        boxes = [(max(0, d.x1), max(0, d.y1), min(w, d.x2), min(h, d.y2), d.class_name, d.confidence)
                 for d in dets if min(w, d.x2) > max(0, d.x1) and min(h, d.y2) > max(0, d.y1)]
        time_s = packet.media_time if packet.media_time is not None else packet.submitted_at
        live, retired = state.tracker.update(boxes, time_s)
        state.traffic.update(live, time_s, w, h, max_gap=max_gap, input_limited=input_limited)
        for track in retired:
            state.tracks.pop(track.track_id, None)
        shown = sorted((t for t in live if t.misses == 0),
                       key=lambda t: (t.x2-t.x1)*(t.y2-t.y1), reverse=True)[:settings.LIVE_ANPR_MAX_VEHICLES]
        output = []
        for track in shown:
            ts = state.tracks.setdefault(track.track_id, TrackState())
            if (packet.submitted_at - ts.last_seen > max_gap
                    or packet.submitted_at - ts.last_read > max_gap):
                # A continuing vehicle box is not a continuing plate read.
                # Do not label unreadable/reassigned tracks with an old number.
                ts.votes = TrackPlateAccumulator()
                ts.event_id = None
            ts.last_seen = packet.submitted_at
            output.append(dict(x1=track.x1, y1=track.y1, x2=track.x2, y2=track.y2,
                               class_name=track.class_name, confidence=round(track.confidence, 4),
                               track_id=track.track_id, plate_box=None, **self._identity(ts),
                               ocr_state="READING" if not output else "QUEUED",
                               ocr_agreement_reads=ts.votes.best().reads if ts.votes.best() else 0,
                               ocr_required_reads=max(2, settings.ANPR_MIN_AGREE_READS),
                               ocr_region_source=None))
        # Make the actual vehicle photos available BEFORE OCR or plate voting.
        # Unreadable plates must not leave the Photo Evidence panel empty.
        self._cache_photos(packet, state, output)
        # Show vehicle boxes during cold-start and preserve fresh, confirmed
        # identities during rechecks instead of flickering to UNKNOWN every second.
        self._publish(packet, state, output, "PROCESSING")
        if not shown:
            self._publish(packet, state, output)
            return
        if not ocr_service.available:
            for detection in output:
                detection["ocr_state"] = "UNAVAILABLE"
            self._publish(packet, state, output, "UNAVAILABLE", "OCR unavailable; enable OCR_ENABLED and install rapidocr-onnxruntime.")
            return
        for index, (track, detection) in enumerate(zip(shown, output)):
            if state.cancelled:
                return
            ts = state.tracks[track.track_id]
            detection["ocr_state"] = "READING"
            if index:
                self._publish(packet, state, output, "PROCESSING")
            attempt = PlateAttempt()
            read = read_plate_for_vehicle(packet.frame, [track.x1, track.y1, track.x2, track.y2],
                                          track.class_name, diagnostics=attempt)
            if read:
                best = ts.votes.best()
                # A changed identity needs fresh agreement, not old majority votes
                # carried across two vehicles that happen to overlap geometrically.
                if best and best.normalized != read.normalized:
                    ts.votes = TrackPlateAccumulator()
                    ts.event_id = None
                ts.votes.add(read)
                ts.last_read = packet.submitted_at
                if read.plate_box:
                    b = read.plate_box
                    detection["plate_box"] = [b.x1, b.y1, b.x2, b.y2]
            region = read.plate_box if read and read.plate_box else attempt.region
            if region:
                self._cache_plate_photo(packet, track.track_id, region)
                detection["ocr_region_source"] = region.source
            # A contradictory read immediately clears the previously shown
            # identity; the replacement still needs two agreeing samples.
            detection.update(self._identity(ts))
            vote = ts.votes.best()
            detection["ocr_agreement_reads"] = vote.reads if vote else 0
            detection["ocr_state"] = ("CONFIRMED" if read and detection["plate_number"] else
                                      "CONFIRMING" if read else "RECENT_READ" if detection["plate_number"] else attempt.state)
            if detection["plate_number"] is None:
                self._publish(packet, state, output, "PROCESSING")
                continue
            previous = state.recent.get(vote.normalized)
            if previous and packet.submitted_at - previous[0] < settings.LIVE_ANPR_DEDUP_SECONDS:
                ts.event_id = previous[1]
            elif ts.event_id is None and read is not None and not state.cancelled:
                ts.event_id = self._persist(packet, track, ts, read)
            if ts.event_id is not None:
                state.recent[vote.normalized] = (packet.submitted_at, ts.event_id)
            detection["event_id"] = ts.event_id
            self._publish(packet, state, output, "PROCESSING")
        state.recent = {p: v for p, v in state.recent.items()
                        if packet.submitted_at - v[0] < settings.LIVE_ANPR_DEDUP_SECONDS}
        self._publish(packet, state, output)

    def configure_traffic(self, camera_id: str, config: TrafficConfig, revision: str) -> None:
        # Applied by the inference owner at a sample boundary. Never mutate a
        # tracker/counter while another thread is using it, or reset OCR votes.
        with self._condition:
            state = self._states.get(camera_id.strip().upper())
            if state:
                state.pending_traffic_config = (config, revision)

    def reset_traffic(self, camera_id: str) -> None:
        with self._condition:
            state = self._states.get(camera_id.strip().upper())
            if state:
                state.reset_traffic = True

    def _prepare_traffic(self, packet, state, tracking_reset):
        if state.traffic_config is None:
            config, revision = TrafficConfig(), "default"
            try:
                with self._session_factory() as db:
                    row = db.query(CameraTrafficConfig).filter(func.upper(CameraTrafficConfig.camera_id) == packet.camera_id).first()
                    if row:
                        config, revision = TrafficConfig.model_validate_json(row.config_json), row.revision
            except Exception:
                # Ancillary settings must not take down plate/photo inference.
                logger.warning("[LIVE ANPR:%s] Traffic configuration unavailable", packet.camera_id)
                state.traffic_config_error = "Traffic settings unavailable; crossing rules are off."
            state.traffic_config, state.traffic_revision = config, revision
        reason = tracking_reset
        with self._condition:
            if state.pending_traffic_config:
                state.traffic_config, state.traffic_revision = state.pending_traffic_config
                state.pending_traffic_config = None
                state.traffic_config_error = None
                reason = "counting settings changed"
            if state.reset_traffic:
                state.reset_traffic = False
                reason = "operator reset"
        if state.traffic is None or reason:
            state.traffic = TrafficCounter(state.traffic_config, started_at=packet.captured_at.isoformat(),
                                           reason=reason or "started", revision=state.traffic_revision)

    def _trim_photos(self, now: float) -> None:
        # Caller holds _condition. Limits are global, not multiplied by viewers.
        for key, batch in list(self._photo_batches.items()):
            if now - batch.submitted_at > PHOTO_PREVIEW_SECONDS:
                self._photo_bytes -= self._photo_batches.pop(key).size
        while self._photo_batches and (len(self._photo_batches) > MAX_PHOTO_BATCHES
                                       or self._photo_bytes > MAX_PHOTO_BYTES):
            _, batch = self._photo_batches.popitem(last=False)
            self._photo_bytes -= batch.size

    @staticmethod
    def _photo_jpeg(frame, box, max_side=640) -> Optional[bytes]:
        try:
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = [int(v) for v in box]
            crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if not crop.size:
                return None
            ch, cw = crop.shape[:2]
            scale = min(1.0, max_side / max(ch, cw))
            if scale < 1:
                crop = cv2.resize(crop, (max(1, round(cw * scale)), max(1, round(ch * scale))))
            ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            return encoded.tobytes() if ok else None
        except Exception:
            logger.warning("[LIVE ANPR] Could not encode a detection preview")
            return None

    def _cache_photos(self, packet, state, detections) -> None:
        photos, images = [], {}
        for detection in detections:
            track_id = detection["track_id"]
            image = self._photo_jpeg(packet.frame, [detection[k] for k in ("x1", "y1", "x2", "y2")])
            if image is None:
                continue
            path = f"/cameras/{quote(packet.camera_id.lower(), safe='')}/anpr/photos/{packet.capture_id}/{track_id}"
            images[(track_id, "vehicle")] = image
            photos.append(dict(
                id=f"{packet.capture_id}:{track_id}", track_id=track_id,
                class_name=detection["class_name"], image_path=f"{path}/vehicle.jpg",
                plate_image_path=None, captured_at=packet.captured_at.isoformat(),
                media_time=packet.media_time,
                **{k: detection.get(k) for k in ("plate_number", "plate_status", "plate_confidence", "event_id",
                                                "ocr_state", "ocr_agreement_reads", "ocr_required_reads", "ocr_region_source")},
            ))
        if not photos:
            return  # keep the last capture, labelled by its original timestamp
        with self._condition:
            if state.cancelled:
                return
            batch = PhotoBatch(packet.submitted_at, photos, images)
            key = (packet.camera_id, packet.capture_id)
            previous = self._photo_batches.pop(key, None)
            if previous:
                self._photo_bytes -= previous.size
            self._photo_batches[key] = batch
            self._photo_bytes += batch.size
            state.latest_capture_id = packet.capture_id
            self._trim_photos(self._clock())

    def _cache_plate_photo(self, packet, track_id, box) -> None:
        image = self._photo_jpeg(packet.frame, [box.x1, box.y1, box.x2, box.y2], max_side=320)
        if image is None:
            return
        with self._condition:
            batch = self._photo_batches.get((packet.camera_id, packet.capture_id))
            if not batch:
                return
            previous = batch.images.get((track_id, "plate"), b"")
            batch.images[(track_id, "plate")] = image
            self._photo_bytes += len(image) - len(previous)
            for photo in batch.photos:
                if photo["track_id"] == track_id:
                    photo["plate_image_path"] = photo["image_path"].replace("/vehicle.jpg", "/plate.jpg")
            self._trim_photos(self._clock())

    def photo(self, camera_id: str, capture_id: str, track_id: int, kind: str) -> Optional[bytes]:
        with self._condition:
            self._trim_photos(self._clock())
            batch = self._photo_batches.get((camera_id.strip().upper(), capture_id))
            return batch.images.get((track_id, kind)) if batch else None

    def _persist(self, packet, track, ts, read) -> Optional[int]:
        vote = ts.votes.best()
        with self._session_factory() as db:
            camera = db.query(Camera).filter(func.upper(Camera.camera_id) == packet.camera_id).first()
            if camera is None:
                return None  # registry entry was deleted while the sample ran
            # Survives a reconnect/service restart. Per-camera worker serialization
            # prevents concurrent viewers from writing the same sighting twice.
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.LIVE_ANPR_DEDUP_SECONDS)
            existing = db.query(VehicleEvent).filter(
                VehicleEvent.camera_id == camera.camera_id,
                VehicleEvent.plate_number == vote.normalized,
                VehicleEvent.created_at >= cutoff,
            ).order_by(VehicleEvent.id.desc()).first()
            if existing:
                return existing.id
            evidence_ref = self._write_evidence(packet, track, read)
            recorded = (camera.stream_type or "").lower() == "file"
            result = store_event(
                db=db, camera_id=camera.camera_id, vehicle_track_id=track.track_id,
                plate_raw=vote.best_raw, plate_confidence=ts.votes.aggregate_confidence(),
                vehicle_class=track.class_name, event_time=packet.captured_at,
                latitude=camera.latitude, longitude=camera.longitude, evidence_ref=evidence_ref,
                plate_status=ts.votes.status(), vehicle_confidence=track.confidence,
                bbox=[track.x1, track.y1, track.x2, track.y2],
                video_file=Path(camera.stream_url).name if recorded else None,
                video_offset_sec=packet.media_time if recorded else None,
            )
            # Fan-out only after persistence; never fabricate a notification on
            # an OCR, storage or transport failure. Uses the application's loop.
            ws_manager.broadcast_threadsafe(*event_message(*result))
            return result[0].id

    @staticmethod
    def _write_evidence(packet, track, read: PlateRead) -> Optional[str]:
        try:
            camera_dir = re.sub(r"[^a-z0-9_-]", "_", packet.camera_id.lower())[:50]
            ref = f"live/{camera_dir}/{uuid4().hex}.jpg"
            path = evidence_root() / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            crop = packet.frame[track.y1:track.y2, track.x1:track.x2]
            if not cv2.imwrite(str(path), crop):
                return None
            if read.plate_box:
                b = read.plate_box
                plate = packet.frame[b.y1:b.y2, b.x1:b.x2]
                if plate.size:
                    cv2.imwrite(str(path.with_name(path.stem + "_plate.jpg")), plate)
            return ref
        except Exception:
            logger.warning("[LIVE ANPR:%s] Evidence image unavailable", packet.camera_id)
            return None

    def annotate(self, camera_id: str, frame, *, source_id: Optional[str] = None,
                 media_time: Optional[float] = None):
        """Only draw a fresh result; rendering never performs model inference."""
        result = self.snapshot(camera_id, source_id=source_id)
        w, h = result["frame_width"], result["frame_height"]
        if not w or not h or not result["detections"]:
            return frame
        sample_time = result.get("media_time")
        if media_time is not None and sample_time is not None:
            if media_time < sample_time or media_time - sample_time > settings.LIVE_ANPR_OVERLAY_TTL_SECONDS:
                return frame  # seek/loop or decoder jumped ahead of the sampled picture
        if not scenes_match(result.get("frame_signature"), frame_signature(frame)):
            return frame  # video continues, but boxes from another picture do not
        sx, sy = frame.shape[1] / w, frame.shape[0] / h
        for d in result["detections"]:
            x1, y1, x2, y2 = [int(v * (sx if i % 2 == 0 else sy))
                               for i, v in enumerate((d["x1"], d["y1"], d["x2"], d["y2"]))]
            color = (0, 210, 255) if d["plate_status"] == "LOW_CONFIDENCE" else (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = d["plate_number"] or f'{d["class_name"]} - reading plate'
            if d["plate_status"] == "LOW_CONFIDENCE":
                label += " ?"
            cv2.putText(frame, label, (x1, max(16, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            if d["plate_box"]:
                a, b, c, e = d["plate_box"]
                cv2.rectangle(frame, (round(a*sx), round(b*sy)), (round(c*sx), round(e*sy)), color, 2)
        return frame


live_anpr_service = LiveAnprService()
