"""
Register the two DEMO FEED cameras (CAMD01, CAMD02) in the backend registry.

``cv-engine/scripts/run_feed_demo.py`` runs the real pipeline on two local
clips and serves annotated MJPEG previews for camd01/camd02, but the Cameras
page can only list them once they exist in the registry. This script creates
(or refreshes) both rows with ``stream_type='file'`` pointing at the clips
produced by ``cv-engine/scripts/make_local_feeds.py``.

Idempotent: safe to re-run any time (it refreshes names, coordinates and feed
paths, so the registry always matches the current demo clips). It replaces
the old bash-heredoc README snippet so the same flow also works on Windows
PowerShell.

Usage (from TRINETRAAI/backend, with the backend environment active):
    python -m scripts.register_demo_cameras
"""
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.database.database import SessionLocal  # noqa: E402
from app.database.models import Camera  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
FEEDS_DIR = REPO_ROOT / "cv-engine" / "feeds"

# Mirrors cv-engine/scripts/run_feed_demo.py::FEEDS (if the demo runner's
# clips or metadata change, update both together so the registry, the live
# views and the map pins stay consistent).
DEMO_CAMERAS = [
    {
        "camera_id": "CAMD01",
        "name": "DEMO FEED — Highway Interchange",
        "location": "Local Demo Interchange",
        "latitude": 23.0322,
        "longitude": 72.5570,
        "video": "highway2.mp4",
    },
    {
        "camera_id": "CAMD02",
        "name": "DEMO FEED — City Arterial (ANPR Lane)",
        "location": "Local Demo Arterial",
        "latitude": 23.0405,
        "longitude": 72.5301,
        "video": "city_cctv.mp4",
    },
]


# Recordings used as local camera sources (built by
# TRINETRAAI/backend/scripts/build_synthetic_test_clips.py). Their ids are the
# ones the UI routes and tests address. Every one of them is a FILE source, so
# the registry reports them as RECORDED - a looping clip is never presented as
# a live camera, and the OSD on their frames says the same.
ANALYSIS_DIR = backend_root / "uploads" / "analysis"
LOCAL_TEST_CLIPS = [
    {"camera_id": "JUNCTION_DAY", "name": "RECORDED - Junction, daytime",
     "location": "Local test recording", "latitude": 23.0225, "longitude": 72.5714,
     "video": "junction_day.mp4"},
    {"camera_id": "NIGHT_BRIDGE", "name": "RECORDED - Bridge, night grade",
     "location": "Local test recording", "latitude": 23.0156, "longitude": 72.5610,
     "video": "night_bridge.mp4"},
    {"camera_id": "DENSE_PARKED_BIKES", "name": "RECORDED - Parked two-wheeler rows",
     "location": "Local test recording", "latitude": 23.0288, "longitude": 72.5800,
     "video": "dense_parked_bikes.mp4"},
    {"camera_id": "AVENUE_1080P", "name": "RECORDED - Avenue, 1080p",
     "location": "Local test recording", "latitude": 23.0195, "longitude": 72.5672,
     "video": "avenue_1080p.mp4"},
]


def register_local_test_cameras(db, clips_dir: Path = ANALYSIS_DIR) -> list[dict]:
    """Create/refresh the RECORDED test-camera rows; returns those registered.

    Skips (rather than fails on) a clip that has not been built: a fresh clone
    has no recordings, and the app must still start with only real cameras. The
    caller prints what was skipped so an operator knows what to generate.
    """
    present = []
    for cam in LOCAL_TEST_CLIPS:
        path = Path(clips_dir) / cam["video"]
        if not path.is_file():
            continue
        row = db.query(Camera).filter(Camera.camera_id == cam["camera_id"]).first()
        if row is None:
            row = Camera(camera_id=cam["camera_id"])
            db.add(row)
        row.name = cam["name"]
        row.location = cam["location"]
        row.latitude = cam["latitude"]
        row.longitude = cam["longitude"]
        row.stream_type = "file"
        row.stream_url = str(path.resolve())
        # ONLINE because the media exists and is decoded on demand; a deleted
        # clip drops back to NOT_CONFIGURED through the API's own resolution.
        row.status = "ONLINE"
        present.append(cam)
    db.commit()
    return present


def register_demo_cameras(db, feeds_dir: Path = FEEDS_DIR) -> list[dict]:
    """Create/refresh the CAMD rows in ``db``; returns the camera dicts.

    Raises FileNotFoundError when the demo feed clips are missing so callers
    can point the operator at ``make_local_feeds.py`` instead of guessing.
    """
    missing = [c["video"] for c in DEMO_CAMERAS if not (feeds_dir / c["video"]).is_file()]
    if missing:
        raise FileNotFoundError(
            "missing feed clip(s) in %s: %s - run "
            "cv-engine/scripts/make_local_feeds.py first" % (feeds_dir, ", ".join(missing))
        )

    for cam in DEMO_CAMERAS:
        row = db.query(Camera).filter(Camera.camera_id == cam["camera_id"]).first()
        if row is None:
            row = Camera(camera_id=cam["camera_id"])
            db.add(row)
        row.name = cam["name"]
        row.location = cam["location"]
        row.latitude = cam["latitude"]
        row.longitude = cam["longitude"]
        row.stream_type = "file"
        row.stream_url = str((feeds_dir / cam["video"]).resolve())
        row.status = "ONLINE"
    db.commit()
    return DEMO_CAMERAS


def main() -> int:
    db = SessionLocal()
    rc = 0
    try:
        try:
            cams = register_demo_cameras(db)
        except FileNotFoundError as exc:
            cams, rc = [], 0   # no cv-engine feeds here: report, do not fail
            print("[SKIP] %s" % exc)
        for cam in cams:
            print("[OK] %s -> %s" % (cam["camera_id"], FEEDS_DIR / cam["video"]))
        print("registered %d DEMO FEED cameras (%s)" % (
            len(cams), ", ".join(c["camera_id"] for c in cams)))

        recorded = register_local_test_cameras(db)
        for cam in recorded:
            print("[OK] %s -> %s" % (cam["camera_id"], ANALYSIS_DIR / cam["video"]))
        absent = [c["camera_id"] for c in LOCAL_TEST_CLIPS
                  if not (ANALYSIS_DIR / c["video"]).is_file()]
        print("registered %d RECORDED test cameras%s" % (
            len(recorded),
            " (no clip for: %s - build them with scripts/"
            "build_synthetic_test_clips.py)" % ", ".join(absent) if absent else ""))
    finally:
        db.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
