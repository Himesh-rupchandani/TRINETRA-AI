#!/usr/bin/env python3
"""
TRINETRA cv-engine runner (spec §24, §36).

LIVE SENTINEL MODE (Government-feed demo):
    python scripts/run_pipeline.py --mode live --camera cam04
    python scripts/run_pipeline.py --mode live --subset 3 --duration 300

DEMO MODE (scripted fixtures — NOT live Sentinel):
    python scripts/run_pipeline.py --mode demo

The demo mode exercises the full pipeline plumbing (tracking, ANPR
aggregation, dedup, evidence, backend POST) with scripted detections and is
clearly labelled. It must never be presented as live-feed performance.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from integration.backend_client import BackendClient


def build_arg_parser():
    p = argparse.ArgumentParser(description="TRINETRA cv-engine pipeline runner")
    p.add_argument("--mode", choices=["live", "demo"], default="live")
    p.add_argument("--camera", default=None, help="camera id from Sentinel catalogue (e.g. cam04)")
    p.add_argument("--subset", type=int, default=0, help="run N catalogue-diverse cameras (multi-cam)")
    p.add_argument("--catalogue-url", default=None)
    p.add_argument("--backend-url", default=None)
    p.add_argument("--duration", type=float, default=0.0, help="seconds to run (0 = forever)")
    p.add_argument("--frame-skip", type=int, default=None)
    p.add_argument("--demo-frames", type=int, default=90)
    p.add_argument("--no-backend", action="store_true", help="demo: skip backend POST")
    return p


def configure_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        datefmt="%H:%M:%S",
    )


def run_live(args, settings: Settings):
    from capture.reconnect import ManagedCapture
    from capture.sentinel_catalogue import SentinelCatalogue, select_test_subset
    from detection.vehicle_detector import VehicleDetector
    from anpr.ocr import OcrEngine
    from evidence.evidence_writer import EvidenceWriter
    from pipeline.camera_pipeline import CameraPipeline

    cat = SentinelCatalogue(
        url=args.catalogue_url or settings.sentinel_catalogue_url,
        timeout_sec=settings.catalogue_timeout_sec,
        email=settings.sentinel_email,
        password=settings.sentinel_password,
    )
    cat.fetch()  # raises CatalogueError -> hard stop; live mode needs the catalogue

    if args.camera:
        camera = cat.get_camera(args.camera)
        if camera is None:
            raise SystemExit(f"camera '{args.camera}' not in catalogue. Known: "
                             f"{[c.camera_id for c in cat.get_cameras()]}")
        cameras = [camera]
    elif args.subset > 0:
        cameras = select_test_subset(cat.get_cameras(), args.subset)
    else:
        raise SystemExit("live mode needs --camera <id> or --subset N")

    if args.frame_skip:
        settings.frame_skip = args.frame_skip

    detector = VehicleDetector(
        model_path=settings.model_path,
        conf_threshold=settings.conf_threshold,
        imgsz=settings.inference_imgsz,
        device=settings.device,
    )
    detector.warmup()
    ocr = OcrEngine(gpu=settings.device != "cpu") if settings.anpr_enabled else None
    evidence = EvidenceWriter(settings.evidence_dir, settings.evidence_jpeg_quality)
    backend = BackendClient(
        base_url=settings.backend_base_url,
        timeout_sec=settings.backend_timeout_sec,
        max_retries=settings.backend_max_retries,
        queue_size=settings.backend_queue_size,
    )
    backend.start()

    stop = {"flag": False}

    def _sig(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    t_end = time.monotonic() + args.duration if args.duration > 0 else None

    def stop_check():
        return stop["flag"] or (t_end is not None and time.monotonic() >= t_end)

    if len(cameras) == 1:
        cam = cameras[0]
        logging.getLogger("cv_engine").info("LIVE mode: single camera %s", cam.camera_id)
        managed = ManagedCapture(cam, settings)
        pipeline = CameraPipeline(cam, settings, detector, ocr, backend, evidence)
        pipeline.run(managed.packets(stop_check), stop_check)
        managed.stop()
    else:
        import threading

        logging.getLogger("cv_engine").info("LIVE mode: %d cameras (1 thread each)", len(cameras))
        threads = []
        for cam in cameras:
            def worker(cam=cam):
                managed = ManagedCapture(cam, settings)
                pipeline = CameraPipeline(cam, settings, detector, ocr, backend, evidence)
                pipeline.run(managed.packets(stop_check), stop_check)
                managed.stop()
            th = threading.Thread(target=worker, name=f"cam-{cam.camera_id}", daemon=True)
            th.start()
            threads.append(th)
        while not stop_check():
            time.sleep(0.5)
        stop["flag"] = True
        for th in threads:
            th.join(timeout=5)

    backend.flush(timeout_sec=15)
    backend.close()
    logging.getLogger("cv_engine").info("backend stats: %s", backend.stats)


def run_demo(args, settings: Settings):
    """⚠ DEMO MODE — scripted fixtures, NOT live Sentinel."""
    from capture.sentinel_catalogue import Camera
    from evidence.evidence_writer import EvidenceWriter
    from pipeline.camera_pipeline import CameraPipeline
    from pipeline.demo_source import DemoDetector, DemoOcr, DemoScenario, demo_packets

    print("=" * 64)
    print("⚠ DEMO MODE — scripted detections. NOT a live Sentinel feed.")
    print("=" * 64)

    scenario = DemoScenario.default()
    scenario.n_frames = args.demo_frames
    # No coordinates are invented here. The backend resolves the sighting's
    # position from the camera registry, so a demo event lands on the same map
    # point as a live one from the same camera.
    camera = Camera(
        camera_id=scenario.camera_id,
        name="Demo Camera (scripted)",
        location=None,
    )

    demo_ocr = DemoOcr()

    def _hook(packet):
        demo_ocr.ctx = (scenario, getattr(packet.frame, "demo_index", -1))

    backend = None
    if not args.no_backend:
        backend = BackendClient(base_url=settings.backend_base_url)
        backend.start()

    class _NullBackend:  # records locally when backend disabled
        def __init__(self):
            self.events = []

        def submit(self, event):
            self.events.append(event)
            print(f"  [no-backend] would POST: {event.get('plate')} conf={event.get('plate_confidence')}")
            return True

    pipeline = CameraPipeline(
        camera,
        settings,
        detector=DemoDetector(),
        ocr_engine=demo_ocr,
        backend_client=backend or _NullBackend(),
        evidence_writer=EvidenceWriter(settings.evidence_dir),
        on_packet=_hook,
    )
    pipeline.run(demo_packets(scenario))

    if backend is not None:
        backend.flush(timeout_sec=15)
        backend.close()
        print(f"backend stats: {backend.stats}")
    print(f"pipeline stats: {pipeline.stats}")


def main():
    args = build_arg_parser().parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    if args.backend_url:
        settings.backend_base_url = args.backend_url
    if args.mode == "demo":
        run_demo(args, settings)
    else:
        run_live(args, settings)


if __name__ == "__main__":
    main()
