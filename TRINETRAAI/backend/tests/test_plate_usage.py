"""
Number-plate usage report — time-in-shot accounting.

The detector and OCR stages are stubbed (so the suite is deterministic and
needs no model weights), but everything that actually produces the numbers is
exercised for real: video decoding, frame sampling, tracking, presence-window
recording, aggregation across multiple appearances, the REST endpoint and the
CSV export.

The stub detector is driven by a *script*: each frame number maps to the set of
`synthetic vehicles` present in it. That lets us state the expected dwell times
up front and then assert the pipeline measures exactly those.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

for _p in [str(Path(__file__).resolve().parents[1])]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.database.database import SessionLocal, init_db
from app.database.models import Camera, VehicleEvent, VehiclePresence, VideoSource
from app.services import plate_usage_service as pus
from app.services import video_analysis_service as vas
from app.services.anpr_pipeline import PlateRead
from app.services.ocr_service import ocr_service
from app.services.vehicle_detection_service import VehicleDetection, vehicle_detection_service

TEST_PREFIX = "PUCAM"
SIZE = (320, 240)

# Timing constants chosen to make the expected numbers exact.
FPS = 10
EVERY_N = 5          # ANALYSIS_EVERY_N_FRAMES
PERIOD = EVERY_N / FPS   # 0.5 s of video per analysed frame
FRAMES = 60          # 6.0 s of video  -> analysed frames 0,5,...,55


# --------------------------------------------------------------------------- #
# A controllable "video": frame number -> vehicles present in that frame
# --------------------------------------------------------------------------- #
class ScriptedDetector:
    """
    Stands in for RF-DETR/YOLO. ``script`` maps an analysed frame index to a
    list of ``(vehicle_key, x1)``; each key gets its own plate.

    Different x positions keep the IoU tracker's identities stable and separate.
    """

    def __init__(self, script, plates):
        self.script = script
        self.plates = plates
        self.frame = -1

    def detect(self, frame):
        self.frame += 1
        h, w = frame.shape[:2]
        out = []
        for key, x1 in self.script.get(self.frame, []):
            out.append(
                VehicleDetection(
                    x1=x1, y1=60,
                    x2=min(w - 1, x1 + 120), y2=min(h - 1, 180),
                    class_name="car", confidence=0.9,
                )
            )
        return out


def _write_clip(path: Path, frames: int = FRAMES) -> None:
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, SIZE)
    for i in range(frames):
        frame = np.full((SIZE[1], SIZE[0], 3), 40, dtype=np.uint8)
        cv2.rectangle(frame, (40 + (i % 7), 60), (200, 180), (170, 170, 170), -1)
        w.write(frame)
    w.release()


def _make_read(plates, detector):
    """OCR stub: reads the plate of whichever synthetic vehicle is in the box."""
    def _read(frame, bbox, vehicle_class="car"):
        x1 = int(bbox[0])
        for key, px in detector.script.get(detector.frame, []):
            if abs(px - x1) <= 2:
                plate = plates.get(key)
                if not plate:
                    return None
                return PlateRead(raw=plate, normalized=plate, confidence=0.95,
                                 ocr_confidence=0.95, indian_format=True, plate_box=None)
        return None
    return _read


# --------------------------------------------------------------------------- #
# Fixture: real app + stubbed model stages
# --------------------------------------------------------------------------- #
@pytest.fixture()
def harness(tmp_path, monkeypatch):
    init_db()
    from app.main import app

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    monkeypatch.setattr(vas.settings, "ANALYSIS_EVERY_N_FRAMES", EVERY_N)
    monkeypatch.setattr(vas.settings, "ANALYSIS_MIN_TRACK_HITS", 1)
    monkeypatch.setattr(vas.settings, "ANALYSIS_MIN_VEHICLE_AREA", 0)
    monkeypatch.setattr(vas.settings, "ANALYSIS_OCR_COOLDOWN_STEPS", 1)

    vehicle_detection_service._model = object()
    vehicle_detection_service._backend = "stub"
    vehicle_detection_service._disabled_reason = None
    ocr_service._engine, ocr_service._attempted = object(), True

    client = TestClient(app, raise_server_exceptions=True)

    created = []
    last: dict = {}

    def arm(script, plates):
        """Point the stubbed model stages at one script."""
        detector = ScriptedDetector(script, plates)
        vehicle_detection_service.detect = detector.detect
        vas.read_plate_for_vehicle = _make_read(plates, detector)
        return detector

    def run(script, plates, name="PUCAM1", frames=FRAMES):
        """Analyse one synthetic video and return (video_id, report)."""
        last.update(script=script, plates=plates)
        arm(script, plates)

        path = tmp_path / f"{name}.mp4"
        _write_clip(path, frames)

        db = SessionLocal()
        try:
            video = vas.register_upload(db, f"{name}.mp4", path.read_bytes(), "pubatch")
            video_id = video.video_id
            created.append(video_id)
        finally:
            db.close()

        vas._run_video(video_id)   # synchronous: no worker thread in tests

        db = SessionLocal()
        try:
            return video_id, pus.build_report(db, video_id)
        finally:
            db.close()

    def rerun(video_id, script=None, plates=None):
        """Re-run through the public entry point (queues a worker thread)."""
        arm(script if script is not None else last["script"],
            plates if plates is not None else last["plates"])
        db = SessionLocal()
        try:
            vas.start_analysis(db, [video_id])
        finally:
            db.close()

    def wait(video_id, timeout=20.0):
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            db = SessionLocal()
            try:
                v = db.query(VideoSource).filter(
                    VideoSource.video_id == video_id
                ).first()
                if v and v.status in ("DONE", "FAILED"):
                    return v.status
            finally:
                db.close()
            time.sleep(0.05)
        raise AssertionError(f"analysis of {video_id} did not finish in time")

    run.rerun = rerun
    run.wait = wait
    yield run

    db = SessionLocal()
    try:
        vids = db.query(VideoSource).filter(
            VideoSource.camera_id.like(f"{TEST_PREFIX}%")
        ).all()
        for v in vids:
            db.query(VehiclePresence).filter(
                VehiclePresence.video_id == v.video_id
            ).delete(synchronize_session=False)
            db.query(VehicleEvent).filter(
                VehicleEvent.video_id == v.video_id
            ).delete(synchronize_session=False)
            if v.file_path:
                Path(v.file_path).unlink(missing_ok=True)
            db.delete(v)
        db.query(Camera).filter(Camera.camera_id.like(f"{TEST_PREFIX}%")).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Pure interval maths
# --------------------------------------------------------------------------- #
def test_merge_intervals_basic():
    assert pus.merge_intervals([(0, 10), (5, 12), (30, 40)]) == [(0, 12), (30, 40)]


def test_merge_intervals_touching_and_empty():
    assert pus.merge_intervals([(0, 10), (10, 20)]) == [(0, 20)]
    assert pus.merge_intervals([]) == []


def test_merge_intervals_unsorted():
    assert pus.merge_intervals([(30, 40), (0, 10)]) == [(0, 10), (30, 40)]


# --------------------------------------------------------------------------- #
# Measured time in shot
# --------------------------------------------------------------------------- #
def test_single_vehicle_present_whole_video(harness):
    """Present in every analysed frame (0..55) → dwell == visible == 6.0 s."""
    script = {i: [("a", 40)] for i in range(12)}   # 12 analysed samples
    _, report = harness(script, {"a": "GJ01AB1234"})

    assert report["summary"]["unique_plates"] == 1
    row = report["plates"][0]
    assert row["plate"] == "GJ01AB1234"
    assert row["appearances"] == 1
    assert row["first_seen_sec"] == 0.0
    assert row["last_seen_sec"] == pytest.approx(5.5)     # frame 55 / 10 fps
    # (5.5 - 0.0) + one 0.5 s sampling window
    assert row["dwell_sec"] == pytest.approx(6.0)
    assert row["visible_sec"] == pytest.approx(6.0)       # 12 samples x 0.5 s
    assert row["presence_pct"] == pytest.approx(100.0)
    assert row["frames_present"] == 12


def test_partial_presence_is_not_extrapolated(harness):
    """Present only in samples 4..7 (frames 20..35) → 2.0 s, not the whole clip."""
    script = {i: [("a", 40)] for i in range(4, 8)}
    _, report = harness(script, {"a": "MH12XY4567"})

    row = report["plates"][0]
    assert row["first_seen_sec"] == pytest.approx(2.0)    # frame 20 / 10
    assert row["last_seen_sec"] == pytest.approx(3.5)     # frame 35 / 10
    assert row["dwell_sec"] == pytest.approx(2.0)         # (3.5-2.0)+0.5
    assert row["visible_sec"] == pytest.approx(2.0)       # 4 samples x 0.5
    assert row["presence_pct"] == pytest.approx(33.3, abs=0.1)


def test_short_occlusion_dwell_exceeds_on_screen(harness):
    """
    Seen, briefly hidden, seen again. The tracker bridges the gap, so it stays
    ONE appearance: dwell spans the whole window including the hidden part,
    while on-screen counts only the frames it was actually detected in.
    """
    script = {}
    for i in range(0, 3):                 # samples 0-2  (0.0 - 1.0 s)
        script[i] = [("a", 40)]
    for i in range(9, 12):                # samples 9-11 (4.5 - 5.5 s)
        script[i] = [("a", 40)]

    _, report = harness(script, {"a": "GJ01AB1234"})

    row = report["plates"][0]
    assert row["appearances"] == 1        # tracker bridged the occlusion
    assert row["dwell_sec"] == pytest.approx(6.0)      # 5.5 - 0.0 + 0.5
    assert row["visible_sec"] == pytest.approx(3.0)    # 6 detected samples x 0.5
    assert row["dwell_sec"] > row["visible_sec"]


def test_leaves_and_returns_counts_two_appearances(harness):
    """
    Gone for longer than the tracker's miss budget: two separate appearances,
    recorded separately and then summed into one plate line.
    """
    script = {}
    for i in range(0, 3):                 # samples 0-2   (0.0 - 1.0 s)
        script[i] = [("a", 40)]
    for i in range(17, 20):               # samples 17-19 (8.5 - 9.5 s)
        script[i] = [("a", 40)]

    # 100 frames = 20 analysed samples.
    _, report = harness(script, {"a": "GJ01AB1234"}, name="PUCAM2", frames=100)

    row = report["plates"][0]
    assert row["appearances"] == 2
    assert len(row["segments"]) == 2
    assert row["first_seen_sec"] == pytest.approx(0.0)
    assert row["last_seen_sec"] == pytest.approx(9.5)
    assert row["dwell_sec"] == pytest.approx(10.0)     # 9.5 - 0.0 + 0.5
    assert row["visible_sec"] == pytest.approx(3.0)    # 6 detected samples x 0.5
    # Each individual appearance covers 1.5 s on its own.
    assert [s["duration_sec"] for s in row["segments"]] == [pytest.approx(1.5)] * 2


def test_two_plates_sorted_by_time_in_shot(harness):
    """The report is ordered longest-dwell first — the question it answers."""
    script = {}
    for i in range(12):                   # A is there the whole time
        script.setdefault(i, []).append(("a", 40))
    for i in range(0, 2):                 # B only briefly
        script.setdefault(i, []).append(("b", 200))

    _, report = harness(script, {"a": "GJ01AB1234", "b": "GJ05CD6789"})

    assert [r["plate"] for r in report["plates"]] == ["GJ01AB1234", "GJ05CD6789"]
    assert report["summary"]["unique_plates"] == 2
    assert report["summary"]["longest_plate"] == "GJ01AB1234"
    assert report["plates"][0]["dwell_sec"] > report["plates"][1]["dwell_sec"]


def test_unreadable_vehicle_is_listed_not_dropped(harness):
    """A vehicle whose plate cannot be read still has its time recorded."""
    script = {i: [("a", 40)] for i in range(6)}
    _, report = harness(script, {"a": None})   # no plate readable

    assert report["summary"]["unique_plates"] == 0
    assert report["summary"]["unreadable_vehicles"] == 1
    row = report["unreadable"][0]
    assert row["plate_label"] == "UNREADABLE"
    assert row["plate_status"] == "UNKNOWN"
    assert row["dwell_sec"] == pytest.approx(3.0)


def test_plates_are_never_fabricated(harness):
    script = {i: [("a", 40)] for i in range(12)}
    _, report = harness(script, {"a": None})
    assert report["plates"] == []


# --------------------------------------------------------------------------- #
# API + export
# --------------------------------------------------------------------------- #
def test_endpoint_and_csv(harness):
    from app.main import app

    script = {}
    for i in range(12):
        script.setdefault(i, []).append(("a", 40))
    for i in range(0, 4):
        script.setdefault(i, []).append(("b", 200))
    video_id, _ = harness(script, {"a": "GJ01AB1234", "b": "GJ05CD6789"})

    with TestClient(app, raise_server_exceptions=True) as client:
        res = client.get("/api/analysis/plate-usage", params={"video_id": video_id})
        assert res.status_code == 200
        body = res.json()
        assert body["video"]["video_id"] == video_id
        assert [r["plate"] for r in body["plates"]] == ["GJ01AB1234", "GJ05CD6789"]

        # No video_id -> latest video, so the one-video workflow needs no lookup.
        auto = client.get("/api/analysis/plate-usage")
        assert auto.status_code == 200
        assert auto.json()["plates"][0]["plate"] == "GJ01AB1234"

        csv_res = client.get("/api/analysis/plate-usage.csv", params={"video_id": video_id})
        assert csv_res.status_code == 200
        assert csv_res.headers["content-type"].startswith("text/csv")
        lines = [l for l in csv_res.text.strip().splitlines() if l]
        assert lines[0].startswith("plate,vehicle_class,appearances")
        assert "GJ01AB1234" in csv_res.text
        assert len(lines) == 3          # header + two plates

        missing = client.get("/api/analysis/plate-usage", params={"video_id": "nope"})
        assert missing.status_code == 404


def _presence_count(video_id):
    db = SessionLocal()
    try:
        return db.query(VehiclePresence).filter(
            VehiclePresence.video_id == video_id
        ).count()
    finally:
        db.close()


def test_rerun_replaces_previous_measurements(harness):
    """Analysing the same video twice must not double-count its appearances."""
    script = {i: [("a", 40)] for i in range(12)}
    video_id, _ = harness(script, {"a": "GJ01AB1234"})
    assert _presence_count(video_id) == 1

    harness.rerun(video_id)
    assert harness.wait(video_id) == "DONE"
    assert _presence_count(video_id) == 1      # replaced, not appended


def test_rerun_clears_rows_even_when_nothing_is_found(harness):
    """Stale measurements from an earlier run never survive a re-run."""
    script = {i: [("a", 40)] for i in range(12)}
    video_id, _ = harness(script, {"a": "GJ01AB1234"})
    assert _presence_count(video_id) == 1

    # Re-run over footage where the detector now finds nothing at all.
    harness.rerun(video_id, script={}, plates={})
    assert harness.wait(video_id) == "DONE"
    assert _presence_count(video_id) == 0
