"""
Analyse one video and print every number plate with how long it was in shot.

This is the offline / batch entry point to the same pipeline the web UI runs —
no server, no browser, no database rows left behind unless you ask for a
report file.

    cd TRINETRAAI/backend
    python -m scripts.analyze_video_plates ../ footage.mp4

    # keep the artefacts
    python -m scripts.analyze_video_plates footage.mp4 \
        --csv plates.csv --json plates.json

    # analyse every Nth frame instead of the default (5) — smaller = slower but
    # finer-grained time measurement
    python -m scripts.analyze_video_plates footage.mp4 --every-n 2

What it prints: one row per number plate, each with

    in shot     span from first sighting to last (how long it was in the area)
    on screen   time it was actually tracked on camera
    entries     how many separate times it entered the shot
    entry/exit  timestamps into the video

Plus a section for vehicles whose plate could not be read — they are listed,
never guessed.

Requires the same optional packages as the server (``rfdetr`` for RF-DETR
detection, ``ultralytics`` for YOLO11, ``rapidocr-onnxruntime`` for OCR). The
script tells you plainly which stages are unavailable rather than inventing
results.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.logging_config import logger  # noqa: E402
from app.database.database import SessionLocal, init_db  # noqa: E402
from app.database.models import VideoSource  # noqa: E402
from app.services import plate_usage_service as pus  # noqa: E402
from app.services import video_analysis_service as vas  # noqa: E402
from app.services import rfdetr_detector  # noqa: E402
from app.services.ocr_service import ocr_service  # noqa: E402
from app.services.vehicle_detection_service import VehicleDetectionService  # noqa: E402

ALLOWED = vas.ALLOWED_VIDEO_SUFFIXES


def _print_table(title: str, rows: list) -> None:
    if not rows:
        return
    print(f"\n{title}")
    header = f"{'PLATE':<14} {'CLASS':<11} {'IN SHOT':>10} {'ON SCREEN':>10} {'ENTRY':>9} {'EXIT':>9} {'ENTRIES':>8}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['plate_label']:<14} "
            f"{(r['vehicle_class'] or '-'):<11} "
            f"{r['dwell_label']:>10} "
            f"{r['visible_label']:>10} "
            f"{r['first_seen']:>9} "
            f"{r['last_seen']:>9} "
            f"{r['appearances']:>8}"
        )


def _stage_status() -> list:
    """Tell the user exactly which stages are live, before doing the work."""
    lines = []
    detector = VehicleDetectionService()
    backend = str(getattr(settings, "DETECTOR_BACKEND", "auto"))
    rf = "installed" if rfdetr_detector.available else "NOT installed"
    lines.append(f"  Vehicle detection : backend={backend} (rfdetr {rf})")
    lines.append(f"  OCR (plate read)  : {'ready' if ocr_service.available else 'NOT installed'}")
    lines.append(
        "  Plate localiser   : "
        + (
            "RF-DETR (fine-tuned)"
            if getattr(settings, "PLATE_RFDETR_MODEL_PATH", "")
            else "classical OpenCV proposer"
        )
    )
    return lines


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="analyze_video_plates",
        description="Detect every number plate in a video and report how long each was in shot.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", type=Path, help="path to the video file")
    parser.add_argument("--csv", type=Path, help="write the report to this CSV file")
    parser.add_argument("--json", type=Path, help="write the report to this JSON file")
    parser.add_argument(
        "--every-n",
        type=int,
        default=None,
        help="analyse every Nth frame (default: ANALYSIS_EVERY_N_FRAMES, "
             "currently %(default)s). Smaller = more accurate times, slower.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the video and its detections in the TRINETRA database "
             "(so the web UI can show it). Off by default.",
    )
    parser.add_argument("--quiet", action="store_true", help="only print the tables")
    args = parser.parse_args(argv)

    video_path: Path = args.video
    if not video_path.is_file():
        print(f"error: no such file: {video_path}", file=sys.stderr)
        return 2
    if video_path.suffix.lower() not in ALLOWED:
        print(
            f"error: unsupported video type '{video_path.suffix}'. "
            f"Use one of {', '.join(sorted(ALLOWED))}.",
            file=sys.stderr,
        )
        return 2

    if args.every_n is not None:
        if args.every_n < 1:
            print("error: --every-n must be >= 1", file=sys.stderr)
            return 2
        settings.ANALYSIS_EVERY_N_FRAMES = args.every_n

    if not args.quiet:
        print(f"Analysing {video_path.name}")
        print("\n".join(_stage_status()))
        print(f"  Frame sampling     : every {settings.ANALYSIS_EVERY_N_FRAMES} frame(s)\n")

    init_db()
    db = SessionLocal()

    # Copy into the analysis dir only when the result is being kept; otherwise
    # register in place and clean the video row up at the end.
    register_path = video_path
    tmp_dir = None
    if not args.keep:
        tmp_dir = Path(tempfile.mkdtemp(prefix="plate-usage-"))
        register_path = tmp_dir / video_path.name
        shutil.copy2(video_path, register_path)

    video_id = None
    try:
        video = vas.register_upload(db, video_path.name, register_path.read_bytes(), "cli")
        video_id = video.video_id
        db.close()

        vas._run_video(video_id)          # synchronous: blocks until finished

        db = SessionLocal()
        stored = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
        if stored and stored.status == "FAILED":
            print(f"\nAnalysis failed: {stored.error}", file=sys.stderr)
            return 1

        report = pus.build_report(db, video_id)

        v = report["video"]
        s = report["summary"]
        print(
            f"\n{v['source_name']} — {v['width']}x{v['height']} @ {v['fps']} fps, "
            f"{v['duration_label'] or '?'} long"
        )
        print(
            f"{s['appearances']} appearance(s), {s['unique_plates']} plate(s) read, "
            f"{s['unreadable_vehicles']} vehicle(s) with no readable plate"
        )
        if s["watchlist_hits"]:
            print(f"!! {s['watchlist_hits']} plate(s) matched the watchlist")

        _print_table("NUMBER PLATES (longest in shot first)", report["plates"])
        _print_table("VEHICLES WITH NO READABLE PLATE", report["unreadable"])

        if not report["plates"] and not report["unreadable"]:
            print("\nNo vehicles were detected in this video.")

        for note in report["notes"]:
            print(f"\nnote: {note}")

        if args.csv:
            args.csv.write_text(pus.report_to_csv(report), encoding="utf-8")
            print(f"\nCSV written to  {args.csv}")
        if args.json:
            args.json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            print(f"JSON written to {args.json}")

        return 0
    except vas.AnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            db.close()
        except Exception:
            pass
        if video_id and not args.keep:
            cleanup = SessionLocal()
            try:
                vas.delete_video(cleanup, video_id)
            except Exception as exc:
                logger.debug(f"cleanup skipped: {exc}")
            finally:
                cleanup.close()
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
