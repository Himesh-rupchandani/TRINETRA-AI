"""
Number-plate search + matching video frames — end-to-end.

Exercises the REAL pipeline exactly like ``test_video_analysis.py``: real
video decoding, real tracking, real storage, real API. Only the two model
stages (YOLO detection and OCR) are stubbed so the suite is deterministic on
a CPU-only box. The frame annotation/storage code added for the plate-search
feature (``video_analysis_service.annotate_frame`` and the ``frame_ref``
write in ``finalize``) runs for real and is asserted here.

Scenario (prefix ``TCAMS`` so no other suite's rows are touched):

    TCAMS1 — TWO vehicles, both read GJ09QR5678  -> 2 occurrences, one video
    TCAMS2 — one vehicle reads GJ09QR5678        -> 1 occurrence, other video
    TCAMS3 — one vehicle reads MH12XY4567        -> a different vehicle

GJ09QR5678 is deliberately NOT on the seeded watchlist, so no alerts are
created as a side effect of this suite.
"""
import sys
import time
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
from app.database.models import Camera, VehicleEvent, VideoSource
from app.services import video_analysis_service as vas
from app.services.anpr_pipeline import PlateRead
from app.services.ocr_service import ocr_service
from app.services.plate_detector_service import PlateBox
from app.services.vehicle_detection_service import VehicleDetection, vehicle_detection_service

TEST_PREFIX = "TCAMS"
BATCH = "tspssbatch"  # isolates this suite from any other analysis videos
SEARCH_PLATE = "GJ09QR5678"     # seen by TCAMS1 (x2 tracks) and TCAMS2
OTHER_PLATE = "MH12XY4567"      # seen by TCAMS3 only
FRAMES = 30
SIZE = (320, 240)

SCRIPT = {
    "TCAMS1": (SEARCH_PLATE, 0.95, True),
    "TCAMS2": (SEARCH_PLATE, 0.91, True),
    "TCAMS3": (OTHER_PLATE, 0.93, True),
}
TWO_VEHICLE_CAMERAS = {"TCAMS1"}

_TLS = __import__("threading").local()


# --------------------------------------------------------------------------- #
# Stubs + fixtures (same pattern as test_video_analysis.py)
# --------------------------------------------------------------------------- #
def _write_clip(path: Path, frames: int = FRAMES) -> None:
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, SIZE)
    for i in range(frames):
        frame = np.full((SIZE[1], SIZE[0], 3), 40, dtype=np.uint8)
        cv2.rectangle(frame, (40 + i, 60), (200 + i, 180), (200, 200, 200), -1)
        w.write(frame)
    w.release()


def _fake_detect(frame):
    cam = getattr(_TLS, "camera", "")
    h, w = frame.shape[:2]
    if cam in TWO_VEHICLE_CAMERAS:
        return [
            VehicleDetection(x1=20, y1=60, x2=180, y2=min(h - 1, 180),
                             class_name="car", confidence=0.92),
            VehicleDetection(x1=200, y1=60, x2=min(w - 1, 310), y2=min(h - 1, 180),
                             class_name="car", confidence=0.90),
        ]
    return [VehicleDetection(x1=40, y1=60, x2=min(w - 1, 220), y2=min(h - 1, 180),
                             class_name="car", confidence=0.92)]


