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
        "video": CV_ROOT / "feeds" / "cctv.avi",
        "name": "DEMO FEED — City Arterial",
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


class MjpegHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Works both directly (/camd01) and behind the dev proxy (/cvfeed/camd01).
        camera_id = self.path.strip("/").split("?")[0].split("/")[-1].lower()
        jpeg = STORE.get(camera_id)
        if jpeg is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        last: bytes | None = None
        while True:
            jpeg = STORE.get(camera_id)
            if jpeg is not None and jpeg is not last:
                try:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                    self.wfile.flush()
                    last = jpeg
                except (BrokenPipeError, ConnectionResetError):
                    return
            time.sleep(0.05)  # ~20 fps preview

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

    pipeline = CameraPipeline(
        camera,
        settings,
        detector=detector,
        ocr_engine=None,           # real detection + tracking; ANPR stays off (no plate reader in this env)
        backend_client=backend,
        evidence_writer=EvidenceWriter(settings.evidence_dir, settings.evidence_jpeg_quality),
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
