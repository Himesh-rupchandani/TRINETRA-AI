"""
Point registry cameras at local demo feed files.

For the offline hackathon demo every fictional cloud camera
(``https://cctv.corp8.cloud/...``) is repointed at a real local traffic
clip under ``cv-engine/feeds/`` so the whole grid is playable. The live
view for these cameras is decoded ON DEMAND by the backend when an
operator opens one (no permanent worker per camera), so this is safe on
small machines.

Usage (from TRINETRAAI/backend):
    python -m scripts.point_cameras_at_local_feeds [--feeds-dir ../../cv-engine/feeds]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

FEEDS_DIR = Path(__file__).resolve().parents[3] / "cv-engine" / "feeds"
CANDIDATE_FEEDS = [
    "highway2.mp4",  # real highway CCTV, dense traffic
    "city_cctv.mp4",  # real city CCTV footage
    "city_traffic.mp4",  # dense urban arterial
    "intersection_a.mp4",  # fixed intersection cam (multi-cam set)
    "intersection_b.mp4",  # second angle of the intersection set
    "crosswalk.avi",  # pedestrians + cars (OpenCV classic vtest)
    "night_traffic.mp4",  # night-time traffic
    "los_angeles.mp4",  # 1080p highway aerial
    "cctv.avi",  # small CCTV clip
]
# Cameras with dedicated detection feeds (managed by run_feed_demo.py).
KEEP_AS_IS = {"CAMD01", "CAMD02"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feeds-dir", type=Path, default=FEEDS_DIR)
    parser.add_argument("--db", type=Path, default=Path("trinetra.db"))
    args = parser.parse_args()

    feeds = [args.feeds_dir / name for name in CANDIDATE_FEEDS if (args.feeds_dir / name).exists()]
    if not feeds:
        print(f"no local feeds found in {args.feeds_dir}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    # Idempotent: re-map every non-demo camera so the registry always tracks
    # the current CANDIDATE_FEEDS list (handles removed/renamed clips too).
    rows = conn.execute(
        "SELECT camera_id FROM cameras WHERE camera_id NOT IN (%s)"
        % ",".join("?" * len(KEEP_AS_IS)),
        sorted(KEEP_AS_IS),
    ).fetchall()

    updated = 0
    for i, (camera_id,) in enumerate(rows):
        feed = feeds[i % len(feeds)]
        conn.execute(
            "UPDATE cameras SET stream_type='file', stream_url=?, status='ONLINE' WHERE camera_id=?",
            (str(feed), camera_id),
        )
        updated += 1
    conn.commit()
    conn.close()
    print(f"repointed {updated} cameras to {len(feeds)} local feeds: {[f.name for f in feeds]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
