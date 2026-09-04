#!/usr/bin/env python
"""
LOCAL FEED DEMO RUNNER — real CV on local video files (no Sentinel network).

    Sentinel (unreachable on this network)
        -> replaced, clearly labelled, by a LOCAL DEMO FEED file
        -> frame (container PTS) -> YOLO11 detection -> ByteTrack tracking
        -> sighting events -> POST /api/events -> dashboard + SSE

Everything in the chain is REAL: real frames, real inference, real tracks,
real dedup, real backend ingestion. Only the video SOURCE is a local file,
and every annotated frame is watermarked "LOCAL DEMO FEED" so nobody mistakes
it for a government camera (spec: demo material must be unmistakable).

Also serves an annotated MJPEG preview per camera:

    http://0.0.0.0:8555/<camera_id>          (multipart/x-mixed-replace)

Usage:
    python scripts/run_feed_demo.py                      # all configured feeds
    python scripts/run_feed_demo.py --only camd01        # single feed
    python scripts/run_feed_demo.py --no-annotate        # skip MJPEG server
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CV_ROOT = Path(__file__).resolve().parents[1]
if str(CV_ROOT) not in sys.path:
    sys.path.insert(0, str(CV_ROOT))

import cv2
import numpy as np

from capture.frame_packet import CaptureState, FramePacket
from capture.sentinel_catalogue import Camera
from config.settings import Settings
from detection.vehicle_detector import VehicleDetector
from evidence.evidence_writer import EvidenceWriter
from integration.backend_client import BackendClient
from pipeline.camera_pipeline import CameraPipeline
from tracking.vehicle_tracker import VehicleTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("feed_demo")

# ---------------------------------------------------------------- feeds ----
# Camera IDs must exist in the backend camera registry (see scripts below);
# the stream_url in the registry points at the same file so the backend can
# serve its own MJPEG fallback view of the identical source.
FEEDS = {
    "camd01": {
        "video": CV_ROOT / "feeds" / "los_angeles.mp4",
        "name": "DEMO FEED — Highway Interchange",
        "location": "Local Demo Interchange",
        "latitude": 23.0322,
        "longitude": 72.5570,
    },
    "camd02": {
        # Plate-legible close-up footage: rear plates are readable at this
        # angle/resolution, so the ANPR stage (plate detect + OCR) can fire.
        "video": CV_ROOT / "feeds" / "city_cctv.mp4",
        "name": "DEMO FEED — City Arterial (ANPR Lane)",
        "location": "Local Demo Arterial",
        "latitude": 23.0405,
        "longitude": 72.5301,
    },
}

# ------------------------------------------------------- annotated store ----


class AnnotatedStore:
    """Latest annotated JPEG per camera + a tiny MJPEG HTTP server."""

    def __init__(self) -> None:
        self._frames: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def publish(self, camera_id: str, jpeg: bytes) -> None:
        with self._lock:
            self._frames[camera_id] = jpeg

    def get(self, camera_id: str) -> bytes | None:
        with self._lock:
            return self._frames.get(camera_id)

    def discard(self, camera_id: str) -> None:
        with self._lock:
            self._frames.pop(camera_id, None)

    def ids(self) -> list[str]:
        with self._lock:
            return sorted(self._frames)


STORE = AnnotatedStore()

_COLORS = [
    (60, 200, 90), (70, 170, 255), (90, 130, 255), (0, 220, 220),
    (200, 120, 60), (230, 90, 160), (140, 220, 60), (60, 120, 230),
]


def annotate(frame: np.ndarray, camera_id: str, tracks, pts_ms: float) -> np.ndarray:
    """Draw vehicle boxes + track IDs + an honest LOCAL DEMO FEED watermark."""
    out = frame.copy()
    live = [t for t in tracks if t.time_since_update_ms == 0]
    for t in live:
        x1, y1, x2, y2 = (int(v) for v in t.bbox)
        color = _COLORS[int(t.track_id) % len(_COLORS)]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        label = f"#{t.track_id} {t.class_name}"
        if t.confidence:
            label += f" {t.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 8, y1), color, -1)
        cv2.putText(out, label, (x1 + 4, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (15, 18, 24), 1, cv2.LINE_AA)

    h, w = out.shape[:2]
    osd = f"TRINETRA CV | {camera_id.upper()} | tracks {len(live)} | LOCAL DEMO FEED"
    cv2.rectangle(out, (0, 0), (w, 34), (15, 18, 24), -1)
    cv2.putText(out, osd, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (90, 220, 140), 1, cv2.LINE_AA)
    return out


def annotate_green(frame: np.ndarray, camera_id: str, tracks, demo: bool = True) -> np.ndarray:
    """On-demand live view: bright-green boxes + small labels (surveillance style)."""
    out = frame.copy()
    live = [t for t in tracks if t.time_since_update_ms == 0]
    for t in live:
        x1, y1, x2, y2 = (int(v) for v in t.bbox)
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{t.class_name} #{t.track_id}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 8, y1), (0, 255, 0), -1)
        cv2.putText(out, label, (x1 + 4, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (15, 18, 24), 1, cv2.LINE_AA)
    h, w = out.shape[:2]
    suffix = "LOCAL DEMO" if demo else "LIVE CAM"
    osd = f"TRINETRA LIVE AI | {camera_id.upper()} | vehicles {len(live)} | {suffix}"
    cv2.rectangle(out, (0, 0), (w, 30), (15, 18, 24), -1)
    cv2.putText(out, osd, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1, cv2.LINE_AA)
    return out


# ------------------------------------------------- on-demand annotated views ----

_ONDEMAND_DETECTOR = None
_ONDEMAND_DETECTOR_LOCK = threading.Lock()


def _ondemand_detector(settings):
    """One shared cheap-settings detector for all on-demand views."""
    global _ONDEMAND_DETECTOR
    with _ONDEMAND_DETECTOR_LOCK:
        if _ONDEMAND_DETECTOR is None:
            _ONDEMAND_DETECTOR = VehicleDetector(
                model_path=settings.model_path,
                conf_threshold=0.35,
                imgsz=416,
                device="cpu",
            )
        return _ONDEMAND_DETECTOR


class _Watch:
    def __init__(self, camera_id: str, source: str, is_file: bool):
        self.camera_id = camera_id
        self.source = source
        self.is_file = is_file
        self.refs = 0
        self.stop = threading.Event()
        self.alive = False
        self.thread = None


class OndemandWatchManager:
    """Annotates arbitrary backend-registry cameras on demand.

    While at least one HTTP client is watching a camera, a detection+tracking
    loop runs on that camera's local file and publishes green-box frames to
    the shared STORE. When the last viewer disconnects the watch stops, so
    CPU is only spent on cameras somebody is actually looking at.
    """

    def __init__(self, store, backend_base_url: str, settings, max_watches: int = 2):
        self.store = store
        self.backend_base_url = backend_base_url.rstrip("/")
        self.settings = settings
        self.max_watches = max_watches
        self._watches: dict = {}
        self._lock = threading.Lock()

    # -- registry lookup (file + real rtsp/hls cameras; never trusts paths) --
    def _resolve_source(self, camera_id: str):
        """Return (source, is_file) for a registry camera, or None."""
        try:
            import httpx

            r = httpx.get(f"{self.backend_base_url}/api/cameras/{camera_id}", timeout=3.0)
            if r.status_code != 200:
                return None
            d = r.json()
            url = (d.get("stream_url") or "").strip()
            stype = (d.get("stream_type") or "").lower()
            if not url:
                return None
            if stype == "file":
                return (url, True) if os.path.exists(url) else None
            if stype in ("rtsp", "hls"):
                return (url, False)  # real network camera
        except Exception as exc:
            logger.warning("[ondemand:%s] registry lookup failed: %s", camera_id, exc)
        return None

    def exists(self, camera_id: str) -> bool:
        with self._lock:
            return camera_id in self._watches

    def alive(self, camera_id: str) -> bool:
        with self._lock:
            w = self._watches.get(camera_id)
            return bool(w and w.alive)

    def acquire(self, camera_id: str) -> bool:
        with self._lock:
            w = self._watches.get(camera_id)
            if w is not None:
                w.refs += 1
                return True
            if len(self._watches) >= self.max_watches:
                logger.info("[ondemand:%s] capacity reached (%d) - serving without boxes",
                            camera_id, self.max_watches)
                return False
        resolved = self._resolve_source(camera_id)
        if resolved is None:
            return False
        source, is_file = resolved
        with self._lock:
            w = self._watches.get(camera_id)
            if w is not None:
                w.refs += 1
                return True
            w = _Watch(camera_id, source, is_file)
            w.refs = 1
            w.thread = threading.Thread(target=self._loop, args=(w,),
                                        name=f"ondemand-{camera_id}", daemon=True)
            self._watches[camera_id] = w
            w.thread.start()
        logger.info("[ondemand:%s] live AI view started: %s", camera_id, source)
        return True

    def release(self, camera_id: str) -> None:
        with self._lock:
            w = self._watches.get(camera_id)
            if w is None:
                return
            w.refs -= 1
            if w.refs <= 0:
                w.stop.set()
                self._watches.pop(camera_id, None)

    def _loop(self, w: _Watch) -> None:
        w.alive = True
        cap = cv2.VideoCapture(w.source)
        tracker = VehicleTracker(
            max_age_sec=self.settings.track_max_age_sec,
            min_hits=self.settings.track_min_hits,
            iou_threshold=self.settings.track_iou_threshold,
        )
        pts = 0.0
        idx = 0
        try:
            detector = _ondemand_detector(self.settings)
            while not w.stop.is_set():
                ok, frame = cap.read()
                if not (ok and frame is not None and frame.size > 0):
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = cv2.VideoCapture(w.source)  # loop the clip (reopen)
                    continue
                idx += 1
                pts += 40.0
                if idx % 3 != 0:  # light CPU budget for on-demand views
                    time.sleep(0.01)
                    continue
                detections = detector.detect(frame, camera_id=w.camera_id, pts_ms=pts)
                tracks = tracker.update(detections, pts_ms=pts)
                annotated = annotate_green(frame, w.camera_id, tracks, demo=w.is_file)
                ok2, buf = cv2.imencode(".jpg", annotated,
                                        [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok2:
                    self.store.publish(w.camera_id, buf.tobytes())
                time.sleep(0.02)
        except Exception as exc:
            logger.warning("[ondemand:%s] watch failed: %s", w.camera_id, exc)
        finally:
            try:
                cap.release()
            except Exception:
                pass
            w.alive = False
            self.store.discard(w.camera_id)
            logger.info("[ondemand:%s] live AI view stopped", w.camera_id)


ONDEMAND = None


class MjpegHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Works both directly (/camd01) and behind the dev proxy (/cvfeed/camd01).
        camera_id = self.path.strip("/").split("?")[0].split("/")[-1].lower()
        jpeg = STORE.get(camera_id)
        acquired = False
        if jpeg is None and camera_id not in FEEDS:
            # Unknown camera: start (or join) an on-demand detection watch so
            # any registry file camera gets a real annotated live view too.
            if ONDEMAND is not None:
                acquired = ONDEMAND.acquire(camera_id)
            if not acquired and STORE.get(camera_id) is None:
                self.send_response(404)
                self.end_headers()
                return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        last: bytes | None = None
        try:
            while True:
                jpeg = STORE.get(camera_id)
                if jpeg is not None and jpeg is not last:
                    try:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                        self.wfile.flush()
                        last = jpeg
                    except (BrokenPipeError, ConnectionResetError):
                        return
                elif jpeg is None and acquired and ONDEMAND is not None and not ONDEMAND.alive(camera_id):
                    return  # watch died (e.g. unreadable source)
                time.sleep(0.05)  # ~20 fps preview
        finally:
            if acquired and ONDEMAND is not None:
                ONDEMAND.release(camera_id)

    def log_message(self, *args):  # silence per-request noise
        pass


# ---------------------------------------------------------- file packets ----


def file_packets(camera_id: str, path: Path, frame_skip: int = 1):
    """Yield paced FramePackets from a video file, looping, PTS-anchored.

    Timing uses the container PTS (CAP_PROP_POS_MSEC) exactly like the RTSP
    capture layer. Each loop REOPENS the file (seeking back is unreliable on
    some containers); the PTS restart flags a hard discontinuity so the
    tracker resets — the same behaviour as a looping Sentinel feed. Broken
    container timestamps (-1 / stutters) are repaired to stay monotonic.
    """
    seq = 0
    next_at = time.monotonic()
    global_last_pts = None  # across reopens: catches the loop rewind

    while True:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise SystemExit(f"cannot open video: {path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        fps = max(min(fps, 30.0), 10.0)
        interval = 1.0 / fps

        last_pts = None
        fails = 0
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                fails += 1
                if fails >= 2:  # EOF (or decode slip) -> reopen from the start
                    cap.release()
                    break
                continue
            fails = 0
            seq += 1
            pts_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC))
            if pts_ms < 0:
                pts_ms = (last_pts if last_pts is not None else 0.0) + interval * 1000.0
            elif last_pts is not None and pts_ms <= last_pts:
                pts_ms = last_pts + interval * 1000.0  # stutter, not a rewind

            is_disc = (
                global_last_pts is not None and pts_ms < global_last_pts - 500.0
            ) or (last_pts is None and global_last_pts is not None)

            yield FramePacket(
                frame=frame,
                camera_id=camera_id,
                pts_ms=pts_ms,
                capture_state=CaptureState.ONLINE,
                sequence_number=seq,
                is_discontinuity=is_disc,
                source_type="file",
            )
            last_pts = pts_ms
            global_last_pts = pts_ms

            next_at += interval
            now = time.monotonic()
            if now < next_at:
                time.sleep(next_at - now)
            else:
                next_at = now  # inference slower than realtime: keep going, no burst-sleep


# ------------------------------------------------------------------ run ----


def run_feed(camera_id: str, cfg: dict, settings: Settings, annotate_feed: bool) -> None:
    camera = Camera(
        camera_id=camera_id,
        name=cfg["name"],
        latitude=cfg["latitude"],
        longitude=cfg["longitude"],
        location=cfg["location"],
    )
    detector = VehicleDetector(
        model_path=settings.model_path,
        conf_threshold=settings.conf_threshold,
        imgsz=settings.inference_imgsz,
        device=settings.device,
    )
    backend = BackendClient(
        base_url=settings.backend_base_url,
        timeout_sec=settings.backend_timeout_sec,
        max_retries=settings.backend_max_retries,
        queue_size=settings.backend_queue_size,
    )
    backend.start()

    def on_tracks(packet, tracks):
        if not annotate_feed:
            return
        frame = annotate(packet.frame, camera_id, tracks, packet.pts_ms)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            STORE.publish(camera_id, buf.tobytes())

    ocr_engine = None
    if settings.anpr_enabled:
        from anpr.ocr import RapidOcrEngine  # offline ONNX OCR (models in wheel)

        ocr_engine = RapidOcrEngine()

    pipeline = CameraPipeline(
        camera,
        settings,
        detector=detector,
        ocr_engine=ocr_engine,     # real detection + tracking; ANPR via RapidOCR when --anpr
        backend_client=backend,
        evidence_writer=EvidenceWriter(settings.evidence_dir, settings.evidence_jpeg_quality,
                                         max_files=settings.evidence_max_files),
        emit_plateless_sightings=True,   # genuine vehicle sightings without OCR
        on_tracks=on_tracks,
    )
    logger.info("[%s] feed runner starting: %s", camera_id, cfg["video"].name)
    try:
        pipeline.run(file_packets(camera_id, cfg["video"]))
    finally:
        backend.flush(timeout_sec=10)
        backend.close()
        logger.info("[%s] pipeline stats: %s", camera_id, pipeline.stats)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", help="camera id(s) to run, e.g. --only camd01")
    ap.add_argument("--backend", default=None, help="backend base URL override")
    ap.add_argument("--no-annotate", action="store_true", help="disable the MJPEG preview server")
    ap.add_argument("--anpr", action="store_true", help="enable ANPR stage if an OCR engine is installed")
    args = ap.parse_args()

    settings = Settings.from_env()
    if args.backend:
        settings.backend_base_url = args.backend
    settings.model_path = str(CV_ROOT / "models" / "yolo11n.pt")
    settings.anpr_enabled = bool(args.anpr)
    # Demo-feed tuning: local clips loop every ~14s, shorter than the default
    # 20s hold-emit, so long-lived tracks would never produce sightings.
    settings.event_max_track_hold_sec = 8.0
    settings.event_on_track_loss_sec = 2.0
    settings.frame_skip = 2  # CPU budget for two concurrent 1080p feeds
    settings.evidence_dir = str(CV_ROOT / "evidence")

    feeds = {k: v for k, v in FEEDS.items() if not args.only or k in args.only}
    for cid, cfg in feeds.items():
        if not Path(cfg["video"]).exists():
            raise SystemExit(f"missing video for {cid}: {cfg['video']}")

    if not args.no_annotate:
        global ONDEMAND
        ONDEMAND = OndemandWatchManager(
            STORE, settings.backend_base_url, settings,
            max_watches=int(os.environ.get("ONDEMAND_MAX_WATCHES", "2")),
        )
        server = ThreadingHTTPServer(("0.0.0.0", 8555), MjpegHandler)
        threading.Thread(target=server.serve_forever, daemon=True, name="mjpeg").start()
        logger.info("annotated MJPEG preview on http://0.0.0.0:8555/<camera_id>")

    threads = []
    for cid, cfg in feeds.items():
        t = threading.Thread(target=run_feed, args=(cid, cfg, settings, not args.no_annotate),
                             name=f"feed-{cid}", daemon=True)
        t.start()
        threads.append(t)
        time.sleep(1.0)  # stagger model warmup
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