def _fake_read(frame, bbox, vehicle_class="car"):
    plate, conf, indian = SCRIPT.get(getattr(_TLS, "camera", ""), (None, 0.0, False))
    if not plate:
        return None
    # A plate-shaped box in the lower part of the vehicle box, like the real
    # plate detector returns — the pipeline must crop exactly this region.
    x1, y1, x2, y2 = (int(v) for v in bbox)
    bw, bh = x2 - x1, y2 - y1
    pbox = PlateBox(x1=x1 + int(bw * 0.30), y1=y1 + int(bh * 0.55),
                    x2=x1 + int(bw * 0.75), y2=y1 + int(bh * 0.80),
                    confidence=0.9, source="model")
    return PlateRead(raw=plate, normalized=plate, confidence=conf,
                     ocr_confidence=conf, indian_format=indian, plate_box=pbox)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    init_db()
    from app.main import app

    @asynccontextmanager
    async def noop_lifespan(app):  # skip camera threads
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    original_detect = vehicle_detection_service.detect
    original_ensure = vehicle_detection_service._ensure_model
    original_model = vehicle_detection_service._model
    original_read = vas.read_plate_for_vehicle
    original_engine = ocr_service._engine
    original_attempted = ocr_service._attempted
    original_run = vas._run_video

    vehicle_detection_service.detect = _fake_detect
    vehicle_detection_service._ensure_model = lambda: object()
    vehicle_detection_service._model = object()
    vas.read_plate_for_vehicle = _fake_read
    ocr_service._engine, ocr_service._attempted = object(), True

    def _run_with_camera(video_id: str):
        """Runs inside the worker thread: tag it with the video it is reading."""
        db = SessionLocal()
        try:
            v = db.query(VideoSource).filter(VideoSource.video_id == video_id).first()
            _TLS.camera = v.camera_id if v else ""
        finally:
            db.close()
        return original_run(video_id)

    vas._run_video = _run_with_camera

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()
    vehicle_detection_service.detect = original_detect
    vehicle_detection_service._ensure_model = original_ensure
    vehicle_detection_service._model = original_model
    vas.read_plate_for_vehicle = original_read
    vas._run_video = original_run
    ocr_service._engine, ocr_service._attempted = original_engine, original_attempted

    db = SessionLocal()
    try:
        videos = db.query(VideoSource).filter(
            VideoSource.camera_id.like(f"{TEST_PREFIX}%")
        ).all()
        for v in videos:
            try:
                if v.file_path:
                    Path(v.file_path).unlink(missing_ok=True)
            except OSError:
                pass
        db.query(VehicleEvent).filter(
            VehicleEvent.camera_id.like(f"{TEST_PREFIX}%")
        ).delete(synchronize_session=False)
        db.query(VideoSource).filter(
            VideoSource.camera_id.like(f"{TEST_PREFIX}%")
        ).delete(synchronize_session=False)
        db.query(Camera).filter(
            Camera.camera_id.like(f"{TEST_PREFIX}%")
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    # Remove the evidence frames this suite wrote.
    ev_root = vas._evidence_root() / "analysis"
    for d in ev_root.glob(f"{TEST_PREFIX.lower()}*"):
        for f in d.glob("*"):
            f.unlink(missing_ok=True)
        d.rmdir()


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("plate_search_clips")
    paths = {}
    for cam in SCRIPT:
        p = d / f"{cam}.mp4"
        _write_clip(p)
        paths[cam] = p
    return paths


def _my_videos(client):
    videos = client.get("/api/analysis/videos", params={"batch_id": BATCH}).json()["videos"]
    return [v for v in videos if v["camera_id"].startswith(TEST_PREFIX)]


def _wait_mine_done(client, timeout=120.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        mine = _my_videos(client)
        if mine and all(v["status"] in ("DONE", "FAILED") for v in mine):
            return mine
        time.sleep(0.4)
    raise AssertionError("plate-search analysis did not finish in time")


@pytest.fixture(scope="module")
def analysed(client, clips):
    files = [("files", (f"{c}.mp4", clips[c].read_bytes(), "video/mp4")) for c in SCRIPT]
    res = client.post("/api/analysis/videos/upload", files=files, data={"batch_id": BATCH})
    assert res.status_code in (200, 201), res.text
    assert res.json()["errors"] == []
    run = client.post("/api/analysis/run", json={})
    assert run.status_code == 200, run.text
    mine = _wait_mine_done(client)
    assert all(v["status"] == "DONE" for v in mine), mine
    return mine


def _events(plate=None):
    db = SessionLocal()
    try:
        q = db.query(VehicleEvent).filter(VehicleEvent.camera_id.like(f"{TEST_PREFIX}%"))
        if plate:
            q = q.filter(VehicleEvent.plate_number == plate)
        rows = q.order_by(VehicleEvent.id.asc()).all()
        return [
            {
                "id": r.id, "camera_id": r.camera_id, "video_id": r.video_id,
                "plate_number": r.plate_number, "plate_confidence": r.plate_confidence,
                "frame_number": r.frame_number, "video_offset_sec": r.video_offset_sec,
                "frame_ref": r.frame_ref, "evidence_ref": r.evidence_ref,
                "bbox": r.bbox, "track_id": r.vehicle_track_id,
            }
            for r in rows
        ]
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 1. Every plate detection stores a FULL annotated frame alongside the record
# --------------------------------------------------------------------------- #
def test_01_full_annotated_frame_is_stored(analysed):
    rows = _events(SEARCH_PLATE)
    assert len(rows) == 3, "2 tracks in TCAMS1 + 1 in TCAMS2"
    for r in rows:
        assert r["frame_ref"], f"event {r['id']} has no stored full frame"
        assert r["frame_ref"].endswith("_frame.jpg")
        path = vas._evidence_root() / r["frame_ref"]
        assert path.is_file(), f"frame file missing on disk: {path}"
        img = cv2.imread(str(path))
        assert img is not None, "stored frame is not a decodable JPEG"
        # It must be the FULL video frame, not a crop of the vehicle.
        assert (img.shape[1], img.shape[0]) == SIZE
        # ...and carry the drawn detection annotation (green box).
        green = ((img[:, :, 1] > 180) & (img[:, :, 2] < 160) & (img[:, :, 0] < 130))
        assert int(green.sum()) > 50, "no detection box was drawn on the stored frame"
        # The pre-existing vehicle crop is still stored, unchanged.
        assert r["evidence_ref"] and r["evidence_ref"] != r["frame_ref"]
        crop = cv2.imread(str(vas._evidence_root() / r["evidence_ref"]))
        assert crop is not None
        assert crop.shape[0] < img.shape[0] or crop.shape[1] < img.shape[1]
        # ANPR crop: the plate-ONLY image at {stem}_plate.jpg (the URL the
        # frontend's evidence panel resolves) — real pixels from the frame,
        # strictly inside the vehicle crop and plate-shaped (wider than tall).
        plate_ref = r["evidence_ref"].replace(".jpg", "_plate.jpg")
        ppath = vas._evidence_root() / plate_ref
        assert ppath.is_file(), f"ANPR plate crop missing: {ppath}"
        pimg = cv2.imread(str(ppath))
        assert pimg is not None
        assert pimg.shape[0] < crop.shape[0] and pimg.shape[1] < crop.shape[1]
        assert pimg.shape[1] > pimg.shape[0], "a plate crop is wider than tall"
        # and it is NOT the vehicle crop bytes
        assert ppath.read_bytes() != (vas._evidence_root() / r["evidence_ref"]).read_bytes()


# --------------------------------------------------------------------------- #
# 2. The stored frame is served by the existing evidence endpoint
# --------------------------------------------------------------------------- #
def test_02_evidence_endpoint_serves_the_frame(client, analysed):
    r = _events(SEARCH_PLATE)[0]
    res = client.get(f"/api/evidence/{r['frame_ref']}")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert len(res.content) > 1000
    # the ANPR crop URL the frontend builds (evidence_ref + _plate.jpg) serves
    plate_url = f"/api/evidence/{r['evidence_ref'].replace('.jpg', '_plate.jpg')}"
    pres = client.get(plate_url)
    assert pres.status_code == 200, f"ANPR crop must be served: {plate_url}"
    assert pres.headers["content-type"] == "image/jpeg"


# --------------------------------------------------------------------------- #
# 3. Search returns EVERY occurrence with frame, timestamp, video, confidence
# --------------------------------------------------------------------------- #
def test_03_search_returns_all_occurrences(client, analysed):
    res = client.get("/api/analysis/search", params={"plate": SEARCH_PLATE, "batch_id": BATCH})
    assert res.status_code == 200
    body = res.json()
    assert body["found"] is True
    assert body["plate"] == SEARCH_PLATE
    assert body["total"] == 3
    assert len(body["results"]) == 3
    for occ in body["results"]:
        assert occ["plate"] == SEARCH_PLATE
        assert occ["frame_url"] and occ["frame_url"].startswith("/api/evidence/")
        assert occ["video_url"] and occ["video_url"].endswith("/file")
        assert occ["video_name"].endswith(".mp4")
        assert occ["timestamp"].count(":") == 2          # HH:MM:SS in the video
        assert occ["timestamp_sec"] is not None
        assert occ["frame_number"] is not None
        assert 0.0 < occ["confidence"] <= 1.0
        assert occ["bbox"] and len(occ["bbox"]) == 4
        assert occ["detected_at"]                        # detection date/time
    # one occurrence comes from the second video (cross-video search)
    assert {occ["camera_id"] for occ in body["results"]} == {"TCAMS1", "TCAMS2"}


# --------------------------------------------------------------------------- #
# 4. Formatting differences normalise to the same search
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("variant", [
    "GJ09QR5678", "gj 09 qr 5678", "GJ-09-QR-5678", "  gj09.qr_5678  ",
])
def test_04_format_variants_match_the_same_plate(client, analysed, variant):
    body = client.get("/api/analysis/search", params={"plate": variant, "batch_id": BATCH}).json()
    assert body["normalized_query"] == SEARCH_PLATE
    assert body["found"] is True
    assert body["total"] == 3


# --------------------------------------------------------------------------- #
# 5. Pagination keeps the UI usable for many occurrences
# --------------------------------------------------------------------------- #
def test_05_pagination(client, analysed):
    p1 = client.get("/api/analysis/search",
                    params={"plate": SEARCH_PLATE, "batch_id": BATCH, "page": 1, "limit": 2}).json()
    assert p1["total"] == 3 and p1["total_pages"] == 2
    assert len(p1["results"]) == 2 and p1["page"] == 1

    p2 = client.get("/api/analysis/search",
                    params={"plate": SEARCH_PLATE, "batch_id": BATCH, "page": 2, "limit": 2}).json()
    assert len(p2["results"]) == 1 and p2["page"] == 2
    # pages never overlap
    ids1 = {o["event_id"] for o in p1["results"]}
    ids2 = {o["event_id"] for o in p2["results"]}
    assert not (ids1 & ids2) and len(ids1 | ids2) == 3

    # an out-of-range page clamps to the last page instead of returning blanks
    p99 = client.get("/api/analysis/search",
                     params={"plate": SEARCH_PLATE, "batch_id": BATCH, "page": 99, "limit": 2}).json()
    assert p99["page"] == 2 and len(p99["results"]) == 1

    bad = client.get("/api/analysis/search", params={"plate": SEARCH_PLATE, "batch_id": BATCH, "page": 0})
    assert bad.status_code == 422


# --------------------------------------------------------------------------- #
# 6. A plate that was never detected gives a clean not-found, never a 500
# --------------------------------------------------------------------------- #
def test_06_no_results_state(client, analysed):
    res = client.get("/api/analysis/search", params={"plate": "DL09ZZ0000", "batch_id": BATCH})
    assert res.status_code == 200
    body = res.json()
    assert body["found"] is False
    assert body["total"] == 0
    assert body["results"] == []
    assert body["vehicle"] is None


# --------------------------------------------------------------------------- #
# 7. Empty / whitespace-only search input is rejected with a clear message
# --------------------------------------------------------------------------- #
def test_07_empty_search_is_rejected(client, analysed):
    res = client.get("/api/analysis/search", params={"plate": "   "})
    assert res.status_code == 422
    assert "number plate" in res.json()["detail"].lower()
    missing = client.get("/api/analysis/search")
    assert missing.status_code == 422


# --------------------------------------------------------------------------- #
# 8. Different plates never cross-match
# --------------------------------------------------------------------------- #
def test_08_different_plate_does_not_cross_match(client, analysed):
    body = client.get("/api/analysis/search", params={"plate": OTHER_PLATE, "batch_id": BATCH}).json()
    assert body["found"] is True
    assert body["total"] == 1
    assert all(o["plate"] == OTHER_PLATE for o in body["results"])
    assert all(o["camera_id"] == "TCAMS3" for o in body["results"])


# --------------------------------------------------------------------------- #
# 9. A missing frame file is reported by the evidence API; search still works
# --------------------------------------------------------------------------- #
def test_09_missing_frame_is_handled(client, analysed):
    rows = _events(OTHER_PLATE)
    frame_path = vas._evidence_root() / rows[0]["frame_ref"]
    frame_path.unlink()  # simulate a deleted evidence file

    gone = client.get(f"/api/evidence/{rows[0]['frame_ref']}")
    assert gone.status_code == 404

    # The search itself never touches the disk — the record is still returned
    # (with its reference) so the UI can show a "frame unavailable" tile.
    body = client.get("/api/analysis/search", params={"plate": OTHER_PLATE, "batch_id": BATCH}).json()
    assert body["total"] == 1
    assert body["results"][0]["frame_url"].endswith(rows[0]["frame_ref"])


# --------------------------------------------------------------------------- #
# 10. Legacy rows without a stored frame degrade to frame_url=None
# --------------------------------------------------------------------------- #
def test_10_row_without_frame_ref_returns_null_frame_url(client, analysed):
    db = SessionLocal()
    try:
        row = (db.query(VehicleEvent)
               .filter(VehicleEvent.camera_id == "TCAMS2")
               .first())
        assert row is not None and row.evidence_ref
        row.frame_ref = None
        db.commit()
    finally:
        db.close()

    body = client.get("/api/analysis/search", params={"plate": SEARCH_PLATE, "batch_id": BATCH}).json()
    legacy = [o for o in body["results"] if o["camera_id"] == "TCAMS2"]
    assert len(legacy) == 1
    assert legacy[0]["frame_url"] is None
    assert legacy[0]["crop_url"] and legacy[0]["crop_url"].startswith("/api/evidence/")


# --------------------------------------------------------------------------- #
# 11. Deleting a video removes its occurrences from search (no stale frames)
# --------------------------------------------------------------------------- #
def test_11_deleted_video_removes_its_occurrences(client, analysed):
    videos = {v["camera_id"]: v["video_id"] for v in _my_videos(client)}
    vid = videos["TCAMS2"]

    gone = client.get(f"/api/analysis/videos/{vid}/file")
    assert gone.status_code == 200  # the video streams before deletion

    assert client.delete(f"/api/analysis/videos/{vid}").status_code == 200

    body = client.get("/api/analysis/search", params={"plate": SEARCH_PLATE, "batch_id": BATCH}).json()
    assert body["total"] == 2
    assert {o["camera_id"] for o in body["results"]} == {"TCAMS1"}
    assert client.get(f"/api/analysis/videos/{vid}/file").status_code == 404
